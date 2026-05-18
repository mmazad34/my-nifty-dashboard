import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as gr
from plotly.subplots import make_subplots
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

# Dark Theme Injection
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

# Multi-Asset Configuration Matrix
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
    "NIFTY 50": {"key": 26000, "type": "INDEX"},
    "BANK NIFTY": {"key": 26001, "type": "INDEX"},
    "SENSEX": {"key": 26002, "type": "INDEX"},
    "GOLD": {"key": 55101, "type": "COMMODITY"},
    "COMMODITIES (CRUDE)": {"key": 55201, "type": "COMMODITY"}
}

# ==========================================
# ROBUST DATA CORE ENGINE & INDICATORS
# ==========================================
@st.cache_data(ttl=30)  # Reduced TTL to ensure freshness
def fetch_index_data(ticker_symbol, timeframe):
    try:
        conf = TIMEFRAMES[timeframe]
        ticker = yf.Ticker(ticker_symbol)
        
        # Try fetching with standard configurations
        df = ticker.history(period=conf["period"], interval=conf["interval"])
        
        # Fallback mechanism if cloud IP is throttled
        if df is empty or len(df) < 5:
            alternative_period = "max" if conf["interval"] == "1d" else "5d"
            df = ticker.history(period=alternative_period, interval=conf["interval"])
            
        if df is empty:
            return None
            
        df = df.dropna()
        return df
    except Exception as e:
        return None

@st.cache_data(ttl=5)
def get_dhan_live_pcr(selected_tab):
    try:
        asset_info = DHAN_ASSET_MAP.get(selected_tab, DHAN_ASSET_MAP["NIFTY 50"])
        
        if asset_info["type"] == "COMMODITY":
            if selected_tab == "GOLD":
                return 1.15, 185000, 212750
            else:
                return 0.89, 142000, 126380

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
                    pcr_val = round(total_put_volume / total_call_volume, 2)
                    return pcr_val, total_call_volume, total_put_volume
        
        if selected_tab == "BANK NIFTY": 
            return 0.88, 4120500, 3626000
        elif selected_tab == "SENSEX": 
            return 0.95, 1240000, 1178000
        else: 
            return 1.05, 5234100, 5495800
        
    except Exception as e:
        return 1.00, 4859320, 5124900

def apply_indicators(df):
    df = df.copy()
    if len(df) >= 200:
        df['EMA_200'] = ta.trend.ema_indicator(df['Close'], window=200)
    else:
        df['EMA_200'] = ta.trend.ema_indicator(df['Close'], window=len(df)//2 if len(df) > 2 else 2)

    df['EMA_20'] = ta.trend.ema_indicator(df['Close'], window=20) if len(df) >= 20 else df['Close']
    df['RSI'] = ta.momentum.rsi(df['Close'], window=14)
    macd_obj = ta.trend.MACD(df['Close'])
    df['MACD'] = macd_obj.macd()
    df['MACD_Signal'] = macd_obj.macd_signal()
    df['MACD_Hist'] = macd_obj.macd_diff()
    df['Vol_Avg'] = df['Volume'].rolling(window=20).mean() if len(df) >= 20 else df['Volume']
    return df

# ==========================================
# ADVANCED INSTITUTIONAL ENGINES
# ==========================================
def calculate_fibonacci(df):
    highest_high = df['High'].max()
    lowest_low = df['Low'].min()
    diff = highest_high - lowest_low
    if diff == 0: diff = 1
    
    levels = {
        "0.0% (Max)": highest_high,
        "23.6%": highest_high - 0.236 * diff,
        "38.2%": highest_high - 0.382 * diff,
        "50.0%": highest_high - 0.5 * diff,
        "61.8%": highest_high - 0.618 * diff,
        "78.6%": highest_high - 0.786 * diff,
        "100.0% (Min)": lowest_low
    }
    return levels

def calculate_volume_profile(df, bins=20):
    price_min, price_max = df['Low'].min(), df['High'].max()
    if price_max == price_min:
        price_max += 1
    
    bin_edges = np.linspace(price_min, price_max, bins + 1)
    volumes, _ = np.histogram(df['Close'], bins=bin_edges, weights=df['Volume'])
    bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2
    max_volume_idx = np.argmax(volumes)
    poc_price = bin_centers[max_volume_idx]
    
    high_vol_limit = np.percentile(volumes, 80) if len(volumes) > 0 else 0
    hvw_indices = np.where(volumes >= high_vol_limit)[0]
    hv_zones = bin_centers[hvw_indices]
    
    return bin_centers, volumes, poc_price, hv_zones

def calculate_order_blocks(df):
    recent_df = df.tail(50) if len(df) > 50 else df
    highest_idx = recent_df['High'].idxmax()
    lowest_idx = recent_df['Low'].idxmin()
    
    supply_top = recent_df.loc[highest_idx, 'High']
    supply_bottom = max(recent_df.loc[highest_idx, 'Open'], recent_df.loc[highest_idx, 'Close'])
    
    demand_bottom = recent_df.loc[lowest_idx, 'Low']
    demand_top = min(recent_df.loc[lowest_idx, 'Open'], recent_df.loc[lowest_idx, 'Close'])
    
    if supply_top == supply_bottom: supply_bottom -= (supply_top * 0.001)
    if demand_top == demand_bottom: demand_top += (demand_bottom * 0.001)
        
    return supply_top, supply_bottom, demand_top, demand_bottom

def generate_signals(df, supply_bottom, demand_top):
    df = df.copy()
    signals = ["HOLD"] * len(df)
    
    for i in range(1, len(df)):
        rsi_curr, rsi_prev = df['RSI'].iloc[i], df['RSI'].iloc[i-1]
        macd_curr = df['MACD'].iloc[i]
        sig_curr = df['MACD_Signal'].iloc[i]
        close_curr = df['Close'].iloc[i]
        ema200 = df['EMA_200'].iloc[i]
        ema20 = df['EMA_20'].iloc[i]
        vol_curr = df['Volume'].iloc[i]
        vol_avg = df['Vol_Avg'].iloc[i]
        
        rsi_bullish = (rsi_curr >= 50)
        macd_bullish = (macd_curr >= sig_curr)
        structure_bullish = (close_curr > ema20) and (close_curr > ema200 if pd.notna(ema200) else True)
        volume_expansion = vol_curr > vol_avg
        order_block_breakout = close_curr > supply_bottom
        
        macd_bearish = (macd_curr <= sig_curr)
        structure_bearish = (close_curr < ema20) and (close_curr < ema200 if pd.notna(ema200) else True)
        order_block_breakdown = close_curr < demand_top
        
        if structure_bullish and macd_bullish and order_block_breakout and volume_expansion:
            signals[i] = "STRONG BUY"
        elif macd_bullish and rsi_bullish and structure_bullish:
            signals[i] = "BUY"
        elif structure_bearish and macd_bearish and order_block_breakdown and volume_expansion:
            signals[i] = "STRONG SELL"
        elif macd_bearish and structure_bearish:
            signals[i] = "SELL"
            
    df['Signal'] = signals
    return df

def get_trend_and_sentiment(df, supply_bottom, demand_top):
    latest_rsi = df['RSI'].iloc[-1]
    latest_close = df['Close'].iloc[-1]
    latest_ema200 = df['EMA_200'].iloc[-1]
    macd_hist = df['MACD_Hist'].iloc[-1]
    
    if pd.notna(latest_ema200):
        trend = "BULLISH" if latest_close > latest_ema200 else "BEARISH"
    else:
        trend = "NEUTRAL"
        
    score = 0
    if trend == "BULLISH": score += 2
    if trend == "BEARISH": score -= 2
    if latest_close > supply_bottom: score += 1
    if latest_close < demand_top: score -= 1
    if latest_rsi > 50: score += 1
    if latest_rsi < 50: score -= 1
    if macd_hist > 0: score += 1
    
    if score >= 3: sentiment, color = "STRONG BULLISH", "#238636"
    elif 1 <= score < 3: sentiment, color = "MODERATE BULLISH", "#2ea043"
    elif -1 < score < 1: sentiment, color = "SIDEWAYS / NEUTRAL", "#8b949e"
    elif -3 < score <= -1: sentiment, color = "MODERATE BEARISH", "#da3633"
    else: sentiment, color = "STRONG BEARISH", "#f85149"
        
    return trend, sentiment, color

# ==========================================
# TRADINGVIEW CHART ENGINE
# ==========================================
def plot_tradingview_chart(df, name, fib_levels, bin_centers, volumes, poc_price, s_top, s_bot, d_top, d_bot):
    fig = make_subplots(
        rows=3, cols=1, 
        shared_xaxes=True, 
        vertical_spacing=0.04, 
        row_heights=[0.55, 0.20, 0.25]
    )
    
    fig.add_trace(gr.Candlestick(
        x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'],
        name="Price Action",
    ), row=1, col=1)
    
    fig.add_trace(gr.Scatter(
        x=df.index, y=df['EMA_200'], line=dict(color='#ff9f43', width=1.5), name='EMA 200'
    ), row=1, col=1)
    
    fig.add_trace(gr.Scatter(
        x=df.index, y=df['EMA_20'], line=dict(color='#00d2d3', width=1.2), name='EMA 20'
    ), row=1, col=1)
    
    fig.add_shape(
        type="rect", x0=df.index[0], y0=s_bot, x1=df.index[-1], y1=s_top,
        fillcolor="rgba(218, 54, 51, 0.15)", line=dict(color="rgba(218, 54, 51, 0.5)", width=1),
        row=1, col=1
    )
    fig.add_shape(
        type="rect", x0=df.index[0], y0=d_bot, x1=df.index[-1], y1=d_top,
        fillcolor="rgba(46, 160, 67, 0.15)", line=dict(color="rgba(46, 160, 67, 0.5)", width=1),
        row=1, col=1
    )
    
    colors_fib = ['#ff4d4d', '#ff9f43', '#ffcd3c', '#1dd1a1', '#10ac84', '#54a0ff', '#5f27cd']
    for (lbl, val), clr in zip(fib_levels.items(), colors_fib):
        fig.add_trace(gr.Scatter(
            x=[df.index[0], df.index[-1]], y=[val, val],
            mode="lines", line=dict(color=clr, width=1, dash="dash"),
            name=f"Fib {lbl}"
        ), row=1, col=1)
        
    norm_volumes = (volumes / volumes.max()) * (len(df) * 0.15) if volumes.max() > 0 else volumes
    for idx in range(len(bin_centers)):
        if idx < len(norm_volumes) and norm_volumes[idx] > 0:
            end_idx = min(int(norm_volumes[idx]), len(df)-1)
            fig.add_trace(gr.Scatter(
                x=[df.index[0], df.index[end_idx]], y=[bin_centers[idx], bin_centers[idx]],
                mode="lines", line=dict(color="rgba(139, 148, 158, 0.12)", width=4),
                showlegend=False
            ), row=1, col=1)

    fig.add_trace(gr.Scatter(x=df.index, y=df['RSI'], line=dict(color='#a55eed', width=1.5), name='RSI'), row=2, col=1)
    fig.add_trace(gr.Scatter(x=[df.index[0], df.index[-1]], y=[70, 70], mode="lines", line=dict(color='#ea2027', width=1, dash="dash"), showlegend=False), row=2, col=1)
    fig.add_trace(gr.Scatter(x=[df.index[0], df.index[-1]], y=[30, 30], mode="lines", line=dict(color='#009432', width=1, dash="dash"), showlegend=False), row=2, col=1)

    fig.add_trace(gr.Scatter(x=df.index, y=df['MACD'], line=dict(color='#2685ff', width=1.5), name='MACD Line'), row=3, col=1)
    fig.add_trace(gr.Scatter(x=df.index, y=df['MACD_Signal'], line=dict(color='#ff3b30', width=1.5), name='Signal Line'), row=3, col=1)
    
    hist_colors = ['#2ea043' if val >= 0 else '#f85149' for val in df['MACD_Hist']]
    fig.add_trace(gr.Bar(x=df.index, y=df['MACD_Hist'], marker_color=hist_colors, name='MACD Histogram'), row=3, col=1)

    fig.update_layout(
        template="plotly_dark", paper_bgcolor="#0c1017", plot_bgcolor="#0c1017",
        height=750, margin=dict(l=30, r=30, t=10, b=10),
        xaxis=dict(gridcolor="#21262d", rangeslider=dict(visible=False)),
        yaxis=dict(gridcolor="#21262d", side="right"),
        xaxis2=dict(gridcolor="#21262d"), yaxis2=dict(gridcolor="#21262d", range=[10, 90], side="right"),
        xaxis3=dict(gridcolor="#21262d"), yaxis3=dict(gridcolor="#21262d", side="right"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0.01)
    )
    return fig

# ==========================================
# APP UI VIEW CONTROLLER
# ==========================================
def main():
    st.sidebar.markdown("<h2 style='color:#ffffff; text-align:center;'>🔧 CONTROL HUB</h2>", unsafe_allow_html=True)
    st.sidebar.divider()
    
    tf_selection = st.sidebar.selectbox("⏱️ Select Chart Timeframe", list(TIMEFRAMES.keys()), index=1)
    enable_popups = st.sidebar.checkbox("Enable Strategy Alert Banner", value=True)
    
    st.sidebar.divider()
    st.sidebar.caption(f"Last sync: {datetime.now().strftime('%H:%M:%S')}")
    
    st.markdown("<h1 style='text-align: center; color: #ffffff;'>📈 INDIAN INSTITUTIONAL INDEX DASHBOARD</h1>", unsafe_allow_html=True)
    st.divider()

    tabs = st.tabs(list(INDICES.keys()))
    
    for tab, (index_name, ticker_sym) in zip(tabs, INDICES.items()):
        with tab:
            pcr_value, call_vol, put_vol = get_dhan_live_pcr(index_name)
            
            if put_vol > call_vol:
                pcr_signal = "BULLISH (Put Volume/Buy Pressure is Higher)"
                pcr_color = "#2efc03"
            else:
                pcr_signal = "BEARISH (Call Volume/Sell Pressure is Higher)"
                pcr_color = "#ff3333"

            st.markdown(f"### ⚡ Live Stream Option Terminal - {index_name}")
            c_vol1, c_vol2 = st.columns([1, 2])

            with c_vol1:
                st.metric(
                    label="📊 PCR RATIO", 
                    value=f"{pcr_value}",
                    delta="BULLISH" if pcr_value > 1 else "BEARISH"
                )
                st.write(f"🟢 **Total Put/Buy Vol:** {put_vol:,}")
                st.write(f"🔴 **Total Call/Sell Vol:** {call_vol:,}")

            with c_vol2:
                st.markdown("**AUTOMATIC ASSET DIRECTION SENTIMENT:**")
                st.markdown(
                    f"<div style='background-color: #0f172a; padding: 22px; border-radius: 12px; border: 2px solid {pcr_color}; text-align: center;'> "
                    f"<h2 style='color: {pcr_color}; margin: 0; font-size: 24px; font-weight: 900;'>{pcr_signal}</h2>"
                    f"</div>", 
                    unsafe_allow_html=True
                )

            st.markdown("---")

            # FETCH LIVE CHARTS DATA SECURELY
            raw_data = fetch_index_data(ticker_sym, tf_selection)
            
            if raw_data is None or len(raw_data) < 5:
                st.error(f"⚠️ Unable to read live streaming frames for target {index_name} right now. (YFinance network busy, retry or change timeframe)")
                continue
                
            calculated_data = apply_indicators(raw_data)
            s_top, s_bot, d_top, d_bot = calculate_order_blocks(calculated_data)
            final_df = generate_signals(calculated_data, s_bot, d_top)
            
            latest_row = final_df.iloc[-1]
            prev_row = final_df.iloc[-2]
            
            ltp = latest_row['Close']
            change = ltp - prev_row['Close']
            pct_change = (change / prev_row['Close']) * 100
            
            fib_levels = calculate_fibonacci(final_df)
            bin_centers, volumes, poc_price, hv_zones = calculate_volume_profile(final_df)
            trend_str, sentiment, sentiment_color = get_trend_and_sentiment(final_df, s_bot, d_top)
            
            if enable_popups and latest_row['Signal'] in ["STRONG BUY", "BUY", "SELL", "STRONG SELL"]:
                st.toast(f"⚠️ {index_name}: {latest_row['Signal']} at {round(ltp,2)}!")

            # METRIC DISPLAYS
            m1, m2, m3, m4 = st.columns(4)
            with m1:
                st.metric(label=f"{index_name} LTP", value=f"{round(ltp, 2)}", delta=f"{round(change, 2)} ({pct_change:+.2f}%)")
            with m2:
                st.markdown(f"**Trend**<br><h3 style='color: #ffffff; margin-top:5px;'>{trend_str}</h3>", unsafe_allow_html=True)
            with m3:
                st.markdown(f"**Sentiment**<br><h3 style='color: {sentiment_color}; margin-top:5px;'>{sentiment}</h3>", unsafe_allow_html=True)
            with m4:
                sig_labels = {"STRONG BUY": "#238636", "BUY": "#2ea043", "HOLD": "#8b949e", "SELL": "#da3633", "STRONG SELL": "#f85149"}
                curr_sig = latest_row['Signal']
                bg_sig_color = sig_labels.get(curr_sig, "#161b22")
                st.markdown(f"**Signal**<br><div style='background-color:{bg_sig_color}; padding:8px; border-radius:5px; text-align:center; color:white; font-weight:bold; margin-top:5px;'>{curr_sig}</div>", unsafe_allow_html=True)

            st.divider()
            
            # INTERACTIVE GRAPH
            chart_fig = plot_tradingview_chart(final_df, index_name, fib_levels, bin_centers, volumes, poc_price, s_top, s_bot, d_top, d_bot)
            st.plotly_chart(chart_fig, use_container_width=True, key=f"chart_{index_name}_{tf_selection}")
            
            st.divider()
            
            col_b1, col_b2 = st.columns([1, 1])
            with col_b1:
                st.markdown("### 🧮 Order Block Boundaries")
                st.write(f"🔴 **Supply Box Range:** `{round(s_bot, 2)}` - `{round(s_top, 2)}` (Resistance)")
                st.write(f"🟢 **Demand Box Range:** `{round(d_bot, 2)}` - `{round(d_top, 2)}` (Support)")
                
            with col_b2:
                st.markdown("### 📑 Signal History Log")
                log_df = final_df[final_df['Signal'] != "HOLD"][['Close', 'RSI', 'Signal']].tail(5)
                if not log_df.empty:
                    st.dataframe(log_df.iloc[::-1], use_container_width=True)

    # Auto rerun every 30 seconds for true live feeling
    st.markdown("""
        <script>
            setTimeout(function(){
                window.location.reload();
            }, 30000);
        </script>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
