# motion_llm 프로젝트 구조

`motion_llm`은 PC relay, 로봇 gateway, 문서만 관리한다. 로봇 ROS 상태머신 전체는 상위 `ai_sapiens_private`에서 관리한다.

```text
motion_llm/
├── run.sh                    # 실행 진입점. 점검 → gateway → relay → 폰 URL
├── README.md                 # 짧은 진입점
├── docs/                     # 현재 문서와 인수인계
├── archive/snapshots_*/      # 과거 코드·설정·문서 스냅샷
├── robot/                    # 로봇 적용 파일 매니페스트
├── static/                   # 아이폰 웹 UI (index=관람객, operator=운영자)
├── motions.yaml              # UI/LLM 모션 카탈로그
├── gateway_config.yaml       # api/llm allowlist, stop_state, ROS endpoint
├── server.py                 # HTTPS UI, Realtime session, backend 선택
├── relay_backend.py          # PC→robot HTTPS relay
├── robot_backend.py          # robot ROS 2 transport
├── gateway.py                # 실행 정책·lifecycle·정지·cooldown
└── test_*.py                 # Python 단위 테스트 (46개)
```

비밀값은 리포지토리에 두지 않는다 — `~/.k1/secrets.env` (chmod 600).

## 폴더 역할

- 루트: 현재 실행에 필요한 코드·설정만 둔다.
- `docs/`: 운영, 설계, 상태를 읽는 곳이다. `README.md`가 문서 색인이다.
- `archive/`: 실행하지 않는 과거 백업이다. 복구나 비교할 때만 본다.
  이 저장소는 git이 아니라서 수정 전 스냅샷을 `*.bak.<주제>_<날짜>` 규칙으로 남긴다.
- `robot/`: 로봇 ROS 패키지를 중복 보관하지 않고 관리본과 배포 파일을 안내한다.
- `static/`: 별도 frontend 빌드 없이 `server.py`가 그대로 제공하는 웹 UI다.

## 로봇 쪽 배포본

로봇 실행본은 호스트가 아니라 **`ai_sapiens` 도커 컨테이너 안** `/root/motion_llm/`에 있다.
PC와 동기화가 필요한 파일은 6개다.

```text
server.py  gateway.py  robot_backend.py  relay_backend.py
gateway_config.yaml  motions.yaml
```

`run.sh`가 md5로 대조하고 `--deploy`로 동기화한다.
`static/`은 PC relay가 서빙하므로 로봇에 없어도 된다.

## 읽는 순서

