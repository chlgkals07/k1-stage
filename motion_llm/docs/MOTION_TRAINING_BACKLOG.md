# Motion Training Backlog

이 문서는 `motion_llm`에서 다음 학습 대상으로 관리할 BONES-SEED 동작 목록을 정리한다. 현재 목록은 동작 카탈로그와 학습 backlog이며, 실 로봇 runtime allowlist가 아니다.

## 현재 결론

- 사용자 제공 A-H 목록은 [../motions.yaml](../motions.yaml)에 `status: planned` 카탈로그로 이미 반영되어 있다.
- `slap_R_001__A457`와 `Kozakiewicz_gesture_stadium_002__A044`는 운영/학습 대상에서 제외한다.
- 운영 제외 2개를 뺀 59개는 모두 [../../seed/metadata/seed_metadata_v004.csv](../../seed/metadata/seed_metadata_v004.csv)에 metadata가 있다.
- 59개 모두 BVH 원본 파일이 [../../seed/soma_uniform/bvh](../../seed/soma_uniform/bvh) 아래에 존재한다.
- metadata의 `move_g1_path`는 있지만 현재 workspace의 `seed/g1/csv` 파일은 확인되지 않았다. 학습 전처리에서 G1 CSV를 새로 만들거나 기존 변환 산출 위치를 찾아야 한다.
- 현재 실 로봇 LLM/API allowlist는 [../gateway_config.yaml](../gateway_config.yaml)의 3개 검증 동작만 유지한다.
- 전체 59개 worklist CSV: [MOTION_TRAINING_WORKLIST.csv](MOTION_TRAINING_WORKLIST.csv)
- 1차 학습 cohort: [MOTION_TRAINING_COHORT_01.md](MOTION_TRAINING_COHORT_01.md), [MOTION_TRAINING_COHORT_01.csv](MOTION_TRAINING_COHORT_01.csv)
- runtime catalog의 `training_backlog`: [../motions.yaml](../motions.yaml)

현재 runtime allowlist:

```yaml
api_allowlist:
  - MimicWaveHand
  - MimicBowNavel
  - MimicBadChestpopVer2
llm_allowlist:
  - MimicWaveHand
  - MimicBowNavel
  - MimicBadChestpopVer2
```

## Source Of Truth

| 대상 | 파일 | 역할 |
|---|---|---|
| LLM 동작 카탈로그 | [../motions.yaml](../motions.yaml) | state 이름, 한국어 이름, 설명, tag, safety, planned 여부 |
| 로봇/PC allowlist | [../gateway_config.yaml](../gateway_config.yaml) | 실제 호출 허용 동작 |
| seed metadata | [../../seed/metadata/seed_metadata_v004.csv](../../seed/metadata/seed_metadata_v004.csv) | `move_name`에서 실제 BVH 경로로 가는 원본 매핑 |
| BVH 원본 | [../../seed/soma_uniform/bvh](../../seed/soma_uniform/bvh) | BONES-SEED 원본 모션 |
| ceremony subset | [../../seed/ceremony_pack/manifest.csv](../../seed/ceremony_pack/manifest.csv) | 일부 선별 모션만 들어 있는 작은 pack |

중요한 기준은 metadata의 `move_soma_uniform_path`다. 일부 동작은 사용자가 준 `move_name`과 실제 BVH 파일 stem이 다르므로 파일명 stem만으로 찾으면 누락처럼 보인다.

## 목록 규모

| 구분 | 개수 | 상태 |
|---|---:|---|
| 사용자 제공 전체 | 61 | A-H 원본 목록 |
| 운영/학습 제외 | 2 | `slap_R_001__A457`, `Kozakiewicz_gesture_stadium_002__A044` |
| 학습 backlog | 59 | metadata/BVH 확인 완료 |
| `motions.yaml` planned 전체 | 70 | A-H 59개 + 추가 고난도/운동 후보 |

## Slot 메모

| Slot | 후보 |
|---:|---|
| 1 | `MimicIdleBase` |
| 5/6 | `MimicWelcoming` |
| 7 | `MimicByeBye` |
| 8 | `MimicPresentLeft` |
| 9 | `MimicPresentRight` |
| 12 | `MimicHighFive` |
| 13 | `MimicBravo` |
| 14 | `MimicCrowdCheer` |
| 16 | `MimicTheRing` 대체 후보 |
| 17 | `MimicJumpForJoy` |
| 18 | 짧은 dance 후보 |
| 20 | `MimicBicepCheck` |
| 21 | 오프닝 dance 재료 |

Slot은 RC/UI 배치 메모다. 실 로봇에 올릴 때는 학습 완료, offline 평가, 단독 실기 검증 후에만 `gateway_config.yaml`로 승격한다.

## Metadata Alias Mapping

아래 13개는 `move_name`으로 metadata 검색은 가능하지만 실제 BVH 파일 stem이 다르다. 학습 파이프라인은 `move_name`을 파일 stem으로 가정하지 말고 `move_soma_uniform_path`를 따라가야 한다.

| Catalog seed | Actual BVH stem |
|---|---|
| `idle_hands_on_back_loop_R_001__A029` | `idle_hands_on_back_loop_001__A029` |
| `body_stretch_opt_1_001__A029` | `body_stretch_1_001__A029` |
| `present_right_R_001__A428` | `desperate_prayer_R_002__A428` |
| `point_dir_horizontal_right_hand_315_head_front_R_004__A031` | `point_direction_horizontal_right_hand_315_head_front_004__A031` |
| `high_five_crowd_R_001__A432` | `hifive_crowd_R_001__A432` |
| `kissing_hands_thanks_stadium_001__A042` | `m_kissing_hands_thanks_stadium_001__A042` |
| `just_realized_R_001__A185` | `just_realised_R_001__A185` |
| `boss_dust_brushing_R_001__A036` | `boss_dust_brushing_001__A036` |
| `tarzan_R_001__A098` | `tarzan_001__A098` |
| `dance_gunslinger_smokeshow_001__A464` | `dance_hit_it_002__A464` |
| `dance_ninja_style_003__A464` | `ninja_style_003__A464` |
| `dance_vogue_dancehall_open_close_270_R_001__A316` | `dance_vouge_dancehall_open_close_270_R_001__A316` |
| `dance_vogue_shake_it_babe_180_R_fast_001__A316` | `dance_vouge_shake_it_babe_180_R_fast_001__A316` |

`present_right_R_001__A428`의 실제 경로가 `desperate_prayer_R_002__A428`로 잡히는 것은 이름상 이상하다. 학습 전에 영상/pose preview로 의미가 맞는지 반드시 확인한다.

## 1차 학습 후보

첫 cohort는 연구 데모 품질을 빨리 올리는 안전한 상호작용 동작 위주로 잡는다. 접촉, 점프, 큰 회전, 긴 댄스는 뒤로 미룬다.

| 우선순위 | State | Seed | 이유 |
|---:|---|---|---|
| 1 | `MimicListening` | `listening_R_001__A116` | 대화 중 idle 반응 |
| 2 | `MimicCasualGreeting` | `casual_greeting_R_001__A428` | 가벼운 인사 |
| 3 | `MimicWelcoming` | `welcoming_001__A142` | 맞이 시나리오 핵심 |
| 4 | `MimicBowPolite` | `bow_R_001__A429` | 정중한 응대 |
| 5 | `MimicByeBye` | `bye_bye_salute_R_002__A474` | 배웅 |
| 6 | `MimicComeHere` | `come_here_R_002__A456` | 안내/호출 |
| 7 | `MimicPresentLeft` | `present_left_R_001__A428` | 방향 안내 |
| 8 | `MimicCalmDown` | `calm_down_R_001__A432` | 제지/안정화 |
| 9 | `MimicBravo` | `bravo_R_001__A431` | 호응/칭찬 |
| 10 | `MimicIGotThis` | `i_got_this_001__A101` | 자신감/응답 캐릭터 |

`MimicPresentRight`는 slot상 중요하지만 metadata alias가 이상하므로 preview 확인 후 1차 cohort에 넣는다.

## 후순위 그룹

| 그룹 | 예시 | 이유 |
|---|---|---|
| 접촉 | `MimicHighFive`, `MimicSseSseSse`, `MimicAirplane` | 사람 접촉/거리 안전 검증 필요 |
| 빠른 전신 | `MimicJumpForJoy`, `MimicFancySpin`, `MimicBicepCheck` | 균형, yaw, 정지 복귀 확인 필요 |
| 댄스 | H 전체 | 길이 trimming, 속도, foot slip, 종료 pose 설계 필요 |
| 운영 제외 | `slap_R_001__A457`, `Kozakiewicz_gesture_stadium_002__A044` | 배포 부적합 |

## 다음 작업 순서

1. [MOTION_TRAINING_WORKLIST.csv](MOTION_TRAINING_WORKLIST.csv)에서 59개 motion의 `move_soma_uniform_path`, duration, category, natural description을 확인한다.
2. 13개 alias 항목은 preview로 실제 의미를 확인한다. 특히 `present_right_R_001__A428`은 우선 검수한다.
3. 1차 10개 cohort를 retarget/train 대상으로 고정한다.
4. offline 평가에서 tracking, foot contact, joint limit, 종료 pose, recovery를 본다.
5. 실 로봇 단독 검증 후 `status: trained` 또는 `robot_verified`로 승격한다.
6. 승격된 동작만 [../gateway_config.yaml](../gateway_config.yaml)의 API/LLM allowlist에 추가한다.
