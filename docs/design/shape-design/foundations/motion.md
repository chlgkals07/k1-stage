# 움직임

SHAPE 의 움직임은 조용합니다. 눈길을 끌려고 움직이지 않고, **무엇이 어디서
왔는지 알려 주려고** 움직입니다. 종류는 네 가지뿐이고, 새로 지어내지 않습니다.

1. **나타나기** — 아래에서 22px 올라오며 흐려짐이 걷힌다
2. **굴리기** — 라벨이 X축을 돌아 다음 것으로 넘어간다
3. **기울이기** — 카드가 포인터를 따라 3D 로 조금 기운다
4. **떠다니기** — 배경 장식이 아주 느리게 오르내린다

## 값

```
지속 시간   instant 140ms  포인터를 따라가는 기울기
           fast    200ms  hover, 색 바뀜
           base    250ms  펼침, 머리글 축소
           slow    350ms  큰 물체
           reveal  550ms  화면에 들어오며 나타나기
           long    850ms  라벨 X축 회전

이징       standard cubic-bezier(.2,.8,.2,1)   기본. 들어오는 모든 것
           soft     cubic-bezier(.2,.75,.2,1)  긴 회전·미끄러짐
           inout    ease-in-out                무한 반복

3D 원근    label 520px   카드 900px   무대 1000px
기울기 최대 카드 X 9° / Y 11°,  무대 X 3° / Y 5°
스태거      45ms, 네 개마다 되감음
```

---

## 1. 나타나기 — 반드시 두 벌을 함께

가장 자주 틀리는 자리입니다. `animation-timeline: view()` 는 **크로뮴에만**
있습니다. 파이어폭스와 사파리에서는 그 규칙이 통째로 무시되므로, 그것만 쓰면
**글이 영영 투명한 채로 남습니다.** 반대로 관찰자만 쓰면 스크롤에 물려 돌아가는
부드러움을 잃습니다. 그래서 늘 짝으로 씁니다.

```css
/* 기본값 — 어느 브라우저에서나 이 상태에서 출발합니다 */
.sh-reveal {
  opacity: 0;
  transform: translateY(22px);
  transition: opacity 550ms cubic-bezier(.2,.8,.2,1),
              transform 550ms cubic-bezier(.2,.8,.2,1);
}
.sh-reveal.is-visible { opacity: 1; transform: none; }

/* 스크롤 진행률에 직접 물리는 쪽(크로뮴). 자바스크립트가 필요 없습니다. */
@supports (animation-timeline: view()) {
  .sh-reveal:not(.is-visible) {
    animation: sh-rise linear both;
    animation-timeline: view();
    animation-range: entry 5% cover 35%;
    opacity: 1;
  }
}
@keyframes sh-rise { from { opacity: 0; transform: translateY(22px); } to { opacity: 1; transform: none; } }
```

```js
/* 나머지 브라우저를 위한 짝. kit/motion.js 에 들어 있습니다. */
var observer = new IntersectionObserver(function (entries) {
  entries.forEach(function (entry) {
    if (!entry.isIntersecting) return;
    entry.target.classList.add("is-visible");
    observer.unobserve(entry.target);           // 한 번 나타나면 끝
  });
}, { threshold: 0.08, rootMargin: "0px 0px -8%" });
document.querySelectorAll(".sh-reveal").forEach(function (el) { observer.observe(el); });
```

`rootMargin` 의 `-8%` 는 "화면 바닥에 걸치자마자" 가 아니라 조금 올라온 뒤에
시작하게 합니다. 그래야 스크롤을 멈췄을 때 움직임이 실제로 보입니다.

**주의 — 스크린샷을 찍을 때는 이것이 함정입니다.** 화면 밖 요소는 아직 투명해서
전체 페이지 캡처에 흰 칸으로 찍힙니다. 미리보기·검증용 페이지에는 나타나기를
걸지 마세요.

### 목록을 하나씩

```css
.sh-stagger > * { transition-delay: calc(var(--sh-order, 0) * 45ms); }
```
```js
Array.prototype.forEach.call(list.children, function (child, i) {
  child.style.setProperty("--sh-order", String(i % 4));   /* 4 를 넘기지 않습니다 */
});
```

`% 4` 로 되감는 이유는, 스무 번째 항목이 0.9초를 기다리면 고장 난 것처럼 보이기
때문입니다.

---

## 2. X축으로 굴리기 — SHAPE 내비의 서명

같은 자리에 글자를 두 벌 겹쳐 두고, 위 칸은 위로 굴러 사라지고 아래 칸은
아래에서 굴러 올라옵니다. 한글 항목이 영문 라벨로 바뀌는 자리에 씁니다.

```html
<span class="nav-label">
  <span class="nav-label-current">장비</span>
  <span class="nav-label-next">EQUIPMENT</span>
</span>
```

```css
/* 부모의 overflow:hidden 과 고정 높이가 반드시 필요합니다.
   없으면 굴러 나간 글자가 상자 밖에 그대로 보입니다. */
.nav-label { position: relative; display: inline-grid; height: 1.35em;
             place-items: center; overflow: hidden;
             perspective: 520px; transform-style: preserve-3d; }

.nav-label-current, .nav-label-next {
  grid-area: 1 / 1;                       /* 두 벌을 같은 칸에 겹칩니다 */
  transition: transform 850ms cubic-bezier(.2,.75,.2,1),
              opacity   850ms cubic-bezier(.2,.75,.2,1);
}
.nav-label-current { transform: rotateX(0deg) translateY(0);   transform-origin: 50% 100%; }
.nav-label-next    { opacity: 0; transform: rotateX(-90deg) translateY(8px); transform-origin: 50% 0; }

.nav-item:hover .nav-label-current, .nav-item:focus-within .nav-label-current {
  opacity: 0; transform: rotateX(90deg) translateY(-8px);
}
.nav-item:hover .nav-label-next, .nav-item:focus-within .nav-label-next {
  opacity: 1; transform: rotateX(0deg) translateY(0);
}
```

`transform-origin` 이 위아래로 다른 것이 핵심입니다. 나가는 글자는 아래쪽 모서리
(50% 100%)를 축으로 넘어가고, 들어오는 글자는 위쪽 모서리(50% 0)를 축으로
올라옵니다. 그래야 하나의 판이 돌아가는 것처럼 보입니다.

`:focus-within` 을 빼먹지 마세요. 키보드로 넘길 때도 같아야 합니다.

---

## 3. 포인터를 따라 기울이기

3D 는 세 자리에서만 씁니다 — 손에 든 것처럼 보여야 하는 카드, 로봇 무대,
내비 라벨. 그 밖에는 쓰지 않습니다.

```css
.sh-tilt {
  --sh-rx: 0deg; --sh-ry: 0deg;
  transform: perspective(900px) rotateX(var(--sh-rx)) rotateY(var(--sh-ry));
  transition: transform 140ms ease-out;   /* 짧아야 손을 따라오는 느낌이 납니다 */
  will-change: transform;
}
.sh-tilt.stage {                          /* 큰 물체는 각도를 훨씬 작게 */
  transform: perspective(1000px) rotateX(var(--sh-rx)) rotateY(var(--sh-ry));
  transition-duration: 350ms;
}
```

```js
el.addEventListener("pointermove", function (event) {
  if (event.pointerType === "touch") return;   /* 손가락에는 걸지 않습니다 */
  if (frame) return;                            /* 프레임마다 한 번만 */
  frame = requestAnimationFrame(function () {
    frame = 0;
    var box = el.getBoundingClientRect();
    var px = (event.clientX - box.left) / box.width;    // 0 ~ 1
    var py = (event.clientY - box.top) / box.height;
    el.style.setProperty("--sh-ry", ((px - 0.5) * 2 * 11).toFixed(2) + "deg");
    el.style.setProperty("--sh-rx", ((0.5 - py) * 2 * 9).toFixed(2) + "deg");
  });
});
el.addEventListener("pointerleave", function () {
  el.style.setProperty("--sh-rx", "0deg");
  el.style.setProperty("--sh-ry", "0deg");
});
```

세 가지를 지키세요.

- **터치에는 걸지 않습니다.** 손가락으로 기울이려면 스크롤을 막아야 하고,
  그것은 얻는 것보다 잃는 것이 큽니다.
- **`requestAnimationFrame` 으로 묶습니다.** 포인터 이벤트는 초당 수백 번
  옵니다. 그대로 스타일을 고치면 스크롤이 끊깁니다.
- **각도를 키우지 마세요.** 카드 9°/11°, 큰 물체 3°/5° 가 상한입니다.

---

## 4. 떠다니기

배경 장식 전용입니다. **글자나 버튼에 걸지 마세요.**

```css
@keyframes sh-float { 50% { transform: translateY(-12px); } }
.sh-float { animation: sh-float 7s ease-in-out infinite; }
.sh-float:nth-child(2n) { animation-delay: -2s; }   /* 음수 지연으로 위상을 흩습니다 */
.sh-float:nth-child(3n) { animation-delay: -4s; }
```

음수 `animation-delay` 는 "이미 그만큼 진행된 상태로 시작" 을 뜻합니다. 여러
요소가 한 몸처럼 오르내리는 것을 막습니다.

---

## 끌 수 있어야 합니다

빠뜨리면 안 되는 블록입니다. 어지럼증이 있는 사람에게 이 설정은 접근성 문제가
아니라 실제 통증 문제입니다.

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: .01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: .01ms !important;
    scroll-behavior: auto !important;
  }
  .sh-reveal { opacity: 1; transform: none; }   /* 감추지 말고 "이미 나타난" 상태로 */
  .sh-tilt { transform: none; }
}
```

자바스크립트에서도 같은 판단을 해야 합니다.

```js
var reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
if (reduced) { targets.forEach(function (el) { el.classList.add("is-visible"); }); }
```

## 하지 말 것

- 통통 튀는 이징(`cubic-bezier` 의 되튐), 회전 로딩 스피너 말고 다른 무한 회전
- 페이지 전환마다 통째로 미끄러지는 연출
- 스크롤을 가로채 강제로 넘기는 것
- 자동 재생 캐러셀
- `transform`·`opacity` 가 아닌 것을 애니메이션하기 (`width`, `top`, `box-shadow`
  를 움직이면 매 프레임 다시 그려집니다)
