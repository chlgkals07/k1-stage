# K1 대화형 인터랙션 방법론

작성일: 2026-08-07

> 연구 질문, 비교 실험, 평가지표와 관련 논문 정리는
> [LLM_ROBOT_RESEARCH_METHODOLOGY.md](LLM_ROBOT_RESEARCH_METHODOLOGY.md)를 참고한다.

## 한 줄 결론

K1에서 LLM은 관절값이나 보행을 직접 만들지 않는다. **대화 문맥에 맞는 검증된
행동을 선택하는 interaction director** 역할을 맡고, 기존 Mimic policy와
`ai_sapiens_sim2real` 상태머신이 실제 동작과 안전을 담당한다.

```text
음성/대화 (향후 비전 포함)
  -> LLM: 의도, 감정, 대화 문맥 판단
  -> Interaction Director: 행동 0~2개 선택, 순서/쿨다운/상태/안전 검사
  -> Motion Library: 검증된 Mimic state만 허용
  -> ai_sapiens_sim2real: API 권한, Mimic 실행, failsafe, Damping
```

이 구조의 목표는 “항상 몸을 움직이는 로봇”이 아니라, **중요한 말에 작고 적절한
비언어 반응을 하는 로봇**이다.

---

## 왜 행동 라이브러리인가

LLM이 새 관절 trajectory를 직접 출력하게 하면 지연, 재현성, 물리 안전을 보장하기
어렵다. K1에는 이미 영상 -> retarget -> Mimic RL policy 경로가 있으므로, 새 동작은
그 경로에서 학습하고 LLM은 state 이름만 고르게 한다.

이 방식의 장점:

- 로봇이 실행할 수 있는 행동만 LLM에 노출한다.
- 모션별 안전 등급과 실행 전제조건을 강제할 수 있다.
- RC 수동 모션 페이지가 앱/API의 즉시 백업 경로가 된다.
- 잘못 선택한 사례는 trajectory가 아니라 카탈로그 설명, 분류, prompt를 고쳐서
  반복 개선할 수 있다.

---

## 관련 사례와 배울 점

### 1. Microsoft Research — GPT + gesture library

Microsoft Research의 *Co-Speech Gesturing Chat System*은 GPT가 대화를 생성하고,
별도 gesture engine이 발화 의미에 맞는 행동을 gesture library에서 선택한다.
MSRAbot 및 Toyota HSR 예제를 제공했다.

- K1 적용: `motions.yaml`을 gesture library로, `play_motion(state)`를 선택 API로 사용한다.
- 배울 점: LLM은 의미/대화 담당, 실행기는 로봇별 제스처 담당으로 분리한다.

출처: <https://www.microsoft.com/en-us/research/articles/gpt-models-meet-robotic-applications-co-speech-gesturing-chat-system/>

### 2. Pepper — 사전정의 행동 우선, 생성은 fallback

AAMAS 2025의 Pepper 연구는 LLM이 대화 문맥에 맞춰 로봇의 기존 애니메이션 풀에서
행동을 선택해 음성과 동기화했다. 새 관절각 생성도 시도했으나 속도가 느려, 적합한
사전정의 행동이 있으면 그것을 먼저 실행하는 전략을 사용했다.

- K1 적용: 신규 행동이 필요하면 실시간 관절 생성 대신 새 Mimic motion을 학습한다.
- 배울 점: 빠른 현장 반응에는 pre-defined/검증된 행동 우선이 적합하다.

출처: <https://ifaamas.csc.liv.ac.uk/Proceedings/aamas2025/pdfs/p242.pdf>

### 3. Furhat / Pepper — 고수준 intent와 제한된 출력 공간

Frontiers 2025 연구는 음성 생성과 함께 로봇별 가능한 행동 공간 안에서 제스처를
생성/분류하는 방법을 Furhat와 Pepper에서 평가했다.

- K1 적용: LLM 출력은 `intent` 또는 허용된 `state` enum으로 제한한다.
- 배울 점: 언어 모델의 자유 출력 뒤에 robot-specific 제약 계층이 반드시 필요하다.

출처: <https://www.frontiersin.org/journals/robotics-and-ai/articles/10.3389/frobt.2025.1581024/full>

### 4. 사회적 로봇의 정서적 비언어 단서

SAFE(Speech, Action, Facial expression, Emotion)로 비언어 단서를 라벨링하여 LLM이
선택하게 한 연구가 있다. 단순한 끄덕임 같은 작은 반응이 대화의 자연스러움에 중요하다.

출처: <https://arxiv.org/abs/2308.16529>

### 5. 표현이 많다고 항상 좋은 것은 아님

Honda Research의 Haru 파일럿은 음성과 표정/몸 표현을 동기화한 방식을 선호한
참가자가 많았지만, 표현 빈도나 강도가 지나치면 부정적 반응이 생길 수 있다고 보고했다.

- K1 적용: 매 발화마다 큰 모션을 실행하지 않는다. 동작 없음도 올바른 선택이다.

출처: <https://doi.org/10.1145/3776734.3794507>

---

## 행동 라이브러리 설계

### 우선순위

처음부터 큰 춤을 늘리기보다, 1~3초 길이의 마이크로 반응을 우선 확보한다.

| 비율 | 그룹 | 예시 |
|---:|---|---|
| 50% | idle / 경청 / micro-reaction | 기본 자세, 듣기, 끄덕임, 고개 갸웃, 생각하기, 주변 살피기 |
| 30% | communicative gesture | 손 흔들기, 목례, 감사, 박수, 왼쪽/오른쪽 안내, 가리키기 |
| 15% | 감정 표현 | 기쁨, 놀람, 아차, 자신감, 부탁 |
| 5% | 큰 퍼포먼스 | 짧은 춤, 큰 축하 표현 |

초기 목표는 **마이크로 동작 25~40개 + 검증된 2단 시퀀스 10개**다.

### 카탈로그 메타데이터

`motions.yaml`의 `state`, `ko`, `desc`, `safety`, `llm` 외에 아래 필드를 추가하는
방향을 권장한다.

```yaml
state: MimicListeningNod
intent: listening_ack
class: micro_reaction
duration_sec: 1.4
entry_pose: stand
exit_pose: stand
can_follow: [micro_reaction, gesture, idle]
cooldown_sec: 2
requires: [standing, clear_space]
interaction_allowed: true
```

`desc`는 LLM에게 전달되는 핵심 정보다. 현재 `build_tools()`는 `tags`가 아니라
`state`, `ko`, `desc`를 tool description에 넣는다. 따라서 행동 선택이 헷갈리면
태그만 늘리지 말고 `desc`에 **언제 쓰고 언제 쓰지 않는지**를 명시한다.

예:

```yaml
desc: 상대의 말을 듣고 이해했다는 짧은 반응. 질문을 듣는 중이나 긍정할 때 사용한다.
      인사·축하·방향 안내 용도로는 사용하지 않는다.
```

---

## 시퀀싱 규칙

임의의 Mimic motion을 계속 연결하면 시작/종료 자세, 팔 위치, 중심 이동이 맞지 않아
어색하거나 위험할 수 있다. 첫 버전에서는 아래를 강제한다.

- 한 대화 턴에 행동은 최대 1개, 필요할 때만 최대 2개.
- `entry_pose: stand`와 `exit_pose: stand`인 마이크로 동작끼리만 연속 실행한다.
- 이동, 회전, 점프, 큰 춤은 단독 실행한다.
- 다음 행동은 이전 행동 완료 뒤 `/ai_sapiens/mode_status`가 `Velocity` 또는 준비 상태로
  복귀한 것을 확인한 뒤 시작한다.
- 자주 쓰는 조합(예: `경청 끄덕임 -> 방향 안내`)은 임의 조합 대신 사전 검증한
  sequence로 등록한다.
- 모션 재생 중 새 발화에는 기본적으로 음성만 응답한다. 중단 가능한 안전 행동만
  명시적으로 interrupt한다.

---

## LLM 행동 선택 검증: 로봇 연결 전

### 전제

실로봇에서 쓸 후보와 동일하게 `--ready-only`로 mock 테스트한다. `planned` 동작은
실로봇 테스트의 LLM 후보에서 제외한다.

### 평가 세트

행사에서 나올 발화 30~50개를 만들고, 각 발화를 최소 3회 반복한다. 정답은 state 하나가
아닌 **허용 행동군**으로 정의한다.

| 발화 | 허용 행동군 | 금지 |
|---|---|---|
| “안녕 K1” | 손 흔들기, 목례 | 춤, 이동 |
| “수고했어, 멋지다” | 박수, 기쁨 | 복싱, 점프 |
| “저쪽이 어디야?” | 방향 가리키기 + 음성 | 회전, 걷기 |
| “그만, 쉬어” | 기본 자세/Velocity | 새 Mimic 실행 |
| “뭐라고?” | 되묻기, 동작 없음 | 임의 모션 |
| 모션 중 “안녕” | 음성만 응답 또는 현재 동작 유지 | 모션 중첩 |

### 통과 기준

- 허용 행동군 선택률: 90% 이상
- 존재하지 않거나 금지된 모션 선택: 0%
- 모션 중첩/연타: 0%
- 불필요한 몸동작은 사람 평가로 계속 줄인다.

로그에는 `전사 -> LLM 답변 -> tool call -> 평가`를 남긴다. 실패는 우선
`desc`, 행동 분류, prompt, sequence 규칙을 수정해 해결한다.

---

## 폰과 로봇 API 연결 계획

### 권장 구조

첫 연결에는 Zenoh를 넣지 않는다. 로봇 PC에서 `motion_llm` 서버를 ROS2 gateway로
실행하고, 폰은 기존 HTTPS만 사용한다.

```text
폰 브라우저
  -> HTTPS POST /motion
  -> robot PC: motion_gateway
       - heartbeat publisher (10 Hz)
       - ModeStatus subscriber
       - RequestModeByName service client
  -> ai_sapiens_sim2real
  -> Mimic policy

RC
  -> API Arm (SD): 앱/API 권한의 물리적 허가
  -> Damping: 어떤 경우에도 즉시 탈출
  -> X/SA + 20-slot selector: API 실패 시 수동 백업
```

### ROS 계약

| 목적 | ROS 이름 | 타입/조건 |
|---|---|---|
| heartbeat 발행 | `/ai_sapiens/api_mode_heartbeat` | `ApiModeHeartbeat`; 증가하는 `sequence`, 10 Hz 권장 |
| 행동 요청 | `/ai_sapiens/request_mode_by_name` | `RequestModeByName`; `mode_name`에 concrete Mimic state |
| 상태 확인 | `/ai_sapiens/mode_status` | `ModeStatus`; 실행 가능성 및 UI 피드백 |

API 요청은 아래가 모두 참일 때만 보낸다.

```text
authority == API
api_mode_heartbeat_valid == true
api_request_available == true
```

현재 설정의 API warm-up은 3초다. 폰 UI는 SD Arm 직후 “API 준비 중”을 보여주고, 위
상태가 되기 전의 요청은 실행하지 않는다.

### 구현/검증 순서

1. 조종기에서 SA/SD/X 및 20-slot selector의 실제 RC 채널과 PWM을 측정한다.
2. SD를 API Arm으로 확정하고, X/SA 두 페이지의 수동 모션 백업을 구성한다.
3. `motion_gateway`에 ROS2 publisher/subscriber/service client를 추가한다.
4. LLM 없이 폰 수동 버튼으로 안전 행동 하나를 요청한다.
5. gateway가 `accepted -> executing -> completed/rejected`를 폰에 전달하는지 확인한다.
6. 마지막에 Realtime의 `play_motion` tool call을 같은 `/motion` endpoint에 연결한다.

gateway는 LLM이 고른 state를 그대로 실행하지 않는다. 카탈로그 화이트리스트, 학습
완료 여부, 안전 등급, 현재 로봇 상태, cooldown을 다시 검사하는 최종 실행자다.

### RC/API의 역할 분리

- SD/API Arm: 폰 명령을 허용하는 물리적 deadman.
- RC Damping: 항상 API보다 우선하는 즉시 탈출.
- X/SA 수동 페이지: API 또는 네트워크 실패 때 동일/유사 모션을 사람이 직접 실행하는 백업.
- 앱/gateway: API Arm이 해제되면 새 요청을 보내지 않고 UI에도 수동 모드임을 표시한다.

Zenoh은 gateway가 로봇 PC 외부의 별도 PC로 이동하거나, 여러 로봇/별도 네트워크를
연결해야 할 때 gateway와 로봇 사이에 도입한다. 첫 실로봇 연결에서 로컬 ROS2 service
대신 Zenoh을 먼저 넣을 필요는 없다.
