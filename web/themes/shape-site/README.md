# shape-site

동아리 사이트(snu-shape.com)와 같은 얼굴. 원천은 `docs/design/shape-design/` 이다.

- **대기화면**은 SHAPE 심볼 한 장(`idle.png`, 256px 원본)이 기본이다. 행사 아트워크가
  있으면 이 자리에 `idle.jpg` 든 `idle.png` 든 갈아 끼우면 된다 — 페이지는 늘
  `/theme/idle` 로만 부르고 서버가 확장자를 찾는다.
- **글꼴을 저장소가 직접 실어 보낸다**(`pretendard-variable.woff2`, 2.1MB, SIL OFL 1.1).
  현장 네트워크를 믿을 수 없고, 안 깔린 기계에서는 여유가 십몇 픽셀뿐인 칸이 무너진다.

```bash
python3 app.py --theme shape-site
```
