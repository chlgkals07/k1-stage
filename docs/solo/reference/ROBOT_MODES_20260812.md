# 로봇 실측 모드 목록 (2026-08-12)

`/ai_sapiens/list_modes`를 실제로 호출해 받은 결과다. **로봇이 무엇을 실행할 수 있는지에 대한
유일한 신뢰 가능한 출처다.**

```bash
ssh root@192.168.55.1
docker exec ai_sapiens bash -lc "
  source /opt/ros/jazzy/setup.bash
  source /root/ros2_ws/install/setup.bash
  ros2 service call /ai_sapiens/list_modes ai_sapiens_sim2real/srv/ListModes '{}'"
```

## ⚠️ 관리본 `k1_config.yaml`을 믿지 말 것

`ai_sapiens_private/ai_sapiens_sim2real/config/k1_config.yaml`의 RC 다이얼 슬롯 목록에는
`MimicSquat`, `MimicBillyJean`, `MimicOmbrinho`, `MimicPara`, `MimicAiming`, `Mimicggang_*`,
`MimicRedRed*` 등이 들어 있는데, **아래 실측 목록에는 이 중 어느 것도 없다.**
관리본이 로봇 배포본보다 뒤처져 있다. 모드 목록이 필요하면 관리본이 아니라 `list_modes`를 쓴다.

관리본 동기화는 별도 작업으로 남아 있다.

## 실측 결과 — 24개

`success: True`, `modes`에 24개, **`available_modes`는 빈 배열**이었다.
`robot_backend.py:_on_list_modes`가 `response.available_modes or response.modes`로
fallback하므로 정상 동작한다.

### 제어 상태 (4)

| state | API 개방 | 비고 |
|---|---|---|
| `Damping` | ✗ | RC의 즉시 탈출구. 소프트웨어 버튼을 두면 비상정지로 착각할 위험 |
| `ReadyPose` | 정지 대상 | `gateway_config.yaml`의 `stop_state` |
| `Velocity` | ✗ | 보행 활성 상태 |
| `ZeroPose` | ✗ | `k1_config.yaml`의 `api_entry.allowed_from_states`에 없어 의미 불분명 |

### Mimic (20) — 16개 개방, 4개 제외

| state | 카탈로그 | api_allowlist | 비고 |
|---|---|---|---|
| `MimicWaveHand` | ○ | ✓ | 실물 검증 완료 |
| `MimicBowNavel` | ○ | ✓ | 실물 검증 완료 |
| `MimicBadChestpopVer2` | ○ | ✓ | 실물 검증 완료, cooldown 8초 |
| `MimicAnseKabanse` | **신규** | ✓ | 놀이 제스처, 제자리 |
| `MimicBeckon` | ○ | ✓ | status 불일치 (아래 참조) |
| `MimicBodyStretch` | **신규** | ✓ | 스트레칭, 제자리 |
| `MimicBossDustBrushingNew` | **신규** | ✓ | `horizontal_move: 1` |
| `MimicBossDustBrushingR001A036` | **신규** | ✓ | `horizontal_move: 1` |
| `MimicBow` | **신규** | ✓ | **앞으로 한 발 내딛음** |
| `MimicBravo` | ○ | ✓ | status 불일치 |
| `MimicCoinPick` | ○ | ✓ | 로드맵 §3.2 수동 검증 대상 |
| `MimicDanceBasicTurnV1360RLoopFast003A325` | ○ | ✓ | 회전, 로드맵 §3.2 |
| `MimicDeepDab001A467` | **신규** | ✓ | 로드맵 §3.1 후보 |
| `MimicGuapIntroP2` | **신규** | ✓ | 로드맵 §3.1 후보. seed 데이터 없음 |
| `MimicGuapVer2` | ○ | ✓ | 로드맵 §3.2 |
| `MimicShuffleDance` | ○ | ✓ | 로드맵 §3.2 |
| `MimicBoxingNewton` | ○ | **✗** | restricted |
| `MimicCartwheel` | ○ | **✗** | restricted, 옆돌기 |
| `MimicShadowBoxing` | ○ | **✗** | restricted |
| `MimicWalk1Subject1` | ○ | **✗** | RC locomotion과 역할 충돌 |

**개방 = 운영자 수동 버튼 전용이다.** `llm_allowlist`는 실물 검증된 3개 그대로다.

## 알려진 불일치 — 이번에 고치지 않음

`MimicBeckon`, `MimicBravo`, `MimicCartwheel`은 `motions.yaml`에서 `status: planned`(미학습)인데
**로봇에는 실제로 로드돼 있다.** 카탈로그의 `status`는 BONES-SEED 학습 backlog 기준이라
로봇 배포 상태와 다른 축이다.

`status`를 `ready`로 바꾸면 나중에 `llm_allowlist`를 넓힐 때 이 셋이 자동으로 딸려 들어올 수
있어 이번에는 데이터를 건드리지 않았다. 별도 판단이 필요하다.

## 신규 카탈로그 항목의 출처

`desc`는 추측이 아니라 `seed/metadata/seed_metadata_v004.csv`의
`content_short_description` / `content_natural_desc_1` / `content_horizontal_move`에서 가져왔다.

| state | seed move_name |
|---|---|
| `MimicBow` | `bow_R_001__A428` |
| `MimicBossDustBrushing*` | `boss_dust_brushing_R_001__A405` |
| `MimicAnseKabanse` | `anse_kabanse_R_001__A456` |
| `MimicBodyStretch` | `body_stretch_v001_001__A359` |
| `MimicDeepDab001A467` | `dance_deep_dab_001__A464` |
| `MimicGuapIntroP2` | **대응 없음** — 로드맵 §3.1 기술만 근거 |

## 그 밖에 확인된 것

- `mimic_defaults.on_complete: Velocity` — Mimic 완료 시 Velocity로 복귀한다.
  `gateway.py`의 `COMPLETION_MODES`가 이와 맞다.
- `authority.api_entry.allowed_from_states: [Damping, ReadyPose, Velocity]`,
  `warmup_duration: 3.0`
- `mimic_defaults.fps: 50`
- 컨테이너 시계가 약 11일 느리다 (실측 시점 Aug 1). `time.monotonic()` 기반이라
  heartbeat·cooldown·timeout에는 영향 없고 로그 타임스탬프만 어긋난다.
- `solo_stage` 실행본은 호스트가 아니라 **`ai_sapiens` 도커 컨테이너 안** `/root/motion_llm/`에 있다.
