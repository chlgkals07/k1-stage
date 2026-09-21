# 2026-08-31 개소식 (보관)

이 폴더는 **서버가 읽지 않는 스냅샷을 함께 담고 있다.**

| 파일 | 내용 |
|---|---|
| `venue.yaml` | 그날의 패드 12칸(12번째가 `MimicGuapVer2`) · `archived: true` |
| `presets.json` | 그날의 프리셋 8개와 실측 오프셋 |
| `motions.full.yaml` | 그때의 **전체 동작 카탈로그 139개** (참고용) |
| `gateway_config.full.yaml` | 그때의 **전체 정책 — `api_allowlist` 79개** (참고용) |

`main` 은 9/22 행사를 위해 카탈로그를 16개, 허용목록을 14개로 줄였다(리허설로 검증한 동작만). 그 줄이기 전의
전체 목록이 여기 남아 있다. 다음 행사에서 동작을 더 열고 싶으면 이 목록에서 골라 카탈로그·정책에 되살린다 —
되살릴 때는 `docs/` 의 승격 절차(수동 실물 검증 → 허용 → 패드)를 따른다.

`*.full.yaml` 은 `core/catalog.py` 가 읽지 않는다. 서버 부팅과 `tools/preflight.py` 는 `venue.yaml` 과 `presets.json`
만 본다.
