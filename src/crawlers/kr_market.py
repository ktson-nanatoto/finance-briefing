import random
import time
import requests
import yfinance as yf
from tenacity import retry, stop_after_attempt, wait_exponential

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]

NAVER_INDEX_URL = "https://m.stock.naver.com/api/index/{code}/basic"
INDEX_CODES = {"kospi": "KOSPI", "kosdaq": "KOSDAQ"}

YAHOO_TICKERS = {
    "usd_krw": "KRW=X",
    "jpy_krw": "JPYKRW=X",
    "oil_wti": "CL=F",
    "gold": "GC=F",
}

# JPYKRW=X는 1엔 기준이므로 100엔 기준으로 변환
JPY_SCALE_100 = {"jpy_krw"}


def _naver_headers():
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Referer": "https://finance.naver.com/",
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


def _fetch_yahoo(symbol: str) -> dict:
    ticker = yf.Ticker(symbol)
    info = ticker.fast_info
    current = info.last_price
    prev_close = info.previous_close
    if not current or not prev_close:
        raise ValueError(f"No data for {symbol}")
    change = current - prev_close
    change_pct = (change / prev_close) * 100
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
            data = _fetch_yahoo(symbol)
            if name in JPY_SCALE_100:
                data = {
                    "price": round(data["price"] * 100, 2),
                    "change": round(data["change"] * 100, 2),
                    "change_pct": data["change_pct"],
                }
            result[name] = data
        except Exception as e:
            result[name] = {"error": str(e)}

    return result
