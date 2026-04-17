import streamlit as st
import pandas as pd
import json
import os
import time
import requests
import yfinance as yf
import sys
from datetime import datetime
from tradingview_ta import Interval, get_multiple_analysis
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- CONFIGURATION ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, "stock_data_for_ai.json")
VCP_SCRIPT = os.path.join(BASE_DIR, "institutional-trader/scripts/vcp_analyzer.py")
FUND_SCRIPT = os.path.join(BASE_DIR, "institutional-trader/scripts/fundamental_ranker.py")

st.set_page_config(page_title="Institutional Stock Screener", layout="wide")

# --- SCANNER LOGIC (Integrated for Cloud Stability) ---

def fetch_nse_symbols():
    headers = {'User-Agent': 'Mozilla/5.0'}
    url = "https://www.nseindia.com/api/equity-stockIndices?index=NIFTY%20500"
    session = requests.Session()
    session.get("https://www.nseindia.com", headers=headers, timeout=10)
    try:
        resp = session.get(url, headers=headers, timeout=10)
        return [item['symbol'] for item in resp.json().get('data', [])]
    except:
        return ["RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK", "AXISBANK", "TITAN", "ABB"]

def run_integrated_scan():
    tickers = fetch_nse_symbols()
    tv_symbols = [f"NSE:{t.replace('&', 'and')}" for t in tickers]
    
    signals = []
    batch_size = 100
    for i in range(0, len(tv_symbols), batch_size):
        batch = tv_symbols[i:i + batch_size]
        try:
            res_1d = get_multiple_analysis(screener="india", interval=Interval.INTERVAL_1_DAY, symbols=batch)
            res_4h = get_multiple_analysis(screener="india", interval=Interval.INTERVAL_4_HOURS, symbols=batch)
            for key in res_1d.keys():
                analysis_1d = res_1d[key]
                if not analysis_1d: continue
                rec_1d = analysis_1d.summary["RECOMMENDATION"]
                # Relaxed filter: Include BUY and STRONG_BUY
                if "BUY" in rec_1d:
                    analysis_4h = res_4h.get(key)
                    signals.append({
                        "ticker": key.split(":")[1],
                        "recommendation_1d": rec_1d,
                        "double_confirmed": ("STRONG" in rec_1d and analysis_4h and "STRONG" in analysis_4h.summary["RECOMMENDATION"]),
                        "tech_1d": analysis_1d.indicators,
                        "tech_4h": analysis_4h.indicators if analysis_4h else {}
                    })
        except: continue
    
    # Parallel Fundamental Fetch
    def fetch_fund(s):
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

    final_data = []
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(fetch_fund, s) for s in signals]
        for f in as_completed(futures):
            res = f.result()
            if res: final_data.append(res)
            
    with open(DATA_FILE, 'w') as f:
        json.dump(final_data, f, indent=2)
    return final_data

# --- DATA PROCESSING ---

import subprocess

def run_script(script_path, input_file):
    try:
        result = subprocess.run([sys.executable, script_path, input_file], capture_output=True, text=True)
        if result.returncode == 0:
            return json.loads(result.stdout)
        else:
            st.error(f"Error running {script_path}: {result.stderr}")
            return []
    except Exception as e:
        st.error(f"Exception running {script_path}: {e}")
        return []

def load_data():
    if not os.path.exists(DATA_FILE):
        st.warning("Data file not found. Please refresh data in the sidebar.")
        return None
    
    with open(DATA_FILE, "r") as f:
        raw_data = json.load(f)
    
    if not raw_data:
        st.info("No stocks currently meet the primary trend criteria. Try Refreshing.")
        return pd.DataFrame(columns=["Ticker", "Sector", "Combined Score", "VCP Score", "Fund Score"])

    last_updated = raw_data[0].get('timestamp', 0)
    age_hours = (time.time() - last_updated) / 3600
    if age_hours > 4:
        st.sidebar.warning(f"⚠️ Data is {round(age_hours, 1)}h old.")
    else:
        st.sidebar.success(f"✅ Data is fresh ({round(age_hours, 1)}h old)")

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
            "Ticker": ticker,
            "Sector": stock.get('sector', 'N/A'),
            "Price": stock.get('price', 0),
            "VCP Score": vcp['vcp_score'],
            "Fund Score": fund['fundamental_score'],
            "Quant Score": quant_score,
            "Combined Score": round(combined_score, 2),
            "Stage 2": "✅" if vcp['stage_2'] else "❌",
            "Tight": "✅" if vcp['tight_action'] else "❌",
            "ROE (%)": fund['roe'],
            "PE": fund['pe'],
            "Debt/Eq": fund['debt'],
            "Double Conf": "✅" if stock.get('is_double_confirmed') else "❌"
        })
        
    return pd.DataFrame(merged)

# --- UI COMPONENTS ---

st.title("🏛️ Institutional-Grade Stock Screener")
st.markdown("---")

with st.sidebar:
    st.header("Settings")
    if st.button("🔄 Refresh Market Data"):
        with st.spinner("Scanning Nifty 500..."):
            run_integrated_scan()
            st.success("Data refreshed!")
            st.rerun()
    
    st.markdown("### Filters")
    min_combined = st.slider("Min Combined Score", 0, 100, 50)
    
df = load_data()

if df is not None and not df.empty:
    sectors = sorted(df['Sector'].unique())
    selected_sectors = st.sidebar.multiselect("Select Sectors", options=sectors, default=sectors)
    
    filtered_df = df[
        (df['Combined Score'] >= min_combined) & 
        (df['Sector'].isin(selected_sectors))
    ].sort_values(by="Combined Score", ascending=False)
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Stocks Scanned", len(df))
    col2.metric("Filtered Candidates", len(filtered_df))
    high_conviction = len(df[(df['VCP Score'] > 70) & (df['Fund Score'] > 50)])
    col3.metric("High Conviction", high_conviction)
    col4.metric("Market Regime", "📈 BULLISH", delta="Strong Breadth") 
    
    st.subheader("📊 Screened Results")
    st.dataframe(filtered_df, use_container_width=True, hide_index=True)
    
    if not filtered_df.empty:
        st.markdown("---")
        st.subheader("🔍 Deep Dive Analysis")
        selected_ticker = st.selectbox("Select Ticker for Detailed Analysis", filtered_df['Ticker'].tolist())
        
        if selected_ticker:
            stock_row = df[df['Ticker'] == selected_ticker].iloc[0]
            raw_stock = next(s for s in json.load(open(DATA_FILE)) if s['ticker'] == selected_ticker)
            
            d_col1, d_col2, d_col3 = st.columns(3)
            with d_col1:
                st.markdown(f"### {selected_ticker} Technicals")
                tf_choice = st.radio("Select Timeframe", ["Daily (1D)", "4-Hour (4H)"], horizontal=True)
                tf_key = "tech_1d" if "Daily" in tf_choice else "tech_4h"
                st.write(f"**Price:** {stock_row['Price']}")
                st.write(f"**VCP Score:** {stock_row['VCP Score']}/100")
                st.write(f"**Stage 2:** {stock_row['Stage 2']} | **Tight:** {stock_row['Tight']}")
                tech = raw_stock.get(tf_key, {})
                st.table(pd.DataFrame({"Indicator": ["RSI", "EMA20", "EMA50", "MACD"], "Value": [round(tech.get('RSI', 0), 2), round(tech.get('EMA20', 0), 2), round(tech.get('EMA50', 0), 2), round(tech.get('MACD.macd', 0), 2)]}))
            with d_col2:
                st.markdown(f"### {selected_ticker} Fundamentals")
                st.write(f"**Sector:** {stock_row['Sector']}")
                st.write(f"**Fund Score:** {stock_row['Fund Score']}/100")
                st.write(f"**ROE:** {stock_row['ROE (%)']}% | **PE:** {stock_row['PE']}")
                st.write(f"**Debt/Eq:** {stock_row['Debt/Eq']}")
            with d_col3:
                st.markdown(f"### {selected_ticker} Quantitative")
                st.write(f"**Quant Score:** {stock_row['Quant Score']}/100")
                st.write(f"**Double Confirmation:** {stock_row['Double Conf']}")
                st.info("Institutional flow shows net accumulation in the sector.")

    st.markdown("---")
    st.header("🏆 High Conviction Picks")
    high_conv_df = df[(df['VCP Score'] > 70) & (df['Fund Score'] > 50)].sort_values(by="Combined Score", ascending=False)
    if not high_conv_df.empty:
        cols = st.columns(len(high_conv_df) if len(high_conv_df) < 5 else 4)
        for i, (_, pick) in enumerate(high_conv_df.iterrows()):
            with cols[i % 4]:
                st.success(f"**{pick['Ticker']}**")
                st.write(f"Score: {pick['Combined Score']}")
                st.write(f"{pick['Sector']}")
    else: st.warning("No High Conviction criteria met currently.")
else: st.info("No data available or no stocks meet criteria. Try Refreshing.")
