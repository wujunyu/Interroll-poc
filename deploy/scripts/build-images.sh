#!/usr/bin/env bash
# 用 podman 构建四个应用镜像，可选导入 docker 供 compose 运行。
#
#   bash deploy/scripts/build-images.sh            # 只构建
#   bash deploy/scripts/build-images.sh --load     # 构建后导入 docker
#   TAG=0.3.0 bash deploy/scripts/build-images.sh  # 指定版本
#
# 说明：基础镜像与包源都指向国内镜像站（Alpine→阿里云、pip→清华、npm→npmmirror），
# 换站点改各 Containerfile 顶部两行即可。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TAG="${TAG:-$(grep -E '^APP_VERSION=' "$ROOT/.env" 2>/dev/null | cut -d= -f2)}"
TAG="${TAG:-0.3.1}"
LOAD="${1:-}"

command -v podman >/dev/null || { echo "没装 podman：sudo apt-get install -y podman uidmap" >&2; exit 2; }

echo "[build] tag=$TAG  engine=podman $(podman --version | awk '{print $3}')"
for svc in simulator ingest api web; do
  t0=$(date +%s)
  podman build --pull=never \
    -t "interroll-poc-$svc:$TAG" \
    -f "$ROOT/code/$svc/Containerfile" \
    "$ROOT/code/$svc" >/dev/null
  echo "  ✓ $svc ($(( $(date +%s) - t0 ))s)"
done

if [ "$LOAD" = "--load" ]; then
  echo "[build] 导入 docker（compose 运行用）"
  for svc in simulator ingest api web; do
    podman save "interroll-poc-$svc:$TAG" | docker load >/dev/null
    docker tag "localhost/interroll-poc-$svc:$TAG" "interroll-poc-$svc:$TAG" 2>/dev/null || true
  done
fi

echo "[build] 完成："
podman images --format '  {{.Repository}}:{{.Tag}} {{.Size}}' | grep "interroll-poc.*$TAG" || true
