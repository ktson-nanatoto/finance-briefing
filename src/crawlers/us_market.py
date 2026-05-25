import yfinance as yf

TICKERS = {
    "sp500": "^GSPC",
    "nasdaq": "^IXIC",
    "dow": "^DJI",
    "vix": "^VIX",
}


def _fetch_ticker(symbol: str) -> dict:
    ticker = yf.Ticker(symbol)
    info = ticker.fast_info
    current = info.last_price
    prev_close = info.previous_close
    if not current or not prev_close:
        raise ValueError(f"No data for {symbol}")
    change = current - prev_close
    change_pct = (change / prev_close) * 100
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
        except Exception as e:
            result[name] = {"error": str(e)}
    return result
