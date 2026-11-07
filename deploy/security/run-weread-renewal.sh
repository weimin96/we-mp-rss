#!/bin/bash
set -euo pipefail

cd /opt/we-mp-rss/source

# Shared lock: never rewrite wx.lic while the feed worker is reading it.
exec 9>/run/lock/we-mp-rss-daily-douban.lock
flock -n 9 || exit 0

exec timeout --signal=TERM --kill-after=5s 35s \
  docker exec -i -w /app compose-we-mp-rss-1 \
  /app/env_x86_64/bin/python - \
  < /opt/we-mp-rss/source/deploy/security/renew_weread_cookie.py
