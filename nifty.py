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

st.markdown("""
<style>
    html, body, [data-testid="stAppViewContainer"] {
        background-color: #0a0a0a !important;
        color: #e0e0e0;
    }
    [data-testid="stSidebar"] { background-color: #0f0f0f !important; }
    .block-container { padding-top: 1rem; }
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
        50%  { opacity: 0.3; }
        100% { opacity: 1; }
    }
    .stTextArea textarea {
        background: #141414 !important;
        color: #e0e0e0 !important;
        border: 1px solid #2a2a2a !important;
        font-family: 'Courier New', monospace !important;
        font-size: 14px !important;
    }
    .stButton > button {
        background: #141414;
        color: #00e676;
        border: 1px solid #00e676;
        border-radius: 6px;
        font-family: 'Courier New', monospace;
        font-weight: bold;
    }
    .stButton > button:hover { background:#00e676; color:#000; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 🔒 PASSWORD WALL
# ==========================================
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False

if not st.session_state["authenticated"]:
    st.markdown("""
    <div style='text-align:center; padding:80px 0 30px 0;'>
        <div style='font-size:52px;'>🔒</div>
        <div style='font-size:22px; font-weight:bold; color:#fff;
                    font-family:Courier New; letter-spacing:3px; margin:16px 0 6px;'>
            AUTHORIZED ACCESS ONLY
        </div>
        <div style='font-size:11px; color:#444; font-family:Courier New; letter-spacing:3px;'>
            INTRADAY CONFLUENCE SCREENER — NSE
        </div>
    </div>
    """, unsafe_allow_html=True)

    _, col, _ = st.columns([1, 2, 1])
    with col:
        pwd = st.text_input("", placeholder="🔑 Password enter karo...",
                            type="password", label_visibility="collapsed")
        if st.button("LOGIN →", use_container_width=True):
            try:
                correct = st.secrets["MY_APP_PASSWORD"]
            except Exception:
                correct = "admin123"   # local testing fallback

            if pwd == correct:
                st.session_state["authenticated"] = True
                st.rerun()
            else:
                st.error("❌ Wrong password!")
    st.stop()

# ==========================================
# PURE PYTHON INDICATORS (no ta-lib)
# ==========================================

def ema(s, n):
    return s.ewm(span=n, adjust=False).mean()

def calc_rsi(s, n=14):
    d = s.diff()
    g = d.clip(lower=0).rolling(n).mean()
    l = (-d.clip(upper=0)).rolling(n).mean()
    return 100 - 100 / (1 + g / (l + 1e-10))

def calc_macd_hist(s):
    h = ema(s, 12) - ema(s, 26)
    return h - ema(h, 9)

def calc_vwap(df):
    tp = (df["High"] + df["Low"] + df["Close"]) / 3
    return (tp * df["Volume"]).cumsum() / df["Volume"].cumsum()

def calc_supertrend(df, period=10, mult=3):
    hl2 = (df["High"] + df["Low"]) / 2
    tr = pd.concat([
        df["High"] - df["Low"],
        (df["High"] - df["Close"].shift(1)).abs(),
        (df["Low"]  - df["Close"].shift(1)).abs()
    ], axis=1).max(axis=1)
    atr   = tr.rolling(period).mean()
    upper = hl2 + mult * atr
    lower = hl2 - mult * atr
    dirn  = pd.Series(0, index=df.index)
    for i in range(1, len(df)):
        if   df["Close"].iloc[i] > upper.iloc[i-1]: dirn.iloc[i] =  1
        elif df["Close"].iloc[i] < lower.iloc[i-1]: dirn.iloc[i] = -1
        else: dirn.iloc[i] = dirn.iloc[i-1]
    return dirn

def calc_fib(df):
    hi   = float(df["High"].max())
    lo   = float(df["Low"].min())
    diff = max(hi - lo, 1)
    return {
        "0%(Hi)":  round(hi, 2),
        "23.6%":   round(hi - 0.236*diff, 2),
        "38.2%":   round(hi - 0.382*diff, 2),
        "50.0%":   round(hi - 0.500*diff, 2),
        "61.8%🎯": round(hi - 0.618*diff, 2),
        "100%(Lo)":round(lo, 2),
    }

def nearest_fib(price, fibs):
    k = min(fibs, key=lambda x: abs(fibs[x] - price))
    return f"{k}=₹{fibs[k]}"

def mkt_struct(close):
    v = close.tail(30).values
    hi, lo = [], []
    for i in range(1, len(v)-1):
        if v[i] > v[i-1] and v[i] > v[i+1]: hi.append(v[i])
        if v[i] < v[i-1] and v[i] < v[i+1]: lo.append(v[i])
    if len(hi)>=2 and len(lo)>=2:
        if hi[-1]>hi[-2] and lo[-1]>lo[-2]: return "HH+HL 🟢"
        if hi[-1]<hi[-2] and lo[-1]<lo[-2]: return "LH+LL 🔴"
    return "Choppy ⚪"

def fmt_vol(v):
    if v >= 1e6: return f"{v/1e6:.1f}M"
    if v >= 1e3: return f"{v/1e3:.1f}K"
    return str(int(v))

# ==========================================
# SCORING
# ==========================================

def score_row(row):
    b = be = 0
    if "🟢" in str(row.get("EMA","")): b  += 1
    else: be += 1
    if "🟢" in str(row.get("VWAP","")): b  += 1
    else: be += 1
    try:
        r = float(str(row.get("RSI","50")).split()[0])
        if 50<=r<=65: b  += 1
        elif 35<=r<50: be += 1
    except: pass
    if "🟢" in str(row.get("MACD","")): b  += 1
    elif "🔴" in str(row.get("MACD","")): be += 1
    if "SURGE" in str(row.get("Vol","")): b += 1; be += 1
    if "HH"   in str(row.get("Struct","")): b  += 1
    elif "LH" in str(row.get("Struct","")): be += 1
    if "🟢"   in str(row.get("ST","")): b  += 1
    elif "🔴" in str(row.get("ST","")): be += 1

    sc = b - be
    if sc >=  4: sig = "🟢 STRONG BUY"
    elif sc >= 2: sig = "🟡 BUY"
    elif sc <= -4: sig = "🔴 STRONG SELL"
    elif sc <= -2: sig = "🟠 SELL"
    else: sig = "⚪ WAIT"
    return b, be, sig

# ==========================================
# FETCH ONE STOCK
# ==========================================

def fetch(symbol, interval):
    ticker = symbol.strip().upper()
    yf_sym = ticker + ".NS"
    try:
        df = yf.download(yf_sym, period="2d", interval=interval,
                         progress=False, auto_adjust=True)
        # Fix MultiIndex
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df.dropna()
        if len(df) < 20:
            return None

        cl = df["Close"].squeeze()
        vo = df["Volume"].squeeze()

        price    = float(cl.iloc[-1])
        e9       = float(ema(cl, 9).iloc[-1])
        e21      = float(ema(cl,21).iloc[-1])
        rsi_v    = float(calc_rsi(cl).iloc[-1])
        mh       = float(calc_macd_hist(cl).iloc[-1])
        mh_p     = float(calc_macd_hist(cl).iloc[-2])
        vwap_v   = float(calc_vwap(df).iloc[-1])
        st_v     = int(calc_supertrend(df).iloc[-1])
        vol_now  = float(vo.iloc[-1])
        vol_avg  = float(vo.rolling(20).mean().iloc[-1])

        today = df.index[-1].date()
        prev  = df[pd.to_datetime(df.index).date < today]
        pdh   = float(prev["High"].max()) if not prev.empty else float(df["High"].max())

        fibs     = calc_fib(df)
        fib_zone = nearest_fib(price, fibs)
        struct   = mkt_struct(cl)

        rsi_tag = " ⚠️OB" if rsi_v > 70 else (" ⚠️OS" if rsi_v < 30 else "")

        row = {
            "Stock":  ticker,
            "Price":  f"₹{price:.2f}",
            "EMA":    f"🟢 ₹{e9:.1f}" if price > e9 else f"🔴 ₹{e9:.1f}",
            "VWAP":   f"🟢 ₹{vwap_v:.1f}" if price > vwap_v else f"🔴 ₹{vwap_v:.1f}",
            "RSI":    f"{rsi_v:.1f}{rsi_tag}",
            "MACD":   "🟢 +Rising"  if (mh > 0 and mh > mh_p) else
                      ("🔴 -Falling" if (mh < 0 and mh < mh_p) else "⚪ Flat"),
            "Vol":    f"🚀 SURGE {fmt_vol(vol_now)}" if vol_now > 1.8*vol_avg
                      else f"Normal {fmt_vol(vol_now)}",
            "ST":     "🟢 Bull" if st_v==1 else ("🔴 Bear" if st_v==-1 else "⚪"),
            "PDH":    "🟢 Above" if price > pdh else "🔴 Below",
            "Struct": struct,
            "Fib":    fib_zone,
        }
        b, be, sig = score_row(row)
        row["✅B"] = b
        row["🔴S"] = be
        row["Signal"] = sig
        return row

    except Exception:
        return {
            "Stock": symbol.upper(), "Price": "⚠️ Error",
            "EMA":"—","VWAP":"—","RSI":"—","MACD":"—","Vol":"—",
            "ST":"—","PDH":"—","Struct":"—","Fib":"—",
            "✅B":0,"🔴S":0,"Signal":"❓ N/A"
        }

# ==========================================
# SAFE STYLE FUNCTION — works on ALL pandas versions
# ==========================================

def style_df(df_in):
    """Returns HTML table string — no .applymap/.map needed"""
    def cell_color(col, val):
        s = str(val)
        if col == "Signal":
            if "STRONG BUY"  in s: return "background:#0d2e0d;color:#00e676;font-weight:bold"
            if "BUY"         in s: return "background:#0a1f0a;color:#69f0ae"
            if "STRONG SELL" in s: return "background:#2e0d0d;color:#ff1744;font-weight:bold"
            if "SELL"        in s: return "background:#1f0a0a;color:#ff6d00"
            return "color:#666"
        if col in ["EMA","VWAP","MACD","ST","PDH","Vol","Struct"]:
            if "🟢" in s: return "color:#00e676"
            if "🔴" in s: return "color:#ff5252"
            if "⚠️" in s: return "color:#ffd740"
            if "🚀" in s: return "color:#40c4ff"
        return "color:#ccc"

    rows_html = ""
    for _, row in df_in.iterrows():
        cells = ""
        for col in df_in.columns:
            style = cell_color(col, row[col])
            cells += f"<td style='padding:6px 10px;border-bottom:1px solid #1a1a1a;font-family:Courier New;font-size:12px;{style}'>{row[col]}</td>"
        rows_html += f"<tr>{cells}</tr>"

    headers = "".join(
        f"<th style='padding:8px 10px;text-align:left;background:#111;color:#888;"
        f"font-family:Courier New;font-size:11px;letter-spacing:1px;"
        f"border-bottom:2px solid #222;'>{c}</th>"
        for c in df_in.columns
    )

    return f"""
    <div style='overflow-x:auto;'>
    <table style='width:100%;border-collapse:collapse;background:#0a0a0a;'>
        <thead><tr>{headers}</tr></thead>
        <tbody>{rows_html}</tbody>
    </table>
    </div>
    """

# ==========================================
# SIDEBAR
# ==========================================
with st.sidebar:
    st.markdown("### ⚙️ Control Panel")

    st.markdown("**📝 Stocks likho (NSE symbol, ek line mein ek):**")
    default_txt = "RELIANCE\nHDFCBANK\nTCS\nINFY\nSBIN\nICICIBANK\nAXISBANK\nTATAMOTORS\nITC\nLT"
    stock_input = st.text_area("", value=default_txt, height=230,
                               label_visibility="collapsed",
                               help="Koi bhi NSE stock likho — .NS mat likho")

    interval = st.selectbox("⏱️ Timeframe:", ["1m","5m","15m","1h"], index=2)

    refresh_sec = st.selectbox("🔄 Refresh interval:",
                               [10, 15, 30, 60], index=1,
                               format_func=lambda x: f"Har {x} seconds")

    st.markdown("---")
    show_filter = st.selectbox("👁️ Filter:",
                               ["All","BUY Only","SELL Only","Strong Only"])
    min_bull = st.slider("Min Bull Score:", 0, 7, 0)

    st.markdown("---")
    if st.button("🔓 Logout"):
        st.session_state["authenticated"] = False
        st.rerun()

# Parse stocks list
stocks = []
for s in stock_input.strip().splitlines():
    s = s.strip().upper()
    if s and s not in stocks:
        stocks.append(s)
stocks = stocks[:15]   # max 15

# ==========================================
# MAIN HEADER
# ==========================================
st.markdown("""
<div style='margin-bottom:6px;'>
  <span style='font-size:24px;font-weight:900;font-family:Courier New;
               color:#fff;letter-spacing:2px;'>
    ⚡ INTRADAY CONFLUENCE SCREENER
  </span>
  <span class='live-badge'>● LIVE</span>
</div>
<div style='font-size:11px;color:#444;font-family:Courier New;
            letter-spacing:3px;margin-bottom:18px;'>
  NSE REAL-TIME MARKET SCANNER
</div>
""", unsafe_allow_html=True)

if not stocks:
    st.warning("⬅️ Sidebar mein stocks likho")
    st.stop()

# Placeholders — sirf inhe update karo, page reload NAHI hoga
ph_metrics = st.empty()
ph_table   = st.empty()
ph_status  = st.empty()

# Static sections
with st.expander("📘 Strategy Guide — Kab Entry Leni Hai"):
    st.markdown("""
| Check | BULLISH ✅ | BEARISH 🔴 |
|-------|-----------|-----------|
| EMA 9 | Price > EMA | Price < EMA |
| VWAP | Price > VWAP | Price < VWAP |
| RSI | 50–65 zone | 35–50 zone |
| MACD | +ve Rising | -ve Falling |
| Volume | 🚀 SURGE (2x) | 🚀 SURGE (2x) |
| Supertrend | 🟢 Bull | 🔴 Bear |
| Structure | HH+HL | LH+LL |

**Rule:** Score 5+/7 pe hi trade lo. SL mandatory. Min RR 1:2.
    """)

st.markdown("---")
st.caption("⚠️ yfinance data 1–2 min delayed hota hai. Sirf analysis tool hai.")

# ==========================================
# ♾️ LIVE LOOP — Page reload NAHI hoga
# ==========================================
cycle = 0
while True:
    cycle += 1
    t0 = time.time()

    results = [r for s in stocks if (r := fetch(s, interval)) is not None]

    if results:
        df_all = pd.DataFrame(results)

        # Apply filter
        df_show = df_all.copy()
        if show_filter == "BUY Only":
            df_show = df_show[df_show["Signal"].str.contains("BUY", na=False)]
        elif show_filter == "SELL Only":
            df_show = df_show[df_show["Signal"].str.contains("SELL", na=False)]
        elif show_filter == "Strong Only":
            df_show = df_show[df_show["Signal"].str.contains("STRONG", na=False)]
        df_show = df_show[df_show["✅B"] >= min_bull].reset_index(drop=True)

        # Count signals
        n_sb  = (df_all["Signal"]=="🟢 STRONG BUY").sum()
        n_b   = (df_all["Signal"]=="🟡 BUY").sum()
        n_ss  = (df_all["Signal"]=="🔴 STRONG SELL").sum()
        n_s   = (df_all["Signal"]=="🟠 SELL").sum()
        n_w   = (df_all["Signal"]=="⚪ WAIT").sum()
        now_s = datetime.now().strftime("%H:%M:%S")
        elapsed = time.time() - t0

        # Update metrics
        with ph_metrics.container():
            c1,c2,c3,c4,c5,c6 = st.columns(6)
            c1.metric("🟢 Strong Buy",  n_sb)
            c2.metric("🟡 Buy",         n_b)
            c3.metric("🔴 Strong Sell", n_ss)
            c4.metric("🟠 Sell",        n_s)
            c5.metric("⚪ Wait",        n_w)
            c6.metric("📊 Total",       len(df_all))

        # Update table — pure HTML, no .applymap/.map
        with ph_table.container():
            if df_show.empty:
                st.info("Filter ke hisaab se koi stock match nahi kiya.")
            else:
                st.markdown(style_df(df_show), unsafe_allow_html=True)

        # Update status bar
        ph_status.caption(
            f"🕐 Last scan: **{now_s}** | "
            f"Cycle #{cycle} | "
            f"Scan time: {elapsed:.1f}s | "
            f"Next in: {refresh_sec}s | "
            f"Stocks: {len(stocks)}"
        )

    else:
        ph_table.error("⚠️ Data nahi mila. Internet ya stock symbol check karo.")

    # Wait — no rerun, no page reload
    time.sleep(refresh_sec)
