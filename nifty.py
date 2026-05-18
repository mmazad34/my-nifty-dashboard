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
# 🚀 CORE TERMINAL GRID DESIGN
# ==========================================
st.title("⚡ Nifty Liquid Confluence Screener Matrix")
st.caption("Tx3 Analysis ke baad 4-Confirmations aur Fibonacci Levels ko ek hi dashboard par check karein")

# Comprehensive High-Liquidity Nifty 200 Core Trading Pool
NIFTY_200_POOL = {
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
    "M&M": {"yf": "M&M.NS", "gfin": "NSE:M&M", "dhan_id": "2031"},
    "RELIANCE": {"yf": "RELIANCE.NS", "gfin": "NSE:RELIANCE", "dhan_id": "2885"},
    "SUNPHARMA": {"yf": "SUNPHARMA.NS", "gfin": "NSE:SUNPHARMA", "dhan_id": "3351"},
    "TATAMOTORS": {"yf": "TATAMOTORS.NS", "gfin": "NSE:TATAMOTORS", "dhan_id": "3456"}
}

# ==========================================
# 🔧 SIDEBAR DASHBOARD FILTERS
# ==========================================
st.sidebar.markdown("### 🎂️ LIQUID POOL WATCHLIST")
st.sidebar.write("Tx3 Heatmap ke high momentum stocks yahan add karein:")

selected_stocks = st.sidebar.multiselect(
    "Target Stocks Matrix Select:",
    options=list(NIFTY_200_POOL.keys()),
    default=list(NIFTY_200_POOL.keys())[:6] # Default loads 6 stocks parallelly
)

timeframe = st.sidebar.selectbox("⏱️ System Candle Interval", ["5m", "15m", "1h"], index=0)

# ==========================================
# 🛰️ LIVE PRICING & INDICATOR PROCESSING ENGINE
# ==========================================
def get_live_price(stock_name):
    """Fallback real-time market tracker across multi-channel scrapers"""
    try:
        dhan = dhanhq(st.secrets["DHAN_CLIENT_ID"], st.secrets["DHAN_ACCESS_TOKEN"])
        sec_id = NIFTY_200_POOL[stock_name]["dhan_id"]
        quote = dhan.get_quote_data(security_id=sec_id, exchange_segment="NSE_EQ", instrument_type="EQUITY")
        if quote and quote.get('status') == 'success':
            return float(quote.get('data', {}).get('last_price', 0))
    except Exception:
        pass

    try:
        gfin_ticker = NIFTY_200_POOL[stock_name]["gfin"]
        url = f"https://www.google.com/finance/quote/{gfin_ticker}"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        html = urllib.request.urlopen(req).read().decode('utf-8')
        match = re.search(r'data-last-price="([^"]+)"', html)
        if match:
            return float(match.group(1).replace(',', ''))
    except Exception:
        pass
    return None

def format_volume(volume_num):
    """Converts raw volumes into clean professional stock terminal formatting (K/M)"""
    if volume_num >= 1_000_000:
        return f"{round(volume_num / 1_000_000, 1)}M"
    elif volume_num >= 1_000:
        return f"{round(volume_num / 1_000, 1)}K"
    return str(int(volume_num))

def generate_matrix_row(stock_name, interval="5m"):
    """Compiles structural chart math and builds standardized dashboard grid layout dictionaries"""
    yf_ticker = NIFTY_200_POOL[stock_name]["yf"]
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

    # Fetch fresh price streams
    live_p = get_live_price(stock_name)
    if not live_p:
        live_p = float(df['Close'].iloc[-1])

    # Core Technical Indicators Computations
    df['EMA_20'] = ta.trend.ema_indicator(df['Close'], window=min(20, len(df)))
    df['RSI'] = ta.momentum.rsi(df['Close'], window=min(14, len(df)))
    df['Vol_Avg'] = df['Volume'].rolling(window=20, min_periods=1).mean()
    df = df.bfill().ffill()

    latest_bar = df.iloc[-1]
    
    # 1. EMA Rule Interpretation
    ema_20_val = round(latest_bar['EMA_20'], 2)
    ema_string = f"ABOVE 🟢 (₹{ema_20_val})" if live_p > latest_bar['EMA_20'] else f"BELOW 🔴 (₹{ema_20_val})"
    
    # 2. RSI Formatting
    rsi_string = f"{round(latest_bar['RSI'], 1)}"
    
    # 3. Volume Surge Processing
    raw_vol = float(latest_bar['Volume'])
    raw_avg_vol = float(latest_bar['Vol_Avg'])
    formatted_vol_str = format_volume(raw_vol)
    volume_string = f"🚀 SURGE ({formatted_vol_str})" if raw_vol > raw_avg_vol else f"Normal ({formatted_vol_str})"

    # 4. Accurate Fibonacci Mapping Matrix
    high_marker = float(df['High'].max())
    low_marker = float(df['Low'].min())
    spread_diff = high_marker - low_marker if (high_marker - low_marker) != 0 else 1

    fibonacci_matrix = {
        "0.0% (High)": round(high_marker, 2),
        "23.6%": round(high_marker - (0.236 * spread_diff), 2),
        "38.2%": round(high_marker - (0.382 * spread_diff), 2),
        "50.0%": round(high_marker - (0.500 * spread_diff), 2),
        "61.8% Golden": round(high_marker - (0.618 * spread_diff), 2),
        "100.0% (Low)": round(low_marker, 2)
    }
    
    # Calculate proximity to nearest level threshold
    closest_fib_ratio = min(fibonacci_matrix, key=lambda key: abs(fibonacci_matrix[key] - live_p))
    fibonacci_string = f"🎯 Near {closest_fib_ratio} (₹{fibonacci_matrix[closest_fib_ratio]})"

    return {
        "Stock Name": stock_name,
        "Live LTP": f"₹{round(live_p, 2)}",
        "EMA 20 Trend": ema_string,
        "RSI (14)": rsi_string,
        "Volume": volume_string,
        "Fibonacci Zone": fibonacci_string
    }

# ==========================================
# 📊 VIEW PORT COMPILER & RENDER
# ==========================================
if selected_stocks:
    screener_matrix_data = []
    
    with st.spinner("Refreshing Screener Ticks across Nifty 200 liquid pools..."):
        for target_stock in selected_stocks:
            row_data = generate_matrix_row(target_stock, interval=timeframe)
            if row_data:
                screener_matrix_data.append(row_data)
                
    if screener_matrix_data:
        # Building the explicit clean layout frame requested
        display_df = pd.DataFrame(screener_matrix_data)
        display_df.index = np.arange(1, len(display_df) + 1) # Clean 1,2,3... index layout
        
        st.subheader("📋 Realtime Confluence Matrix Grid View")
        st.dataframe(display_df, use_container_width=True)
        
        # Operational Trade execution blueprints
        st.info(
            "💡 **Intraday Quick Setup Execution:** \n"
            "1. Check **Tx3** for strong sector confirmation. \n"
            "2. Identify matrix stocks showing **EMA 20 ABOVE 🟢**, **RSI > 50**, and **Volume SURGE 🚀**. \n"
            "3. If that stock's Fibonacci Zone says **Near 50.0%** or **Near 61.8% Golden**, it's a high-probability trade zone."
        )
    else:
        st.error("⚠️ Pipeline structural connection error. Synchronizing feeds...")
else:
    st.warning("⚠️ Terminal monitoring block empty. Please select active liquid assets from the sidebar watchlist.")

# Smooth continuous background updater script (Ticks every 10 seconds flat)
st.markdown("""
    <script>
        setTimeout(function(){ window.location.reload(); }, 10000);
    </script>
""", unsafe_allow_html=True)
