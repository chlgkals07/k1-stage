#!/usr/bin/env bash
# group_stage 서버를 세션과 무관하게 띄운다 (tmux 있으면 tmux, 없으면 setsid).
cd "$(dirname "$0")"
set -a; . ~/.k1/secrets.env; set +a
export K1_GATEWAY_TOKEN="$K1_STAGE_TOKEN"
PORT="${1:-19000}"
pkill -f "server.py --https --port $PORT" 2>/dev/null; sleep 1
if command -v tmux >/dev/null; then
  tmux kill-session -t rc-stage 2>/dev/null
  tmux new-session -d -s rc-stage "python3 -u server.py --https --port $PORT 2>&1 | tee -a logs/server.log"
  echo "tmux 세션 rc-stage 로 기동 (tmux attach -t rc-stage 로 확인)"
else
  setsid nohup python3 -u server.py --https --port $PORT >> logs/server.log 2>&1 < /dev/null &
  disown
  echo "setsid 로 기동 (logs/server.log)"
fi
sleep 4
echo "토큰: $K1_STAGE_TOKEN"
for ip in 192.168.10.58 100.86.174.82; do
  code=$(curl -sk -o /dev/null -w '%{http_code}' --max-time 3 "https://$ip:$PORT/operator?token=$K1_STAGE_TOKEN")
  echo "  https://$ip:$PORT  → $code"
done
