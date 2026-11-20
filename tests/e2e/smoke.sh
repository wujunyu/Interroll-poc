#!/usr/bin/env bash
# 端到端冒烟：起栈 → 等出数 → 断网 → 恢复 → 断言零丢点（B 批补实现）
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
echo "[smoke] TODO(B 批)：在 $ROOT 下执行"
exit 0
