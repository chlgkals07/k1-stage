# solo_stage — Wi-Fi 단일 로봇 운영 서버

K1 한 대를 Wi-Fi로 운영하는 정본 앱이다. 관객이 아이패드에서 동작을 고르면 미리보기가 TV에
뜨고, [실행]을 누르면 로봇이 움직인다. 운영자는 폰으로 상태를 보고 정지를 쥔다.

```
아이패드 /pad ─┐
폰 /operator ─┼─ 장소 랜 ── PC relay ──Wi-Fi──> 로봇 gateway ──> ROS 2
메인컴 /dance ─┘                │                 request_mode_by_name
                                └── HDMI ── TV /display
```

여러 대를 동시에 움직이거나 Wi-Fi가 죽었을 때는 옆의 [`group_stage`](../group_stage/)가 라디오
전파로 직접 쏜다. 라디오 준비는 [`rc_link`](../rc_link/)에 있다.

## 실행

로봇과 함께 쓸 때는 `run.sh` 하나면 된다. 로봇에서 `go`(ROS bringup)만 사람이 띄운다.

```bash
./run.sh            # 점검 → gateway 확인/기동 → relay 실행 → 접속 URL 출력
./run.sh --status   # 상태만 확인
./run.sh --deploy   # PC→로봇 파일 동기화까지
./run.sh --stop     # 정리
~/k1links 18444     # 화면 4개 접속 링크
```

토큰이 고정이라 접속 URL이 매번 같다 — 한 번 북마크하면 끝이다.
비밀값은 `~/.k1/secrets.env`(chmod 600, 저장소 밖)에 있고 첫 실행 때 만들어진다.

로봇 없이 UI만 보려면:

```bash
python3 server.py --https          # 자체 서명 인증서 자동 생성
```

`pyyaml` 외 의존성이 없다.

현장 절차 전체는 [docs/RUNBOOK.md](docs/RUNBOOK.md) 하나로 끝난다.

## 화면

| 경로 | 기기 | 역할 |
|---|---|---|
| `/pad` | 아이패드 | 관객: 동작 선택 → **미리보기 → [실행]** |
| `/display` | TV | 무대: 대기 / 미리보기 / 실행중 / 무대영상 |
| `/operator` | 폰·메인컴 | 정지 · 상태 · 수동 버튼 · 무대 시작/정지 · RC 모드 토글 |
| `/dance` | 메인컴 | 음악 싱크 오프셋 보정 |

`/`로 들어오면 `/pad`로 리다이렉트된다(옛 북마크 대응).

`/operator` 상단의 빨간 **정지**는 실행 중인 동작을 중단하고 로봇을 `Velocity`(보행·균형)로
되돌린다. 수동 버튼과 달리 실행 중에도 잠기지 않는다. **즉시 탈출이 필요하면 RC Damping /
E-stop을 쓴다** — 항상 최우선이고 네트워크와 무관하다.

## `motions.yaml`이 핵심이다

이 파일 하나가 여러 곳에 쓰인다. 동작을 추가·제외하려면 **이 파일부터** 고친다.

| 쓰임 | 무엇을 보나 |
|---|---|
| 웹 UI | `page`별 탭, `ko`로 버튼 이름, `desc`로 설명 |
| 안전 게이트 | `safety: restricted`는 관객·모델 경로에서 거부 |
| RC 매핑 | `rc_list` — 로봇 다이얼 2뱅크 × 20슬롯의 실배포 덤프 |

현재 카탈로그는 **136개**, 그중 `restricted`가 17개다.

### 허용목록이 세 개인 이유

카탈로그에 있다고 실행되지는 않는다. `gateway_config.yaml`이 최종 게이트다.

| 목록 | 뜻 | 현재 |
|---|---|---|
| `api_allowlist` | gateway가 실행을 허용하는 전부. **운영자 수동 버튼**이 여기서 나온다 | **78개** |
| `pad_grid` (venue) | 그중 **관객 아이패드에 여는 것**. 행사 연출이라 `config/venues/` 에 있다 | **12개** |
| `llm_allowlist` | 그중 **모델이 스스로 고를 수 있는 것** | **21개** |

사람이 E-stop을 두고 버튼으로 부르는 것, 관객이 아무거나 누르는 것, 모델이 대화 중 고르는
것은 위험도가 다르다. 새 동작은 **수동으로 먼저 실물 검증한 뒤** 패드·모델에 승격한다.

허용목록에 있어도 `motions.yaml`에 카탈로그 항목이 없으면 버튼이 뜨지 않고 요청도 거부된다.
로봇에 policy 자체가 없어도 거부된다 — 실제 로드 목록은
[docs/reference/ROBOT_MODES_20260812.md](docs/reference/ROBOT_MODES_20260812.md), 대조는
`tools/check_modes.sh`.

## 잠금 타이밍

기준은 **sim 클립 길이 = 그 동작이 도는 시간**이다(`clip_len.py`가 mp4 헤더에서 읽는다).
동작이 끝나고 2초 뒤 패드가 풀리고, 3초 뒤 서버가 화면을 되돌린다(안전망).

현장에서 조절하려면 세 값이 같은 뜻이므로 함께 움직인다:
`static/pad.html`의 `+2000` · `server.py`의 `EXEC_IDLE_MARGIN_SEC` ·
`rc_backend.py`의 `BUSY_MARGIN_SEC`. 근거는
[docs/STATUS.md §4](docs/STATUS.md#잠금-타이밍-구조).

## 파일

| 파일 | 역할 |
|---|---|
| `motions.yaml` | 동작 카탈로그 + RC 매핑 |
| `gateway_config.yaml` | 허용목록 3종, 정지 목표 상태, ROS 엔드포인트 |
| `server.py` | 화면 서빙, stage 상태기계, 무대 스케줄, 백엔드 선택 |
| `relay_backend.py` | PC → 로봇 HTTPS relay |
| `robot_backend.py` · `gateway.py` | 로봇 쪽 ROS 게이트웨이와 실행 정책 |
| `rc_backend.py` · `rc_serial.py` | 유선 RC 경로 |
| `clip_len.py` | sim 클립 길이 측정 |
| `run.sh` | 실행 진입점. 점검·배포·기동·정리 |
| `test_*.py` | 단위 테스트 **172개** |

로봇과 동기화가 필요한 파일은 6개다(`server.py` `gateway.py` `robot_backend.py`
`relay_backend.py` `gateway_config.yaml` `motions.yaml`). `run.sh`가 md5로 대조한다.

## 문서

[docs/](docs/)에 있다. [RUNBOOK](docs/RUNBOOK.md) 절차 · [STATUS](docs/STATUS.md) 현재 상태 ·
[ARCHITECTURE](docs/ARCHITECTURE.md) 설계 — 이 셋이면 대개 끝난다.

## 저장소에 없는 것

`media/`(음원·안무 영상 417MB, 저작권물) · `static/clips/`(동작 sim 렌더 39MB) ·
`logs/`(관객 발화 원문) · TLS 개인키 · `archive/`. 전부 로컬에만 둔다.
