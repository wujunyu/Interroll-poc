#!/usr/bin/env bash
# rollback：骨架占位，B 批补实现。要求：幂等、可重复执行、失败非零退出。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
COMPOSE="docker compose --env-file $ROOT/.env -f $ROOT/deploy/compose/compose.yaml"

echo "[rollback] TODO(B 批)：实现在 $ROOT 下执行"
exit 0
