# voice — 음성·LLM 경로 재개발

**이 폴더는 `voice-llm-dev` 브랜치에만 있다.** main 에는 음성이 없고, 앞으로도 두지
않는다. 무대 운영(버튼 + 무대 싱크)은 음성 없이 돌아가고 개소식도 그렇게 치렀다.

여기는 **음성을 다시 붙이는 작업 공간**이다. 무대용 코드가 계속 굴러가는 동안
따로 굴리려고 브랜치를 갈랐다.

## 먼저 알아야 할 것 — 코드는 이 저장소에 없다

2026-08-05~17 에 돌던 음성 구현은 **git 에 커밋된 적이 없다.** `.gitignore` 가
`archive/` 를 통째로 걸고 있어서, 제거 당시 스냅샷은 작업 PC 로컬에만 남았다.

```text
solo_stage/archive/server_voice_20260818.py            제거 직전 server.py 전체
solo_stage/archive/index_voice_20260818.html           음성 폰 화면
solo_stage/archive/test_ui_dispatch_voice_20260818.py  해당 테스트
```

그러니 **"옛 커밋으로 되돌리기"가 안 된다.** 되돌릴 커밋이 없다. 재개할 때는 위
파일들을 로컬에서 꺼내 이 브랜치에 새로 올려야 한다. 옛 `archive/` 경로가 아니라
실행 경로(`server.py` 계열, `static/`, `test_*.py`)로 복원한다 — `archive/` 에 두면
gitignore 에 다시 걸린다.

## 지금 main 에 남아 있는 음성 시절 유산

코드에서 **안 지운 것들**이다. 음성이 빠져도 구조가 유효해서 그대로 뒀고, 재개할 때
그대로 쓰면 된다.

| 남은 것 | 어디 | 무엇 |
|---|---|---|
| `llm_allowlist` (21개) | `gateway_config.yaml` | 모델이 스스로 고를 수 있는 동작. `api_allowlist` 의 부분집합 |
| `pad_llm_exclude` | `gateway_config.yaml` | 관객이 말로는 못 부르는 것 (카트휠) |
| `llm_motions()` · `source == "llm"` 검사 | `server.py` | LLM 경로 게이트. 지금은 이 경로로 들어오는 요청이 없을 뿐 살아 있다 |
| `safety: restricted` | `motions.yaml` | 사람이 버튼으로만 부르는 동작 17개 |

`pad_allowlist` 는 `llm_allowlist` 와 같은 발상의 후속이다 — 누가 부르느냐에 따라
위험도가 다르다는 원칙.

## 이 폴더의 문서

| 문서 | 내용 |
|---|---|
| [REMOVED_2026-08-18.md](REMOVED_2026-08-18.md) | 무엇이었고 왜 뺐나. 튜닝 손잡이(VAD·모델·목소리) 표 포함 |
| [INTERACTION_METHODOLOGY.md](INTERACTION_METHODOLOGY.md) | 행동 라이브러리 설계 원칙과 권한 분리 구조 |
| [LLM_ROBOT_RESEARCH_METHODOLOGY.md](LLM_ROBOT_RESEARCH_METHODOLOGY.md) | 연구 질문·비교 실험·평가 지표·참고 논문 |
| [INTERACTION_EXPANSION_ROADMAP.md](INTERACTION_EXPANSION_ROADMAP.md) | 당시 로드맵. §5 Locomotion↔API 검증 절차는 아직 유효 |
| [TEST_DIALOGUES.md](TEST_DIALOGUES.md) | 발화 → 동작 매핑 기록. 새 동작 `desc`/`tags` 쓸 때 참고 |
| [DEMO_SCRIPT.md](DEMO_SCRIPT.md) | 4막 데모 시나리오. 동작 배치는 패드·무대 순서 짤 때도 쓸 수 있다 |

## 재개할 때 확인할 것

음성을 뺀 이유가 기술적 실패가 아니라 **운영 형태의 문제**였다는 점을 기억한다 —
왕복 1.5~3초가 쇼의 리듬을 끊었고 시끄러운 현장에서 인식이 불안정했다. 같은 형태로
되돌리면 같은 문제를 만난다. 자세한 것은 REMOVED_2026-08-18.md 의 "왜 뺐나".

그리고 **정지는 모델에 노출하지 않는다**는 규칙은 그대로 간다. 즉시 탈출은 RC
Damping / E-stop 이 담당한다.
