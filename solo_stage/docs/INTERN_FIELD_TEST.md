# 내일 실물 검증 — 인턴 1회용 사용법

목적은 `solo_stage`를 무대에서 쓸 수 있는 상태인지 **실물로** 판정하는 것이다. 이 문서의
순서를 바꾸지 않는다: **RC → 로봇 → Wi-Fi/RC 통합**. 결과는 반드시
[HANDOVER_CHECK.md](HANDOVER_CHECK.md)에 체크·기록하고 커밋한다.

> 이 문서는 한 대의 K1용 `solo_stage` 전용이다. `group_stage` 군무는 이번 검증 대상이 아니다.

## 0. 시작 조건 (5분)

1. 로봇 주변을 비우고, **E-stop 담당자를 별도로 한 명 정한다. 혼자 시험하지 않는다.**
2. 대기 스위치를 `SC 상단(CH7 2000)`, `SB 중앙(CH6 1500)`에 둔다. SC 중앙은 ReadyPose가
   될 수 있어 위험하므로 금지한다.
3. PC에서 다음을 실행해 기준 커밋과 자동 검사를 확인한다.

   ```bash
   cd solo_stage
   git log -1 --oneline
   python3 -m unittest discover -s tests -t .
   ```

   `ModuleNotFoundError: yaml`이면 PC의 운영 Python에 `PyYAML`이 없다. 준비된 가상환경을
   활성화하거나 운영 담당자에게 설치를 요청한다. 검사를 건너뛰고 실기로 가지 않는다.

4. [HANDOVER_CHECK.md](HANDOVER_CHECK.md)의 날짜·담당자 칸을 먼저 채운다. 실패하면
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
cd solo_stage
python3 tools/verify_robot_rc_config.py /받은/경로/k1_config.yaml
```

`통과`는 A/B 40개 슬롯이 `motions.yaml`과 같고, 가장 중요한 **B-202가
`MimicGuapVer2`**라는 뜻이다. 실패하면 실기 진행 금지다.

특히 `MimicGuap`(v1)이라고 나오면 로봇의
`selectors.mimic_selector_b.table.202`를 `MimicGuapVer2`로 바꾼 뒤 새 백업을 받아 다시
검사한다. 그 다음에만 아래처럼 PC의 RC 목록을 재생성하고 변경 내용을 검토한다.

```bash
python3 ../rc_link/gen_rc_list.py /받은/경로/k1_config.yaml motions.yaml
git diff -- motions.yaml
```

의도한 `rc_list` 변경만 확인한다. 이 명령은 `motions.yaml`을 바꾸므로, 실수 또는
예상 밖 변경이면 커밋하지 말고 운영 담당자에게 넘긴다. 패드의 12개 동작이 라디오 다이얼에
모두 있는지도 `HANDOVER_CHECK.md` §1.2에 기록한다.

### 1-3. SD 권한 상호작용을 눈으로 재현

E-stop 담당자가 준비됐을 때만, 안전한 손동작 하나로 아래 두 경우를 **같은 세션**에 확인한다.

1. `SD OFF → ON`으로 API를 켠 뒤 RC 명령을 보낸다. PC/라디오는 `OK`여도 로봇이
   **무시하는 것이 정상**이다.
2. SD를 다시 OFF로 내리고 같은 RC 명령을 보낸다. 이번에는 로봇이 **실행**해야 정상이다.

둘 중 하나라도 반대면 중단하고 RUNBOOK §5를 따른다. “PC가 성공이라고 말함”은 성공 근거가
아니다.

## 2. 로봇과 Wi-Fi 경로 확인 (15분)

1. 로봇 전원 후 로봇에서 사람이 `go`를 실행한다.
2. PC에서 `tools/check_modes.sh`를 실행한다. 로드 수를 `___/136`으로 기록하고 빠진 mode를
   적는다. `MimicGuapVer2`가 없다면 B-202를 고쳐도 해당 동작은 실행되지 않으므로 중단한다.
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

## 3. 무대 통합 검증 (E-stop 대기, 순서 고정)

`/operator`, `/pad`, `/display`, `/dance`를 연다. TV는 화면을 한 번 클릭해 소리 잠금을 푼다.

1. 로봇이 동작 중일 때 **정지 버튼**이 즉시 동작하는지 먼저 확인한다.
2. 손 흔들기 → 배꼽 인사 → 손키스 순서로 회귀한다.
3. 패드 탭 → TV 미리보기 → `[실행]` → 로봇 동작 및 TV `실행 중`을 확인한다.
4. API 모드 dance: 프리셋 재생, 영상/음악/로봇 싱크를 확인한다. 어긋나면 오프셋을 조정하고
   프리셋을 저장한다.
5. RC 모드 dance: `/rc/mode`를 토글하고 같은 프리셋을 재생해 싱크를 기록한다.
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
