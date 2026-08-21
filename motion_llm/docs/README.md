# motion_llm 문서 안내

루트는 실행 코드와 설정만 두고, 설계·운영·상태 문서는 이 폴더에서 관리한다.

### 지금 작업을 이어갈 때 (이 순서로)

| 문서 | 용도 |
|---|---|
| [STATUS_AND_HANDOVER.md](STATUS_AND_HANDOVER.md) | **첫 문서.** 지금 무엇이 참인가 — 검증된 것과 아닌 것 |
| [NEXT_SESSION_CHECKLIST.md](NEXT_SESSION_CHECKLIST.md) | **로봇 앞에서 볼 한 장.** Phase B 절차 + 검증 순서 |
| [TEST_DIALOGUES.md](TEST_DIALOGUES.md) | 음성 세션용 추천 발화와 세션 후 로그 분석법 |
| [DEMO_SCRIPT.md](DEMO_SCRIPT.md) | 데모 영상용 4막 다이얼로그 + 재시작 방법 |
| [CEREMONY_RUNBOOK.md](CEREMONY_RUNBOOK.md) | 현장 시작·종료 절차 (`./run.sh` 빠른 경로 + 수동 폴백) |
| [WORK_LOG_2026-08-14.md](WORK_LOG_2026-08-14.md) | **실기 로그 분석 + 안정화·UI** — 빈 motion 버그, 무선 링크, 카테고리, PTT, 자막 |
| [FIELD_SETUP.md](FIELD_SETUP.md) | 새 장소 셋업 (무선 전제) — 라우터·배치·끊겼을 때 |
| [WORK_LOG_2026-08-13.md](WORK_LOG_2026-08-13.md) | shape10 탐색 / 로깅 / PERSONA 개편 / check_modes — Phase A |
| [WORK_LOG_2026-08-12.md](WORK_LOG_2026-08-12.md) | 정지 경로 / 응답·VAD·발사시점 / allowlist 16개 / `run.sh` |

### 사실 확인용

| 문서 | 용도 |
|---|---|
| [ROBOT_MODES_20260812.md](ROBOT_MODES_20260812.md) | **로봇 실측 모드 24개.** 관리본 `k1_config.yaml`은 신뢰 불가 |
| [WIRELESS_LLM_ROBOT_ARCHITECTURE.md](WIRELESS_LLM_ROBOT_ARCHITECTURE.md) | 네트워크, gateway, ROS 계약, 로봇 배포 상세 |

### 방향을 정할 때

| 문서 | 용도 |
|---|---|
| [INTERACTION_EXPANSION_ROADMAP.md](INTERACTION_EXPANSION_ROADMAP.md) | UI·안전·동작 확장 우선순위 |
| [INTERACTION_METHODOLOGY.md](INTERACTION_METHODOLOGY.md) | LLM과 모션 라이브러리의 역할 분리 원칙 |
| [LLM_ROBOT_RESEARCH_METHODOLOGY.md](LLM_ROBOT_RESEARCH_METHODOLOGY.md) | 연구 질문, 실험 설계, 지표, 참고 논문 |
| [MOTION_TRAINING_BACKLOG.md](MOTION_TRAINING_BACKLOG.md) | BONES-SEED 학습 후보와 metadata 매칭 |
| [MOTION_TRAINING_COHORT_01.md](MOTION_TRAINING_COHORT_01.md) | 1차 학습 후보 10개와 검증 gate |

## 코드에서 시작할 때

```text
실행 진입점:            ../run.sh
PC/아이폰 요청:         server.py → relay_backend.py
로봇 HTTPS/ROS gateway: server.py --robot → robot_backend.py → gateway.py
로봇 상태머신 관리본:    ../ai_sapiens_private/ai_sapiens_sim2real/
동작·안전 메타데이터:    ../motions.yaml, ../gateway_config.yaml
```

## 새 동작을 여는 순서

카탈로그만 고쳐서는 아무 일도 일어나지 않는다. **셋이 모두 맞아야 한다.**

```text
1. motions.yaml 에 카탈로그 항목    ← 없으면 버튼이 안 뜨고 요청도 거부된다
2. gateway_config.yaml api_allowlist ← 운영자 수동 버튼으로 실행 가능해짐
3. 실물 단독 검증 (공간 + E-stop)
4. gateway_config.yaml llm_allowlist ← 그 뒤에야 모델이 고를 수 있다
```

로봇에 policy 자체가 없으면 gateway가 "현재 로봇에 배포되지 않은 동작입니다"로 거부한다.
실제 로드 목록은 [ROBOT_MODES_20260812.md](ROBOT_MODES_20260812.md)를 본다.

로봇 실행본은 **호스트가 아니라 `ai_sapiens` 도커 컨테이너 안** `/root/motion_llm/`에 있다.
`../run.sh`가 PC↔로봇 파일 md5를 대조하므로 배포 누락은 자동으로 잡힌다.
