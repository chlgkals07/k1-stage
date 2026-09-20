# group_stage — K1 RC 군무 서버

**연결된 RadioMaster Pocket 전부에 명령을 동시에 쏜다** — 꽂은 라디오 수 = 같이
움직이는 로봇 수. PC→USB→Pocket→ELRS→로봇, 로봇 소프트웨어 수정 없음.
단일 로봇·Wi-Fi(relay) 운영은 정본 `../solo_stage` 을 쓴다. 이 앱은 RC 전용이다.

## 실행

```bash
python3 server.py            # http://<pc>:19000 → /operator 로 리다이렉트
python3 server.py --mock     # 라디오 없이 UI/무대 흐름 확인
```

화면 3장: `/operator`(플릿 상태·수동 실행·무대 조작) · `/display`(TV) · `/dance`(오프셋 보정)

## 라디오 준비 (대당 ~10분, 1호기와 동일 절차)

1. Storage 모드: `../rc_link/radio/gen_model_p1.py` 로 model00.yml 패치(L1+pc5/6/7 믹스),
   `../rc_link/radio/K1PC.lua`(v2.3+) 를 SCRIPTS/TOOLS/ 에 복사
2. USB-VCP=LUA (부팅마다 리셋되니 사용 전 확인) · Serial 모드 연결
3. SYS→Tools→K1PC 실행 (화면 v2.3 확인)
4. 운영자 화면 [USB 재탐색] → 플릿에 들어옴

## 운영 수칙

- 미믹 쏠 때 각 라디오 **SB 중앙** (하단이면 펄스 후 code 3 이 미믹을 끊는다)
- 로봇 부팅 직후엔 **정지 버튼**(Velocity 복귀 펄스) 먼저 — Damping 에선 미믹 불가
- 라디오 각각이 자기 로봇의 물리 E-stop (SC) — 책상에 나란히 두고 운영
- 무대는 `-rc` 프리셋 사용, 오프셋은 /dance 에서 실기 보정

## 구조

`server.py`(solo_stage 파생: stage 상태기계·dance 절대시각 싱크·자막·자동종료 상속)
+ `rc_fleet.py`(USB 열거·Barrier 동시 발사·대별 집계) + `rc_serial.py`/`rc_backend.py`
(solo_stage 과 동일). 상세 배경: ../solo_stage/docs/RC_WIRED_COMMAND_PLAN.md
