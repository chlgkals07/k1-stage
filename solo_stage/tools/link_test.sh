#!/usr/bin/env bash
# 로봇 무선 링크 실측 — 신호 강도 + 왕복시간 + 손실률을 한 번에.
#
#   tools/link_test.sh           # 10초 측정
#   tools/link_test.sh 30        # 30초 측정 (워크 테스트: 사람이 로봇-PC 사이를 오가며)
#
# 데모 위치를 정할 때 쓴다: PC 를 후보 자리에 두고 실행 → 손실 0% · RTT 한 자릿수 ms
# 면 합격. 사람 몸이 전파를 막는 것이 실제 행사에서 가장 흔한 변수라, 30초짜리를
# 걸어두고 그 사이를 오가 보는 것이 실전과 가장 가깝다.

set -u
ROBOT=${ROBOT:-192.168.60.1}
SECS=${1:-10}

echo "── 로봇 AP 신호 (PC 위치 기준)"
nmcli -t -f IN-USE,SSID,CHAN,SIGNAL device wifi list 2>/dev/null \
  | awk -F: '/orinnx/{printf "   %s  채널 %s  신호 %s%%\n",$2,$3,$4}' \
  || echo "   측정 불가"
grep -H . /proc/net/wireless 2>/dev/null | awk 'NR==3{printf "   링크 품질(raw): %s\n",$0}'

echo "── ping ${SECS}초 (${ROBOT})"
ping -i 0.2 -w "$SECS" "$ROBOT" 2>/dev/null | tail -2 | sed 's/^/   /'

echo "── gateway 응답 (실제 서비스 경로)"
code=$(curl -k -o /dev/null -s -w '%{http_code}' --max-time 3 "https://$ROBOT:8443/" 2>/dev/null)
case "$code" in
  403) echo "   gateway 정상 (403 = 인증 요구)";;
  000) echo "   gateway 미기동 또는 도달 불가";;
  *)   echo "   응답 $code";;
esac
