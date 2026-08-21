#!/usr/bin/env bash
# 로봇 Wi-Fi 워치독 — 링크가 죽으면 재접속을 시도한다.
#
#   tools/wifi_watch.sh          # 포그라운드 (별도 터미널 권장)
#   tools/wifi_watch.sh &        # 백그라운드
#
# NetworkManager 의 autoconnect 가 대부분 처리하지만, 다른 Wi-Fi 로 옮겨 앉거나
# 재접속을 안 물고 늘어지는 경우가 실측으로 두 번 있었다 (2026-08-16).
# ping 이 연속 N회 실패하면 nmcli 로 로봇 AP 재접속을 강제한다.
#
# 로봇이 꺼져 있을 때도 계속 재시도하므로, 행사 전 미리 켜두면 로봇이 부팅되는
# 순간 자동으로 붙는다.

set -u

ROBOT=${ROBOT:-192.168.60.1}
CONN=${CONN:-k1-orinnx10}
FAIL_LIMIT=${FAIL_LIMIT:-3}     # 연속 실패 허용 횟수 (3회 ≈ 6초)
INTERVAL=${INTERVAL:-2}

fails=0
echo "[wifi_watch] $ROBOT 감시 시작 (${FAIL_LIMIT}회 연속 실패 시 '$CONN' 재접속)"
while true; do
  if ping -c1 -W2 "$ROBOT" >/dev/null 2>&1; then
    if (( fails >= FAIL_LIMIT )); then
      echo "[wifi_watch] $(date +%T) 링크 복구됨"
    fi
    fails=0
  else
    fails=$((fails + 1))
    if (( fails == FAIL_LIMIT )); then
      echo "[wifi_watch] $(date +%T) ${FAIL_LIMIT}회 연속 실패 — 재접속 시도"
      nmcli connection up "$CONN" >/dev/null 2>&1 \
        && echo "[wifi_watch] $(date +%T) nmcli up 성공" \
        || echo "[wifi_watch] $(date +%T) nmcli up 실패 (AP 전파 없음일 수 있음)"
      # 재접속 직후 바로 또 시도하지 않게 카운터를 절반으로
      fails=1
    fi
  fi
  sleep "$INTERVAL"
done
