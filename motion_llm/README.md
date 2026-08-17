# K1 모션 LLM — PC relay + Robot gateway

**현재 상태**: 아이폰 음성 대화 → Omen PC relay → 로봇 gateway → 검증된 K1 Mimic policy 실행까지 연결됐다. 무선 relay, 음성 응답, 인사 동작을 실물로 확인했다. 최신 인수인계와 로봇 적용 내용은 docs/STATUS_AND_HANDOVER.md를 기준으로 한다.

```
브라우저 ──WebRTC(음성)──> OpenAI Realtime API
    │  function call: play_motion(motion, reason)
    ↓ fetch POST /motion
 server.py ──> MotionBackend
                ├─ MockBackend   로봇 없이 UI/LLM 검증
                ├─ RelayBackend  PC → HTTPS → robot gateway (운영 경로)
                └─ RobotBackend  (2단계) gateway → rclpy → request_mode_by_name
```

오디오는 **브라우저와 OpenAI 사이에서만** 흐른다. 서버는 작은 JSON만 받는다.

## 실행

로봇과 함께 쓸 때는 `run.sh` 하나면 된다. 로봇에서 `go`(ROS bringup)만 사람이 띄운다.

```bash
./run.sh            # 점검 → gateway 확인/기동 → relay 실행 → 폰 URL 출력
./run.sh --status   # 상태만 확인
./run.sh --deploy   # PC→로봇 파일 동기화까지
./run.sh --stop     # 정리
```

토큰이 고정이라 폰 URL이 매번 같다 — 한 번 북마크하면 끝이다.
비밀값은 `~/.k1/secrets.env`(chmod 600, 리포지토리 밖)에 있고 첫 실행 때 만들어진다.

로봇 없이 UI/LLM만 보려면:

```bash
export OPENAI_API_KEY=sk-...

# PC 에서 테스트 (localhost 는 HTTP 로도 마이크가 열린다)
python3 server.py

# 폰에서 테스트 (마이크는 HTTPS 필수, 자체 서명 인증서 자동 생성)
python3 server.py --https
```

`pyyaml` 외 의존성 없음. OpenAI SDK 불필요.

선택된 동작은 터미널과 웹 화면에 동시에 찍힌다.

## 파일

| 파일 | 역할 |
|---|---|
| `motions.yaml` | **모든 것의 입력.** 동작 목록 + 한국어 이름/설명/태그/안전등급 |
| `server.py` | 토큰 발급, 동작 검증·기록, UI 서빙 |
| `static/index.html` | WebRTC 클라이언트 + 수동 버튼 UI |

## motions.yaml 이 핵심이다

이 파일 하나가 세 곳에 쓰인다:

1. **LLM 도구 정의** — `llm: true` 인 항목만 `play_motion` 의 enum 과 설명에 들어간다
2. **안전 게이트** — `safety: restricted` 는 LLM 경로에서 무조건 거부
3. **웹 UI** — `page` 별 탭, `ko` 로 버튼 이름

동작을 추가·제외하려면 **이 파일만** 고치면 된다. 서버 재시작으로 반영된다.

### 안전 규칙

| 경로 | 허용 범위 |
|---|---|
| LLM (`source: llm`) | `llm: true` **그리고** `safety != restricted` |
| 수동 버튼 (`source: manual`) | 카탈로그의 전부 |

복싱·섀도우복싱처럼 격한 동작은 사람이 버튼으로만 부를 수 있다.
`slap`(뺨 때리기) 류는 **카탈로그에 아예 넣지 않는다.**

## 튜닝할 곳

- **`PERSONA`** (`server.py`) — 로봇 말투와 "말만 하지 말고 반드시 움직여라" 규칙.
  대화가 밋밋하면 여기부터 손본다.
- **`desc` / `tags`** (`motions.yaml`) — LLM 이 동작을 고르는 유일한 근거.
  엉뚱한 걸 고르면 설명이 부족한 것이다.
- **`REALTIME_MODEL` / `REALTIME_VOICE`** — 환경변수로 교체 가능.

### 대화 감각 조절 (환경변수)

행사장에서 코드 수정 없이 바꿀 수 있다. relay 재시작으로 반영된다.

| 변수 | 기본값 | 역할 |
|---|---|---|
| `REALTIME_MAX_TOKENS` | `200` | 응답 길이 하드캡. 문장 중간에서 잘리므로 폭주 방지용이고, 실제 길이는 PERSONA가 잡는다 |
| `REALTIME_VAD_TYPE` | `server_vad` | `semantic_vad`로 바꾸면 의미로 발화 종료를 판단한다 |
| `REALTIME_VAD_THRESHOLD` | `0.5` | 감지 민감도. 시끄러우면 올린다 |
| `REALTIME_VAD_SILENCE_MS` | `400` | **턴 전환 느낌을 잡는 주 손잡이.** 300~700 사이에서 맞춘다 |
| `REALTIME_VAD_PREFIX_MS` | `300` | 감지 직전 오디오를 얼마나 포함할지 |
| `REALTIME_VAD_EAGERNESS` | `auto` | `semantic_vad`일 때만 쓴다 |

말과 동작을 맞추려고 `play_motion`은 응답이 끝나길(`response.done`) 기다리지 않고
`response.function_call_arguments.done` 시점에 바로 발사한다. 모델에 결과를 돌려주는 일은
`call_id`가 필요하므로 여전히 `response.done`에서 한다. 대화 화면 로그에 찍히는 `ms`는
요청 왕복 시간이다.

## allowlist 가 두 개인 이유

`gateway_config.yaml` 에 목록이 둘 있고 서로 다르다.

| 목록 | 뜻 | 현재 |
|---|---|---|
| `api_allowlist` | gateway 가 실행을 허용하는 전부. **운영자 수동 버튼**이 여기서 나온다 | 16개 |
| `llm_allowlist` | 그중 **모델이 스스로 고를 수 있는** 것 | 3개 |

사람이 E-stop 을 두고 버튼으로 부르는 것과, 모델이 대화 중 알아서 고르는 것은 위험도가 다르다.
새 동작은 수동으로 먼저 실물 검증한 뒤 `llm_allowlist` 로 승격한다.

`api_allowlist` 에 넣으려면 `motions.yaml` 에 카탈로그 항목도 있어야 한다 —
없으면 버튼이 뜨지 않고 요청도 거부된다. 로봇에 실제로 로드된 모드 목록은
docs/ROBOT_MODES_20260812.md 를 본다.

## 현재 운영 allowlist

- LLM 이 고를 수 있는 동작은 MimicWaveHand, MimicBowNavel, MimicBadChestpopVer2 셋뿐이다.
- 운영자 수동 버튼은 `api_allowlist` 16개를 부를 수 있다. 이 중 실물 검증된 것은 위 3개뿐이므로 나머지는 공간과 E-stop 을 확보하고 눌러야 한다.
- motions.yaml의 카탈로그 항목이 많더라도 gateway_config.yaml allowlist에 없으면 운영 API로는 실행되지 않는다.
- MimicShadowBoxing 같은 restricted 동작과 없는 동작은 거부한다.
- OPENAI_API_KEY가 없으면 음성 기능은 비활성화되지만 수동 UI는 계속 동작한다.

## Robot Gateway 및 실기 검증

`--robot --https`는 gateway를 시작한다. gateway는 증가하는 sequence의 heartbeat를 **10Hz**로 발행하고,
`mode_status`와 `list_modes`를 읽어 준비된 경우에만 `request_mode_by_name`을 호출한다.

- 첫 API 허용 동작: `MimicWaveHand`, `MimicBowNavel`, `MimicBadChestpopVer2`
- 위 세 동작은 LLM 대화에서도 노출하며, 새 사용자 발화에서는 같은 동작을 다시 실행할 수 있다.
- 모션 실행 중 새 요청은 거부한다. 위험한 동작은 RC 전용이다.
- 시작 시 출력되는 일회용 HTTPS token URL로만 폰을 연결한다.
- `api_arm_probe.py`는 실제 RC를 흉내 내지 않고 heartbeat와 API Arm 전환만 확인한다.

```bash
# ai_sapiens ROS 환경에서
python3 api_arm_probe.py
python3 server.py --robot --https --ready-only
```

**실기 전제**: SD(CH8) API Arm을 ON으로 유지해야 하고, `mode_status`에서
`authority: API`, `api_mode_heartbeat_valid: true`, `api_request_available: true`를 확인한다.
상세 실행법은 docs/CEREMONY_RUNBOOK.md, 구조는 docs/WIRELESS_LLM_ROBOT_ARCHITECTURE.md, 다음 개선 순서는 docs/INTERACTION_EXPANSION_ROADMAP.md를 참고한다.


## 화면

- `/`: 관람객용 음성 대화 화면. 상단 `운영자`로 운영 화면에 이동한다.
- `/operator`: gateway 상태, 정지 버튼, 수동 실행, 다음 세션의 음성·말투 선택. MockBackend에서는 LLM 허용 동작을 실제 실행 없이 로그에 기록한다.
- `/operator` 상단의 빨간 **정지** 버튼은 실행 중인 동작을 중단하고 `ReadyPose`로 되돌린다. 수동 버튼과 달리 실행 중에도 잠기지 않는다. 즉시 탈출이 필요하면 RC Damping/E-stop을 쓴다. 정지는 LLM에 노출하지 않는다 — 음성 왕복이 1.5~3초라 정지 수단으로 부적합하다.
- voice 또는 말투 변경은 연결을 끊고 운영자 화면에서 다시 대화 세션을 시작해야 적용된다.
