# 코드 읽기 안내 — 레이어 순서로

이 저장소를 처음 여는 사람이 **안쪽(데이터)에서 바깥쪽(화면)으로** 읽도록 짠 안내다. 무엇을 하는 파일인지,
왜 그렇게 생겼는지, 어디가 위험한지, 직접 돌려 볼 명령을 회차마다 적었다. 한 회차는 30~60분이다.
막히면 그 자리에서 멈추고 물어본다 — 다음 회차는 이해한 뒤에 간다.

> 이 문서는 코드가 아니라 **지도**다. 파일 이름·줄 수는 바뀐다. 헷갈리면 코드가 맞다.
> 구조가 바뀌면 이 문서의 해당 회차를 같이 고친다(그래서 줄 번호는 적지 않았다).

## 한 장 지도

```
                 ┌────────────── web/ ───────────────┐   화면 4장 (HTML+JS, 빌드 없음)
                 │ pad(관객) display(TV) operator dance │
                 └───────────────┬───────────────────┘
                                 │ HTTP (폴링)
        app.py  ── HTTP 라우트 · 인증 · 부팅 검증 · 모드(solo|fleet) · State 배선
                                 │
        core/stage.py ── 무대 상태기계 (동작 실행 규칙 · dance 스케줄 · 정지)     ← 도메인. 파일도 하드웨어도 모른다
        core/ports.py ── 백엔드가 지켜야 할 모양(Transport)
        core/catalog.py ── 설정 셋의 정합 검증 (부팅과 preflight 가 같이 씀)
                                 │ Transport 계약
        runtime/ ── 로봇에 실어 나르는 다섯 경로 + 보조
          mock(app.py 안) · relay_backend(PC→로봇 HTTPS) · robot_backend+gateway(로봇 안 ROS)
          rc_backend+rc_serial(유선 RC→ELRS) · rc_fleet(라디오 여러 대)
        config/ ── 데이터: solo/ fleet/(카탈로그·정책) · venues/<행사>/(패드·프리셋·오프셋)
```

**의존은 안쪽으로만 흐른다.** `core/` 는 `runtime/` 도 `app.py` 도 import 하지 않는다. 그래서 하드웨어 없이
테스트가 돈다(`tests/test_stage.py` 는 0.1초). 이 규칙이 깨지면 이 구조가 무너진다 — 새 코드를 어디에 둘지
모르겠으면 "이게 파일·네트워크·하드웨어를 아는가?"를 묻는다. 안다면 `core/` 에 두면 안 된다.

## 읽기 전에 알아야 할 것 (5분)

1. **로봇이 움직이기까지의 길** — 관객이 아이패드에서 버튼 → `POST /motion` → `State.play` 가 검사(카탈로그에 있나 ·
   패드 허용 목록인가 · 무대 중인가) → `backend.submit` → (relay 면) PC 가 HTTPS 로 로봇의 gateway 에 전달 →
   gateway 가 다시 검사(`api_allowlist`) → ROS 서비스로 로봇에 요청. **검사가 두 번이다.** 서버가 뚫려도 gateway 가 막는다.
2. **정지는 별개의 길이다.** `POST /stop` 은 허용 목록·실행 중 여부를 거치지 않는다(안전 기능이라 우회한다).
   그리고 dance 무대를 **정지하는 것과 로봇을 세우는 것은 다르다** — 무대 정지는 영상·예약만 내리고 로봇은 동작을 끝까지
   마친다. 로봇을 즉시 세우려면 빨간 정지 버튼이나 RC/E-stop 이다.
3. **허용 목록은 둘이고 서로 다르다.** `api_allowlist`(정책: 로봇이 받는 전부) ⊇ `pad_grid`(행사 연출: 관객 패드 12칸).
   venue 가 권한을 넓힐 수는 없다 — 서버가 교집합을 낸다.
4. **모드는 둘이다.** `solo`(로봇 1대, Wi-Fi/RC) · `fleet`(라디오 여러 대 군무). 같은 코드에 데이터·화면 표·기본값만 다르다.
5. **`main` 은 무대에 나가는 브랜치라 건드리지 않는다.** 이 문서는 `rebuild` 브랜치 기준이다.

---

## 회차 1 — L1 설정과 데이터 (`config/`)  ← 여기가 안전 경계다

**읽을 것:** `config/solo/gateway_config.yaml` → `config/solo/motions.yaml` → `config/venues/20260922-bank/venue.yaml`

| 파일 | 누가 쓰나 | 무엇이 들었나 |
|---|---|---|
| `gateway_config.yaml` | 사람 | **`api_allowlist`**(로봇이 실행을 허용하는 전부), 정지 목표 상태(`Velocity`), ROS 토픽 이름, 타임아웃 |
| `motions.yaml` | 사람 | 동작 카탈로그(state·한글 이름·`safety`) + `rc_list`(로봇 RC 다이얼 2뱅크의 실배포 덤프) |
| `venues/<행사>/venue.yaml` | 사람 | 이 행사의 관객 패드 12칸(`pad_grid`, 순서 = 그리드 번호). 주석을 마음껏 단다 |
| `venues/<행사>/presets.json` | **서버** | `/dance` 에서 저장하는 프리셋: 동작·음원·**싱크 오프셋** |

**왜 이렇게 생겼나**
- `venue.yaml`(사람)과 `presets.json`(서버)을 가른 이유: 서버가 YAML 을 통째로 다시 쓰면 사람이 단 주석이 사라진다.
- 패드 12칸이 정책이 아니라 venue 에 있는 이유: 안전이 아니라 **연출**이라서다. 대신 정책과 교집합이라 권한은 못 넓힌다.
- `solo/` 와 `fleet/` 카탈로그가 다른 이유: 로봇의 RC 다이얼 덤프가 다르다(코드가 아니라 물리 사실).
- `20260831-opening/` 은 `archived: true` — 옛 행사의 139/79 전체 목록 보관용이고 이 venue 로는 기동하지 않는다.

**어디가 위험한가**
- `api_allowlist` 에 동작을 **넣는 것**이 곧 "로봇이 그걸 하게 허락한다"이다. 로봇에 학습·배포가 안 된 동작을 넣으면
  눌러도 거부되고, 검증 안 된 동작을 넣으면 관객 앞에서 넘어질 수 있다. 새 동작은 **수동 버튼으로 먼저 실물 검증한 뒤**
  패드에 올린다.
- 오프셋(`offset_ms`)은 **그 장소의 물리량**이다(스피커·TV·로봇 경로). 저장소의 값은 출발점일 뿐, 현장에서 재보정한다.
- 카탈로그·`rc_list`·`api_allowlist` 는 **함께** 바꾼다. 셋이 어긋나면 버튼은 뜨는데 눌러도 안 나가거나 그 반대다.

**직접 해 보기**
```bash
python3 tools/preflight.py                  # 설정 셋의 정합 점검. 이 Mac 에선 음원이 없어 FATAL 6 이 정상이다
python3 tools/preflight.py --venue 20260831-opening   # 보관된 venue 는 FATAL 1 (기동 거부)
```
`venue.yaml` 의 `pad_grid` 에 없는 동작 이름을 한 줄 넣고 preflight 를 돌려 보라 — FATAL 이 뜬다. (되돌릴 것)

---

## 회차 2 — L2 도메인 (`core/`)

세 파일을 이 순서로 읽는다: **`ports.py` → `catalog.py` → `stage.py`**.

### `core/ports.py` (81줄) — 백엔드의 계약
- `Transport` Protocol: `name` · `submit` · `stop_motion` · `status` · `stop` 다섯 개. `State` 가 백엔드에 부르는 전부다.
- `SupportsPrepare`(발사 1.5초 전 사전 준비, RC 계열) · `SupportsDuration`(완료 신호가 없는 경로의 길이 추정) ·
  `SupportsDiscovery`(라디오 재탐색, 플릿). **선택 능력**이라 `isinstance` 로 묻는다.
- **함정:** `stop()`(백엔드가 쥔 자원을 놓음)과 `stop_motion()`(**로봇을 세움**)은 이름이 비슷하지만 완전히 다른 일이다.

### `core/catalog.py` (175줄) — 무대 전에 어긋남을 잡는다
- `load_venue` 가 venue 폴더를 읽고, `validate` 가 카탈로그·정책·venue 를 대조해 `Problem`(FATAL/WARN) 목록을 준다.
- 예: 패드 버튼이 카탈로그·`api_allowlist` 에 없으면 FATAL(눌러도 거부되는 버튼), 프리셋의 동작이 허용 밖이면 FATAL,
  음원이 없으면 FATAL(mock 개발 실행은 WARN), 같은 state 가 카탈로그에 두 번 있으면 WARN.
- **같은 함수를 두 곳이 부른다**: 서버 부팅(FATAL 이면 기동 거부)과 `tools/preflight.py`. 두 벌이면 "preflight 는 통과하는데
  부팅은 실패"하는 날이 온다.
- **못 잡는 것:** 프리셋의 동작이 카탈로그에 있고 허용돼 있으면 통과한다. 그게 그 곡에 맞는 동작인지는 모른다
  (8/21 "영상은 뉴진스, 로봇은 체스트팝"). 그래서 preflight 는 끝에 **짝 확인표**를 찍고 사람이 눈으로 본다.

### `core/stage.py` (436줄) — 이 프로젝트의 심장
`Stage` 는 무대의 유일한 주인이다. 관객 패드·운영자·TV 가 서로 다른 시각에 같은 무대를 본다.

읽는 순서(이 순서로 메서드를 따라가라):
1. `__init__` — 필요한 것을 **함수로** 받는다(`catalog`, `load_presets`, `media_files`, `clip_seconds`, …). 값이 아니라 함수인
   이유: 프리셋·음원·클립은 실행 중에 바뀐다.
2. 화면 상태 `idle · preview · executing · dance` 와 수명(`STAGE_TTL`) — 패드가 죽어도 화면이 한 상태에 영원히 갇히지 않게
   읽는 시점에 만료를 계산한다.
3. `play` → `_play` — **동작 실행 규칙 전부**가 여기 있다(위의 "로봇이 움직이기까지의 길" 1단계).
4. `stop_motion` — 허용 목록을 안 거친다. dance 중이면 **예약을 먼저 무력화한 뒤** 정지한다(안 그러면 정지 1~3초 뒤에
   예약된 안무가 발사된다).
5. `start_dance` → `_fire_dance_motion` / `_prep_dance_motion` / `_auto_stop_dance` / `stop_dance` — **가장 섬세한 로직.**

**`start_dance` 를 이해하는 열쇠 두 개**
- **절대 시각 싱크:** "지금 눌렀으니 바로 재생"은 폴링 지연(±300ms)이 매번 달라 싱크가 안 맞는다. 미래의 절대 시각
  `base = now + 2초` 를 정하고, 동작은 서버 타이머가, 음원은 display 가 `server_now` 와의 시계 차이로 각자 그 시각에 맞춘다.
  오프셋의 부호: **+ 면 로봇 먼저, − 면 음원 먼저.**
- **세대 번호 `_dance_gen`:** `Timer.cancel()` 은 이미 시작된 콜백을 못 멈춘다. 그래서 콜백이 "내가 걸렸던 그 무대가 아직
  유효한가"를 세대 번호로 확인한다. 이게 없으면 A 재생 중 B 를 시작할 때 A 의 늦은 콜백이 B 의 음악에 A 의 동작을 쏜다.

**어디가 위험한가** (전부 실제로 있었던 사고에서 나온 규칙이다 — 주석에 날짜가 적혀 있다)
- `stop_dance` 는 로봇을 **절대** 건드리지 않는다(2026-08-18 사용자 확정). 바꾸면 영상이 안무보다 짧을 때 로봇이 관객 앞에서
  뚝 끊긴다.
- 무대 중 관객(`pad`) 명령은 서버가 막는다. 패드가 스스로 잠그는 건 1초 폴링 뒤에야 반영돼 그 창으로 새어 나간다.
- 게이트웨이가 준비 안 된 채 무대를 시작하면 영상만 돌고 로봇은 안 움직인다(9/20). 시작 시점에 막는다.
- 숫자 필드는 타이머를 걸기 **전에** 다 파싱한다. 반대면 "시작 실패"로 보이는데 2초 뒤 로봇만 움직인다.
- 이 파일 안의 락(`self.lock`) 순서를 건드리지 않는다. 콜백 스레드가 여럿이라 교착이 나면 무대 중에 멈춘다.

**직접 해 보기**
```bash
python3 -m unittest tests.test_stage -v         # 하드웨어 없이 무대 시나리오 전부. 0.1초
python3 -m unittest tests.test_ports -v          # 백엔드 계약
```
`tests/test_stage.py` 는 **읽기 좋은 명세서**다 — 무대 규칙이 한 줄 시나리오로 적혀 있다. 코드를 읽기 전에 이걸 먼저 읽어도 된다.

---

## 회차 3 — L3 통신 경로 (`runtime/`)

`Transport` 를 구현하는 다섯 백엔드와 보조 모듈. **`gateway.py` 를 먼저** 읽는다(나머지의 기준이다).

| 파일 | 하는 일 | 언제 쓰나 |
|---|---|---|
| `gateway.py` | **로봇 쪽 실행 정책**: `api_allowlist` · 단일 요청(이미 실행 중이면 거부) · 쿨다운 · 수명주기 · 정지(모든 검사 우회) | 로봇 안에서 |
| `robot_backend.py` | ROS 2 노드. heartbeat 발행 · 모드 상태 구독 · 요청 서비스 호출. gateway 를 ROS 에 물린다 | `app.py --robot` (로봇 컨테이너 안) |
| `relay_backend.py` | PC 서버 → 로봇의 gateway 로 HTTPS 전달. 연결 실패만 1회 재시도(거부는 재시도 안 함 — 같은 동작이 두 번 나갈 수 있다) | PC 에서 Wi-Fi 로 |
| `rc_backend.py` + `rc_serial.py` | 유선 RC 경로: PC → USB → RadioMaster → ELRS → 로봇. 로봇 소프트웨어 수정이 없다. 완료 신호가 없어 동작 길이를 **추정**한다 | Wi-Fi 가 죽었을 때, 또는 RC 로 운영 |
| `rc_fleet.py` | 꽂힌 라디오 **전부**에 동시 발사(스레드+Barrier). 1대 = 1 `RcBackend` | fleet 모드 |
| `clip_len.py` | mp4 의 `moov/mvhd` 에서 길이를 읽는다 — **클립 길이 = 동작 길이**(잠금 타이밍의 기준) | 항상 |
| `session_log.py` | JSONL 세션 로그(별도 스레드로 써서 HTTP 핸들러가 디스크를 안 기다린다) | 항상 |

**왜 이렇게 생겼나**
- 로봇은 "동작이 끝났다"를 알려 주지 않는다(RC 경로엔 완료 신호가 아예 없다). 그래서 서버가 시간을 **추정**해야 하고, 그 기준이
  sim 클립 파일의 길이다. 카탈로그에 숫자를 베껴 두면 클립을 다시 구울 때마다 어긋나서 파일 자체를 출처로 삼았다.
- `rc_serial` 은 라디오의 `K1PC.lua` 와 줄 단위 프로토콜(`PING/RUN/PREP/FIRE/VEL/…`)로 대화한다. 0.2초 간격 keepalive `PING`
  이 끊기면 라디오가 0.5초 안에 자동 해제한다(**연결이 끊기면 안전하게 풀리는** 설계).

**어디가 위험한가**
- `gateway.stop_motion` 은 정지 목표 `Velocity`(보행 대기)를 보낸다. **로봇이 Damping 일 때만** `ReadyPose` 로 보낸다
  (Damping 을 벗어나는 전이가 ReadyPose 뿐이라서). 그래서 부팅 직후엔 정지 버튼을 먼저 한 번 눌러야 한다.
- 잠금 타이밍 세 값은 **함께** 움직인다: `web/pad.html` 의 `+2000` · `core/stage.py` 의 `EXEC_IDLE_MARGIN_SEC` ·
  `runtime/rc_backend.py` 의 `BUSY_MARGIN_SEC`. 하나만 바꾸면 패드가 먼저 풀리거나 늦게 풀린다.
- RC 모드에서 **SD 스위치를 내려야** 명령이 먹는다(API 권한일 때 로봇은 텔레옵 전이를 무시한다). RC Damping/E-stop 은 항상
  최우선이고 네트워크와 무관하다 — **소프트웨어 정지에 의존하지 않는다.**
- `rc_serial` 의 TLM 대기: solo 1.5초 / fleet 0.6초(`FLEET_TLM_TIMEOUT_S`). 0.6 은 "전파 구간 미검증"이라 통일하지 않았다.

**직접 해 보기**
```bash
python3 -m unittest tests.test_gateway tests.test_relay_backend tests.test_rc_backend tests.test_rc_fleet -v
```
`tests/test_gateway.py` 가 정지 우선순위·쿨다운·단일 요청 규칙의 명세다. `tests/test_rc_serial.py` 는 가짜 pty 로 라디오를 흉내 낸다.

---

## 회차 4 — L4 진입점 (`app.py`)

`app.py` 는 765줄이지만 **얇은 배선**이다. 도메인은 `core/` 에 있다. 위에서 아래로 이 덩어리들이다:

1. **모드 표 `MODES` 와 `select_mode`** — 모드가 정하는 것: 읽을 데이터 폴더 · 화면 표 · 기본 화면·테마·포트·백엔드.
   새 모드는 표에 한 줄 + `config/<모드>/` 폴더다. (`select_mode` 는 모듈 전역을 바꾼다 — 테스트는 끝나고 solo 로 되돌린다.)
2. **`check_venue`, `_catalog`** — 부팅 검증. `_catalog` 가 `core.catalog` 를 **늦게** import 하는 이유: 로봇 컨테이너에는
   `catalog.py` 가 안 간다(UI·venue 가 없다). 최상단 import 로 바꾸면 로봇에서 `app.py` 가 안 뜬다.
3. **프리셋 파일 입출력** — `load_presets` / `save_preset`. 저장 시 `title` · `credit` · `media_len_sec` 가 빠져 있으면 기존 값을
   유지한다(오프셋 한 번 저장에 제목이 사라지면 안 된다).
4. **`MockBackend`** — 로봇 없이 UI 만 볼 때. 기록만 한다.
5. **`State(Stage)`** — 배선 클래스. `Stage` 에 이 앱의 파일·어댑터를 **함수로** 꽂고, 모드 고유 메서드(`set_rc_mode` / `rescan_rc`)만 갖는다.
   `tests/test_wiring.py` 가 "여기에 도메인이 다시 생기지 않는다"를 지킨다(그러면 두 모드가 다시 갈라진다).
6. **`Handler`** — HTTP. `do_GET`(화면·폴링 JSON·정적 파일) / `do_POST`(`/motion` `/stop` `/stage` `/dance/start` `/dance/stop`
   `/rc/mode` `/rc/rescan` `/dance/presets`). 파일 서빙(`_send_web` `_send_clip` `_send_media`)은 **경로 탈출 방지**가 핵심이다.
7. **`QuietServer`, `ensure_cert`, `main`** — 인자 파싱 · 백엔드 선택 · 서버 기동.

**인증 (반드시 이해할 것)**
- `--robot`/`--relay`/`--rc`(실제로 로봇을 움직이는 백엔드)면 토큰이 필수이고 `--https` 를 강제한다. 토큰은 URL `?token=` 으로
  한 번 주면 서버가 쿠키(`Secure; HttpOnly; SameSite=Strict`)로 바꿔 준다. 화면은 주소창에서 토큰을 지운다(`stripToken`).
- `mock` 은 토큰이 없다(로봇을 안 움직이므로).

**어디가 위험한가**
- `/motion` 의 `source` 는 클라이언트가 보낸다. 서버는 `llm` 을 항상 거부하고, `/stop` 의 source 는 **서버가 강제**한다.
  새 입력(음성·카메라 등)을 붙일 때 이 지점이 안전 경계다 — 새 source 가 `api_allowlist` 를 넘거나 정지를 부를 수 있게 하지 않는다.
- `/web/` 는 경로를 그대로 받으므로 `..` 탈출을 막는 코드(`_send_web`)를 건드리면 저장소 밖 파일이 나간다.
  `tests/test_ui_http.py` 가 공격 문자열로 지킨다.
- 부팅은 FATAL 이 하나라도 있으면 **기동을 거부한다.** 이건 기능이다 — "일단 띄우게" 우회하지 않는다.

**직접 해 보기**
```bash
python3 app.py                       # solo, mock. http://localhost:8000 → /pad
python3 app.py --mode fleet --mock   # http://localhost:19000 → /operator
python3 -m unittest tests.test_modes tests.test_venue tests.test_wiring tests.test_ui_http -v
```
브라우저로 `/operator` 를 열어 **수동 실행 버튼**과 **정지**를 눌러 보고, 터미널에 찍히는 줄(`OK`/`REJECT`/`STOP`)과 대조한다.

---

## 회차 5 — L5 화면 (`web/`)

빌드 없음. `app.py` 가 파일을 그대로 서빙한다.

| 파일 | 누가 보나 | 하는 일 |
|---|---|---|
| `pad.html` | 관객(아이패드) | 동작 12칸 선택 → **미리보기 → [실행]**. `/status`+`/conversation` 을 1초 폴링 |
| `display.html` | TV | 서버 상태만 본다(300ms 폴링): 대기 / 미리보기 / 실행중 / 무대 영상. 무대에서 `media_at` 에 맞춰 재생 |
| `operator.html` | 운영자(폰·메인컴) | **정지** · 상태 카드 · 수동 실행 · 무대 시작/정지 · (solo) RC 토글 / (fleet) 라디오 재탐색 |
| `dance.html` | 메인컴 | 음원·동작 짝과 **싱크 오프셋** 보정 → 프리셋 저장 |
| `k1.js` | 위 둘이 공유 | `fitCanvas`(고정 캔버스 스케일) · `stripToken` |
| `base.css` · `tool.css` · `themes/` | — | 아래 |

**CSS 3층 (이게 이 구조의 핵심 발상이다)**
- `base.css` — **테마가 못 건드리는 뼈대**: 캔버스 스케일 메커니즘 · 레이어 페이드 · z-index. 디자인을 잘못 넣어도 화면이 안 뜨는 일은 없다.
- `themes/<이름>/` — **관객 화면(display·pad)만** 테마를 탄다(`--theme`, solo=`shape` / fleet=`shape-gym`). 디자인 자산(색·글꼴·대기 이미지)이 여기 있다.
- `tool.css` — **운영자 화면(operator·dance)** 은 테마 밖이다. 행사마다 바뀌면 현장에서 헷갈린다.
- 색을 바꾸는 작업이 쇼를 멈추면 안 된다 — 그래서 뼈대와 옷을 가른다.

**화면은 서버 상태만 그린다.** display 는 어느 기기가 조작하든 `/conversation` 하나만 본다(`stage`, `stage_data`, `server_now`).
그래서 새 화면(방송용 오버레이 등)은 이 피드만 읽으면 된다 — 코어를 안 고친다.

**어디가 위험한가**
- `operator.html` 의 **정지 버튼**은 실행 중에도 잠기면 안 된다. 수동 버튼과 달리 항상 눌려야 한다.
- 화면 JS 는 `/motions` 의 `dance_motions`(무대 동작 목록)와 `pad_allowed`(패드 순서 = 그리드 번호, **정렬 금지**)를 서버에서 받는다.
  화면에 목록을 박아 두면 행사가 바뀔 때 어긋난다(옛 `dance.html` 에 3종이 박혀 있었고 앱마다 달랐다).

**직접 해 보기**
```bash
python3 app.py     # 그리고 브라우저 창 셋: /pad · /display · /operator
```
`/pad` 에서 버튼 → 미리보기 → 실행을 하며 `/display` 의 상태가 따라 바뀌는 것을 본다. `/operator` 에서 **무대 시작**(프리셋이 있으면)을
눌러 `/display` 의 무대 화면을 본다. 개발자 도구 Network 탭에서 폴링을 확인한다.

---

## 회차 6 — L6 테스트와 도구 (`tests/`, `tools/`)

**테스트를 믿는 법:** 초록 = 안전이 아니다. 이 저장소는 "아무것도 검증하지 않고 통과하는 테스트"를 실제로 겪었다(false pass).
그래서 중요한 규칙마다 **변이 테스트**를 한다 — 프로덕션 코드를 일부러 망가뜨리고 테스트가 **실패하는지** 본다. 안 실패하면 그 테스트는
그 규칙을 지키지 않는 것이다. 새 규칙을 추가하면 같은 방식으로 확인한다.

| 그룹 | 파일 |
|---|---|
| 도메인 (하드웨어 없음, 빠름) | `test_stage` · `test_catalog` · `test_ports` · `test_wiring` |
| 모드 | `test_modes`(두 모드가 갈리는 곳과 **안 갈려야 하는 곳**: 안전 코어) |
| 통신 경로 | `test_gateway` · `test_relay_backend` · `test_rc_backend` · `test_rc_serial`(가짜 pty) · `test_rc_fleet` · `test_motion_duration` · `test_clip_len` |
| 서버 | `test_ui_http`(경로 탈출 공격 포함) · `test_dance` · `test_venue`(부팅) · `test_server_tools`(**로봇 배포 목록 검사**) · `test_session_log` |
| 로봇 RC 설정 | `test_robot_rc_config` |

- `test_server_tools.DeployListTest` — **로봇 배포 목록**(`run.sh` 의 `DEPLOY_FILES`)이 `app.py` 의 import 를 전이적으로 다 덮는지 본다.
  이 목록에서 파일이 하나 빠지면 로봇에서 gateway 가 안 뜬다(2026-08-13 실제로 겪음, 무대 전에 잡으려는 테스트).
- 이 Mac 에서 못 하는 것: GNU tar 로 `run.sh --deploy` 의 md5 대조 · 실제 로봇 · 실제 라디오 · 실기 리허설 → **Linux PC 에서 사람이**.

**도구 (`tools/`)**
| 파일 | 용도 |
|---|---|
| `preflight.py` | **출발 전 점검.** 서버 부팅과 같은 검증 + 프리셋 짝 확인표 |
| `check_modes.sh` | 로봇에 실제 로드된 모드와 카탈로그를 대조(새 정책을 로봇에 넣은 뒤 먼저 돌린다) |
| `verify_robot_rc_config.py` | 로봇 `k1_config` 백업과 `rc_list` 의 정합 (읽기 전용) |
| `rehearsal.py` · `edge_probe.py` | 실행 중인 서버에 HTTP 로 때려 보는 리허설/엣지 케이스 |
| `api_arm_probe.py` · `link_test.sh` · `wifi_watch.sh` · `set_ap_channel.sh` | 로봇·링크 진단 |
| `render_motion.py` | 동작 sim 클립(mp4) 렌더 → `clips/` |
| `start_fleet.sh` | fleet 모드 서버를 세션과 무관하게 기동(tmux) |

**직접 해 보기**
```bash
python3 -m unittest discover -s tests -t .           # 전부 (약 10초)
```
변이 테스트를 한 번 해 본다: `core/stage.py` 의 `_fire_dance_motion` 에서 `gen != self._dance_gen or` 를 지우고 `tests.test_dance` 를 돌려
본다 — 실패해야 한다. **끝나면 되돌린다**(`git checkout core/stage.py`).

---

## 위험한 곳 한눈에

| 곳 | 규칙 | 어기면 |
|---|---|---|
| `config/*/gateway_config.yaml` `api_allowlist` | 수동 실물 검증 뒤에만 추가 | 미검증 동작이 관객 앞에서 실행 |
| `core/stage.py` `stop_dance` | 로봇을 건드리지 않는다 | 로봇이 관객 앞에서 뚝 끊김 |
| `core/stage.py` `stop_motion` | 예약(dance)을 **먼저** 무력화 | 정지 1~3초 뒤 안무 발사 |
| `core/stage.py` `_dance_gen` | 콜백은 세대 번호로 유효성 확인 | B 음악에 A 동작 |
| `core/stage.py` `start_dance` | 숫자 파싱은 타이머 전에 | "실패"로 보이는데 로봇만 움직임 |
| 잠금 타이밍 3값 | pad `+2000` · `EXEC_IDLE_MARGIN_SEC` · `BUSY_MARGIN_SEC` 함께 | 패드가 일찍/늦게 풀림 |
| `runtime/gateway.py` `stop_motion` | 모든 검사 우회 | 정지가 거부됨 |
| `app.py` `/web/` `_send_web` | `..` 탈출 방지 | 저장소 밖 파일 노출 |
| `app.py` 인증 | 로봇을 움직이는 백엔드는 토큰+HTTPS | 누구나 `/motion` 을 쏨 |
| `run.sh` `DEPLOY_FILES` | `app.py` import 를 전이적으로 다 포함 | 로봇에서 gateway 가 안 뜸 |
| `app.py` `_catalog()` 늦은 import | 최상단으로 올리지 않는다 | 로봇에서 `app.py` 가 안 뜸 |
| `venue.yaml` `pad_grid` | 순서 = 그리드 번호 | 버튼 배치가 뒤섞임 |
| `presets.json` 오프셋 | 현장 재보정 필수 | 음악과 동작이 어긋남 |
| RC 경로 | SD 내려야 명령이 먹음 / RC E-stop 이 항상 최우선 | 명령이 무시됨 / 소프트웨어 정지에만 의존 |

## 용어집

| 용어 | 뜻 |
|---|---|
| **state / 동작** | 로봇이 아는 모드 이름(`MimicWaveHand` 등). 카탈로그의 키 |
| **Mimic** | 모션캡처를 따라 하는 학습된 동작 정책 |
| **Velocity / ReadyPose / Damping** | 로봇의 제어 상태. Velocity=보행 대기(정지의 목표), ReadyPose=준비 자세(균형 정책 없음), Damping=힘 뺌 |
| **API authority / SD** | 로봇이 API 명령을 받는 권한 / 그 물리 허가 스위치(RC 의 SD, CH8) |
| **gateway** | 로봇 안의 실행 정책기(`runtime/gateway.py`). 서버가 뚫려도 마지막에 막는다 |
| **relay** | PC 서버가 로봇의 gateway 로 HTTPS 를 전달하는 경로 |
| **RC / ELRS / Pocket** | 유선 리모컨 경로(RadioMaster Pocket 라디오 → ELRS 전파). Wi-Fi 가 죽었을 때의 차선 |
| **solo / fleet** | 앱의 두 모드. 로봇 1대 / 라디오 여러 대 동시 |
| **venue** | 한 행사의 설정 폴더(패드 12칸 · 프리셋 · 오프셋) |
| **pad / display / operator / dance** | 화면 넷: 관객 아이패드 / TV / 운영자 / 싱크 보정 |
| **stage(무대 상태)** | `idle · preview · executing · dance` — display 가 그리는 상태 |
| **dance / 프리셋** | 음원과 로봇 동작을 짝지은 무대. `offset_ms` 로 싱크를 맞춘다(+ 로봇 먼저 / − 음원 먼저) |
| **PREP / FIRE** | RC 의 발사 지터를 줄이는 사전 준비(코드 0 유지) / 발사 엣지 |
| **preflight** | 출발 전 설정 정합 점검 |
| **FATAL / WARN** | 검증 결과. FATAL 이 있으면 서버가 기동을 거부한다 |
| **변이 테스트** | 코드를 일부러 망가뜨려 테스트가 실패하는지 보는 것. 테스트를 믿는 방법 |
| **oracle(정답지)** | `origin/main` 을 분리 워크트리로 띄워 같은 요청을 보내 응답을 비교하는 검증 방식 |

## 다음에 읽을 것

- 구조가 왜 이렇게 됐는지(1~7단계 기록, 측정 수치): [`docs/RESTRUCTURE.md`](RESTRUCTURE.md)
- 무엇을 확장하려면(새 통신 경로 · 시연 방식 · 입력 · 화면): Phase 3 산출물 `docs/EXTENDING.md` (아직 없음)
- 행사 당일 절차: [`docs/solo/RUNBOOK.md`](solo/RUNBOOK.md) · 현재 상태: [`docs/solo/STATUS.md`](solo/STATUS.md)
- fleet(군무): [`docs/fleet/README.md`](fleet/README.md) · [`docs/fleet/RUNBOOK.md`](fleet/RUNBOOK.md)
