#!/usr/bin/env bash
# 开发辅助：起基础设施 + 本地跑三个服务（B 批补）
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
echo "[dev] TODO(B 批)：make up-infra 后本地起 ingest/api/web"
