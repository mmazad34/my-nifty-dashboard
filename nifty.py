import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
try:
    import ta
except ImportError:
    import ta as ta
import urllib.request
import re
from datetime import datetime, timedelta
from dhanhq import dhanhq

# ==========================================
# CONFIGURATION & PAGE SETUPS
# ==========================================
st.set_page_config(page_title="Intraday Confluence Matrix", layout="wide")

# ==========================================
# 🔒 SECURITY SYSTEM (PASSWORD WALL)
# ==========================================
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False

if not st.session_state["authenticated"]:
    st.title("🔒 Authorized Access Only")
    user_input = st.text_input("Enter Admin Password:", type="password")
    if st.button("Login"):
        if user_input == st.secrets["MY_APP_PASSWORD"]:
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("❌ Wrong Password! Access Denied.")
    st.stop()

# ==========================================
# 🚀 CORE MATRIX INTERFACE
# ==========================================
st.title("⚡ Nifty High-Liquidity Confluence Matrix")
st.caption("Tx3 Sector Tracker ke baad sabhi technicals aur Fibonacci zones ek hi screen par")

# Highly Liquid Nifty 200 Trading Stocks Pool
NIFTY_LIQUID_POOL = {
    "RELIANCE": {"yf": "RELIANCE.NS", "gfin": "NSE:RELIANCE", "dhan_id": "2885"},
    "TCS": {"yf": "TCS.NS", "gfin": "NSE:TCS", "dhan_id": "11536"},
    "HDFC BANK": {"yf": "HDFCBANK.NS", "gfin": "NSE:HDFCBANK", "dhan_id": "1333"},
    "INFY": {"yf": "INFY.NS", "gfin": "NSE:INFY", "dhan_id": "1594"},
    "SBIN": {"yf": "SBIN.NS", "gfin": "NSE:SBIN", "dhan_id": "3045"},
    "ICICIBANK": {"yf": "ICICIBANK.NS", "gfin": "NSE:ICICIBANK", "dhan_id": "4963"},
    "BHARTIARTL": {"yf": "BHARTIARTL.NS", "gfin": "NSE:BHARTIARTL", "dhan_id": "10604"},
    "AXISBANK": {"yf": "AXISBANK.NS", "gfin": "NSE:AXISBANK", "dhan_id": "596"},
    "TATASTEEL": {"yf": "TATASTEEL.NS", "gfin": "NSE:TATASTEEL", "dhan_id": "3499"},
    "ITC": {"yf": "ITC.NS", "gfin": "NSE:ITC", "dhan_id": "1660"},
    "LT": {"yf": "LT.NS", "gfin": "NSE:LT", "dhan_id": "11483"},
    "M&M": {"yf": "M&M.NS", "gfin": "NSE:M&M", "dhan_id": "2031"}
}

# ==========================================
# 🔧 SIDEBAR CONTROLS & WATCHLIST
# ==========================================
st.sidebar.markdown("### 🗂️ LIQUID WATCHLIST TARGETS")
st.sidebar.write("Apne targeted intraday stocks yahan se select karein:")

selected_stocks = st.sidebar.multiselect(
    "Select Stocks (Nifty 200 Favorites):",
    options=list(NIFTY_LIQUID_POOL.keys()),
    default=list(NIFTY_LIQUID_POOL.keys())[:5] # Default 5 stocks on load
)

timeframe = st.sidebar.selectbox("⏱️ Timeframe", ["5m", "15m", "1h"], index=0)

# ==========================================
# 🛰️ LIVE DATA & INDICATOR ENGINE
# ==========================================
def get_live_price(stock_name):
    """Real-time instant price feed fallback via Dhan / Google Finance"""
    try:
        dhan = dhanhq(st.secrets["DHAN_CLIENT_ID"], st.secrets["DHAN_ACCESS_TOKEN"])
        sec_id = NIFTY_LIQUID_POOL[stock_name]["dhan_id"]
        quote = dhan.get_quote_data(security_id=sec_id, exchange_segment="NSE_EQ", instrument_type="EQUITY")
        if quote and quote.get('status') == 'success':
            return float(quote.get('data', {}).get('last_price', 0))
    except Exception:
        pass

    try:
        gfin_ticker = NIFTY_LIQUID_POOL[stock_name]["gfin"]
        url = f"https://www.google.com/finance/quote/{gfin_ticker}"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        html = urllib.request.urlopen(req).read().decode('utf-8')
        match = re.search(r'data-last-price="([^"]+)"', html)
        if match:
            return float(match.group(1).replace(',', ''))
    except Exception:
        pass
    return None

def compute_matrix_row(stock_name, interval="5m"):
    """Downloads charts, calculates indicators + fibonacci levels, generates clean dictionary row"""
    yf_ticker = NIFTY_LIQUID_POOL[stock_name]["yf"]
    df = pd.DataFrame()
    
    try:
        df = yf.download(yf_ticker, period="5d", interval=interval, progress=False, group_by='ticker')
        if isinstance(df.columns, pd.MultiIndex) and not df.empty:
            if yf_ticker in df.columns.levels[0]:
                df = df[yf_ticker]
    except Exception:
        pass

    if df.empty or len(df) < 5:
        try:
            df = yf.Ticker(yf_ticker).history(period="5d", interval=interval)
        except Exception:
            return None

    if df.empty:
        return None

    # Inject Live Price Ticks
    live_p = get_live_price(stock_name)
    if not live_p:
        live_p = float(df['Close'].iloc[-1])

    # Technical Indicators Logic
    df['EMA_20'] = ta.trend.ema_indicator(df['Close'], window=min(20, len(df)))
    df['RSI'] = ta.momentum.rsi(df['Close'], window=min(14, len(df)))
    df['Vol_Avg'] = df['Volume'].rolling(window=20, min_periods=1).mean()
    df = df.bfill().ffill()

    latest = df.iloc[-1]
    
    # 1. EMA Trend Interpretation
    ema_val = round(latest['EMA_20'], 2)
    ema_trend = f"🟢 ABOVE (₹{ema_val})" if live_p > latest['EMA_20'] else f"🔴 BELOW (₹{ema_val})"
    
    # 2. RSI Calculation
    rsi_val = round(latest['RSI'], 2)
    
    # 3. Volume Surge Monitor
    current_vol = int(latest['Volume'])
    avg_vol = int(latest['Vol_Avg'])
    vol_display = f"🚀 SURGE ({current_vol:,})" if current_vol > avg_vol else f"Normal ({current_vol:,})"

    # 4. Fibonacci Level Processing
    high_val = float(df['High'].max())
    low_val = float(df['Low'].min())
    diff = high_val - low_val if (high_val - low_val) != 0 else 1

    fib_levels = {
        "0.0% (High)": round(high_val, 2),
        "23.6%": round(high_val - (0.236 * diff), 2),
        "38.2%": round(high_val - (0.382 * diff), 2),
        "50.0%": round(high_val - (0.500 * diff), 2),
        "61.8% Golden": round(high_val - (0.618 * diff), 2),
        "100.0% (Low)": round(low_val, 2)
    }
    
    # Find closest Fibonacci target zone
    closest_fib = min(fib_levels, key=lambda k: abs(fib_levels[k] - live_p))
    fib_display = f"🎯 Near {closest_fib} (₹{fib_levels[closest_fib]})"

    return {
        "Stock Name": stock_name,
        "Live LTP": f"₹{round(live_p, 2)}",
        "EMA 20 Trend": ema_trend,
        "RSI (14)": rsi_val,
        "Volume Surge Status": vol_display,
        "Fibonacci Proximity Zone": fib_display
    }

# ==========================================
# 📊 MATRIX RENDER CONTROLLER
# ==========================================
if selected_stocks:
    final_matrix = []
    
    with st.spinner("Compiling Live Technical Matrix Grid..."):
        for stock in selected_stocks:
            row = compute_matrix_row(stock, interval=timeframe)
            if row:
                final_matrix.append(row)
                
    if final_matrix:
        matrix_df = pd.DataFrame(final_matrix)
        matrix_df.set_index("Stock Name", inplace=True)
        
        # Displaying Custom Requested Matrix Dashboard
        st.subheader("📋 Live Confluence Matrix Terminal Overview")
        st.dataframe(matrix_df, use_container_width=True)
        
        # Quick Multi-Confirmation Guide Block
        st.success(
            "💡 **Matrix Trade Strategy:** Agar Tx3 terminal par sector strong bullish ho, "
            "toh is matrix mein aisa stock pakadiye jiska **EMA Trend ABOVE** ho, **RSI > 50** ho, "
            "**Volume SURGE 🚀** dikha raha ho, aur price **50.0% ya 61.8% Golden** level ke paas (🎯) ho. "
            "Aise setups ki intraday accuracy sabse solid hoti hai!"
        )
    else:
        st.error("⚠️ Data connection lost. Re-fetching ticks...")
else:
    st.warning("⚠️ Terminal chalane ke liye kripya sidebar watchlist se stocks select karein.")

# Auto-Refresh Mechanism (Crisp 10 Seconds Loop)
st.markdown("""
    <script>
        setTimeout(function(){ window.location.reload(); }, 10000);
    </script>
""", unsafe_allow_html=True)
