import os
import json
import requests
import time
import yfinance as yf
from datetime import datetime
from tradingview_ta import Interval, get_multiple_analysis
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- CONFIG ---
SCREENER = "india"
EXCHANGE = "NSE"
DATA_FILE = "stock_data_for_ai.json"

def fetch_nse_symbols():
    """Fetches Nifty 500 symbols."""
    headers = {'User-Agent': 'Mozilla/5.0'}
    url = "https://www.nseindia.com/api/equity-stockIndices?index=NIFTY%20500"
    session = requests.Session()
    session.get("https://www.nseindia.com", headers=headers, timeout=10)
    try:
        resp = session.get(url, headers=headers, timeout=10)
        return [item['symbol'] for item in resp.json().get('data', [])]
    except:
        return ["RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK"]

def get_technicals(tickers):
    """Batched technical analysis from TradingView."""
    tv_symbols = [f"{EXCHANGE}:{t.replace('&', 'and')}" for t in tickers]
    signals = []
    batch_size = 100
    for i in range(0, len(tv_symbols), batch_size):
        batch = tv_symbols[i:i + batch_size]
        try:
            res_1d = get_multiple_analysis(screener=SCREENER, interval=Interval.INTERVAL_1_DAY, symbols=batch)
            res_4h = get_multiple_analysis(screener=SCREENER, interval=Interval.INTERVAL_4_HOURS, symbols=batch)
            for key in res_1d.keys():
                analysis_1d = res_1d[key]
                if not analysis_1d: continue
                rec_1d = analysis_1d.summary["RECOMMENDATION"]
                if "STRONG" in rec_1d:
                    analysis_4h = res_4h.get(key)
                    signals.append({
                        "ticker": key.split(":")[1],
                        "recommendation_1d": rec_1d,
                        "recommendation_4h": analysis_4h.summary["RECOMMENDATION"] if analysis_4h else "NEUTRAL",
                        "double_confirmed": ("STRONG" in rec_1d and analysis_4h and "STRONG" in analysis_4h.summary["RECOMMENDATION"]),
                        "tech_1d": analysis_1d.indicators,
                        "tech_4h": analysis_4h.indicators if analysis_4h else {}
                    })
        except: continue
    return signals

def fetch_single_fundamental(s):
    """Worker function for single stock fundamental fetch."""
    try:
        ticker = s['ticker']
        stock = yf.Ticker(f"{ticker}.NS")
        info = stock.info
        return {
            "ticker": ticker,
            "price": round(s['tech_1d'].get('close', 0), 2),
            "is_double_confirmed": s['double_confirmed'],
            "tech_1d": {k: s['tech_1d'].get(k) for k in ['RSI', 'EMA20', 'EMA50', 'MACD.macd', 'MACD.signal']},
            "tech_4h": {k: s['tech_4h'].get(k) for k in ['RSI', 'EMA20', 'EMA50', 'MACD.macd', 'MACD.signal']},
            "sector": info.get('sector', 'Others'),
            "timestamp": time.time(),
            "fundamentals": {
                "trailingPE": info.get('trailingPE'),
                "forwardPE": info.get('forwardPE'),
                "debtToEquity": info.get('debtToEquity'),
                "returnOnEquity": info.get('returnOnEquity'),
            }
        }
    except: return None

def fetch_fundamentals_parallel(strong_movers):
    """Parallelized fundamental fetching using ThreadPoolExecutor."""
    payload = []
    # Using 5 workers for speed (Cloud friendly)
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_stock = {executor.submit(fetch_single_fundamental, s): s for s in strong_movers}
        for future in as_completed(future_to_stock):
            res = future.result()
            if res: payload.append(res)
    return payload

def run_scan():
    symbols = fetch_nse_symbols()
    strong_movers = get_technicals(symbols)
    # Parallelize the slowest part
    data = fetch_fundamentals_parallel(strong_movers)
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)
    return data

if __name__ == "__main__":
    run_scan()
