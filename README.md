# uos-gallery

**UOS RECODE** - 서울시립대학교 디자인학과 코딩 스터디그룹 갤러리

## 개요

이 저장소는 작품 페이지, 썸네일, 아카이브 카드를 템플릿 기반으로 관리합니다.

## 프로젝트 구조

```text
uos-gallery/
├── index.html
├── netlify.toml
├── recode1/                    # 네트워크 시각화 진입 페이지
├── templates/
│   ├── work-template.html
│   ├── archive-card-template.html
│   └── archive-template.html
├── assets/
│   ├── css/
│   │   └── styles.css
│   ├── js/
│   │   └── script.js
│   └── images/
│       ├── common/
│       │   ├── logo.png
│       │   └── cursor.png
│       └── gallery/
│           ├── 2023/
│           │   ├── 07/
│           │   └── 10/
│           └── {year}/{month}/      ← 예: assets/images/gallery/2024/01/
├── archives/
│   └── {year}/
│       └── {month}/
│           └── index.html
└── works/
    ├── kim-ye-young/2023/10/danbi/index.html
    ├── ryu-chae-eun/
    │   ├── 2023/07/ryufolio/index.html
    │   ├── 2023/07/uosvd/index.html
    │   └── 2023/10/busy-day/index.html
    ├── park-na-hyun/
    │   ├── 2023/07/positive-words/index.html
    │   └── 2023/10/tmi-pli/index.html
    ├── park-ju-hye/2023/07/bbss/index.html
    ├── byun-min-kyung/2023/10/letter-archiving/index.html
    ├── choi-hyemin/2023/10/freshly-weaved/index.html
    └── hwang-yein/2023/10/undercover/index.html
```

## 템플릿

### `templates/work-template.html`
- 작품 페이지 생성용
- 치환 변수:
  - `{{TITLE}}`
  - `{{ARTIST}}`
  - `{{YEAR}}`
  - `{{MONTH}}`
  - `{{DESCRIPTION}}`
  - `{{IMAGE_PATH}}`

### `templates/archive-card-template.html`
- 아카이브 카드 생성용
- 치환 변수:
  - `{{WORK_PATH}}`
  - `{{THUMBNAIL_PATH}}`
  - `{{TITLE}}`
  - `{{ARTIST}}`

### `templates/archive-template.html`
- 월별 아카이브 페이지 기본 뼈대
- `<!-- AUTO-GENERATED-START -->` 와 `<!-- AUTO-GENERATED-END -->` 사이만 OpenClaw가 갱신

### `recode1`
- `recode1/`는 D3 기반 네트워크 갤러리 페이지(클릭 시 작품 페이지로 이동)

## OpenClaw 실행 스크립트

```bash
# 기본 사용 예시
python3 scripts/add-artwork.py \
  --artist-name "박나현" \
  --title "TMI PLI" \
  --year 2023 \
  --month 10 \
  --description "작품 설명" \
  --image /path/to/cover.jpg
```

### 옵션

- `--artist-slug`, `--work-slug` : 자동 생성(slugify) 대신 수동 지정
- `--overwrite` : 동일한 작품/썸네일 경로가 있어도 덮어쓰기
- `--no-git` : `git add/commit/push` 수행 안 함
- `--sync-navigation` : 현재 archives 폴더 기준으로 기존 상세/아카이브/루트 nav를 일괄 갱신(신규 등록 없이)
- `--sync-network` : 작품 네트워크용 데이터 파일(`/assets/data/network-catalog.json`)만 갱신(신규 등록 없이)

### 예외 처리 규칙

- `archives/{year}/{month}/index.html`에 auto marker(`AUTO-GENERATED-START/END`)가 없으면 실패
- 동일 `WORK_PATH` 카드가 이미 존재하면 카드만 갱신/교체
- 필요 시 `--overwrite`로 기존 파일 덮어쓰기 가능

### 생성 결과

- 작품 페이지: `works/{artistSlug}/{year}/{month}/{workSlug}/index.html`
- 썸네일: `assets/images/gallery/{year}/{month}/{workSlug}.{ext}`
- 월 아카이브: `archives/{year}/{month}/index.html`

## 작품/카드 자동 등록 규칙(안) 

- 입력값: `artistName`, `title`, `year`, `month`, `description`, `imagePath`
- slug 생성
  - `artistSlug = slugify(artistName)` (kebab-case)
  - `workSlug = slugify(title)`
- 디렉토리 생성
  - `works/{artistSlug}/{year}/{month}/{workSlug}/index.html`
  - `assets/images/gallery/{year}/{month}/`
  - `archives/{year}/{month}/index.html`
- 아티팩트 생성
  - `work-template.html` 복사 후 치환하여 `works/.../{workSlug}/index.html`
  - `archive-card-template.html`로 카드 생성 후 `archives/.../index.html`의 AUTO-GENERATED 구간에 반영

## URL 정책

- 신규 canonical URL
  - 월별: `/archives/{year}/{month}/`
  - 작품: `/works/{person}/{year}/{month}/{project}/`
- 레거시 URL 호환
  - 기존 `/2307`, `/2309`, `/2307/1`~`/2309/6` 경로는 `netlify.toml`에서 301 리다이렉트로 유지

## 이미지 규칙

- 이미지 경로 예시: `assets/images/gallery/{year}/{month}/{work-slug}.jpg`
- 썸네일/메인 이미지 파일명은 작업 slug 기준으로 관리하면 OpenClaw 연동이 단순해집니다.

## 기술 스택

- HTML5 / CSS3 / JavaScript
- jQuery 3.6.0 + jQuery UI 1.13.2
- 폰트: Space Grotesk (Google Fonts), Pretendard
- 배포: Netlify

## 멤버

김예영 / 류채은 / 박나현 / 변민경 / 안지민 / 최혜민 / 황예인

## 연락처

uos.recode@gmail.com
