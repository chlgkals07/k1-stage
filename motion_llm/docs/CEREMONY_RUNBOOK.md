# K1 개소식 실행 가이드

이 문서는 현장에서 그대로 따라 하기 위한 짧은 실행 절차다.

## 빠른 경로 — `./run.sh`

로봇에서 ROS bringup만 사람이 띄우고, 나머지는 스크립트가 한다.

```bash
# 1. 로봇에서 (사람이 직접 — 로봇이 물리 상태에 진입하므로 자동화하지 않는다)
ssh root@192.168.55.1
docker exec -it ai_sapiens bash
go

# 2. PC에서
cd /home/robotis-ai/Projects/shape3/motion_llm
./run.sh
```

`run.sh`가 순서대로 확인한다: SSH 경로 → 컨테이너 → **ROS bringup** → PC↔로봇 파일 md5 →
gateway 기동(이미 떠 있으면 재사용) → relay 경로 → 폰 URL 출력 → PC relay 실행.

| 명령 | 용도 |
|---|---|
| `./run.sh` | 점검 + gateway + relay |
| `./run.sh --deploy` | 위 + PC→로봇 파일 동기화 (백업 후) |
| `./run.sh --status` | 상태만 확인. 아무것도 시작하지 않는다 |
| `./run.sh --stop` | relay·gateway 정리 |

**폰 URL은 토큰이 고정이라 매번 같다. 한 번 북마크하면 다음부터는 탭 한 번이다.**
비밀값은 `~/.k1/secrets.env`(chmod 600)에 있고 첫 실행 때 만들어진다.

무엇이 잘못됐는지 알아야 하거나 스크립트를 못 쓰는 상황이면 아래 수동 절차를 따른다.

---

## 수동 절차 (폴백)

## 목표 구조

```text
아이폰(일반 Wi-Fi)
→ Omen PC(유선 인터넷)
→ PC Wi-Fi(k1-orinnx10)
→ 로봇 gateway
→ 검증된 Mimic 3종
```

## 1. 로봇 켜기

로봇에서:

```bash
go
```

ROS 상태 확인:

```bash
ros2 node list | grep -E 'sim2real|rc|controller'
ros2 topic echo /ai_sapiens/mode_status --once
```

## 2. 로봇 gateway 실행

로봇 컨테이너에서:

```bash
cd /root/motion_llm

python3 server.py \
  --robot \
  --https \
  --port 8443 \
  --ready-only
```

출력된 robot gateway token을 복사한다.

> 운영 중에는 별도의 `api_arm_probe.py`를 같이 실행하지 않는다.

## 3. PC 네트워크 확인

- PC 유선 LAN: 일반 인터넷
- PC Wi-Fi: `k1-orinnx10`
- 아이폰 Wi-Fi: 일반 Wi-Fi

PC에서:

```bash
nmcli -t -f DEVICE,STATE,CONNECTION device status
ip route get 192.168.60.1
```

정상 로봇 경로:

```text
192.168.60.1 dev wlp128s20f3 src 192.168.60.77
```

gateway 확인:

```bash
curl --interface wlp128s20f3 -k \
  -o /dev/null -sS -w '%{http_code}\n' \
  https://192.168.60.1:8443/
```

`403`이면 정상이다. token 인증이 필요한 살아 있는 서버라는 뜻이다.

## 4. PC에 비밀값 입력

Omen PC에서:

```bash
cd /home/robotis-ai/Projects/shape3/motion_llm

read -rsp "OpenAI API key: " OPENAI_API_KEY
echo
export OPENAI_API_KEY

read -rsp "Robot gateway token: " K1_RELAY_TOKEN
echo
export K1_RELAY_TOKEN
```

확인:

```bash
test -n "$OPENAI_API_KEY" && echo 'OpenAI key OK' || echo 'OpenAI key MISSING'
test -n "$K1_RELAY_TOKEN" && echo 'Robot token OK' || echo 'Robot token MISSING'
```

## 5. PC relay 실행

```bash
python3 server.py \
  --relay https://192.168.60.1:8443 \
  --https \
  --port 18444 \
  --ready-only
```

다음 경고가 나오면 음성 기능이 안 된다.

```text
OPENAI_API_KEY가 없습니다
```

## 6. 아이폰 연결

아이폰은 일반 Wi-Fi에 연결한다. PC 출력에 나온 token을 사용한다.

```text
https://192.168.10.58:18444/?token=<PC_UI_TOKEN>
```

인증서 경고가 나오면 고급 메뉴에서 계속한다.

## 7. 로봇 API 준비

1. 로봇 주변을 비운다.
2. RC와 E-stop 상태를 확인한다.
3. SD를 OFF → ON으로 전환한다.
4. 약 3초 기다린다.
5. 아이폰 UI에서 `API 준비됨`을 확인한다.

## 8. 음성 테스트

1. 아이폰에서 음성 연결 버튼을 누른다.
2. 마이크 권한을 허용한다.
3. “안녕”이라고 말해 손 흔들기를 확인한다.
4. 동작 완료와 `ready` 복귀 뒤 다시 “안녕”이라고 말해 반복 실행을 확인한다.
5. “정중하게 인사해줘”로 배꼽 인사를 확인한다.
6. “체스트팝 보여줘”로 체스트팝을 확인한다.
7. 일반 질문에는 불필요한 모션이 나오지 않는지 확인한다.

현재 LLM 허용 동작:

```text
MimicWaveHand
MimicBowNavel
MimicBadChestpopVer2
```

## 8.5 정지 버튼

`/operator` 상단의 빨간 **정지** 버튼은 실행 중인 Mimic을 중단하고 로봇을 `ReadyPose`로
되돌린다. 수동 모션 버튼과 달리 **실행 중에도 잠기지 않는다.**

역할 구분을 지킨다.

| 수단 | 용도 | 우선순위 |
|---|---|---|
| RC Damping / E-stop | 즉시 탈출. 물리 안전장치 | 최상위 — 항상 API보다 우선 |
| `/operator` 정지 버튼 | "지금 이 동작만 멈춰". 운영 중 일상적 중단 | API 경로 |
| 음성 "멈춰" | **열려 있지 않다.** LLM 왕복이 1.5~3초라 정지 수단으로 부적합 | — |

위험 상황에서는 버튼이 아니라 **RC Damping 또는 E-stop을 쓴다.**

첫 실물 세션에서는 [STATUS_AND_HANDOVER.md](STATUS_AND_HANDOVER.md)의
"운영자 정지" 검증 7항목을 순서대로 확인한다.

## 9. 종료

1. 아이폰 음성 연결 종료
2. PC server에서 `Ctrl-C`
3. 로봇 gateway 종료
4. SD OFF
5. 로봇이 Manual 상태인지 확인

```bash
ros2 topic echo /ai_sapiens/mode_status --once
```

## 문제 해결

### 폰 링크가 안 열림

```bash
ip -br addr show enp129s0
```

아이폰과 PC 일반 LAN이 같은 대역인지 확인한다. PC 주소가 바뀌면 URL의 `192.168.10.58`도 바꾼다.

### 로봇이 offline으로 표시됨

```bash
nmcli -t -f DEVICE,STATE,CONNECTION device status
ip route get 192.168.60.1
curl --interface wlp128s20f3 -k https://192.168.60.1:8443/
```

PC Wi-Fi가 `k1-orinnx10`인지 확인한다.

### API key 경고

PC server를 `Ctrl-C`로 종료하고 같은 터미널에서 다시 입력한다.

```bash
read -rsp "OpenAI API key: " OPENAI_API_KEY; echo; export OPENAI_API_KEY
```

### API 준비가 안 됨

- heartbeat 확인
- SD OFF → ON edge 재생성
- 3초 warmup 대기
- RC link 및 E-stop 확인

### 버튼/음성은 되지만 동작이 거부됨

- UI가 `API 준비됨`인지 확인
- 이미 다른 동작이 실행 중인지 확인
- `MimicWaveHand`가 robot mode 목록에 로드됐는지 확인

## 주의

- 실제 API key/token을 문서나 채팅에 저장하지 않는다.
- 로봇 USB 주소 `192.168.55.1`은 운영 명령 경로로 사용하지 않는다.
- locomotion 중 teleop velocity passthrough는 로봇 배포·빌드와 하드웨어 비연결 C++ 테스트 25/25까지 완료했다.
- ReadyPose/locomotion에서의 실제 출력 연속성은 아직 실물 검증 전이다.
- 배포 후에는 ReadyPose → API부터 확인하고, E-stop 담당자가 있는 상태에서 저속 locomotion → API를 검증한다.
- 개소식 전 무선 장시간 테스트와 E-stop 리허설이 필요하다.

