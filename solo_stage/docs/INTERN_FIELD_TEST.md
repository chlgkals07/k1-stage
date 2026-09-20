# 실물 검증 사용법

목적은 `solo_stage`를 무대에서 쓸 수 있는 상태인지 **실물로** 판정하는 것이다. 이 문서의
순서를 바꾸지 않는다: **RC → 로봇 → Wi-Fi/RC 통합**. 결과는 반드시
[HANDOVER_CHECK.md](HANDOVER_CHECK.md)에 체크·기록하고 커밋한다.

> 이 문서는 한 대의 K1용 `solo_stage` 전용이다. `group_stage` 군무는 이번 검증 대상이 아니다.

## 실행만 먼저 보기

로봇에서는 전원을 켠 뒤 사람이 `go`를 실행한다. PC에서는 터미널을 두 개 연다.

```bash
# 터미널 1 — 사전 검사
cd /프로젝트/경로/k1-stage/solo_stage
python3 -m unittest discover -s tests -t .
tools/check_modes.sh

# 터미널 2 — 실제 서버. 출력 후에도 닫지 않는다.
cd /프로젝트/경로/k1-stage/solo_stage
./run.sh --stop
./run.sh --deploy
```

터미널 2에 출력된 `operator` URL을 운영자 기기에서 연다. 같은 URL의 경로만 `/dance`로
바꾸면 dance 화면이다(예: `https://호스트:18444/dance?token=같은토큰`). 출력된 `pad`는
아이패드, `display`는 TV에서 연다. 검증이 끝나면 터미널 2에서 `Ctrl-C` 후
`./run.sh --stop`을 실행한다.

| 목적 | SD(API Arm) | 서버/조작 | 정상 결과 |
|---|---|---|---|
| Wi-Fi/API | OFF→ON | `/operator`, `/dance` | gateway 명령만 실행, RC 펄스는 무시 |
| RC 폴백 | OFF | `/rc/mode`, K1PC | K1PC가 Mimic 펄스 후 CH6 중앙으로 복귀 |
| 대기 | OFF | SC 상단, SB 중앙 | 새 동작 명령 없음 |

## 0. 시작 조건 (5분)

1. 로봇 주변을 비우고, **E-stop 담당자를 별도로 한 명 정한다. 혼자 시험하지 않는다.**
2. 대기 스위치를 `SC 상단(CH7 2000)`, `SB 중앙(CH6 1500)`에 둔다. SC 중앙은 ReadyPose가
   될 수 있어 위험하므로 금지한다.
3. PC 터미널에서 `solo_stage/`로 이동해 기준 커밋과 자동 검사를 확인한다. 이후 이 문서의
   PC 명령은 모두 이 위치에서 실행한다.

   ```bash
   cd /프로젝트/경로/k1-stage/solo_stage
   git log -1 --oneline
   python3 -m unittest discover -s tests -t .
   ```

   `ModuleNotFoundError: yaml`이면 PC의 운영 Python에 `PyYAML`이 없다. 준비된 가상환경을
   활성화한다. 준비된 환경이 없다면 운영 담당자와 확인 후 아래처럼 로컬 환경을 만든다.

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   python3 -m pip install PyYAML
   ```

   이후 테스트와 `run.sh`는 같은 터미널에서 실행한다. 검사를 건너뛰고 실기로 가지 않는다.

4. 실행 전 상태만 볼 때는 `./run.sh --status`를 쓴다. 실제 기동은 §2-5의
   `./run.sh --deploy`이며, **접속 URL을 출력한 뒤 relay가 계속 실행되므로 터미널을 닫지 않는다.**
5. [HANDOVER_CHECK.md](HANDOVER_CHECK.md)를 열어 함께 체크한다. 실패하면
   [RUNBOOK §5](RUNBOOK.md#5-장애-대응)를 보고, 안전 실패는 그 자리에서 중단한다.

## 1. RC와 로봇 설정 대조 (15분)

### 1-1. 라디오가 PC에 보이는지

1. 라디오 **위쪽 USB-C**를 PC에 연결한다. 아래쪽은 충전 전용이다.
2. 라디오에서 `SYS → Hardware → USB-VCP = LUA`를 확인한다.
3. `SYS → Tools → K1PC`를 열어 `K1PC vX.X IDLE`을 확인하고 버전을 기록한다.

### 1-2. 로봇 백업으로 RC 슬롯 대조

로봇의 최신 `ai_sapiens/config/k1_config.yaml`을 PC에 **복사본으로만** 가져온다. 원본을
편집하지 않는다. 아래 첫 명령은 읽기 전용 검사다.

```bash
python3 tools/verify_robot_rc_config.py /받은/경로/k1_config.yaml
```

`통과`는 로봇의 A/B selector가 이번 무대의 14개 `rc_list`와 정확히 같다는 뜻이다.
실패하면 RC 모드 실기를 진행하지 않는다. 둘 중 실제 사용할 목록을 먼저 결정한다.

- 로봇 설정이 최신이면 아래 명령으로 그 값을 `motions.yaml`에 가져온다.
- 저장소의 14개가 이번 무대 목표면 로봇 selector를 갱신한 뒤, 새 백업을 받아 재검사한다.
- 새 동작은 로봇 selector와 `motions.yaml`의 `motions`/`rc_list`, `gateway_config.yaml`의
  `api_allowlist`에 함께 추가한다. 패드용이면 `pad_allowlist`, dance용이면
  `dance_presets.json`에도 추가한다.

```bash
python3 ../rc_link/gen_rc_list.py /받은/경로/k1_config.yaml motions.yaml
git diff -- motions.yaml
```

의도한 14개 고유 RC 항목만 확인한다. 이 명령은 `motions.yaml`을 바꾸므로, 예상 밖 state가
들어오면 커밋하지 말고 운영 담당자에게 넘긴다. 패드 12개와 dance 전용 서울대 응원·
스트레이키즈가 다이얼에 있는지 기록한다. `BAD`는 패드와 dance가 같은 슬롯을 공유한다.

### 1-3. SD 권한 상호작용을 눈으로 재현

E-stop 담당자가 준비됐을 때만, 안전한 손동작 하나로 아래 두 경우를 **같은 세션**에 확인한다.

1. `SD OFF → ON`으로 API를 켠 뒤 RC 명령을 보낸다. API 권한에서는 gateway 명령만
   허용되므로, PC/라디오는 `OK`여도 로봇이 **무시하는 것이 정상**이다.
2. SD를 다시 OFF로 내리고 같은 RC 명령을 보낸다. 이번에는 로봇이 **실행**해야 정상이다.

RC 명령은 계속 Mimic 상태를 붙들지 않는다. K1PC가 실행 순간에만 `CH6=2000`과
`CH7=2000`(Mimic code)을 펄스로 만들고, 곧 `CH6=1500` 중앙(code 0)으로 돌린다.
따라서 대기 중 SB(CH6)는 중앙에 두고, 사람이 Mimic 위치를 계속 유지하지 않는다.

둘 중 하나라도 반대면 중단하고 RUNBOOK §5를 따른다. “PC가 성공이라고 말함”은 성공 근거가
아니다.

## 2. 로봇과 Wi-Fi 경로 확인 (15분)

1. 로봇 전원 후 로봇에서 사람이 `go`를 실행한다.
2. PC에서 `tools/check_modes.sh`를 실행한다. 아래 14개 중 하나라도 빠지면 중단하고 기록한다:
   패드 12개와 dance 전용 `MimicNewSnuCheerHeadShort`, `MimicStraykidsThisAndThat`.
3. SD를 `OFF → ON`으로 올리고 약 3초 기다린다. `/operator` 상단이 **API 준비됨**이어야 한다.
4. 이동하며 Wi-Fi를 측정한다.

   ```bash
   tools/link_test.sh 30
   ```

   손실 0%, RTT 한 자릿수 ms를 기록한다. 실패하면 RUNBOOK §5의 링크 진단부터 한다.
5. 코드가 갱신된 날에는 이전 gateway를 쓰지 않도록 다음 순서로 시작한다.

   ```bash
   ./run.sh --stop
   ./run.sh --deploy
   ```

   출력된 `pad`, `display`, `operator` URL을 각각 아이패드·TV·운영자 폰에 연다.
   dance는 operator URL의 경로만 `/dance`로 바꿔 연다. 이 터미널은 relay이므로 검증이
   끝날 때까지 켜 둔다.

### 2-6. API 모드와 RC 모드 바꾸기

`./run.sh --deploy` 뒤에는 서버를 다시 켤 필요 없이 `/operator`에서 경로를 바꾼다.

**API 모드로 사용할 때**

1. `/operator` 상단의 현재 경로가 `RELAY · PC→ROBOT`인지 확인한다.
2. RC의 SD를 `OFF → ON`으로 올리고 약 3초 기다린다.
3. 상태가 `API 준비됨`이 되면 `/operator`나 `/dance`에서 실행한다.

**RC 모드로 바꿀 때**

1. SD를 `OFF`로 내린다. API 권한이 켜진 채면 로봇이 RC 명령을 무시한다.
2. `/operator`에서 `RC 모드 켜기 — 유선 RC로 전환`을 누른다.
3. 상단 배지가 `RC · 유선 RC→ELRS`, 현재 경로가 `rc`인지 확인한다.
4. 같은 `/dance` 화면에서 프리셋을 실행한다. 영상 재생은 그대로고 로봇 명령만 RC로 간다.

**다시 API 모드로 돌아갈 때**

1. `/operator`에서 `RC 모드 끄기 — 기본 경로 복귀`를 누른다.
2. 상단 배지가 `RELAY · PC→ROBOT`인지 확인한다.
3. SD를 `OFF → ON`으로 올리고 `API 준비됨`을 확인한다.

RC 전환 버튼은 라디오 USB와 K1PC가 정상일 때만 성공한다. `MOCK` 실행에서는 화면과
dance 흐름만 볼 수 있고, 실제 라디오가 없으면 RC 전환은 실패 메시지가 뜨는 것이 정상이다.

## 3. 무대 통합 검증 (E-stop 대기, 순서 고정)

`/operator`, `/pad`, `/display`, `/dance`를 연다. TV는 화면을 한 번 클릭해 소리 잠금을 푼다.

1. 로봇이 동작 중일 때 **정지 버튼**이 즉시 동작하는지 먼저 확인한다.
2. 손 흔들기 → 배꼽 인사 → 손키스 순서로 회귀한다.
3. 패드 탭 → TV 미리보기 → `[실행]` → 로봇 동작 및 TV `실행 중`을 확인한다.
4. API 모드 dance: 현재 경로 `RELAY` + SD ON + `API 준비됨`을 확인하고 프리셋을 재생한다.
   영상/음악/로봇 싱크가 어긋나면 오프셋을 조정하고 프리셋을 저장한다.
5. RC 모드 dance: SD OFF → `/operator`의 `RC 모드 켜기` → 현재 경로 `RC`를 확인하고
   같은 프리셋을 재생해 싱크를 기록한다.
6. **신규 회귀:** SD를 올리지 않은 상태로 dance 시작을 누른다. 시작하지 않고
   `로봇이 명령을 받을 준비가 안 됐습니다`가 보여야 한다. 영상만 재생되면 실패다.
7. 공간을 다시 확보한 뒤 팔굽혀펴기 → 스쿼트 → 섀도우 복싱을 확인한다.
8. 끝나면 `./run.sh --stop`, SD OFF, 그리고 아래로 Manual 복귀를 확인한다.

   ```bash
   ros2 topic echo /ai_sapiens/mode_status --once
   ```

## 4. 인계 기준

- 성공: HANDOVER의 모든 안전 항목과 §3 신규 회귀가 통과하고, 실측값·이슈·다음 조치가
  결과 표에 남아 있다.
- 실패: 로봇을 계속 시험하지 않는다. 오류 메시지, 스위치 위치, 시각, 실행한 명령과
  `git diff`를 남긴 뒤 RUNBOOK §5를 따른다.
- 마무리: 변경된 `HANDOVER_CHECK.md`와 의도한 `motions.yaml`만 검토해 커밋·푸시한다.
