#!/usr/bin/env bash
# K1 대화 시스템 실행 — 로봇 gateway 확인/기동 + PC relay 실행을 한 번에.
#
#   ./run.sh            점검 → gateway 확인/기동 → relay 실행
#   ./run.sh --deploy   위 + PC→로봇 파일 동기화 (백업 후)
#   ./run.sh --status   상태만 출력. 아무것도 시작하지 않는다
#   ./run.sh --stop     PC relay 와 로봇 gateway 정리
#
# 비밀값은 ~/.k1/secrets.env (chmod 600, 리포지토리 밖) 에 둔다. 없으면 만든다.
# 토큰은 고정이라 폰 URL 이 바뀌지 않는다 — 한 번 북마크하면 끝이다.

set -euo pipefail
umask 077

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SECRETS="${K1_SECRETS:-$HOME/.k1/secrets.env}"

# 2026-08-16: 로봇 AP 를 192.168.50.1 → 192.168.60.1 로 옮겼다. 장소 공유기(ASUS 계열)의
# 공장 초기 LAN 주소가 192.168.50.1 이라 PC 라우팅에서 대역이 겹쳐 로봇에 닿지 못했다.
SSH_HOSTS=(192.168.60.1 192.168.55.1)   # 무선 우선, USB 는 복구용 폴백
RELAY_PREFERRED=192.168.60.1            # 운영 경로 (로봇 AP)
GATEWAY_PORT=8443
RELAY_PORT=18444
CONTAINER=ai_sapiens
# 로봇 컨테이너 안 경로다. PC 폴더를 solo_stage 로 바꿨어도 여기는 그대로 둔다 —
# 먼저 로봇에서 mv 하지 않고 이 값만 바꾸면 빈 디렉터리에 배포하고, 로봇 gateway 는
# 옛 코드를 계속 돌린다. 바꾸려면 로봇에서 mv 한 뒤 이 값을 같이 고친다.
ROBOT_DIR=/root/motion_llm
SESSION=motion-gateway
# server.py 가 import 하는 로컬 모듈은 전부 여기 있어야 한다. 하나 빠지면 로봇에서
# gateway 가 아예 뜨지 않는다 (2026-08-13 relay_backend.py 로 실제로 겪었다).
# test_server_tools.py 의 test_deploy_list_covers_imports(평평한 모듈)와
# test_deploy_list_covers_core_imports_transitively(core/ 하위, 전이 의존까지)가 이 불변식을 지킨다.
#
# core/ 는 저장소 루트에 한 벌만 있고, 이 폴더의 core 는 ../core 로 가는 **심볼릭 링크**다 — PC 에서는
# `import core` 가 그대로 되고, 아래 `tar` 는 링크를 통과해 진짜 파일을 담아 로봇에는 core/ 가 **진짜
# 디렉터리**로 풀린다. core/catalog.py 는 일부러 뺐다: 로봇(--robot)은 venue 를 안 쓴다.
DEPLOY_FILES=(server.py gateway.py robot_backend.py relay_backend.py rc_backend.py rc_serial.py
              clip_len.py session_log.py gateway_config.yaml motions.yaml
              core/__init__.py core/ports.py core/stage.py)

SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=5 -o StrictHostKeyChecking=no)

info() { printf '  %s\n' "$*"; }
ok()   { printf '  \033[32m✓\033[0m %s\n' "$*"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$*"; }
die()  { printf '\n  \033[31m✗ %s\033[0m\n\n' "$*" >&2; exit 1; }
section() { printf '\n\033[1m%s\033[0m\n' "$*"; }

# ── 비밀값 ──────────────────────────────────────────────────────────
gen_token() { python3 -c 'import secrets; print(secrets.token_urlsafe(32))'; }

load_secrets() {
  if [[ ! -f $SECRETS ]]; then
    section "첫 실행 — $SECRETS 를 만든다"
    mkdir -p "$(dirname "$SECRETS")"
    local key=""
    if [[ -t 0 ]]; then
      read -rsp "  OpenAI API key (비워두면 음성 없이 버튼만): " key; echo
    else
      warn "비대화형 실행 — API key 는 비워둔다. $SECRETS 에 직접 채워라"
    fi
    umask 077
    cat >"$SECRETS" <<EOF
# K1 비밀값. 이 파일을 리포지토리·채팅·문서에 넣지 않는다.
OPENAI_API_KEY=$key
K1_ROBOT_TOKEN=$(gen_token)
K1_UI_TOKEN=$(gen_token)
EOF
    chmod 600 "$SECRETS"
    ok "생성됨 (chmod 600). 토큰은 고정이라 폰 URL 이 계속 같다"
  fi

  set -a; . "$SECRETS"; set +a

  # 나중에 항목이 추가돼도 조용히 실패하지 않게 채워 넣는다.
  local changed=0
  for var in K1_ROBOT_TOKEN K1_UI_TOKEN; do
    if [[ -z ${!var:-} ]]; then
      printf '%s=%s\n' "$var" "$(gen_token)" >>"$SECRETS"
      changed=1
    fi
  done
  (( changed )) && { set -a; . "$SECRETS"; set +a; warn "누락된 토큰을 새로 만들었다"; }
  return 0
}

# ── 로봇 접근 ───────────────────────────────────────────────────────
SSH_HOST=""
find_ssh_host() {
  for h in "${SSH_HOSTS[@]}"; do
    if ssh "${SSH_OPTS[@]}" "root@$h" true 2>/dev/null; then SSH_HOST=$h; return 0; fi
  done
  return 1
}

rexec() { ssh "${SSH_OPTS[@]}" "root@$SSH_HOST" "docker exec $CONTAINER bash -lc $(printf '%q' "$1")"; }

container_up() {
  ssh "${SSH_OPTS[@]}" "root@$SSH_HOST" \
    "docker ps --format '{{.Names}}' | grep -qx $CONTAINER" 2>/dev/null
}

# -x 는 못 쓴다: 리눅스 comm 은 15자로 잘려 ai_sapiens_sim2 가 된다.
# -f 로 전체 명령줄을 보되, [a] 로 감싸 이 pgrep 을 감싼 셸 자신이 잡히지 않게 한다.
ros_up() { rexec "pgrep -f '[a]i_sapiens_sim2real_node' >/dev/null" 2>/dev/null; }

http_code() {
  # "/" 는 이제 /pad 로 302 리다이렉트라(음성 제거) 헬스체크로 못 쓴다.
  # 무인증 /status 는 변함없이 403 → 이것으로 "떠 있음"을 판정한다.
  local c
  c=$(curl -k -o /dev/null -s -w '%{http_code}' --max-time 5 "https://$1:$GATEWAY_PORT/status" 2>/dev/null) || true
  echo "${c:-000}"
}
gateway_healthy() { [[ $(http_code "$1") == 403 ]]; }

pc_lan_ip() { ip route get 8.8.8.8 2>/dev/null | grep -oP 'src \K\S+' | head -1; }

# ── 배포 대조 ───────────────────────────────────────────────────────
# 오늘 두 번 놓친 실패 유형이다: 로봇 사본이 뒤처져 gateway 가 시작조차 못 했다.
compare_files() {
  local remote diff_count=0
  remote=$(rexec "cd $ROBOT_DIR 2>/dev/null && md5sum ${DEPLOY_FILES[*]} 2>/dev/null" || true)
  for f in "${DEPLOY_FILES[@]}"; do
    local lsum rsum
    lsum=$(md5sum "$HERE/$f" | awk '{print $1}')
    rsum=$(awk -v f="$f" '$2==f {print $1}' <<<"$remote")
    # (( x++ )) 는 x 가 0 일 때 종료코드 1 을 내므로 set -e 와 함께 쓰면 위험하다.
    if [[ -z $rsum ]]; then warn "$f — 로봇에 없음"; diff_count=$((diff_count + 1))
    elif [[ $lsum != "$rsum" ]]; then warn "$f — 다름"; diff_count=$((diff_count + 1)); fi
  done
  return "$diff_count"
}

deploy_files() {
  info "백업 후 배포한다"
  local stamp; stamp=$(date +%Y%m%d_%H%M%S)
  rexec "cd $ROBOT_DIR && mkdir -p backup_$stamp && cp -p ${DEPLOY_FILES[*]} backup_$stamp/ 2>/dev/null || true"
  ( cd "$HERE" && tar cf - "${DEPLOY_FILES[@]}" ) \
    | ssh "${SSH_OPTS[@]}" "root@$SSH_HOST" "docker exec -i $CONTAINER tar xf - -C $ROBOT_DIR" 2>/dev/null
  if compare_files; then ok "배포 완료 (백업: backup_$stamp)"; else die "배포 후에도 파일이 다르다"; fi
}

start_gateway() {
  # 토큰은 tmux 명령 문자열 안에서 export 한다. tmux 서버가 이미 떠 있으면
  # 클라이언트 환경변수를 물려받지 못하기 때문이다.
  rexec "tmux kill-session -t $SESSION 2>/dev/null; \
    tmux new-session -d -s $SESSION \"export K1_GATEWAY_TOKEN='$K1_ROBOT_TOKEN'; \
      source /opt/ros/jazzy/setup.bash; source /root/ros2_ws/install/setup.bash; \
      cd $ROBOT_DIR; exec python3 server.py --robot --https --port $GATEWAY_PORT --ready-only\"" >/dev/null
  for _ in $(seq 1 15); do
    gateway_healthy "$SSH_HOST" && return 0
    sleep 1
  done
  return 1
}

# ── 사전 점검 ───────────────────────────────────────────────────────
preflight() {
  section "1. 로봇 연결"
  find_ssh_host || die "로봇에 SSH 할 수 없다 (${SSH_HOSTS[*]}).
    유선 케이블 또는 Wi-Fi(k1-orinnx10)를 확인하라:
      nmcli -t -f DEVICE,STATE,CONNECTION device status
      ip route get $RELAY_PREFERRED"
  ok "SSH $SSH_HOST"

  container_up || die "컨테이너 '$CONTAINER' 가 떠 있지 않다. 로봇을 켜고 컨테이너를 시작하라"
  ok "컨테이너 $CONTAINER"

  section "2. ROS bringup"
  if ! ros_up; then
    die "ROS bringup 이 없다. 로봇에서 먼저 'go' 를 실행하라:
      ssh root@$SSH_HOST
      docker exec -it $CONTAINER bash
      go

    RC 와 E-stop 상태도 함께 확인한다."
  fi
  ok "ai_sapiens_sim2real_node 실행 중"

  section "3. 배포 상태"
  if compare_files; then
    ok "PC 와 로봇 파일 일치 (${#DEPLOY_FILES[@]}개)"
  else
    if [[ ${DO_DEPLOY:-0} == 1 ]]; then
      deploy_files
      # 파일이 새로 갔으면 떠 있는 gateway 는 옛 코드다. 재사용 금지 (리뷰 지적 —
      # 배포는 초록인데 로봇이 배포 전 코드로 도는 함정. --stop 수동 회피를 자동화).
      JUST_DEPLOYED=1
    else warn "로봇 사본이 PC 와 다르다. './run.sh --deploy' 로 동기화하라"; fi
  fi
}

# ── 명령 ────────────────────────────────────────────────────────────
cmd_status() {
  load_secrets
  section "1. 로봇 연결"
  if find_ssh_host; then
    ok "SSH $SSH_HOST"
    if container_up; then ok "컨테이너 $CONTAINER"; else warn "컨테이너 없음"; fi
    if ros_up; then ok "ROS bringup 실행 중"; else warn "ROS bringup 없음 — 'go' 필요"; fi
    section "2. 배포 상태"
    if compare_files; then ok "PC 와 일치"; fi
    section "3. gateway"
    for h in "${SSH_HOSTS[@]}"; do
      local c; c=$(http_code "$h")
      [[ $c == 403 ]] && ok "$h:$GATEWAY_PORT → 403 (정상)" || warn "$h:$GATEWAY_PORT → $c"
    done
  else
    warn "로봇에 SSH 불가 (${SSH_HOSTS[*]}) — 로봇이 꺼져 있거나 네트워크 문제"
  fi
  section "4. PC relay"
  if pgrep -f "server.py --relay" >/dev/null; then ok "실행 중"; else info "실행 중 아님"; fi
  echo
}

cmd_stop() {
  load_secrets
  section "정리"
  if pkill -f "server.py --relay" 2>/dev/null; then ok "PC relay 종료"; else info "PC relay 실행 중 아니었음"; fi
  if find_ssh_host; then
    rexec "tmux kill-session -t $SESSION 2>/dev/null" >/dev/null 2>&1 || true
    ok "로봇 gateway 종료"
  else
    warn "로봇에 접근할 수 없어 gateway 는 그대로 둔다"
  fi
  echo
}

cmd_run() {
  load_secrets
  preflight

  section "4. 로봇 gateway"
  # 403 은 "떠는 있다"일 뿐이다. 낡은 토큰의 gateway 를 재사용하면 모든 요청이
  # 403 으로 죽는데 preflight 는 전부 초록이었다 (리뷰 지적). 토큰으로 인증해 본다.
  gateway_authed() {
    local c
    c=$(curl -k -o /dev/null -s -w '%{http_code}' --max-time 5 \
        -b "k1_gateway=$K1_ROBOT_TOKEN" "https://$1:$GATEWAY_PORT/status" 2>/dev/null) || true
    [[ ${c:-000} == 200 ]]
  }
  if [[ ${JUST_DEPLOYED:-0} == 1 ]] && gateway_healthy "$SSH_HOST"; then
    warn "방금 배포했으므로 떠 있는 gateway(옛 코드)를 재기동한다"
    rexec "tmux kill-session -t $SESSION 2>/dev/null" >/dev/null 2>&1 || true
  fi
  if [[ ${JUST_DEPLOYED:-0} != 1 ]] && gateway_healthy "$SSH_HOST" && gateway_authed "$SSH_HOST"; then
    ok "이미 실행 중 — 토큰 인증 확인, 재사용한다"
  else
    if gateway_healthy "$SSH_HOST"; then
      warn "gateway 가 떠 있지만 현재 토큰을 거부한다 — 재기동한다"
      rexec "tmux kill-session -t $SESSION 2>/dev/null" >/dev/null 2>&1 || true
    fi
    info "기동 중..."
    start_gateway || die "gateway 가 뜨지 않았다. 로그를 확인하라:
      ssh root@$SSH_HOST 'docker exec -it $CONTAINER tmux attach -t $SESSION'"
    ok "기동됨"
  fi

  section "5. relay 경로"
  local relay_host=$RELAY_PREFERRED
  if ! gateway_healthy "$relay_host"; then
    warn "운영 경로 $relay_host 로 닿지 않는다"
    relay_host=$SSH_HOST
    gateway_healthy "$relay_host" || die "어느 경로로도 gateway 에 닿지 않는다"
    warn "$relay_host (관리 경로) 로 폴백한다 — 행사 운영에는 권장하지 않는다"
  fi
  ok "relay → https://$relay_host:$GATEWAY_PORT"

  local ip; ip=$(pc_lan_ip)
  [[ -n $ip ]] || die "PC LAN IP 를 찾지 못했다"

  section "6. 접속 URL"
  printf '\n    아이패드   \033[1;36mhttps://%s:%s/pad?token=%s\033[0m\n' "$ip" "$RELAY_PORT" "$K1_UI_TOKEN"
  printf     '    모니터     \033[1;36mhttps://%s:%s/display?token=%s\033[0m\n' "$ip" "$RELAY_PORT" "$K1_UI_TOKEN"
  printf     '    운영자     \033[1;36mhttps://%s:%s/operator?token=%s\033[0m\n\n' "$ip" "$RELAY_PORT" "$K1_UI_TOKEN"
  info "토큰이 고정이라 이 주소들은 계속 같다. 한 번 북마크해두면 다음부터는 탭 한 번이다."
  warn "아이패드는 진행자 감독 하에 둔다 — 주소를 /operator 로 바꾸면 격한 동작까지 열린다"
  # 음성 완전 삭제(2026-08-18) — OPENAI 키는 더 이상 쓰지 않는다

  section "7. PC relay 실행 (Ctrl-C 로 종료)"
  echo
  exec env \
           K1_RELAY_TOKEN="$K1_ROBOT_TOKEN" \
           K1_GATEWAY_TOKEN="$K1_UI_TOKEN" \
    python3 "$HERE/server.py" --relay "https://$relay_host:$GATEWAY_PORT" \
      --https --port "$RELAY_PORT" --ready-only
}

usage() { sed -n "2,10p" "$0" | sed 's/^# \{0,1\}//'; }

DO_DEPLOY=0
case "${1:-}" in
  --status) cmd_status ;;
  --stop)   cmd_stop ;;
  --deploy) DO_DEPLOY=1; cmd_run ;;
  -h|--help) usage ;;
  "")       cmd_run ;;
  *)        die "알 수 없는 인자: $1 (--help 참고)" ;;
esac
