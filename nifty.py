# ============================================================
# INTRADAY CONFLUENCE SCREENER - FULL UPGRADE v4.0
# Upgrades: Threading, Dhan API, EMA Stack, Dynamic Confidence,
#           Real Volume Ratio, BankNifty Filter, WebSocket Engine
# ============================================================
import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
import time
import requests
import threading
import queue
from concurrent.futures import ThreadPoolExecutor, as_completed

# ============================================================
# PAGE CONFIG
# ============================================================
st.set_page_config(page_title="Intraday Screener v4", layout="wide", page_icon="⚡")

st.markdown("""
<style>
html, body, [data-testid="stAppViewContainer"] {
    background-color: #080808 !important; color: #e0e0e0;
}
[data-testid="stSidebar"] { background-color: #0d0d0d !important; }
.block-container { padding-top: 0.5rem; }
.live-badge {
    display: inline-block; background: #00e676; color: #000;
    font-size: 11px; font-weight: bold; padding: 2px 10px;
    border-radius: 20px; animation: pulse 1.2s infinite; margin-left: 8px;
}
.ws-badge {
    display: inline-block; background: #2979ff; color: #fff;
    font-size: 11px; font-weight: bold; padding: 2px 8px;
    border-radius: 20px; margin-left: 6px;
}
.dhan-badge {
    display: inline-block; background: #ff6d00; color: #fff;
    font-size: 11px; font-weight: bold; padding: 2px 8px;
    border-radius: 20px; margin-left: 6px;
}
@keyframes pulse { 0%{opacity:1} 50%{opacity:0.25} 100%{opacity:1} }
.header-title {
    font-size: 22px; font-weight: 800; letter-spacing: 2px;
    color: #fff; font-family: 'Courier New', monospace;
}
textarea {
    background: #111 !important; color: #e0e0e0 !important;
    font-family: 'Courier New', monospace !important;
}
div[data-testid="stDataFrame"] { font-size: 12px; }
</style>
""", unsafe_allow_html=True)

# ============================================================
# SESSION STATE
# ============================================================
for k, v in {
    "auth": False,
    "sent_alerts": {},
    "ws_prices": {},        # WebSocket live prices cache
    "ws_volumes": {},       # WebSocket live volumes cache
    "ws_connected": False,
    "last_results": [],     # Cache last scan results
}.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ============================================================
# PASSWORD WALL
# ============================================================
if not st.session_state["auth"]:
    st.markdown("""
    <div style='text-align:center;padding:70px 0 16px 0;'>
        <div style='font-size:48px;'>🔒</div>
        <div style='font-size:20px;font-weight:bold;font-family:Courier New;
                    color:#fff;margin:14px 0 6px 0;'>AUTHORIZED ACCESS ONLY</div>
        <div style='font-size:11px;color:#333;font-family:Courier New;
                    letter-spacing:3px;'>INTRADAY SCREENER v4.0 - NSE</div>
    </div>
    """, unsafe_allow_html=True)
    _, col, _ = st.columns([1, 2, 1])
    with col:
        pwd = st.text_input("", placeholder="Password enter karo...",
                            type="password", label_visibility="collapsed")
        if st.button("LOGIN >>", use_container_width=True):
            try:
                correct = st.secrets["MY_APP_PASSWORD"]
            except Exception:
                correct = "admin123"
            if pwd == correct:
                st.session_state["auth"] = True
                st.rerun()
            else:
                st.error("Wrong password!")
    st.stop()

# ============================================================
# DHAN API - UPGRADE 2
# Real-time price fetcher using Dhan brokerage API
# ============================================================
DHAN_SECURITY_IDS = {
    "RELIANCE":   "2885",  "HDFCBANK":   "1333",
    "TCS":        "11536", "INFY":       "1594",
    "SBIN":       "3045",  "ICICIBANK":  "4963",
    "BHARTIARTL": "10604", "AXISBANK":   "596",
    "TATASTEEL":  "3499",  "ITC":        "1660",
    "LT":         "11483", "TATAMOTORS": "3456",
    "SUNPHARMA":  "3351",  "KOTAKBANK":  "1922",
    "BAJFINANCE": "317",   "WIPRO":      "3787",
    "HCLTECH":    "7229",  "MARUTI":     "10999",
    "ADANIENT":   "25",    "NTPC":       "11630",
    # BankNifty components
    "HDFCBANK":   "1333",  "ICICIBANK":  "4963",
    "KOTAKBANK":  "1922",  "AXISBANK":   "596",
    "INDUSINDBK": "5258",  "BANDHANBNK": "2263",
    "FEDERALBNK": "1023",  "IDFCFIRSTB": "17873",
    "AUBANK":     "3660",  "PNB":        "14366",
}

def get_dhan_price(symbol):
    """Fetch live price from Dhan API"""
    try:
        token   = st.secrets["DHAN_ACCESS_TOKEN"]
        client  = st.secrets["DHAN_CLIENT_ID"]
        sec_id  = DHAN_SECURITY_IDS.get(symbol)
        if not sec_id:
            return None
        url  = "https://api.dhan.co/v2/marketfeed/ltp"
        hdrs = {
            "access-token": token,
            "client-id":    client,
            "Content-Type": "application/json",
        }
        payload = {
            "NSE_EQ": [int(sec_id)]
        }
        r = requests.post(url, json=payload, headers=hdrs, timeout=3)
        if r.status_code == 200:
            data = r.json()
            ltp = data.get("data", {}).get("NSE_EQ", {}).get(sec_id, {}).get("last_price")
            if ltp:
                return float(ltp)
    except Exception:
        pass
    return None

def get_dhan_ohlcv(symbol, interval="15"):
    """Fetch OHLCV candles from Dhan intraday API"""
    try:
        token   = st.secrets["DHAN_ACCESS_TOKEN"]
        client  = st.secrets["DHAN_CLIENT_ID"]
        sec_id  = DHAN_SECURITY_IDS.get(symbol)
        if not sec_id:
            return None
        url  = "https://api.dhan.co/v2/charts/intraday"
        hdrs = {
            "access-token": token,
            "client-id":    client,
            "Content-Type": "application/json",
        }
        payload = {
            "securityId":    sec_id,
            "exchangeSegment": "NSE_EQ",
            "instrument":    "EQUITY",
            "interval":      interval,
            "oi":            False,
        }
        r = requests.post(url, json=payload, headers=hdrs, timeout=5)
        if r.status_code == 200:
            d = r.json()
            df = pd.DataFrame({
                "Open":   d.get("open",   []),
                "High":   d.get("high",   []),
                "Low":    d.get("low",    []),
                "Close":  d.get("close",  []),
                "Volume": d.get("volume", []),
            })
            if len(df) >= 10:
                return df
    except Exception:
        pass
    return None

# ============================================================
# UPGRADE 7 - WEBSOCKET LIVE PRICE ENGINE
# Simulated WebSocket using Dhan LTP polling in background thread
# Real WebSocket would need dhanhq library with async support
# ============================================================
_ws_stop_event = threading.Event()

def _ws_price_worker(symbols, interval_sec=2):
    """
    Background thread - polls Dhan LTP every 2 seconds
    Updates st.session_state ws_prices and ws_volumes
    Falls back to yfinance if Dhan unavailable
    """
    while not _ws_stop_event.is_set():
        for sym in symbols:
            try:
                # Try Dhan first
                price = get_dhan_price(sym)
                if price:
                    st.session_state["ws_prices"][sym]    = price
                    st.session_state["ws_connected"]      = True
                else:
                    # Fallback: yfinance 1-min tick
                    tk = yf.Ticker(sym + ".NS")
                    info = tk.fast_info
                    lp = getattr(info, "last_price", None)
                    if lp:
                        st.session_state["ws_prices"][sym] = float(lp)
            except Exception:
                pass
        time.sleep(interval_sec)

def start_ws_engine(symbols):
    """Start background WebSocket-like price thread if not running"""
    if "ws_thread" not in st.session_state or \
       not st.session_state.get("ws_thread_alive", False):
        _ws_stop_event.clear()
        t = threading.Thread(
            target=_ws_price_worker,
            args=(symbols,),
            daemon=True
        )
        t.start()
        st.session_state["ws_thread"]       = t
        st.session_state["ws_thread_alive"] = True

# ============================================================
# TELEGRAM
# ============================================================
def send_telegram(msg):
    try:
        token   = st.secrets["TELEGRAM_BOT_TOKEN"]
        chat_id = st.secrets["TELEGRAM_CHAT_ID"]
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data={"chat_id": chat_id, "text": msg, "parse_mode": "HTML"},
            timeout=5
        )
    except Exception:
        pass

def maybe_alert(ticker, sig, price, atr, confidence):
    if sig not in ("🟢 STRONG BUY", "🔴 STRONG SELL"):
        return
    key  = f"{ticker}_{sig}"
    now  = time.time()
    last = st.session_state["sent_alerts"].get(key, 0)
    if now - last < 900:
        return
    sl_b  = round(price - 1.5 * atr, 2)
    sl_s  = round(price + 1.5 * atr, 2)
    tgt_b = round(price + 3.0 * atr, 2)
    tgt_s = round(price - 3.0 * atr, 2)
    if sig == "🟢 STRONG BUY":
        msg = (f"🟢 <b>STRONG BUY</b>\n\n<b>{ticker}</b>\n\n"
               f"Price:      Rs {price:.2f}\n"
               f"SL:         Rs {sl_b:.2f}\n"
               f"Target:     Rs {tgt_b:.2f}\n"
               f"Confidence: {confidence}%")
    else:
        msg = (f"🔴 <b>STRONG SELL</b>\n\n<b>{ticker}</b>\n\n"
               f"Price:      Rs {price:.2f}\n"
               f"SL:         Rs {sl_s:.2f}\n"
               f"Target:     Rs {tgt_s:.2f}\n"
               f"Confidence: {confidence}%")
    send_telegram(msg)
    st.session_state["sent_alerts"][key] = now

# ============================================================
# INDICATORS
# ============================================================
def ema(s, p):
    return s.ewm(span=p, adjust=False).mean()

def calc_rsi(s, n=14):
    d    = s.diff()
    g    = d.clip(lower=0).ewm(alpha=1/n, adjust=False).mean()
    l    = (-d.clip(upper=0)).ewm(alpha=1/n, adjust=False).mean()
    return 100 - (100 / (1 + g / (l + 1e-10)))

def macd_hist(s):
    ml = ema(s, 12) - ema(s, 26)
    return ml - ema(ml, 9)

def vwap_calc(df):
    tp = (df["High"] + df["Low"] + df["Close"]) / 3
    return (tp * df["Volume"]).cumsum() / df["Volume"].cumsum()

def calc_atr(df, p=14):
    tr = pd.concat([
        df["High"] - df["Low"],
        (df["High"] - df["Close"].shift()).abs(),
        (df["Low"]  - df["Close"].shift()).abs()
    ], axis=1).max(axis=1)
    return tr.rolling(p).mean()

def supertrend(df, p=10, m=3):
    hl2 = (df["High"] + df["Low"]) / 2
    atr = calc_atr(df, p)
    up  = hl2 + m * atr
    dn  = hl2 - m * atr
    d   = pd.Series(0, index=df.index)
    for i in range(1, len(df)):
        if   df["Close"].iloc[i] > up.iloc[i-1]: d.iloc[i] =  1
        elif df["Close"].iloc[i] < dn.iloc[i-1]: d.iloc[i] = -1
        else: d.iloc[i] = d.iloc[i-1]
    return d

def mkt_structure(close):
    v = close.tail(30).values
    H, L = [], []
    for i in range(1, len(v)-1):
        if v[i] > v[i-1] and v[i] > v[i+1]: H.append(v[i])
        if v[i] < v[i-1] and v[i] < v[i+1]: L.append(v[i])
    if len(H) >= 2 and len(L) >= 2:
        if H[-1] > H[-2] and L[-1] > L[-2]: return "HH+HL 🟢"
        if H[-1] < H[-2] and L[-1] < L[-2]: return "LH+LL 🔴"
    return "Choppy ⚪"

def fib_nearest(df, price):
    hi = float(df["High"].max())
    lo = float(df["Low"].min())
    d  = max(hi - lo, 1)
    lvl = {"0%": hi, "23.6%": hi-0.236*d, "38.2%": hi-0.382*d,
           "50%": hi-0.5*d, "61.8%": hi-0.618*d, "100%": lo}
    k = min(lvl, key=lambda x: abs(lvl[x] - price))
    return f"{k} Rs{lvl[k]:.0f}"

def fmtvol(v):
    if v >= 1e6: return f"{v/1e6:.1f}M"
    if v >= 1e3: return f"{v/1e3:.1f}K"
    return str(int(v))

# ============================================================
# UPGRADE 3 - EMA 20/50 STACK
# ============================================================
def ema_stack(close):
    """
    EMA 9/20/50/200 full stack analysis
    Returns trend grade: Strong/Moderate/Weak/Bear
    """
    n   = len(close)
    e9  = float(ema(close, 9).iloc[-1])
    e20 = float(ema(close, 20).iloc[-1])
    e50 = float(ema(close, min(50,  n-1)).iloc[-1])
    e200= float(ema(close, min(200, n-1)).iloc[-1])
    px  = float(close.iloc[-1])

    bull_count = sum([px>e9, px>e20, px>e50, px>e200,
                      e9>e20, e20>e50, e50>e200])
    if bull_count >= 6: return "🟢 Strong",  e9, e20, e50, e200
    if bull_count >= 4: return "🟡 Moderate", e9, e20, e50, e200
    if bull_count >= 2: return "⚪ Weak",     e9, e20, e50, e200
    return "🔴 Bear Stack",                    e9, e20, e50, e200

# ============================================================
# UPGRADE 5 - REAL VOLUME RATIO
# ============================================================
def real_volume_ratio(volume_series):
    """
    Volume ratio = current vol / 20-period avg
    Classifies: Climax / Surge / Above / Normal / Dry
    """
    vol_now = float(volume_series.iloc[-1])
    vol_avg = float(volume_series.rolling(20).mean().iloc[-1])
    if vol_avg == 0:
        return "Normal", 1.0
    ratio = vol_now / vol_avg
    if ratio >= 4.0:   label = "CLIMAX 🌋"
    elif ratio >= 2.0: label = "SURGE 🚀"
    elif ratio >= 1.3: label = "Above Avg"
    elif ratio >= 0.7: label = "Normal"
    else:              label = "Dry 📉"
    return label, round(ratio, 2)

# ============================================================
# UPGRADE 6 - BANKNIFTY FILTER
# ============================================================
@st.cache_data(ttl=60)
def get_banknifty_trend(interval):
    """BankNifty trend for banking stocks filter"""
    try:
        df = yf.download("^NSEBANK", period="2d", interval=interval,
                         progress=False, auto_adjust=True)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df.dropna()
        if len(df) < 10:
            return "⚪ Unknown", 0.0
        cl  = df["Close"].squeeze()
        e20 = float(ema(cl, 20).iloc[-1])
        e50 = float(ema(cl, min(50, len(cl)-1)).iloc[-1])
        px  = float(cl.iloc[-1])
        chg = (px / float(cl.iloc[-20]) - 1) * 100 if len(cl) >= 20 else 0
        if px > e20 > e50:   return "🟢 Bull", round(chg, 2)
        elif px < e20 < e50: return "🔴 Bear", round(chg, 2)
        return "⚪ Mixed", round(chg, 2)
    except Exception:
        return "⚪ Unknown", 0.0

BANKING_STOCKS = {
    "HDFCBANK","ICICIBANK","SBIN","AXISBANK","KOTAKBANK",
    "INDUSINDBK","BANDHANBNK","FEDERALBNK","IDFCFIRSTB","PNB","AUBANK"
}

# ============================================================
# UPGRADE 4 - DYNAMIC CONFIDENCE SCORE
# ============================================================
def dynamic_confidence(bull, bear, htf, rs, orb, vol_ratio,
                        ema_grade, is_sideways, vix_level):
    """
    Calculates confidence % based on:
    - Signal score spread
    - HTF alignment
    - Volume ratio
    - EMA stack quality
    - Market VIX conditions
    """
    if is_sideways:
        return 0

    spread   = bull - bear
    base     = 50

    # Score spread contribution
    base += min(spread * 4, 24)

    # HTF alignment
    if "HTF Bull" in htf or "HTF Bear" in htf:
        base += 8

    # Relative strength
    if "Strong" in rs or "Weak" in rs:
        base += 4

    # ORB
    if "Breakout" in orb or "Breakdown" in orb:
        base += 4

    # Volume quality
    if vol_ratio >= 4.0:   base += 6   # climax
    elif vol_ratio >= 2.0: base += 4   # surge
    elif vol_ratio < 0.7:  base -= 5   # dry

    # EMA stack quality
    if "Strong"   in ema_grade: base += 6
    elif "Moderate" in ema_grade: base += 3
    elif "Weak"   in ema_grade: base -= 3
    elif "Bear"   in ema_grade: base -= 6

    # VIX penalty
    if vix_level > 20:   base -= 10
    elif vix_level > 15: base -= 5

    return max(0, min(int(base), 95))

# ============================================================
# HELPER: fetch index data
# ============================================================
@st.cache_data(ttl=60)
def fetch_index(ticker, interval):
    try:
        df = yf.download(ticker, period="5d", interval=interval,
                         progress=False, auto_adjust=True)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return df.dropna()
    except Exception:
        return pd.DataFrame()

@st.cache_data(ttl=300)
def fetch_vix():
    try:
        df = yf.download("^INDIAVIX", period="1d", interval="1h",
                         progress=False, auto_adjust=True)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return float(df["Close"].iloc[-1]) if not df.empty else 15.0
    except Exception:
        return 15.0

def higher_tf_trend(symbol):
    try:
        df  = yf.download(symbol+".NS", period="10d", interval="15m",
                          progress=False, auto_adjust=True)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df  = df.dropna()
        cl  = df["Close"].squeeze()
        e20 = float(ema(cl, 20).iloc[-1])
        e50 = float(ema(cl, min(50, len(cl)-1)).iloc[-1])
        px  = float(cl.iloc[-1])
        if px > e20 > e50:   return "🟢 HTF Bull"
        elif px < e20 < e50: return "🔴 HTF Bear"
        return "⚪ Mixed"
    except Exception:
        return "⚪ Unknown"

def relative_strength(stock_close, nifty_close):
    try:
        sc  = stock_close.squeeze()
        nc  = nifty_close.squeeze()
        n   = min(len(sc), len(nc), 10)
        if n < 2: return "⚪ Neutral"
        sr  = float(sc.iloc[-1]) / float(sc.iloc[-n])
        nr  = float(nc.iloc[-1]) / float(nc.iloc[-n])
        rs  = sr / (nr + 1e-10)
        if rs > 1.02:   return "🟢 Strong"
        elif rs < 0.98: return "🔴 Weak"
        return "⚪ Neutral"
    except Exception:
        return "⚪ Neutral"

def opening_range_breakout(df):
    try:
        orb_h = float(df.head(3)["High"].max())
        orb_l = float(df.head(3)["Low"].min())
        cur   = float(df["Close"].iloc[-1])
        if cur > orb_h:   return "🟢 ORB Breakout"
        elif cur < orb_l: return "🔴 ORB Breakdown"
        return "⚪ Inside Range"
    except Exception:
        return "⚪ Unknown"

def sideways_market(df):
    try:
        atr = float(calc_atr(df).iloc[-1])
        px  = float(df["Close"].iloc[-1])
        return (atr / px) < 0.003
    except Exception:
        return False

# ============================================================
# UPGRADE 1 - PARALLEL THREADING CORE ANALYZE
# ============================================================
def analyze_one(sym, interval, nifty_df, bn_trend, vix_level,
                use_dhan, use_ws):
    """
    Analyzes a single stock. Called in parallel via ThreadPoolExecutor.
    """
    ticker = sym.strip().upper()
    ns     = ticker + ".NS"
    try:
        # --- DATA SOURCE PRIORITY ---
        # 1. Dhan OHLCV (if enabled and key present)
        # 2. yfinance fallback
        df = None
        dhan_src = False

        if use_dhan:
            dhan_interval_map = {"1m":"1","5m":"5","15m":"15","1h":"60"}
            di = dhan_interval_map.get(interval, "15")
            df = get_dhan_ohlcv(ticker, di)
            if df is not None and len(df) >= 20:
                dhan_src = True

        if df is None:
            df = yf.download(ns, period="2d", interval=interval,
                             progress=False, auto_adjust=True)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            df = df.dropna()

        if df is None or len(df) < 20:
            return None

        cl  = df["Close"].squeeze()
        vo  = df["Volume"].squeeze()

        # Live price override from WebSocket cache if available
        ws_price = st.session_state["ws_prices"].get(ticker)
        px       = float(ws_price if ws_price else cl.iloc[-1])

        # -- Core indicators --
        rv   = float(calc_rsi(cl).iloc[-1])
        mh   = float(macd_hist(cl).iloc[-1])
        mhp  = float(macd_hist(cl).iloc[-2])
        vw   = float(vwap_calc(df).iloc[-1])
        st_d = int(supertrend(df).iloc[-1])
        atr  = float(calc_atr(df).iloc[-1])

        # UPGRADE 5 - Real Volume Ratio
        vol_label, vol_ratio = real_volume_ratio(vo)

        # UPGRADE 3 - EMA 20/50 Stack
        ema_grade, e9, e20, e50, e200 = ema_stack(cl)

        # PDH/PDL
        today = df.index[-1].date() if hasattr(df.index[-1], "date") else datetime.today().date()
        prev  = df[pd.to_datetime(df.index).date < today]
        pdh   = float(prev["High"].max()) if not prev.empty else float(df["High"].max())
        pdl   = float(prev["Low"].min())  if not prev.empty else float(df["Low"].min())

        # Extra signals
        htf      = higher_tf_trend(ticker)
        is_side  = sideways_market(df)
        rs       = relative_strength(cl, nifty_df["Close"]) if not nifty_df.empty else "⚪ Neutral"
        orb      = opening_range_breakout(df)
        struct_s = mkt_structure(cl)
        fib_s    = fib_nearest(df, px)

        # -- Format display strings --
        ema_s  = f"🟢 E9:{e9:.0f}" if px > e9  else f"🔴 E9:{e9:.0f}"
        vwap_s = f"🟢 {vw:.1f}"   if px > vw  else f"🔴 {vw:.1f}"
        rsi_s  = f"{rv:.1f}{'OB' if rv>70 else ('OS' if rv<30 else '')}"
        macd_s = ("🟢 Rise" if mh > 0 and mh > mhp else
                  ("🔴 Fall" if mh < 0 and mh < mhp else "⚪ Flat"))
        st_s   = "🟢 Bull" if st_d == 1 else ("🔴 Bear" if st_d == -1 else "⚪")
        pdh_s  = "🟢 >PDH" if px > pdh else "🔴 <PDH"
        vol_s  = f"{vol_label} x{vol_ratio:.1f}"
        src_s  = "DHAN" if dhan_src else ("WS" if ws_price else "YF")

        # UPGRADE 6 - BankNifty filter for banking stocks
        bn_filter = ""
        if ticker in BANKING_STOCKS:
            if "Bull" in bn_trend and "Bear" in macd_s:
                bn_filter = "⚠️ BN-Bull/ST-Conflict"
            elif "Bear" in bn_trend and "🟢" in macd_s:
                bn_filter = "⚠️ BN-Bear/ST-Conflict"
            else:
                bn_filter = f"BN:{bn_trend.split()[0]}"

        # -- SCORING --
        b = be = 0
        if "🟢" in ema_s:    b  += 1
        else:                 be += 1
        if "🟢" in vwap_s:   b  += 1
        else:                 be += 1
        try:
            r = float(rsi_s[:4])
            if 50 <= r <= 65:  b  += 1
            elif 35 <= r < 50: be += 1
        except: pass
        if "🟢" in macd_s:   b  += 1
        elif "🔴" in macd_s: be += 1
        # Volume quality scoring
        if vol_ratio >= 2.0:   b  += 1; be += 1
        elif vol_ratio < 0.7:  b  -= 1; be -= 1
        if "HH" in struct_s:  b  += 1
        elif "LH" in struct_s: be += 1
        if "🟢" in st_s:     b  += 1
        elif "🔴" in st_s:   be += 1
        if "🟢" in pdh_s:    b  += 1
        else:                  be += 1
        # HTF double weight
        if "HTF Bull" in htf:  b  += 2
        elif "HTF Bear" in htf: be += 2
        # RS
        if "Strong" in rs:     b  += 1
        elif "Weak" in rs:     be += 1
        # ORB
        if "Breakout" in orb:   b  += 1
        elif "Breakdown" in orb: be += 1
        # EMA Stack bonus
        if "Strong" in ema_grade:   b  += 2
        elif "Moderate" in ema_grade: b += 1
        elif "Bear"  in ema_grade:  be += 2
        elif "Weak"  in ema_grade:  be += 1
        # BankNifty alignment bonus
        if ticker in BANKING_STOCKS and "Bull" in bn_trend: b  += 1
        if ticker in BANKING_STOCKS and "Bear" in bn_trend: be += 1

        b  = max(b,  0)
        be = max(be, 0)

        # UPGRADE 4 - Dynamic Confidence
        confidence = dynamic_confidence(
            b, be, htf, rs, orb, vol_ratio,
            ema_grade, is_side, vix_level
        )

        # Signal
        if is_side:
            sig = "⚪ SIDEWAYS"
        else:
            sc = b - be
            if sc >= 7:    sig = "🟢 STRONG BUY"
            elif sc >= 3:  sig = "🟡 BUY"
            elif sc <= -7: sig = "🔴 STRONG SELL"
            elif sc <= -3: sig = "🟠 SELL"
            else:          sig = "⚪ WAIT"

        row = {
            "Stock":    ticker,
            "Src":      src_s,
            "Price":    f"Rs{px:.1f}",
            "EMA":      ema_s,
            "EMAStack": ema_grade,
            "VWAP":     vwap_s,
            "RSI":      rsi_s,
            "MACD":     macd_s,
            "Volume":   vol_s,
            "ST":       st_s,
            "PDH":      pdh_s,
            "Struct":   struct_s,
            "HTF":      htf,
            "RS":       rs,
            "ORB":      orb,
            "Fib":      fib_s,
            "BNifty":   bn_filter if bn_filter else "-",
            "Bull":     b,
            "Bear":     be,
            "Conf%":    f"{confidence}%",
            "Signal":   sig,
        }

        # Telegram alert with dynamic confidence
        maybe_alert(ticker, sig, px, atr, confidence)
        return row

    except Exception:
        return {
            "Stock": ticker, "Src": "ERR", "Price": "Error",
            "EMA": "-", "EMAStack": "-", "VWAP": "-", "RSI": "-",
            "MACD": "-", "Volume": "-", "ST": "-", "PDH": "-",
            "Struct": "-", "HTF": "-", "RS": "-", "ORB": "-",
            "Fib": "-", "BNifty": "-", "Bull": 0, "Bear": 0,
            "Conf%": "0%", "Signal": "ERR"
        }

# ============================================================
# UPGRADE 1 - PARALLEL SCAN using ThreadPoolExecutor
# ============================================================
def parallel_scan(stocks, interval, nifty_df, bn_trend, vix_level,
                  use_dhan, use_ws):
    results = []
    # max_workers=8 = 8 stocks scanned simultaneously
    with ThreadPoolExecutor(max_workers=min(8, len(stocks))) as exe:
        futures = {
            exe.submit(
                analyze_one, sym, interval, nifty_df,
                bn_trend, vix_level, use_dhan, use_ws
            ): sym for sym in stocks
        }
        for fut in as_completed(futures):
            r = fut.result()
            if r:
                results.append(r)
    # Sort by original stock order
    order = {s: i for i, s in enumerate(stocks)}
    results.sort(key=lambda x: order.get(x["Stock"], 99))
    return results

# ============================================================
# SIDEBAR
# ============================================================
with st.sidebar:
    st.markdown("### Settings")

    st.markdown("**Stock Names (NSE Symbol, ek line = ek):**")
    stock_input = st.text_area(
        "", height=220, label_visibility="collapsed",
        value="RELIANCE\nHDFCBANK\nTCS\nINFY\nSBIN\nICICIBANK\nAXISBANK\nTATAMOTORS\nITC\nLT"
    )

    interval  = st.selectbox("Timeframe:", ["1m","5m","15m","1h"], index=2)
    refresh   = st.selectbox("Refresh:", [5,10,15,30,60], index=2,
                             format_func=lambda x: f"{x} sec")
    show_f    = st.selectbox("Show:", ["All","BUY Only","SELL Only","Strong Only","Conf > 70%"])

    st.markdown("---")
    use_dhan = st.toggle("Dhan API (live price)", value=False,
                         help="Requires DHAN_ACCESS_TOKEN + DHAN_CLIENT_ID in secrets")
    use_ws   = st.toggle("WebSocket Engine", value=True,
                         help="Background price polling thread")
    tg_on    = st.toggle("Telegram Alerts",   value=True)

    st.markdown("---")
    if st.button("Logout"):
        st.session_state["auth"] = False
        st.rerun()

stocks = list(dict.fromkeys(
    [s.strip().upper() for s in stock_input.splitlines() if s.strip()]
))[:20]

# ============================================================
# START WEBSOCKET ENGINE (background thread)
# ============================================================
if use_ws and stocks:
    start_ws_engine(stocks)

# ============================================================
# HEADER
# ============================================================
ws_badge   = '<span class="ws-badge">WS ON</span>'   if use_ws  else ""
dhan_badge = '<span class="dhan-badge">DHAN</span>'  if use_dhan else ""
st.markdown(f"""
<div style='margin-bottom:4px;'>
  <span class='header-title'>INTRADAY SCREENER v4.0</span>
  <span class='live-badge'>LIVE</span>
  {ws_badge}{dhan_badge}
</div>
<div style='font-size:11px;color:#333;font-family:Courier New;
            letter-spacing:2px;margin-bottom:10px;'>
  NSE | THREADING | DHAN | EMA STACK | DYNAMIC CONF | VOL RATIO | BN FILTER
</div>
""", unsafe_allow_html=True)

if not stocks:
    st.warning("Sidebar mein stock names likho")
    st.stop()

summary_ph = st.empty()
table_ph   = st.empty()
status_ph  = st.empty()

with st.expander("Strategy + Scoring Guide"):
    st.markdown("""
| Indicator | BUY | SELL | Pts |
|-----------|-----|------|-----|
| EMA 9 | Above | Below | 1 |
| EMA Stack (20/50/200) | Strong | Bear | 1-2 |
| VWAP | Above | Below | 1 |
| RSI | 50-65 | 35-50 | 1 |
| MACD | Rising | Falling | 1 |
| Real Volume | Surge x2+ | Dry <0.7x | 1 |
| Supertrend | Bull | Bear | 1 |
| PDH | Above | Below | 1 |
| Structure | HH+HL | LH+LL | 1 |
| HTF (15m) | HTF Bull | HTF Bear | 2 |
| Rel. Strength | Strong | Weak | 1 |
| ORB | Breakout | Breakdown | 1 |
| BankNifty | Aligned | Conflict | 1 |

Score +7 = STRONG BUY | Score -7 = STRONG SELL
Sideways (ATR<0.3%) = skip
Confidence 0-95% = dynamic based on all factors
    """)

st.caption("yfinance/Dhan feed. Analysis tool only - use your own judgment.")

# ============================================================
# MAIN LIVE LOOP
# ============================================================
cycle = 0
while True:
    cycle += 1
    t0 = time.time()

    # Fetch shared data once
    nifty_df         = fetch_index("^NSEI",    interval)
    bn_trend_str, _  = get_banknifty_trend(interval)
    vix              = fetch_vix()

    # UPGRADE 1 - Parallel scan
    results = parallel_scan(
        stocks, interval, nifty_df, bn_trend_str, vix,
        use_dhan, use_ws
    )

    if results:
        df_all  = pd.DataFrame(results)
        df_show = df_all.copy()

        if show_f == "BUY Only":
            df_show = df_show[df_show["Signal"].str.contains("BUY",  na=False)]
        elif show_f == "SELL Only":
            df_show = df_show[df_show["Signal"].str.contains("SELL", na=False)]
        elif show_f == "Strong Only":
            df_show = df_show[df_show["Signal"].str.contains("STRONG", na=False)]
        elif show_f == "Conf > 70%":
            df_show = df_show[
                df_show["Conf%"].str.replace("%","").apply(
                    lambda x: int(x) > 70 if x.isdigit() else False
                )
            ]

        # Styling - pandas 2.1+ safe .map()
        def sig_style(v):
            s = str(v)
            if "STRONG BUY"  in s: return "background:#0a2e0a;color:#00e676;font-weight:bold"
            if "BUY"         in s: return "background:#071a07;color:#69f0ae"
            if "STRONG SELL" in s: return "background:#2e0808;color:#ff1744;font-weight:bold"
            if "SELL"        in s: return "background:#1a0505;color:#ff6d00"
            if "SIDEWAYS"    in s: return "background:#1a1800;color:#ffd740"
            return "color:#444"

        def cell_style(v):
            s = str(v)
            if "🟢" in s: return "color:#00e676"
            if "🔴" in s: return "color:#ff5252"
            if "SURGE" in s or "CLIMAX" in s: return "color:#40c4ff;font-weight:bold"
            if "Dry"   in s: return "color:#ff6d00"
            if "OB"    in s or "OS" in s: return "color:#ffd740"
            return "color:#aaa"

        def conf_style(v):
            try:
                n = int(str(v).replace("%",""))
                if n >= 80: return "color:#00e676;font-weight:bold"
                if n >= 60: return "color:#ffd740"
                return "color:#666"
            except: return ""

        cc = [c for c in ["EMA","EMAStack","VWAP","MACD","ST","PDH","Volume","Struct","HTF","RS","ORB","BNifty"]
              if c in df_show.columns]

        styler = (
            df_show.style
            .map(sig_style,  subset=["Signal"])
            .map(cell_style, subset=cc)
            .map(conf_style, subset=["Conf%"])
            .set_properties(**{"font-size": "11.5px", "font-family": "Courier New"})
            .hide(axis="index")
        )

        # Counts
        sb = (df_all["Signal"] == "🟢 STRONG BUY").sum()
        b  = (df_all["Signal"] == "🟡 BUY").sum()
        ss = (df_all["Signal"] == "🔴 STRONG SELL").sum()
        sl = (df_all["Signal"] == "🟠 SELL").sum()
        sw = (df_all["Signal"] == "⚪ SIDEWAYS").sum()
        w  = (df_all["Signal"] == "⚪ WAIT").sum()

        elapsed = round(time.time() - t0, 1)
        now     = datetime.now().strftime("%H:%M:%S")
        ws_s    = "ON" if st.session_state.get("ws_connected") else "OFF"

        with summary_ph.container():
            c1,c2,c3,c4,c5,c6,c7,c8 = st.columns(8)
            c1.metric("🟢 S.Buy",    sb)
            c2.metric("🟡 Buy",      b)
            c3.metric("🔴 S.Sell",   ss)
            c4.metric("🟠 Sell",     sl)
            c5.metric("⚪ Sideways", sw)
            c6.metric("VIX",        f"{vix:.1f}")
            c7.metric("BankNifty",  bn_trend_str.split()[0] if bn_trend_str else "-")
            c8.metric("Threads",    f"{min(8,len(stocks))}")

        with table_ph.container():
            st.dataframe(styler, use_container_width=True,
                         height=min(80 + len(df_show) * 36, 580))

        with status_ph.container():
            st.caption(
                f"Clock: {now} | Cycle #{cycle} | "
                f"Scan: {elapsed}s | Next: {refresh}s | "
                f"Stocks: {len(stocks)} | WS: {ws_s} | "
                f"VIX: {vix:.1f} | TG: {'ON' if tg_on else 'OFF'}"
            )
    else:
        table_ph.error("Data nahi mila. Internet ya stock names check karo.")

    time.sleep(refresh)
