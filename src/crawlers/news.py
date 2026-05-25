import time
import random
import feedparser
import requests
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]

# 네이버 뉴스 경제 섹션 RSS
NAVER_ECONOMY_RSS = "https://feeds.feedburner.com/navernews/economy"
NAVER_ECONOMY_URL = "https://news.naver.com/main/main.naver?mode=LSD&mid=shm&sid1=101"

# 해외 뉴스 RSS
FOREIGN_FEEDS = {
    "cnbc_finance": "https://www.cnbc.com/id/10000664/device/rss/rss.html",
    "yahoo_finance": "https://finance.yahoo.com/rss/topstories",
}

MAX_ARTICLES = 5


def _headers():
    return {"User-Agent": random.choice(USER_AGENTS)}


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=5, max=20))
def _fetch_naver_economy() -> list[dict]:
    resp = requests.get(NAVER_ECONOMY_URL, headers=_headers(), timeout=10)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")
    seen = set()
    articles = []
    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        title = a.get_text(strip=True)
        if "/article/" not in href or not title or len(title) < 10:
            continue
        if href in seen:
            continue
        seen.add(href)
        articles.append({"title": title, "url": href, "source": "네이버 경제"})
        if len(articles) >= MAX_ARTICLES:
            break
    return articles


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=5, max=20))
def _fetch_rss(feed_url: str, source_name: str) -> list[dict]:
    feed = feedparser.parse(feed_url)
    articles = []
    for entry in feed.entries[:MAX_ARTICLES]:
        articles.append({
            "title": entry.get("title", ""),
            "url": entry.get("link", ""),
            "summary": entry.get("summary", "")[:200],
            "source": source_name,
        })
    return articles


def fetch() -> dict:
    result = {
        "kr_news": [],
        "us_news": [],
    }

    # 한국 뉴스
    try:
        result["kr_news"] = _fetch_naver_economy()
        time.sleep(random.uniform(1, 2))
    except Exception as e:
        result["kr_news"] = [{"error": str(e)}]

    # 해외 뉴스 (Reuters + CNBC)
    source_names = {
        "cnbc_finance": "CNBC",
        "yahoo_finance": "Yahoo Finance",
    }
    for key, url in FOREIGN_FEEDS.items():
        try:
            articles = _fetch_rss(url, source_names[key])
            result["us_news"].extend(articles)
            time.sleep(random.uniform(1, 2))
        except Exception as e:
            result["us_news"].append({"error": f"{key}: {str(e)}"})

    # 해외 뉴스 최대 10개로 제한
    result["us_news"] = result["us_news"][:10]
    return result
