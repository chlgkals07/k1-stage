/* SHAPE 움직임 — 붙여 넣으면 끝나는 한 파일.
 *
 * shape-kit.css 의 .sh-reveal / .sh-stagger / .sh-tilt 를 실제로 움직이게 합니다.
 * 의존성이 없고, 페이지 어디에 넣어도 됩니다.  <script src="motion.js" defer></script>
 *
 * ## 왜 CSS 만으로 안 되는가
 * `animation-timeline: view()` 는 크로뮴에만 있습니다. 파이어폭스와 사파리에서는
 * 그 규칙이 통째로 무시되므로, 관찰자로 .is-visible 을 붙여 주지 않으면 글이
 * 영영 투명한 채로 남습니다. 그래서 이 파일은 선택이 아니라 짝입니다.
 */
(function () {
  "use strict";

  var reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ── 1. 화면에 들어오면 나타나기 ─────────────────────────────────── */
  var revealTargets = document.querySelectorAll(".sh-reveal");

  if (reduced || !("IntersectionObserver" in window)) {
    revealTargets.forEach(function (el) { el.classList.add("is-visible"); });
  } else {
    var observer = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (!entry.isIntersecting) return;
          entry.target.classList.add("is-visible");
          observer.unobserve(entry.target);
        });
      },
      /* rootMargin 의 -8% 는 "화면 바닥에 걸치자마자" 가 아니라 조금 올라온
         뒤에 시작하게 합니다. 그래야 스크롤을 멈췄을 때 움직임이 보입니다. */
      { threshold: 0.08, rootMargin: "0px 0px -8%" },
    );
    revealTargets.forEach(function (el) { observer.observe(el); });
  }

  /* ── 2. 목록을 하나씩 ────────────────────────────────────────────── */
  document.querySelectorAll(".sh-stagger").forEach(function (list) {
    Array.prototype.forEach.call(list.children, function (child, index) {
      child.style.setProperty("--sh-order", String(index % 4));
    });
  });

  /* ── 3. 포인터를 따라 기울이기 ───────────────────────────────────── */
  if (!reduced) {
    document.querySelectorAll(".sh-tilt").forEach(function (el) {
      var stage = el.classList.contains("stage");
      var maxX = stage ? 3 : 9;   /* 위아래 각도. 토큰 motion.tilt 와 같은 값 */
      var maxY = stage ? 5 : 11;  /* 좌우 각도 */
      var frame = 0;

      function apply(event) {
        if (frame) return;                 /* 포인터는 초당 수백 번 옵니다.
                                              프레임마다 한 번만 반영합니다. */
        frame = requestAnimationFrame(function () {
          frame = 0;
          var box = el.getBoundingClientRect();
          var px = (event.clientX - box.left) / box.width;   /* 0 ~ 1 */
          var py = (event.clientY - box.top) / box.height;
          el.style.setProperty("--sh-ry", ((px - 0.5) * 2 * maxY).toFixed(2) + "deg");
          el.style.setProperty("--sh-rx", ((0.5 - py) * 2 * maxX).toFixed(2) + "deg");
          el.style.setProperty("--sh-px", (px * 100).toFixed(1) + "%");
          el.style.setProperty("--sh-py", (py * 100).toFixed(1) + "%");
        });
      }

      function reset() {
        el.style.setProperty("--sh-rx", "0deg");
        el.style.setProperty("--sh-ry", "0deg");
      }

      /* 손가락에는 걸지 않습니다. 터치 화면에서 기울이려면 스크롤을 막아야 하고,
         그것은 얻는 것보다 잃는 것이 큽니다. */
      el.addEventListener("pointermove", function (event) {
        if (event.pointerType === "touch") return;
        apply(event);
      });
      el.addEventListener("pointerleave", reset);
    });
  }

  /* ── 4. 스크롤하면 머리글이 줄어들기 ─────────────────────────────── */
  var header = document.querySelector(".site-header");
  if (header) {
    var onScroll = function () {
      header.classList.toggle("is-scrolled", window.scrollY > 12);
    };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
  }
})();
