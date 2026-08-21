# 유선 RC 명령 경로 계획 (PC → RadioMaster Pocket → ELRS → K1)

작성 2026-08-17. 상태: **P0 진행 중** (준비 완료, 실기 검증 대기)

**작업 위치**: 개발은 `~/Projects/shape3/k1-stage/rc_link/`에서 진행한다 (행사 스택과 격리,
shape17→shape3 dance 병합 선례를 따름). motion_llm에는 P3(백엔드 통합)에서만
`rc_serial.py`/`rc_backend.py`/`rc_slots.yaml`을 가산 병합하고 `server.py`에 토글
분기를 넣는다. 그 전까지 motion_llm 코드는 무접촉 (이 문서 제외).

**P0 결과 (2026-08-17, 실기 완료)**: USB-VCP=LUA에서 PC↔RC Lua 왕복 실증 성공.
- `bench.py ping`: 50/50 손실 0, 왕복 지연 min 10.8 / avg 29.1 / max 44.7 ms
  (스크립트 실행 주기 ~30ms와 일치). 첫 접속 직후에는 모드 전환 전 버퍼 찌꺼기
  (바이너리)가 섞여 나오므로 프로토콜은 낙오/쓰레기 줄을 걸러야 한다 (bench에 반영).
- `GV3 42` 쓰기 → "OK" 회신 + 라디오 화면 실측 확인.
- **본 구현 호스트 판정: TOOLS 스크립트 확정.** 운영자가 Tools에서 K1PC를 여는
  행위 = PC 제어 모드 진입(화면 점유가 곧 모드 표시), EXIT = 해제. 커스텀 펌웨어
  (`K1-2.10.0-POCKET.bin`)가 MDL 키를 "Mimic setup"으로 재매핑하고 표준 모델 메뉴
  (CUSTOM SCRIPTS 포함)가 노출되지 않아 MIXES 등록은 보류 — 필요 시 model00.yml
  직접 편집으로 가능(백업 확보됨). `K1PCM.lua`는 SD에 있으나 미등록(비활성).
- 명령 왕복 ~30ms는 스위치 시퀀스(수백 ms 유지)에 충분.

**P1 결과 (2026-08-18, 실기 완료)**: 펄스형 오버라이드 전 매트릭스 통과.
- 배포: `K1PC.lua`(TOOLS 운영판) + model00.yml에 pc5/pc6/pc7 REPL 믹스(swtch L1)
  + L1(FUNC_STICKY, 물리 미연결) — 총 55줄 추가, 삭제 0. 재부팅 후 모델 무결성·
  물리 통과(스위치→채널 그대로) 실측 확인. **평상시 RC 동작 불변 실증.**
- 펄스 실측: `RUN 3`/`STOP`/`DAMP` 순서대로 화면 확인, 완료 후 물리 복귀.
  keepalive 차단 시 **+0.60s ABORT** 자동 해제, 직후 정상 펄스 복구.
  슬롯 검증: 21-40 `ERR PAGE`(P2 전), 범위 밖 `ERR ARG`.
- K1PC 왕복 지연 avg **0.4ms** (P0 도구 29ms보다 빠름 — 싱크에 유리).
- **운영 체크리스트 추가**: ① USB-VCP=LUA가 재부팅 후 CLI로 되돌아감(커스텀 펌웨어
  추정) — PC 모드 사용 전 Hardware에서 확인 필수. ② 포트 권한은 udev rule 설치로
  해결됨(`/etc/udev/rules.d/99-radiomaster.rules`). ③ 펄스 중 CH5는 물리 SA 미러링.
- **P3 개선 예약**: 발사 엣지를 sticky(10Hz, ~100ms 지터)가 아니라 GV 쓰기(즉시)로
  옮기면 dance 절대시각 싱크에 ms급 정밀도 확보 가능 — L1은 code 0 자세로 미리
  올려두고, code 4 진입만 GV4로 트리거.

**P3a 결과 (2026-08-18, 코드 완성 — 로봇 불가 기간의 선행 구현)**:
- **사본** `~/Projects/shape3/k1-stage/rc_link/motion_llm_rc/` (정본 무접촉). `--rc` 플래그로
  `RcBackend` 선택: `rc_serial.py`(keepalive 스레드 포함 시리얼 클라이언트) +
  `rc_backend.py`(busy/cooldown/완료타이머 PC측 구현, 기존 백엔드 계약 준수).
- 매핑은 **motions.yaml `rc_list`**(2026-08-15 로봇 k1_config 덤프, 뱅크 A/B×20)
  직접 사용 — 뱅크 B는 input_code 5. 별도 매핑 파일 없음. 실배포 대조는 P2.
- **dance 싱크**: `start_dance`에 PREP 타이머(발사 1.5s 전, hasattr(prepare) 덕타이핑)
  추가. K1PC v2가 PREP(code 0 유지)/FIRE(GV 즉시 쓰기 엣지) 분리 — 지터 ms급 목표.
- RC 모드 패드 버튼 4개(rc_list∩pad_allowlist). **기존 dance 프리셋 3종은 다이얼에
  없어 RC로 불가** — 테스트 프리셋 `rctest`(마카레나) 추가. 로봇 다이얼에 공연
  모션 추가는 P2 논의 항목.
- 검증: 전체 123 tests OK (신규 rc 25 포함), `--rc` 실기동 확인.

**P3a 실기 dry-run 결과 (2026-08-18, RC만·로봇 OFF)**: 전 항목 통과.
- PREP(2s 유지)→FIRE 시퀀스 화면 육안 확인 (code 0 유지 → CH6 엣지 → 복귀)
- 뱅크 B PREP + keepalive 차단 → **+0.56s 자동 ABORT**
- dance 싱크: `/dance/start`(rctest) → PREP 발사 1.43s 전 → **FIRE 예약 대비 +1ms**
  (라디오 처리 ~30ms + ELRS ~4ms가 상수로 더해짐 — v2 도구 주기 30ms가 지터 상한)
- 패드: `/motion source=pad` → RUN 뱅크A 슬롯1 발사, 직후 재요청 busy 거부,
  `/stop` → RC ReadyPose 펄스. source 미지정 시 llm 게이트가 거부 (안전층 정상)
- 운영 메모: K1PC 갱신 후엔 도구를 EXIT 후 재실행해야 새 코드가 로드됨.
  udev rule(`99-radiomaster.rules`) 설치로 포트 권한 영구 해결.

**P3b 결과 (2026-08-18)**: 운영자 런타임 토글 + UI 동일성 + 등가성 검증 완료.
- 운영자 "명령 경로" 섹션: [RC 모드 켜기/끄기] (`POST /rc/mode`), 실패 원인 표시.
  RcBackend gateway 보고를 "ready/offline"로 바꿔 실행 버튼 잠김 해결.
- UI 동일: api_allowlist 제거로 패드 12개·수동 목록·무대 primary 와 동일.
  다이얼에 없는 동작만 실행 시점 거부. EXECUTING = rc_list note 길이 or 기본 30s
  추정(정지 버튼이 busy 해제).
- **실배포 다이얼 확정** (`~/Projects/ai_sapiens_backup/ai_sapiens_sim2real_20260818`):
  뱅크A 인사 20 + 뱅크B 퍼포먼스 20 — 무대 3종(ChestpopV2 B1·SnuCheer B4·Straykids
  B5·NewSnuCheerHeadShort B20)과 패드 11/12 전부 포함. 예외: MimicGuapVer2(다이얼엔
  MimicGuap — 이름 정리 필요). rc_list는 `rc_link/gen_rc_list.py`로 백업에서 재생성.
- **verify_sweep.py 40/40 통과** (K1PC v2.1 CHK) — 펄스 출력이 검증된 다이얼 경로와
  동일. 명목 대비 ±12µs는 EdgeTX 표시 관례로 로봇 보드 스케일에서 소멸 추정.
  시리얼 신뢰성 수정: 타임아웃 시 포트 유지 + 재시도. 전체 127 tests OK.

**정본 병합 완료 (2026-08-18)**: motion_llm은 이제 **git 저장소**(main 브랜치)다.
베이스라인(title/credit 자막 포함) → RC delta 2커밋 → merge 커밋. 병합 후 133 tests
OK, 기본 모드 부팅 시 패드 12개·mock·시리얼 미사용 확인 (RC는 토글 전 존재감 0).
사본 `rc_link/motion_llm_rc`는 보관용으로 강등. rc_list 갱신은
`rc_link/gen_rc_list.py <로봇백업 k1_config> motions.yaml`. 후속 변경은 git으로 관리.

**다음 (로봇 복구 후, P2)**: `/ai_sapiens_rc/status` 에코로 스위프 재검증(Damping
상태라 안전) → 정지(ReadyPose) 진입 → E-stop 요원 두고 단일 모션 → dance 실기
오프셋 보정 → GuapVer2 이름 정리 (다이얼엔 MimicGuap — 패드 목록과 이름 불일치).

## 1. 목표

API 모드(PC↔OrinNX Wi-Fi)가 현장에서 불안할 때를 대비한 **차선 명령 경로**.
패드/운영자 UI와 `server.py` `/motion` API는 그대로 두고, 백엔드만 하나 추가한다:

```
패드 "스쿼트" ──HTTPS──> server.py /motion (기존 allowlist·UI 불변)
                           ├─ RelayBackend ── Wi-Fi ──> 로봇 gateway   (1순위, 기존)
                           └─ RcBackend ── USB 시리얼 ──> Pocket Lua
                                └ GV/믹스 ──> ELRS 2.4GHz ──> 로봇 CRSF 수신기
                                                └ /ai_sapiens_rc/status → 기존 상태기계
```

- 로봇 소프트웨어 **수정 0** (로봇에겐 정상 RC 입력으로 보임)
- 전환은 자동 failover가 아니라 **운영자 수동 토글** (운영자 화면)
- 부를 수 있는 모션은 다이얼 슬롯(최대 40)에 등록된 것으로 제한 — 합의됨

## 2. 실측으로 확정된 사실 (2026-08-17)

### RC (RadioMaster Pocket, "SNPR50A1010")

- 펌웨어 **EdgeTX 2.10.0 커스텀 빌드** (`K1-2.10.0-POCKET.bin`). `serialRead()`의
  2.9.0 버그는 2.10에서 수정된 버전대.
- USB-C(위쪽 포트)로 PC 연결 → 팝업에서 Serial 선택 시 `/dev/ttyACM0` (VID:PID
  0483:5740). 현재 VCP 모드는 **CLI** (프롬프트 응답 확인).
- **EdgeTX 소스 확인: USB-VCP에서 SBUS Trainer 모드는 명시적으로 차단됨**
  (`isSerialModeAvailable`). → A안 탈락, **B안(VCP=LUA + Lua 스크립트) 확정**.
- 활성 모델 `model00.yml` "K1-000"의 채널 구성:

| 채널 | 소스 | 비고 |
|---|---|---|
| CH1~4 | 스틱 (I3/I1/I2/I0) | 속도. **PC는 건드리지 않음** |
| CH5 | SA | 페이지 뱅크 (2페이지×20=40슬롯, 실배포 로봇 확인 필요) |
| CH6 | SB | input code 조합 |
| CH7 | SC | input code 조합 (하단=Damping) |
| CH8 | SD | API arm. **PC는 건드리지 않음** |
| CH9 | SE | 모멘터리 |
| CH10 | P1 (포트) | |
| CH11 | **GV1 (REPL, 이름 "mode")** | 다이얼은 물리 노브가 아니라 GV |
| CH12 | **GV2 (REPL, 이름 "estop")** | E-stop. **PC는 건드리지 않음** |

- **핵심: "Lua가 GV를 세팅해 채널을 구동"은 이미 이 라디오의 기본 패턴이다.**
  메인 화면 `SCRIPTS/TELEMETRY/ROBOT.lua`(891줄, 팀 작업물, 8/14 수정)가
  `/RADIO/k1-modes.txt`(20슬롯: Mimic_squat, dance1~2, custom1~17)를 읽어
  `model.setGlobalVariable(0, 0, pct)`로 CH11을 구동한다. E-stop은 트림 버튼
  제스처로 GV2→CH12. pwm=1500+pct×5 (슬롯 n → pwm 1000+(n-1)×20, pct −100+(n-1)×4).
- 텔레메트리 센서 정의됨: RQly/1RSS/TQly 등 — Lua에서 `getValue()`로 읽어 PC로
  회신 가능 (RF 링크 상태 피드백).

### 로봇 (ai_sapiens, 수정 불필요)

- CRSF 수신 → 컨트롤 테이블 → `/ai_sapiens_rc/status` → teleop plugin
  (`radiomaster_pocket.yaml`): input code = CH7 1000→Damping(1) / 1500→ReadyPose(2)
  / 2000+CH6 1000→Velocity(3) / 2000+CH6 2000→**Mimic 진입(4)** / 2000+CH6 1500→코드 0.
  selector = CH11 (tolerance, code 4에서만 필요). switch_match_tolerance 50.
- Mimic 완료 시 `on_complete: Velocity` 복귀. 관리본 selector table(10슬롯)은
  구버전 — **실배포본(40슬롯)은 로봇 켠 뒤 조회**.

## 3. 설계

### 3.1 RC 쪽 — 추가 파일 2개 + 모델 편집 1건 (가산적, 기존 파일 수정 없음*)

*ROBOT.lua는 v1에서 수정하지 않는다. GV1 쓰기 충돌은 §6 리스크 참조.

**(a) `/SCRIPTS/MIXES/K1PC.lua` — PC 명령 수신 Lua 믹서 스크립트**

- 매 믹스 사이클 `serialRead()`로 줄 단위 명령 파싱 (VCP 모드 = LUA 필요)
- 명령이 신선할 때만(keepalive) `setStickySwitch(0, true)` — 끊기면 200ms 내 자동 false
- GV 세팅: GV1(CH11 selector, ROBOT.lua와 같은 방식) + **GV4→CH6, GV5→CH7,
  GV6→CH5** 오버라이드 값
- 회신: 명령 ACK + 주기적 텔레메트리(RQly, 1RSS, GV 상태) `serialWrite()`
- 믹서 스크립트가 커스텀 펌웨어에서 안 돌면(P0에서 판정) ROBOT.lua에 통합하는
  폴백 (메인 화면이 항상 떠 있으므로 실용상 동작; 화면 이탈=자동 해제라는 fail-safe 부수효과)

**(b) `model00.yml` 편집 — 게이트된 오버라이드 믹스 3개 추가**

- CH5/CH6/CH7에 각각 `REPL, weight=GV6/GV4/GV5, swtch=L02` 믹스 추가
- **L01** = sticky (Lua keepalive가 setStickySwitch로 제어),
  **L02 = L01 AND SE↑** 같은 물리 스위치 조합 *(게이트 스위치는 논의 필요 — §7)*
- 게이트 OFF = 물리 스위치 값 그대로 (기존 동작 완전 보존)
- 편집 전 `model00.yml` 백업 (`BACKUP/` + PC 사본)

**(c) 라디오 설정**: USB-VCP 모드 CLI→**LUA**, USB mode 기본값을 Serial로
(팝업 생략). 둘 다 Hardware/일반 설정 메뉴에서.

### 3.2 PC 쪽 — motion_llm에 가산적 추가 (정본 `shape3/motion_llm`)

**(a) `rc_serial.py`** — `/dev/serial/by-id/usb-OpenTX_Radiomaster_Pocket*` 오픈,
재연결 루프, 10Hz keepalive, 줄 프로토콜:

```
PC→RC:  PING | MODE <1..40> | CODE <0|1|2|3|4> | NEUTRAL
RC→PC:  OK <cmd> | ERR <이유> | TLM lq=<RQly> rssi=<1RSS> gate=<0|1>
```

**(b) `rc_backend.py` — `RcBackend`** (MotionBackend 인터페이스 준수):

- `rc_slots.yaml`: 모션 이름 ↔ 슬롯 번호 매핑 (**로봇 실배포 selector table에서
  생성**, 수동 관리 금지)
- 실행 시퀀스: idle 확인 → `MODE n` → 100ms → `CODE 4` → 300ms 유지 → `CODE 0`
  → 모션 길이 타이머(motions.yaml `duration` 활용, 없으면 보수적 기본값+cooldown)
- 정지(`/motion/stop`) = `CODE 2` (ReadyPose) — gateway `stop_state`와 동일 의미
- allowlist·cooldown·단일 실행은 gateway와 동일 규칙을 PC에서 재구현
- 상태 보고: 로봇 모드 피드백이 없으므로 `executing`은 타이머 추정임을 UI에 명시
  (운영자 화면에 "RC 모드 — 상태는 추정" 배지 + TLM의 RF 링크 지표 표시)

**(c) `server.py`** — 백엔드 토글: 운영자 화면에 `relay ↔ rc` 전환 버튼
(`POST /backend`), 기존 코드는 분기 추가만.

**(d) 테스트** — `test_rc_backend.py`(시퀀스·allowlist·타이머, 시리얼은 mock),
`test_rc_serial.py`(프로토콜 파싱·keepalive), 가짜 RC 역할 pty 루프백.

### 3.3 안전 설계 (불변 조건)

1. **CH12(estop)·CH8(API arm)·CH1~4(속도)는 PC가 절대 만지지 않는다.**
   ROBOT.lua의 트림 E-stop 제스처도 그대로 산다.
2. 게이트는 **물리 스위치 AND 소프트웨어 sticky** — 스위치 내리면 즉시 물리 복귀,
   PC/케이블/스크립트가 죽어도 keepalive 타임아웃으로 자동 복귀.
3. PC의 소프트 정지는 `CODE 1`(Damping)/`CODE 2`(ReadyPose) 두 단계 다 제공하되,
   UI의 빨간 정지는 기존 의미(ReadyPose) 유지, Damping은 별도 확인 버튼.
4. LLM 경로는 v1에서 RC 백엔드에 노출하지 않는다 — **수동(pad/operator) 전용**으로
   실물 검증 후 승격 (기존 api→llm allowlist 승격 관행과 동일).

## 4. 단계별 실행 계획

| 단계 | 내용 | 완료 판정 |
|---|---|---|
| **P0 벤치** | VCP=LUA 전환, 최소 에코 Lua(MIXES 또는 ROBOT 통합)로 serialRead/Write 왕복 확인 | PC에서 보낸 줄이 에코됨 |
| **P1 모델** | model00.yml 백업 → 오버라이드 믹스+LS 추가 → 라디오 채널 모니터로 게이트 ON/OFF 시 CH5/6/7만 움직이는지 확인 (로봇 OFF) | 게이트 OFF에서 기존 조작과 완전 동일 |
| **P2 로봇 관측** | 로봇 ON, Damping 상태에서 `ros2 topic echo /ai_sapiens_rc/status`로 PC 명령→채널 반영 확인. **실배포 selector table 조회 → `rc_slots.yaml` 생성** | 명령한 pwm이 status에 그대로 보임 |
| **P3 단일 모션** | RcBackend 연결, E-stop 요원 배치, `MimicWaveHand` 1회 실기 실행→타이머 복귀 | 실행·정지·게이트 해제 3종 실증 |
| **P4 통합** | 패드 end-to-end, 백엔드 토글 리허설, FIELD_SETUP/CEREMONY_RUNBOOK에 RC 모드 절차 추가, 20분 soak | 운영 문서로 제3자가 재현 가능 |

각 단계 종료 시 이 문서의 상태를 갱신한다 (living doc).

## 5. 롤백

- RC: `model00.yml` 백업 복원 + `K1PC.lua` 삭제 + VCP 모드 CLI 복귀 — 원상태
- PC: RcBackend는 가산적 — 토글을 relay로 두면 기존 경로 그대로

## 6. 리스크

| 리스크 | 대응 |
|---|---|
| 커스텀 K1 펌웨어에 Lua 믹서 미포함 | P0에서 판정, ROBOT.lua 통합 폴백 |
| GV1 쓰기 충돌 (ROBOT.lua UI vs PC) | v1 운영 수칙: 게이트 ON 중 라디오 다이얼 조작 금지. v2에서 ROBOT.lua에 게이트 표시 추가 검토 |
| serialRead 줄 버퍼 한계 | 명령을 16자 이내로 유지 |
| USB 재열거(케이블 재연결) | by-id 경로 + 재연결 루프 + udev rule |
| 타이머 추정과 실제 완료 불일치 | duration+여유 cooldown, 운영자 화면에 추정 표시 |
| 실배포 selector 40슬롯 구조(CH5 페이지) 미확인 | P2에서 실측 후 rc_slots.yaml 생성. 그 전엔 페이지1(20슬롯)만 사용 |

## 7. 확정 전 논의 필요

1. **게이트 물리 스위치 선택** — 후보: SE(모멘터리라 부적합할 수 있음), SA/SB/SC는
   이미 기능 있음. 남는 물리 입력이 사실상 없어 **"sticky 단독(물리 AND 없이) +
   keepalive 타임아웃"**으로 갈지, 스위치 하나의 기존 역할을 조정할지 결정 필요.
2. 다이얼 페이지(CH5) 오버라이드를 v1에 포함할지 (미포함 시 20슬롯).
3. `rc_slots.yaml` 생성 시점 — 로봇을 언제 켤 수 있는지.
4. RC 모드에서 UI 문구/배지 디자인 (추정 상태 표시 방식).
