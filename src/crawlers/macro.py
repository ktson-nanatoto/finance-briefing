import os
import requests
from tenacity import retry, stop_after_attempt, wait_exponential

FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"
ECOS_BASE = "https://ecos.bok.or.kr/api/StatisticSearch"

# FRED 시리즈 코드
FRED_SERIES = {
    "us_fed_rate": "FEDFUNDS",    # 미국 기준금리
    "us_cpi": "CPIAUCSL",         # 미국 CPI
    "us_10y_yield": "DGS10",      # 미국 10년 국채 금리
}

# 한국은행 ECOS 통계 코드
# 722Y001 / 0101000 = 기준금리
ECOS_STATS = {
    "kr_base_rate": {"stat_code": "722Y001", "item_code": "0101000"},
}


def _fred_headers():
    return {"Accept": "application/json"}


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=5, max=20))
def _fetch_fred(series_id: str) -> dict:
    api_key = os.environ.get("FRED_API_KEY", "")
    if not api_key:
        return {"error": "FRED_API_KEY not set"}
    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "sort_order": "desc",
        "limit": 2,
    }
    resp = requests.get(FRED_BASE, headers=_fred_headers(), params=params, timeout=10)
    resp.raise_for_status()
    observations = resp.json().get("observations", [])
    if not observations:
        return {"error": "no data"}
    latest = observations[0]
    previous = observations[1] if len(observations) > 1 else None
    value = float(latest["value"]) if latest["value"] != "." else None
    prev_value = float(previous["value"]) if previous and previous["value"] != "." else None
    change = round(value - prev_value, 4) if value is not None and prev_value is not None else None
    return {
        "value": value,
        "date": latest["date"],
        "change": change,
    }


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=5, max=20))
def _fetch_ecos(stat_code: str, item_code: str) -> dict:
    api_key = os.environ.get("ECOS_API_KEY", "")
    if not api_key:
        return {"error": "ECOS_API_KEY not set"}
    url = f"{ECOS_BASE}/{api_key}/json/kr/1/2/{stat_code}/MM/202301/209912/{item_code}"
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    rows = data.get("StatisticSearch", {}).get("row", [])
    if not rows:
        return {"error": "no data"}
    # 최신순 정렬
    rows_sorted = sorted(rows, key=lambda x: x.get("TIME", ""), reverse=True)
    latest = rows_sorted[0]
    previous = rows_sorted[1] if len(rows_sorted) > 1 else None
    value = float(latest["DATA_VALUE"]) if latest.get("DATA_VALUE") else None
    prev_value = float(previous["DATA_VALUE"]) if previous and previous.get("DATA_VALUE") else None
    change = round(value - prev_value, 4) if value is not None and prev_value is not None else None
    return {
        "value": value,
        "date": latest.get("TIME"),
        "change": change,
    }


def fetch() -> dict:
    result = {}

    for name, series_id in FRED_SERIES.items():
        try:
            result[name] = _fetch_fred(series_id)
        except Exception as e:
            result[name] = {"error": str(e)}

    for name, codes in ECOS_STATS.items():
        try:
            result[name] = _fetch_ecos(codes["stat_code"], codes["item_code"])
        except Exception as e:
            result[name] = {"error": str(e)}

    return result
