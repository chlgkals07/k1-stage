# K1 대화·동작·UI 확장 로드맵

작성일: 2026-08-10

## 1. 현재 기준선

현재 운영 구조:

```text
아이폰(일반 Wi-Fi)
→ Omen PC HTTPS UI / OpenAI Realtime / RelayBackend
→ PC Wi-Fi k1-orinnx10
→ Robot gateway
→ ROS 2 request_mode_by_name
→ ai_sapiens_sim2real
→ 검증된 Mimic policy
```

현재 LLM과 robot API 양쪽에서 허용한 동작은 세 개다.

| 발화 의도 | state | 현재 상태 |
|---|---|---|
| 일반 인사·작별 | `MimicWaveHand` | 실물 확인 |
| 정중한 인사·감사 | `MimicBowNavel` | 실물 확인 |
| 명시적인 신나는 동작·체스트팝 요청 | `MimicBadChestpopVer2` | 실물 확인 |

반복 규칙:

- 한 사용자 발화당 tool call은 최대 1회다.
- 동작 실행 중 새 동작 요청은 gateway가 거부한다.
- 동작이 끝나고 `Velocity`로 복귀한 뒤 새로운 발화에서는 같은 동작을 다시 실행할 수 있다.
- 일반 질문에는 음성으로만 답하고 몸동작을 호출하지 않는다.

검증 결과:

- Python gateway/relay/tool 테스트 10개 통과
- 로봇 sim2real C++ 설정·상태전환 테스트 25개 통과
- `ReadyPose → API → Mimic` 실물 동작 확인
- 동일 인사 반복 발화에서 손 흔들기 재실행 확인
- Mimic policy 실행 도중 중단 시 약한 전환 튐은 있었으나 안정적으로 복귀함
- locomotion teleop velocity passthrough는 로봇 배포와 단위 테스트까지 완료

아직 남은 핵심 실물 검증은 비영 속도 locomotion 중 API 전환, 이동 중 Mimic 진입·종료의 출력 연속성, Mimic 완료 후 최신 RC 속도 복귀다. 중단 뒤의 안정 복귀는 확인했지만 전환 튐의 정량 측정·완화는 별도 항목이다.

## 2. 변경 종류별 필요한 재시작

| 변경 | 필요한 작업 | `cb`/`go` |
|---|---|---|
| PC `PERSONA`, `motions.yaml`, LLM allowlist | PC relay 재시작 | 불필요 |
| `static/index.html` UI | 브라우저 새로고침; 필요 시 PC relay 재시작 | 불필요 |
| robot gateway API allowlist | robot gateway 재시작 | 불필요 |
| 이미 로드된 Mimic state를 앱에 노출 | PC/robot gateway 설정 갱신과 재시작 | 불필요 |
| `k1_config.yaml` state/policy 변경 | 설정 설치 반영 후 bringup 재시작 | 경우에 따라 필요 |
| sim2real C++ 변경 | 패키지 빌드 후 `go` 재시작 | 필요 |
| 새 policy asset 배포 | asset/config 설치 및 검증 후 `go` 재시작 | 필요 |

단순 카탈로그 확장 때문에 전체 robot bringup을 재시작하지 않는다.

## 3. 동작 확장 우선순위

### 3.1 다음 추가 후보

다음 두 동작은 로봇에 이미 로드돼 있어 새 policy 빌드는 필요 없다.

| state | 권장 용도 | 필요한 작업 |
|---|---|---|
| `MimicDeepDab001A467` | 명시적인 “멋진 포즈”, “댑 해줘” | 카탈로그 메타데이터, 수동 실물 검증, 양쪽 allowlist |
| `MimicGuapIntroP2` | 자기소개 뒤 짧은 시그니처 포즈 | 카탈로그 메타데이터, 수동 실물 검증, 양쪽 allowlist |

추가 순서:

1. RC 또는 수동 버튼으로 단독 실행한다.
2. 필요한 공간, 동작 시간, 시작·종료 자세를 기록한다.
3. `motions.yaml`에 `ko`, `desc`, `safety`, `duration_sec`, `requires`를 추가한다.
4. robot API allowlist에 먼저 추가하고 수동 버튼으로 재검증한다.
5. 마지막에 PC LLM allowlist와 PERSONA 발화 매핑을 추가한다.

### 3.2 수동 전용으로 먼저 검증할 동작

- `MimicGuapVer2`
- `MimicShuffleDance`
- `MimicDanceBasicTurnV1360RLoopFast003A325`
- `MimicCoinPick`

회전, 발 이동, 큰 중심 이동 가능성이 있어 처음에는 LLM에 열지 않는다. UI의 운영자 전용 수동 버튼에서 공간과 복귀 상태를 확인한 뒤 승격한다.

### 3.3 당분간 LLM 금지

- `MimicWalk1Subject1`
- `MimicShadowBoxing`
- `MimicBoxingNewton`

Walk는 RC locomotion과 역할이 충돌한다. 복싱류는 사람과의 거리 조건이 필요하므로 공간 인식이나 운영자 승인 없이 LLM이 선택하면 안 된다.

## 4. 대화 정책 개선

현재 명확한 규칙 기반 매핑:

| 예시 발화 | 예상 동작 |
|---|---|
| “안녕”, “반가워”, “잘 가” | WaveHand |
| “정중하게 인사해줘”, “감사합니다” | BowNavel |
| “체스트팝 보여줘” | BadChestpopVer2 |
| “너는 누구야?”, “오늘 기분 어때?” | 동작 없음 |

추가 정책:

- 모션 중에는 음성 답변은 가능하지만 새 모션은 예약하지 않는다.
- 한 발화에 두 동작을 요청해도 하나만 선택한다.
- “멈춰”, “그만”은 새 동작보다 높은 우선순위로 처리한다.
- 같은 동작의 최소 재실행 간격을 motion별 `cooldown_sec`로 관리한다.
- 큰 동작은 명시적 요청에만 허용한다.
- 실패 시 모델이 성공한 것처럼 말하지 않고 실행 불가를 알린다.

행사 발화 30~50개를 만들고 각 발화를 3회씩 실행해 동작 선택률, 불필요한 동작률, 금지 동작률을 기록한다.

## 5. Locomotion → API → Mimic 실물 검증

처음부터 빠르게 움직이면서 Mimic을 호출하지 않는다.

### 단계 A: Velocity 상태, 속도 0

1. E-stop 담당자와 충분한 공간을 확보한다.
2. `Velocity` 상태에서 스틱은 중립으로 둔다.
3. heartbeat가 유효한 상태에서 SD를 OFF → ON으로 전환한다.
4. `MANUAL → API_WARMUP → API`와 `active_mode: Velocity` 유지를 확인한다.
5. 스틱 중립 상태에서 WaveHand를 호출하고 완료 후 Velocity 복귀를 확인한다.

### 단계 B: 아주 낮은 비영 속도

1. SD OFF에서 저속 직진을 시작한다.
2. SD를 ON으로 바꾸고 속도가 끊기지 않는지 관찰한다.
3. API 전환 뒤 스틱을 중립으로 놓아 정지한다.
4. WaveHand를 실행한다.
5. 완료 뒤 스틱 중립이 유지되어 재출발하지 않는지 확인한다.

### 단계 C: 최신 RC 속도 복귀

충분히 검증된 뒤에만 Mimic 중 스틱 변경과 완료 후 최신 RC 명령 복귀를 확인한다. Mimic 완료 순간 스틱이 전진이면 즉시 움직일 수 있으므로 운영 시험에서는 기본적으로 스틱 중립을 강제한다.

기록 항목:

- authority 전환 시 속도 discontinuity
- Mimic 진입 전 감속 시간
- Mimic 종료 뒤 첫 velocity command
- heartbeat/PC Wi-Fi 손실 시 정지와 Manual 복귀 시간

## 6. UI 개선 우선순위

### P0: 현장 안전과 상태 가시성

- robot `list_modes`와 양쪽 allowlist 교집합만 버튼으로 표시
- `MANUAL`, `API_WARMUP`, `API`, heartbeat, RC link를 상단 고정 표시
- 동작 실행 중 모든 motion 버튼 비활성화
- 현재 동작, 경과 시간, 완료 후 복귀 상태 표시
- 거부 사유를 “API 준비 안 됨”, “실행 중”, “허용 안 됨”, “연결 끊김”으로 구분

2026-08-11 A 단계 완료: `/`는 관람객 대화·동작 이력 전용, `/operator`는 gateway 상태·허용 수동 모션·음성/말투 설정 전용으로 분리했다. 최초 URL token은 secure cookie 발급 뒤 주소창에서 제거하며, 운영자 수동 버튼은 API `ready` 상태가 아니거나 요청 처리 중이면 잠긴다. Realtime 한국어 입력 전사를 켜서 사용자와 K1의 대화 이력을 안전한 텍스트 렌더링으로 남긴다.
- 운영자용 SD OFF 안내와 E-stop 확인 문구

### P1: 대화 경험

- 음성 연결, 듣는 중, 생각 중, 말하는 중, 움직이는 중 상태 표시
- 현재 인식된 사용자 발화와 선택된 동작 이유 표시
- 동작별 cooldown과 남은 대기 시간 표시
- 대화용 화면과 운영자 수동 제어 화면 분리
- 큰 글씨·큰 버튼의 행사장 kiosk 모드

### P2: 운영성

- 자동 reconnect와 재연결 횟수 표시
- PC 인터넷과 robot Wi-Fi 상태를 별도 표시
- 세션별 로그 다운로드
- 관리자만 allowlist와 발화 매핑을 바꾸는 설정 화면
- 방문객 화면에는 token이나 내부 state 이름을 노출하지 않기

## 7. 통신·프로세스 안정성

1. PC relay가 robot gateway에 주기적으로 lease를 갱신한다.
2. PC relay가 끊기면 robot gateway heartbeat를 자동 중단한다.
3. robot gateway와 PC relay를 systemd 또는 명시적인 tmux launcher로 관리한다.
4. 중복 heartbeat publisher를 탐지하고 시작을 거부한다.
5. 포트 충돌 시 backend thread까지 정상 종료해 core dump를 남기지 않는다.
6. 20~30분 Wi-Fi soak test와 AP 재연결 시험을 수행한다.
7. OpenAI 장애 시 수동 버튼은 유지하고 음성만 degraded 상태로 표시한다.

보안 원칙:

- OpenAI API key는 PC에만 둔다.
- robot token과 PC UI token을 문서, Git, 채팅에 저장하지 않는다.
- ~~서버 재시작 시 새 PC UI token을 사용한다.~~
  **2026-08-12 변경**: `run.sh` 도입과 함께 토큰을 고정했다. 매번 새 토큰을 손으로 옮기는
  비용이 커서 폰 북마크가 불가능했기 때문이다. 대가로 **같은 네트워크에서 URL을 한 번 본
  사람은 계속 접근할 수 있다.** 토큰은 `~/.k1/secrets.env`(chmod 600)에만 둔다.
  회전이 필요하면 그 파일의 `K1_UI_TOKEN`/`K1_ROBOT_TOKEN`을 지우고 다시 실행하면 새로 만든다.

## 8. 속도와 모션 전환 품질

- RC linear/angular scale을 각각 기록하고 행사장 최대 속도를 정한다.
- acceleration/deceleration limiter를 적용한다.
- Locomotion → Mimic 전에 0.2~0.5초 감속 구간을 검토한다.
- Mimic → Velocity 복귀 시 최신 RC 명령을 바로 적용할지 ramp할지 결정한다.
- motion별 `entry_pose`, `exit_pose`, `duration_sec`, `footprint_m`, `cooldown_sec`를 카탈로그에 추가한다.

## 9. 개소식 운영 완료 기준

- 세 가지 기본 대화 동작 30회 반복에서 오동작 0회
- 동일 인사 반복, 모션 중 재요청, 일반 질문 negative control 통과
- 저속 locomotion API 전환과 heartbeat 손실 시험 통과
- 30분 무선 soak test 통과
- PC relay와 robot gateway 재시작 절차 3회 반복 성공
- E-stop 담당자와 종료 절차 리허설 완료
- UI에서 API/heartbeat/RC/실행 중 상태를 한눈에 확인 가능

## 10. 권장 다음 작업

1. UI P0 구현
2. `DeepDab`, `GuapIntroP2` 메타데이터와 수동 검증
3. Velocity 속도 0 상태에서 API → WaveHand 실물 시험
4. 저속 locomotion → API 연속성 시험
5. upstream lease와 프로세스 supervisor 구현
6. 행사 발화 평가 세트와 로그 리포트 추가
