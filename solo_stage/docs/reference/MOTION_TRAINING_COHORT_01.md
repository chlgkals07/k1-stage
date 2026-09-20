# Motion Training Cohort 01

목표는 실 로봇 테스트 전에 대화형 K1의 기본 상호작용 품질을 올리는 것이다. 이 cohort는 접촉, 점프, 큰 회전, 긴 댄스를 제외하고 안전한 상체/제자리 응답 위주로 고른다.

## Files

- 전체 backlog: [MOTION_TRAINING_BACKLOG.md](MOTION_TRAINING_BACKLOG.md)
- 전체 worklist: [MOTION_TRAINING_WORKLIST.csv](MOTION_TRAINING_WORKLIST.csv)
- 이 cohort CSV: [MOTION_TRAINING_COHORT_01.csv](MOTION_TRAINING_COHORT_01.csv)
- runtime catalog: [../motions.yaml](../../motions.yaml)

## Cohort

| Priority | State | KO | Seed | Frames | BVH |
|---:|---|---|---|---:|---|
| 1 | `MimicListening` | 듣는 자세 | `listening_R_001__A116` | 443 | `seed/soma_uniform/bvh/230112/listening_R_001__A116.bvh` |
| 2 | `MimicCasualGreeting` | 캐주얼 인사 | `casual_greeting_R_001__A428` | 490 | `seed/soma_uniform/bvh/230713/casual_greeting_R_001__A428.bvh` |
| 3 | `MimicWelcoming` | 어서오세요 | `welcoming_001__A142` | 693 | `seed/soma_uniform/bvh/230124/welcoming_001__A142.bvh` |
| 4 | `MimicBowPolite` | 정중한 인사 | `bow_R_001__A429` | 693 | `seed/soma_uniform/bvh/230713/bow_R_001__A429.bvh` |
| 5 | `MimicByeBye` | 배웅 인사 | `bye_bye_salute_R_002__A474` | 370 | `seed/soma_uniform/bvh/231010/bye_bye_salute_R_002__A474.bvh` |
| 6 | `MimicComeHere` | 이리 오세요 | `come_here_R_002__A456` | 480 | `seed/soma_uniform/bvh/231004/come_here_R_002__A456.bvh` |
| 7 | `MimicPresentLeft` | 왼쪽 안내 | `present_left_R_001__A428` | 670 | `seed/soma_uniform/bvh/230713/present_left_R_001__A428.bvh` |
| 8 | `MimicCalmDown` | 진정하세요 | `calm_down_R_001__A432` | 802 | `seed/soma_uniform/bvh/230713/calm_down_R_001__A432.bvh` |
| 9 | `MimicBravo` | 정중한 박수 | `bravo_R_001__A431` | 1058 | `seed/soma_uniform/bvh/230713/bravo_R_001__A431.bvh` |
| 10 | `MimicIGotThis` | 나만 믿어 | `i_got_this_001__A101` | 393 | `seed/soma_uniform/bvh/230103/i_got_this_001__A101.bvh` |

## Gate

각 motion은 아래 순서를 통과해야 `gateway_config.yaml` allowlist로 승격한다.

1. BVH preview로 의미와 시작/종료 pose 확인
2. 필요하면 앞뒤 trim 및 ReadyPose 복귀 구간 정의
3. retarget 산출물 생성
4. train 실행
5. offline 평가: tracking, foot contact, joint limit, recovery 확인
6. 실 로봇 단독 실행
7. `motions.yaml`에서 `status` 승격 후 `gateway_config.yaml` allowlist 반영

## Notes

- `MimicPresentRight`는 slot상 중요하지만 `present_right_R_001__A428`의 실제 BVH stem이 `desperate_prayer_R_002__A428`로 잡혀 있다. preview 확인 전에는 이 cohort에 넣지 않는다.
- planned 동작은 PC/mock 대화 검증에는 보일 수 있지만, robot/relay 실행은 `--ready-only`와 gateway allowlist로 제한한다.
