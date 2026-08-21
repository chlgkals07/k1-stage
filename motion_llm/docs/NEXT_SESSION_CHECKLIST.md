# 실로봇 세션 체크리스트 (2026-08-13)

오늘 목적: **① API mode로 전 동작 명령(버튼) ② 음성 상호작용 ③ 로그를 쌓아 persona 튜닝.**
**E-stop 담당자와 공간 확보가 전제다.** 발화 목록은 [TEST_DIALOGUES.md](TEST_DIALOGUES.md).

> 수동 버튼은 `/operator` **전용**이다 (관람객 `/`에는 없다). 그리고 gateway가
> `API 준비됨`이 되기 전에는 잠긴다 — SD Arm 전에 버튼이 안 눌리는 건 고장이 아니다.

---

## Phase B-0. 신규 정책을 로봇에 넣기 (사람)

shape10 신규 학습분(ONNX)을 로봇에 배포하고 `go` 재시작. 이건 sim2real 쪽 절차다
(asset/config 설치, 로드맵 §2). 끝나면 아래로.

## Phase B-1. 실측 → 이름 확정 → allowlist 갱신

```bash
cd /home/robotis-ai/Projects/shape3/motion_llm
tools/check_modes.sh          # 로봇 list_modes ↔ 카탈로그 대조
```

- `[로드됨 + 카탈로그 없음]` 항목 → 카탈로그의 state 이름을 실측 이름으로 교정
  (유사 후보를 같이 출력해준다. seed 충돌 주의: anse A456/A459, bow A428/A429)
- 실측 확인된 것만 `status: planned → ready`
- `gateway_config.yaml`: api_allowlist에 실측 존재 전부 추가
  (**제외 유지**: Cartwheel·ShadowBoxing·BoxingNewton·Walk·Damping·ZeroPose·PushUp?),
  llm_allowlist = api − 제외군(회전·긴 댄스·체조·미확인·이동)
- `python3 -m unittest discover -p 'test_*.py'` 통과 확인
- 이 단계는 Claude 와 함께 하면 빠르다 — check_modes 출력을 붙여넣으면 일괄 반영한다.

## Phase B-2. 기동

```bash
./run.sh --deploy      # 갱신된 config 를 로봇에 배포 + gateway 재시작 + relay
```

폰 북마크 URL 접속 → SD **OFF → ON** → 3초 → `/operator`에서 `API 준비됨`.
relay 시작 시 터미널의 `세션 로그 logs/....jsonl` 줄 확인 (목적 ③의 전제).

---

## 1. 정지 먼저 — 멈출 수단 확보

| # | 할 것 | 볼 것 |
|---|---|---|
| 1 | 유휴에서 정지 버튼 | ReadyPose 진입 |
| 2 | 손 흔들기 **실행 중** 정지 | 버튼이 잠기지 않고 눌림 / 실제 멈춤 |
| 3 | 2번 중 `API request` 카드 | **available / unavailable 기록** ⭐ 설계의 미검증 가정 |
| 4 | 정지 직후 | 튐 정도, 복귀 시간 |
| 5 | 정지 후 새 모션 | 정상 수락 |

위험하면 버튼 말고 **RC Damping / E-stop**. 음성 "멈춰"는 열려 있지 않다 (왕복 1.5~3초).

## 2. 버튼 전수 — 목적 ①

`/operator`에서 api_allowlist **전 동작을 1회씩.** `안전 · 제자리` 먼저, `주의` 는 공간 확보 후.

각 동작 기록: 시작·종료 자세 / 이동량 / 소요 시간 / 복귀 상태 / 이상 여부.
이 기록이 `duration_sec`·`entry_pose` 채우기와 LLM 승격 판단의 근거다.

기존 검증 3종(손흔들기·배꼽인사·체스트팝)도 다시 — 운영 경로를 건드렸으므로 회귀 확인.

## 3. 음성 — 목적 ②

[TEST_DIALOGUES.md](TEST_DIALOGUES.md) 순서대로: 회귀 → 신규 유도 → 네거티브 → 경계.
대화 품질(싱크·길이·끼어들기·cooldown)도 함께 관찰.

턴 전환 어색하면: `REALTIME_VAD_SILENCE_MS=300~700` 바꿔 relay 재시작.

## 4. 로그 확인 — 목적 ③

세션 중간과 종료 후:

```bash
ls -la logs/ && tail -5 logs/*.jsonl
```

`user_transcript ↔ motion_request` 가 같은 turn_id 로 묶여 있는지.
분석 원라이너는 TEST_DIALOGUES.md 하단에 있다. 오선택 → desc 수정 → relay 재시작 → 재시도.

## 5. 종료

`./run.sh --stop` → SD OFF → `ros2 topic echo /ai_sapiens/mode_status --once` 로 Manual 확인.

## 기록 양식

```
[정지] 실행중 눌림? / API request 값 / 튐 / 복귀시간
[버튼] 동작명 / 이동량 / 시간 / 이상
[음성] 발화 → 동작 / 정오 / 응답 문장수 / ms
[싱크] 말-동작 간격 체감
```
