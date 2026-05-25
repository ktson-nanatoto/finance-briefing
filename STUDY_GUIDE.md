# 재테크 브리핑 프로젝트 학습 가이드

이 문서는 프로젝트의 주요 개념과 구현 방식을 공부 목적으로 정리한 가이드입니다.

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
| `us_market.py` | S&P500, NASDAQ, DOW, VIX | Yahoo Finance 비공개 API |
| `kr_market.py` | KOSPI, KOSDAQ, 환율, 금, WTI | 네이버 모바일 API + Yahoo Finance |
| `macro.py` | 미국 기준금리, CPI, 10년 국채 / 한국 기준금리 | FRED API + ECOS API |
| `news.py` | 국내 경제 뉴스 / 해외 뉴스 | 네이버 HTML 파싱 + RSS feedparser |
| `realestate.py` | 부동산 뉴스 키워드 필터링 | 네이버 HTML 파싱 |

### Yahoo Finance 비공개 API
```python
# 공식 SDK 없이 직접 호출 — 언제든 차단될 수 있어 tenacity로 재시도 처리
url = f"https://query2.finance.yahoo.com/v8/finance/chart/{symbol}"
params = {"interval": "1d", "range": "2d"}
```

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

### ECOS API (한국은행)
```python
# URL 경로에 파라미터 포함하는 REST 방식
url = f"{ECOS_BASE}/{api_key}/json/kr/1/2/{stat_code}/MM/202301/209912/{item_code}"
# stat_code: 722Y001 = 기준금리 통계
# item_code: 0101000 = 기준금리 항목
```

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
result = response.text  # 모델 응답 텍스트
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
    {"title_kr": "한국어 번역", "title_en": "원문", "source": "CNBC"}
  ]
}
```

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

<!-- 필터 (내장 함수) -->
{{ item.price | round(2) }}   {# 소수점 2자리 반올림 #}
{{ item.change | abs }}        {# 절댓값 #}
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
def _fetch_ticker(symbol: str) -> dict:
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
      - run: python -m src.main          # 브리핑 생성
      - run: git add output/ && git commit && git push  # 결과 저장
      - uses: peaceiris/actions-gh-pages@v4  # Pages 배포
```

- **Secrets**: 민감한 API 키를 코드에 직접 쓰지 않고 `${{ secrets.KEY_NAME }}`으로 주입
- **permissions**: Pages 배포에는 `contents: write`, `pages: write` 권한 필요
- **cron 표기**: `분 시 일 월 요일` (UTC 기준)

---

## 8. 모델 선택 기준 (Gemini)

| 모델 | 속도 | 비용 | 적합한 용도 |
|------|------|------|-------------|
| gemini-2.5-flash | 빠름 | 무료(할당량) | 반복 자동화, JSON 추출, 번역 |
| gemini-2.5-pro | 느림 | 유료 | 복잡한 분석, 고난도 추론 |

이 프로젝트는 매일 반복되는 정형화된 JSON 출력 + 번역 작업이므로 **gemini-2.5-flash**가 최적.

---

## 9. 주요 의존 패키지 정리

| 패키지 | 용도 |
|--------|------|
| `google-generativeai` | Gemini API 클라이언트 |
| `requests` | HTTP 요청 |
| `beautifulsoup4` + `lxml` | HTML 파싱 (네이버 크롤링) |
| `feedparser` | RSS 피드 파싱 (CNBC, Yahoo) |
| `tenacity` | 네트워크 재시도 |
| `Jinja2` | HTML 템플릿 렌더링 |
| `qrcode` + `Pillow` | QR코드 이미지 생성 → base64 → HTML 인라인 삽입 |
| `python-dotenv` | `.env` 파일에서 환경변수 로드 |
