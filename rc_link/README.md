# rc_link — PC → 유선 RC(RadioMaster Pocket) → ELRS → K1 명령 경로

motion_llm API 모드(Wi-Fi)의 차선 명령 경로 개발 작업공간.
전체 설계·단계는 `../motion_llm/docs/RC_WIRED_COMMAND_PLAN.md` 참조 (living doc).
행사 스택과 격리하기 위해 여기서 개발하고, P3에서 motion_llm에 가산 병합한다.

## 구성

| 경로 | 내용 |
|---|---|
| `radio/backup_20260817/` | RC SD의 MODELS/RADIO/SCRIPTS 원본 백업 (수정 전) |
| `radio/K1PCT.lua` | P0 시리얼 테스트 (TOOLS, 화면 있음) → SD `SCRIPTS/TOOLS/` |
| `radio/K1PCM.lua` | P0 믹서 컨텍스트 판정 (MIXES, 채널 출력 없음) → SD `SCRIPTS/MIXES/` |
| `bench.py` | PC측 왕복 벤치: `ping` / `gv3 <n>` / `monitor` |
| `tests/` | (P3용) |

## 진행 현황

- [x] **P0 벤치 (2026-08-17 완료)** — VCP=LUA 왕복 성공: ping 50/50 손실 0,
      RTT avg 29ms, GV3 쓰기 화면 확인. **호스트 = TOOLS 스크립트 확정**
      (커스텀 펌웨어가 표준 모델 메뉴를 숨겨 MIXES 등록 보류, K1PCM은 SD에 비활성 잔류).
      첫 접속 시 버퍼 찌꺼기 걸러야 함 (bench.py 반영)
- [x] **P1 펄스형 오버라이드 (2026-08-18 완료)** — `K1PC.lua` + 모델 믹스 3개(L1 게이트).
      RUN/STOP/DAMP 펄스 실증, keepalive 차단 +0.6s ABORT, 물리 통과 불변 확인.
      주의: USB-VCP=LUA가 재부팅 시 CLI로 리셋됨 — 사용 전 확인. 포트 권한은 udev로 해결
- [x] **P3a motion_llm 사본 + RcBackend (2026-08-18 코드 완성)** — `motion_llm_rc/`:
      `--rc` 백엔드(rc_serial/rc_backend), dance PREP 훅(발사 1.5s 전 사전 준비),
      매핑은 motions.yaml `rc_list`(8/15 로봇 덤프) 사용, busy/cooldown/완료타이머
      PC측 구현. 전체 123 tests OK. **실기 dry-run 통과 (8/18)**: PREP→FIRE 육안,
      뱅크B+자동해제 0.56s, dance 싱크 FIRE 오차 +1ms, 패드 RUN+busy 거부.
      주의: K1PC.lua 갱신 후 도구 EXIT→재실행 필요 (열려 있으면 옛 코드가 돔)
- [ ] P2 로봇 관측 + rc_list 실배포 대조 (로봇 복구 뒤)
- [ ] P3b 실기 검증 후 delta를 정본 motion_llm에 가산 병합
- [ ] P4 통합 리허설·런북

## motion_llm_rc 사본 실행

```bash
cd motion_llm_rc && python3 server.py --rc --https --port 18500
# operator 화면에서 dance 프리셋 "rctest"(마카레나=뱅크B 슬롯2) 로 무대 싱크 dry-run
```
RC 모드 패드 버튼 4개: 기사식 절 · 마카레나 · 록아웃 · 푸시업 (다이얼∩패드 교집합).
dance 기존 프리셋 3종(SnuCheer 등)은 **다이얼에 없어 RC로 못 쏨** — 로봇 다이얼
테이블에 추가해야 함 (P2 논의 항목).

## P0 절차 요약

1. RC 전원 ON + 위쪽 USB-C 연결 → 팝업 "USB Serial (VCP)"
2. 라디오 SYS → Hardware → Serial ports → **USB-VCP: CLI → LUA**
3. 라디오 SYS → Tools → `K1PCT` 실행
4. PC: `python3 bench.py ping 100` → 손실 0 확인, `python3 bench.py gv3 42` → 화면 GV3=42
5. K1PCT 종료(EXIT) → MDL → Custom scripts에 `K1PCM` 등록 → `ping`이 "PONG M"으로
   응답하면 본 구현 호스트=MIXES 확정, 안 되면 ROBOT.lua 통합 폴백
6. 판정을 RC_WIRED_COMMAND_PLAN.md에 기록. 롤백: USB-VCP를 CLI로 복귀

주의: 포트 권한은 재연결마다 초기화됨 — `sudo chmod a+rw /dev/ttyACM0`.
K1PCT와 K1PCM을 동시에 돌리지 말 것 (serialRead 경합).
