#!/usr/bin/env bash
# Start the frontend image and check it serves the app and forwards /api the way Cloud Run will run it.
# Usage: smoke_test_web.sh <image>
set -euo pipefail
IMAGE="$1"
STUB_PORT=9099
stub_dir=$(mktemp -d)
stub_pid=""
cleanup() {
  docker rm -f web web-port >/dev/null 2>&1 || true
  if [ -n "$stub_pid" ]; then kill "$stub_pid" 2>/dev/null || true; fi
  rm -rf "$stub_dir"
}
trap cleanup EXIT

fail() {
  echo "::error::$1"
  docker logs web 2>&1 | tail -50 || true
  exit 1
}

wait_up() {
  for _ in $(seq 1 30); do
    curl -fsS "http://127.0.0.1:$1/" >/dev/null 2>&1 && return 0
    sleep 1
  done
  return 1
}

# Stand-in backend: a file server, so a forwarded /api/v1/ping returns "pong".
mkdir -p "$stub_dir/api/v1"
echo pong >"$stub_dir/api/v1/ping"
python3 -m http.server "$STUB_PORT" --bind 0.0.0.0 --directory "$stub_dir" >/dev/null 2>&1 &
stub_pid=$!

docker run -d --name web -p 8080:8080 --add-host host.docker.internal:host-gateway \
  -e API_ORIGIN="http://host.docker.internal:$STUB_PORT" "$IMAGE" >/dev/null
wait_up 8080 || fail "Container did not answer / on port 8080 within 30s"

index=$(curl -fsS http://127.0.0.1:8080/)
grep -q 'id="root"' <<<"$index" || fail "/ did not return the app's index.html"
curl -fsS http://127.0.0.1:8080/orders/123 | grep -q 'id="root"' \
  || fail "A client-side route did not fall back to index.html"
asset=$(grep -oE '/assets/[^"]+\.js' <<<"$index" | head -1)
[ -n "$asset" ] || fail "index.html links no script under /assets/"
curl -fsSI "http://127.0.0.1:8080$asset" | grep -qi '^cache-control: public, max-age=31536000, immutable' \
  || fail "$asset is not served with a long cache"
[ "$(curl -fsS http://127.0.0.1:8080/api/v1/ping)" = pong ] || fail "/api was not forwarded to API_ORIGIN"
# A 3 MB upload (an order history) must reach the backend, not stop at nginx with 413.
big="$stub_dir/upload.bin"
head -c 3000000 /dev/zero >"$big"
code=$(curl -s -o /dev/null -w '%{http_code}' -X POST --data-binary @"$big" http://127.0.0.1:8080/api/v1/ping)
[ "$code" != 413 ] || fail "nginx refused a 3 MB upload to /api (client_max_body_size)"
uid=$(docker exec web id -u)
[ "$uid" != "0" ] || fail "Container runs as root"

# Cloud Run injects PORT; nginx must listen on it.
docker run -d --name web-port -e PORT=9090 -e API_ORIGIN=http://127.0.0.1:1 -p 9090:9090 "$IMAGE" >/dev/null
wait_up 9090 || fail "Container ignored PORT=9090"

echo "Smoke test passed: app, client-side routes, asset caching, /api forwarding, 3 MB uploads, non-root user, PORT override."
