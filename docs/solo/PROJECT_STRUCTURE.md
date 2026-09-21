# 프로젝트 구조

앱은 `app.py` 하나고 모드가 둘이다(`--mode solo|fleet`). 이 저장소는 PC relay, 로봇 gateway, 화면, 문서를 관리한다.
로봇 ROS 상태머신 전체는 상위 `ai_sapiens_private`에서 관리한다.

```text
k1-stage/
├── app.py                    # HTTPS UI, 모드·백엔드 선택, State 배선 (상태기계·무대 싱크는 core/stage.py)
├── run.sh                    # 로봇 배포·relay 기동 진입점. 점검 → 배포 → gateway → relay → 폰 URL
├── core/                     # 도메인: stage(상태기계·무대 싱크) · ports(백엔드 계약) · catalog(설정 검증)
├── runtime/                  # 통신 경로·보조: relay_backend · robot_backend · rc_backend · rc_fleet · rc_serial ·
│                             #   gateway(실행 정책·lifecycle·정지·cooldown) · clip_len · session_log
├── web/                      # 화면 4장(pad · display · operator · dance) · k1.js · base/tool.css · themes/
├── config/
│   ├── solo/  fleet/         # 모드별 motions.yaml(카탈로그+RC 다이얼) · gateway_config.yaml(api_allowlist 등)
│   └── venues/<행사>/        # venue.yaml(패드 12칸) · presets.json(프리셋·오프셋) — 행사마다 바뀌는 것
├── tools/                    # preflight · 진단·검증 스크립트 (check_modes, edge_probe, rehearsal …) · start_fleet.sh
├── tests/                    # 단위 테스트 (`python3 -m unittest discover -s tests -t .`)
├── docs/                     # solo/ · fleet/ 운영 문서 · design/ · RESTRUCTURE.md
├── rc_link/  robot/          # 라디오 Lua·믹서 패치 · ai_sapiens 변경분
├── media/ clips/ logs/       # 음원 · 동작 sim 렌더 · 세션 로그 (gitignore — 로컬에만)
└── archive/                  # 과거 스냅샷 (gitignore — 로컬에만)
```

비밀값은 리포지토리에 두지 않는다 — `~/.k1/secrets.env` (chmod 600).

## 폴더 역할

- 루트: 실행 진입점(`app.py` · `run.sh`)만 둔다.
- `docs/solo/`, `docs/fleet/`: 운영, 설계, 상태를 읽는 곳이다. `docs/solo/README.md`가 문서 색인이다.
- `archive/`: 실행하지 않는 과거 백업이다. **gitignore 대상이라 이 저장소에는 없고 작업 PC에만 있다.**
  지금 이력은 git 이 들고 있으므로 새 스냅샷을 여기 쌓지 않는다.
- `web/`: 별도 frontend 빌드 없이 `app.py`가 그대로 제공하는 웹 UI다.

## 로봇 쪽 배포본

로봇 실행본은 호스트가 아니라 **`ai_sapiens` 도커 컨테이너 안** `/root/motion_llm/`에 있다.
**PC 쪽 이름은 여러 번 바뀌었지만 로봇 쪽 경로는 아직 옛 이름 그대로다** — 로봇에서
`mv` 하지 않은 채 `run.sh`의 `ROBOT_DIR`만 고치면 빈 디렉터리에 배포되고 gateway 는 옛
코드를 계속 돌린다. 둘은 반드시 같이 바꾼다.

PC와 동기화가 필요한 파일은 `run.sh` 의 `DEPLOY_FILES` 다(지금 15개: `app.py`, `runtime/` 아홉 개, `config/solo/` 의 yaml 둘, 그리고 `core/` 세 개). 저장소와 같은 배치의 부분집합이 로봇의 같은 경로에 풀린다.
목록은 `run.sh` 의 `DEPLOY_FILES` 가 정본이다 — 여기에 베껴 적으면 또 썩는다(실제로 코드는 10개인데 문서는 6개였다).
`app.py` 가 import 하는 모듈이 목록에서 빠지면 로봇에서 gateway 가 안 뜨는데, `tests/test_server_tools` 의
`test_deploy_list_covers_imports` 가 그걸 지킨다.

`run.sh`가 md5로 대조하고 `--deploy`로 동기화한다.
`web/`은 PC relay가 서빙하므로 로봇에 없어도 된다.

## 읽는 순서

