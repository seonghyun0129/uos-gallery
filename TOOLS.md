# TOOLS.md - 로컬 메모

이 파일은 도구를 실제로 운영할 때 필요한 **개인 환경 설정**을 기록하는 노트입니다.

## 이 파일에 적는 내용

- 카메라/장치 이름과 위치
- SSH 호스트와 별칭
- TTS 기본 음성 설정
- 스피커·공간(룸)별 설정
- 기기별 별명
- 기타 환경 특화 설정

## 예시

```markdown
### 카메라

- living-room → 거실, 180도 광각
- front-door → 현관, 동작 감지형

### SSH

- home-server → 192.168.1.100, 사용자: admin

### TTS

- 기본 음성: "Nova" (따뜻한 톤)
- 기본 출력 장치: Kitchen HomePod
```

---

## UOS Gallery 자동화

### 이미지 처리 규칙

작가가 Telegram으로 작품을 등록할 때 이미지 파일을 반드시 첨부한다.

1. Telegram에서 수신한 이미지를 다음 경로에 저장한다.
   - `assets/images/gallery/{year}/{month}/{workSlug}.jpg`
2. 저장한 경로를 `IMAGE_PATH`로 사용해 작품을 생성한다.
3. 이미지가 없으면 등록을 중단하고 첨부를 요청한다.

### 작품 등록 입력 형식

```text
artist: {영문-슬러그}
title: {작품명}
year: {연도}
month: {월(두 자리)}
description: {설명}
+ 이미지 첨부
```

### 디렉토리 구조

```text
works/{artist}/{year}/{month}/{slug}/index.html
assets/images/gallery/{year}/{month}/{slug}.jpg
archives/{year}/{month}/index.html
```

## 분리해 두는 이유

- Skills는 공유되고, 이 파일은 개인 환경 메모용으로 분리해 관리한다.
- 개인 세팅은 유지하면서도, 스킬 문서는 따로 업데이트할 수 있다.
- 환경 정보 유출 없이 협업/공유가 쉬워진다.

---

필요한 메모를 계속 추가해서, 작업 기준을 빠르게 정리해두는 문서로 사용한다.
