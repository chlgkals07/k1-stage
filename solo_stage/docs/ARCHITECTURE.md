# K1 무대 운영 시스템 상세 문서

> **왜 이렇게 생겼나**를 적는다. 네트워크 구성, gateway, ROS 계약, 보안·안전 정책,
> Locomotion→API→Mimic 설계가 여기 있다.
> 현재 운영 절차는 [RUNBOOK.md](RUNBOOK.md), 지금 무엇이 참인지는 [STATUS.md](STATUS.md).

## 1. 목표

관객이 아이패드(`/pad`)에서 동작을 고르면 TV(`/display`)에 미리보기가 뜨고, 확정하면
로봇이 그 동작을 한다. 무대(`/dance`)는 음원과 안무를 **절대 시각 기준으로** 맞춰 튼다.
운영자는 폰(`/operator`)으로 수동 실행과 정지를 쥔다.

```text
관객 아이패드 /pad
→ 동작 선택 → /display 에 sim 클립 미리보기
→ 확정 → 로봇이 실행 → 동작 길이만큼 잠금 → 대기 복귀

운영자 폰 /operator
→ 수동 버튼(api_allowlist 78개) · 빨간 정지 · 무대 시작/정지 · RC 모드 토글

메인컴 /dance
→ 프리셋(동작 + 음원 + offset_ms) 보정 → 무대 시작
→ 로봇과 /display 가 각자 같은 절대 시각에 맞춰 발사·재생
```

통신 구조는 아래와 같다.

```text
아이패드 · 폰
  │ 장소 랜 + HTTPS
  ▼
Omen PC (relay)
  ├─ k1-orinnx10 Wi-Fi → Robot gateway        ← 기본 경로
  │                          │ ROS 2 / Zenoh
  │                          ▼
  │                    sim2real / Mimic policy
  └─ USB → RadioMaster → ELRS → 로봇          ← RC 폴백 (`--rc` 또는 /rc/mode 토글)

Radiomaster RC
  └─ SD: API authority 허용/해제 및 물리 안전장치
```

아이패드는 로봇 AP에 연결하지 않는다. 아이패드는 장소 랜을 쓰고, PC가 장소 랜과 로봇 AP
양쪽에 동시에 연결된다.

## 2. 현재 검증 상태

### 완료

- 아이패드·폰 → PC HTTPS UI 연결
- PC mock backend에서 수동 버튼 매핑
- 로봇 API heartbeat 및 `MANUAL → API_WARMUP → API` 전환
- API를 통한 `MimicWaveHand` 실물 실행
- 아이패드 → 로봇 AP → robot gateway 직접 무선 실행
- PC 유선 LAN 인터넷과 PC Wi-Fi 로봇 연결 동시 사용
- PC RelayBackend → 로봇 gateway 무선 `/status` 조회
- 아이패드 → PC relay → 로봇 gateway → `MimicWaveHand` 실행
- 개소식 현장 운영 (패드 12개 중 10개 정상, 나머지 2개는 로봇 config 미등록)
- Python 단위 테스트 통과 (현재 172개 — [STATUS.md](STATUS.md) 참고)
- locomotion 유지용 teleop velocity passthrough를 로봇 sim2real 소스에 배포하고 패키지 빌드 완료
- 로봇에서 `ReadyPose/Velocity → API`, Mimic 완료 후 최신 RC 속도 복귀, heartbeat 정지 우선순위 C++ 테스트 25/25 통과

### 아직 완전히 검증하지 않은 항목

- locomotion 중 비영(非零) 속도를 유지한 API authority 전환 실물 검증
- API 전환 순간 active mode뿐 아니라 실제 joint/velocity 출력이 끊기지 않는지 검증
- Mimic 종료 후 이전 locomotion 속도 자동 복귀
- PC↔로봇 Wi-Fi 20~30분 장시간 soak test
- PC relay 연결 단절 시 robot heartbeat를 자동 중단하는 upstream lease
- 개소식용 자동 시작과 프로세스 supervisor
- 속도 scale, acceleration limit, 전환 smoothing 조정

## 3. 네트워크 구성

현재 확인된 주소는 다음과 같다.

| 역할 | 인터페이스 | 주소 | 용도 |
|---|---|---:|---|
| PC 장소 랜 | `enp129s0` | `192.168.10.58` | 아이패드·폰 접속 |
| PC 로봇 Wi-Fi | `wlp128s20f3` | `192.168.60.77` | 로봇 전용 |
| 로봇 Wi-Fi AP | `wlan0` | `192.168.60.1` | robot gateway |
| 로봇 USB fallback | `l4tbr0` | `192.168.55.1` | 설치/복구용, 운영 명령 경로에서 제외 |

로봇 AP 정보:

```text
SSID: k1-orinnx10
대역: 2.4 GHz
채널: 6
로봇 주소: 192.168.60.1
```

### 라우팅 검증

PC에서 다음을 확인한다.

```bash
nmcli -t -f DEVICE,TYPE,STATE,CONNECTION device status
ip -br addr
ip route get 192.168.60.1
ip route get 1.1.1.1
```

정상 결과의 핵심:

```text
192.168.60.1 dev wlp128s20f3 src 192.168.60.77
1.1.1.1 via 192.168.10.1 dev enp129s0 src 192.168.10.58
```

로봇과 인터넷을 각각 강제로 확인한다.

```bash
curl --interface wlp128s20f3 -k -o /dev/null -sS \
  -w 'robot=%{http_code} remote=%{remote_ip}\n' \
  https://192.168.60.1:8443/

curl --interface enp129s0 -o /dev/null -sS \
  -w 'internet=%{http_code} remote=%{remote_ip}\n' \
  https://1.1.1.1/
```

robot gateway의 token 없이 `/`에 접근했을 때 `403`은 정상이다. 서버가 살아 있고 인증이 동작한다는 뜻이다.

## 4. 주요 파일

| 파일 | 역할 |
|---|---|
| `server.py` | HTTPS UI, stage 상태기계, 무대 싱크, motion 검증 및 backend 호출 |
| `relay_backend.py` | PC에서 robot gateway의 `/status`, `/motion`을 HTTPS로 중계 |
| `robot_backend.py` | 로봇 내부에서 ROS heartbeat, status, mode service 처리 |
| `rc_backend.py` · `rc_serial.py` | RC 폴백 경로 — PC→USB→라디오→ELRS |
| `gateway.py` | allowlist, 단일 요청, lifecycle, timeout 상태 머신 |
| `gateway_config.yaml` | ROS endpoint, allowlist 3종, stop/entry state, timeout |
| `static/pad.html` | 관객 아이패드 화면 — 동작 선택·미리보기·진행바 |
| `static/display.html` | TV 화면 — 대기·미리보기·실행중·무대영상 |
| `static/operator.html` | 운영자 화면 — 정지·수동 버튼·무대 조작·RC 토글 |
| `static/dance.html` | 무대 싱크 오프셋 보정 |
| `clip_len.py` | sim 클립 mp4에서 길이만 읽는다 — 잠금 타이밍의 기준 |
| `motions.yaml` | 동작 카탈로그 |
| `api_arm_probe.py` | 모션 없이 heartbeat/API authority를 점검하는 개발용 도구 |
| `test_gateway.py` | gateway lifecycle 단위 테스트 |
| `test_ui_http.py` | token→cookie→운영자 화면과 보호 endpoint 회귀 테스트 |
| `test_relay_backend.py` | PC relay 전달 및 allowlist 테스트 |
| `test_dance.py` | 무대 싱크·세대 번호·자동 종료 테스트 |

## 5. 보안 및 안전 정책

### 이중 검사 + 허용목록 3종

**PC relay와 robot gateway가 각각** motion을 검사한다. 한쪽을 뚫어도 다른 쪽이 막는다.

허용목록은 셋이고 서로 포함 관계다 — **누가 부르느냐에 따라 위험도가 다르기** 때문이다.

| 목록 | 누가 부르나 |
|---|---|
| `api_allowlist` | gateway가 실행을 허용하는 전부. 운영자 수동 버튼이 여기서 나온다 |
| `pad_grid` (venue) | 그중 관객 아이패드에 여는 것. `config/venues/<행사>/venue.yaml` |
| `llm_allowlist` | 그중 모델이 스스로 고를 수 있는 것. **현재 이 경로로 들어오는 요청은 없다** |

승격 경로는 **수동으로 먼저 실물 검증 → 그 뒤 패드에 개방**이다. 실제 개수와 목록은
`gateway_config.yaml`이 정본이고, 현재 값은 [STATUS.md §2](STATUS.md#2-허용목록이-세-개인-이유)에 있다.

`safety: restricted`(복싱류 등)는 사람이 버튼으로만 부른다 — 모델 경로에서는
`llm_motions()`가 구조적으로 거른다.

### Gateway token

- robot gateway token과 PC UI token은 서로 다르다.
- robot gateway 재시작 시 token이 새로 발급될 수 있다.
- PC relay에는 robot token을 `K1_RELAY_TOKEN`으로 전달한다.
- token 값은 문서에 고정 저장하지 않는다.

### Radiomaster 역할

Radiomaster는 PC 명령의 전송 수단이 아니라 **권한과 안전을 쥐는 물리 장치**다.

- SD ON: API authority 요청 허용
- SD OFF: API authority 해제
- 물리 RC: locomotion 및 긴급 수동 제어
- PC: 허용된 Mimic policy 이름만 요청

RC status/input 토픽을 소프트웨어로 위조하면 물리 RC와 충돌하고 안전 계층이 불분명해지므로 사용하지 않는다.

## 6. 전체 실행 순서

### 6.1 로봇 ROS 기동

로봇에서 기존 alias를 사용한다.

```bash
go
```

또는 로봇 컨테이너 진입 후 상태를 확인한다.

```bash
cd /data/ai_sapiens_private/docker
./container.sh enter

ros2 node list | grep -E 'sim2real|rc|controller'
ros2 topic echo /ai_sapiens_rc/status --once
ros2 topic echo /ai_sapiens/mode_status --once
```

RC status에서 다음 값이 정상이어야 한다.

```text
status_data_valid: true
hardware_ok: true
estop_released: true
rc_link_ok: true
is_control_input_safe: true
```

### 6.2 Robot gateway 실행

로봇 컨테이너에서:

```bash
cd /root/motion_llm

python3 server.py \
  --robot \
  --https \
  --port 8443 \
  --ready-only
```

장시간 실행은 tmux를 사용한다.

```bash
tmux new-session -d -s motion-gateway \
  "source /opt/ros/jazzy/setup.bash; \
   source /root/ros2_ws/install/setup.bash; \
   cd /root/motion_llm; \
   python3 server.py --robot --https --port 8443 --ready-only"

tmux capture-pane -pt motion-gateway -S -60
```

출력된 robot gateway token을 복사한다. 실제 token은 문서에 기록하지 않는다.

`RobotBackend`가 ROS heartbeat를 생성하므로 운영 중에는 별도의 `api_arm_probe.py` heartbeat를 동시에 실행하지 않는다.

### 6.3 PC 네트워크 준비

PC Wi-Fi를 `k1-orinnx10`에 연결하고, 유선 LAN 인터넷은 유지한다.

```bash
nmcli -t -f DEVICE,STATE,CONNECTION device status
ip route get 192.168.60.1
```

robot gateway 응답 확인:

```bash
curl --interface wlp128s20f3 -k \
  -o /dev/null -sS -w '%{http_code}\n' \
  https://192.168.60.1:8443/
```

token 없이 실행했을 때 `403`이면 정상이다.

### 6.4 PC 환경변수 설정

Omen PC의 같은 터미널에서:

```bash
cd /home/robotis-ai/Projects/shape3/k1-stage/solo_stage

read -rsp "Robot gateway token: " K1_RELAY_TOKEN
echo
export K1_RELAY_TOKEN
```

값을 출력하지 않고 존재 여부만 확인한다.

```bash
test -n "$K1_RELAY_TOKEN" && echo 'Robot token OK' || echo 'Robot token MISSING'
```

### 6.5 PC relay 실행

```bash
python3 server.py \
  --relay https://192.168.60.1:8443 \
  --https \
  --port 18444 \
  --ready-only
```

정상 출력 예:

```text
카탈로그 136개 (학습완료 ... / 예정 ...)
패드 버튼 12개 · 백엔드 relay

PC   https://localhost:18444
폰   https://192.168.10.58:18444
제어 URL  https://<robot-ip>:18444/?token=<PC_UI_TOKEN>
```

### 6.6 아이패드·폰 접속

아이패드는 `k1-orinnx10`이 아니라 장소 랜에 연결한다.

PC relay가 출력한 token을 사용해 다음 형식으로 접속한다.

```text
https://192.168.10.58:18444/?token=<PC_UI_TOKEN>
```

자체 서명 인증서 경고가 나오면 고급 메뉴에서 계속 접속한다.

### 6.7 API Arm 및 동작 테스트

1. 로봇 주변을 비운다.
2. RC link와 E-stop 상태를 확인한다.
3. SD를 OFF로 두었다가 ON으로 전환한다.
4. 약 3초 warmup 후 UI가 `API 준비됨`인지 확인한다.
5. `/operator` 에서 수동 버튼으로 `MimicWaveHand` 1회 실행을 확인한다.
6. `/pad` 에서 같은 동작을 preview → 실행 → 대기 복귀까지 확인한다.

예상 lifecycle:

```text
MANUAL
→ API_WARMUP (api_authority_requested)
→ API (api_warmup_complete)
→ MimicWaveHand
→ Velocity 또는 설정된 on_complete state
```

## 7. 개발·진단 명령

### 테스트

```bash
cd /home/robotis-ai/Projects/shape3/k1-stage/solo_stage

python3 -m py_compile \
  server.py gateway.py robot_backend.py relay_backend.py

python3 -m unittest \
  test_gateway.py \
  test_relay_backend.py \
  test_server_tools.py \
  test_ui_http.py
```

### 로봇 상태만 조회

```bash
curl -k -b "k1_gateway=<ROBOT_TOKEN>" \
  https://192.168.60.1:8443/status
```

### 로봇 gateway 로그

```bash
tmux capture-pane -pt motion-gateway -S -100
```

### 프로세스 종료

PC relay는 실행 터미널에서:

```text
Ctrl-C
```

로봇 gateway:

```bash
tmux kill-session -t motion-gateway
```

종료 후 SD를 OFF로 내려 Manual authority로 복귀한다.

## 8. Locomotion → API → Mimic 설계

### 요구 동작

```text
Manual locomotion
→ SD ON + heartbeat
→ API authority 전환 중에도 locomotion 계속 유지
→ API 명령 수신
→ Mimic policy 실행
→ 완료 후 정의된 locomotion/정지 상태로 복귀
```

### 로봇 배포 상태

로봇 `ai_sapiens_sim2real/config/k1_config.yaml`에 다음 설정을 적용하고 패키지를 빌드했다.

```yaml
authority:
  api_entry:
    velocity_neutral_threshold: 0.05
    allow_non_neutral_teleop: true
  teleop_velocity_passthrough: true
```

각 수정 파일의 로컬 백업 suffix:

```text
.bak_api_teleop_passthrough_20260810
```

로봇 배포 전 복구 백업:

```text
/root/ros2_ws/api_passthrough_backup_20260810
```

두 옵션은 기본값이 `false`이므로 설정하지 않은 구성은 기존 동작을 유지한다.

- `allow_non_neutral_teleop`: API 진입 시 물리 RC 속도가 0이 아니어도 허용한다.
- `teleop_velocity_passthrough`: `API_WARMUP`과 `API`에서도 velocity source를 물리 RC Teleop으로 유지한다.
- API `/cmd_vel`의 중립 조건은 그대로 남아 있어, 이 옵션으로 API 속도 입력까지 우회하지 않는다.
- heartbeat 손실 시 `zero_velocity`가 passthrough보다 우선하여 해당 tick을 0으로 만들고 Manual authority로 복귀한다.

로봇에는 과거 임시 설정인 `velocity_neutral_threshold: 2.0`이 남아 있을 수 있다. 배포할 때 로봇의 정리된 motion 목록을 덮어쓰지 말고, 백업 후 authority 항목과 빌드 산출물만 반영해야 한다. 당시 로봇 백업은 다음과 같다.

```text
k1_config.yaml.bak_api_locomotion_20260731_171553
```

### 구현된 동작

현재 구현은 속도를 latch하지 않고 매 tick 최신 물리 RC Teleop 속도를 사용한다. 따라서 API 전환 뒤에도 조종자가 속도를 바꾸거나 스틱을 중립으로 놓으면 그대로 반영된다.

```text
MANUAL / Velocity / Teleop velocity
→ SD ON + valid heartbeat
→ API_WARMUP / Velocity / Teleop velocity
→ API / Velocity / Teleop velocity
→ Mimic service request / Mimic policy
→ Mimic 완료 / Velocity / 최신 Teleop velocity
```

로봇 없이 수행한 검증:

- ROS 2 Jazzy 격리 빌드 성공
- `test_state_machine_config` 12/12 통과
- `test_mode_controller` 13/13 통과
- 신규 시나리오: locomotion 유지 전환, ReadyPose 전환, Mimic 완료 후 최신 RC 속도 복귀, heartbeat 손실 시 1 tick zero
- K1 YAML 파싱과 변경 파일 whitespace 검사 통과

남은 위험은 Locomotion↔Mimic policy 전환 순간의 실제 joint 출력 discontinuity다. 따라서 배포 후에는 바퀴/발이 움직이지 않는 지지 상태에서 ReadyPose 시험을 먼저 하고, E-stop 담당자를 둔 저속 locomotion 시험으로 넘어간다. 속도 감속·smoothing은 별도 단계다.

## 9. 속도 개선 방향

속도 문제는 세 부분으로 나누어야 한다.

- 입력 scale: RC/API velocity command의 최대 크기
- acceleration/deceleration limit: 급가속과 급정지 방지
- mode transition smoothing: Locomotion↔Mimic 전환 시 출력 discontinuity 완화

권장 순서:

1. 현재 RC raw axis와 최종 velocity command를 기록한다.
2. 원하는 행사장 최대 속도를 정한다.
3. linear/angular scale을 별도로 조절한다.
4. acceleration limiter를 적용한다.
5. Mimic 전환 전후 0.2~0.5초 smoothing을 검토한다.
6. 저속에서 실물 검증 후 상향한다.

## 10. 운영 전에 남은 필수 작업

- PC relay ↔ robot gateway upstream lease 추가
- 20~30분 무선 soak test와 reconnect test
- Wi-Fi 단절, 폰 화면 종료 각각의 fail-safe 확인
- 고정 실행 절차 또는 systemd/tmux launcher 작성
- 고정 token 저장 방식 결정
- 행사장 Wi-Fi 간섭 테스트
- locomotion 전환 저속 실물 검증
- E-stop 담당자와 종료 절차 지정

