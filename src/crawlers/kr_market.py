import random
import time
import requests
from tenacity import retry, stop_after_attempt, wait_exponential

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]

# 네이버 금융: 지수 (KOSPI/KOSDAQ)
NAVER_INDEX_URL = "https://m.stock.naver.com/api/index/{code}/basic"
INDEX_CODES = {"kospi": "KOSPI", "kosdaq": "KOSDAQ"}

# Yahoo Finance: 환율 + 원자재 (네이버 환율 API 지원 종료로 대체)
YAHOO_URL = "https://query2.finance.yahoo.com/v8/finance/chart/{symbol}"
YAHOO_TICKERS = {
    "usd_krw": "KRW=X",       # USD/KRW 환율
    "jpy_krw": "JPYKRW=X",    # JPY/KRW 환율 (100엔)
    "oil_wti": "CL=F",        # WTI 원유
    "gold": "GC=F",            # 금
}


def _naver_headers():
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Referer": "https://finance.naver.com/",
        "Accept": "application/json",
    }


def _yahoo_headers():
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "application/json",
    }


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=5, max=20))
def _fetch_naver_index(code: str) -> dict:
    url = NAVER_INDEX_URL.format(code=code)
    resp = requests.get(url, headers=_naver_headers(), timeout=10)
    resp.raise_for_status()
    data = resp.json()
    current = float(data.get("closePrice", "0").replace(",", ""))
    change = float(data.get("compareToPreviousClosePrice", "0").replace(",", ""))
    change_pct = float(data.get("fluctuationsRatio", "0"))
    return {"price": current, "change": change, "change_pct": change_pct}


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=5, max=20))
def _fetch_yahoo(symbol: str) -> dict:
    url = YAHOO_URL.format(symbol=symbol)
    resp = requests.get(url, headers=_yahoo_headers(), params={"interval": "1d", "range": "2d"}, timeout=10)
    resp.raise_for_status()
    meta = resp.json()["chart"]["result"][0]["meta"]
    prev_close = meta.get("chartPreviousClose") or meta.get("previousClose", 0)
    current = meta.get("regularMarketPrice", 0)
    change = current - prev_close
    change_pct = (change / prev_close * 100) if prev_close else 0
    return {
        "price": round(current, 4),
        "change": round(change, 4),
        "change_pct": round(change_pct, 2),
    }


def fetch() -> dict:
    result = {}

    for name, code in INDEX_CODES.items():
        try:
            result[name] = _fetch_naver_index(code)
            time.sleep(random.uniform(1, 2))
        except Exception as e:
            result[name] = {"error": str(e)}

    for name, symbol in YAHOO_TICKERS.items():
        try:
            result[name] = _fetch_yahoo(symbol)
            time.sleep(random.uniform(2, 3))
        except Exception as e:
            result[name] = {"error": str(e)}

    return result
