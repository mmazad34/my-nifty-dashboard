import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
import time

# ==========================================
# PAGE CONFIG
# ==========================================
st.set_page_config(
    page_title="⚡ Intraday Screener",
    layout="wide",
    page_icon="⚡"
)

# ==========================================
# CUSTOM CSS
# ==========================================
st.markdown("""
<style>
    html, body, [data-testid="stAppViewContainer"] {
        background-color: #0a0a0a !important;
        color: #e0e0e0;
    }
    [data-testid="stSidebar"] {
        background-color: #111111 !important;
    }
    .block-container { padding-top: 1rem; }
    div[data-testid="stDataFrame"] { font-size: 13px; }
    .live-badge {
        display: inline-block;
        background: #00e676;
        color: #000;
        font-size: 11px;
        font-weight: bold;
        padding: 2px 10px;
        border-radius: 20px;
        animation: pulse 1.5s infinite;
        margin-left: 10px;
    }
    @keyframes pulse {
        0%   { opacity: 1; }
        50%  { opacity: 0.4; }
        100% { opacity: 1; }
    }
    .header-title {
        font-size: 26px;
        font-weight: 800;
        letter-spacing: 2px;
        color: #ffffff;
        font-family: 'Courier New', monospace;
    }
    .stTextInput > div > input {
        background: #1a1a1a !important;
        color: #e0e0e0 !important;
        border: 1px solid #333 !important;
        border-radius: 6px;
    }
    .stButton > button {
        background: #1a1a1a;
        color: #00e676;
        border: 1px solid #00e676;
        border-radius: 6px;
        font-family: 'Courier New', monospace;
        font-weight: bold;
        letter-spacing: 1px;
    }
    .stButton > button:hover {
        background: #00e676;
        color: #000;
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 🔒 PASSWORD WALL — Streamlit Secrets
# ==========================================
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False

if not st.session_state["authenticated"]:
    st.markdown("""
    <div style='text-align:center; padding: 80px 0 20px 0;'>
        <div style='font-size:48px;'>🔒</div>
        <div style='font-size:24px; font-weight:bold; font-family: Courier New; color:#fff; margin:16px 0 8px 0;'>
            AUTHORIZED ACCESS ONLY
        </div>
        <div style='font-size:13px; color:#555; font-family: Courier New; letter-spacing:2px;'>
            INTRADAY CONFLUENCE SCREENER — NSE
        </div>
    </div>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        pwd = st.text_input("", placeholder="🔑 Password enter karo...", type="password", label_visibility="collapsed")
        login_btn = st.button("LOGIN →", use_container_width=True)

        if login_btn:
            try:
                correct = st.secrets["MY_APP_PASSWORD"]
            except Exception:
                correct = "admin123"  # fallback agar secrets set nahi hain (testing ke liye)

            if pwd == correct:
                st.session_state["authenticated"] = True
                st.rerun()
            else:
                st.error("❌ Wrong password! Access denied.")
    st.stop()

# ==========================================
# INDICATOR FUNCTIONS — Pure Python, no ta lib
# ==========================================

def calc_ema(series, period):
    return series.ewm(span=period, adjust=False).mean()

def calc_rsi(series, period=14):
    delta = series.diff()
    gain  = delta.clip(lower=0).rolling(period).mean()
    loss  = (-delta.clip(upper=0)).rolling(period).mean()
    rs    = gain / (loss + 1e-10)
    return 100 - (100 / (1 + rs))

def calc_macd(series):
    macd_line = calc_ema(series, 12) - calc_ema(series, 26)
    signal    = calc_ema(macd_line, 9)
    return macd_line - signal   # histogram

def calc_vwap(df):
    tp = (df['High'] + df['Low'] + df['Close']) / 3
    return (tp * df['Volume']).cumsum() / df['Volume'].cumsum()

def calc_supertrend(df, period=10, mult=3):
    hl2 = (df['High'] + df['Low']) / 2
    tr  = pd.concat([
        df['High'] - df['Low'],
        (df['High'] - df['Close'].shift(1)).abs(),
        (df['Low']  - df['Close'].shift(1)).abs()
    ], axis=1).max(axis=1)
    atr   = tr.rolling(period).mean()
    upper = hl2 + mult * atr
    lower = hl2 - mult * atr
    direction = pd.Series(0, index=df.index)
    for i in range(1, len(df)):
        if   df['Close'].iloc[i] > upper.iloc[i - 1]: direction.iloc[i] =  1
        elif df['Close'].iloc[i] < lower.iloc[i - 1]: direction.iloc[i] = -1
        else: direction.iloc[i] = direction.iloc[i - 1]
    return direction

def calc_fibonacci(df):
    high = float(df['High'].max())
    low  = float(df['Low'].min())
    diff = max(high - low, 1)
    return {
        "0% (High)":  round(high, 2),
        "23.6%":      round(high - 0.236 * diff, 2),
        "38.2%":      round(high - 0.382 * diff, 2),
        "50.0%":      round(high - 0.500 * diff, 2),
        "61.8% 🎯":   round(high - 0.618 * diff, 2),
        "100% (Low)": round(low,  2),
    }

def nearest_fib(price, fibs):
    key = min(fibs, key=lambda k: abs(fibs[k] - price))
    return f"{key} ₹{fibs[key]}"

def market_structure(close):
    vals = close.tail(30).values
    highs, lows = [], []
    for i in range(1, len(vals) - 1):
        if vals[i] > vals[i-1] and vals[i] > vals[i+1]: highs.append(vals[i])
        if vals[i] < vals[i-1] and vals[i] < vals[i+1]: lows.append(vals[i])
    if len(highs) >= 2 and len(lows) >= 2:
        if highs[-1] > highs[-2] and lows[-1] > lows[-2]: return "HH+HL 🟢"
        if highs[-1] < highs[-2] and lows[-1] < lows[-2]: return "LH+LL 🔴"
    return "Choppy ⚪"

def format_vol(v):
    if v >= 1_000_000: return f"{v/1_000_000:.1f}M"
    if v >= 1_000:     return f"{v/1_000:.1f}K"
    return str(int(v))

def score_and_verdict(row):
    bull = bear = 0
    if "🟢" in str(row.get("EMA","")): bull += 1
    else: bear += 1
    if "🟢" in str(row.get("VWAP","")): bull += 1
    else: bear += 1
    try:
        r = float(str(row.get("RSI","50")).split()[0])
        if 50 <= r <= 65: bull += 1
        elif 35 <= r < 50: bear += 1
    except: pass
    if "🟢" in str(row.get("MACD","")): bull += 1
    elif "🔴" in str(row.get("MACD","")): bear += 1
    if "SURGE" in str(row.get("Volume","")): bull += 1; bear += 1
    if "HH"   in str(row.get("Struct","")): bull += 1
    elif "LH" in str(row.get("Struct","")): bear += 1
    if "🟢"   in str(row.get("ST","")): bull += 1
    elif "🔴" in str(row.get("ST","")): bear += 1

    score = bull - bear
    if score >= 4:  verdict = "🟢 STRONG BUY"
    elif score >= 2: verdict = "🟡 BUY"
    elif score <= -4: verdict = "🔴 STRONG SELL"
    elif score <= -2: verdict = "🟠 SELL"
    else: verdict = "⚪ WAIT"
    return bull, bear, verdict

# ==========================================
# FETCH & ANALYZE ONE STOCK (no cache — live data)
# ==========================================

def analyze(symbol, interval):
    ticker = symbol.strip().upper() + ".NS"
    try:
        df = yf.download(ticker, period="2d", interval=interval, progress=False, auto_adjust=True)

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df.dropna()

        if len(df) < 20:
            return None

        close  = df['Close'].squeeze()
        volume = df['Volume'].squeeze()

        price     = float(close.iloc[-1])
        ema9      = float(calc_ema(close, 9).iloc[-1])
        ema21     = float(calc_ema(close, 21).iloc[-1])
        rsi_v     = float(calc_rsi(close).iloc[-1])
        macd_h    = float(calc_macd(close).iloc[-1])
        macd_h_p  = float(calc_macd(close).iloc[-2])
        vwap_v    = float(calc_vwap(df).iloc[-1])
        st_dir    = int(calc_supertrend(df).iloc[-1])
        vol_now   = float(volume.iloc[-1])
        vol_avg   = float(volume.rolling(20).mean().iloc[-1])

        # PDH / PDL
        today = df.index[-1].date()
        prev  = df[pd.to_datetime(df.index).date < today]
        pdh   = float(prev['High'].max()) if not prev.empty else float(df['High'].max())
        pdl   = float(prev['Low'].min())  if not prev.empty else float(df['Low'].min())

        fibs     = calc_fibonacci(df)
        fib_zone = nearest_fib(price, fibs)
        struct   = market_structure(close)

        rsi_flag = " ⚠️OB" if rsi_v > 70 else (" ⚠️OS" if rsi_v < 30 else "")

        row = {
            "Stock":  symbol.upper(),
            "Price":  f"₹{price:.2f}",
            "EMA":    f"🟢 {ema9:.1f}" if price > ema9 else f"🔴 {ema9:.1f}",
            "VWAP":   f"🟢 {vwap_v:.1f}" if price > vwap_v else f"🔴 {vwap_v:.1f}",
            "RSI":    f"{rsi_v:.1f}{rsi_flag}",
            "MACD":   "🟢 +Rising" if (macd_h > 0 and macd_h > macd_h_p) else (
                      "🔴 -Falling" if (macd_h < 0 and macd_h < macd_h_p) else "⚪ Flat"),
            "Volume": f"🚀 SURGE {format_vol(vol_now)}" if vol_now > 1.8 * vol_avg else f"Normal {format_vol(vol_now)}",
            "ST":     "🟢 Bull" if st_dir == 1 else ("🔴 Bear" if st_dir == -1 else "⚪"),
            "PDH":    "🟢 Above" if price > pdh else "🔴 Below",
            "Struct": struct,
            "Fib":    fib_zone,
        }

        bull, bear, verdict = score_and_verdict(row)
        row["✅Bull"] = bull
        row["🔴Bear"] = bear
        row["Signal"] = verdict
        return row

    except Exception:
        return {"Stock": symbol.upper(), "Price": "Error", "Signal": "❓ N/A",
                "EMA":"—","VWAP":"—","RSI":"—","MACD":"—","Volume":"—",
                "ST":"—","PDH":"—","Struct":"—","Fib":"—","✅Bull":0,"🔴Bear":0}

# ==========================================
# SIDEBAR — Settings
# ==========================================
with st.sidebar:
    st.markdown("### ⚙️ Settings")

    st.markdown("**📝 10 Stocks Likho (NSE Symbol):**")
    default_stocks = "RELIANCE\nHDFCBANK\nTCS\nINFY\nSBIN\nICICIBANK\nAXISBANK\nTATAMOTORS\nITC\nLT"
    stock_input = st.text_area(
        "",
        value=default_stocks,
        height=220,
        placeholder="Ek line mein ek stock\nExample:\nRELIANCE\nHDFCBANK",
        label_visibility="collapsed",
        help="NSE symbol likho — .NS mat likho, automatically add hoga"
    )

    interval = st.selectbox("⏱️ Timeframe:", ["1m", "5m", "15m", "1h"], index=2,
                            help="15m = best intraday | 1m = most live")

    refresh_sec = st.selectbox("🔄 Auto-Refresh Har:", [10, 15, 30, 60, 120], index=2,
                               format_func=lambda x: f"{x} seconds")

    st.markdown("---")
    show_filter = st.selectbox("👁️ Show:", ["All Signals", "BUY Only", "SELL Only", "Strong Only"])
    min_bull    = st.slider("Min Bull Score:", 0, 7, 0)

    st.markdown("---")
    if st.button("🔓 Logout"):
        st.session_state["authenticated"] = False
        st.rerun()

# Parse stocks
stocks = [s.strip().upper() for s in stock_input.strip().splitlines() if s.strip()]
stocks = list(dict.fromkeys(stocks))[:10]  # max 10, deduplicate

# ==========================================
# MAIN DASHBOARD
# ==========================================
st.markdown("""
<div style='margin-bottom:8px;'>
    <span class='header-title'>⚡ INTRADAY CONFLUENCE SCREENER</span>
    <span class='live-badge'>● LIVE</span>
</div>
<div style='font-size:12px; color:#555; font-family: Courier New; letter-spacing:2px; margin-bottom:16px;'>
    NSE MARKET SCANNER — REAL TIME ANALYSIS
</div>
""", unsafe_allow_html=True)

if not stocks:
    st.warning("⬅️ Sidebar mein stocks likho")
    st.stop()

# ── Top metrics bar ──────────────────────────────────────────
m1, m2, m3, m4, m5 = st.columns(5)
meta_placeholder   = st.empty()   # will hold live metrics

# ── Main table placeholder (NO page refresh) ────────────────
table_placeholder  = st.empty()
status_placeholder = st.empty()

# ── Summary counts placeholder ───────────────────────────────
summary_placeholder = st.empty()

# ── Expandable sections (static — render once) ───────────────
with st.expander("📘 Strategy Guide"):
    st.markdown("""
| Condition | BUY Signal | SELL Signal |
|-----------|-----------|------------|
| EMA 9 vs Price | 🟢 Price Above | 🔴 Price Below |
| VWAP | 🟢 Price Above | 🔴 Price Below |
| RSI | 50–65 zone | 35–50 zone |
| MACD Histogram | 🟢 +ve Rising | 🔴 -ve Falling |
| Volume | 🚀 SURGE (2x avg) | 🚀 SURGE (2x avg) |
| Supertrend | 🟢 Bullish | 🔴 Bearish |
| Structure | HH+HL 🟢 | LH+LL 🔴 |

**⚡ Entry Rule:** Signal score 5+ hone pe hi trade lo.
**🛡️ SL Rule:** Har trade mein 0.5–0.8% stop loss mandatory.
**💰 RR Rule:** Minimum 1:2 Risk:Reward target set karo.
    """)

st.markdown("---")
st.caption("⚠️ yfinance data 1–2 min delayed ho sakta hai free feed mein. Sirf analysis tool hai — apna judgment use karo.")

# ==========================================
# ♾️ TRUE LIVE LOOP — No page reload
# ==========================================
cycle = 0
while True:
    cycle += 1
    scan_start = time.time()

    # Fetch all stocks
    results = []
    for sym in stocks:
        row = analyze(sym, interval)
        if row:
            results.append(row)

    if results:
        df_all = pd.DataFrame(results)

        # Apply filters
        df_show = df_all.copy()
        if show_filter == "BUY Only":
            df_show = df_show[df_show["Signal"].str.contains("BUY", na=False)]
        elif show_filter == "SELL Only":
            df_show = df_show[df_show["Signal"].str.contains("SELL", na=False)]
        elif show_filter == "Strong Only":
            df_show = df_show[df_show["Signal"].str.contains("STRONG", na=False)]
        df_show = df_show[df_show["✅Bull"] >= min_bull]

        # Color styling
        def style_signal(val):
            if "STRONG BUY"  in str(val): return "background:#0d2e0d; color:#00e676; font-weight:bold"
            if "BUY"         in str(val): return "background:#0a200a; color:#69f0ae"
            if "STRONG SELL" in str(val): return "background:#2e0d0d; color:#ff1744; font-weight:bold"
            if "SELL"        in str(val): return "background:#200a0a; color:#ff6d00"
            return "color:#666"

        def style_cell(val):
            s = str(val)
            if "🟢" in s: return "color:#00e676"
            if "🔴" in s: return "color:#ff5252"
            if "⚠️" in s: return "color:#ffd740"
            if "🚀" in s: return "color:#40c4ff"
            return "color:#aaa"

        cols_to_color = [c for c in ["EMA","VWAP","MACD","ST","PDH","Volume","Struct"] if c in df_show.columns]

        styled = (
            df_show.style
            .applymap(style_signal, subset=["Signal"])
            .applymap(style_cell,   subset=cols_to_color)
            .set_properties(**{"font-size": "12.5px", "font-family": "Courier New"})
            .hide(axis="index")
        )

        # Summary counts
        n_sbuy  = len(df_all[df_all["Signal"] == "🟢 STRONG BUY"])
        n_buy   = len(df_all[df_all["Signal"] == "🟡 BUY"])
        n_ssell = len(df_all[df_all["Signal"] == "🔴 STRONG SELL"])
        n_sell  = len(df_all[df_all["Signal"] == "🟠 SELL"])
        n_wait  = len(df_all[df_all["Signal"] == "⚪ WAIT"])

        # Update placeholders (IN-PLACE — no reload)
        now_str = datetime.now().strftime("%H:%M:%S")

        with summary_placeholder.container():
            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("🟢 Strong Buy",  n_sbuy)
            c2.metric("🟡 Buy",         n_buy)
            c3.metric("🔴 Strong Sell", n_ssell)
            c4.metric("🟠 Sell",        n_sell)
            c5.metric("⚪ Wait",        n_wait)

        with table_placeholder.container():
            st.dataframe(styled, use_container_width=True, height=min(80 + len(df_show) * 38, 520))

        with status_placeholder.container():
            elapsed = time.time() - scan_start
            st.caption(f"🕐 Last scan: **{now_str}** | Cycle #{cycle} | Scan time: {elapsed:.1f}s | Next refresh: {refresh_sec}s | Stocks: {len(stocks)}")

    else:
        table_placeholder.error("⚠️ Koi data nahi mila. Internet check karo.")

    # Wait for next cycle — NO st.rerun(), NO page reload
    time.sleep(refresh_sec)
