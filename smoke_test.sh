#!/usr/bin/env bash
set -uo pipefail

API_URL="${API_URL:-http://localhost:8000}"
FAIL=0

check() {
  local name="$1" url="$2"
  if curl -fsS --max-time 5 "$url" > /dev/null; then
    echo "PASS: $name"
  else
    echo "FAIL: $name"
    FAIL=1
  fi
}

check "liveness (/health)" "$API_URL/health"
check "readiness (/ready)" "$API_URL/ready"

# Redis reachability, independent of the app
if docker compose exec -T redis redis-cli ping | grep -q PONG; then
  echo "PASS: redis"
else
  echo "FAIL: redis"
  FAIL=1
fi

# Worker: confirm the container is up and not crash-looping
if docker compose ps worker | grep -q "Up"; then
  echo "PASS: worker running"
else
  echo "FAIL: worker not running"
  FAIL=1
fi

exit $FAIL
