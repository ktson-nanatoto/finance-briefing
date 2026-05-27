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
    - cron: '30 21 * * *'  # UTC 21:30 = KST 06:30 (모닝 브리핑)
    - cron: '0 3 * * *'    # UTC 03:00 = KST 12:00 (장중 업데이트)
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
- **스케줄 첫 활성화**: 새로 만든 워크플로우는 `workflow_dispatch`로 한 번 수동 실행해야 스케줄이 활성화됨

### 수동 실행 vs Re-run all jobs 차이
| | 설명 |
|---|---|
| **Run workflow** | 최신 코드로 새로 실행 (코드 변경 후 테스트할 때) |
| **Re-run all jobs** | 이전 실행을 그대로 다시 돌림 (코드 변경 반영 안 됨) |

### 조건부 스텝 — 트리거 이벤트에 따라 분기
```yaml
- name: Run crawler
  if: github.event_name == 'schedule' || github.event_name == 'workflow_dispatch'
  run: python crawler.py
```

### 스텝 결과를 다음 스텝에 전달 (step outputs)
```yaml
- name: Check data changed
  id: commit          # id 부여
  run: |
    if git diff --cached --quiet; then
      echo "changed=false" >> $GITHUB_OUTPUT
    else
      git commit -m "update"
      echo "changed=true" >> $GITHUB_OUTPUT
    fi

- name: Notify
  if: steps.commit.outputs.changed == 'true'   # 앞 스텝 결과 참조
  run: python notify.py
```

### GITHUB_TOKEN push는 같은 워크플로우를 재트리거하지 않음
GitHub Actions 내에서 `GITHUB_TOKEN`으로 push하면 **동일 레포의 다른 워크플로우가 트리거되지 않음** (무한 루프 방지 정책).  
→ 크롤링 후 커밋 + 배포를 **같은 워크플로우 안**에서 처리해야 하는 이유.

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

### 엔화 환율 이상 표시 (100엔 당 9.5원?)
**증상**: JPY/KRW가 9.5로 표시 — 실제는 950원  
**원인**: Yahoo Finance `JPYKRW=X` 티커는 **1엔 기준** 반환 (약 9.5). 대시보드 라벨은 "100엔" 기준  
**해결**: 크롤러에서 price · change에 ×100 적용, change_pct는 그대로 (비율이므로 변환 불필요)
```python
if name == "jpy_krw":
    data["price"] = round(data["price"] * 100, 2)
    data["change"] = round(data["change"] * 100, 2)
    # change_pct는 % 단위라 그대로
```

### 아침/오후 브리핑 구분 (report_type 패턴)
**배경**: 06:30 실행 시 한국 장 미개장 → 전일 종가 / 12:00 실행 시 장중 실시간 데이터  
**구현**: `main.py`에서 현재 시각 기준으로 report_type 결정, 프롬프트/알림 분기
```python
report_type = "afternoon" if now.hour >= 10 else "morning"
archive_key = f"{date_str}-{'1200' if report_type == 'afternoon' else '0630'}"
```
아카이브 파일명에 시각 포함 이유: 같은 날 두 번 실행 시 오전 파일을 오후가 덮어쓰는 것 방지.

### GitHub Actions 스케줄 지연 / 미실행
**증상**: 설정한 시간에 워크플로우가 실행되지 않거나, 수 시간 지연됨  
**원인 1**: GitHub 서버 부하 — 스케줄 트리거는 최대 수 시간 지연 가능 (공식 문서 명시)  
**원인 2**: 새 스케줄 첫 1~2일 — cron을 새로 만들거나 변경한 직후에는 스킵되는 경우 잦음  
**확인 방법**: GitHub API로 최근 실행 이력 조회
```bash
curl -s -H "Authorization: token $TOKEN" \
  "https://api.github.com/repos/{owner}/{repo}/actions/runs?per_page=5"
```
**대응**: `workflow_dispatch`로 수동 트리거 후 다음 날부터 정상 여부 확인. 이틀 이상 지속되면 외부 cron 서비스(예: cron-job.org)로 보완.

### GitHub Pages CDN 캐시로 인한 구 버전 표시
**증상**: 워크플로우 성공 후에도 브라우저에서 이전 날짜·이전 데이터가 보임  
**원인**: GitHub Pages는 CDN을 통해 서빙되어 배포 직후에도 캐시된 이전 버전이 보일 수 있음  
**해결**:
- 모바일: 브라우저 새로고침 길게 누르기
- PC: `Ctrl+Shift+R` (캐시 무시 강제 새로고침)
- 확인 방법: HTML 파일 내용은 `output/archive/` 에서 직접 확인 가능

---

## 12. busan_radar 프로젝트 — 부산 청약 레이더

### 전체 구조
```
[호갱노노 API] 부산 청약 목록 (requests, 10~20초)
       +
[호갱노노 상세 페이지] 상위 10개 Selenium 크롤링 (2~3분)
       ↓
[data.json] 저장
       ↓ git push
[GitHub Actions] 자동 실행
       ↓
[GitHub Pages] dashboard.html + data.json 배포
       ↓
[Telegram] 그룹 알림 발송
```

### 크롤링 두 가지 모드
| 모드 | 방식 | 시간 | 가져오는 것 |
|------|------|------|------------|
| `--no-detail` | requests API만 | 10~20초 | 단지명, 지역, 청약일, D-day, 상태, 경쟁률 |
| 풀 크롤링 (기본) | API + Selenium | 2~3분 | 위 항목 + 건설사/시행사, 좌표, 입주시기, 리뷰, 뉴스 |

### GitHub Actions에서 Selenium 사용하기
ubuntu-latest에 Chrome이 내장되어 있고, selenium 4.x의 `selenium-manager`가 chromedriver를 자동 다운로드.

```yaml
- name: Install Chrome
  run: |
    sudo apt-get update
    sudo apt-get install -y google-chrome-stable

- name: Install dependencies
  run: pip install requests selenium

- name: Run crawler
  timeout-minutes: 10     # Selenium 크롤링 시간 여유 확보
  run: python crawler.py
```

Selenium Options에 반드시 포함해야 할 옵션 (CI 환경):
```python
options.add_argument("--headless")           # 브라우저 UI 없이 실행
options.add_argument("--no-sandbox")         # 권한 이슈 방지
options.add_argument("--disable-dev-shm-usage")  # 메모리 이슈 방지
```

### GitHub Pages에서 정적 데이터 로드
Flask 서버 없이 `data.json`을 직접 fetch하도록 수정:
```javascript
// 변경 전 (Flask 서버 필요)
const res = await fetch('/api/data');

// 변경 후 (정적 파일 직접 로드)
const res = await fetch('data.json');
```

로컬 Flask 서버와 동시 호환하려면 `/data.json` 라우트 추가:
```python
@app.route("/data.json")
@app.route("/api/data")
def api_data():
    return jsonify(load_data())
```

### 로컬/Pages 환경 분기
크롤 버튼처럼 서버 기능이 필요한 UI는 로컬에서만 노출:
```javascript
(async () => {
  if (location.hostname === 'localhost' || location.hostname === '127.0.0.1') {
    document.getElementById('btn-crawl').style.display = '';
  }
  await fetchData();
})();
```

### GitHub Secrets API로 시크릿 등록 자동화
```python
from nacl import encoding, public
import base64

def encrypt_secret(public_key_b64, secret_value):
    pk = public.PublicKey(public_key_b64.encode(), encoding.Base64Encoder())
    box = public.SealedBox(pk)
    return base64.b64encode(box.encrypt(secret_value.encode())).decode()

# 1. 레포 public key 가져오기
# GET /repos/{owner}/{repo}/actions/secrets/public-key

# 2. 값 암호화 후 등록
# PUT /repos/{owner}/{repo}/actions/secrets/{secret_name}
# body: {"encrypted_value": "...", "key_id": "..."}
```
GitHub Secrets는 API로 읽을 수 없음 (쓰기만 가능). 값 확인은 `.env` 파일 참조.
