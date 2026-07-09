#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${HOTSPOT_PROJECT_DIR:-/var/www/hotspot-radar}"
ENV_FILE="${HOTSPOT_ENV_FILE:-/etc/hotspot-radar.env}"
PYTHON_BIN="${PYTHON_BIN:-/usr/bin/python3}"

cd "$PROJECT_DIR"
mkdir -p output logs
export TZ="${HOTSPOT_TZ:-Asia/Shanghai}"
export PYTHONUNBUFFERED=1

LOG_FILE="${HOTSPOT_CRON_LOG:-logs/hotspot_cron.log}"
LOCK_FILE="${HOTSPOT_CRON_LOCK:-logs/hotspot_cron.lock}"

exec 9>"$LOCK_FILE"
if command -v flock >/dev/null 2>&1; then
  if ! flock -n 9; then
    echo "===== $(date '+%F %T') hotspot skipped: previous run still active =====" >> "$LOG_FILE"
    exit 0
  fi
fi

if [ -f "$ENV_FILE" ]; then
  # shellcheck disable=SC1090
  source "$ENV_FILE"
fi

{
  echo "===== $(date '+%F %T') hotspot start ====="
  "$PYTHON_BIN" run_daily_hotspots.py --date "$(date +%Y%m%d)" --output-dir output --sources-dir sources --top 20 --min-score 5.8
  "$PYTHON_BIN" export_wechat_context.py || true
  "$PYTHON_BIN" scripts/indexnow_notify.py --site-root . --sitemap sitemap.xml --state logs/indexnow_state.json || true
  "$PYTHON_BIN" scripts/baidu_submit.py --site-root . --sitemap sitemap.xml --state logs/baidu_submit_state.json || true
  "$PYTHON_BIN" scripts/hotspot_health_alert.py --health output/health.json || true
  "$PYTHON_BIN" scripts/send_hermes_daily_digest.py || true
  ls -lh output/latest_hotspots_ranked.json output/latest_hotspots_windows.json output/latest_daily_brief.json output/health.json
  echo "===== $(date '+%F %T') hotspot done ====="
} >> "$LOG_FILE" 2>&1
