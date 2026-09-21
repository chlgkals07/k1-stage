# solo_stage 프로젝트 구조

`solo_stage`는 PC relay, 로봇 gateway, 문서만 관리한다. 로봇 ROS 상태머신 전체는 상위 `ai_sapiens_private`에서 관리한다.

```text
solo_stage/
├── run.sh                    # 실행 진입점. 점검 → 배포 → gateway → relay → 폰 URL
├── README.md                 # 짧은 진입점
├── docs/                     # 현재 문서와 인수인계
├── archive/                  # 과거 코드·설정 스냅샷 (gitignore — 로컬에만)
├── robot/                    # 로봇 적용 파일 매니페스트
├── static/                   # 웹 UI 4장 — pad · display · operator · dance
├── media/                    # 무대 음원·안무 영상 (gitignore — 로컬에만)
├── motions.yaml              # 동작 카탈로그
├── gateway_config.yaml       # api·llm allowlist, stop/entry state, ROS endpoint
│                             # (패드 12칸·무대 프리셋은 ../config/venues/<행사>/ — 행사마다 바뀌는 것)
├── server.py                 # HTTPS UI, stage 상태기계, 무대 싱크, backend 선택
├── relay_backend.py          # PC→robot HTTPS relay
├── robot_backend.py          # robot ROS 2 transport
├── rc_backend.py · rc_serial.py  # RC 폴백 경로 (PC→USB→라디오→ELRS)
├── gateway.py                # 실행 정책·lifecycle·정지·cooldown
├── ports.py                  # 백엔드 계약(Protocol) — Transport · SupportsPrepare · SupportsDuration · SupportsDiscovery
├── clip_len.py               # sim 클립 길이 → 잠금 타이밍 기준
├── session_log.py            # JSONL 세션 로그
├── tools/                    # 진단·검증 스크립트 (check_modes, edge_probe, rehearsal …)
└── test_*.py                 # Python 단위 테스트 (189개)
```

비밀값은 리포지토리에 두지 않는다 — `~/.k1/secrets.env` (chmod 600).

## 폴더 역할

- 루트: 현재 실행에 필요한 코드·설정만 둔다.
- `docs/`: 운영, 설계, 상태를 읽는 곳이다. `README.md`가 문서 색인이다.
- `archive/`: 실행하지 않는 과거 백업이다. 복구나 비교할 때만 본다. **gitignore 대상이라
  이 저장소에는 없고 작업 PC에만 있다** — git 이전 시절에 `*.bak.<주제>_<날짜>` 규칙으로
  남기던 것의 잔재다. 지금 이력은 git 이 들고 있으므로 새 스냅샷을 여기 쌓지 않는다.
- `robot/`: 로봇 ROS 패키지를 중복 보관하지 않고 관리본과 배포 파일을 안내한다.
- `static/`: 별도 frontend 빌드 없이 `server.py`가 그대로 제공하는 웹 UI다.

## 로봇 쪽 배포본

로봇 실행본은 호스트가 아니라 **`ai_sapiens` 도커 컨테이너 안** `/root/motion_llm/`에 있다.
**PC 폴더는 `solo_stage`로 바뀌었지만 로봇 쪽 경로는 아직 옛 이름 그대로다** — 로봇에서
`mv` 하지 않은 채 `run.sh`의 `ROBOT_DIR`만 고치면 빈 디렉터리에 배포되고 gateway 는 옛
코드를 계속 돌린다. 둘은 반드시 같이 바꾼다.

PC와 동기화가 필요한 파일은 `run.sh` 의 `DEPLOY_FILES` 다(지금 11개: 서버·백엔드·`ports.py` 와 정책·카탈로그 yaml).
목록은 `run.sh` 의 `DEPLOY_FILES` 가 정본이다 — 여기에 베껴 적으면 또 썩는다(실제로 코드는 10개인데 문서는 6개였다).
`server.py` 가 import 하는 모듈이 목록에서 빠지면 로봇에서 gateway 가 안 뜨는데, `test_server_tools` 의
`test_deploy_list_covers_imports` 가 그걸 지킨다.

`run.sh`가 md5로 대조하고 `--deploy`로 동기화한다.
`static/`은 PC relay가 서빙하므로 로봇에 없어도 된다.

## 읽는 순서

