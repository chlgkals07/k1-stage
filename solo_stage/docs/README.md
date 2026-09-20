# solo_stage 문서

루트는 실행 코드와 설정만 두고, 운영·상태·설계 문서는 여기서 관리한다.

## 세 문서면 대개 끝난다

| 문서 | 언제 보나 |
|---|---|
| **[RUNBOOK.md](RUNBOOK.md)** | 로봇을 돌릴 때. 셋업 → 검증 → 장애 대응 → 종료 |
| **[STATUS.md](STATUS.md)** | "지금 무엇이 참인가". 허용목록 실제 값, 최종 리뷰 결과, 남은 검증 |
| **[ARCHITECTURE.md](ARCHITECTURE.md)** | 왜 이렇게 생겼나. 네트워크·gateway·ROS 계약·보안 |

## 그 밖

| 문서 | 내용 |
|---|---|
| [RC_WIRED_COMMAND_PLAN.md](RC_WIRED_COMMAND_PLAN.md) | 유선 RC 명령 경로(PC→라디오→ELRS→K1) 설계와 단계별 계획 |
| [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md) | 폴더 역할과 로봇 동기화 대상 6파일 |
| [worklog/](worklog/) | 날짜별 작업 기록 5편. 결론이 아니라 경위 |
| [reference/](reference/) | 실측 데이터 — 로봇 모드 목록, 학습 후보 |

## 코드에서 시작할 때

```text
실행 진입점:            ../run.sh
관객·운영자 화면 요청:   server.py → relay_backend.py
로봇 HTTPS/ROS gateway: server.py --robot → robot_backend.py → gateway.py
RC(유선 라디오) 경로:    server.py --rc → rc_backend.py → rc_serial.py
동작·안전 메타데이터:    ../motions.yaml, ../gateway_config.yaml
로봇 상태머신 변경분:    ../../robot/
```

## 새 동작을 여는 순서

카탈로그만 고쳐서는 아무 일도 일어나지 않는다. **넷이 모두 맞아야 한다.**

```text
1. motions.yaml 에 카탈로그 항목      ← 없으면 버튼이 안 뜨고 요청도 거부된다
2. gateway_config.yaml api_allowlist  ← 운영자 수동 버튼으로 실행 가능해짐
3. 실물 단독 검증 (공간 + E-stop)
4. venue 의 pad_grid 또는 llm_allowlist ← 그 뒤에야 관객·모델에게 연다
```

로봇에 policy 자체가 없으면 gateway가 "현재 로봇에 배포되지 않은 동작입니다"로 거부한다.
실제 로드 목록은 [reference/ROBOT_MODES_20260812.md](reference/ROBOT_MODES_20260812.md),
대조 도구는 `tools/check_modes.sh`다.

## 음성·LLM 경로는 여기 없다

한때 이 앱의 주 경로는 아이폰 음성 대화(OpenAI Realtime)였고 2026-08-18에 뺐다.
관련 문서와 재개 지침은 **`voice-llm-dev` 브랜치**의 `docs/voice/`로 옮겼다.

코드에는 `llm_allowlist`·`pad_llm_exclude`·`source == "llm"` 검사가 아직 살아 있다.
지금 이 경로로 들어오는 요청이 없을 뿐이고, 구조가 유효해서 그대로 뒀다.
