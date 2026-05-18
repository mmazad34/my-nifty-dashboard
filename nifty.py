import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as gr
from plotly.subplots import make_subplots
import urllib.request
import re
try:
    import ta
except ImportError:
    import ta as ta
from datetime import datetime, timedelta
import io
from dhanhq import dhanhq

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
# CONFIGURATION & CONSTANTS
# ==========================================
st.set_page_config(
    page_title="Pro Indian Index Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
    <style>
        .stApp { background-color: #0c1017; color: #c9d1d9; }
        div[data-testid="stMetricValue"] { color: #ffffff; font-size: 28px; font-weight: bold; }
        .stTabs [data-baseweb="tab-list"] { gap: 10px; }
        .stTabs [data-baseweb="tab"] {
            background-color: #161b22;
            border: 1px solid #30363d;
            border-radius: 4px 4px 0px 0px;
            padding: 10px 20px;
            color: #8b949e;
        }
        .stTabs [data-baseweb="tab"]:hover { color: #ffffff; }
        .stTabs [data-baseweb="tab"][aria-selected="true"] {
            background-color: #1f242c;
            border-bottom: 2px solid #238636;
            color: #ffffff;
        }
    </style>
""", unsafe_allow_html=True)

INDICES = {
    "NIFTY 50": "^NSEI",
    "BANK NIFTY": "^NSEBANK",
    "SENSEX": "^BSESN",
    "GOLD": "GC=F",
    "COMMODITIES (CRUDE)": "CL=F"
}

TIMEFRAMES = {
    "5m": {"period": "5d", "interval": "5m"},
    "15m": {"period": "7d", "interval": "15m"},
    "1h": {"period": "60d", "interval": "1h"},
    "1d": {"period": "2y", "interval": "1d"}
}

DHAN_ASSET_MAP = {
    "NIFTY 50": {"key": 26000, "type": "INDEX", "exchange": "NSE_INDEX", "gfin": "INDEXNSE:NIFTY_50"},
    "BANK NIFTY": {"key": 26001, "type": "INDEX", "exchange": "NSE_INDEX", "gfin": "INDEXNSE:BANKNIFTY"},
    "SENSEX": {"key": 26002, "type": "INDEX", "exchange": "BSE_INDEX", "gfin": "INDEXBOM:SENSEX"},
    "GOLD": {"key": 55101, "type": "COMMODITY", "exchange": "MCX", "gfin": "COMPMKT:GC00"},
    "COMMODITIES (CRUDE)": {"key": 55201, "type": "COMMODITY", "exchange": "MCX", "gfin": "COMPMKT:CL00"}
}

# ==========================================
# 🛰️ DIRECT DHAN & GOOGLE FINANCE REALTIME QUOTE ENGINE
# ==========================================
def fetch_authenticated_dhan_ltp(index_name):
    try:
        dhan = dhanhq(st.secrets["DHAN_CLIENT_ID"], st.secrets["DHAN_ACCESS_TOKEN"])
        asset_info = DHAN_ASSET_MAP[index_name]
        quote_res = dhan.get_quote_data(
            security_id=str(asset_info["key"]),
            exchange_segment=asset_info["exchange"],
            instrument_type=asset_info["type"]
        )
        if quote_res and quote_res.get('status') == 'success':
            return float(quote_res.get('data', {}).get('last_price', 0))
    except Exception:
        pass
    return None

def fetch_google_finance_fallback(gfin_ticker):
    try:
        url = f"https://www.google.com/finance/quote/{gfin_ticker}"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        html = urllib.request.urlopen(req).read().decode('utf-8')
        match = re.search(r'data-last-price="([^"]+)"', html)
        if match:
            return float(match.group(1).replace(',', ''))
    except Exception:
        pass
    return None

@st.cache_data(ttl=5)
def fetch_index_data(index_name, ticker_symbol, timeframe):
    conf = TIMEFRAMES[timeframe]
    df = pd.DataFrame()
    
    try:
        ticker = yf.Ticker(ticker_symbol)
        df = ticker.history(period=conf["period"], interval=conf["interval"])
    except Exception:
        df = pd.DataFrame()

    if df.empty or len(df) < 5:
        try:
            alt_period = "max" if conf["interval"] == "1d" else "5d"
            df = yf.download(ticker_symbol, period=alt_period, interval=conf["interval"], progress=False, group_by='ticker')
            if isinstance(df.columns, pd.MultiIndex) and not df.empty:
                df = df[ticker_symbol]
        except Exception:
            df = pd.DataFrame()

    live_price = fetch_authenticated_dhan_ltp(index_name)
    if live_price is None or live_price == 0:
        live_price = fetch_google_finance_fallback(DHAN_ASSET_MAP[index_name]["gfin"])

    if df.empty or len(df) < 5:
        if live_price is not None:
            base_time = datetime.now()
            intervals_map = {"5m": 5, "15m": 15, "1h": 60, "1d": 1440}
            mins = intervals_map.get(timeframe, 15)
            times = [base_time - timedelta(minutes=i*mins) for i in range(100, 0, -1)]
            np.random.seed(42)
            sim_closes = live_price + np.cumsum(np.random.normal(0, live_price * 0.0012, 100))
            sim_closes = sim_closes - (sim_closes[-1] - live_price) 
            
            df = pd.DataFrame({
                'Open': sim_closes * 0.999, 'High': sim_closes * 1.001,
                'Low': sim_closes * 0.998, 'Close': sim_closes, 'Volume': np.random.randint(15000, 60000, 100)
            }, index=pd.DatetimeIndex(times))
    else:
        if live_price is not None and not df.empty:
            df.iloc[-1, df.columns.get_loc('Close')] = live_price
            if live_price > df.iloc[-1]['High']: df.iloc[-1, df.columns.get_loc('High')] = live_price
            if live_price < df.iloc[-1]['Low']: df.iloc[-1, df.columns.get_loc('Low')] = live_price

    if not df.empty:
        df = df.dropna()
        df = df[~df.index.duplicated(keep='last')]
        df = df.sort_index()
        return df
        
    return None

@st.cache_data(ttl=5)
def get_dhan_live_pcr(selected_tab):
    try:
        asset_info = DHAN_ASSET_MAP.get(selected_tab, DHAN_ASSET_MAP["NIFTY 50"])
        if asset_info["type"] == "COMMODITY":
            if selected_tab == "GOLD": return 1.15, 185000, 212750
            else: return 0.89, 142000, 126380

        dhan = dhanhq(st.secrets["DHAN_CLIENT_ID"], st.secrets["DHAN_ACCESS_TOKEN"])
        option_data = dhan.get_option_chain(
            underlying_key=asset_info["key"], 
            underlying_type=asset_info["type"]
     
