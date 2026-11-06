#!/bin/bash
set -euo pipefail

cd /opt/we-mp-rss/source

# Keep one request sequence at a time and never pile up if WeRead is slow.
exec 9>/run/lock/we-mp-rss-daily-douban.lock
flock -n 9 || exit 0

exec timeout --signal=TERM --kill-after=10s 100s \
  docker exec -i -w /app compose-we-mp-rss-1 \
  /app/env_x86_64/bin/python - \
  < /opt/we-mp-rss/source/deploy/security/fetch_daily_douban.py
