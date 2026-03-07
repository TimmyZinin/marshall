#!/bin/bash
# Marshall healthcheck — runs every 5 min via cron
# Cron: */5 * * * * /opt/marshall/scripts/healthcheck.sh

URL="http://127.0.0.1:8100/api/health"
RESPONSE=$(curl -sf -m 5 "$URL" 2>/dev/null)

if [ $? -ne 0 ]; then
    echo "$(date): Marshall DOWN — no response from $URL"
    # Restart containers
    cd /opt/marshall && docker compose restart app
    exit 1
fi

echo "$RESPONSE" | grep -q '"ok"'
if [ $? -ne 0 ]; then
    echo "$(date): Marshall UNHEALTHY — $RESPONSE"
    exit 1
fi
