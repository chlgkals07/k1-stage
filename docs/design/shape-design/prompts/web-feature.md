# 웹 화면을 만들 때 쓰는 프롬프트

주는 파일: `AGENTS.md`, `kit/shape-kit.css`, `components/index.md`,
움직임이 필요하면 `foundations/motion.md` 와 `kit/motion.js`.

```
SHAPE 웹사이트에 들어갈 [화면 이름] 을 만들어 줘.

이 화면이 하는 일: [부원이 자기 예약을 확인하고 취소한다]
보는 사람: [로그인한 부원]
있어야 할 것:
- [다가오는 예약 목록]
- [지난 예약 접어 두기]
- [예약 취소 버튼과 확인 대화상자]

만드는 방법:
- 함께 준 shape-kit.css 의 클래스를 써. 새 CSS 는 그것으로 안 되는 것만
  최소한으로 덧붙이고, 색·크기·여백은 --sh-* 토큰만 써.
- components/index.md 에 있는 구성 요소를 먼저 찾아 쓰고, 없을 때만 새로 만들어.
- 모바일을 함께 만들어. 360px 폭에서 넘치는 곳이 없어야 하고, 표는
  .sh-table-scroll 로 감싸고, 누를 것은 44px 이상이어야 해.
- 빈 상태(.empty-state)와 오류 문구를 빠뜨리지 마.
- 말투는 담담한 존댓말.
```

## 움직임을 넣을 때 덧붙일 말

```
- 나타나기는 .sh-reveal 과 kit/motion.js 를 함께 써. CSS 의
  animation-timeline: view() 만 쓰면 파이어폭스에서 글이 안 보여.
- prefers-reduced-motion: reduce 를 반드시 처리해.
```
