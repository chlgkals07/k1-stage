# 운영 런북

셋업 → 검증 → 운영 → 장애 대응까지 이 문서 하나로 끝난다. 2026-08-17 개소식 현장에서
실측한 값이 기준이다.

> 로봇을 한동안 안 켰다가 다시 잡는 자리라면(특히 다른 사람이 로봇을 만졌을 수
> 있으면) 이 문서보다 **[HANDOVER_CHECK.md](HANDOVER_CHECK.md)를 먼저** 돈다 —
> 여기 적힌 값들이 아직도 참인지부터 실측으로 확인한다.

> **2026-09-22 산업은행 본점**처럼 통신 사전 허가가 필요한 장소에서는 먼저
> [BANK_EVENT_20260922.md](BANK_EVENT_20260922.md)를 따른다. RC도 ELRS 무선통신이며,
> RC-only 현장에서는 Wi-Fi를 전제로 하는 `run.sh --deploy`를 실행하지 않는다.

> 이 문서는 예전의 `OPENING_RUNBOOK` · `CEREMONY_RUNBOOK` · `FIELD_SETUP` ·
> `NEXT_SESSION_CHECKLIST` 네 편을 합친 것이다. 같은 절차가 네 판으로 갈라져 어느 것이
> 최신인지 파일명으로만 구분되던 문제를 없앴다.

---

## 0. 한눈에

```
아이패드(/pad) ──┐
폰(/operator) ──┼── 장소 랜(192.168.0.x) ──── 인터넷
PC 유선 ────────┘        PC = 192.168.0.9
PC Wi-Fi ─────────── k1-orinnx10 · 채널1 · 192.168.60.x ── 로봇(60.1)
PC ── HDMI ── TV(/display)                                  ← 네트워크 무관
```

| 화면 | 기기 | 역할 |
|---|---|---|
| `/pad` | 아이패드 | 관객: 동작 선택 → **미리보기 → [실행]** |
| `/display` | TV | 무대: 대기 / 미리보기 / 실행중 / 무대영상 |
| `/operator` | 폰 + 메인컴 | 정지 · 상태 · 수동 버튼 · 무대(dance) 시작/정지 |
| `/dance` | 메인컴 | 음악 싱크 오프셋 보정 |

`/`로 들어오면 `/pad`로 리다이렉트된다(옛 북마크 대응). 운영은 버튼(preview→실행)과
무대(dance) 둘이다.

---

## 1. 장소 준비 — 새 장소일 때만

### 네트워크 구성

```
폰·패드 ──(장소 랜 또는 휴대용 라우터)── PC ──(로봇 AP Wi-Fi)── K1
                                          └──(인터넷)
```

| 구간 | 무엇을 쓰나 | 왜 |
|---|---|---|
| 폰·패드 ↔ PC | 장소 랜, 없으면 **휴대용 라우터** | 게스트망은 기기 간 통신이 막혀 있는 경우가 많아 폰이 PC에 못 붙는다 |
| PC ↔ 로봇 | 로봇 AP (`k1-orinnx10`) | **PC를 로봇 가시선 안, 가능한 가까이.** 여기가 끊기는 구간이다 |
| PC ↔ 인터넷 | 랜 / 유선 / 폰 테더링 | 없어도 버튼·무대는 전부 동작한다 |

**PC는 로봇 AP와 장소 랜에 동시에 붙어야 한다** (Wi-Fi + 유선, 또는 Wi-Fi 어댑터 2개).

### 로봇 AP 주소가 `192.168.60.1`인 이유

원래 `192.168.50.1`이었는데 **ASUS 공유기의 공장 초기 LAN 주소가 정확히 그 값이다.**
장소 공유기가 ASUS면 PC 라우팅 테이블에 `192.168.50.0/24`가 두 개 생기고, 커널은 목적지마다
인터페이스를 하나만 고르므로 `192.168.50.1`이 전부 공유기로 빨려 들어가 **로봇에 영원히
닿지 못한다.** 설정으로 우회할 수 있는 문제가 아니라 구조적이다. 2026-08-16에 바꿨다.

`192.168.60.x`는 공유기 초기값으로 거의 쓰이지 않아 재발 확률이 낮다. 바뀐 것은 로봇 `wlan0`
주소와 DHCP 대역뿐이고 **SSID·비밀번호는 그대로**다.

| 대역 | 쓰임 |
|---|---|
| `192.168.60.1` | 로봇 gateway (AP `k1-orinnx10`). PC는 `192.168.60.50~149`를 받는다 |
| `192.168.55.1` | 로봇 USB — **복구용 폴백. 운영 경로가 아니다** |
| 장소 대역 | 폰·패드 ↔ PC, 인터넷 |

로봇 쪽 실체는 `/etc/systemd/network/75-wifi-ap.network`의 `Address=` 한 줄이다
(백업 `.bak.ap60_20260816`). dnsmasq가 아니라 systemd-networkd 내장 DHCP를 쓴다.

### PC Wi-Fi 프로파일

로봇 AP는 인터넷이 없으므로 기본 경로로 쓰면 안 된다.

```bash
nmcli connection modify k1-orinnx10 ipv4.never-default yes
```

### 준비물

휴대용 라우터(장소 랜이 없을 때) · PC를 로봇 근처에 둘 받침대와 연장 전원 · **E-stop 담당자**

---

## 2. 셋업 순서

```bash
# 0. PC: 절전·화면보호기 꺼짐 확인. TV 입력 = PC HDMI
# 1. 로봇 전원 → (사람) go        ※ cb(colcon build) 불필요 — 코드 안 바뀜
# 2. PC 터미널 1 — 워치독 (로봇 부팅 전에 켜도 된다. 알아서 붙는다)
cd /home/robotis-ai/Projects/shape3/k1-stage/solo_stage
tools/wifi_watch.sh

# 3. PC 터미널 2 — 링크 실측 (손실 0% 확인)
tools/link_test.sh 10

# 4. PC 터미널 3 — 배포 + gateway + relay 한 번에
./run.sh --deploy
#    ※ 코드가 갱신된 뒤라면 반드시:  ./run.sh --stop && ./run.sh --deploy
#      (--stop 없이는 로봇의 옛 gateway 를 재사용해 새 코드가 안 탄다)

# 5. 접속 링크 출력
~/k1links 18444
```

로봇 bringup(`go`)은 **사람이 직접 한다.** 로봇이 물리 상태에 진입하므로 자동화하지 않는다.

`run.sh`가 순서대로 확인한다: SSH 경로 → 컨테이너 → ROS bringup → PC↔로봇 파일 md5 →
gateway 기동(이미 떠 있으면 재사용) → relay 경로 → 접속 URL 출력 → PC relay 실행.

| 명령 | 용도 |
|---|---|
| `./run.sh` | 점검 + gateway + relay |
| `./run.sh --deploy` | 위 + PC→로봇 파일 동기화 (백업 후) |
| `./run.sh --status` | 상태만 확인. 아무것도 시작하지 않는다 |
| `./run.sh --stop` | relay·gateway 정리 |

**접속 URL은 토큰이 고정이라 매번 같다.** 한 번 북마크하면 다음부터는 탭 한 번이다.
비밀값은 `~/.k1/secrets.env`(chmod 600, 저장소 밖)에 있고 첫 실행 때 만들어진다.

### 기기 배치

- **아이패드**: 장소 랜 접속 → `pad` 링크 → 홈 화면 추가 → **안내 접근(단일 앱) 켜기**
  (주소를 `/operator`로 바꾸면 격한 동작까지 열린다)
- **TV**: PC 브라우저에서 `display` 링크 → TV 화면으로 이동 → **화면 한 번 클릭**
  (소리 잠금 해제 — footer에 ⚠가 남아 있으면 아직 안 된 것) → F11 전체화면
- **폰**: `operator` 링크 (정지 버튼이 여기 있다)

---

## 3. 검증 시퀀스 — 순서 고정

1. `/operator` 상단 경로가 `RELAY · PC→ROBOT`인지 확인하고 RC **API Arm(CH8) 올림** →
   `API 준비됨` 확인 (SD를 OFF → ON으로 edge를 만들고 약 3초 warm-up)
2. **정지 버튼** — 동작 중에도 눌리는지 **가장 먼저**
3. 인사 3종 회귀: 손 흔들기 → 배꼽 인사 → 손키스
4. **preview 흐름**: 패드 탭 → TV 미리보기 → [실행] → 로봇 동작 + TV "실행 중"
5. **dance API 모드**: `/dance` 프리셋 불러오기 → ▶ 시작("무대에서 재생" 체크 상태)
   → 2초 뒤 TV 영상+소리 + 로봇 동작 → **어긋나면 오프셋 조정 → 재시작 → 프리셋 저장**
6. **dance RC 모드**: SD OFF → `/operator`에서 `RC 모드 켜기 — 유선 RC로 전환` →
   상단 `RC · 유선 RC→ELRS` 확인 → 같은 프리셋 재생·싱크 확인
7. **API 복귀**: `/operator`에서 `RC 모드 끄기 — 기본 경로 복귀` → `RELAY` 확인 →
   SD OFF→ON → `API 준비됨` 확인
8. **신규 회귀**: SD OFF 상태에서 dance 시작 → `로봇이 명령을 받을 준비가 안 됐습니다`로
   시작이 거부돼야 한다. 영상만 재생되면 실패다.
9. 공간 확보 후: 팔굽혀펴기 → 스쿼트 → 섀도우 복싱 (E-stop 대기)

> 수동 버튼은 `/operator` 전용이다. gateway가 `API 준비됨`이 되기 전에는 잠긴다 —
> **SD Arm 전에 버튼이 안 눌리는 건 고장이 아니다.**

### 새 동작을 처음 실기에서 확인할 때

각 동작마다 기록한다: 시작·종료 자세 / 이동량 / 소요 시간 / 복귀 상태 / 이상 여부.
이 기록이 잠금 시간과 패드·dance 공개 여부 판단의 근거가 된다.

로봇에 실제로 로드된 모드와 카탈로그를 대조하려면:

```bash
tools/check_modes.sh
```

`[로드됨 + 카탈로그 없음]` 항목은 카탈로그의 state 이름을 실측 이름으로 고친다.
유사 후보를 같이 출력해 준다 (seed 충돌 주의: anse A456/A459, bow A428/A429).

---

## 4. 도구

| 도구 | 용도 |
|---|---|
| `./run.sh` | 점검→gateway→relay. `--deploy` 배포 포함 / `--status` 상태만 / `--stop` 정리 |
| `~/k1links [포트]` | 접속 링크 4개 출력. 기본 18500(mock), 행사는 **18444** |
| `tools/wifi_watch.sh` | 로봇 링크 자동 재접속 (행사 내내 켜둔다) |
| `tools/link_test.sh [초]` | 신호·손실·RTT·gateway 실측. 30초 걸고 워크 테스트 |
| `tools/set_ap_channel.sh N` | AP 채널 변경 (자동 원복 안전장치). 개소식에서 6→1 적용 |
| `tools/check_modes.sh` | 로봇 로드 모드 ↔ 카탈로그 대조 |
| `tools/rehearsal.py` | 3면(패드·디스플레이·운영자) 리허설 |
| `tools/edge_probe.py` | 엣지 케이스 훑기 |
| `tools/render_motion.py` | 동작 CSV → 미리보기 MP4 |

---

## 5. 장애 대응

| 증상 | 대응 |
|---|---|
| 무선 순단 | 워치독이 재접속. **로봇은 상태를 유지한다 — 당황하지 말 것** |
| `로봇 연결 끊김` 지속 | PC를 로봇 쪽으로 옮긴다. relay 재시작: `Ctrl-C` → `./run.sh` |
| **API 전체 사망** | **RC 다이얼 수동 진행** (2페이지 × 20동작). 화면·자막은 그대로 산다 |
| 위험 상황 | **RC Damping / E-stop — 항상 최우선, 네트워크 무관** |
| display가 이상 | 새로고침 → **탭 한 번 다시** (잊으면 footer에 ⚠) |
| dance 영상만 안 나옴 | display 탭 안 함 / 옛 탭 캐시 → 새로고침 + 탭 |
| API 준비가 안 됨 | heartbeat 확인 → SD OFF→ON edge 재생성 → 3초 warm-up → RC link와 E-stop 확인 |
| 버튼은 되는데 동작이 거부됨 | `API 준비됨`인지 / 다른 동작이 실행 중인지 / 그 동작이 로봇에 로드됐는지 |

### 정지 수단의 역할 구분

| 수단 | 용도 | 우선순위 |
|---|---|---|
| **RC Damping / E-stop** | 즉시 탈출. 물리 안전장치 | **최상위 — 항상 API보다 우선** |
| `/operator` 빨간 정지 | "지금 이 동작만 멈춰". 일상적 중단 | API 경로 |

빨간 정지는 실행 중에도 잠기지 않는다. 로봇을 **`Velocity`(보행·균형)로 되돌린다** —
`ReadyPose`는 균형 정책 없이 관절을 고정 자세로 끌어당기는 `posture`라, 팔굽혀펴기·스쿼트처럼
바닥에 붙은 자세에서 누르면 가장 넘어지기 쉽다. 예외는 로봇이 **Damping**일 때뿐으로,
상태기계상 탈출구가 `ReadyPose`밖에 없어 그때만 자동으로 그쪽으로 간다. **버튼은 하나다.**

위험 상황에서는 버튼이 아니라 **RC Damping 또는 E-stop을 쓴다.**

### 링크·경로 진단

```bash
nmcli -t -f DEVICE,STATE,CONNECTION device status
ip route get 192.168.60.1          # → 192.168.60.1 dev wlp128s20f3 src 192.168.60.x
curl --interface wlp128s20f3 -k -o /dev/null -sS -w '%{http_code}\n' \
     https://192.168.60.1:8443/    # → 403 이면 정상 (토큰 인증이 필요한 살아있는 서버)
```

---

## 6. 종료

```bash
./run.sh --stop
```

그 뒤 SD OFF → 로봇이 Manual로 돌아왔는지 확인한다.

```bash
ros2 topic echo /ai_sapiens/mode_status --once
```

---

## 7. 알려진 제약

- 이번 무대 목록은 패드 12개 + dance 전용 서울대 응원·스트레이키즈, 총 14개 고유
  동작이다. `BAD`는 패드와 dance가 같은 동작을 공유한다.
  등록하려면 config 2쌍 삽입 + `go` 재시작이 필요하다
- 로봇 시계가 이틀 어긋난다. 싱크는 전부 PC 시계라 무영향이고, **로봇 로그를 대조할 때만** 주의
- dance 오프셋(-420ms 등)은 **이 현장에서 재보정한 값이어야 한다**
- 토큰이 하나라 아이패드에서 주소만 바꾸면 `/operator`가 열린다 → **안내 접근 필수**
- RC 모드에서는 라디오 **SD(CH8)를 내려야** 명령이 먹는다. 로봇은 API 권한일 때 teleop 전이를
  무시하므로, SD가 올라가 있으면 RC 펄스가 조용히 무시되고 PC는 성공으로 보고한다
- 대기 중 물리 스위치는 **SC 상단(CH7 2000) + SB 중앙(CH6 1500)** 에 둔다.
  **SC 중앙에 두지 않는다** — 그 위치가 곧 "권한을 잃으면 ReadyPose" 스위치다

---

## 8. 새 자산을 로봇에 올릴 때

새 정책을 올릴 때 **`params/` 전체(csv + sim2real.yaml)를 복사**해야 한다. csv만 넣으면
bringup이 `sim2real_yaml missing file`로 죽는다 (2026-08-18에 실제로 발생).

새 파일을 추가한 뒤에는 **`cb`(colcon build) 한 번**이 필요할 수 있다 — install이 파일 단위
심링크라 새 파일의 링크는 빌드가 만든다.

### 새 동작을 여는 순서

카탈로그만 고쳐서는 아무 일도 일어나지 않는다. **넷이 모두 맞아야 한다.**

```text
1. 로봇 k1_config.yaml selector       ← RC 다이얼에서 실행할 슬롯
2. motions.yaml motions / rc_list     ← UI 카탈로그와 RC 배포 목표
3. gateway_config.yaml api_allowlist  ← 운영자 수동 버튼으로 실행 가능해짐
4. 실물 단독 검증 (공간 + E-stop)
5. pad_allowlist                     ← 패드에 보일 동작만 추가
6. dance_presets.json                ← dance에서 사용할 때만 추가
```

로봇에 policy 자체가 없으면 gateway가 "현재 로봇에 배포되지 않은 동작입니다"로 거부한다.
실제 로드 목록은 [reference/ROBOT_MODES_20260812.md](reference/ROBOT_MODES_20260812.md)를 본다.

---

## 부록 A. 수동 절차 — `run.sh`를 못 쓸 때

무엇이 잘못됐는지 알아야 하거나 스크립트를 쓸 수 없는 상황에서만 쓴다.

```bash
# 1. 로봇 (사람이 직접)
ssh root@192.168.55.1
docker exec -it ai_sapiens bash
go
ros2 node list | grep -E 'sim2real|rc|controller'
ros2 topic echo /ai_sapiens/mode_status --once

# 2. 로봇 컨테이너에서 gateway
cd /root/motion_llm
python3 server.py --robot --https --port 8443 --ready-only
#   → 출력된 robot gateway token 을 복사한다
#   → 운영 중에는 tools/api_arm_probe.py 를 같이 실행하지 않는다

# 3. PC 네트워크 확인 (§5 "링크·경로 진단")

# 4. PC 비밀값
cd /home/robotis-ai/Projects/shape3/k1-stage/solo_stage
read -rsp "Robot gateway token: " K1_RELAY_TOKEN; echo; export K1_RELAY_TOKEN

# 5. PC relay
python3 server.py --relay https://192.168.60.1:8443 --https --port 18444 --ready-only

# 6. 접속
~/k1links 18444
```

로봇 실행본은 호스트가 아니라 **`ai_sapiens` 도커 컨테이너 안** `/root/motion_llm/`에 있다.
`run.sh`가 PC↔로봇 파일 md5를 대조하므로 배포 누락은 자동으로 잡힌다(`--deploy`로 동기화).
이 경로에서 실제로 두 번 사고가 났다.

## 부록 B. 주의

- 실제 API key와 token을 **문서·채팅에 저장하지 않는다.** `~/.k1/secrets.env`에만 둔다
- 로봇 USB 주소 `192.168.55.1`은 **운영 명령 경로로 쓰지 않는다** (복구용 폴백)
- locomotion 중 teleop velocity passthrough는 로봇 배포·빌드와 하드웨어 비연결 C++ 테스트
  25/25까지 끝났으나 **실제 움직임에서는 미검증**이다
- 배포 후에는 ReadyPose → API부터 확인하고, E-stop 담당자가 있는 상태에서
  저속 locomotion → API를 검증한다
