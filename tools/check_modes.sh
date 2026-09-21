#!/usr/bin/env bash
# 로봇 list_modes 실측 ↔ 카탈로그·allowlist 대조.
#
#   tools/check_modes.sh                  로봇에 SSH 해 실측 후 대조
#   tools/check_modes.sh --sample FILE    저장된 service call 출력으로 대조 (오프라인 테스트)
#
# 로봇 state 이름은 shape10 이름에서 규칙 없이 변환되므로 (suffix 유지/제거 혼재,
# 매핑 테이블 없음) 실측이 유일한 진실이다. 새 정책을 로봇에 넣은 뒤 이걸 먼저 돌리고,
# [로드됨 + 카탈로그 없음] 항목의 이름을 카탈로그에 반영한 뒤 run.sh --deploy 한다.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SSH_HOSTS=(192.168.60.1 192.168.55.1)   # 로봇 AP(60.1) 우선, USB(55.1) 폴백
SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=5 -o StrictHostKeyChecking=no)
CONTAINER=ai_sapiens

fetch_modes() {
  local host
  for host in "${SSH_HOSTS[@]}"; do
    if ssh "${SSH_OPTS[@]}" "root@$host" true 2>/dev/null; then
      echo "  로봇: $host" >&2
      ssh "${SSH_OPTS[@]}" "root@$host" "docker exec $CONTAINER bash -lc '
        source /opt/ros/jazzy/setup.bash >/dev/null 2>&1
        source /root/ros2_ws/install/setup.bash >/dev/null 2>&1
        timeout 20 ros2 service call /ai_sapiens/list_modes ai_sapiens_sim2real/srv/ListModes \"{}\"'"
      return 0
    fi
  done
  echo "로봇에 SSH 할 수 없다 (${SSH_HOSTS[*]})" >&2
  return 1
}

if [[ ${1:-} == --sample ]]; then
  RAW=$(cat "${2:?--sample 뒤에 파일 경로가 필요하다}")
else
  RAW=$(fetch_modes)
fi

RAW="$RAW" python3 - "$HERE" <<'PY'
import difflib
import os
import re
import sys

import yaml

here = sys.argv[1]
raw = os.environ["RAW"]

# ros2 service call 출력의 modes=['A', 'B', ...] 에서 이름을 뽑는다.
# 필드명 등 잡음이 섞이므로 Mimic*/제어 상태만 남긴다.
CONTROL = {"Damping", "ReadyPose", "Velocity", "ZeroPose"}
names = re.findall(r"'([A-Za-z][A-Za-z0-9_]*)'", raw)
robot = sorted({n for n in names if n.startswith("Mimic") or n in CONTROL})
if not robot:
    sys.exit("list_modes 출력에서 모드 이름을 찾지 못했다. 원문을 확인하라.")

doc = yaml.safe_load(open(f"{here}/config/solo/motions.yaml"))
catalog = {m["state"]: m for m in (doc.get("motions") or []) + (doc.get("control_states") or [])}
policy = yaml.safe_load(open(f"{here}/config/solo/gateway_config.yaml"))["policy"]
api = set(policy["api_allowlist"])

loaded_ok = [n for n in robot if n in catalog]
loaded_missing = [n for n in robot if n not in catalog]
not_loaded = sorted(s for s in api if s not in robot)

print(f"\n로봇 로드 모드: {len(robot)}개\n")

print(f"[로드됨 + 카탈로그 OK] {len(loaded_ok)}개")
for n in loaded_ok:
    m = catalog[n]
    mark = "api✓" if n in api else "api✗"
    print(f"  {n:<46} {mark}  {m.get('status', 'ready')}/{m.get('safety')}/llm:{m.get('llm')}")

# Damping/ZeroPose 는 일부러 카탈로그에 안 넣었다 (RC 탈출구 혼동 방지 / api_entry 불가).
INTENTIONAL = {"Damping", "ZeroPose"}
fix_targets = [n for n in loaded_missing if n not in INTENTIONAL]
print(f"\n[로드됨 + 카탈로그 없음] {len(fix_targets)}개 — 이름 교정 대상")
for n in fix_targets:
    close = difflib.get_close_matches(n, list(catalog), n=2, cutoff=0.6)
    hint = f"   유사: {', '.join(close)}" if close else ""
    print(f"  {n}{hint}")
skipped = [n for n in loaded_missing if n in INTENTIONAL]
if skipped:
    print(f"  (의도적 미등록: {', '.join(skipped)})")

print(f"\n[allowlist 에만 있고 로봇에 없음] {len(not_loaded)}개 — 실행 불가")
for s in not_loaded:
    print(f"  {s}")
print()
PY
