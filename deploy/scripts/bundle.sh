#!/usr/bin/env bash
# 打离线交付包：镜像 tar + compose + 环境模板 + 运维脚本 → dist/interroll-poc-<ver>.tar.gz
#
#   bash deploy/scripts/bundle.sh              # 用 .env 里的 APP_VERSION
#   TAG=0.3.0 bash deploy/scripts/bundle.sh
#
# 客户现场：解包 → docker load -i images.tar → 改 .env → docker compose up -d
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TAG="${TAG:-$(grep -E '^APP_VERSION=' "$ROOT/.env" 2>/dev/null | cut -d= -f2)}"
TAG="${TAG:-0.3.1}"
OUT="$ROOT/dist"
WORK="$(mktemp -d)"
DIR="$WORK/interroll-poc-$TAG"

mkdir -p "$DIR"/{compose,scripts,runbook} "$OUT"

echo "[bundle] 版本 $TAG"
IMAGES=(
  "interroll-poc-api:$TAG"
  "interroll-poc-ingest:$TAG"
  "interroll-poc-web:$TAG"
  "eclipse-mosquitto:2"
  "timescale/timescaledb:latest-pg17"
)

ENGINE="${ENGINE:-podman}"   # podman 是发布路径的正主；没有时回退 docker
if ! command -v "$ENGINE" >/dev/null 2>&1; then
  echo "  ! 没有 $ENGINE，回退 docker save" >&2
  ENGINE=docker
fi
echo "[bundle] 检查镜像（engine=$ENGINE）"
for img in "${IMAGES[@]}"; do
  if [ "$ENGINE" = podman ]; then
    podman image exists "$img" || { echo "  ✗ podman 里缺 $img" >&2; exit 2; }
  else
    docker image inspect "$img" >/dev/null 2>&1 || { echo "  ✗ 缺 $img" >&2; exit 2; }
  fi
done

echo "[bundle] 导出镜像（这一步最慢，约 3GB）"
# 关键：podman 不加 -m 会把后面的参数当成同一个镜像的 tags，打出只有 1 个镜像、5 个名字的坏包
if [ "$ENGINE" = podman ]; then
  podman save -m -o "$DIR/images.tar" "${IMAGES[@]}"
else
  docker save -o "$DIR/images.tar" "${IMAGES[@]}"
fi

echo "[bundle] 收编排与脚本"
cp "$ROOT/deploy/compose/compose.yaml" "$DIR/compose/"
cp "$ROOT/.env.example" "$DIR/.env.example"
cp "$ROOT/deploy/scripts/rollback.sh" "$ROOT/deploy/scripts/diag.sh" "$DIR/scripts/"

# podman 给本地镜像加的 localhost/ 前缀，load 之后必须摘掉，否则 compose 的 image: 名字对不上
cat > "$DIR/scripts/load.sh" <<LOAD
#!/usr/bin/env bash
set -euo pipefail
TAG="$TAG"
cd "\$(dirname "\$0")/.."
if command -v docker >/dev/null 2>&1; then
  echo "[load] docker load"; docker load -i images.tar
  for svc in api ingest web; do
    docker tag "localhost/interroll-poc-\$svc:\$TAG" "interroll-poc-\$svc:\$TAG" 2>/dev/null || true
  done
else
  echo "[load] podman load"; podman load -i images.tar
  for svc in api ingest web; do
    podman tag "localhost/interroll-poc-\$svc:\$TAG" "interroll-poc-\$svc:\$TAG" 2>/dev/null || true
  done
fi
echo "[load] 完成"
LOAD
chmod +x "$DIR/scripts/load.sh"
cp "$ROOT/docs/runbook/RB-01-部署.md" "$ROOT/docs/runbook/RB-02-回滚.md" "$DIR/runbook/"

cat > "$DIR/安装说明.txt" <<TXT
Interroll PoC $TAG —— 离线安装

1) 导入镜像（约 3GB，约 1 分钟）
   bash scripts/load.sh
   # 它会 load 镜像并摘掉 podman 的 localhost/ 前缀，否则 compose 找不到镜像

2) 准备环境
   cp .env.example .env
   vi .env            # 必改 DB_PASSWORD；确认端口 1884/5433/8001/5174 空闲

3) 起栈
   docker compose --env-file .env -f compose/compose.yaml up -d

4) 验收
   curl -s localhost:8001/healthz        # ok:true, version:$TAG
   浏览器打开 http://<本机IP>:5174

5) 回滚 / 诊断
   bash scripts/rollback.sh <另一个版本>   # 需先 docker load 那个版本的 images.tar
   bash scripts/diag.sh                    # 出 diag-<ts>.zip

注意：compose 里 pull_policy=never，镜像必须来自本包，现场不会联网拉取。
TXT

echo "[bundle] 打包"
( cd "$WORK" && tar czf "$OUT/interroll-poc-$TAG.tar.gz" "interroll-poc-$TAG" )
rm -rf "$WORK"

ls -lh "$OUT/interroll-poc-$TAG.tar.gz"
echo "[bundle] 内容："
tar tzf "$OUT/interroll-poc-$TAG.tar.gz" | head -12
