#!/usr/bin/env bash
# 诊断包：system / config(脱敏) / logs / mqtt-tail / db-stats → dist/diag-<ts>.zip
# 目标：集成商不用登机器，拿到 zip 就能发邮件。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUT="$ROOT/dist"
TS="$(date +%Y%m%d-%H%M%S)"
WORK="$(mktemp -d)"
PKG="$WORK/interroll-diag-$TS"
ENGINE="${ENGINE:-docker}"
COMPOSE="$ENGINE compose --env-file $ROOT/.env -f $ROOT/deploy/compose/compose.yaml"

mkdir -p "$PKG"/{logs,config} "$OUT"

echo "[diag] 收集系统信息"
{
  echo "version: $(grep -E '^APP_VERSION=' "$ROOT/.env" | cut -d= -f2)"
  echo "time: $(date -Iseconds)"
  echo "host: $(uname -a)"
  echo
  echo "--- containers"
  $COMPOSE ps 2>/dev/null || true
  echo
  echo "--- healthz"
  curl -fsS "http://127.0.0.1:$(grep -E '^API_PORT=' "$ROOT/.env" | cut -d= -f2 || echo 8001)/healthz" 2>/dev/null || echo "api 不可达"
} > "$PKG/system.txt" 2>&1

echo "[diag] 收集配置（脱敏）"
# 只保留非密码行，密码统一替换
grep -vE 'PASSWORD|SECRET|TOKEN' "$ROOT/.env" > "$PKG/config/env.redacted" 2>/dev/null || true
cp "$ROOT/deploy/compose/compose.yaml" "$PKG/config/" 2>/dev/null || true

echo "[diag] 收集日志（每个容器 300 行）"
for svc in mqtt db ingest api web; do
  $COMPOSE logs --tail=300 "$svc" > "$PKG/logs/$svc.log" 2>&1 || true
done

echo "[diag] 抓 MQTT 尾巴（10 条，3 秒超时）"
timeout 5 $ENGINE run --rm --network host eclipse-mosquitto:2 \
  mosquitto_sub -h 127.0.0.1 -p "${MQTT_PORT:-1884}" -t 'line/#' -C 10 -W 3 -v 2>/dev/null \
  > "$PKG/mqtt-tail.ndjson" || echo "(没有收到消息)" > "$PKG/mqtt-tail.ndjson"

echo "[diag] 收集库统计"
$ENGINE exec -i -e PGPASSWORD="$(grep -E '^DB_PASSWORD=' "$ROOT/.env" | cut -d= -f2)" \
  interroll-poc-db-1 psql -U "$(grep -E '^DB_USER=' "$ROOT/.env" | cut -d= -f2)" \
  -d "$(grep -E '^DB_NAME=' "$ROOT/.env" | cut -d= -f2)" <<'SQL' > "$PKG/db-stats.txt" 2>&1 || echo "库不可达" > "$PKG/db-stats.txt"
\pset pager off
select 'telemetry 行数' k, count(*)::text v from telemetry
union all select '聚合行数', count(*)::text from telemetry_1m
union all select '最新水位', max(ts)::text from telemetry;
select hypertable_name, pg_size_pretty(hypertable_size(format('%I', hypertable_name)::regclass)) as size
from timescaledb_information.hypertables;
SQL

echo "[diag] 打包"
( cd "$WORK" && zip -qr "$OUT/interroll-diag-$TS.zip" "interroll-diag-$TS" )
rm -rf "$WORK"
ls -lh "$OUT/interroll-diag-$TS.zip"
