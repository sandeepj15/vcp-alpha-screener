# 🏛️ Institutional VCP Alpha Screener (NSE)

An institutional-grade equity research and momentum trading tool designed to identify high-probability swing trading opportunities in the Indian stock market (NSE). This screener combines **Fundamental Strength**, **Mark Minervini-style Volatility Contraction Patterns (VCP)**, and **Quantitative Momentum Signals**.

## 🚀 Key Features

- **Triple Pillar Scoring Model**:
    - **Fundamentals (50%)**: Evaluates ROE, PE Ratio, and Debt-to-Equity using a tiered quality framework.
    - **Technicals (30%)**: Identifies Stage 2 uptrends and VCP tightening on the Daily (1D) timeframe.
    - **Quantitative (20%)**: Uses 4-Hour (4H) timeframe confirmation and institutional flow proxies.
- **Broad Market Coverage**: Screens the **Nifty 500** and **Nifty Microcap 250** (~750 stocks) to find hidden gems and liquid leaders.
- **High Conviction Dashboard**: Automatically isolates "Institutional Grade" setups (VCP > 70 & Fund > 50).
- **Real-Time Data**: Integrated scanner fetching live technicals from TradingView and fundamentals from yfinance.
- **Freshness Tracking**: Built-in data aging indicator with a "Refresh" mechanism.

## 🛠️ Installation & Local Setup

1. **Clone the Repository**:
   ```bash
   git clone https://github.com/sandeepj15/vcp-alpha-screener.git
   cd vcp-alpha-screener
   ```

2. **Create a Virtual Environment**:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Run the Application**:
   ```bash
   streamlit run stock_screener_app.py
   ```

## ☁️ Deployment (Streamlit Cloud)

This project is pre-configured for **Streamlit Cloud**:

1. Push this repository to your GitHub.
2. Connect your GitHub account to [Streamlit Cloud](https://share.streamlit.io/).
3. Select this repository and the `main` branch.
4. Set the **Main file path** to `stock_screener_app.py`.
5. Click **Deploy**!

## 🧪 Technical Architecture

- **Frontend**: Streamlit (Python-based interactive dashboard).
- **Data Engine**: `scanner.py` (Batched multi-threaded data fetching).
- **Analysis Logic**:
    - `vcp_analyzer.py`: Technical trend and volatility contraction logic.
    - `fundamental_ranker.py`: Institutional tiered quality ranking.
- **Data Sources**: TradingView (Technicals), yfinance (Fundamentals), NSE India (Index constituents).

## ⚖️ Disclaimer

*This tool is for educational and research purposes only. Stock market investments are subject to market risks. Always consult with a certified financial advisor before making any trading decisions.*
