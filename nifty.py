import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
import time
import requests

# ==========================================
# PAGE CONFIG
# ==========================================
st.set_page_config(page_title="⚡ Intraday Screener", layout="wide", page_icon="⚡")

st.markdown("""
<style>
html, body, [data-testid="stAppViewContainer"] { background-color: #0a0a0a !important; color: #e0e0e0; }
[data-testid="stSidebar"] { background-color: #0f0f0f !important; }
.block-container { padding-top: 1rem; }
.live-badge {
    display: inline-block; background: #00e676; color: #000;
    font-size: 11px; font-weight: bold; padding: 2px 10px;
    border-radius: 20px; animation: pulse 1.5s infinite; margin-left: 10px;
}
@keyframes pulse { 0%{opacity:1} 50%{opacity:0.3} 100%{opacity:1} }
.header-title { font-size:24px; font-weight:800; letter-spacing:2px; color:#fff; font-family:'Courier New',monospace; }
textarea { background:#1a1a1a !important; color:#e0e0e0 !important; font-family:'Courier New',monospace !important; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# SESSION STATE INIT
# ==========================================
if "auth"         not in st.session_state: st.session_state["auth"]         = False
if "sent_alerts"  not in st.session_state: st.session_state["sent_alerts"]  = {}

# ==========================================
# PASSWORD WALL
# ==========================================
if not st.session_state["auth"]:
    st.markdown("""
    <div style='text-align:center;padding:80px 0 20px 0;'>
        <div style='font-size:52px;'>🔒</div>
        <div style='font-size:22px;font-weight:bold;font-family:Courier New;color:#fff;margin:16px 0 8px 0;'>AUTHORIZED ACCESS ONLY</div>
        <div style='font-size:12px;color:#444;font-family:Courier New;letter-spacing:3px;'>INTRADAY CONFLUENCE SCREENER - NSE</div>
    </div>
    """, unsafe_allow_html=True)
    _, col, _ = st.columns([1, 2, 1])
    with col:
        pwd = st.text_input("", placeholder="🔑 Password enter karo...", type="password", label_visibility="collapsed")
        if st.button("LOGIN >>", use_container_width=True):
            try:
                correct = st.secrets["MY_APP_PASSWORD"]
            except Exception:
                correct = "admin123"
            if pwd == correct:
                st.session_state["auth"] = True
                st.rerun()
            else:
                st.error("❌ Wrong password!")
    st.stop()

# ==========================================
# TELEGRAM FUNCTION
# ==========================================
def send_telegram(msg):
    try:
        token   = st.secrets["TELEGRAM_BOT_TOKEN"]
        chat_id = st.secrets["TELEGRAM_CHAT_ID"]
        url     = f"https://api.telegram.org/bot{token}/sendMessage"
        requests.post(url, data={"chat_id": chat_id, "text": msg, "parse_mode": "HTML"}, timeout=5)
    except Exception:
        pass  # Telegram fail hone pe app crash nahi karega

def maybe_alert(ticker, sig, price, atr):
    """15 min mein ek baar hi same stock ka alert bhejo"""
    if sig not in ("🟢 STRONG BUY", "🔴 STRONG SELL"):
        return
    alert_key    = f"{ticker}_{sig}"
    last_alert   = st.session_state["sent_alerts"].get(alert_key)
    current_time = time.time()
    if last_alert and (current_time - last_alert < 900):   # 15 min cooldown
        return

    sl_buy     = round(price - 1.5 * atr, 2)
    sl_sell    = round(price + 1.5 * atr, 2)
    buy_target = round(price + 3.0 * atr, 2)
    sel_target = round(price - 3.0 * atr, 2)
    confidence = 85 if sig == "🟢 STRONG BUY" else 82

    if sig == "🟢 STRONG BUY":
        msg = (
            f"🟢 <b>STRONG BUY</b>\n\n"
            f"<b>{ticker}</b>\n\n"
            f"Price:      ₹{price:.2f}\n"
            f"SL:         ₹{sl_buy:.2f}\n"
            f"Target:     ₹{buy_target:.2f}\n"
            f"Confidence: {confidence}%"
        )
    else:
        msg = (
            f"🔴 <b>STRONG SELL</b>\n\n"
            f"<b>{ticker}</b>\n\n"
            f"Price:      ₹{price:.2f}\n"
            f"SL:         ₹{sl_sell:.2f}\n"
            f"Target:     ₹{sel_target:.2f}\n"
            f"Confidence: {confidence}%"
        )
    send_telegram(msg)
    st.session_state["sent_alerts"][alert_key] = current_time

# ==========================================
# INDICATOR FUNCTIONS
# ==========================================
def ema(s, p):
    return s.ewm(span=p, adjust=False).mean()

def calc_rsi(s, n=14):
    """Wilder smoothing RSI - accurate version"""
    delta    = s.diff()
    gain     = delta.clip(lower=0)
    loss     = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/n, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/n, adjust=False).mean()
    rs       = avg_gain / (avg_loss + 1e-10)
    return 100 - (100 / (1 + rs))

def macd_hist(s):
    ml = ema(s, 12) - ema(s, 26)
    return ml - ema(ml, 9)

def vwap(df):
    tp = (df['High'] + df['Low'] + df['Close']) / 3
    return (tp * df['Volume']).cumsum() / df['Volume'].cumsum()

def calc_atr(df, p=14):
    tr = pd.concat([
        df['High'] - df['Low'],
        (df['High'] - df['Close'].shift()).abs(),
        (df['Low']  - df['Close'].shift()).abs()
    ], axis=1).max(axis=1)
    return tr.rolling(p).mean()

def supertrend(df, p=10, m=3):
    hl2 = (df['High'] + df['Low']) / 2
    atr = calc_atr(df, p)
    up  = hl2 + m * atr
    dn  = hl2 - m * atr
    d   = pd.Series(0, index=df.index)
    for i in range(1, len(df)):
        if   df['Close'].iloc[i] > up.iloc[i-1]: d.iloc[i] =  1
        elif df['Close'].iloc[i] < dn.iloc[i-1]: d.iloc[i] = -1
        else: d.iloc[i] = d.iloc[i-1]
    return d

def structure(close):
    v = close.tail(30).values
    H, L = [], []
    for i in range(1, len(v)-1):
        if v[i] > v[i-1] and v[i] > v[i+1]: H.append(v[i])
        if v[i] < v[i-1] and v[i] < v[i+1]: L.append(v[i])
    if len(H) >= 2 and len(L) >= 2:
        if H[-1] > H[-2] and L[-1] > L[-2]: return "HH+HL 🟢"
        if H[-1] < H[-2] and L[-1] < L[-2]: return "LH+LL 🔴"
    return "Choppy ⚪"

def fib_zone(df, price):
    hi = float(df['High'].max())
    lo = float(df['Low'].min())
    d  = max(hi - lo, 1)
    levels = {"0%": hi, "23.6%": hi-0.236*d, "38.2%": hi-0.382*d,
              "50%": hi-0.5*d, "61.8%🎯": hi-0.618*d, "100%": lo}
    k = min(levels, key=lambda x: abs(levels[x] - price))
    return f"{k} ₹{levels[k]:.1f}"

def fmtvol(v):
    if v >= 1e6: return f"{v/1e6:.1f}M"
    if v >= 1e3: return f"{v/1e3:.1f}K"
    return str(int(v))

# ==========================================
# NEW FUNCTIONS
# ==========================================

def higher_tf_trend(symbol):
    """15-min chart pe EMA20/50 se higher timeframe bias"""
    try:
        df_htf = yf.download(symbol + ".NS", period="10d", interval="15m",
                             progress=False, auto_adjust=True)
        if isinstance(df_htf.columns, pd.MultiIndex):
            df_htf.columns = df_htf.columns.get_level_values(0)
        df_htf = df_htf.dropna()
        close  = df_htf["Close"].squeeze()
        e20    = float(ema(close, 20).iloc[-1])
        e50    = float(ema(close, 50).iloc[-1])
        price  = float(close.iloc[-1])
        if price > e20 > e50:   return "🟢 HTF Bull"
        elif price < e20 < e50: return "🔴 HTF Bear"
        return "⚪ Mixed"
    except Exception:
        return "⚪ Unknown"

def sideways_market(df):
    """ATR/Price < 0.3% = choppy/sideways market"""
    try:
        atr_val   = float(calc_atr(df).iloc[-1])
        price_val = float(df["Close"].iloc[-1])
        return (atr_val / price_val) < 0.003
    except Exception:
        return False

def relative_strength(stock_close, nifty_close):
    """Stock return vs Nifty return - last 10 candles"""
    try:
        sc = stock_close.squeeze()
        nc = nifty_close.squeeze()
        # align lengths
        min_len = min(len(sc), len(nc), 10)
        if min_len < 2:
            return "⚪ Neutral"
        sr = float(sc.iloc[-1]) / float(sc.iloc[-min_len])
        nr = float(nc.iloc[-1]) / float(nc.iloc[-min_len])
        rs = sr / (nr + 1e-10)
        if rs > 1.02:   return "🟢 Strong"
        elif rs < 0.98: return "🔴 Weak"
        return "⚪ Neutral"
    except Exception:
        return "⚪ Neutral"

def opening_range_breakout(df):
    """First 3 candles ka high/low = ORB zone"""
    try:
        first_3  = df.head(3)
        orb_high = float(first_3["High"].max())
        orb_low  = float(first_3["Low"].min())
        current  = float(df["Close"].iloc[-1])
        if current > orb_high:  return "🟢 ORB Breakout"
        elif current < orb_low: return "🔴 ORB Breakdown"
        return "⚪ Inside Range"
    except Exception:
        return "⚪ Unknown"

# ==========================================
# FETCH & ANALYZE
# ==========================================
@st.cache_data(ttl=30)
def fetch_nifty(interval):
    """Nifty index download - cached separately"""
    try:
        df = yf.download("^NSEI", period="5d", interval=interval,
                         progress=False, auto_adjust=True)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return df.dropna()
    except Exception:
        return pd.DataFrame()

def analyze(sym, interval, nifty_df):
    ticker = sym.strip().upper()
    ns     = ticker + ".NS"
    try:
        df = yf.download(ns, period="2d", interval=interval,
                         progress=False, auto_adjust=True)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df.dropna()

        if len(df) < 20:
            return None

        cl  = df['Close'].squeeze()
        vo  = df['Volume'].squeeze()

        px   = float(cl.iloc[-1])
        e9   = float(ema(cl, 9).iloc[-1])
        rv   = float(calc_rsi(cl).iloc[-1])
        mh   = float(macd_hist(cl).iloc[-1])
        mhp  = float(macd_hist(cl).iloc[-2])
        vw   = float(vwap(df).iloc[-1])
        st   = int(supertrend(df).iloc[-1])
        vnow = float(vo.iloc[-1])
        vavg = float(vo.rolling(20).mean().iloc[-1])
        atr_val = float(calc_atr(df).iloc[-1])

        # PDH / PDL
        today = df.index[-1].date()
        prev  = df[pd.to_datetime(df.index).date < today]
        pdh   = float(prev['High'].max()) if not prev.empty else float(df['High'].max())
        pdl   = float(prev['Low'].min())  if not prev.empty else float(df['Low'].min())

        # New features
        htf     = higher_tf_trend(ticker)
        is_side = sideways_market(df)
        rs      = relative_strength(cl, nifty_df["Close"]) if not nifty_df.empty else "⚪ Neutral"
        orb     = opening_range_breakout(df)
        struct_s = structure(cl)
        fib_s   = fib_zone(df, px)

        # Format strings
        ema_s  = f"🟢 {e9:.1f}"   if px > e9 else f"🔴 {e9:.1f}"
        vwap_s = f"🟢 {vw:.1f}"   if px > vw else f"🔴 {vw:.1f}"
        rsi_s  = f"{rv:.1f}{'⚠️OB' if rv>70 else ('⚠️OS' if rv<30 else '')}"
        macd_s = ("🟢 Rising"  if mh > 0 and mh > mhp else
                  ("🔴 Falling" if mh < 0 and mh < mhp else "⚪ Flat"))
        vol_s  = f"🚀 SURGE {fmtvol(vnow)}" if vnow > 1.8*vavg else f"Normal {fmtvol(vnow)}"
        st_s   = "🟢 Bull" if st == 1 else ("🔴 Bear" if st == -1 else "⚪")
        pdh_s  = "🟢 AbovePDH" if px > pdh else "🔴 BelowPDH"

        row = {
            "Stock":  ticker,
            "Price":  f"₹{px:.2f}",
            "EMA9":   ema_s,
            "VWAP":   vwap_s,
            "RSI":    rsi_s,
            "MACD":   macd_s,
            "Volume": vol_s,
            "ST":     st_s,
            "PDH":    pdh_s,
            "Struct": struct_s,
            "HTF":    htf,
            "RS":     rs,
            "ORB":    orb,
            "Fib":    fib_s,
        }

        # SCORING
        b = be = 0
        if "🟢" in ema_s:  b  += 1
        else:               be += 1
        if "🟢" in vwap_s: b  += 1
        else:               be += 1
        try:
            r = float(rsi_s.split()[0])
            if 50 <= r <= 65: b  += 1
            elif 35 <= r < 50: be += 1
        except: pass
        if "🟢" in macd_s:  b  += 1
        elif "🔴" in macd_s: be += 1
        if "SURGE" in vol_s: b  += 1; be += 1
        if "HH"   in struct_s: b  += 1
        elif "LH" in struct_s: be += 1
        if "🟢"   in st_s:  b  += 1
        elif "🔴" in st_s:  be += 1
        if "🟢"   in pdh_s: b  += 1
        else:                be += 1
        # HTF - double weight
        if "HTF Bull" in htf: b  += 2
        elif "HTF Bear" in htf: be += 2
        # RS
        if "Strong" in rs:   b  += 1
        elif "Weak" in rs:   be += 1
        # ORB
        if "Breakout"  in orb: b  += 1
        elif "Breakdown" in orb: be += 1

        row["✅Bull"] = b
        row["🔴Bear"] = be

        # Sideways override
        if is_side:
            sig = "⚪ SIDEWAYS"
        else:
            sc = b - be
            if sc >= 6:    sig = "🟢 STRONG BUY"
            elif sc >= 3:  sig = "🟡 BUY"
            elif sc <= -6: sig = "🔴 STRONG SELL"
            elif sc <= -3: sig = "🟠 SELL"
            else:          sig = "⚪ WAIT"

        row["Signal"] = sig

        # Telegram alert
        maybe_alert(ticker, sig, px, atr_val)

        return row

    except Exception:
        return {
            "Stock": ticker, "Price": "Error", "EMA9": "-", "VWAP": "-",
            "RSI": "-", "MACD": "-", "Volume": "-", "ST": "-", "PDH": "-",
            "Struct": "-", "HTF": "-", "RS": "-", "ORB": "-", "Fib": "-",
            "✅Bull": 0, "🔴Bear": 0, "Signal": "❓ ERR"
        }

# ==========================================
# SIDEBAR
# ==========================================
with st.sidebar:
    st.markdown("### ⚙️ Settings")
    st.markdown("**📝 Stock Names (NSE Symbol, ek line = ek stock):**")
    stock_input = st.text_area(
        "", height=250, label_visibility="collapsed",
        value="RELIANCE\nHDFCBANK\nTCS\nINFY\nSBIN\nICICIBANK\nAXISBANK\nTATAMOTORS\nITC\nLT"
    )
    interval = st.selectbox("⏱️ Timeframe:", ["1m", "5m", "15m", "1h"], index=2)
    refresh  = st.selectbox("🔄 Refresh:", [10, 15, 30, 60], index=1,
                            format_func=lambda x: f"{x} sec")
    st.markdown("---")
    show_f = st.selectbox("👁️ Filter:", ["All", "BUY Only", "SELL Only", "Strong Only"])
    tg_on  = st.toggle("📲 Telegram Alerts", value=True)
    st.markdown("---")
    if st.button("🔓 Logout"):
        st.session_state["auth"] = False
        st.rerun()

stocks = list(dict.fromkeys(
    [s.strip().upper() for s in stock_input.splitlines() if s.strip()]
))[:15]

# ==========================================
# HEADER
# ==========================================
st.markdown("""
<div style='margin-bottom:4px;'>
  <span class='header-title'>⚡ INTRADAY CONFLUENCE SCREENER</span>
  <span class='live-badge'>● LIVE</span>
</div>
<div style='font-size:11px;color:#444;font-family:Courier New;letter-spacing:2px;margin-bottom:12px;'>
  NSE | AUTO REFRESH | TELEGRAM ALERTS | HTF + RS + ORB
</div>
""", unsafe_allow_html=True)

if not stocks:
    st.warning("⬅️ Sidebar mein stock names likho")
    st.stop()

summary_ph = st.empty()
table_ph   = st.empty()
status_ph  = st.empty()

with st.expander("📘 Strategy + Scoring Guide"):
    st.markdown("""
| Indicator | BUY (+) | SELL (-) | Weight |
|-----------|---------|----------|--------|
| EMA 9 | 🟢 Above | 🔴 Below | 1 |
| VWAP | 🟢 Above | 🔴 Below | 1 |
| RSI | 50-65 | 35-50 | 1 |
| MACD | 🟢 Rising | 🔴 Falling | 1 |
| Volume | 🚀 SURGE | 🚀 SURGE | 1 |
| Supertrend | 🟢 Bull | 🔴 Bear | 1 |
| PDH | 🟢 Above | 🔴 Below | 1 |
| Structure | HH+HL | LH+LL | 1 |
| **HTF Trend** | 🟢 HTF Bull | 🔴 HTF Bear | **2** |
| **Rel. Strength** | 🟢 Strong | 🔴 Weak | 1 |
| **ORB** | 🟢 Breakout | 🔴 Breakdown | 1 |

**Score ≥ +6 = STRONG BUY | Score ≤ -6 = STRONG SELL**
**⚪ SIDEWAYS = ATR volatility < 0.3% - trade mat karo**
**📲 Telegram = STRONG signal pe alert, 15 min cooldown**
    """)

st.caption("⚠️ yfinance free feed - delay possible. Sirf analysis tool hai.")

# ==========================================
# LIVE LOOP
# ==========================================
cycle = 0
while True:
    cycle += 1
    t0 = time.time()

    # Nifty download once per cycle
    nifty_df = fetch_nifty(interval)

    results = []
    for sym in stocks:
        r = analyze(sym, interval, nifty_df)
        if r:
            results.append(r)

    if results:
        df_all  = pd.DataFrame(results)
        df_show = df_all.copy()

        if show_f == "BUY Only":
            df_show = df_show[df_show["Signal"].str.contains("BUY",  na=False)]
        elif show_f == "SELL Only":
            df_show = df_show[df_show["Signal"].str.contains("SELL", na=False)]
        elif show_f == "Strong Only":
            df_show = df_show[df_show["Signal"].str.contains("STRONG", na=False)]

        # ── Styling - .map() only (pandas 2.1+ safe) ──
        def sc_sig(val):
            v = str(val)
            if "STRONG BUY"  in v: return "background:#0d2e0d;color:#00e676;font-weight:bold"
            if "BUY"         in v: return "background:#0a200a;color:#69f0ae"
            if "STRONG SELL" in v: return "background:#2e0d0d;color:#ff1744;font-weight:bold"
            if "SELL"        in v: return "background:#200a0a;color:#ff6d00"
            if "SIDEWAYS"    in v: return "background:#1a1a00;color:#ffd740"
            return "color:#555"

        def sc_cell(val):
            v = str(val)
            if "🟢" in v: return "color:#00e676"
            if "🔴" in v: return "color:#ff5252"
            if "⚠️" in v: return "color:#ffd740"
            if "🚀" in v: return "color:#40c4ff"
            return "color:#bbb"

        cc = [c for c in ["EMA9","VWAP","MACD","ST","PDH","Volume","Struct","HTF","RS","ORB"]
              if c in df_show.columns]

        styler = (
            df_show.style
            .map(sc_sig,  subset=["Signal"])
            .map(sc_cell, subset=cc)
            .set_properties(**{"font-size": "12px", "font-family": "Courier New"})
            .hide(axis="index")
        )

        # Counts
        sb = (df_all["Signal"] == "🟢 STRONG BUY").sum()
        b  = (df_all["Signal"] == "🟡 BUY").sum()
        ss = (df_all["Signal"] == "🔴 STRONG SELL").sum()
        sl = (df_all["Signal"] == "🟠 SELL").sum()
        sw = (df_all["Signal"] == "⚪ SIDEWAYS").sum()
        w  = (df_all["Signal"] == "⚪ WAIT").sum()

        now     = datetime.now().strftime("%H:%M:%S")
        elapsed = time.time() - t0

        with summary_ph.container():
            c1, c2, c3, c4, c5, c6 = st.columns(6)
            c1.metric("🟢 Strong Buy",  sb)
            c2.metric("🟡 Buy",         b)
            c3.metric("🔴 Strong Sell", ss)
            c4.metric("🟠 Sell",        sl)
            c5.metric("⚪ Sideways",    sw)
            c6.metric("⚪ Wait",        w)

        with table_ph.container():
            st.dataframe(styler, use_container_width=True,
                         height=min(80 + len(df_show) * 38, 560))

        with status_ph.container():
            tg_status = "📲 ON" if tg_on else "📵 OFF"
            st.caption(
                f"🕐 **{now}** | Cycle #{cycle} | "
                f"Fetch: {elapsed:.1f}s | Next: {refresh}s | "
                f"Stocks: {len(stocks)} | Telegram: {tg_status}"
            )
    else:
        table_ph.error("⚠️ Data nahi mila. Internet ya stock names check karo.")

    time.sleep(refresh)
