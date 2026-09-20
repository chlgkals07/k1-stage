#!/usr/bin/env bash
# 로봇 AP 의 2.4GHz 채널 변경 (PC 에서 실행, 로봇이 켜져 있어야 한다).
#
#   tools/set_ap_channel.sh 1
#
# 왜: 2026-08-17 개소식장 실측에서 채널 6 에 강한 AP 9개(eduroam 79% 등)가 몰려
# 있었다. 채널 1 은 7개로 가장 한산했다. 채널만 바뀌므로 주소(60.1)는 그대로이고
# 클라이언트는 잠깐 끊겼다 자동 재접속한다.
#
# 안전장치: 백업 후 hostapd 를 재시작하고, 10초 안에 hostapd 가 살아있지 않으면
# 로봇이 스스로 원복한다 (AP 가 죽으면 무선 접근이 통째로 사라지므로).

set -euo pipefail
CH=${1:?사용법: set_ap_channel.sh <채널 1~11>}
[[ $CH =~ ^([1-9]|1[01])$ ]] || { echo "채널은 1~11"; exit 1; }
ROBOT=${ROBOT:-192.168.60.1}
SSH=(ssh -o BatchMode=yes -o ConnectTimeout=6 -o StrictHostKeyChecking=no "root@$ROBOT")

echo "── 현재 채널"
"${SSH[@]}" "grep ^channel= /etc/hostapd.conf"

"${SSH[@]}" "bash -s" <<EOF
set -u
F=/etc/hostapd.conf
B=\$F.bak.ch_\$(date +%Y%m%d_%H%M%S)
cp -p "\$F" "\$B"
sed -i 's/^channel=.*/channel=$CH/' "\$F"
grep -q "^channel=$CH\$" "\$F" || { cp -p "\$B" "\$F"; echo "치환 실패 — 원복"; exit 1; }
systemctl restart hostapd
sleep 8
if pgrep -x hostapd >/dev/null; then
  echo "OK — 채널 $CH 적용, hostapd 정상 (백업 \$B)"
else
  cp -p "\$B" "\$F"; systemctl restart hostapd
  echo "hostapd 기동 실패 — 원복함"; exit 1
fi
EOF

echo "── PC 재접속 대기"
sleep 4
nmcli connection up k1-orinnx10 >/dev/null 2>&1 || true
sleep 3
ping -c2 -W2 "$ROBOT" >/dev/null 2>&1 && echo "✓ 재접속 확인 ($ROBOT)" \
  || echo "! 아직 안 붙음 — wifi_watch 가 돌고 있으면 곧 붙는다"
