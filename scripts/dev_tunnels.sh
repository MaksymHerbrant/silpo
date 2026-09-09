#!/usr/bin/env bash
# Вартовий dev-стенду.
#
# Serveo дає закріплений піддомен, але на безкоштовному тарифі показує сторінку
# попередження — у Telegram WebView це ламає вхід. localhost.run віддає застосунок
# напряму, але щоразу видає нову адресу.
#
# Тому: тунель localhost.run + автооновлення кнопки меню й webhook бота на кожну
# нову адресу. Відкривати Mini App треба КНОПКОЮ МЕНЮ — вона завжди актуальна.
set -uo pipefail
cd "$(dirname "$0")/.."

CHECK_EVERY="${NK_CHECK_EVERY:-15}"
SSH_PATTERN="R 80:localhost:8000"
LOG=/tmp/nk-tunnel.log
URL=""

backend_up() { pgrep -f "uvicorn app.main" > /dev/null; }
tunnel_proc() { pgrep -f "$SSH_PATTERN" > /dev/null; }
healthy() { [ -n "$URL" ] && curl -s -m 8 "$URL/health" | grep -q '"status"'; }

start_backend() {
  echo "▶ піднімаю бекенд"
  (cd backend && nohup .venv/bin/uvicorn app.main:app --port 8000 \
      > /tmp/nk-backend.log 2>&1 < /dev/null &)
  sleep 4
}

start_tunnel() {
  pkill -f "$SSH_PATTERN" 2>/dev/null
  sleep 2
  : > "$LOG"
  nohup ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
        -o ServerAliveInterval=20 -o ServerAliveCountMax=3 \
        -R 80:localhost:8000 nokey@localhost.run > "$LOG" 2>&1 < /dev/null &
  for _ in $(seq 1 45); do
    URL=$(grep -aoE "https://[a-z0-9-]+\.lhr\.life" "$LOG" | head -1)
    [ -n "$URL" ] && break
    sleep 1
  done
  [ -z "$URL" ] && return 1
  echo "▶ нова адреса: $URL"
  return 0
}

configure_bot() {
  sed -i '' "s|^PUBLIC_BACKEND_URL=.*|PUBLIC_BACKEND_URL=$URL|" backend/.env
  (cd backend && .venv/bin/python scripts/setup_bot.py --webapp-url "$URL" 2>&1 | tail -2)
  [ "${NK_NOTIFY:-1}" = "1" ] && \
    (cd backend && .venv/bin/python scripts/notify_url.py --url "$URL" 2>&1 | tail -1)
}


backend_up || start_backend
start_tunnel && configure_bot

fails=0
while true; do
  sleep "$CHECK_EVERY"
  backend_up || start_backend
  if healthy; then fails=0; continue; fi
  fails=$((fails + 1))
  echo "⚠️  адреса не відповідає ($fails) $(date '+%H:%M:%S')"
  [ "$fails" -lt 2 ] && continue
  if start_tunnel; then
    configure_bot
    echo "✅ відновлено на $URL $(date '+%H:%M:%S')"
    fails=0
  fi
done
