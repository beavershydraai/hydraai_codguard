#!/usr/bin/env bash
# Start the backend image and check it serves requests the way Cloud Run will run it.
# Usage: smoke_test_image.sh <image>
set -euo pipefail
IMAGE="$1"
cleanup() { docker rm -f api api-port >/dev/null 2>&1 || true; }
trap cleanup EXIT

fail() {
  echo "::error::$1"
  docker logs api 2>&1 | tail -50 || true
  exit 1
}

wait_healthy() {
  for _ in $(seq 1 30); do
    curl -fsS "http://127.0.0.1:$1/health" >/dev/null 2>&1 && return 0
    sleep 1
  done
  return 1
}

docker run -d --name api -p 8080:8080 "$IMAGE" >/dev/null
wait_healthy 8080 || fail "Container did not answer /health on port 8080 within 30s"

curl -fsS http://127.0.0.1:8080/health | grep -q '"ok"' || fail "/health did not return ok"
curl -fsS http://127.0.0.1:8080/openapi.json \
  | python3 -c 'import json, sys; assert json.load(sys.stdin)["info"]["title"] == "COD Guard API"' \
  || fail "/openapi.json is missing or wrong"
code=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:8080/api/v1/dashboard/summary?from=2026-10-01&to=2026-10-15")
[ "$code" = "501" ] || fail "Expected 501 from a contract stub, got $code"
uid=$(docker exec api id -u)
[ "$uid" != "0" ] || fail "Container runs as root"

# Cloud Run injects PORT; the server must follow it.
docker run -d --name api-port -e PORT=9090 -p 9090:9090 "$IMAGE" >/dev/null
wait_healthy 9090 || fail "Container ignored PORT=9090"

echo "Smoke test passed: health, OpenAPI, contract stub, non-root user, PORT override."
