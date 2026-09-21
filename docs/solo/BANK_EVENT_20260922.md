# 2026-09-22 산업은행 본점 — 통신 사전 협의와 RC-only 운영안

산업은행 본점은 주최 측 안내상 2급 국가보안시설이며, 통신은 사전 허가된 항목만 사용할 수
있다. 이 문서는 `solo_stage` 한 대 시연의 통신 경로를 설명하고, 네트워크가 허가되지 않을
때의 RC-only 운영 절차를 고정한다.

> **RC도 무선통신이다.** PC→RadioMaster 구간만 USB 유선이고, RadioMaster→로봇은
> ELRS 무선이다. RC를 보안 절차의 우회 수단으로 설명하지 않는다.

## 1. 통신 경로

| 용도 | 경로 | 외부 인터넷 | 행사장 허가 |
|---|---|---:|---|
| API 제어(선택) | PC ↔ 로봇 자체 2.4GHz Wi-Fi AP ↔ robot gateway | 불필요 | Wi-Fi 사용 허가 필요 |
| RC 제어(권장) | PC → USB → RadioMaster → ELRS → 로봇 | 불필요 | ELRS 무선 사용 허가 필요 |
| 로컬 운영 화면 | 메인 PC 브라우저 ↔ `localhost:18444` | 불필요 | 네트워크 통신 없음 |
| TV | 메인 PC → HDMI → TV | 불필요 | 네트워크 통신 없음 |
| 패드·운영자 폰(선택) | 아이패드·폰 ↔ 로컬망 ↔ PC HTTPS 18444 | 불필요 | 승인된 로컬망 필요 |

음원·영상·동작 목록은 모두 PC에 저장하며 외부 API와 클라우드를 사용하지 않는다. 기관
내부망 연결도 필수가 아니다.

주의: 로봇 AP를 **사용하지 않는 것**과 AP의 RF 송출이 **꺼진 것**은 다르다. 로봇 전원을
켜면 `k1-orinnx10` AP가 자동 송출될 수 있다. RC-only로 운영하더라도 보안 담당자에게 이
사실을 알리고, 다음 중 하나를 행사 전에 확정한다.

- 로봇 AP의 송출 자체를 허가받는다.
- 행사 전에 AP를 끄고 RC 동작에 영향이 없는지 실물 검증한다.

현장에서 임의로 AP 설정을 바꾸지 않는다.

## 2. 권장 운영 구성

네트워크 허가가 불확실할 때는 다음 구성으로 준비한다.

```text
메인 PC localhost ── 운영자 / dance / display
       │
       ├── HDMI ── TV
       └── USB ── RadioMaster ── ELRS ── K1
```

- 로봇 제어는 RC 모드만 사용한다. RC의 SD(API Arm)는 **OFF**로 둔다.
- `/operator`와 `/dance`는 메인 PC에서 연다.
- TV는 HDMI로 연결하고 메인 PC의 `/display` 창을 띄운다.
- 승인된 로컬망이 없으면 아이패드·운영자 폰을 사용하지 않는다.
- PC 유선 LAN은 연결하지 않는다. Wi-Fi·Bluetooth도 승인받은 항목 외에는 끈다.
- 인터넷이 없어도 버튼, 영상, 음원, dance 싱크는 동작한다.

## 3. 행사 전에 외부 장소에서 끝낼 일

- [ ] 로봇 selector와 `motions.yaml`의 RC 14슬롯 대조 완료
- [ ] RadioMaster 위쪽 USB-C, `USB-VCP=LUA`, K1PC 실행 확인
- [ ] SNU·BAD·Stray Kids를 RC 모드로 재생하고 싱크 저장
- [ ] 정지·Damping과 E-stop 동작 확인
- [ ] 필요한 음원·영상이 PC 로컬 `media/`에 모두 존재
- [ ] Python·PyYAML과 저장소가 인터넷 없이 실행되는지 확인
- [ ] `~/.k1/secrets.env`, HTTPS 인증서와 고정 UI token 준비
- [ ] 기관망 케이블 제거, PC Wi-Fi·Bluetooth 비활성화 상태에서 localhost UI 실행 확인
- [ ] 로봇 AP 송출 허가 또는 AP 비활성화 실물 검증 완료
- [ ] ELRS 주파수 대역·출력·기기 수를 실물에서 확인해 보안 담당자에게 제출

API 배포가 필요하면 행사장이 아니라 허가된 외부 장소에서 `./run.sh --deploy`로 끝낸다.
행사장 RC-only 운영에서는 `run.sh --deploy`를 사용하지 않는다. 이 명령은 로봇 Wi-Fi와
gateway 연결을 전제로 하기 때문이다.

## 4. RC-only 실행

로봇 주변을 비우고 E-stop 담당자가 준비된 뒤 실행한다.

```bash
cd /프로젝트/경로/k1-stage/solo_stage

set -a
source ~/.k1/secrets.env
set +a

python3 server.py \
  --rc \
  --https \
  --port 18444 \
  --gateway-token "$K1_UI_TOKEN" \
  --ready-only
```

실행 터미널은 닫지 않는다. 같은 PC에서 아래 주소를 연다.

```text
https://localhost:18444/operator?token=<K1_UI_TOKEN>
https://localhost:18444/dance?token=<K1_UI_TOKEN>
https://localhost:18444/display?token=<K1_UI_TOKEN>
```

1. `/operator` 상단이 `RC · 유선 RC→ELRS`인지 확인한다.
2. SD가 OFF이고 대기 스위치가 SC 상단 + SB 중앙인지 확인한다.
3. 안전한 손동작 하나와 정지 버튼을 먼저 시험한다.
4. `/dance`에서 프리셋을 재생하고 TV 영상·음원·로봇 싱크를 확인한다.
5. 끝나면 `Ctrl-C`, SD OFF, 로봇 Manual 복귀를 확인한다.

RC 포트 없음·RC 무응답·슬롯 불일치가 나오면 API나 임의 네트워크로 우회하지 않고 시연을
중단한다. [RUNBOOK §5](RUNBOOK.md#5-장애-대응)와
[HANDOVER_CHECK.md](HANDOVER_CHECK.md)를 따른다.

## 5. 보안 담당자에게 제출할 정보

아래 값은 추정하지 말고 실제 장비에서 확인한다.

| 항목 | 제출 값 |
|---|---|
| RadioMaster 정확한 모델·시리얼 | ___ |
| ELRS 주파수 대역 | ___ |
| ELRS 설정 송신 출력 | ___ |
| 로봇 수신기 모델 | ___ |
| 송신기·수신기 수 | 각 1대 |
| 사용 위치·시간 | 산업은행 본점 / 2026-09-22 / ___ |
| 로봇 Wi-Fi 사용 여부 | 사용 안 함 / 송출 허가 / AP 비활성화 중 하나 확정 |
| Wi-Fi 허가 시 SSID·BSSID/MAC | `k1-orinnx10` / ___ |
| Wi-Fi 허가 시 대역·채널 | 2.4GHz / 현장 사용 채널 ___ |
| API 허가 시 프로토콜 | PC→로봇 HTTPS TCP 8443, 사전 관리 시 SSH TCP 22 |
| 모바일 UI 허가 시 프로토콜 | 기기→PC HTTPS TCP 18444 |
| 외부 인터넷·클라우드 | 사용하지 않음 |
| 기관 내부망 | 연결하지 않음(RC-only 기준) |

비밀번호와 제어 token은 허가 목록 정보가 아니며 문서·메일·메신저에 보내지 않는다. MAC
주소처럼 보안 부서가 요청한 식별정보만 별도로 전달한다.

## 6. 회신 문안

> Sapiens 시연에는 외부 인터넷 또는 클라우드 통신이 필요하지 않습니다. 주 운영 방식은
> 메인 PC와 RadioMaster 조종기를 USB로 연결하고, RadioMaster와 로봇 간 ELRS 무선통신으로
> 동작 명령을 전송하는 방식입니다. 운영 화면과 음원·영상은 메인 PC에서 로컬로 실행하며,
> TV는 HDMI로 연결합니다. 따라서 기관 내부 네트워크에 연결하지 않고도 시연할 수 있습니다.
>
> 보조 방식으로 로봇 자체 2.4GHz Wi-Fi AP와 메인 PC 사이의 폐쇄형 로컬 통신을 사용할 수
> 있으나, 허가되지 않을 경우 사용하지 않겠습니다. 로봇 AP가 전원 인가 시 송출될 수 있는
> 점도 사전에 협의하겠습니다.
>
> 무선통신 사전 허가를 위해 실제 장비에서 확인한 ELRS 주파수 대역·송신 출력·기기 수와,
> 필요시 로봇 Wi-Fi의 SSID·MAC 주소·채널 정보를 별도로 제출하겠습니다.
