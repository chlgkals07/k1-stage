# 구성 요소

전부 `kit/shape-kit.css` 안에 들어 있습니다. 클래스 이름은 www.snu-shape.com 과
일부러 같게 두었으므로, 여기서 만든 조각을 `shape_web/frontend` 에 그대로 옮겨
붙일 수 있습니다.

실제로 그려진 모습은 `kit/preview.html` 을 브라우저로 열어 보세요.

## 버튼

```html
<button class="button">신청하기</button>              <!-- 기본. 한 화면에 하나 -->
<button class="button secondary">자세히 보기</button>  <!-- 둘째부터 -->
<button class="button ghost">취소</button>            <!-- 테두리 없는 것 -->
<button class="button danger">예약 취소</button>       <!-- 되돌릴 수 없는 일 -->
<button class="button small">작은 버튼</button>
<button class="button block">화면 폭을 채우는 버튼</button>
<button class="button" disabled>마감</button>
<button class="text-button">더 보기</button>          <!-- 글자만 -->
```

알약 모양, 굵기 800, 좌우 여백 18px. hover 하면 1px 뜨고 파란 그림자가 깔립니다.
`.danger` 는 삭제·취소처럼 되돌릴 수 없는 일에만 씁니다. 확인 대화상자의 확인
버튼이 아니라면 `.danger` 를 쓸 일은 드뭅니다.

## 카드

```html
<article class="card">
  <span class="meta">01</span>
  <h3>정기 세미나</h3>
  <p>매주 목요일 저녁, 부원이 돌아가며 자기 작업을 발표합니다.</p>
  <span class="card-action">일정 보기</span>
</article>

<article class="card solid blue">…</article>   <!-- 파란 카드 -->
<article class="card solid">…</article>        <!-- 남색 카드 -->
```

hover 하면 6px 뜨고 테두리가 파랑으로 바뀌며 화살표가 오른쪽으로 4px 갑니다.
`.card-action` 은 `margin-top:auto` 라 카드 높이가 달라도 아래에 붙습니다.

세 장을 나란히 둘 때는 흰색·파랑·남색 순으로 섞으면 홈과 같은 리듬이 납니다.

## 배지와 칩

```html
<span class="badge info">승인</span>
<span class="badge success">사용 중</span>
<span class="badge warn">임시 저장</span>
<span class="badge danger">반려</span>
<span class="badge staff">운영진</span>

<button class="chip">전체</button>
<button class="chip" aria-pressed="true">3D 프린터</button>
```

배지는 **상태를 알리는 것**이고 칩은 **누르는 것**입니다. 누를 수 없는 것에
`.chip` 을 쓰지 마세요. 칩의 선택 상태는 `aria-pressed="true"` 로 나타냅니다 —
클래스만 바꾸면 화면 낭독기가 알 수 없습니다.

## 입력

```html
<div class="field">
  <label for="name">이름</label>
  <input id="name" placeholder="홍길동">
  <p class="form-note">부원 명부에 등록된 이름을 적어 주세요.</p>
</div>
<p class="form-note error">이미 쓰인 이름입니다.</p>
```

`label` 의 `for` 와 입력칸의 `id` 를 반드시 잇습니다. 초점이 가면 테두리가
파랑으로 바뀌고 3px 파란 테가 생깁니다. placeholder 를 라벨 대신 쓰지 마세요.

## 안내 상자

```html
<p class="note">동아리방은 301동 109호입니다.</p>
<p class="note info">예약은 하루 전까지 신청해 주세요.</p>
<p class="note warn">아직 임시 저장 상태입니다.</p>
<p class="note danger">이미 다른 부원이 잡아 둔 시간입니다.</p>
```

## 표

```html
<div class="sh-table-scroll">
  <table class="sh-table">
    <thead><tr><th>장비</th><th>신청자</th><th class="num">시간</th></tr></thead>
    <tbody><tr><td>3D 프린터 A</td><td>김서연</td><td class="num">3시간</td></tr></tbody>
  </table>
</div>
```

**`.sh-table-scroll` 로 감싸는 것을 빠뜨리지 마세요.** 표는 좁은 화면에서
페이지 전체를 가로로 밀어 버리는 가장 흔한 원인입니다. 숫자 칸에는 `.num` 을
붙여 오른쪽 정렬과 자릿수 고정을 함께 얻습니다.

## 빈 상태

```html
<div class="empty-state">
  <svg width="34" height="34" …>…</svg>
  <h2>아직 예약이 없습니다</h2>
  <p>장비를 고르면 빈 시간이 바로 보입니다.</p>
  <button class="button">예약하러 가기</button>
</div>
```

빈 화면을 그냥 비워 두지 마세요. **무엇이 없는지**와 **다음에 무엇을 할 수
있는지**를 함께 적습니다.

## 뼈대와 글자 도우미

```html
<section class="sh-section">          <!-- 구획. .tint 를 붙이면 옅은 파란 바탕 -->
  <div class="sh-wrap">               <!-- 최대 1680px, 가운데 정렬 -->
    <p class="sh-eyebrow">PROGRAM</p>
    <h2 class="sh-display">함께 만드는 기계</h2>
    <p class="sh-lead sh-reading">…</p>
    <div class="sh-grid">…</div>      <!-- 자동 열 카드 격자 -->
  </div>
</section>
```

`.sh-row` 가로 나열 · `.sh-stack` 세로 나열 · `.sh-spread` 양끝 정렬 ·
`.sh-track` 가로 스크롤 스냅 줄.

## 움직임 도우미

```html
<div class="sh-stagger">
  <article class="card sh-reveal">…</article>   <!-- 화면에 들어오면 나타남 -->
</div>
<article class="card sh-tilt">…</article>        <!-- 포인터를 따라 기움 -->
<span class="sh-float">떠다니는 장식</span>
```

`kit/motion.js` 를 함께 넣어야 파이어폭스·사파리에서도 동작합니다.
자세한 것은 `foundations/motion.md`.

## 사진

```html
<img class="media" src="…" alt="…">              <!-- 16:10 -->
<img class="media cover" …>                       <!-- 16:9 -->
<img class="media portrait" …>                    <!-- 4:5, 인물 -->
<img class="media square" …>                      <!-- 1:1, 장비 -->
```

비율을 미리 정해 두면 사진이 늦게 와도 배치가 튀지 않습니다. `alt` 를 빠뜨리지
마세요.
