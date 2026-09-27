#!/usr/bin/env bash
# Post-deploy end-to-end checks against a real deployed API Gateway URL.
# Usage: scripts/smoke_test.sh https://<api-id>.execute-api.<region>.amazonaws.com
set -euo pipefail

BASE_URL="${1:?Usage: smoke_test.sh <api-gateway-url>}"
BASE_URL="${BASE_URL%/}"
COOKIE_JAR="$(mktemp)"
trap 'rm -f "${COOKIE_JAR}"' EXIT

pass() { echo "  PASS - $1"; }
fail() { echo "  FAIL - $1"; exit 1; }

echo "1. Anonymous GET /"
status=$(curl -s -o /dev/null -w "%{http_code}" "${BASE_URL}/")
[[ "${status}" == "200" ]] && pass "got 200" || fail "got ${status}"

echo "2. POST /seed-users"
status=$(curl -s -o /dev/null -w "%{http_code}" -X POST "${BASE_URL}/seed-users")
[[ "${status}" == "200" || "${status}" == "404" ]] || fail "unexpected status ${status}"
pass "got ${status} (200 if seeding enabled, 404 if disabled)"

echo "3. Login as seeded admin"
status=$(curl -s -c "${COOKIE_JAR}" -o /dev/null -w "%{http_code}" \
  -H "HX-Request: true" \
  -X POST "${BASE_URL}/auth/login" \
  --data-urlencode "username=admin" --data-urlencode "password=Admin123!")
[[ "${status}" == "200" ]] && pass "logged in" || fail "login returned ${status}"
grep -q "id_token" "${COOKIE_JAR}" || fail "id_token cookie missing"
pass "id_token cookie present"

echo "3b. Login by email (moto's Cognito mock can't emulate AliasAttributes - see tests/test_auth.py)"
status=$(curl -s -o /dev/null -w "%{http_code}" \
  -H "HX-Request: true" \
  -X POST "${BASE_URL}/auth/login" \
  --data-urlencode "username=admin@quote-app.local" --data-urlencode "password=Admin123!")
[[ "${status}" == "200" ]] && pass "logged in by email" || fail "email login returned ${status}"

echo "4. Authenticated GET /"
status=$(curl -s -b "${COOKIE_JAR}" -o /dev/null -w "%{http_code}" "${BASE_URL}/")
[[ "${status}" == "200" ]] && pass "got 200" || fail "got ${status}"

echo "5. GET /healthz"
status=$(curl -s -o /dev/null -w "%{http_code}" "${BASE_URL}/healthz")
[[ "${status}" == "200" ]] && pass "got 200" || fail "got ${status}"

echo "6. Throttling regression check (20 quick requests, expect zero 429s)"
codes=""
for _ in $(seq 1 20); do
  codes+="$(curl -s -o /dev/null -w "%{http_code} " "${BASE_URL}/healthz")"
done
if echo "${codes}" | grep -q "429"; then
  fail "got a 429 - check infrastructure/api_gateway.tf default_route_settings throttling limits"
fi
pass "no 429s"

echo
echo "All smoke tests passed."
