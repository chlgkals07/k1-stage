// 관객 화면 두 장(display · pad)이 함께 쓰는 것만 둔다.
//
// 폴링은 여기 없다 — display 는 /conversation 을 300ms 로, pad 는 /status 와
// /conversation 을 1초로 본다. 주기도 대상도 실패 처리도 달라서, 합치면 둘 중
// 하나에 안 맞는 추상이 생긴다. 같아지면 그때 올린다.

export const $ = s => document.querySelector(s);

// 고정 캔버스를 화면에 맞춰 통째로 스케일한다. 치수는 테마가 --canvas-w/h 로 준다 —
// 새 디자인이 다른 비율로 와도 CSS 한 곳만 고치면 되고 여기는 안 고친다.
// 스케일 '메커니즘'(position/transform)은 web/base.css 에 있다.
export function fitCanvas(){
  const cs = getComputedStyle(document.documentElement);
  const w = parseFloat(cs.getPropertyValue('--canvas-w'));
  const h = parseFloat(cs.getPropertyValue('--canvas-h'));
  document.documentElement.style.setProperty('--s', Math.min(innerWidth / w, innerHeight / h));
}

// 주소창에서 토큰을 지운다. 관객에게 그대로 건네는 화면이라 남아 있으면 안 된다.
export function stripToken(){
  const q = new URLSearchParams(location.search);
  if (!q.has("token")) return;
  q.delete("token");
  const rest = q.toString();
  history.replaceState(null, "", location.pathname + (rest ? "?" + rest : ""));
}
