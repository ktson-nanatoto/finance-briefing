import random
import time
import requests
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]

NAVER_ECONOMY_URL = "https://news.naver.com/main/main.naver?mode=LSD&mid=shm&sid1=101"
REALESTATE_KEYWORDS = ["부동산", "아파트", "전세", "매매", "분양", "청약", "집값", "임대차", "재건축", "재개발"]
MAX_ARTICLES = 5


def _headers():
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Referer": "https://news.naver.com/",
    }


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=5, max=20))
def _fetch_realestate_news() -> list[dict]:
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
        if any(kw in title for kw in REALESTATE_KEYWORDS):
            seen.add(href)
            articles.append({"title": title, "url": href, "source": "네이버 부동산뉴스"})
            if len(articles) >= MAX_ARTICLES:
                break
    return articles


def fetch() -> dict:
    try:
        articles = _fetch_realestate_news()
        time.sleep(random.uniform(1, 2))
        return {"articles": articles}
    except Exception as e:
        return {"articles": [], "error": str(e)}
