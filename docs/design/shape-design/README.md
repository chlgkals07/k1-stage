# SHAPE 디자인

서울대학교 로봇 동아리 **SHAPE** 의 디자인을 한곳에 모은 곳입니다.
[www.snu-shape.com](https://www.snu-shape.com) 에서 실제로 쓰는 색·글자·여백을
그대로 뽑아 정리했습니다.

발표자료, 포스터, 새 웹 화면을 만들 때 **이 폴더를 Claude 나 Codex 에 던져 주면**
사이트와 같은 얼굴의 결과가 나옵니다. 디자인을 몰라도 됩니다.

## 이렇게 쓰세요

### 0. 파워포인트만 필요하면 이 폴더는 필요 없습니다

부원이 직접 고쳐 쓰는 **`SHAPE 발표자료 템플릿.pptx`** 가 자료실에 따로 있습니다
(구글 슬라이드용 판과 Pretendard 글꼴 묶음도 같은 자리에 있습니다). 장을 복사해
글자만 바꾸면 됩니다. 이 폴더는 **모델에게 시켜서 만들 때** 쓰는 것입니다.

### 1. 압축을 풉니다

SHAPE 웹사이트의 **바로가기 → SHAPE 자료** 에서 내려받은 zip 을 풀면
이 폴더가 나옵니다.

### 2. Claude 나 Codex 에 파일을 올립니다

무엇을 만드느냐에 따라 이만큼만 올리면 충분합니다.

| 만들 것 | 올릴 파일 |
|---|---|
| 발표자료(PPT) | `AGENTS.md`, `kit/shape-kit.css`, `kit/slide.html` |
| 포스터·전단·명함 | `AGENTS.md`, `kit/shape-kit.css`, `kit/print.html` |
| 웹 화면 | `AGENTS.md`, `kit/shape-kit.css`, `components/index.md` |

`AGENTS.md` 는 꼭 함께 올리세요. 나머지 파일을 언제 어떻게 쓰는지가 거기 있습니다.

### 3. 시킵니다

`prompts/` 폴더에 **복사해서 바로 쓰는 문장**이 들어 있습니다.
`[ ]` 안만 바꿔 보내세요.

- `prompts/ppt.md` — 발표자료
- `prompts/poster-card.md` — 포스터·전단·명함
- `prompts/web-feature.md` — 웹 화면

### 4. 결과를 받습니다

HTML 파일 하나가 나옵니다. 브라우저로 열어 확인하고, **인쇄 → PDF 로 저장**
으로 뽑으면 발표나 인쇄에 그대로 씁니다.
(슬라이드는 용지 **가로**, 포스터는 **A4 세로**. 둘 다 여백 없음, 배경 그래픽 켜기.)

## 먼저 눈으로 보고 싶다면

이 파일들을 내려받아 브라우저로 열어 보세요.

| 파일 | 무엇 |
|---|---|
| `kit/preview.html` | 버튼·카드·표 같은 요소가 실제로 어떻게 생겼는지 한 장에 |
| `kit/slide.html` | 발표자료 견본 7장 |
| `kit/print.html` | A4 포스터와 명함 견본 |

## 폴더 안에 무엇이 있나

```
AGENTS.md        ← 모델이 가장 먼저 읽는 파일. 규칙이 여기 있습니다
prompts/         복사해서 쓰는 문장
kit/             그대로 돌아가는 코드 (CSS·움직임·템플릿)
scripts/         토큰을 다시 만들고, 파워포인트 템플릿을 찍어 내는 코드
tokens/          색·글자·여백 값
foundations/     왜 이런 값인지, 색·글자·배치·움직임의 규칙
components/      버튼·카드·표 같은 요소의 코드와 쓰는 법
assets/          심볼과 글꼴 안내
```

## SHAPE 는 이렇게 생겼습니다

흰 종이 위의 파랑입니다. 강조는 파랑(`#2855f3`) 하나로 하고, 큰 면을 채울 때만
남색(`#0c245e`)을 씁니다. 글자는 Pretendard 한 벌이고, 제목은 굵고 자간을 좁혀
단단하게 보입니다. 버튼과 태그는 예외 없이 알약 모양이고, 그림자는 검정이 아니라
파란 기가 도는 남색을 아주 옅게 깝니다. 움직임은 조용합니다.

## 고칠 때

손으로 고치는 것은 `tokens/tokens.json` 과 `kit/_kit-source.css` 둘뿐입니다.
`tokens/tokens.css`, `kit/shape-kit.css`, `kit/token-names.js` 는 생성물이라
고쳐도 다음 빌드에 지워집니다.

```bash
node scripts/build-tokens.mjs
```

원본은 동아리 사이트 저장소 `shape_new_web` 의 `design-system/` 폴더입니다.
값이 사이트와 어긋나지 않는지 검사하는 스크립트도 그쪽에 있습니다. 이 zip 은
거기서 뜬 사본이므로, 값을 고쳤으면 원본을 고치고 zip 을 다시 올리세요.

## 라이선스

동아리 안에서 자유롭게 쓰세요. Pretendard 는 SIL Open Font License 1.1 입니다.
