import sys
import json

def rank_fundamentals(stock_data):
    """
    Ranks stocks using an Institutional Tiered Quality Framework.
    Prioritizes ROE, Free Cash Flow, and Debt levels.
    """
    ranked = []
    for stock in stock_data:
        ticker = stock.get('ticker')
        fund = stock.get('fundamentals', {})
        
        # Scoring Logic
        f_score = 0
        
        # 1. Valuation Tier (PE < 30 gets points)
        pe = fund.get('forwardPE') or fund.get('trailingPE')
        if pe:
            if pe < 15: f_score += 30
            elif pe < 30: f_score += 20
            
        # 2. Quality Tier (ROE > 15% is excellent)
        roe = fund.get('returnOnEquity')
        if roe:
            if roe > 0.20: f_score += 40
            elif roe > 0.15: f_score += 30
            
        # 3. Risk Tier (Low Debt)
        debt = fund.get('debtToEquity')
        if debt is not None:
            if debt < 50: f_score += 30
            elif debt < 100: f_score += 15
            
        ranked.append({
            "ticker": ticker,
            "fundamental_score": f_score,
            "pe": pe,
            "roe": round(roe * 100, 2) if roe else None,
            "debt": debt
        })
        
    return sorted(ranked, key=lambda x: x['fundamental_score'], reverse=True)

if __name__ == "__main__":
    if len(sys.argv) < 2: sys.exit(1)
    with open(sys.argv[1], 'r') as f:
        data = json.load(f)
    print(json.dumps(rank_fundamentals(data), indent=2))
