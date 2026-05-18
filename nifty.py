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
from datetime import datetime
from dhanhq import dhanhq

# Page configuration
st.set_page_config(page_title="Intraday Signal Terminal", layout="wide")
st.title("⚡ Simple Intraday Live Signal Terminal")

# Ticker Mapping (YFinance vs Google Finance vs Dhan Security ID)
# Aap yahan apne manpasand stocks aaram se add kar sakte hain
STOCKS = {
    "RELIANCE": {"yf": "RELIANCE.NS", "gfin": "NSE:RELIANCE", "dhan_id": "2885"},
    "TCS": {"yf": "TCS.NS", "gfin": "NSE:TCS", "dhan_id": "11536"},
    "HDFC BANK": {"yf": "HDFCBANK.NS", "gfin": "NSE:HDFCBANK", "dhan_id": "1333"},
    "INFY": {"yf": "INFY.NS", "gfin": "NSE:INFY", "dhan_id": "1594"},
    "SBIN": {"yf": "SBIN.NS", "gfin": "NSE:SBIN", "dhan_id": "3045"}
}

# ==========================================
# 🛰️ REALTIME LIVE DATA FETCHERS
# ==========================================
def get_live_price(stock_name):
    """Fetches real-time price from Dhan, falls back to Google Finance if fails"""
    # 1. Try Dhan API
    try:
        dhan = dhanhq(st.secrets["DHAN_CLIENT_ID"], st.secrets["DHAN_ACCESS_TOKEN"])
        sec_id = STOCKS[stock_name]["dhan_id"]
        quote = dhan.get_quote_data(security_id=sec_id, exchange_segment="NSE_EQ", instrument_type="EQUITY")
        if quote and quote.get('status') == 'success':
            return float(quote.get('data', {}).get('last_price', 0))
    except Exception:
        pass

    # 2. Fallback to Google Finance Scraper
    try:
        gfin_ticker = STOCKS[stock_name]["gfin"]
        url = f"https://www.google.com/finance/quote/{gfin_ticker}"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        html = urllib.request.urlopen(req).read().decode('utf-8')
        match = re.search(r'data-last-price="([^"]+)"', html)
        if match:
            return float(match.group(1).replace(',', ''))
    except Exception:
        pass
    
    return None

def fetch_stock_data(stock_name, interval="5m"):
    """Fetches historical structure and injects live price"""
    yf_ticker = STOCKS[stock_name]["yf"]
    
    # Fetch last 5 days data for Intraday structure
    try:
        df = yf.download(yf_ticker, period="5d", interval=interval, progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df = df[yf_ticker]
    except Exception:
        return pd.DataFrame()

    if df.empty:
        return pd.DataFrame()

    # Inject Live Tick
    live_p = get_live_price(stock_name)
    if live_p:
        df.iloc[-1, df.columns.get_loc('Close')] = live_p
        if live_p > df.iloc[-1]['High']: df.iloc[-1, df.columns.get_loc('High')] = live_p
        if live_p < df.iloc[-1]['Low']: df.iloc[-1, df.columns.get_loc('Low')] = live_p

    return df.dropna()

# ==========================================
# 📊 INDICATORS & SIGNAL ENGINE
# ==========================================
def process_signals(df):
    df = df.copy()
    
    # 1. Calculate Technicals
    df['EMA_20'] = ta.trend.ema_indicator(df['Close'], window=20)
    df['EMA_200'] = ta.trend.ema_indicator(df['Close'], window=max(2, len(df)//2)) if len(df) < 200 else ta.trend.ema_indicator(df['Close'], window=200)
    df['RSI'] = ta.momentum.rsi(df['Close'], window=14)
    
    # 2. Generate Simple Intraday Strategy Rules
    signals = []
    for i in range(len(df)):
        if i == 0:
            signals.append("HOLD")
            continue
            
        close = df['Close'].iloc[i]
        ema20 = df['EMA_20'].iloc[i]
        ema200 = df['EMA_200'].iloc[i]
        rsi = df['RSI'].iloc[i]
        
        # BUY Rule: Price EMA 20 ke upar ho, EMA 20 khud EMA 200 ke upar ho, aur RSI > 50 (Bullish Momentum)
        if close > ema20 and ema20 > ema200 and rsi > 50:
            signals.append("BUY 🟢")
        # SELL Rule: Price EMA 20 ke neeche ho, EMA 20 khud EMA 200 ke neeche ho, aur RSI < 45 (Bearish Momentum)
        elif close < ema20 and ema20 < ema200 and rsi < 45:
            signals.append("SELL 🔴")
        else:
            signals.append("HOLD ⚪")
            
    df['Signal'] = signals
    return df

# ==========================================
# 🖥️ USER INTERFACE
# ==========================================
# Sidebar Selection
selected_stock = st.sidebar.selectbox("🎯 Select Stock for Intraday", list(STOCKS.keys()))
timeframe = st.sidebar.selectbox("⏱️ Timeframe", ["5m", "15m", "1h"])

# Fetch and Process
data = fetch_stock_data(selected_stock, interval=timeframe)

if not data.empty:
    final_df = process_signals(data)
    latest_data = final_df.iloc[-1]
    prev_data = final_df.iloc[-2]
    
    # Metrics Calculation
    ltp = round(latest_data['Close'], 2)
    change = round(ltp - prev_data['Close'], 2)
    pct_change = round((change / prev_data['Close']) * 100, 2)
    
    # Display Top Cards
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric(label=f"{selected_stock} LTP", value=f"₹{ltp}", delta=f"{change} ({pct_change}%)")
    with c2:
        st.metric(label="RSI (14)", value=f"{round(latest_data['RSI'], 2)}")
    with c3:
        st.metric(label="EMA 20", value=f"₹{round(latest_data['EMA_20'], 2)}")
    with c4:
        # Dynamic Color Block for Signal
        sig = latest_data['Signal']
        bg_color = "#238636" if "🟢" in sig else ("#da3633" if "🔴" in sig else "#21262d")
        st.markdown(f"""
            <div style="background-color:{bg_color}; padding:10px; border-radius:8px; text-align:center; color:white; font-weight:bold; font-size:20px;">
                CURRENT SIGNAL: {sig}
            </div>
        """, unsafe_allow_html=True)
        
    st.divider()
    
    # Display Recent Data Table for confirmation
    st.subheader("📋 Recent 5-Candles Terminal Log")
    log_df = final_df[['Open', 'High', 'Low', 'Close', 'RSI', 'Signal']].tail(5)
    st.dataframe(log_df, use_container_width=True)

else:
    st.error("⚠️ Data connection lost. Waiting for next interval tick...")

# Auto reload every 10 seconds for real-time tracking
st.markdown("<script>setTimeout(function(){ window.location.reload(); }, 10000);</script>", unsafe_allow_html=True)
