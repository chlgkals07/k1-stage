# 상태와 인수인계

갱신일: **2026-08-20**

> 예전의 `STATUS_AND_HANDOVER`(8/12판) · `FINAL_REVIEW_2026-08-18` · `archive/snapshots_20260812`의
> 옛 판을 합친 것이다. 세 문서가 서로 다른 시점의 "지금 무엇이 참인가"를 주장하고 있어
> 어느 것을 믿어야 할지 알 수 없었다. 이 문서가 유일한 현재 상태다.

---

## 0. 지금 무엇이 참인가

| 항목 | 현재 값 |
|---|---|
| 운영 경로 | **버튼(preview→실행)과 무대(dance)뿐.** 음성은 2026-08-18 제거 |
| 화면 | `/pad`(관객) · `/display`(TV) · `/operator`(운영자) · `/dance`(싱크 보정) |
| 동작 카탈로그 (`motions.yaml`) | **136개** (그중 `restricted` 17개) |
| gateway `api_allowlist` | **78개** — 운영자 수동 버튼이 부를 수 있는 전부 |
| gateway `pad_allowlist` | **12개** — 관객 패드에 뜨는 것 |
| gateway `llm_allowlist` | **21개** — 모델 경로용. **현재 이 경로로 들어오는 요청은 없다** |
| 정지 목표 상태 | **`Velocity`** (Damping일 때만 `ReadyPose`) |
| RC 다이얼 | 2뱅크 × 20슬롯 = **40**. CH5로 뱅크, CH11로 슬롯 |
| 테스트 | `motion_llm` 135 · `rc_stage` 94 |

실기 검증된 인사 3종은 `MimicWaveHand`(손 흔들기) · `MimicBowNavel`(배꼽 인사) ·
`MimicBadChestpopVer2`(체스트팝)이다. 개소식에서 패드 12개 중 10개가 정상 동작했다
(기사식 인사·마카레나는 로봇 config 미등록으로 거부).

---

## 1. 통신 경로

```text
아이패드·폰 (장소 랜)
  → PC: relay (192.168.0.9, 포트 18444)
  → PC Wi-Fi: k1-orinnx10
  → K1 robot gateway (192.168.60.1:8443, HTTPS)
  → ROS 2 request_mode_by_name
  → ai_sapiens_sim2real / Mimic policy
```

PC는 장소 랜과 로봇 Wi-Fi를 동시에 쓴다. 아이패드는 로봇 AP에 직접 붙지 않는다.
DHCP로 주소가 바뀔 수 있으므로 실행 전 `ip route get 192.168.60.1`로 확인한다.

**차선 경로**가 하나 더 있다. Wi-Fi가 죽으면 `rc_stage`가 PC → USB → RadioMaster Pocket →
ELRS 전파로 직접 쏜다. 로봇 소프트웨어 수정이 필요 없고, 꽂은 라디오 수만큼 로봇이 같이 움직인다.

---

## 2. 허용목록이 세 개인 이유

| 목록 | 뜻 | 개수 |
|---|---|---|
| `api_allowlist` | gateway가 실행을 허용하는 전부. **운영자 수동 버튼**이 여기서 나온다 | 78 |
| `pad_allowlist` | 그중 **관객 아이패드에 여는 것** | 12 |
| `llm_allowlist` | 그중 **모델이 스스로 고를 수 있는 것** | 21 |

사람이 E-stop을 두고 버튼으로 부르는 것, 관객이 아무거나 누르는 것, 모델이 대화 중 고르는
것은 위험도가 다르다. 승격 경로는 **수동으로 먼저 실물 검증 → 그 뒤 패드·모델에 개방**이다.

`motions.yaml`의 136개 카탈로그는 이 허용목록 없이는 운영 권한을 얻지 못한다.
반대로 허용목록에 있어도 카탈로그 항목이 없으면 버튼이 뜨지 않고 요청도 거부된다.

---

## 3. 안전 경계

1. **RC Damping / E-stop이 최상위.** 네트워크와 무관하게 항상 동작하고 API보다 우선한다.
2. RC의 **SD(CH8)가 API 권한의 물리 허가**다. 내리면 PC가 무슨 말을 해도 안 움직인다.
   반대로 **RC 모드에서는 SD를 내려야** 명령이 먹는다 — 로봇은 API 권한일 때 teleop 전이를
   무시하므로, SD가 올라가 있으면 RC 펄스가 조용히 무시되고 PC는 라디오에서 `OK`를 받아
   성공으로 보고한다. **무대에서 가장 헷갈릴 실패 모양이다.**
3. PC relay와 robot gateway가 **각각** 허용목록을 검사한다.
4. gateway는 heartbeat · API authority · mode readiness를 확인한 뒤에만
   `request_mode_by_name`을 호출한다. **단 정지는 예외**로 allowlist·busy·cooldown과
   `request_available`을 우회한다 — Mimic 실행 중 이 플래그가 내려가면 정지가 거부되어
   기능이 무의미해지기 때문이다.
5. API key와 token은 PC의 `~/.k1/secrets.env`(chmod 600, 저장소 밖)에만 둔다.
   문서·Git·채팅에 저장하지 않는다.

### 로봇이 권한을 잃으면 어디로 가는가

로봇 소스(`mode_controller.cpp`)로 확인한 실제 실패 거동이다. **"끊기면 ReadyPose로 간다"는
걱정은 사실이 아니었다.**

| 끊긴 것 | 로봇이 하는 일 |
|---|---|
| PC↔로봇 Wi-Fi | **아무 일도 안 남.** 현재 상태 유지 |
| RC 링크 (라디오 꺼짐·전파 두절) | **Damping (힘 빠짐)** — 0.2초 만에 |
| PC 프로세스 종료 / USB 분리 | 라디오가 0.5초 내 게이트 해제 → **물리 스위치 위치로 복귀** |
| 동작이 정상 종료 | **Velocity(보행·균형)** 로 스스로 복귀 |
| heartbeat 상실 중 Mimic 실행 중 | **Velocity** (Mimic 타깃도 Velocity로 치환) |

**단, 그 순간 물리 teleop 입력이 특정 상태를 가리키면 그쪽이 우선한다.**
물리 SC 스위치가 CH7 중앙(1500 = code 2 = ReadyPose)이면 ReadyPose로 간다.
SD를 내려 수동 인계할 때도 같다 — 그 순간의 물리 스위치 위치로 즉시 간다.

→ **운영 수칙**: 대기 중 물리 스위치는 SC 상단(CH7 2000) + SB 중앙(CH6 1500)에 두거나
SB 하단(Velocity)에 둔다. **SC 중앙에 두지 않는다.** 코드로 막을 수 있는 부분이 아니다.

---

## 4. 2026-08-18 최종 리뷰 — 고친 것 12건

배포 확정 전 마지막 점검이다. 코드 정독과 실행 테스트(엣지 51종, 3면 리허설, 치명 후보 재현)
두 갈래로 했고, 로봇 쪽 근거는 8/18 로봇 백업 원본에서 확인했다.

| # | 증상 | 수정 |
|---|---|---|
| 1 | 빨간 정지가 로봇을 **ReadyPose**(균형 없는 고정 자세)로 선점 | `stop_state: Velocity`. 단 로봇이 **Damping**일 때만 `entry_state: ReadyPose`로 자동 전환(상태기계상 탈출구가 그것뿐) — **버튼은 그대로 하나** |
| 2 | 무대 시작 직후 정지를 눌러도 **2~3.5초 뒤 로봇이 안무를 시작** | `stop_motion`이 backend 호출 **전에** 무대 예약(발사·PREP·자동종료)을 무력화하고 무대도 내린다 |
| 3 | `/dance`에서 오프셋을 저장하면 `media_len_sec`이 사라져 **84.5초 무대가 65초에 강제 종료** | `save_preset`이 `media_len_sec`도 보존, `start_dance`가 인라인 시작에서도 같은 음원 프리셋에서 복구 |
| 4 | **RC 모드로 켜는 순간 운영자 수동 버튼이 전부 사라짐**(0개) | `RcBackend.status()`가 primary와 같은 `api_allowlist`를 실어 보냄 |
| 5 | 패드 12번(구압)이 **RC 다이얼에 없어 RC 모드에서만 죽는 버튼** | 다이얼 슬롯을 v1→v2로 교체. **로봇 쪽도 같이 바꿔야 함 → §6-①** |
| 6 | 운영자가 수동 실행하면 **관객 패드 12개가 최대 60초 잠김** | 동작 길이(sim 클립 실측)만큼 뒤 서버가 스스로 idle 복귀. 60초+ → **8.0초** |
| 7 | RC 모드에서 4초짜리 손인사도 **30초 잠김** | 같은 모션으로 구운 클립 길이를 씀 (손인사 3.98s, 스쿼트 3.98s, 마카레나 29.5s) |
| 8 | 라디오 무응답 시 폴링이 시리얼 락을 물어 **빨간 정지가 7초 지연** | TLM 1초 캐시 + 동시 갱신 1개 제한 → **3.95초** |
| 9 | 무대 자막에 동작 약칭 **"체스트팝 v2"** 가 새는 경로 | 못 찾으면 **비운다**. 서버·디스플레이 양쪽에서 약칭 폴백 제거 |
| 10 | `--rc`로 단독 기동하면 **토큰 인증이 통째로 꺼짐** | `protected` 집합에 `rc` 추가 |
| 11 | 무대 시작 직후 ~1초 동안 관객 탭이 **안무 대신 다른 동작**을 낼 수 있었음 | 무대 중 `source=pad`는 서버가 거부 |
| 12 | 깨진 JSON이 오면 **응답 없이 연결이 끊기고** 운영자 콘솔이 traceback으로 덮임 | 400으로 응답 |

새 파일은 `clip_len.py` 하나다. sim 클립 mp4 헤더에서 길이만 읽는다(표준 라이브러리, 실패하면
조용히 None → 기본값으로 떨어짐). 클립을 다시 구우면 자동 반영된다.

### 잠금 타이밍 구조

기준은 **sim 클립 길이 = 그 동작이 도는 시간**이다. 세 시계가 같은 기준에서 나온다.

| 시각 | 일어나는 일 | 주체 |
|---|---|---|
| 0.0s | 명령 발사 | 패드/운영자 |
| +L | 로봇 동작 종료(추정). L = 클립 길이 | 로봇 |
| **+L+2.0s** | 패드 진행바 종료 → 잠금 해제 + `/stage idle` | 패드 |
| **+L+2.0s** | RC 로봇 busy 해제 | 서버(RC) |
| **+L+3.0s** | 서버가 화면을 idle로 되돌림 (패드가 이미 보냈으면 무시) | 서버 — 안전망 |

여백 2초를 남긴 이유: 실기가 sim보다 조금 느릴 수 있고, 여백이 0이면 로봇이 마무리 동작
중일 때 다음 명령이 나간다. 너무 빠르면 관객이 아직 움직이는 로봇에 다음 버튼을 누르고,
너무 늦으면 쇼가 늘어진다.

현장에서 조절하려면 `static/pad.html`의 `+2000`, `server.py`의 `EXEC_IDLE_MARGIN_SEC`,
`rc_backend.py`의 `BUSY_MARGIN_SEC` 세 값이 같은 뜻이므로 함께 움직인다.

클립이 없는 동작은 화면 복귀 기본 12초, RC busy 기본 30초. 둘 다 stage TTL(60초)이 백스톱이다.
**무대(dance)는 이 사다리를 쓰지 않는다** — 영상 종료 신호가 주 해제자이고
`max(영상 길이, 동작 추정) + 5초`가 안전망이다.

---

## 5. 검증했고 문제없던 것

- 패드 12개 preview→실행→대기 복귀 12/12, 무대 3종 전부 대기 화면 복귀, preview 취소 복귀
- 무대 중 패드 잠금, 무대 재시작 시 이전 세대 발사 무력화, 정지 후 늦은 콜백 무력화
- stage TTL(preview 120s / executing 60s / dance 480s) 만료 복귀
- 디스플레이가 죽었다 살아나면 **진행 중 무대에 합류**
- 무대 싱크 계산: `+`면 로봇 먼저 / `−`면 음원 먼저, 리드타임 2초 확보
- 클립·음원 Range(206)·416, 경로 탈출 차단(`../`), 잘못된 프리셋 입력 거부
- RC PREP→FIRE 순서, busy 거부, 발사 관측 대조식이 `verify_sweep` 40/40 기준과 동일
- HTTPS 토큰 게이팅(쿠키 발급·오토큰 403), `/` → `/pad` 리다이렉트
- PC↔로봇 AP 무선 연결, 아이패드→relay→로봇 end-to-end 요청
- 동작 완료 후 동일 동작 재실행

---

## 6. 실기 전에 사람이 해야 하는 일

### ① 로봇 다이얼 교체 (필수)

안 하면 패드 12번이 RC에서 계속 죽는다. 로봇 `ai_sapiens`의 `config/k1_config.yaml`:

```yaml
selectors:
  mimic_selector_b:
    table:
      202: MimicGuapVer2      # 기존 MimicGuap 에서 교체
```

표기는 둘 다 "구압/GUAP"라 화면상 차이는 없다. 바꾼 뒤 로봇 백업을 다시 떠서
`rc_link/gen_rc_list.py <k1_config> motions.yaml`로 rc_list를 재생성하면 정합이 유지된다.
PC 쪽 `motions.yaml`의 rc_list는 이미 v2로 바꿔 뒀다.

### ② 라디오 `K1PC.lua`에 `VEL` 추가 (선택)

현재 RC 정지는 `VEL`을 먼저 시도하고, 라디오가 `ERR`을 주면 기존 `STOP`(ReadyPose)로
폴백한다. **SD 카드를 안 건드려도 지금과 똑같이 동작한다.** 옮기면 RC 경로도 locomotion
복귀가 된다. `rc_link/radio/K1PC.lua`의 `startPulse` 분기에 3줄:

```lua
  elseif kind == "VEL" then
    setGv(GV_CH6, -100)  -- CH6 1000
    setGv(GV_CH7, 100)   -- CH7 2000  → 둘이 합쳐 code 3 = Velocity
```

`handleLine`의 `STOP/DAMP` 분기에 `VEL`을 추가해 `startPulse("VEL", ...)`를 부르고
`OK VEL`로 답하게 한다. 옮긴 뒤에는 도구 EXIT → 재실행이 필요하다.

### ③ RC 검증은 어디까지 됐나

| 구간 | 상태 | 근거 |
|---|---|---|
| PC → 라디오 (USB, 프로토콜) | **실측 완료** | K1PC 왕복 avg 0.4ms, ping 50/50 손실 0 |
| 라디오 믹서 출력 = 기존 다이얼과 동일 | **실측 완료** | `verify_sweep.py` 40/40, pct 모델 대비 오차 ≤2µs |
| 우리 채널 조합 ↔ 로봇 teleop 규약 일치 | **코드 대조 완료** | 로봇 `radiomaster_pocket.yaml` input_code 표와 1:1 |
| **전파 → 로봇이 실제로 동작 실행** | **미검증** | 로봇 앞에서 한 번은 돌려야 한다 |
| SD(CH8) 권한 상호작용 | **미검증** | §3-2는 소스 근거이지 실측이 아니다 |

### ④ 실기에서 확인할 것

- 정지 → `request_mode_by_name("Velocity")`가 실제로 수락되는지 (Damping 상태에서 1회)
- RC 발사 관측이 실제로 뜨는지, 뱅크/슬롯이 의도대로 나가는지
- dance 오프셋 재보정: `-rc` 프리셋 3종은 지금 `offset_ms: 0`이다. RC 경로 지연은 Wi-Fi
  대비 수십 ms 차이라 **`-api` 값(-1500 / +500 / 0)에서 출발**해 미세 조정하는 편이 가깝다
- **저속 locomotion 중 API 출력 연속성** — `teleop_velocity_passthrough`는 로봇 배포·빌드와
  하드웨어 비연결 테스트 25/25까지 끝났으나 실제 움직임에서는 미검증이다

---

## 7. 일부러 안 고친 것

지금 잘 돌아가는 경로를 건드리지 않으려고 남겨 뒀다. 나중에 판단할 것.

1. 무대 중 디스플레이를 새로고침하면 영상이 **0초부터** 재생된다(로봇과 어긋남).
   합류 자체는 되므로 사고는 아니다. 고치려면 `media_at` 기준으로 `currentTime`을 계산.
2. 디스플레이가 preview **도중에** 처음 열리면 클립 목록을 아직 못 받아 영상 대신 동작
   이름만 뜬다. 다음 화면 전환 때 정상화된다.
3. 무대 오디오 잠금 오버레이가 자동재생이 막힌 브라우저에서 계속 남는다.
   현장에서 TV를 한 번 탭하는 절차로 커버 중.
4. `executing` 화면은 카탈로그 한글명을 쓴다 — 무대 3종을 **수동으로** 실행하면
   "체스트팝 v2"가 뜬다. 무대 경로에는 안 뜬다.
5. `/dance` 배지가 RC 모드에서 "MODE 확인 불가"로 뜬다(표시만).
6. `-api`/`-rc` 프리셋 6개가 한 목록에 섞여 있고 현재 경로와 자동으로 묶이지 않는다.
7. `run.sh`에 RC 실행 경로가 없다. RC는 운영자 화면 토글로만 켠다(설계대로).
8. RC 발사 관측이 **불일치**여도 실행은 성공으로 보고한다(경고만).
9. `K1PC.lua`의 `abortAll`은 게이트를 내리면서 같은 틱에 GV를 0으로 되돌린다. 게이트 반영
   지연(≤100ms) 동안 CH7=1500(ReadyPose)이 전파될 여지가 이론상 있다. 정상 종료 경로는
   `T_GATE_LAG`를 두는데 abort 경로만 없다. 실측되지 않아 건드리지 않았다.

---

## 8. 음성 대화 (2026-08-18 제거)

**지금은 없는 기능이다.** 아래는 무엇이었고 왜 뺐는지의 기록이다.

2026-08-05부터 8-17까지 이 앱의 주 경로는 **아이폰 음성 대화**였다. 관객이 폰에 말을 걸면
OpenAI Realtime API가 짧게 답하고, 대화 의미에 맞는 K1 Mimic policy를 실행했다.

```text
브라우저 ──WebRTC(음성)──> OpenAI Realtime API
    │  function call: play_motion(motion, reason)
    ↓ fetch POST /motion
 server.py → MotionBackend → relay → gateway → request_mode_by_name
```

오디오는 **브라우저와 OpenAI 사이에서만** 흘렀다. 서버는 작은 JSON만 받았다.

### 설계에서 나온 것들 (지금도 살아 있는 것)

- **`llm_allowlist`** — 모델이 스스로 고를 수 있는 것을 `api_allowlist`의 부분집합으로
  제한하는 게이트. `source=llm` 검사는 `server.py`에 그대로 있고, 지금은 이 경로로 들어오는
  요청이 없을 뿐이다. `pad_allowlist`가 같은 발상의 후속이다
- **`safety: restricted`** — 복싱·섀도우복싱처럼 격한 동작은 사람이 버튼으로만 부른다.
  뺨 때리기 류는 **카탈로그에 아예 넣지 않는다**. 현재 17개가 restricted다
- **정지를 모델에 노출하지 않는 규칙** — 음성 왕복이 1.5~3초라 정지 수단으로 부적합했다.
  즉시 탈출은 RC Damping / E-stop이 담당한다는 원칙이 여기서 나왔다
- **발사 시점을 `response.done`이 아니라 `response.function_call_arguments.done`으로**
  당긴 것 — 말과 동작을 맞추기 위해서였고, 같은 "예약을 먼저 무력화한다"는 발상이
  현재 무대 정지 로직(§4-2)에 남아 있다

### 튜닝 손잡이였던 것

`PERSONA`(`server.py`)와 `motions.yaml`의 `desc`/`tags`가 모델이 동작을 고르는 유일한
근거였다. 그 밖에 환경변수로 대화 감각을 조절했다.

| 변수 | 기본값 | 역할 |
|---|---|---|
| `REALTIME_MODEL` / `REALTIME_VOICE` | `gpt-realtime-2.1` / `marin` | 모델·목소리 |
| `REALTIME_MAX_TOKENS` | 350 | 응답 길이 하드캡 (폭주 방지용) |
| `REALTIME_VAD_TYPE` | `server_vad` | `semantic_vad`로 바꾸면 의미로 발화 종료를 판단 |
| `REALTIME_VAD_SILENCE_MS` | 400 | **턴 전환 느낌의 주 손잡이.** 300~700에서 맞춘다 |
| `REALTIME_VAD_THRESHOLD` / `_PREFIX_MS` | 0.5 / 300 | 감지 민감도 / 감지 직전 오디오 포함량 |

### 왜 뺐나

개소식 운영 형태가 **관객이 아이패드에서 고르고 TV로 보는 쇼**로 바뀌면서, 음성은 경로가
길고(왕복 1.5~3초) 시끄러운 현장에서 인식이 불안정해 쇼의 리듬을 끊었다. 버튼 preview→실행이
같은 일을 더 확실하게 했다.

### 원본은 어디에

```text
archive/server_voice_20260818.py            제거 직전 server.py 전체
archive/index_voice_20260818.html           음성 폰 화면
archive/test_ui_dispatch_voice_20260818.py  해당 테스트
```

`/`로 들어오는 옛 북마크는 `/pad`로 리다이렉트된다(`server.py:658`).
당시의 연구 설계와 평가 지표는
[methodology/LLM_ROBOT_RESEARCH_METHODOLOGY.md](methodology/LLM_ROBOT_RESEARCH_METHODOLOGY.md)와
[methodology/INTERACTION_METHODOLOGY.md](methodology/INTERACTION_METHODOLOGY.md)에 남아 있다.

---

## 9. 저장소와 배포 위치

| 구분 | 위치 | 내용 |
|---|---|---|
| PC 작업본 | `k1-stage/motion_llm/` | UI, relay, gateway, 동작 카탈로그 |
| 로봇 실행본 | **`ai_sapiens` 컨테이너 안** `/root/motion_llm/` | `server.py --robot`으로 뜨는 HTTPS/ROS gateway |
| 로봇 sim2real 소스 | 로봇의 `/root/ros2_ws` | API authority와 Mimic 실행 상태머신 |
| 그 관리본 | `k1-stage/robot/` | 로봇에 적용·빌드한 변경의 원본·현행·patch |

로봇과 동기화가 필요한 파일은 6개다: `server.py` `gateway.py` `robot_backend.py`
`relay_backend.py` `gateway_config.yaml` `motions.yaml`.
`run.sh`가 md5로 대조하고 `--deploy`로 동기화한다. `static/`은 PC relay가 서빙하므로
로봇에 없어도 된다. **이 경로에서 실제로 두 번 사고가 났다.**
