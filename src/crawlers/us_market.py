import random
import time
import requests
from tenacity import retry, stop_after_attempt, wait_exponential

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]

TICKERS = {
    "sp500": "^GSPC",
    "nasdaq": "^IXIC",
    "dow": "^DJI",
    "vix": "^VIX",
}


def _headers():
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "application/json",
    }


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=5, max=20))
def _fetch_ticker(symbol: str) -> dict:
    url = f"https://query2.finance.yahoo.com/v8/finance/chart/{symbol}"
    params = {"interval": "1d", "range": "2d"}
    resp = requests.get(url, headers=_headers(), params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    meta = data["chart"]["result"][0]["meta"]
    prev_close = meta.get("chartPreviousClose") or meta.get("previousClose", 0)
    current = meta.get("regularMarketPrice", 0)
    change = current - prev_close
    change_pct = (change / prev_close * 100) if prev_close else 0
    return {
        "price": round(current, 2),
        "change": round(change, 2),
        "change_pct": round(change_pct, 2),
        "prev_close": round(prev_close, 2),
    }


def fetch() -> dict:
    result = {}
    for name, symbol in TICKERS.items():
        try:
            result[name] = _fetch_ticker(symbol)
            time.sleep(random.uniform(2, 3))
        except Exception as e:
            result[name] = {"error": str(e)}
    return result
