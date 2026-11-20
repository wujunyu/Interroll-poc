#!/usr/bin/env bash
# 回滚：切镜像 tag → 重建 → 等健康检查 → 打印耗时。
# 用法：make rollback TAG=0.3.0   或   bash deploy/scripts/rollback.sh 0.3.0
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TAG="${1:-${TAG:-}}"
COMPOSE="docker compose --env-file $ROOT/.env -f $ROOT/deploy/compose/compose.yaml"
API_PORT="$(grep -E '^API_PORT=' "$ROOT/.env" | cut -d= -f2 || echo 8001)"
API_PORT="${API_PORT:-8001}"

if [ -z "$TAG" ]; then
  echo "用法：bash deploy/scripts/rollback.sh <TAG>   （当前 APP_VERSION=$(grep -E '^APP_VERSION=' "$ROOT/.env" | cut -d= -f2)）" >&2
  exit 2
fi

START=$(date +%s)
echo "[rollback] → $TAG"

# 1) 先确认目标 tag 的镜像在本地，不在就别动线上
for svc in api ingest web; do
  if ! docker image inspect "interroll-poc-$svc:$TAG" >/dev/null 2>&1; then
    echo "[rollback] ✗ 本地没有 interroll-poc-$svc:$TAG，中止（不做半截回滚）" >&2
    exit 3
  fi
done

# 2) 切版本并重建（只重建应用容器，不碰库）
sed -i "s/^APP_VERSION=.*/APP_VERSION=$TAG/" "$ROOT/.env"
( cd "$ROOT" && APP_VERSION="$TAG" $COMPOSE up -d --no-build api ingest web ) >/dev/null

# 3) 健康检查：等 /healthz 报出目标版本
echo -n "[rollback] 等待 /healthz 报 $TAG "
for i in $(seq 1 30); do
  V="$(curl -fsS "http://127.0.0.1:${API_PORT}/healthz" 2>/dev/null | grep -o "\"version\":\"[^\"]*\"" | cut -d'"' -f4 || true)"
  if [ "$V" = "$TAG" ]; then
    echo "→ ok（$(($(date +%s) - START))s）"
    exit 0
  fi
  echo -n "."
  sleep 1
done

echo " ✗ 30s 内没等到 $TAG，看日志：make logs" >&2
exit 4
