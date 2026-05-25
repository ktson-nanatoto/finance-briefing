# 재테크 모닝 브리핑 자동화 시스템

매일 07:30 KST에 금융 데이터를 수집·분석하여 HTML 카드뉴스를 GitHub Pages로 자동 배포합니다.

## 아키텍처

```
크롤러 (Yahoo Finance / 네이버 금융 / FRED / ECOS / Reuters / CNBC)
  → 데이터 검증 + Fallback
  → Gemini API 분석 + 미국 뉴스 한국어 번역
  → Jinja2 HTML 렌더링
  → GitHub Pages 배포
  → 텔레그램 알림
```

---

## 1. GitHub Secrets 설정

레포지토리 → Settings → Secrets and variables → Actions → New repository secret

| Secret 이름 | 설명 | 발급처 |
|------------|------|--------|
| `GEMINI_API_KEY` | Gemini API 키 | https://aistudio.google.com/app/apikey |
| `FRED_API_KEY` | FRED API 키 (무료) | https://fred.stlouisfed.org/docs/api/api_key.html |
| `ECOS_API_KEY` | 한국은행 ECOS API 키 (무료) | https://ecos.bok.or.kr/api/#/DevGuide/APIKeyApply |
| `TELEGRAM_BOT_TOKEN` | 텔레그램 봇 토큰 | 아래 설명 참고 |
| `TELEGRAM_CHAT_ID` | 텔레그램 채팅 ID | 아래 설명 참고 |
| `PAGES_URL` | GitHub Pages URL | `https://<username>.github.io/<repo>/` |

---

## 2. 텔레그램 봇 설정

1. 텔레그램 앱에서 `@BotFather` 검색
2. `/newbot` 명령 → 봇 이름·username 설정
3. 발급된 토큰을 `TELEGRAM_BOT_TOKEN`에 저장
4. 본인 채팅 ID 확인: `@userinfobot` 에서 `/start` → ID 확인
5. 해당 ID를 `TELEGRAM_CHAT_ID`에 저장

---

## 3. GitHub Pages 활성화

레포지토리 → Settings → Pages → Source: `gh-pages` 브랜치 선택 → Save

---

## 4. 로컬 테스트

```bash
# 의존성 설치
pip install -r requirements.txt

# 환경변수 설정
cp .env.example .env
# .env 파일에 API 키 입력

# 실행
python -m src.main

# 결과 확인
open output/index.html
```

### .env.example

```
GEMINI_API_KEY=your_key_here
FRED_API_KEY=your_key_here
ECOS_API_KEY=your_key_here
TELEGRAM_BOT_TOKEN=your_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
PAGES_URL=https://your-username.github.io/finance-briefing/
```

---

## 5. 수동 실행

GitHub Actions → Daily Finance Briefing → Run workflow

---

## 6. 트러블슈팅

### 브리핑이 생성되지 않을 때
- Actions 탭에서 워크플로우 로그 확인
- Secrets가 올바르게 설정되었는지 확인

### 네이버 크롤링 실패
- 네이버 서버 점검 시간(새벽 2~4시) 회피 필요
- `cache/` 폴더에 전날 JSON이 있으면 자동 fallback

### Gemini API 오류
- `GEMINI_API_KEY` 유효 여부 확인
- 할당량 초과 시 https://aistudio.google.com 에서 확인

### QR코드 미표시
- `PAGES_URL` Secret이 설정되지 않은 경우 발생
- URL은 `https://`로 시작해야 함

### 텔레그램 알림 미수신
- BotFather에서 봇이 활성화 상태인지 확인
- 봇과 먼저 대화를 시작해야 메시지 수신 가능 (`/start` 전송)

---

## 파일 구조

```
.
├── .github/workflows/daily-briefing.yml
├── src/
│   ├── crawlers/
│   │   ├── us_market.py      # Yahoo Finance (S&P500, NASDAQ, DOW, VIX)
│   │   ├── kr_market.py      # 네이버 금융 (KOSPI, KOSDAQ, 환율, 유가, 금)
│   │   ├── macro.py          # FRED (미국 금리/국채), ECOS (한국 기준금리)
│   │   ├── news.py           # 네이버 경제뉴스, CNBC, Yahoo Finance RSS
│   │   └── realestate.py     # 네이버 부동산 뉴스
│   ├── ai/
│   │   ├── prompt.py         # 시스템 프롬프트
│   │   └── generate.py       # Gemini API 호출 → JSON 반환 + 미국 뉴스 번역
│   ├── templates/
│   │   └── briefing.html.j2  # Jinja2 HTML 템플릿
│   ├── utils/
│   │   ├── logger.py         # 로깅
│   │   ├── validator.py      # 데이터 검증 + 이상치 탐지
│   │   ├── notify.py         # 텔레그램 알림
│   │   └── qrcode_gen.py     # QR코드 생성
│   └── main.py               # 전체 파이프라인
├── output/
│   ├── index.html            # 최신 브리핑
│   └── archive/YYYY-MM-DD.html
├── cache/                    # Fallback용 JSON (git 제외)
├── requirements.txt
└── .gitignore
```

---

## 월 예상 비용

| 항목 | 비용 |
|------|------|
| Gemini API (gemini-2.5-flash) | 무료 (할당량 내) |
| FRED API | 무료 |
| ECOS API | 무료 |
| GitHub Actions | 무료 (Public repo) |
| GitHub Pages | 무료 |
| **합계** | **~$0 USD/월** |
