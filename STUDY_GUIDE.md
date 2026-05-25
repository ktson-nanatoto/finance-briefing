# 재테크 브리핑 프로젝트 학습 가이드

이 문서는 프로젝트의 주요 개념, 구현 방식, 트러블슈팅을 공부 목적으로 정리한 가이드입니다.

---

## 1. 전체 데이터 흐름

```
[GitHub Actions 스케줄] 07:30 KST
        ↓
[크롤러 5개] 데이터 수집
        ↓
[validator.py] 데이터 검증 → 실패 시 cache/ fallback
        ↓
[Gemini API] 분석 JSON 생성 + 미국 뉴스 한국어 번역
        ↓
[Jinja2] HTML 렌더링
        ↓
[output/index.html] 저장 → git commit & push
        ↓
[GitHub Pages] 자동 배포 (gh-pages 브랜치)
        ↓
[텔레그램] 알림 발송
```

---

## 2. 크롤러별 데이터 소스

| 파일 | 데이터 | API/방식 |
|------|--------|----------|
| `us_market.py` | S&P500, NASDAQ, DOW, VIX | yfinance 라이브러리 |
| `kr_market.py` | KOSPI, KOSDAQ, 환율, 금, WTI | 네이버 모바일 API + yfinance |
| `macro.py` | 미국 기준금리, CPI, 10년 국채 / 한국 기준금리 | FRED API + ECOS API |
| `news.py` | 국내 경제 뉴스 / 해외 뉴스 | 네이버 HTML 파싱 + RSS feedparser |
| `realestate.py` | 부동산 뉴스 키워드 필터링 | 네이버 HTML 파싱 |

### yfinance 라이브러리 (Yahoo Finance)
```python
import yfinance as yf

ticker = yf.Ticker("^GSPC")   # S&P500
info = ticker.fast_info
current = info.last_price
prev_close = info.previous_close
```
직접 API 호출 대신 yfinance를 사용하는 이유 → 아래 트러블슈팅 참고

### FRED API (미국 연방준비은행)
```python
# 무료 API, 최신 2개 데이터 가져와 전일 대비 변화량 계산
params = {
    "series_id": "FEDFUNDS",  # 시리즈 코드
    "api_key": api_key,
    "sort_order": "desc",
    "limit": 2,
}
```
발급: https://fred.stlouisfed.org/docs/api/api_key.html (무료, 이메일 인증만)

### ECOS API (한국은행)
```python
# URL 경로에 파라미터 포함하는 REST 방식
url = f"{ECOS_BASE}/{api_key}/json/kr/1/2/{stat_code}/MM/202301/209912/{item_code}"
# stat_code: 722Y001 = 기준금리 통계
# item_code: 0101000 = 기준금리 항목
```
발급: https://ecos.bok.or.kr/api/#/DevGuide/APIKeyApply (무료, 회원가입만)

---

## 3. Gemini API 핵심 개념

### 기본 사용 패턴
```python
import google.generativeai as genai

genai.configure(api_key="...")

model = genai.GenerativeModel(
    model_name="gemini-2.5-flash",
    system_instruction="시스템 프롬프트 (AI 역할/규칙 정의)",
    generation_config=genai.GenerationConfig(
        max_output_tokens=4096,
        temperature=0.3,  # 낮을수록 일관된 출력 (0=결정론적, 1=창의적)
    ),
)

response = model.generate_content("사용자 메시지")
result = response.text
```

### JSON 출력 강제하기
LLM에게 정해진 JSON 스키마만 출력하도록 하는 패턴:
```
# 시스템 프롬프트에 명시
"JSON 외 어떠한 텍스트(마크다운 코드블록 포함)도 출력하지 마세요."

# 방어 코드: 모델이 ```json ... ``` 으로 감쌀 경우 처리
if raw.startswith("```"):
    raw = raw.split("```")[1]
    if raw.startswith("json"):
        raw = raw[4:]
```

### 번역 + 분석 한 번에 처리
별도 API 호출 없이 분석 JSON 안에 번역 결과를 포함시켜 비용/속도 절감:
```json
{
  "headline": "분석 결과...",
  "us_news_kr": [
    {"title_kr": "한국어 번역", "title_en": "원문", "source": "CNBC", "url": "https://..."}
  ]
}
```
프롬프트에 `us_news 항목의 title을 한국어로 번역, url은 원문 그대로 복사` 라고 명시하면 Claude/Gemini가 번역과 URL 복사를 함께 처리함.

### 토큰 사용량 확인
```python
usage = response.usage_metadata
logger.info("입력: %d, 출력: %d", usage.prompt_token_count, usage.candidates_token_count)
```

---

## 4. Jinja2 템플릿 엔진

HTML을 Python 변수로 동적 생성하는 템플릿 시스템.

```python
from jinja2 import Environment, FileSystemLoader

env = Environment(loader=FileSystemLoader("src/templates"))
template = env.get_template("briefing.html.j2")
html = template.render(date=date_str, data=data, analysis=analysis)
```

템플릿 문법:
```html
<!-- 변수 출력 -->
{{ analysis.headline }}

<!-- 조건문 -->
{% if item.change > 0 %}up{% else %}down{% endif %}

<!-- 반복문 -->
{% for issue in analysis.key_issues %}
<li>{{ issue }}</li>
{% endfor %}

<!-- 필터 -->
{{ item.price | round(2) }}
{{ item.change | abs }}

<!-- 하이퍼링크 (새 탭, 스타일 유지) -->
<a href="{{ article.url }}" target="_blank" rel="noopener" style="color:inherit;text-decoration:none;">
  {{ article.title }}
</a>
```

---

## 5. Fallback 전략

데이터 수집 실패 시 서비스 중단을 막는 방어 로직:

```
[크롤러 실패]
    ↓
[validator.py] 필수 필드 (usd_krw, kospi, sp500) 체크
    ↓ 실패
[cache/YYYY-MM-DD.json] 전날 데이터로 대체
    ↓ 캐시도 없으면
[수집된 부분 데이터로 진행] + 경고 배너 표시
```

```python
# 뉴스는 최신 유지, 시세만 캐시로 교체
for key in ("us_market", "kr_market", "macro"):
    data[key] = cached.get(key, data[key])
```

---

## 6. tenacity 재시도 패턴

네트워크 요청 실패 시 자동 재시도:

```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(3),           # 최대 3회 시도
    wait=wait_exponential(min=5, max=20)  # 5초 → 10초 → 20초 지수 백오프
)
def _fetch_naver_index(code: str) -> dict:
    ...
```

지수 백오프(exponential backoff): 재시도마다 대기 시간을 2배씩 늘려 서버 부하 방지.

---

## 7. GitHub Actions 워크플로우

```yaml
on:
  schedule:
    - cron: '30 22 * * *'  # UTC 22:30 = KST 07:30
  workflow_dispatch:         # 수동 실행 허용

jobs:
  build-and-deploy:
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
      - run: pip install -r requirements.txt
      - run: python -m src.main
      - run: git add output/ && git commit && git push
      - uses: peaceiris/actions-gh-pages@v4
```

- **Secrets**: `${{ secrets.KEY_NAME }}` 으로 API 키 주입 — 코드에 직접 쓰면 절대 안 됨
- **permissions**: Pages 배포에는 `contents: write`, `pages: write` 권한 필요
- **cron 표기**: `분 시 일 월 요일` (UTC 기준) — KST는 UTC+9이므로 -9시간
- **수동 실행**: Actions 탭 → Daily Finance Briefing → Run workflow 버튼

### 수동 실행 vs Re-run all jobs 차이
| | 설명 |
|---|---|
| **Run workflow** | 최신 코드로 새로 실행 (코드 변경 후 테스트할 때) |
| **Re-run all jobs** | 이전 실행을 그대로 다시 돌림 (코드 변경 반영 안 됨) |

---

## 8. 텔레그램 봇 설정

### 봇 생성
1. `@BotFather` → `/newbot` → 이름/username 설정 → 토큰 발급
2. `@userinfobot` → `/start` → 개인 chat ID 확인

### 그룹 chat ID 찾는 방법
1. 그룹에 봇 추가 (메인 검색창에서 `@봇username` 검색 → 프로필 → Add to Group)
2. 그룹에서 아무 메시지나 전송
3. 아래 API로 chat ID 확인:
```bash
curl "https://api.telegram.org/bot{토큰}/getUpdates"
```
반환 JSON의 `message.chat.id` 값이 그룹 ID (항상 음수 `-`로 시작)

### 테스트 메시지 직접 보내기
```bash
curl "https://api.telegram.org/bot{토큰}/sendMessage" \
  -d "chat_id={chat_id}&text=테스트 메시지"
```

---

## 9. 모델 선택 기준 (Gemini)

| 모델 | 속도 | 비용 | 적합한 용도 |
|------|------|------|-------------|
| gemini-2.5-flash | 빠름 | 무료(할당량) | 반복 자동화, JSON 추출, 번역 |
| gemini-2.5-pro | 느림 | 유료 | 복잡한 분석, 고난도 추론 |

이 프로젝트는 매일 반복되는 정형화된 JSON 출력 + 번역 작업이므로 **gemini-2.5-flash**가 최적.

---

## 10. 주요 의존 패키지 정리

| 패키지 | 용도 |
|--------|------|
| `google-generativeai` | Gemini API 클라이언트 |
| `yfinance` | Yahoo Finance 주가/환율/원자재 데이터 |
| `requests` | HTTP 요청 (네이버, FRED, ECOS) |
| `beautifulsoup4` + `lxml` | HTML 파싱 (네이버 크롤링) |
| `feedparser` | RSS 피드 파싱 (CNBC, Yahoo) |
| `tenacity` | 네트워크 재시도 |
| `Jinja2` | HTML 템플릿 렌더링 |
| `qrcode` + `Pillow` | QR코드 이미지 생성 → base64 → HTML 인라인 삽입 |
| `python-dotenv` | `.env` 파일에서 환경변수 로드 |

---

## 11. 트러블슈팅 모음

### Yahoo Finance GitHub Actions IP 차단
**증상**: `필수 데이터 누락: us_market.sp500` 경고, DOW/VIX/WTI도 RetryError  
**원인**: Yahoo Finance 비공식 API가 GitHub Actions 서버 IP를 간헐적으로 차단  
**해결**: `requests` 직접 호출 → `yfinance` 라이브러리로 교체 (쿠키/인증 자동 처리)

```python
# 변경 전 (차단됨)
resp = requests.get("https://query2.finance.yahoo.com/v8/finance/chart/^GSPC", ...)

# 변경 후 (안정적)
import yfinance as yf
ticker = yf.Ticker("^GSPC")
current = ticker.fast_info.last_price
```

### FRED/ECOS API 키 적용 안 됨
**증상**: `"error": "FRED_API_KEY not set"` — API 키를 .env에 넣었는데도 에러  
**원인**: `.env`는 로컬 실행용, GitHub Actions는 **Secrets**에서 별도로 주입  
**해결**: 레포 → Settings → Secrets and variables → Actions → New repository secret

### 텔레그램 그룹 채팅 ID 찾기
**증상**: 봇을 그룹에 추가했는데 개인 채팅으로만 알림 옴  
**원인**: `TELEGRAM_CHAT_ID`가 개인 chat ID로 설정되어 있음  
**해결**: 
1. 봇을 그룹에 추가 후 그룹에서 메시지 전송
2. `getUpdates` API로 그룹 chat ID 확인 (음수값)
3. GitHub Secrets의 `TELEGRAM_CHAT_ID` 업데이트

### 텔레그램에서 봇 검색 안 됨
**증상**: 그룹 멤버 추가 화면에서 봇이 검색 안 됨  
**해결**: 그룹 내 검색 대신 **메인 검색창**에서 `@봇username` 검색 → 프로필 → Add to Group

### GitHub Pages 404 에러
**증상**: `https://username.github.io/finance-briefing/` 접속 시 404  
**원인**: Pages Source가 설정되지 않음 (gh-pages 브랜치는 생성됐지만 Pages 미활성화)  
**해결**: 레포 → Settings → Pages → Source: `gh-pages` 브랜치 선택 → Save

### git push 거절 (fetch first)
**증상**: `push` 시 `rejected - fetch first` 에러  
**원인**: GitHub Actions가 output/ 커밋을 원격에 추가해서 로컬보다 앞서 있음  
**해결**:
```bash
git pull --rebase origin main && git push origin main
```
