#!/usr/bin/env node
/**
 * tokens/tokens.json → tokens/tokens.css
 *
 * 토큰을 두 군데에 손으로 적어 두면 반드시 어긋납니다. JSON 만 고치고 이 파일을
 * 돌리세요.  node design-system/scripts/build-tokens.mjs
 *
 * 이름 규칙: 중첩된 열쇠를 하이픈으로 이어 `--sh-` 를 붙입니다.
 *   color.brand.blue        → --sh-color-brand-blue
 *   color.status.danger.fg  → --sh-color-status-danger-fg
 *   font.size.body-sm       → --sh-font-size-body-sm
 * `$value` 가 배열이면(글꼴 목록, 베지어) 알맞게 이어 붙입니다.
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const src = path.join(here, "..", "tokens", "tokens.json");
const out = path.join(here, "..", "tokens", "tokens.css");

const tokens = JSON.parse(fs.readFileSync(src, "utf8"));
const lines = [];

function render(value, keyPath) {
  if (Array.isArray(value)) {
    // cubicBezier 는 함수로, fontFamily 는 목록으로.
    if (keyPath.includes("easing")) return `cubic-bezier(${value.join(", ")})`;
    return value.map((v) => (/\s/.test(v) ? `"${v}"` : v)).join(", ");
  }
  return String(value);
}

function walk(node, trail) {
  if (node && typeof node === "object" && "$value" in node) {
    lines.push({ name: `--sh-${trail.join("-")}`, value: render(node.$value, trail), note: node.$description });
    return;
  }
  for (const [key, child] of Object.entries(node ?? {})) {
    if (key.startsWith("$")) continue;
    if (child && typeof child === "object") walk(child, [...trail, key]);
  }
}

for (const [group, node] of Object.entries(tokens)) {
  if (group.startsWith("$")) continue;
  lines.push({ heading: group, note: node.$description });
  walk(node, [group]);
}

const body = lines
  .map((row) =>
    row.heading
      ? `\n  /* ${row.heading}${row.note ? ` — ${row.note}` : ""} */`
      : `  ${row.name}: ${row.value};${row.note ? ` /* ${row.note} */` : ""}`,
  )
  .join("\n");

fs.writeFileSync(
  out,
  `/* 자동 생성 파일입니다. 고치지 마세요.\n * 원천: design-system/tokens/tokens.json\n * 다시 만들기: node design-system/scripts/build-tokens.mjs\n */\n\n:root {${body}\n}\n`,
);

// 슬라이드·포스터 HTML 은 파일 하나만 넣을 수 있어야 합니다. 그래서 토큰과
// 구성 요소를 이어 붙인 kit/shape-kit.css 를 함께 만듭니다.
const kitSrc = path.join(here, "..", "kit", "_kit-source.css");
const kitOut = path.join(here, "..", "kit", "shape-kit.css");
const header = `/* SHAPE UI Kit — 자동 생성 파일입니다. 고치지 마세요.
 * 원천: design-system/tokens/tokens.json + design-system/kit/_kit-source.css
 * 다시 만들기: node design-system/scripts/build-tokens.mjs
 */\n\n`;
fs.writeFileSync(kitOut, header + fs.readFileSync(out, "utf8").replace(/^\/\*[\s\S]*?\*\/\n\n/, "") + "\n" + fs.readFileSync(kitSrc, "utf8"));

// 미리보기 페이지는 file:// 로 열려도 색 견본을 그려야 합니다. 그런데 그때는
// 외부 스타일시트의 규칙을 읽을 수 없으므로, 이름 목록을 따로 내보냅니다.
const colorNames = lines.filter((l) => l.name && l.name.startsWith("--sh-color-")).map((l) => l.name);
fs.writeFileSync(
  path.join(here, "..", "kit", "token-names.js"),
  `/* 자동 생성 파일입니다. build-tokens.mjs 가 씁니다. */\nwindow.SH_COLOR_TOKENS = ${JSON.stringify(colorNames, null, 2)};\n`,
);

console.log(`tokens.css — ${lines.filter((l) => l.name).length}개 변수`);
console.log(`shape-kit.css — ${fs.readFileSync(kitOut, "utf8").split("\n").length}줄`);
