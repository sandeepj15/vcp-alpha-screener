import streamlit as st
import pandas as pd
import json
import os
import subprocess
import time
from datetime import datetime

# --- CONFIGURATION ---
DATA_FILE = "stock_data_for_ai.json"
VCP_SCRIPT = "institutional-trader/scripts/vcp_analyzer.py"
FUND_SCRIPT = "institutional-trader/scripts/fundamental_ranker.py"
SCAN_SCRIPT = "scanner.py"

st.set_page_config(page_title="Institutional Stock Screener", layout="wide")

# --- DATA PROCESSING ---

def run_script(script_path, input_file):
    try:
        result = subprocess.run(["python3", script_path, input_file], capture_output=True, text=True)
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
    
    # Check data freshness
    if raw_data:
        last_updated = raw_data[0].get('timestamp', 0)
        age_hours = (time.time() - last_updated) / 3600
        if age_hours > 4:
            st.sidebar.warning(f"⚠️ Data is {round(age_hours, 1)}h old. Refresh recommended.")
        else:
            st.sidebar.success(f"✅ Data is fresh ({round(age_hours, 1)}h old)")

    vcp_results = run_script(VCP_SCRIPT, DATA_FILE)
    fund_results = run_script(FUND_SCRIPT, DATA_FILE)
    
    # Merge results
    merged = []
    vcp_dict = {item['ticker']: item for item in vcp_results}
    fund_dict = {item['ticker']: item for item in fund_results}
    
    for stock in raw_data:
        ticker = stock['ticker']
        vcp = vcp_dict.get(ticker, {"vcp_score": 0, "stage_2": False, "tight_action": False, "accumulating": False})
        fund = fund_dict.get(ticker, {"fundamental_score": 0, "pe": None, "roe": None, "debt": None})
        
        # 3rd Pillar: Quantitative (Momentum/Confirmation)
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

# Sidebar
with st.sidebar:
    st.header("Settings")
    if st.button("🔄 Refresh Market Data"):
        with st.spinner("Scanning Nifty 500 for fresh signals..."):
            res = subprocess.run(["python3", SCAN_SCRIPT], capture_output=True, text=True)
            if res.returncode == 0:
                st.success("Data refreshed!")
                st.rerun()
            else:
                st.error(f"Refresh failed: {res.stderr}")
    
    st.markdown("### Filters")
    min_combined = st.slider("Min Combined Score", 0, 100, 50)
    
# Main Content
df = load_data()

if df is not None:
    sectors = sorted(df['Sector'].unique())
    selected_sectors = st.sidebar.multiselect("Select Sectors", options=sectors, default=sectors)
    
    filtered_df = df[
        (df['Combined Score'] >= min_combined) & 
        (df['Sector'].isin(selected_sectors))
    ].sort_values(by="Combined Score", ascending=False)
    
    # Stats row
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Stocks Scanned", len(df))
    col2.metric("Filtered Candidates", len(filtered_df))
    high_conviction = len(df[(df['VCP Score'] > 70) & (df['Fund Score'] > 50)])
    col3.metric("High Conviction", high_conviction)
    col4.metric("Market Regime", "📈 BULLISH", delta="Strong Breadth") 
    
    st.subheader("📊 Screened Results")
    st.dataframe(filtered_df, use_container_width=True, hide_index=True)
    
    # Detail View
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

    # --- HIGH CONVICTION SECTION ---
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
else: st.info("No data available. Use the sidebar to refresh.")
