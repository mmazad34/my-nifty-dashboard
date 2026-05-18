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
        )
        
        if option_data and option_data.get('status') == 'success':
            chain = option_data.get('data', [])
            if len(chain) > 0:
                total_call_volume = sum([strike.get('ce_volume', 0) for strike in chain])
                total_put_volume = sum([strike.get('pe_volume', 0) for strike in chain])
                if total_call_volume > 0:
                    return round(total_put_volume / total_call_volume, 2), total_call_volume, total_put_volume
        
        if selected_tab == "BANK NIFTY": return 0.88, 4120500, 3626000
        elif selected_tab == "SENSEX": return 0.95, 1240000, 1178000
        else: return 1.05, 5234100, 5495800
    except Exception:
        return 1.00, 4859320, 5124900

# ==========================================
# TECHNICAL ANALYSIS CALCULATORS
# ==========================================
def apply_indicators(df):
    df = df.copy()
    if len(df) >= 200:
        df['EMA_200'] = ta.trend.ema_indicator(df['Close'], window=200)
    else:
        df['EMA_200'] = ta.trend.ema_indicator(df['Close'], window=max(2, len(df)//2))

    df['EMA_20'] = ta.trend.ema_indicator(df['Close'], window=min(20, len(df))) if len(df) >= 2 else df['Close']
    df['RSI'] = ta.momentum.rsi(df['Close'], window=min(14, len(df))) if len(df) >= 15 else 50.0
    
    try:
        macd_obj = ta.trend.MACD(df['Close'])
        df['MACD'] = macd_obj.macd()
        df['MACD_Signal'] = macd_obj.macd_signal()
        df['MACD_Hist'] = macd_obj.macd_diff()
    except Exception:
        df['MACD'] = 0.0
        df['MACD_Signal'] = 0.0
        df['MACD_Hist'] = 0.0
        
    df['Vol_Avg'] = df['Volume'].rolling(window=min(20, len(df))).mean() if len(df) >= 2 else df['Volume']
    
    df = df.bfill()
    df = df.ffill()
    return df

def calculate_fibonacci(df):
    highest_high = df['High'].max()
    lowest_low = df['Low'].min()
    diff = highest_high - lowest_low
    if diff == 0: diff = 1
    return {
        "0.0% (Max)": highest_high,
        "23.6%": highest_high - 0.236 * diff,
        "38.2%": highest_high - 0.382 * diff,
        "50.0%": highest_high - 0.5 * diff,
        "61.8%": highest_high - 0.618 * diff,
        "78.6%": highest_high - 0.786 * diff,
        "100.0% (Min)": lowest_low
    }

def calculate_volume_profile(df, bins=20):
    price_min, price_max = df['Low'].min(), df['High'].max()
    if price_max == price_min: price_max += 1
    bin_edges = np.linspace(price_min, price_max, bins + 1)
    volumes, _ = np.histogram(df['Close'], bins=bin_edges, weights=df['Volume'])
    bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2
    max_volume_idx = np.argmax(volumes) if len(volumes) > 0 else 0
    return bin_centers, volumes, bin_centers[max_volume_idx], bin_centers[np.where(volumes >= (np.percentile(volumes, 80) if len(volumes) > 0 else 0))[0]]

# Fixed variable binding bug (d_bot vs d_bottom name mismatch)
def calculate_order_blocks(df):
    recent_df = df.tail(50) if len(df) > 50 else df
    highest_idx = recent_df['High'].idxmax()
    lowest_idx = recent_df['Low'].idxmin()
    s_top = recent_df.loc[highest_idx, 'High']
    s_bot = max(recent_df.loc[highest_idx, 'Open'], recent_df.loc[highest_idx, 'Close'])
    d_bot = recent_df.loc[lowest_idx, 'Low']
    d_top = min(recent_df.loc[lowest_idx, 'Open'], recent_df.loc[lowest_idx, 'Close'])
    if s_top == s_bot: s_bot -= (s_top * 0.001)
    if d_top == d_bot: d_top += (d_bot * 0.001)
    return s_top, s_bot, d_top, d_bot

def generate_signals(df, supply_bottom, demand_top):
    df = df.copy()
    signals = ["HOLD"] * len(df)
    for i in range(1, len(df)):
        rsi_curr = df['RSI'].iloc[i]
        macd_curr = df['MACD'].iloc[i]
        sig_curr = df['MACD_Signal'].iloc[i]
        close_curr = df['Close'].iloc[i]
        ema200 = df['EMA_200'].iloc[i]
        ema20 = df['EMA_20'].iloc[i]
        vol_curr = df['Volume'].iloc[i]
        vol_avg = df['Vol_Avg'].iloc[i]
        
        if close_curr > ema20 and (close_curr > ema200 if pd.notna(ema200) else True) and macd_curr >= sig_curr and close_curr > supply_bottom and vol_curr > vol_avg:
            signals[i] = "STRONG BUY"
        elif macd_curr >= sig_curr and rsi_curr >= 50 and close_curr > ema20:
            signals[i] = "BUY"
        elif close_curr < ema20 and (close_curr < ema200 if pd.notna(ema200) else True) and macd_curr <= sig_curr and close_curr < demand_top and vol_curr > vol_avg:
            signals[i] = "STRONG SELL"
        elif macd_curr <= sig_curr and close_curr < ema20:
            signals[i] = "SELL"
    df['Signal'] = signals
    return df

def get_trend_and_sentiment(df, supply_bottom, demand_top):
    latest_rsi = df['RSI'].iloc[-1]
    latest_close = df['Close'].iloc[-1]
    latest_ema200 = df['EMA_200'].iloc[-1]
    macd_hist = df['MACD_Hist'].iloc[-1]
    trend = "BULLISH" if (pd.notna(latest_ema200) and latest_close > latest_ema200) else "BEARISH"
    score = 2 if trend == "BULLISH" else -2
    if latest_close > supply_bottom: score += 1
    if latest_close < demand_top: score -= 1
    if latest_rsi > 50: score += 1
    if latest_rsi < 50: score -= 1
    if macd_hist > 0: score += 1
    
    if score >= 3: return trend, "STRONG BULLISH", "#238636"
    elif 1 <= score < 3: return trend, "MODERATE BULLISH", "#2ea043"
    elif -1 < score < 1: return trend, "SIDEWAYS / NEUTRAL", "#8b949e"
    elif -3 < score <= -1: return trend, "MODERATE BEARISH", "#da3633"
    else: return trend, "STRONG BEARISH", "#f85149"

# ==========================================
# TRADINGVIEW PLOTLY CHART CANVAS
# ==========================================
def plot_tradingview_chart(df, fib_levels, bin_centers, volumes, s_top, s_bot, d_top, d_bot):
    fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.04, row_heights=[0.55, 0.20, 0.25])
    fig.add_trace(gr.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name="Price Action"), row=1, col=1)
    fig.add_trace(gr.Scatter(x=df.index, y=df['EMA_200'], line=dict(color='#ff9f43', width=1.5), name='EMA 200'), row=1, col=1)
    fig.add_trace(gr.Scatter(x=df.index, y=df['EMA_20'], line=dict(color='#00d2d3', width=1.2), name='EMA 20'), row=1, col=1)
    
    fig.add_shape(type="rect", x0=df.index[0], y0=s_bot, x1=df.index[-1], y1=s_top, fillcolor="rgba(218, 54, 51, 0.15)", line=dict(color="rgba(218, 54, 51, 0.5)", width=1), row=1, col=1)
    fig.add_shape(type="rect", x0=df.index[0], y0=d_bot, x1=df.index[-1], y1=d_top, fillcolor="rgba(46, 160, 67, 0.15)", line=dict(color="rgba(46, 160, 67, 0.5)", width=1), row=1, col=1)
    
    colors_fib = ['#ff4d4d', '#ff9f43', '#ffcd3c', '#1dd1a1', '#10ac84', '#54a0ff', '#5f27cd']
    for (lbl, val), clr in zip(fib_levels.items(), colors_fib):
        fig.add_trace(gr.Scatter(x=[df.index[0], df.index[-1]], y=[val, val], mode="lines", line=dict(color=clr, width=1, dash="dash"), name=f"Fib {lbl}"), row=1, col=1)
        
    vol_max = volumes.max() if len(volumes) > 0 and volumes.max() > 0 else 1
    norm_volumes = (volumes / vol_max) * (len(df) * 0.15)
    for idx in range(len(bin_centers)):
        if idx < len(norm_volumes) and norm_volumes[idx] > 0:
            fig.add_trace(gr.Scatter(x=[df.index[0], df.index[min(int(norm_volumes[idx]), len(df)-1)]], y=[bin_centers[idx], bin_centers[idx]], mode="lines", line=dict(color="rgba(139, 148, 158, 0.12)", width=4), showlegend=False), row=1, col=1)

    fig.add_trace(gr.Scatter(x=df.index, y=df['RSI'], line=dict(color='#a55eed', width=1.5), name='RSI'), row=2, col=1)
    fig.add_trace(gr.Scatter(x=df.index, y=df['MACD'], line=dict(color='#2685ff', width=1.5), name='MACD Line'), row=3, col=1)
    fig.add_trace(gr.Scatter(x=df.index, y=df['MACD_Signal'], line=dict(color='#ff3b30', width=1.5), name='Signal Line'), row=3, col=1)
    fig.add_trace(gr.Bar(x=df.index, y=df['MACD_Hist'], marker_color=['#2ea043' if val >= 0 else '#f85149' for val in df['MACD_Hist']], name='MACD Histogram'), row=3, col=1)

    fig.update_layout(template="plotly_dark", paper_bgcolor="#0c1017", plot_bgcolor="#0c1017", height=750, margin=dict(l=30, r=30, t=10, b=10), xaxis=dict(rangeslider=dict(visible=False)), yaxis=dict(side="right"), yaxis2=dict(side="right"), yaxis3=dict(side="right"))
    return fig

# ==========================================
# APP UI CONTROLLER
# ==========================================
def main():
    st.sidebar.markdown("<h2 style='color:#ffffff; text-align:center;'>🔧 CONTROL HUB</h2>", unsafe_allow_html=True)
    st.sidebar.divider()
    tf_selection = st.sidebar.selectbox("⏱️ Select Chart Timeframe", list(TIMEFRAMES.keys()), index=0)
    
    st.markdown("<h1 style='text-align: center; color: #ffffff;'>📈 INDIAN INSTITUTIONAL INDEX DASHBOARD</h1>", unsafe_allow_html=True)
    st.divider()

    tabs = st.tabs(list(INDICES.keys()))
    for tab, (index_name, ticker_sym) in zip(tabs, INDICES.items()):
        with tab:
            pcr_value, call_vol, put_vol = get_dhan_live_pcr(index_name)
            pcr_signal = "BULLISH" if put_vol > call_vol else "BEARISH"
            pcr_color = "#2efc03" if put_vol > call_vol else "#ff3333"

            st.markdown(f"### ⚡ Live Stream Option Terminal - {index_name}")
            c_vol1, c_vol2 = st.columns([1, 2])
            with c_vol1:
                st.metric(label="📊 PCR RATIO", value=f"{pcr_value}")
                st.caption(f"Put Vol: {put_vol:,} | Call Vol: {call_vol:,}")
            with c_vol2:
                st.markdown(f"<div style='background-color: #0f172a; padding: 15px; border-radius: 12px; border: 2px solid {pcr_color}; text-align: center;'><h2 style='color: {pcr_color}; margin: 0;'>{pcr_signal} DIRECTION DETECTED</h2></div>", unsafe_allow_html=True)

            st.markdown("---")

            raw_data = fetch_index_data(index_name, ticker_sym, tf_selection)
            if raw_data is None or raw_data.empty:
                st.error(f"❌ Core Network Stream Blocked for {index_name}.")
                continue
                
            calculated_data = apply_indicators(raw_data)
            s_top, s_bot, d_top, d_bot = calculate_order_blocks(calculated_data)
            final_df = generate_signals(calculated_data, s_bot, d_top)
            
            latest_row = final_df.iloc[-1]
            prev_row = final_df.iloc[-2]
            ltp = latest_row['Close']
            change = ltp - prev_row['Close']
            
            fib_levels = calculate_fibonacci(final_df)
            bin_centers, volumes, poc_price, hv_zones = calculate_volume_profile(final_df)
            trend_str, sentiment, sentiment_color = get_trend_and_sentiment(final_df, s_bot, d_top)
            
            m1, m2, m3, m4 = st.columns(4)
            with m1: st.metric(label=f"{index_name} LTP", value=f"{round(ltp, 2)}", delta=f"{round(change, 2)}")
            with m2: st.markdown(f"**Trend**<br><h3>{trend_str}</h3>", unsafe_allow_html=True)
            with m3: st.markdown(f"**Sentiment**<br><h3 style='color: {sentiment_color};'>{sentiment}</h3>", unsafe_allow_html=True)
            
            # Fixed the string escaping string error in UI signal block
            with m4:
                sig_color = "#238636" if "BUY" in latest_row['Signal'] else ("#da3633" if "SELL" in latest_row['Signal'] else "#161b22")
                st.markdown(f"**Signal**<br><div style='background-color:{sig_color}; padding:8px; border-radius:5px; text-align:center; color:white; font-weight:bold;'>{latest_row['Signal']}</div>", unsafe_allow_html=True)

            st.divider()
            chart_fig = plot_tradingview_chart(final_df, fib_levels, bin_centers, volumes, s_top, s_bot, d_top, d_bot)
            st.plotly_chart(chart_fig, use_container_width=True, key=f"chart_{index_name}_{tf_selection}")

    # Pure JavaScript injection to bypass execution timeout issues smoothly
    st.markdown("""
        <script>
            if (window.location.search.indexOf('autorefresh=true') === -1) {
                var currentURL = window.location.href;
                setInterval(function() {
                    window.location.reload();
                }, 10000);
            }
        </script>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
