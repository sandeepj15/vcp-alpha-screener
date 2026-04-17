import sys
import json

def analyze_vcp(stock_data):
    """
    Implements Volatility Contraction Pattern (VCP) logic.
    Identifies if a stock is in a Stage 2 uptrend and has 'tight' price action.
    """
    results = []
    for stock in stock_data:
        ticker = stock.get('ticker')
        tech_1d = stock.get('tech_1d', {})
        price = stock.get('price', 0)
        
        # 1. Stage 2 Uptrend Logic: Price > EMA20 > EMA50
        ema20 = tech_1d.get('EMA20', 0)
        ema50 = tech_1d.get('EMA50', 0)
        
        is_stage_2 = price > ema20 > ema50
        
        # 2. Volatility Contraction Logic: Using RSI as a proxy for 'tightness'
        # Tight action usually happens when RSI stabilizes between 50 and 65
        rsi = tech_1d.get('RSI', 50)
        is_tight = 50 <= rsi <= 68
        
        # 3. Institutional Accumulation: Positive MACD and double confirmed
        macd = tech_1d.get('MACD.macd', 0)
        signal = tech_1d.get('MACD.signal', 0)
        is_accumulating = macd > signal
        
        score = 0
        if is_stage_2: score += 40
        if is_tight: score += 30
        if is_accumulating: score += 30
        
        results.append({
            "ticker": ticker,
            "vcp_score": score,
            "stage_2": is_stage_2,
            "tight_action": is_tight,
            "accumulating": is_accumulating
        })
    
    # Sort by highest score
    return sorted(results, key=lambda x: x['vcp_score'], reverse=True)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"error": "No data file provided"}))
        sys.exit(1)
        
    try:
        with open(sys.argv[1], 'r') as f:
            data = json.load(f)
        analysis = analyze_vcp(data)
        print(json.dumps(analysis, indent=2))
    except Exception as e:
        print(json.dumps({"error": str(e)}))
