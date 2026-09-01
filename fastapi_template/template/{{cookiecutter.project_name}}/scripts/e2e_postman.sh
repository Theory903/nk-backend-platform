#!/usr/bin/env bash
# End-to-end API smoke via Postman CLI (`postman request`) + curl for
# cookie/multipart/ApiKey flows that the CLI handles poorly.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$ROOT/docs/postman-environment.json"
REPORT=()
API="${API_CONTAINER:-{{ cookiecutter.project_name }}-api-1}"

{%- if cookiecutter.add_users in [True, "True", "true", 1, "1"] %}
EMAIL="e2e-$(date +%s)@example.com"
PASS="DevPass123!"
COOKIE_JAR="$(mktemp)"
UPLOAD_FILE="$(mktemp)"
trap 'rm -f "$COOKIE_JAR" "$UPLOAD_FILE"' EXIT
echo "e2e upload $(date)" >"$UPLOAD_FILE"
{%- endif %}

BASE_URL="$(python3 - <<PY
import json
from pathlib import Path
env = json.loads(Path("$ENV_FILE").read_text())
print(next(v["value"] for v in env["values"] if v["key"] == "baseUrl"))
PY
)"

run_req() {
  local name="$1"
  shift
  local out status
  out="$(postman request "$@" -e "$ENV_FILE" 2>&1)" || true
  if echo "$out" | rg -q '^\s+200 OK|^\s+201 Created|^\s+202 Accepted|^\s+204 No Content'; then
    status="$(echo "$out" | rg -o '^\s+[0-9]{3} [A-Za-z ]+' | head -1 | xargs)"
    REPORT+=("PASS|$name|$status")
    echo "$out" | tail -8
    return 0
  fi
  status="$(echo "$out" | rg -o '^\s+[0-9]{3} [A-Za-z ]+' | head -1 | xargs || echo 'FAIL')"
  REPORT+=("FAIL|$name|${status:-ERROR}")
  echo "$out" | tail -12
  return 1
}

pass() { REPORT+=("PASS|$1|$2"); echo "PASS $1 ($2)"; }
fail() { REPORT+=("FAIL|$1|$2"); echo "FAIL $1 ($2)"; }

curl_code() {
  curl -sS -o /tmp/e2e_body.json -w '%{http_code}' "$@"
}

{%- if cookiecutter.add_users in [True, "True", "true", 1, "1"] and cookiecutter.cookie_auth in [True, "True", "true", 1, "1"] %}
cookie_value() {
  python3 - "$COOKIE_JAR" "$1" <<'PY'
import sys
from http.cookiejar import MozillaCookieJar
jar = MozillaCookieJar(sys.argv[1])
jar.load(ignore_discard=True, ignore_expires=True)
name = sys.argv[2]
for cookie in jar:
    if cookie.name == name:
        print(cookie.value)
        break
PY
}
{%- endif %}

echo "=== E2E Postman CLI — {{ cookiecutter.project_name }} @ $(date) ==="
{%- if cookiecutter.add_users in [True, "True", "true", 1, "1"] %}
echo "email=$EMAIL"
{%- endif %}
echo

echo "--- 0. Wait for API ready ---"
for _ in $(seq 1 30); do
  READY_CODE="$(curl -sS -o /dev/null -w '%{http_code}' "$BASE_URL/api/ready" 2>/dev/null || echo 000)"
  if [[ "$READY_CODE" == "200" ]]; then
    pass "API Ready" "200 OK"
    break
  fi
  sleep 2
done
if [[ "${READY_CODE:-}" != "200" ]]; then
  fail "API Ready" "timeout"
  echo "=== SUMMARY ==="
  printf '%-6s | %-35s | %s\n' "Result" "Test" "Status"
  printf '%-6s | %-35s | %s\n' "FAIL" "API Ready" "timeout"
  exit 1
fi
echo

echo "--- 1. Health ---"
run_req "Health Check" GET "{{'{{'}}baseUrl{{'}}'}}/api/health" || true
echo

{%- if cookiecutter.add_users in [True, "True", "true", 1, "1"] %}
echo "--- 2. Register ---"
run_req "Register" POST "{{'{{'}}baseUrl{{'}}'}}/api/auth/register" \
  -H "Content-Type:application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASS\"}" || true
echo

{%- if cookiecutter.jwt_auth in [True, "True", "true", 1, "1"] %}
echo "--- 3. JWT Login (form) ---"
LOGIN_OUT="$(postman request POST "{{'{{'}}baseUrl{{'}}'}}/api/auth/jwt/login" -e "$ENV_FILE" \
  -f "username=$EMAIL" -f "password=$PASS" 2>&1)" || true
echo "$LOGIN_OUT" | tail -8
ACCESS_TOKEN="$(curl -sS -X POST "$BASE_URL/api/auth/jwt/login" \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -d "username=$EMAIL&password=$PASS" \
  | python3 -c "import json,sys; print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null || true)"
if echo "$LOGIN_OUT" | rg -q '200 OK' && [[ -n "$ACCESS_TOKEN" ]]; then
  pass "JWT Login" "200 + access_token"
else
  fail "JWT Login" "$(echo "$LOGIN_OUT" | rg -o '^\s+[0-9]{3} [A-Za-z ]+' | head -1 | xargs || echo ERROR)"
fi
echo

echo "--- 4. Current User (Bearer) ---"
if [[ -n "${ACCESS_TOKEN:-}" ]]; then
  ME_OUT="$(postman request GET "{{'{{'}}baseUrl{{'}}'}}/api/users/me" -e "$ENV_FILE" \
    --auth-bearer-token "$ACCESS_TOKEN" 2>&1)" || true
  echo "$ME_OUT" | tail -8
  if echo "$ME_OUT" | rg -q '200 OK'; then
    pass "Users:Current User" "200 OK"
  else
    fail "Users:Current User" "$(echo "$ME_OUT" | rg -o '^\s+[0-9]{3} [A-Za-z ]+' | head -1 | xargs || echo ERROR)"
  fi
else
  fail "Users:Current User" "skipped (no access_token)"
fi
echo
{%- endif %}

echo "--- 4b. Forgot Password ---"
run_req "Reset:Forgot Password" POST "{{'{{'}}baseUrl{{'}}'}}/api/auth/forgot-password" \
  -H "Content-Type:application/json" \
  -d "{\"email\":\"$EMAIL\"}" || true
echo

echo "--- 4c. OpenAPI contract ---"
run_req "OpenAPI JSON" GET "{{'{{'}}baseUrl{{'}}'}}/api/openapi.json" || true
echo

echo "--- 4d. Build Info ---"
run_req "Build Info" GET "{{'{{'}}baseUrl{{'}}'}}/api/build-info" || true
echo

{%- if cookiecutter.enable_routers in [True, "True", "true", 1, "1"] and cookiecutter.api_type == 'rest' %}
echo "--- 4e. Echo (authenticated) ---"
if [[ -n "${ACCESS_TOKEN:-}" ]]; then
  ECHO_OUT="$(postman request POST "{{'{{'}}baseUrl{{'}}'}}/api/echo/" -e "$ENV_FILE" \
    --auth-bearer-token "$ACCESS_TOKEN" \
    -H "Content-Type:application/json" \
    -d '{"message":"e2e-postman"}' 2>&1)" || true
  echo "$ECHO_OUT" | tail -8
  if echo "$ECHO_OUT" | rg -q '200 OK'; then
    pass "Send Echo Message" "200 OK"
  else
    fail "Send Echo Message" "$(echo "$ECHO_OUT" | rg -o '^\s+[0-9]{3} [A-Za-z ]+' | head -1 | xargs || echo ERROR)"
  fi
else
  fail "Send Echo Message" "skipped (no access_token)"
fi
echo
{%- endif %}

echo "--- 5. Request Verify Token ---"
run_req "Verify:Request-Token" POST "{{'{{'}}baseUrl{{'}}'}}/api/auth/request-verify-token" \
  -H "Content-Type:application/json" \
  -d "{\"email\":\"$EMAIL\"}" || true
echo

echo "--- 6. Verify (token from dev logs) ---"
sleep 1
VERIFY_TOKEN="$(docker logs "$API" 2>&1 | rg 'POST /api/auth/verify' | tail -1 | rg -o 'eyJ[^"]+' || true)"
if [[ -n "$VERIFY_TOKEN" ]]; then
  run_req "Verify:Verify" POST "{{'{{'}}baseUrl{{'}}'}}/api/auth/verify" \
    -H "Content-Type:application/json" \
    -d "{\"token\":\"$VERIFY_TOKEN\"}" || true
else
  fail "Verify:Verify" "no token in docker logs"
fi
echo

{%- if cookiecutter.jwt_auth in [True, "True", "true", 1, "1"] %}
echo "--- 7. Verify with JWT access_token (should fail) ---"
if [[ -n "${ACCESS_TOKEN:-}" ]]; then
  BAD_OUT="$(postman request POST "{{'{{'}}baseUrl{{'}}'}}/api/auth/verify" -e "$ENV_FILE" \
    -H "Content-Type:application/json" \
    -d "{\"token\":\"$ACCESS_TOKEN\"}" 2>&1)" || true
  echo "$BAD_OUT" | tail -6
  if echo "$BAD_OUT" | rg -q '400 Bad Request'; then
    pass "Verify rejects access_token" "400 (expected)"
  else
    fail "Verify rejects access_token" "unexpected response"
  fi
else
  fail "Verify rejects access_token" "skipped"
fi
echo
{%- endif %}

echo "--- 8. Ready ---"
run_req "Readiness Check" GET "{{'{{'}}baseUrl{{'}}'}}/api/ready" || true
echo

{%- if cookiecutter.jwt_auth in [True, "True", "true", 1, "1"] %}
echo "--- 9. Bad JWT login (expected 400) ---"
BAD_LOGIN="$(postman request POST "{{'{{'}}baseUrl{{'}}'}}/api/auth/jwt/login" -e "$ENV_FILE" \
  -f "username=$EMAIL" -f "password=WrongPass123!" 2>&1)" || true
echo "$BAD_LOGIN" | tail -6
if echo "$BAD_LOGIN" | rg -q '400 Bad Request'; then
  pass "JWT Login bad password" "400 (expected)"
else
  fail "JWT Login bad password" "unexpected response"
fi
echo

echo "--- 10. Duplicate register (expected 400) ---"
DUP_REG="$(postman request POST "{{'{{'}}baseUrl{{'}}'}}/api/auth/register" -e "$ENV_FILE" \
  -H "Content-Type:application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASS\"}" 2>&1)" || true
echo "$DUP_REG" | tail -6
if echo "$DUP_REG" | rg -q '400 Bad Request'; then
  pass "Register duplicate" "400 (expected)"
else
  fail "Register duplicate" "unexpected response"
fi
echo
{%- endif %}

echo "--- 11. E2E infra ApiKey (dev bootstrap) ---"
E2E_API_KEY="${E2E_API_KEY:-$(docker logs "$API" 2>&1 | rg '\[dev e2e\] Authorization: ApiKey ' | tail -1 | sed 's/.*ApiKey //' | xargs || true)}"
if [[ -n "$E2E_API_KEY" ]]; then
  pass "E2E ApiKey bootstrap" "found in docker logs"
  echo "api_key=${E2E_API_KEY:0:12}..."
else
  fail "E2E ApiKey bootstrap" "missing — restart api after pulling latest code"
fi
echo

REDIS_KEY="e2e-$(date +%s)"
REDIS_VAL="hello-redis"

if [[ -n "$E2E_API_KEY" ]]; then
{%- if cookiecutter.enable_redis in [True, "True", "true", 1, "1"] %}
  echo "--- 12. Redis set/get ---"
  REDIS_PUT="$(curl_code -X PUT "$BASE_URL/api/redis/" \
    -H "Authorization: ApiKey $E2E_API_KEY" \
    -H "Content-Type: application/json" \
    -d "{\"key\":\"$REDIS_KEY\",\"value\":\"$REDIS_VAL\"}")"
  if [[ "$REDIS_PUT" == "200" ]]; then
    pass "Redis:Set Value" "200 OK"
  else
    fail "Redis:Set Value" "HTTP $REDIS_PUT"
  fi
  REDIS_GET="$(curl_code "$BASE_URL/api/redis/?key=$REDIS_KEY" \
    -H "Authorization: ApiKey $E2E_API_KEY")"
  if [[ "$REDIS_GET" == "200" ]] && rg -q "$REDIS_VAL" /tmp/e2e_body.json; then
    pass "Redis:Get Value" "200 OK"
  else
    fail "Redis:Get Value" "HTTP $REDIS_GET"
  fi
  echo
{%- endif %}
{%- if cookiecutter.enable_rmq in [True, "True", "true", 1, "1"] %}
  echo "--- 13. RabbitMQ publish ---"
  RMQ_CODE="$(curl_code -X POST "$BASE_URL/api/rabbit/" \
    -H "Authorization: ApiKey $E2E_API_KEY" \
    -H "Content-Type: application/json" \
    -d "{\"exchange_name\":\"e2e\",\"routing_key\":\"e2e\",\"message\":\"e2e-rabbit\"}")"
  if [[ "$RMQ_CODE" == "200" ]]; then
    pass "RabbitMQ:Publish" "200 OK"
  else
    fail "RabbitMQ:Publish" "HTTP $RMQ_CODE"
  fi
  echo
{%- endif %}
{%- if cookiecutter.enable_kafka in [True, "True", "true", 1, "1"] %}
  echo "--- 14. Kafka publish ---"
  KAFKA_CODE="$(curl_code -X POST "$BASE_URL/api/kafka/" \
    -H "Authorization: ApiKey $E2E_API_KEY" \
    -H "Content-Type: application/json" \
    -d "{\"topic\":\"e2e\",\"message\":\"e2e-kafka\"}")"
  if [[ "$KAFKA_CODE" == "200" ]]; then
    pass "Kafka:Publish" "200 OK"
  else
    fail "Kafka:Publish" "HTTP $KAFKA_CODE"
  fi
  echo
{%- endif %}
{%- if cookiecutter.enable_nats in [True, "True", "true", 1, "1"] %}
  echo "--- 15. NATS publish ---"
  NATS_CODE="$(curl_code -X POST "$BASE_URL/api/nats/" \
    -H "Authorization: ApiKey $E2E_API_KEY" \
    -H "Content-Type: application/json" \
    -d "{\"subject\":\"e2e\",\"message\":\"e2e-nats\"}")"
  if [[ "$NATS_CODE" == "200" ]]; then
    pass "NATS:Publish" "200 OK"
  else
    fail "NATS:Publish" "HTTP $NATS_CODE"
  fi
  echo
{%- endif %}
{%- if cookiecutter.orm in ['sqlalchemy', 'beanie'] %}
  echo "--- 16. SCIM list/create ---"
  SCIM_LIST="$(curl_code "$BASE_URL/scim/v2/Users" \
    -H "Authorization: ApiKey $E2E_API_KEY")"
  if [[ "$SCIM_LIST" == "200" ]]; then
    pass "SCIM:List Users" "200 OK"
  else
    fail "SCIM:List Users" "HTTP $SCIM_LIST"
  fi
  SCIM_USER="scim-$(date +%s)@example.com"
  SCIM_CREATE="$(curl_code -X POST "$BASE_URL/scim/v2/Users" \
    -H "Authorization: ApiKey $E2E_API_KEY" \
    -H "Content-Type: application/json" \
    -d "{\"userName\":\"$SCIM_USER\",\"active\":true}")"
  if [[ "$SCIM_CREATE" == "201" ]]; then
    pass "SCIM:Create User" "201 Created"
  else
    fail "SCIM:Create User" "HTTP $SCIM_CREATE"
  fi
  echo
{%- endif %}
  echo "--- 17. File upload/list ---"
  FILE_CODE="$(curl_code -X POST "$BASE_URL/api/files" \
    -H "Authorization: ApiKey $E2E_API_KEY" \
    -F "file=@$UPLOAD_FILE;type=text/plain;filename=e2e.txt")"
  if [[ "$FILE_CODE" == "201" ]]; then
    pass "Files:Upload" "201 Created"
    FILE_ID="$(python3 -c "import json; print(json.load(open('/tmp/e2e_body.json')).get('file_id',''))")"
    LIST_CODE="$(curl_code "$BASE_URL/api/files/org" \
      -H "Authorization: ApiKey $E2E_API_KEY")"
    if [[ "$LIST_CODE" == "200" ]]; then
      pass "Files:List Org" "200 OK"
    else
      fail "Files:List Org" "HTTP $LIST_CODE"
    fi
    if [[ -n "$FILE_ID" ]]; then
      GET_CODE="$(curl_code "$BASE_URL/api/files/$FILE_ID" \
        -H "Authorization: ApiKey $E2E_API_KEY")"
      if [[ "$GET_CODE" == "200" ]]; then
        pass "Files:Get" "200 OK"
      else
        fail "Files:Get" "HTTP $GET_CODE"
      fi
    else
      fail "Files:Get" "no file_id in upload response"
    fi
  else
    fail "Files:Upload" "HTTP $FILE_CODE"
    fail "Files:List Org" "skipped"
    fail "Files:Get" "skipped"
  fi
  echo
else
{%- if cookiecutter.enable_redis in [True, "True", "true", 1, "1"] %}
  fail "Redis:Set Value" "skipped (no api key)"
  fail "Redis:Get Value" "skipped"
{%- endif %}
{%- if cookiecutter.enable_rmq in [True, "True", "true", 1, "1"] %}
  fail "RabbitMQ:Publish" "skipped"
{%- endif %}
{%- if cookiecutter.enable_kafka in [True, "True", "true", 1, "1"] %}
  fail "Kafka:Publish" "skipped"
{%- endif %}
{%- if cookiecutter.enable_nats in [True, "True", "true", 1, "1"] %}
  fail "NATS:Publish" "skipped"
{%- endif %}
{%- if cookiecutter.orm in ['sqlalchemy', 'beanie'] %}
  fail "SCIM:List Users" "skipped"
  fail "SCIM:Create User" "skipped"
{%- endif %}
  fail "Files:Upload" "skipped"
  fail "Files:List Org" "skipped"
  fail "Files:Get" "skipped"
fi

{%- if cookiecutter.enable_agents in [True, "True", "true", 1, "1"] and cookiecutter.jwt_auth in [True, "True", "true", 1, "1"] %}
if [[ -n "${ACCESS_TOKEN:-}" ]]; then
  echo "--- 18. MCP capabilities (Bearer) ---"
  MCP_GET="$(curl_code "$BASE_URL/api/mcp" \
    -H "Authorization: Bearer $ACCESS_TOKEN")"
  if [[ "$MCP_GET" == "200" ]] && rg -q '"protocol"' /tmp/e2e_body.json; then
    pass "MCP:Capabilities" "200 OK"
  else
    fail "MCP:Capabilities" "HTTP $MCP_GET"
  fi
  MCP_POST="$(curl_code -X POST "$BASE_URL/api/mcp" \
    -H "Authorization: Bearer $ACCESS_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}')"
  if [[ "$MCP_POST" == "200" ]] && rg -q 'tools' /tmp/e2e_body.json; then
    pass "MCP:Tools List" "200 OK"
  else
    fail "MCP:Tools List" "HTTP $MCP_POST"
  fi
  MCP_ROOT="$(curl_code "$BASE_URL/mcp" \
    -H "Authorization: Bearer $ACCESS_TOKEN")"
  if [[ "$MCP_ROOT" == "200" ]]; then
    pass "MCP:Root Capabilities" "200 OK"
  else
    fail "MCP:Root Capabilities" "HTTP $MCP_ROOT"
  fi
  echo
else
  fail "MCP:Capabilities" "skipped (no access_token)"
  fail "MCP:Tools List" "skipped"
  fail "MCP:Root Capabilities" "skipped"
fi
{%- endif %}

{%- if cookiecutter.cookie_auth in [True, "True", "true", 1, "1"] %}
echo "--- 19. Cookie login + session ---"
COOKIE_CODE="$(curl_code -c "$COOKIE_JAR" -b "$COOKIE_JAR" \
  -X POST "$BASE_URL/api/auth/cookie/login" \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -d "username=$EMAIL&password=$PASS")"
AUTH_SESSION="$(cookie_value auth_session || true)"
if [[ "$COOKIE_CODE" == "204" || "$COOKIE_CODE" == "200" ]] && [[ -n "$AUTH_SESSION" ]]; then
  pass "Cookie:Login" "HTTP $COOKIE_CODE"
  ME_COOKIE="$(curl_code -c "$COOKIE_JAR" -b "$COOKIE_JAR" "$BASE_URL/api/users/me")"
  if [[ "$ME_COOKIE" == "200" ]]; then
    pass "Cookie:Current User" "200 OK"
  else
    fail "Cookie:Current User" "HTTP $ME_COOKIE"
  fi
  CSRF_TOKEN="$(curl -sS -b "$COOKIE_JAR" "$BASE_URL/api/auth/csrf" \
    | python3 -c "import json,sys; print(json.load(sys.stdin).get('token',''))" 2>/dev/null || true)"
  if [[ -n "$CSRF_TOKEN" ]]; then
{%- if cookiecutter.enable_routers in [True, "True", "true", 1, "1"] and cookiecutter.api_type == 'rest' %}
    ECHO_COOKIE="$(curl_code -X POST "$BASE_URL/api/echo/" \
      -b "$COOKIE_JAR" \
      -H "X-CSRF-Token: $CSRF_TOKEN" \
      -H "Content-Type: application/json" \
      -d '{"message":"e2e-cookie"}')"
    if [[ "$ECHO_COOKIE" == "200" ]]; then
      pass "Cookie:Echo" "200 OK"
    else
      fail "Cookie:Echo" "HTTP $ECHO_COOKIE"
    fi
{%- else %}
    pass "Cookie:Echo" "skipped (echo router disabled)"
{%- endif %}
  else
    fail "Cookie:Echo" "no csrf token"
  fi
  LOGOUT_CODE="$(curl_code -X POST "$BASE_URL/api/auth/cookie/logout" \
    -b "$COOKIE_JAR" \
    -H "X-CSRF-Token: $CSRF_TOKEN")"
  if [[ "$LOGOUT_CODE" == "204" || "$LOGOUT_CODE" == "200" ]]; then
    pass "Cookie:Logout" "HTTP $LOGOUT_CODE"
  else
    fail "Cookie:Logout" "HTTP $LOGOUT_CODE"
  fi
else
  fail "Cookie:Login" "HTTP $COOKIE_CODE"
  fail "Cookie:Current User" "skipped"
  fail "Cookie:Echo" "skipped"
  fail "Cookie:Logout" "skipped"
fi
echo
{%- endif %}
{%- endif %}

echo "=== SUMMARY ==="
printf '%-6s | %-35s | %s\n' "Result" "Test" "Status"
printf '%s\n' "-------|-------------------------------------|--------"
for row in "${REPORT[@]}"; do
  IFS='|' read -r result name status <<< "$row"
  printf '%-6s | %-35s | %s\n' "$result" "$name" "$status"
done

FAIL_COUNT="$(printf '%s\n' "${REPORT[@]}" | rg -c '^FAIL\|' || true)"
set -- "${REPORT[@]}"
TOTAL_COUNT="$#"
PASS_COUNT="$(expr "$TOTAL_COUNT" - "$FAIL_COUNT")"
echo
echo "Total: $TOTAL_COUNT | Pass: $PASS_COUNT | Fail: $FAIL_COUNT"
if [[ "$FAIL_COUNT" -gt 0 ]]; then
  exit 1
fi
