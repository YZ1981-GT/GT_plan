#!/usr/bin/env bash
# E2E: Zero-downtime rolling update integration test
# Requires: Docker Compose + docker-backend profile running
# Feature: zero-downtime-deployment, Property 20 (real Docker-level validation)
set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
PROFILE="--profile docker-backend"
TRAFFIC_LOG=$(mktemp)
TRAFFIC_PID=""

cleanup() {
    [ -n "$TRAFFIC_PID" ] && kill "$TRAFFIC_PID" 2>/dev/null || true
    rm -f "$TRAFFIC_LOG"
    docker compose -f "$COMPOSE_FILE" $PROFILE down --timeout 10 2>/dev/null || true
}
trap cleanup EXIT

echo "=== Starting services ==="
docker compose -f "$COMPOSE_FILE" $PROFILE up -d --build --wait

echo "=== Waiting for readyz ==="
for i in $(seq 1 30); do
    if curl -sf http://localhost/readyz > /dev/null 2>&1; then
        echo "Backend ready after ${i}s"
        break
    fi
    sleep 1
done

echo "=== Starting continuous traffic ==="
# Background: hit /api/version every 200ms, log status codes
(while true; do
    code=$(curl -s -o /dev/null -w "%{http_code}" http://localhost/api/version 2>/dev/null || echo "000")
    echo "$code" >> "$TRAFFIC_LOG"
    sleep 0.2
done) &
TRAFFIC_PID=$!

echo "=== Executing rolling update ==="
sleep 2  # let some baseline traffic accumulate
./scripts/deploy/rolling_update.sh "$(docker compose -f "$COMPOSE_FILE" images backend -q | head -1)" || {
    echo "FAIL: rolling_update.sh exited non-zero"
    exit 1
}

echo "=== Stopping traffic ==="
sleep 3  # let post-update traffic settle
kill "$TRAFFIC_PID" 2>/dev/null || true
TRAFFIC_PID=""

echo "=== Analyzing results ==="
TOTAL=$(wc -l < "$TRAFFIC_LOG")
ERRORS_5XX=$(grep -c "^5" "$TRAFFIC_LOG" || true)
ERRORS_000=$(grep -c "^000" "$TRAFFIC_LOG" || true)

echo "Total requests: $TOTAL"
echo "5xx errors: $ERRORS_5XX"
echo "Connection failures (000): $ERRORS_000"

if [ "$ERRORS_5XX" -gt 0 ]; then
    echo "FAIL: Got $ERRORS_5XX 5xx responses during rolling update!"
    exit 1
fi

if [ "$ERRORS_000" -gt "$((TOTAL / 10))" ]; then
    echo "WARN: High connection failure rate ($ERRORS_000/$TOTAL)"
fi

echo "=== PASS: Zero 5xx during rolling update ($TOTAL requests) ==="
