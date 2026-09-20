# k1-stage 구조 정리 계획

`restructure` 브랜치의 작업 계획이다. `main` 은 무대에 나가는 것이고 여기는 개발본이다.

목표는 두 가지다 — **다음 사람(6개월 뒤의 나 포함)이 이어받을 수 있게** 만드는 것과,
**행사마다 바뀌는 것을 코드에서 떼어내는** 것.

---

## 0. 왜 지금 이 모양인가

구조를 이해하려면 어떻게 여기 도달했는지를 봐야 한다.

```
8/05~8/17  음성 대화(OpenAI Realtime)가 주 경로     ← 앱 이름이 motion_llm 이었던 이유
8/17       RC 경로 병합 — 같은 앱에 --rc 추가
8/18       음성 제거. 버튼+무대로 전환. 최종 리뷰 12건 수정
8/20       rc_stage 를 motion_llm 복사해서 신설 (군무용)
8/21       k1-stage 저장소 신설, 셋을 합침
8/21~8/31  현장 수정이 한쪽에만 들어감 → 드리프트 3건
9/20       폴더명 정리 (solo_stage / group_stage)
```

**이건 실패가 아니라 정상적인 진화다.** 데드라인이 있는 프로젝트에서 "복사해서 분기"는
가장 빠르고 안전한 수단이다. 문제는 복사한 뒤에 **동기화 비용을 지불할 장치를 안 만든 것**.

> DRY 의 진짜 의미는 "복사하지 마라"가 아니라 **"복사하면 동기화 비용을 지불해라"**다.
> 지불 방법은 셋뿐이다 — 테스트로 감시하거나, 런타임에 하나로 합치거나, 빌드로 생성하거나.

---

## 1. 확정된 결정 (뒤집지 말 것)

| # | 결정 | 근거 |
|---|---|---|
| 1 | **빌드 스텝 없음** (webpack/Vite/npm 금지) | 현장에서 `python3 server.py` 하나로 뜨는 게 이 시스템 최대 자산. 행사장에서 `npm install` 이 실패하면 쇼가 멈춘다. 공유는 ES modules + CSS 커스텀 프로퍼티로만 |
| 2 | **고정 캔버스 + contain scale 유지** | TV 16:9 = 1440×810 정확히 일치. 아이패드 1024×768 유지. `Math.min(innerW/W, innerH/H)` 로 이미 기기 크기에 맞춰진다. 반응형 재작성은 Figma 좌표를 그대로 쓰는 이득을 없앤다 |
| 3 | **테마는 관객용 2장에만** (display, pad) | operator/dance 는 운영자 도구. 행사마다 바뀌면 현장에서 헷갈린다. 둘의 중복 다크 CSS 는 `web/tool.css` 로 합치되 테마 대상 아님 |
| 4 | **`web/` 은 저장소 루트에 두고 두 앱이 공유** | 지금 화면이 복제돼 있고 실제로 드리프트 3건 발생 |
| 5 | **`core/` 는 `adapters/` 를 import 하지 않는다** | 의존은 항상 안쪽으로. 하드웨어 없이 테스트 가능해야 함 |
| 6 | **로봇 배포 경로 `/root/motion_llm/` 는 그대로** | PC 폴더명만 바꿨다. 로봇에서 먼저 `mv` 하지 않고 `ROBOT_DIR` 만 고치면 빈 디렉터리에 배포되고 gateway 는 옛 코드를 계속 돈다 |

---

## 2. 목표 구조

```
k1-stage/
├── core/                      도메인. adapters 를 import 하지 않는다
│   ├── stage.py                 무대 상태기계 · 스케줄 (server.py 의 State, ~400줄)
│   ├── catalog.py               motions/policy/venue 로딩 + 정합 검증
│   └── gateway.py               (이동만. 이미 순수 정책 코어다)
│
├── ports.py                   Protocol 3~4개. ~40줄
│
├── adapters/                  I/O. 얇게. 로직 없음
│   ├── mock.py  relay.py  robot.py
│   ├── rc.py  rc_fleet.py
│   └── serial_link.py
│
├── web/                       프론트 단일 정본
│   ├── base.css                 구조. 테마가 바꾸면 안 되는 것
│   ├── tool.css                 operator + dance 다크 UI (고정)
│   ├── k1.js                    폴링 · 시계 보정 · 레이어 전환
│   ├── display.html  pad.html  operator.html  dance.html
│   └── themes/
│       ├── shape/  tokens.css  display.css  pad.css  idle.jpg
│       └── shape-gym/  idle.png
│
├── config/
│   ├── motions.yaml             카탈로그 (거의 안 바뀜)
│   ├── policy.yaml              안전 정책 (거의 안 바뀜)
│   └── venues/
│       ├── 20260831-opening.yaml
│       └── assets/
│
├── app.py                     배선 + CLI. --mode solo|fleet
├── tools/                     preflight.py · postmortem.py · 기존 것들
└── tests/
```

**변경 이유가 다른 것을 같은 곳에 두지 않는다** (Parnas, 1972). 지금 문제는 이렇다:

| 무엇 | 왜 바뀌나 | 빈도 | 지금 어디 |
|---|---|---|---|
| 안전 정책 (stop_state, 권한) | 사고가 나거나 로봇이 바뀔 때 | 거의 없음 | `gateway_config.yaml` |
| stage 상태기계 | 쇼 연출이 바뀔 때 | 드물게 | `server.py` |
| 통신 어댑터 | 새 경로가 생길 때 | 드물게 | `*_backend.py` |
| **오프셋·패드 목록·음원** | **행사마다** | **매번** | `dance_presets.json` + `gateway_config.yaml` |
| **디자인** | 보기 싫을 때 | **아무때나** | `static/*.html` 인라인 |

오프셋(매 행사)이 안전 정책(거의 안 바뀜)과 같은 파일에 있고, 디자인(아무때나)이 무대
상태기계와 같은 파일에 있다. **자주 만지는 것과 절대 틀리면 안 되는 것이 같은 파일에
있으면 언젠가 손이 미끄러진다.**

---

## 3. 단계별 계획

**각 단계는 독립적으로 배포 가능해야 하고, 멈춰도 그 전보다 나은 상태여야 한다.**
"절반 한 상태가 최악"인 리팩터는 잘못 쪼갠 것이다.

### ✅ 1단계 — 대기 이미지 base64 탈출 + `/theme/` 라우트 (커밋 `30971b3`, 완료)

`display.html` 194KB 중 177KB 가 base64 JPEG 한 줄이었고, **그게 두 앱의 display.html 이
갈라진 원인**이었다 (8/31 새 이미지가 group 에만 들어감).

- `web/themes/shape/idle.jpg` (solo 현재) · `web/themes/shape-gym/idle.png` (8/31, 16:9)
- 페이지는 `/theme/idle` 로 요청 → 서버가 활성 테마에서 `idle.*` 를 찾아 서빙
  (확장자가 테마마다 달라 페이지가 알 수 없다. 덕분에 테마를 바꿔도 HTML 을 안 고친다)
- `--theme` CLI. 기본 solo=`shape` / group=`shape-gym` → **지금 화면과 픽셀 단위로 동일**
- 결과: display.html 각각 14.7KB. 읽을 수 있고 diff 할 수 있다

### ✅ 2단계 — CSS 3층 분리 + 화면을 `web/` 로 (완료)

```
web/base.css                구조만
web/tool.css                operator + dance 공통 (테마 아님)
web/themes/shape/*.css      관객용 디자인 언어
```

**base vs theme 경계:**

| base.css (테마가 못 건드림) | theme (자유) |
|---|---|
| `*{box-sizing}` reset | `:root` 토큰 전부 |
| 캔버스 스케일 **메커니즘** (`position/transform/transform-origin`) | 캔버스 **치수** (`--canvas-w/h`) |
| 레이어 교차 페이드 (`.canvas,.full{opacity/pointer-events/transition}`) | 색·폰트·여백·타이포 |
| `#layer-unlock` 의 `z-index`·`display` | 캔버스 안의 모든 위치·크기 |
| `footer` 의 `position`·`z-index` | 대기화면 이미지 크기·배경 |

이유: **테마가 `z-index` 나 `position` 을 건드릴 수 있으면 디자인 하나 잘못 넣었을 때
무대에서 화면이 안 뜬다.** 색 바꾸는 작업이 쇼를 멈추면 안 된다.

**함정:**
- `pad.html` 은 캔버스 선택자가 `#cv`, `display.html` 은 `.canvas`. base 에서 둘 다
  커버하되 **레이어 페이드(`opacity:0`)는 `.canvas`/`.full` 에만.** `#cv` 에 걸면
  패드 화면이 통째로 안 보인다
- `display.html` 은 이미 **하이브리드**다. 레이아웃 프레임은 고정 캔버스지만
  `#idleImg`(94vw/96vh) · `#clipVideo`(100vw/100vh) · `#clipName`(2.2vw) 은 vw/vh 반응형.
  의도된 분업이니 유지한다
- 두 화면의 토큰이 통일돼 있지 않다: display `--violet:#7667ff` vs pad `#8b5cf6`,
  같은 개념을 display 는 `--ink`, pad 는 `--fg`. **이번 이동에서 통일하지 말 것**
  (픽셀이 바뀐다). 새 디자인을 만들 때가 통일할 때다
- 캔버스 치수가 CSS 와 JS 두 곳에 하드코딩 (`pad.html:120`). CSS 변수로 모으고 JS 가
  읽게 하면 새 디자인이 다른 비율로 와도 한 곳만 고친다

**리스크**: 중. **검증**: mock 서버 띄우고 브라우저로 4장 육안. 자동 테스트는 CSS 를
커버하지 않는다. **원칙: 이동과 디자인 변경을 절대 같이 하지 않는다. 픽셀 변화 0.**

**한 것:**

- `web/base.css` · `web/tool.css` · `web/themes/shape/{tokens,display,pad}.css`
- `shape-gym` 은 `shape` 를 `@import` 하고 대기화면 두 줄만 덮는다. 시각을 통째로
  복사하면 또 갈린다 — 이 브랜치가 고치려는 바로 그 병이다
- 캔버스 치수를 `--canvas-w/h` 로 모으고 `fit()` 이 그 값을 읽는다
- **`display.html` · `pad.html` 을 `web/` 로 올렸다.** 공통 JS 세 조각(`$` · `fitCanvas`
  · `stripToken`)은 `web/k1.js` 로 뺐다. `server.py` 의 `SHARED_PAGES` 가 어느 화면이
  공유본인지 한 곳에서 말한다
- 글꼴도 테마 소유로 내렸다. Inter `<link>` 가 페이지 HTML 에 박혀 있어 테마를 바꿔도
  안 따라오던 구멍이었다

**검증**: 헤드리스 크롬 before/after 스크린샷이 네 장 전부 바이트 동일. 선택자별 최종
선언을 `var()` 까지 풀어 대조해 값이 바뀐 선언 0건. 콘솔 오류 없음(모듈 전환 확인).

**폴링을 `k1.js` 에 안 올린 이유**: display 는 `/conversation` 을 300ms 로, pad 는
`/status` 와 `/conversation` 을 1초로 본다. 주기도 대상도 실패 처리도 달라서 합치면
둘 중 하나에 안 맞는 추상이 생긴다. 같아지면 그때 올린다.

**`operator.html` · `dance.html` 이 아직 `*/static/` 에 남은 이유**: 합치려면 둘 중
하나를 골라야 하는데 그게 곧 드리프트 처리다.

- `dance.html` 의 유일한 차이가 **드리프트 1번 그 자체**다(프리셋 유실 수정, group 에만).
  solo 것을 고르면 수정이 사라지고 group 것을 고르면 포팅이 된다. 둘 다 이 브랜치에서
  할 일이 아니다 — §4 대로 `main` 에서 한다
- `operator.html` 은 RC 토글 대 플릿 재탐색으로 진짜 갈린다. 7단계(`app.py --mode`) 몫이다

둘이 정리되면 `SHARED_PAGES` 에 넣고 `static/` 을 지우면 된다.

### 3단계 — 테스트 초록화

지금 fresh clone 에서 **solo 7건 / group 7건 실패**한다. `media/` 와 `static/clips/` 가
gitignore 라 없어서다. 더 나쁜 건 같은 이유로 **거짓 통과가 4건** 있다는 것.

```python
# 통과하지만 아무것도 검증하지 않는 테스트
self.state.start_dance("snucheer-api")   # → {'ok': False, '음원 파일이 없습니다'}
self.state.stop_dance()
self.assertIsNone(self.state._dance_timer)   # True (애초에 없었음)
```

> **빨간 스위트는 테스트가 없는 것보다 나쁘다.** 7건이 원래 실패한다는 걸 알면 8건이
> 돼도 아무도 모른다. 실패는 눈에 띄지만 **거짓 통과는 안 보인다.**

**원칙: 테스트는 자기가 쓸 데이터를 스스로 만든다.** 프로덕션 데이터에 의존하면
(a) 데이터가 바뀌면 테스트가 깨지고 (b) 없는 환경에선 못 돌고 (c) 읽어도 뭘 검사하는지
모른다. 실제로 `# offset -1500ms (2026-08-18 실측 고정)` 주석이 그 증거다 — 실측값을
바꾸면 테스트가 깨지니까 "고정"이라고 못박은 것.

할 일:
- `DanceFixture` 믹스인으로 `server.MEDIA` · `server.PRESETS` 를 임시 경로로 교체
- 픽스처 프리셋 (`fx-media-first` 등) 을 테스트 안에 정의 — 값이 보여서 읽으면 이해된다
- 각 테스트에 `assertTrue(out["ok"])` 추가 → 거짓 통과 영구 차단
- 클립은 코드로 생성 (저장소에 바이너리 불필요):
  ```python
  def fake_mp4(seconds, timescale=1000):
      """clip_len 이 읽을 수 있는 최소 mp4 (ftyp + moov/mvhd). 100바이트."""
  ```
  `clip_len.py` 는 `moov/mvhd` 의 timescale·duration 만 읽는다

**리스크**: 낮음. **얻는 것**: 4~6단계의 안전망. **이게 없으면 그다음을 검증할 수 없다.**

### 4단계 — `config/` 분리 + 부팅 검증 + preflight

지금 오프셋은 "현장에서 재보정해야 하는 값"인데 **재보정 결과가 쌓일 자리가 없다.**
매 행사가 직전 값을 덮어쓴다. 커밋 `5eb5783` 에 증거가 있다 — *"배드 api 오프셋
+1200**(기억 기반, 재보정 필요)**"*. 기억 기반.

오프셋은 코드가 아니라 **그 장소의 물리량**이다:
```
offset = (음향 경로 지연) + (영상 디코딩 지연) − (로봇 명령 왕복)
         └ 스피커·믹서마다   └ TV마다            └ Wi-Fi vs RC
```

```
config/motions.yaml          불변 카탈로그 — 무엇이 존재하는가
config/policy.yaml           안전 정책 — 누가 무엇을 부를 수 있는가
config/venues/<행사>.yaml     이번 행사 — 오프셋·패드 12개·음원·테마
```

venue 파일 예:
```yaml
name: 2026 로보틱스 페스티벌
date: 2026-09-22
mode: solo
theme: shape
notes: 스피커가 무대 뒤라 음원이 늦게 들림
pad_grid: [MimicBowNavel, MimicWaveHand, ...]   # 순서 = 그리드 번호
presets:
  snucheer:
    motion: MimicNewSnuCheerHeadShort
    media: 응원단 fade_out.mp4
    media_len_sec: 84.5
    offset_ms: { api: -1500, rc: -1500 }        # 이 장소의 실측값
```

**주의**: `pad_allowlist` 12개는 `policy.yaml` 이 아니라 **venue 로 간다.** 그건 안전
정책이 아니라 이번 행사의 연출이다. 안전 정책은 "무엇이 실행 가능한가"(`api_allowlist`)까지.

**핵심은 검증 함수 하나:**
```python
def validate(catalog, policy, venue, clips_dir, media_dir) -> list[Problem]
```

| 검사 | 등급 | 없애는 사고 |
|---|---|---|
| 프리셋 `motion` 이 카탈로그에 있나 | FATAL | **"영상은 뉴진스, 로봇은 체스트팝"** |
| 프리셋 `motion` 이 `api_allowlist` 에 있나 | FATAL | 무대 시작 후 조용한 거부 |
| 프리셋 `media` 파일이 있나 | FATAL | 무대 시작 시 실패 |
| `pad_grid` 항목이 카탈로그·allowlist 에 있나 | FATAL | 눌러도 거부되는 버튼 |
| `pad_grid` 항목의 sim 클립이 있나 | WARN | 미리보기 안 뜸 |
| `media_len_sec` 이 있나 | WARN | 자동종료가 기본 60초로 |
| rc 슬롯 중복 | WARN | RC 에서 엉뚱한 동작 |

**같은 함수를 두 곳에서 부른다** — `app.py` 부팅(FATAL 이면 기동 거부) 과
`tools/preflight.py`(출발 전 전수 검사). 두 벌이면 preflight 는 통과하는데 부팅은
실패하는 상황이 생긴다.

> 이게 **fail fast** 다. 잘못된 상태를 가능한 한 빨리, 시끄럽게 드러낸다.
> 무대에서 발견하던 걸 노트북에서 발견하게 된다.

**리스크**: 중. **투자 대비 효과가 이 목록에서 가장 크다.**

### 5단계 — `ports.py` + `adapters/` 이동

```python
class Transport(Protocol):
    name: str
    def submit(self, motion: str, source: str, reason: str) -> MotionResult: ...
    def stop_motion(self, source: str, reason: str = "") -> MotionResult: ...
    def status(self) -> dict: ...
    def close(self) -> None: ...

@runtime_checkable
class SupportsPrepare(Protocol):     # 무대 발사 지터 감소 (RC 계열)
    def prepare(self, motion: str) -> bool: ...

@runtime_checkable
class SupportsDuration(Protocol):    # 로봇이 완료를 안 알려주는 경로
    def motion_duration(self, motion: str) -> float | None: ...

@runtime_checkable
class SupportsDiscovery(Protocol):   # 물리 장치 탐색 (RC · fleet)
    def connect_check(self) -> tuple[bool, str]: ...
    def rescan(self) -> dict[str, bool]: ...
```

`hasattr` → `isinstance(backend, SupportsPrepare)`. **의도가 이름으로 드러난다.**

**ABC 가 아니라 Protocol 인 이유**: ABC 는 상속을 강요한다. 지금 5개 백엔드가 각자 다른
파일에 상속 관계 없이 있는데 억지로 공통 조상을 만들면 **없던 결합이 생긴다.** Protocol 은
"모양만 맞으면 된다"라서 기존 코드를 안 건드린다. 이미 하고 있는 덕 타이핑을 문서화할 뿐.

**여기서 `api_allowlist` 지뢰를 없앤다.** 지금 `rc_backend.py:104` 의 주석:
```python
# 주의: api_allowlist **속성**은 일부러 두지 않는다 — 두면 State 가 패드·LLM
# 목록을 여기에 교집합해 버린다.
```
`RcBackend` 는 **속성이 없어야만 올바르다.** 누가 일관성을 위해 추가하면 관객 패드가
조용히 0개가 된다. 두 가지가 섞여 있어서다:

| 섞인 것 | 지금 | 바뀐 뒤 |
|---|---|---|
| 무엇을 실행할 수 있나 | `backend.api_allowlist` 속성 유무 | Transport 가 실행 시점에 거부 |
| 어떤 버튼을 보여주나 | 같은 속성에서 파생 | **`policy` + `venue` 에서만** |

UI 목록이 transport 에 전혀 의존하지 않게 만들면 지뢰가 사라진다. RC 의 "다이얼에 없는
동작" 거부는 `submit()` 이 하면 된다 — 주석이 원하던 바로 그 동작이다.

**리스크**: 낮음 (런타임 동작 100% 동일해야 함).

### 6단계 — `core/stage.py` 추출

`server.py` 의 `State` 클래스를 들어낸다. **로직은 안 바꾼다.** 옮기고 의존성만 끊는다.

지금 의존 방향이 깨진 곳이 하나 있다 — `State.set_rc_mode()` 가 `RcBackend` 를 직접
생성한다 (도메인이 어댑터를 앎). 주입으로 바꾼다:

```python
class Stage:
    def __init__(self, catalog, policy, venue, transports, primary):
        #   transports = {"relay": factory, "rc": factory, ...}

    def switch_transport(self, name: str | None):
        """name=None 이면 primary 복귀. solo 의 Wi-Fi↔RC 토글과
        fleet 의 단일 경로가 같은 코드로 처리된다."""
```

**리스크**: 중. **얻는 것**: 도메인 테스트가 HTTP·파일시스템 없이 밀리초로 돈다.
느린 테스트는 안 돌리게 되므로, 빨라지면 더 많이 쓰게 된다.

### 7단계 — `app.py --mode` 로 두 앱 통합

이 시점엔 차이가 배선 20줄이다.

```python
MODES = {
    "solo":  dict(pages=["pad","display","operator","dance"], default="/pad",
                  transports={"relay": mk_relay, "robot": mk_robot, "rc": mk_rc}),
    "fleet": dict(pages=["display","operator","dance"], default="/operator",
                  transports={"rc_fleet": mk_fleet}),
}
```

근거 셋:
1. `server.py` 차이가 4가지뿐 — 백엔드 배선, 라우트(`/pad` 유무), `/rc/mode` vs
   `/rc/rescan`, CLI
2. **런타임에 상호 배타적** — solo 를 RC 모드로 토글하면 group 과 같은 USB tty 를 놓고
   다툰다. 두 프로세스가 같은 포트에 쓰면 명령이 섞인다
3. 공유 파일 16개 + 드리프트 3건 — 분리의 비용은 이미 지불했고 이득은 못 받고 있다

**리스크**: 중. 큰 리팩터는 "한 번에 하는 것"이 아니라 **"여러 작은 안전한 변경의
결과로 저절로 가능해지는 것"**이다. 1~6 이 끝나면 남는 게 배선뿐이다.

---

## 4. 알려진 문제 (이 브랜치에서 고치지 않는 것)

### 드리프트 3건 — `group_stage` 에만 있고 `solo_stage` 에 없음

**`solo_stage` 가 무대에서 쓰는 앱인데 더 오래된 상태다.** 이 포팅은 **별도 세션에서
`main` 브랜치에** 한다.

| # | 내용 | 들어간 커밋 |
|---|---|---|
| 1 | **무대 프리셋 유실 버그** — 프리셋 동작이 드롭다운에 없으면 이전 선택이 남아 "영상은 A, 로봇은 B" 가 나간다. 2026-08-21 실제 사고 | `dde74b7` |
| 2 | `rc_serial.py` TLM 타임아웃 1.5s → 0.6s | `dde74b7` |
| 3 | `display.html` 대기화면 스타일 (#fafafa/94vw → #fff/72vw) | `4b3c6d3` |

3번은 2단계에서 테마별로 자연히 갈린다.

### 문서와 코드 불일치

`run.sh` 의 `DEPLOY_FILES` 는 **10개**인데 `docs/PROJECT_STRUCTURE.md`·`STATUS.md` 는
**6개**라고 적고 있다. 문서를 따라 6개만 동기화하면 로봇 gateway 가 import 에러로 안 뜬다.
`STATUS.md` 는 *"이 경로에서 실제로 두 번 사고가 났다"* 고 적고 있고, 코드에는 이미
`test_deploy_list_covers_imports` 가 있다 — **코드는 지켜지는데 문서가 썩었다.**

> 검증되지 않는 문서는 반드시 썩는다. 해법은 "문서를 잘 관리하자"가 아니라
> **문서가 코드에서 생성되거나, 코드가 문서를 검증하게** 만드는 것.

### 백엔드에서 찾은 것 (무대 후 처리)

- **RC 정지가 시리얼 락 뒤에 줄 선다 — 최악 6초.** `submit()` 이 `_lock` 을 쥔 채
  최대 3초 블로킹 I/O 를 하고, `stop_motion()` 이 같은 락을 기다린 뒤 자기 3초를 쓴다.
  전형적인 **우선순위 역전**. 정석 해법은 시리얼 소유자 스레드 1개 + 우선순위 큐.
  치명적이진 않다 — 즉시 탈출은 물리 E-stop 이 담당하고 문서도 그렇게 말한다.
  다만 운영자 체감이 나쁘다 (낙관적 UI 로 완화 가능)
- **`_find_port()` 가 `matches[0]` 을 집는다.** 라디오들이 USB 시리얼을 전부
  `00000000001B` 로 똑같이 보고해서 by-id 에 1개만 뜬다. 4대 꽂고 solo 를 RC 로 켜면
  어느 대에 나가는지 알 수 없다. `rc_fleet.py` 는 이걸 알고 by-path 로 우회했는데
  solo 는 그대로
- **`executing` 단계에만 타임아웃이 없다.** 로봇이 완료를 보고하지 않으면 `_current` 가
  영구히 남는다. 복구 경로는 있다 (빨간 정지가 busy 를 우회). 버그라기보단 설계인데
  문서에 없다
- **API 와 RC 의 완료 판정 모델이 다르다** — API 는 이벤트(로봇이 `active_mode` 보고),
  RC 는 시간 추정(클립 길이 + 2초). RC 는 로봇이 실제로 뭘 하는지 **전혀 모른다**.
  물리적 한계지만 "RC 무대에서는 로봇 상태에 대한 모든 판단이 추정"이라는 게 운영
  문서에 크게 적혀 있어야 한다

---

## 5. 안 하기로 한 것

리팩터는 **멈출 지점을 미리 안 정하면 계속 번진다.**

- ❌ 빌드 스텝 (webpack/Vite) — 현장 단순성이 최대 자산
- ❌ 프레임워크 교체 (FastAPI/React) — 검증된 코드를 버리는 것
- ❌ 의존성 주입 컨테이너 — 생성자 인자로 충분
- ❌ 이벤트 소싱 / CQRS — 그런 힘이 없다
- ❌ 도커라이즈 — 노트북 한 대에서 도는 앱
- ❌ CI 파이프라인 — 혼자 쓰면 `python3 -m unittest` 가 빠르다 (여럿이 되면 그때)
- ❌ 타입 힌트 전면 적용 — 포트 경계에만. 내부까지는 과함
- ❌ 계약 테스트 — 어댑터가 더 늘어날 때
- ❌ `core/` 를 5개 모듈로 쪼개기 — 도메인 로직이 400줄인데 5분할은 과함
- ❌ `tests/` 를 3개 디렉터리로 — 이 규모엔 평평한 게 낫다

---

## 6. 판단 기준 (나중에 스스로 결정할 때)

목록을 외우는 것보다 기준을 갖는 게 낫다.

1. **사고가 난 곳만 구조화한다.** "좋은 구조니까"가 아니라 "여기서 피를 봤으니까"
2. **한 파일이 머리에 안 들어오면 쪼갠다. 그 전엔 안 쪼갠다.** 임계 ~400줄.
   줄 수가 아니라 "몇 가지 이유로 바뀌나"가 진짜 기준이지만 줄 수가 좋은 대리 지표다
3. **되돌리기 비싼 결정만 미리 정한다.** venue 설정 포맷·로봇 배포 경로·`web/` 경로는
   지금. `core/` 내부 분할·Protocol 메서드 이름은 나중에.
   *"나중에 필요할 것 같아서"는 근거가 아니다. "나중에 하면 비싸져서"는 근거다*
4. **추상화는 두 번째 구현에서. 단, 둘 다 프로덕션일 때만.**
   Rule of Three 는 둘 다 운영에 나가는 경우엔 안 맞는다 — 드리프트가 곧 사고다
5. **구조는 "기억해야 하는 것"을 "틀릴 수 없는 것"으로 바꿀 때만 값을 한다.**
   주석이 시스템을 지탱하고 있으면 그걸 타입·테스트·검증으로 옮긴다.
   효과가 없는 재배치는 그냥 파일 옮기기다

---

## 7. 릴리스 규칙 (무대 시스템이라 중요)

행사마다 태그를 박는다. **되돌릴 수 있다는 확신이 있어야 과감하게 고칠 수 있다.**

```bash
git tag -a stage-20260922 -m "
장소: ...
로봇: 1대 (solo, Wi-Fi)
오프셋: bad +1200 / snucheer -1500 / newjeans +750
패드 12개 중 N개 정상
이슈: ...
"
```

현장 실측값을 태그 메시지에 남기면 다음 행사의 출발점이 된다. 지금은 "지난 무대에서 돈
정확한 코드"를 커밋 로그를 뒤져서 찾아야 한다.

그리고 운영자 화면 구석에 실행 중인 버전을 표시한다 — 현장에서 "지금 뭐가 돌고 있나"를
1초에 확인할 수 있어야 한다.
