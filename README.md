# k1-stage — K1 행사 운영 스택

휴머노이드 **K1을 행사에서 운영하기 위한 앱**이다. 관객이 아이패드로 동작을 고르고,
TV가 미리보기와 무대 영상을 띄우고, 운영자가 폰으로 정지를 쥔다. 앱은 `app.py` 하나고
**모드**가 둘이다 — 갈리는 기준은 통신 경로가 아니라 **로봇을 몇 대 움직이느냐**다.

```
아이패드 /pad ─┐
폰 /operator ─┼─ 장소 랜 ─ PC ─┬─ Wi-Fi ───────────────→ 로봇 1대  ┐
메인컴 /dance ─┘               │                                    ├ solo 모드
                               ├─ USB ─ 라디오 1대 ─ ELRS ─→ 로봇 1대  ┘
                               │
                               └─ USB ─ 라디오 N대 ─ ELRS ─→ 로봇 N대  ← fleet 모드

                          TV /display (HDMI, 네트워크 무관)
```

## 두 모드와 고르는 기준

| | `--mode solo` (기본) | `--mode fleet` |
|---|---|---|
| 로봇 수 | **1대** | **꽂은 라디오 수만큼 동시에** |
| 경로 | Wi-Fi(기본) **+ RC 폴백** — 운영 중 `/rc/mode` 토글로 전환 | RC 전용 |
| 로봇 소프트웨어 | Wi-Fi 경로는 gateway 실행 필요 | **수정 불필요** |
| 실기 검증 | 개소식에서 운영 완료 | 전파 구간 미검증 (P2) |
| 이럴 때 | 평소 운영 (Wi-Fi가 죽어도 RC로 이어감) | 여러 대 군무 |

solo 모드도 RC를 쏠 수 있다 — `--rc`로 기동하거나 운영자 화면에서 토글하면 같은 1대를
전파로 몬다. fleet 모드만 가진 것은 **여러 대 동시 발사**(`runtime/rc_fleet.py`)다.

`rc_link`는 앱이 아니라 **라디오 쪽 작업 결과물**이다. 라디오에 올리는 Lua 도구(`K1PC.lua`),
믹서 모델 패치, SD 원본 백업, PC↔라디오 왕복 벤치가 들어 있다. fleet 모드를 쓰려면
여기 있는 절차대로 라디오를 먼저 준비해야 한다.

`robot/`은 로봇 쪽 짝이다. 위 앱들이 명령을 보낼 수 있도록 `ai_sapiens`에서 바꾼 부분
(RC 버튼 뱅크 10→26, API 권한·텔레옵 패스스루)만 담았다.

## 빠른 실행

```bash
# Wi-Fi 단일 로봇 — 점검·배포·gateway·relay 를 한 번에
./run.sh --deploy

# 로봇·라디오 없이 UI 만 (solo 는 인자 없이 mock)
python3 app.py
python3 app.py --mode fleet --mock

# RC 군무 — 라디오 준비가 끝난 뒤
python3 app.py --mode fleet                    # 또는 tools/start_fleet.sh
```

행사 당일 절차는 [docs/solo/RUNBOOK.md](docs/solo/RUNBOOK.md) 하나로 끝난다.
셋업 → 검증 시퀀스 → 장애 대응까지 현장 실측값 기준이다. 지금 무엇이 참인지는
[docs/solo/STATUS.md](docs/solo/STATUS.md)를 본다.

## 안전 경계

1. **RC Damping / E-stop이 항상 최우선**이다. 네트워크와 무관하게 동작한다.
2. RC의 SD(CH8)가 API 권한의 물리 허가다. 내리면 PC가 무슨 말을 해도 안 움직인다.
   반대로 **RC 모드에서는 SD를 내려야** 명령이 먹는다 — API 권한일 때 로봇은 teleop
   전이를 무시하기 때문이다.
3. 허용목록이 둘이고 서로 다르다. `api_allowlist` 14개가 운영자 수동 버튼이 부를 수 있는
   전부이고, 그 부분집합인 12개(venue 의 `pad_grid`)만 관객 패드에 연다. 모델(LLM) 경로는
   9/22 행사용으로 제거됐다(`source="llm"` 은 거부). 새 동작은 수동으로 먼저 실물 검증한 뒤 승격한다.
   (행사 전 전체 목록 139/79 는 `config/venues/20260831-opening/` 에 보관돼 있다.)
4. 대기 중 물리 스위치는 SC 상단 + SB 중앙에 둔다. **SC 중앙에 두지 않는다** —
   그 위치가 곧 "권한을 잃으면 ReadyPose"이고, 균형 정책 없는 자세라 가장 넘어지기 쉽다.

## 무엇이 저장소에 없나

`media/`(음원·안무 영상 417MB, 저작권물) · `static/clips/`(동작 sim 렌더 39MB) ·
`logs/`(관객 발화 원문) · TLS 개인키. 전부 로컬에만 둔다.

클립은 다시 구우면 재생성되고, 음원은 행사마다 다르다. `config/venues/<행사>/presets.json`의 싱크
오프셋은 **현장에서 재보정해야 하는 값**이라 저장소의 값은 출발점일 뿐이다.

## 저장소 구성

```
k1-stage/
├── app.py         앱 하나 — `--mode solo|fleet`. HTTP·인증·부팅 검증·백엔드 선택·State 배선
├── core/          도메인 — 무대 상태기계(stage) · 백엔드 계약(ports) · 설정 검증(catalog). 어댑터를 모른다
├── runtime/       통신 경로와 보조 — gateway · robot/relay/rc/rc_fleet 백엔드 · rc_serial · clip_len · session_log
├── web/           화면 4장(display · pad · operator · dance) · k1.js · base/tool.css · themes/
├── config/        solo/ · fleet/ (모드별 카탈로그·정책) · venues/<행사>/ (패드 12칸 · 프리셋 · 오프셋)
├── tools/         preflight.py(출발 전 점검) · 진단 스크립트 · start_fleet.sh
├── tests/         전부 여기 — 저장소 루트에서 `python3 -m unittest discover -s tests -t .`
├── docs/          solo/ · fleet/ (운영 문서) · design/ · RESTRUCTURE.md(구조 정리 기록)
├── run.sh         로봇 배포·relay 기동 진입점 (solo)
├── rc_link/       라디오 Lua·믹서 패치·SD 백업·왕복 벤치
└── robot/         ai_sapiens 변경분 (원본 · 현행 · patch)
```

화면 4장의 CSS 는 `web/` 한 벌이다. 앱마다 복제해 두니 실제로 갈렸다 — 8/31 새 대기
이미지가 fleet 앱 쪽에만 들어가 `display.html` 두 벌이 서로 다른 화면이 됐다. 지금은
**관객 화면(display·pad)만 테마를 타고**(`--theme`, 기본 solo=`shape` / fleet=`shape-gym`),
**운영자 화면(operator·dance)은 테마 밖**이다 — 행사마다 바뀌면 현장에서 헷갈린다.
`web/base.css` 는 테마가 못 건드리는 뼈대(캔버스 스케일 메커니즘·레이어 페이드·z-index)라
디자인을 잘못 넣어도 화면이 안 뜨는 일은 없다.

## 행사 설정과 출발 전 점검

행사마다 바뀌는 것(패드 12칸 · 오프셋 · 음원)은 코드가 아니라 `config/venues/<행사>/` 에 있다.

```
config/venues/20260922-bank/
├── venue.yaml     사람이 쓴다 — 패드 12칸(pad_grid)·메모. 주석을 마음껏 단다
└── presets.json   서버가 쓴다 — /dance 에서 저장한 프리셋과 오프셋
```

두 파일로 가른 이유는 쓰는 주체가 달라서다. 서버가 저장할 때마다 YAML 을 통째로 다시 쓰면 사람이
적은 주석이 사라진다. 오프셋은 **그 장소의 물리량**(스피커·TV·로봇 경로)이라 행사마다 재보정하는
값이다 — 폴더째 커밋해 두면 다음 행사의 출발점이 된다.

```bash
python3 tools/preflight.py                            # 출발 전 점검 (solo, 기본 venue 20260922-bank)
python3 tools/preflight.py --mode fleet
python3 app.py --venue 20260922-bank                  # 같은 검증이 부팅 때도 돈다
```

서버 부팅과 preflight 는 **같은 함수**(`core/catalog.validate`)를 부른다. FATAL 이 있으면 서버가
뜨지 않는다 — 프리셋이 카탈로그·`api_allowlist` 에 없는 동작을 가리키거나, 패드가 눌러도 거부될
버튼을 갖고 있거나, 숫자 자리에 문자열이 들어간 경우다. 무대에서 발견하던 걸 노트북에서 발견한다.

**이 검증이 못 잡는 것**: 프리셋의 동작이 카탈로그에 있고 허용돼 있으면 통과한다. 그게 그 곡의
동작이 맞는지는 코드가 알 수 없다(8/21 의 "영상은 뉴진스, 로봇은 체스트팝"). preflight 가 끝에
찍는 **프리셋 짝 확인표**를 사람이 한 번 눈으로 본다.

`motions.yaml` · `gateway_config.yaml` 은 **모드별** 데이터라 `config/solo/` · `config/fleet/` 에 따로 있다 —
로봇의 RC 다이얼 덤프가 달라서다(코드가 아니라 데이터의 차이다). 로봇에는 저장소와 같은 배치의
부분집합(`run.sh` 의 `DEPLOY_FILES`)이 실린다.

`solo_stage` 와 `group_stage` 는 각각의 이력을 가지고 합쳐졌고 2026-09-21 에 앱 하나로 통합됐다
(기록: [docs/RESTRUCTURE.md](docs/RESTRUCTURE.md)).

> 폴더 이름은 2026-09-20에 바꿨다: `motion_llm` → `solo_stage`, `rc_stage` → `group_stage` (그 뒤 통합).
> **로봇 컨테이너 안 배포 경로는 아직 `/root/motion_llm/`이다** — `run.sh`의 `ROBOT_DIR`
> 참고.
