# robot — ai_sapiens 실기 변경분

`k1-stage`의 세 앱(`solo_stage` · `group_stage` · `rc_link`)이 명령을 보내는 **로봇 쪽 짝**이다.
상류는 ROBOTIS의 `ai_sapiens_private`이고, 여기에는 **shape3에서 바꾼 부분만** 둔다.
로봇 전체 소스나 정책 자산(`assets/` 132MB)은 들어 있지 않다.

## 구성

| 경로 | 내용 |
|---|---|
| `current/` | 변경 후 (실제로 로봇에 빌드해 올린 상태) |
| `baseline/` | 변경 직전 PC 작업본 — 각 파일의 `.bak` 에서 복원 |
| `baseline/robot_snapshot_20260805/` | **별개 기준선.** 2026-08-05 17:19 로봇에서 그대로 뜬 config 2종 |
| `changes.patch` | `baseline` → `current` 통합 diff (575줄) |

`baseline/`과 `robot_snapshot_20260805/`는 **같지 않다.** 전자는 PC 작업본이 편집되기
직전 상태(16:37)이고, 후자는 같은 날 로봇에 실제로 올라가 있던 상태(17:19)로 모션
목록이 서로 다르다. 변경분을 읽을 때의 기준은 `baseline/`이다.

## 무엇을 바꿨나

### ① RC 버튼 뱅크 확장 (2026-08-05, 152줄)

`config/k1_config.yaml` · `config/teleop/radiomaster_pocket.yaml`

동작 슬롯을 **10개에서 26개로** 늘렸다. 기존 `mimic_selector`(뱅크 A)는 그대로 두고
`mimic_selector_b`(L1 홀드)와 `mimic_selector_c`(R1 홀드)를 더해, 조종기 버튼 조합으로
같은 다이얼에서 세 뱅크를 고르게 했다.

- 뱅크 A — 버튼 안 누름. 기존 배치 유지
- 뱅크 B — L1 홀드. 그때까지 안 쓰이던 자산들
- 뱅크 C — R1 홀드. 같은 동작의 다른 테이크(A/B 비교용)

### ② API 권한과 텔레옵 패스스루 (2026-08-10, ~180줄)

`authority_config.hpp` · `authority_runtime.{hpp,cpp}` · `mode_controller.cpp` ·
`root_config.cpp` · 테스트 2종

```yaml
authority:
  api_entry:
    velocity_neutral_threshold: 0.05
    allow_non_neutral_teleop: true
  teleop_velocity_passthrough: true
```

- `allow_non_neutral_teleop` — RC 속도 입력이 0이 아니어도 API 권한 전환을 허용한다
- `teleop_velocity_passthrough` — `API_WARMUP`/`API` 상태에서도 물리 RC의 최신 velocity를 계속 쓴다
- heartbeat를 잃으면 zero velocity가 우선하고 Manual 권한으로 복귀하는 규칙은 그대로다

테스트는 `test_state_machine_config` 12/12, `test_mode_controller` 13/13 통과.
**저속 locomotion 중 출력 연속성은 실기 미검증**이다.

## 적용 방법

```bash
git apply --directory=<ai_sapiens_private 체크아웃>/ai_sapiens_sim2real changes.patch
```

로봇에 올릴 때는 `colcon build` 한 번이 필요하다. 새 정책 자산을 같이 넣는다면
`params/` 전체(csv + sim2real.yaml)를 복사해야 한다 — csv만 넣으면 bringup이
`sim2real_yaml missing file`로 죽는다.

## 관련 문서

- 뱅크 구성과 슬롯표: `../docs/`의 RC 문서
- 권한 인계 시 로봇 거동: `../solo_stage/docs/FINAL_REVIEW_2026-08-18.md` §0
