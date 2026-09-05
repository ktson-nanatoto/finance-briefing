import os
import random
import time
import requests
import yfinance as yf
from datetime import datetime, timedelta
from tenacity import retry, stop_after_attempt, wait_exponential

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]

NAVER_INDEX_URL = "https://m.stock.naver.com/api/index/{code}/basic"
INDEX_CODES = {"kospi": "KOSPI", "kosdaq": "KOSDAQ"}

YAHOO_TICKERS = {
    "oil_wti": "CL=F",
    "gold": "GC=F",
}

# 한국은행 ECOS 환율 (731Y001, 매매기준율, 일별)
ECOS_BASE = "https://ecos.bok.or.kr/api/StatisticSearch"
ECOS_FX = {
    "usd_krw": "0000001",  # 원/미국달러(매매기준율)
    "jpy_krw": "0000002",  # 원/일본엔(100엔)
}


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


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=5, max=20))
def _fetch_ecos_fx(item_code: str) -> dict:
    api_key = os.environ.get("ECOS_API_KEY", "")
    if not api_key:
        return {"error": "ECOS_API_KEY not set"}
    today = datetime.now().strftime("%Y%m%d")
    start = (datetime.now() - timedelta(days=14)).strftime("%Y%m%d")
    url = f"{ECOS_BASE}/{api_key}/json/kr/1/10/731Y001/D/{start}/{today}/{item_code}"
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    rows = sorted(
        resp.json().get("StatisticSearch", {}).get("row", []),
        key=lambda x: x["TIME"],
        reverse=True,
    )
    if len(rows) < 2:
        raise ValueError(f"ECOS 환율 데이터 부족: {item_code}")
    latest, previous = rows[0], rows[1]
    value = float(latest["DATA_VALUE"])
    prev_value = float(previous["DATA_VALUE"])
    change = round(value - prev_value, 2)
    return {
        "price": value,
        "change": change,
        "change_pct": round(change / prev_value * 100, 2),
        "date": latest["TIME"],
    }


def fetch() -> dict:
    result = {}

    for name, code in INDEX_CODES.items():
        try:
            result[name] = _fetch_naver_index(code)
            time.sleep(random.uniform(1, 2))
        except Exception as e:
            result[name] = {"error": str(e)}

    for name, item_code in ECOS_FX.items():
        try:
            result[name] = _fetch_ecos_fx(item_code)
        except Exception as e:
            result[name] = {"error": str(e)}

    for name, symbol in YAHOO_TICKERS.items():
        try:
            result[name] = _fetch_yahoo(symbol)
        except Exception as e:
            result[name] = {"error": str(e)}

    return result
