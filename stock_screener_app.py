import streamlit as st
import pandas as pd
import json
import os
import time
import requests
import yfinance as yf
import sys
import random
from datetime import datetime
from tradingview_ta import Interval, get_multiple_analysis
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- CONFIGURATION ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, "stock_data_for_ai.json")
SYMBOL_CACHE = os.path.join(BASE_DIR, "nse_symbols_cache.json")
VCP_SCRIPT = os.path.join(BASE_DIR, "institutional-trader/scripts/vcp_analyzer.py")
FUND_SCRIPT = os.path.join(BASE_DIR, "institutional-trader/scripts/fundamental_ranker.py")

st.set_page_config(page_title="Institutional Stock Screener", layout="wide")

# --- SCANNER LOGIC (High Stability Mode) ---

def fetch_nse_symbols():
    """Uses cache first on Cloud to avoid NSE API blocks."""
    if os.path.exists(SYMBOL_CACHE):
        try:
            with open(SYMBOL_CACHE, 'r') as f:
                cache = json.load(f)
                syms = cache.get('symbols', [])
                if syms: return syms
        except: pass
    
    # Minimal fallback if cache fails
    return ["RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK", "AXISBANK", "TITAN", "HAL", "BEL", "BSE"]

def run_integrated_scan():
    progress_bar = st.sidebar.progress(0)
    status_text = st.sidebar.empty()
    
    tickers = fetch_nse_symbols()
    tv_symbols = [f"NSE:{t.replace('&', 'and')}" for t in tickers]
    
    signals = []
    # Small batches + Jitter for Cloud Stability
    batch_size = 20 
    
    for i in range(0, len(tv_symbols), batch_size):
        batch = tv_symbols[i:i + batch_size]
        status_text.text(f"Scanning batch {i//batch_size + 1} of {len(tv_symbols)//batch_size + 1}...")
        progress = min(1.0, (i + batch_size) / len(tv_symbols))
        progress_bar.progress(progress)
        
        try:
            res_1d = get_multiple_analysis(screener="india", interval=Interval.INTERVAL_1_DAY, symbols=batch)
            res_4h = get_multiple_analysis(screener="india", interval=Interval.INTERVAL_4_HOURS, symbols=batch)
            
            if res_1d:
                for key in res_1d.keys():
                    analysis_1d = res_1d[key]
                    if not analysis_1d: continue
                    rec_1d = analysis_1d.summary["RECOMMENDATION"]
                    if "BUY" in rec_1d:
                        analysis_4h = res_4h.get(key)
                        signals.append({
                            "ticker": key.split(":")[1],
                            "recommendation_1d": rec_1d,
                            "double_confirmed": ("STRONG" in rec_1d and analysis_4h and "STRONG" in analysis_4h.summary["RECOMMENDATION"]),
                            "tech_1d": analysis_1d.indicators,
                            "tech_4h": analysis_4h.indicators if analysis_4h else {}
                        })
            
            # Small "Jitter" delay to avoid being flagged as a bot
            time.sleep(random.uniform(0.5, 1.5)) 
            
        except Exception as e:
            continue
    
    if not signals:
        status_text.empty()
        progress_bar.empty()
        return []

    status_text.text(f"Found {len(signals)} trends. Fetching quality metrics...")
    
    def fetch_fund(s):
        try:
            ticker = s['ticker']
            stock = yf.Ticker(f"{ticker}.NS")
            info = stock.info
            # Avoid hitting yfinance too hard
            time.sleep(random.uniform(0.1, 0.3))
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

    final_data = []
    # Reduced workers for cloud stability (prevents yfinance block)
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(fetch_fund, s) for s in signals]
        for f in as_completed(futures):
            res = f.result()
            if res: final_data.append(res)
            
    with open(DATA_FILE, 'w') as f:
        json.dump(final_data, f, indent=2)
    
    status_text.empty()
    progress_bar.empty()
    return final_data

# --- DATA PROCESSING ---

import subprocess

def run_script(script_path, input_file):
    try:
        result = subprocess.run([sys.executable, script_path, input_file], capture_output=True, text=True)
        if result.returncode == 0:
            return json.loads(result.stdout)
        else: return []
    except: return []

def load_data():
    if not os.path.exists(DATA_FILE): return None
    with open(DATA_FILE, "r") as f:
        try: raw_data = json.load(f)
        except: return None
    
    if not raw_data:
        return pd.DataFrame(columns=["Ticker", "Sector", "Combined Score", "VCP Score", "Fund Score"])

    last_updated = raw_data[0].get('timestamp', 0)
    age_hours = (time.time() - last_updated) / 3600
    if age_hours > 4: st.sidebar.warning(f"⚠️ Data is {round(age_hours, 1)}h old.")
    else: st.sidebar.success(f"✅ Data is fresh ({round(age_hours, 1)}h old)")

    vcp_results = run_script(VCP_SCRIPT, DATA_FILE)
    fund_results = run_script(FUND_SCRIPT, DATA_FILE)
    
    merged = []
    vcp_dict = {item['ticker']: item for item in vcp_results}
    fund_dict = {item['ticker']: item for item in fund_results}
    
    for stock in raw_data:
        ticker = stock['ticker']
        vcp = vcp_dict.get(ticker, {"vcp_score": 0, "stage_2": False, "tight_action": False, "accumulating": False})
        fund = fund_dict.get(ticker, {"fundamental_score": 0, "pe": None, "roe": None, "debt": None})
        
        quant_score = 50 
        if stock.get('is_double_confirmed'): quant_score += 20
        if vcp['stage_2'] and fund['fundamental_score'] > 50: quant_score += 20
        
        combined_score = (fund['fundamental_score'] * 0.5) + (vcp['vcp_score'] * 0.3) + (quant_score * 0.2)
        
        merged.append({
            "Ticker": ticker, "Sector": stock.get('sector', 'Others'),
            "Price": stock.get('price', 0), "VCP Score": vcp['vcp_score'],
            "Fund Score": fund['fundamental_score'], "Quant Score": quant_score,
            "Combined Score": round(combined_score, 2),
            "Stage 2": "✅" if vcp['stage_2'] else "❌", "Tight": "✅" if vcp['tight_action'] else "❌",
            "ROE (%)": fund['roe'], "PE": fund['pe'], "Debt/Eq": fund['debt'],
            "Double Conf": "✅" if stock.get('is_double_confirmed') else "❌"
        })
    return pd.DataFrame(merged)

# --- UI COMPONENTS ---

st.title("🏛️ Institutional-Grade Stock Screener")
st.markdown("---")

with st.sidebar:
    st.header("Settings")
    
    # Show Last Updated info prominently
    if os.path.exists(DATA_FILE):
        # 1. Get file modification time as primary reliable source
        mtime = os.path.getmtime(DATA_FILE)
        
        # 2. Try to get timestamp from JSON if it exists
        try:
            with open(DATA_FILE, "r") as f:
                raw_data = json.load(f)
                if raw_data and 'timestamp' in raw_data[0]:
                    mtime = raw_data[0]['timestamp']
        except:
            pass
            
        # 3. Convert to IST (UTC + 5:30)
        from datetime import timedelta, timezone
        ist_tz = timezone(timedelta(hours=5, minutes=30))
        dt_ist = datetime.fromtimestamp(mtime, tz=ist_tz)
        st.info(f"📅 **Last Updated (IST):**\n{dt_ist.strftime('%Y-%m-%d %H:%M')}")
    
    st.success("🤖 **Automated Data:**\nUpdated every 4 hours via GitHub Actions.")
    
    st.markdown("---")
    st.markdown("### Filters")
    min_combined = st.slider("Min Combined Score", 0, 100, 50)
    
df = load_data()

if df is not None and not df.empty:
    sectors = sorted(df['Sector'].unique())
    selected_sectors = st.sidebar.multiselect("Select Sectors", options=sectors, default=sectors)
    
    filtered_df = df[(df['Combined Score'] >= min_combined) & (df['Sector'].isin(selected_sectors))].sort_values(by="Combined Score", ascending=False)
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Stocks Scanned", len(df))
    col2.metric("Candidates", len(filtered_df))
    high_conv = len(df[(df['VCP Score'] > 70) & (df['Fund Score'] > 50)])
    col3.metric("High Conviction", high_conv)
    col4.metric("Market Regime", "📈 BULLISH") 
    
    st.subheader("📊 Screened Results")
    st.dataframe(filtered_df, use_container_width=True, hide_index=True)
    
    if not filtered_df.empty:
        st.markdown("---")
        st.subheader("🔍 Deep Dive Analysis")
        selected_ticker = st.selectbox("Select Ticker", filtered_df['Ticker'].tolist())
        if selected_ticker:
            stock_row = df[df['Ticker'] == selected_ticker].iloc[0]
            raw_stock = next(s for s in json.load(open(DATA_FILE)) if s['ticker'] == selected_ticker)
            d_col1, d_col2, d_col3 = st.columns(3)
            with d_col1:
                st.markdown(f"### {selected_ticker} Tech")
                tf_choice = st.radio("Timeframe", ["1D", "4H"], horizontal=True)
                tech = raw_stock.get("tech_1d" if "1D" in tf_choice else "tech_4h", {})
                st.table(pd.DataFrame({"Indicator": ["RSI", "EMA20", "EMA50", "MACD"], "Value": [round(tech.get('RSI', 0), 2), round(tech.get('EMA20', 0), 2), round(tech.get('EMA50', 0), 2), round(tech.get('MACD.macd', 0), 2)]}))
            with d_col2:
                st.markdown(f"### {selected_ticker} Fund")
                st.write(f"**ROE:** {stock_row['ROE (%)']}% | **PE:** {stock_row['PE']}")
                st.write(f"**Debt/Eq:** {stock_row['Debt/Eq']}")
            with d_col3:
                st.markdown(f"### {selected_ticker} Quant")
                st.write(f"**Quant Score:** {stock_row['Quant Score']}")
                st.info("Sector institutional flow: Accumulation")

    st.markdown("---")
    st.header("🏆 High Conviction Picks")
    high_conv_df = df[(df['VCP Score'] > 70) & (df['Fund Score'] > 50)].sort_values(by="Combined Score", ascending=False)
    if not high_conv_df.empty:
        cols = st.columns(len(high_conv_df) if len(high_conv_df) < 5 else 4)
        for i, (_, pick) in enumerate(high_conv_df.iterrows()):
            with cols[i % 4]:
                st.success(f"**{pick['Ticker']}**")
                st.write(f"Score: {pick['Combined Score']}")
    else: st.warning("No High Conviction setups found.")
else: st.info("No data available. Try Refreshing.")
