# k1-stage — K1 행사 운영 스택

휴머노이드 **K1을 행사에서 운영하기 위한 앱 모음**이다. 관객이 아이패드로 동작을 고르고,
TV가 미리보기와 무대 영상을 띄우고, 운영자가 폰으로 정지를 쥔다. 앱이 갈리는 기준은
통신 경로가 아니라 **로봇을 몇 대 움직이느냐**다.

```
아이패드 /pad ─┐
폰 /operator ─┼─ 장소 랜 ─ PC ─┬─ Wi-Fi ───────────────→ 로봇 1대  ┐
메인컴 /dance ─┘               │                                    ├ solo_stage
                               ├─ USB ─ 라디오 1대 ─ ELRS ─→ 로봇 1대  ┘
                               │
                               └─ USB ─ 라디오 N대 ─ ELRS ─→ 로봇 N대  ← group_stage

                          TV /display (HDMI, 네트워크 무관)
```

## 두 앱과 고르는 기준

| | `solo_stage` | `group_stage` |
|---|---|---|
| 로봇 수 | **1대** | **꽂은 라디오 수만큼 동시에** |
| 경로 | Wi-Fi(기본) **+ RC 폴백** — 운영 중 `/rc/mode` 토글로 전환 | RC 전용 |
| 로봇 소프트웨어 | Wi-Fi 경로는 gateway 실행 필요 | **수정 불필요** |
| 실기 검증 | 개소식에서 운영 완료 | 전파 구간 미검증 (P2) |
| 이럴 때 | 평소 운영 (Wi-Fi가 죽어도 RC로 이어감) | 여러 대 군무 |

`solo_stage`도 RC를 쏠 수 있다 — `--rc`로 기동하거나 운영자 화면에서 토글하면 같은 1대를
전파로 몬다. `group_stage`만 가진 것은 **여러 대 동시 발사**(`rc_fleet.py`)다.

`rc_link`는 앱이 아니라 **라디오 쪽 작업 결과물**이다. 라디오에 올리는 Lua 도구(`K1PC.lua`),
믹서 모델 패치, SD 원본 백업, PC↔라디오 왕복 벤치가 들어 있다. `group_stage`를 쓰려면
여기 있는 절차대로 라디오를 먼저 준비해야 한다.

`robot/`은 로봇 쪽 짝이다. 위 앱들이 명령을 보낼 수 있도록 `ai_sapiens`에서 바꾼 부분
(RC 버튼 뱅크 10→26, API 권한·텔레옵 패스스루)만 담았다.

## 빠른 실행

```bash
# Wi-Fi 단일 로봇 — 점검·배포·gateway·relay 를 한 번에
cd solo_stage && ./run.sh --deploy

# RC 군무 — 라디오 준비가 끝난 뒤
cd group_stage && python3 server.py            # 실기
cd group_stage && python3 server.py --mock     # 라디오 없이 UI 확인
```

행사 당일 절차는 [solo_stage/docs/RUNBOOK.md](solo_stage/docs/RUNBOOK.md) 하나로 끝난다.
셋업 → 검증 시퀀스 → 장애 대응까지 현장 실측값 기준이다. 지금 무엇이 참인지는
[solo_stage/docs/STATUS.md](solo_stage/docs/STATUS.md)를 본다.

## 안전 경계

1. **RC Damping / E-stop이 항상 최우선**이다. 네트워크와 무관하게 동작한다.
2. RC의 SD(CH8)가 API 권한의 물리 허가다. 내리면 PC가 무슨 말을 해도 안 움직인다.
   반대로 **RC 모드에서는 SD를 내려야** 명령이 먹는다 — API 권한일 때 로봇은 teleop
   전이를 무시하기 때문이다.
3. 허용목록이 셋이고 서로 다르다. `api_allowlist` 78개가 운영자 수동 버튼이 부를 수 있는
   전부이고, 그 부분집합인 `pad_allowlist` 12개만 관객 패드에 연다(`llm_allowlist` 21개는
   모델 경로용). 새 동작은 수동으로 먼저 실물 검증한 뒤 승격한다.
4. 대기 중 물리 스위치는 SC 상단 + SB 중앙에 둔다. **SC 중앙에 두지 않는다** —
   그 위치가 곧 "권한을 잃으면 ReadyPose"이고, 균형 정책 없는 자세라 가장 넘어지기 쉽다.

## 무엇이 저장소에 없나

`media/`(음원·안무 영상 417MB, 저작권물) · `static/clips/`(동작 sim 렌더 39MB) ·
`logs/`(관객 발화 원문) · TLS 개인키. 전부 로컬에만 둔다.

클립은 다시 구우면 재생성되고, 음원은 행사마다 다르다. `dance_presets.json`의 싱크
오프셋은 **현장에서 재보정해야 하는 값**이라 저장소의 값은 출발점일 뿐이다.

## 저장소 구성

```
k1-stage/
├── solo_stage/    로봇 1대 운영 서버 (정본). Wi-Fi + RC 폴백. 140 tests
├── group_stage/   RC 군무 서버 — 연결된 Pocket 전부 동시 발사. 99 tests
├── web/           두 앱이 같이 쓰는 프론트 — 관객 화면 2장 · k1.js · base/tool.css · themes/
├── rc_link/       라디오 Lua·믹서 패치·SD 백업·왕복 벤치
└── robot/         ai_sapiens 변경분 (원본 · 현행 · patch)
```

화면 4장의 CSS 는 `web/` 한 벌이다. 앱마다 복제해 두니 실제로 갈렸다 — 8/31 새 대기
이미지가 `group_stage` 에만 들어가 `display.html` 두 벌이 서로 다른 화면이 됐다. 지금은
**관객 화면(display·pad)만 테마를 타고**(`--theme`, 기본 solo=`shape` / group=`shape-gym`),
**운영자 화면(operator·dance)은 테마 밖**이다 — 행사마다 바뀌면 현장에서 헷갈린다.
`web/base.css` 는 테마가 못 건드리는 뼈대(캔버스 스케일 메커니즘·레이어 페이드·z-index)라
디자인을 잘못 넣어도 화면이 안 뜨는 일은 없다.

`solo_stage`와 `group_stage`는 각각의 커밋 이력을 그대로 가지고 합쳐졌다.
`group_stage`는 `solo_stage`에서 파생됐고 stage 상태기계·무대 싱크·자막·자동종료를 공유한다.

> 폴더 이름은 2026-09-20에 바꿨다: `motion_llm` → `solo_stage`, `rc_stage` → `group_stage`.
> 옛 이름은 음성·LLM 경로가 주 기능이던 시절(2026-08-18 제거)의 잔재이고, RC 폴백이
> 들어오면서 "Wi-Fi 앱 / RC 앱" 구분도 사실과 맞지 않게 됐다.
> **로봇 컨테이너 안 배포 경로는 아직 `/root/motion_llm/`이다** — `run.sh`의 `ROBOT_DIR`
> 참고.
