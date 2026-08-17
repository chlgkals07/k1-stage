# motion_llm 상태 및 인수인계

갱신일: 2026-08-12

> **다음 세션에서 무엇을 할지**는 [NEXT_SESSION_CHECKLIST.md](NEXT_SESSION_CHECKLIST.md)를 본다.
> 이 문서는 "지금 무엇이 참인가"를 다룬다.

## 결론

현재 K1은 아이폰 음성 대화에서 **Omen PC relay를 거쳐 로봇에 무선으로 연결**되며, 음성 응답과 인사 동작까지 실물로 확인했다.

**LLM이 고를 수 있는 동작은 실물 검증된 3개뿐이다.**

| 의도 | state | 실물 확인 |
|---|---|---|
| 가벼운 인사·환영·작별 | `MimicWaveHand` | 확인됨 |
| 정중한 인사·감사 | `MimicBowNavel` | 확인됨 |
| 명시적인 체스트팝 요청 | `MimicBadChestpopVer2` | 확인됨 |

일반 질문은 음성으로만 답하고 동작을 요청하지 않는다. 동작 중 새 동작 요청은 거부하며, 완료 뒤 새 발화에서 같은 인사를 다시 요청하는 것은 확인됐다.

### 2026-08-12에 바뀐 것 — 전부 실물 검증 전이다

네 가지를 추가했고 코드 테스트 46개를 통과했으나, **어느 것도 로봇에서 확인하지 않았다.**
상세 경위는 [WORK_LOG_2026-08-12.md](WORK_LOG_2026-08-12.md)에 있다.

| 변경 | 요지 | 상태 |
|---|---|---|
| **운영자 정지** | 실행 중인 모션을 선점해 `ReadyPose`로 되돌린다. 이전에는 멈출 방법이 없었다 | 코드만 |
| **응답 길이·VAD·발사 시점** | `max_output_tokens`, `turn_detection` 설정, 모션을 `response.done` 대기 없이 발사 | 코드만 |
| **allowlist 확장** | `api_allowlist` 3 → **16** (운영자 수동 전용). `llm_allowlist`는 3 그대로 | 로봇 배포됨, 실행 미검증 |
| **`run.sh`** | 연결 절차 9단계 → 1명령. 토큰 고정으로 폰 URL 불변 | PC 검증만 |

**운영 경로를 건드린 변경이 둘(정지 선점, 발사 시점)이므로, 새 기능뿐 아니라
기존에 검증됐던 인사 3종 흐름도 다시 확인해야 한다.**

## 실제 통신 경로

```text
아이폰 (일반 Wi-Fi, HTTPS/WebRTC)
  → Omen PC: Realtime UI + OpenAI Realtime API + RelayBackend
  → PC Wi-Fi: k1-orinnx10
  → K1 robot gateway (HTTPS)
  → ROS 2 request_mode_by_name
  → ai_sapiens_sim2real / Mimic policy
```

PC는 인터넷용 유선 LAN과 로봇용 Wi-Fi를 동시에 사용한다. 아이폰은 로봇 AP에 직접 붙지 않는다. 확인했던 주소는 PC LAN `192.168.10.58`, PC robot Wi-Fi `192.168.60.77`, 로봇 gateway `192.168.60.1:8443`이다. DHCP 등으로 주소가 바뀔 수 있으므로 실행 전에는 `ip route get 192.168.60.1`로 확인한다.

## 저장소와 배포 위치

| 구분 | 위치 | 내용 |
|---|---|---|
| PC 작업본 | `shape3/motion_llm/` | HTTPS UI, Realtime, relay, gateway, 동작 카탈로그 |
| 로봇 실행본 | `/root/motion_llm/` | `server.py --robot`으로 실행하는 HTTPS/ROS gateway |
| 로봇 sim2real 소스 | `/root/ros2_ws` | API authority와 Mimic 실행 상태머신 |
| 이 저장소의 대응 소스 | `shape3/ai_sapiens_private/ai_sapiens_sim2real/` | 로봇에 적용·빌드한 변경의 관리본 |

`shape3`에는 이미 `motion_llm/`이 있으며, 별도 이름의 `llm_interaction/` 및 `rc_controller/` 디렉터리는 현재 작업공간에서 발견되지 않았다. 따라서 `rc_controller` 관련 작업은 이 문서와 소스에서 `motion_llm`의 robot gateway 및 `ai_sapiens_sim2real` 변경으로 추적한다.

## 로봇에 적용한 변경

2026-08-10에 로봇 `ai_sapiens_sim2real`의 K1 설정과 상태 전환 코드를 적용하고 빌드했다. K1 설정의 authority 항목은 다음과 같다.

```yaml
authority:
  api_entry:
    velocity_neutral_threshold: 0.05
    allow_non_neutral_teleop: true
  teleop_velocity_passthrough: true
```

- `allow_non_neutral_teleop`: RC 속도 입력이 0이 아니어도 API authority 전환을 허용한다.
- `teleop_velocity_passthrough`: `API_WARMUP`/`API`에서 물리 RC의 최신 velocity를 계속 쓴다.
- API cmd_vel의 중립 조건은 유지된다. heartbeat를 잃으면 zero velocity가 우선하고 Manual authority로 복귀한다.
- 코드·설정 테스트는 `test_state_machine_config` 12/12와 `test_mode_controller` 13/13, 합계 25/25를 통과했다.

배포 시 로봇 측 백업은 `/root/ros2_ws/api_passthrough_backup_20260810`이며, 개별 파일에는 `.bak_api_teleop_passthrough_20260810` suffix가 사용됐다. 이 기능은 실제 저속 locomotion에서 아직 검증 전이다. `ReadyPose/Velocity → API → Mimic`의 인사 동작 확인과 **비영 속도 locomotion 중 출력 연속성 확인은 별도 항목**으로 구분한다.

## 안전 경계

1. RC의 SD가 API Arm 물리 허가를 제공한다. SD OFF 또는 E-stop은 LLM/PC보다 우선한다.
2. PC relay와 robot gateway가 각각 allowlist를 검사한다.
3. **allowlist가 두 개고 서로 다르다** (`gateway_config.yaml`, 2026-08-12 변경):
   - `api_allowlist` **16개** — gateway가 실행을 허용하는 전부. 운영자 수동 버튼이 여기서 나온다
   - `llm_allowlist` **3개** — 그중 모델이 스스로 고를 수 있는 것

   사람이 E-stop을 두고 버튼으로 부르는 것과 모델이 대화 중 고르는 것은 위험도가 다르다.
   승격 경로는 로드맵 §3.2의 "수동 전용으로 먼저 검증 후 LLM 개방"이다.
   `motions.yaml`의 더 넓은 카탈로그는 이 allowlist 없이는 운영 권한을 얻지 못한다.
4. gateway는 heartbeat, API authority, mode readiness를 확인한 뒤에만 `request_mode_by_name`을 호출한다.
   **단 정지(`stop_motion`)는 예외**로 allowlist·busy·cooldown과 `request_available`을 우회한다 —
   Mimic 실행 중 이 플래그가 내려가면 정지가 거부되어 기능이 무의미해지기 때문이다.
   이 가정은 아직 실물로 확인되지 않았다.
5. 정지는 LLM에 노출하지 않는다. 음성 왕복이 1.5~3초라 정지 수단으로 부적합하다.
   즉시 탈출은 RC Damping / E-stop이 담당한다.
5. API key와 token은 PC의 `~/.k1/secrets.env`(chmod 600, 리포지토리 밖)에만 둔다.
   문서·Git·채팅에 저장하지 않는다. 2026-08-12부터 토큰은 고정이다 —
   [INTERACTION_EXPANSION_ROADMAP.md](INTERACTION_EXPANSION_ROADMAP.md) §7의 변경 사유를 참고한다.

## 재현 가능한 실행 순서

2026-08-12부터 `run.sh`가 대부분을 대신한다. 상세는 [CEREMONY_RUNBOOK.md](CEREMONY_RUNBOOK.md).

1. 로봇 컨테이너에서 `go`로 ROS bringup을 실행하고 RC/E-stop 상태를 확인한다.
   **이건 사람이 한다** — 로봇이 물리 상태에 진입하므로 자동화하지 않는다.
2. PC를 유선 인터넷과 `k1-orinnx10` Wi-Fi에 함께 연결한다.
3. PC에서 `./run.sh`. 네트워크·컨테이너·ROS·파일 md5·gateway를 점검하고 relay까지 띄운다.
4. 아이폰은 일반 Wi-Fi에서 출력된 HTTPS URL로 접속한다. **토큰이 고정이라 북마크가 계속 동작한다.**
5. 주변을 비운 뒤 SD를 OFF → ON, 약 3초 warm-up 후 UI의 API 준비 상태를 확인한다.
6. 먼저 “안녕”으로 손 흔들기를 검증한다.
7. 종료는 `./run.sh --stop` 후 SD OFF, Manual 복귀 확인.

로봇 실행본은 **호스트가 아니라 `ai_sapiens` 도커 컨테이너 안** `/root/motion_llm/`에 있다.
`run.sh`가 PC↔로봇 파일 md5를 대조하므로 배포 누락은 자동으로 잡힌다
(`--deploy`로 동기화). 이 경로에서 실제로 두 번 사고가 났다 —
[WORK_LOG_2026-08-12.md](WORK_LOG_2026-08-12.md) 참고.

## 완료와 남은 검증을 분리

### 완료

- PC↔로봇 AP 무선 연결과 PC relay→robot gateway 통신
- 아이폰→PC relay→로봇의 end-to-end 모션 요청
- OpenAI Realtime 음성 응답 및 “안녕” 인사 동작
- 로봇 API heartbeat/authority 전환과 3개 허용 Mimic 동작의 실물 확인
- 동작 완료 후 동일 인사 재실행
- Mimic policy 실행 도중 중단 시 약한 전환 튐은 있었으나 안정적으로 복귀함

### 실물 검증이 남은 항목

#### 운영자 정지 (2026-08-12 추가, 최우선)

코드는 들어갔고 단위 테스트 28개를 통과했으나 **실물 확인 전이다.**

1. `ReadyPose`가 로봇 `list_modes`에 실제로 있는지 — 없으면 정지 대상을 다시 골라야 한다.
2. 유휴 상태에서 정지 버튼 → ReadyPose 진입.
3. `MimicWaveHand` 실행 중 정지. **핵심 관찰점은 Mimic 실행 중 `api_request_available`가
   true로 유지되는지 여부다.** false로 내려간다면 일반 요청 경로는 막히지만, 정지 경로는
   이 플래그를 의도적으로 검사하지 않도록 설계했으므로 그래도 통과해야 한다.
4. 정지 후 전환 튐 정도와 안정 복귀 시간 기록. 기존에 관찰된 "중단 시 약한 전환 튐"은
   **API 경로로 유발된 중단인지 확인되지 않았다.**
5. 정지 직후 새 모션 요청이 정상 처리되는지.
6. `MimicBadChestpopVer2` 연속 요청 시 8초 cooldown 거부 메시지.
7. 회귀 확인: 인사 3종의 "새 발화에서 같은 동작 재실행"이 여전히 되는지.

#### Locomotion ↔ API 연속성

`teleop_velocity_passthrough`는 로봇 배포·빌드와 하드웨어 비연결 테스트 25/25까지 끝났으나
실제 움직임에서는 미검증이다. 상세 절차는
[INTERACTION_EXPANSION_ROADMAP.md](INTERACTION_EXPANSION_ROADMAP.md) §5의 단계 A/B/C를 따른다.

- 비영 속도 locomotion 중 API authority 전환 시 속도 discontinuity
- 이동 중 Mimic 진입·종료의 출력 연속성, Mimic 진입 전 감속 시간
- Mimic 완료 후 최신 RC 속도 복귀 (단계 C — 스틱 중립 강제 전제)
- heartbeat / PC Wi-Fi 손실 시 정지와 Manual 복귀까지 걸리는 시간

#### 운영 안정성

- 30분 무선 soak test와 AP 재연결 시험
- PC relay·robot gateway 재시작 절차 3회 반복 성공
- E-stop 담당자와 종료 절차 리허설
- 전환 튐의 정량 측정과 완화 (관찰은 됐으나 수치화 전)

완료 기준 전체는 [INTERACTION_EXPANSION_ROADMAP.md](INTERACTION_EXPANSION_ROADMAP.md) §9를 따른다.

