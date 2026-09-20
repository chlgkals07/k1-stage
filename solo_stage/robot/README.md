# 로봇 적용 소스 안내

이 폴더는 로봇에 들어가는 큰 ROS 패키지를 중복 복사하지 않고, 관리본과 배포 위치를 명확히 연결한다.

## 관리본과 배포본

- 관리본: `../../ai_sapiens_private/ai_sapiens_sim2real/` (약 145 MB, 전체 ROS 패키지)
- 로봇 배포본: `/root/ros2_ws`의 같은 패키지와 설치 산출물

## 이번 API/locomotion 변경 관련 파일

| 관리본 상대 경로 | 역할 |
|---|---|
| `config/k1_config.yaml` | `allow_non_neutral_teleop`, `teleop_velocity_passthrough` 활성화 |
| `src/config/root_config.cpp` | YAML authority 옵션 파싱 |
| `src/mode_runtime/authority_runtime.cpp` | API 진입 시 non-neutral RC 정책 |
| `src/controllers/mode_controller.cpp` | API/API_WARMUP의 teleop velocity passthrough |
| `include/ai_sapiens_sim2real/config/authority_config.hpp` | authority 설정 구조체 |
| `include/ai_sapiens_sim2real/mode_runtime/authority_runtime.hpp` | authority runtime API |
| `test/test_state_machine_config.cpp` | 설정 파싱 테스트 |
| `test/test_mode_controller.cpp` | 전환·heartbeat 우선순위 테스트 |

## 운영 원칙

