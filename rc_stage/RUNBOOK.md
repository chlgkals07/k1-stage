# rc_stage 런북 — RC 군무 (라디오 N대 동시 발사)

연결된 RadioMaster Pocket **전부**에 같은 명령이 동시에 나간다. 꽂은 라디오 수 =
같이 움직이는 로봇 수. 단일 로봇·Wi-Fi 운영은 `../motion_llm`(run.sh)을 쓴다.

---

## 1. 라디오 준비 (라디오마다, 매번)

| # | 할 일 | 확인 |
|---|---|---|
| 1 | 라디오 **전원 ON** | ROBOT 화면이 평소대로 뜬다 |
| 2 | **위쪽 USB-C**로 PC 연결 → 팝업에서 **Serial** 선택 | (Storage/Joystick 아님) |
| 3 | SYS → Hardware → Serial ports → **USB-VCP = LUA** | **재부팅하면 CLI로 리셋된다 — 매번 확인** |
| 4 | SYS → Tools → **K1PC** 실행 | 화면 상단 `K1PC v2.3 IDLE` |
| 5 | 미믹 쏠 준비: **SB 중앙**, SC 상단 | SB 하단이면 펄스 후 미믹이 끊긴다 |

> **K1PC 화면은 계속 떠 있어야 한다.** EXIT로 닫으면 그 라디오는 명령을 못 받는다
> (= 그 라디오의 PC 제어 해제). 화면이 곧 "PC 제어 중" 표시다.

메뉴에서 USB-VCP를 못 찾으면: Storage 모드로 꽂아 SD의 `RADIO/radio.yml` 에서
`serialPort: VCP: mode:` 를 `CLI` → `LUA` 로 바꾸고 라디오를 재부팅한다.

## 2. 서버 켜기 (PC)

```bash
cd ~/Projects/shape3/k1-stage/rc_stage
set -a; . ~/.k1/secrets.env; set +a
export K1_GATEWAY_TOKEN="$K1_STAGE_TOKEN"      # 토큰 고정 → 링크가 안 바뀐다
python3 server.py --https --port 19000
```

`--https` 를 빼면 **외부 기기(아이패드·TV)에서 로그인이 안 된다** — 인증 쿠키에
Secure 플래그가 붙어 HTTP 에서는 브라우저가 저장하지 않는다. 자체 서명 인증서라
첫 접속 때 "고급 → 계속" 을 눌러야 한다.

## 3. 화면 열기

토큰은 `~/.k1/secrets.env` 의 `K1_STAGE_TOKEN` (고정). `<PC-IP>` 는 유선 LAN
`192.168.10.58`, 원격이면 Tailscale `100.86.174.82`.

| 화면 | 주소 |
|---|---|
| 운영자 | `https://<PC-IP>:19000/operator?token=<TOKEN>` |
| 무대(TV) | `https://<PC-IP>:19000/display?token=<TOKEN>` |
| 댄스 싱크 | `https://<PC-IP>:19000/dance?token=<TOKEN>` |

한 번 열면 쿠키가 남아 이후엔 `?token=` 없이 들어가도 된다.

## 4. 운영 순서

1. 운영자 화면에서 **라디오 N/N대** 표시 확인. 안 맞으면 **[USB 재탐색]**
2. (로봇 있을 때) 로봇 부팅 직후엔 **정지 버튼** 먼저 — Damping 에서는 미믹이 안 나간다
3. **수동 실행**: 동작 하나 → 전 라디오가 동시에 PULSE, 로그에 "N/N대 발사"와
   대별 **발사 관측 OK**
4. **무대**: `-rc` 프리셋 선택 → 시작. 발사 1.5초 전 PREP, 정각 FIRE, display 가
   같은 시각에 영상 재생. 영상이 끝나거나 추정 시간 + 5초 뒤 자동 종료
5. **정지**: 빨간 버튼 = 전 라디오에 VEL(locomotion 복귀) 펄스 + 무대 예약 취소

## 5. 안전

- 라디오 각각이 자기 로봇의 **물리 E-stop**(SC 하단 = Damping). 펄스 1초 구간 밖에서
  항상 우선이다. 라디오를 손 닿는 곳에 나란히 둔다
- PC/케이블이 죽으면 keepalive 끊김으로 **0.5초 내 물리 조종 복귀** (라디오별 독립)
- PC 는 CH1~4(스틱)·CH8(API arm)·CH12(E-stop)를 절대 건드리지 않는다

## 6. 문제 해결

| 증상 | 원인 / 조치 |
|---|---|
| 라디오가 0대 / 수가 모자람 | 케이블·전원 확인 → [USB 재탐색]. USB 허브면 허브 전원도 |
| "무응답"으로 표시 | 그 라디오의 VCP 가 CLI 다 (재부팅 후 리셋됨) 또는 K1PC 가 닫혀 있다 |
| 실행이 잠김(idle 안 풀림) | 완료 추정 시간(기본 30s) 대기 중. **정지 버튼**으로 즉시 해제 |
| 미믹이 1초 만에 끊김 | 그 라디오 **SB가 하단**(code 3) — 중앙으로 |
| 외부 기기에서 로그인 안 됨 | HTTP 로 띄웠다. `--https` 로 재시작 |
| 다이얼에 없는 동작 거부 | 로봇 다이얼 40슬롯에 없는 모션. 로봇 k1_config 갱신 필요 |

## 7. 상태 (2026-08-21)

- 라디오 2대 실측: **동시 발사 검증 완료** (전송 시각 차 <1ms, 양쪽 발사 관측 OK)
- **로봇 연결 실기는 아직** — 로봇 붙는 날 P2 절차(`../motion_llm/docs/RC_WIRED_COMMAND_PLAN.md`)
- 라디오 시리얼이 전 기기 동일(`00000000001B`)이라 **by-path(물리 포트)로 구분**한다
