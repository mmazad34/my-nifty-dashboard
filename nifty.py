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
from datetime import datetime
import io

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

INDICES = {
    "NIFTY 50": "^NSEI",
    "BANK NIFTY": "^NSEBANK",
    "SENSEX": "^BSESN"
}

TIMEFRAMES = {
    "5m": {"period": "5d", "interval": "5m"},
    "15m": {"period": "7d", "interval": "15m"},
    "1h": {"period": "60d", "interval": "1h"},
    "1d": {"period": "2y", "interval": "1d"}
}

# ==========================================
# DATA CORE ENGINE & INDICATORS
# ==========================================
@st.cache_data(ttl=60)
def fetch_index_data(ticker_symbol, timeframe):
    try:
        conf = TIMEFRAMES[timeframe]
        ticker = yf.Ticker(ticker_symbol)
        df = ticker.history(period=conf["period"], interval=conf["interval"])
        if df.empty:
            return None
        df = df.dropna()
        return df
    except Exception as e:
        st.error(f"Error fetching data for {ticker_symbol}: {e}")
        return None

def apply_indicators(df):
    # Avoid working on views
    df = df.copy()
    
    # 1. EMA 200
    if len(df) >= 200:
        df['EMA_200'] = ta.trend.ema_indicator(df['Close'], window=200)
    else:
        df['EMA_200'] = ta.trend.ema_indicator(df['Close'], window=len(df)//2 if len(df) > 2 else 2)

    # 2. RSI (14)
    df['RSI'] = ta.momentum.rsi(df['Close'], window=14)

    # 3. MACD
    macd_obj = ta.trend.MACD(df['Close'])
    df['MACD'] = macd_obj.macd()
    df['MACD_Signal'] = macd_obj.macd_signal()
    df['MACD_Hist'] = macd_obj.macd_diff()
    
    return df

# ==========================================
# ADVANCED ANALYTICS ENGINES
# ==========================================
def calculate_fibonacci(df):
    highest_high = df['High'].max()
    lowest_low = df['Low'].min()
    diff = highest_high - lowest_low
    
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
    poc_price = bin_centers[max_volume_idx] # Point of Control
    
    # Identify key high volume support/resistance zones (top 20% volume bars)
    high_vol_limit = np.percentile(volumes, 80)
    hvw_indices = np.where(volumes >= high_vol_limit)[0]
    hv_zones = bin_centers[hvw_indices]
    
    return bin_centers, volumes, poc_price, hv_zones

# ==========================================
# QUANT ALGORITHMIC SIGNAL SYSTEM
# ==========================================
def generate_signals(df):
    df = df.copy()
    signals = ["HOLD"] * len(df)
    
    for i in range(1, len(df)):
        # Base indicators
        rsi_curr, rsi_prev = df['RSI'].iloc[i], df['RSI'].iloc[i-1]
        macd_curr, macd_prev = df['MACD'].iloc[i], df['MACD'].iloc[i-1]
        sig_curr, sig_prev = df['MACD_Signal'].iloc[i], df['MACD_Signal'].iloc[i-1]
        close = df['Close'].iloc[i]
        ema = df['EMA_200'].iloc[i]
        
        # BUY Logic Matrix
        rsi_buy = (rsi_prev < 30 and rsi_curr >= 30) or (rsi_curr > 30 and rsi_curr < 45 and rsi_curr > rsi_prev)
        macd_buy = (macd_prev < sig_prev) and (macd_curr >= sig_curr)
        ema_buy = close > ema if pd.notna(ema) else True
        
        # SELL Logic Matrix
        rsi_sell = (rsi_prev > 70 and rsi_curr <= 70) or (rsi_curr < 70 and rsi_curr > 55 and rsi_curr < rsi_prev)
        macd_sell = (macd_prev > sig_prev) and (macd_curr <= sig_curr)
        ema_sell = close < ema if pd.notna(ema) else True
        
        if rsi_buy and macd_buy and ema_buy:
            signals[i] = "STRONG BUY"
        elif macd_buy or (rsi_buy and ema_buy):
            signals[i] = "BUY"
        elif rsi_sell and macd_sell and ema_sell:
            signals[i] = "STRONG SELL"
        elif macd_sell or (rsi_sell and ema_sell):
            signals[i] = "SELL"
            
    df['Signal'] = signals
    return df

def get_trend_and_sentiment(df):
    latest_rsi = df['RSI'].iloc[-1]
    latest_close = df['Close'].iloc[-1]
    latest_ema = df['EMA_200'].iloc[-1]
    macd_hist = df['MACD_Hist'].iloc[-1]
    
    # Trend Analysis
    if pd.notna(latest_ema):
        trend = "BULLISH" if latest_close > latest_ema else "BEARISH"
    else:
        trend = "NEUTRAL (Insufficient Historical Rows)"
        
    # Sentiment Weightage System
    score = 0
    if trend == "BULLISH": score += 2
    if trend == "BEARISH": score -= 2
    if latest_rsi > 50: score += 1
    if latest_rsi < 50: score -= 1
    if latest_rsi > 70: score -= 1 # Overbought correction risk
    if latest_rsi < 30: score += 1 # Oversold recovery potential
    if macd_hist > 0: score += 1
    if macd_hist < 0: score -= 1
    
    if score >= 3: sentiment, color = "STRONG BULLISH", "#238636"
    elif 1 <= score < 3: sentiment, color = "MODERATE BULLISH", "#2ea043"
    elif -1 < score < 1: sentiment, color = "SIDEWAYS / NEUTRAL", "#8b949e"
    elif -3 < score <= -1: sentiment, color = "MODERATE BEARISH", "#da3633"
    else: sentiment, color = "STRONG BEARISH", "#f85149"
        
    return trend, sentiment, color

# ==========================================
# TRADINGVIEW CHART ENGINE
# ==========================================
def plot_tradingview_chart(df, name, fib_levels, bin_centers, volumes, poc_price):
    # Create subplots grid layout (Row 1: Main candles + Vol profile, Row 2: RSI, Row 3: MACD)
    fig = make_subplots(
        rows=3, cols=1, 
        shared_xaxes=True, 
        vertical_spacing=0.04, 
        row_heights=[0.55, 0.20, 0.25]
    )
    
    # 1. Main Candlestick Chart
    fig.add_trace(gr.Candlestick(
        x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'],
        name="Price Action",
    ), row=1, col=1)
    
    # 2. Add EMA 200 Overlay
    fig.add_trace(gr.Scatter(
        x=df.index, y=df['EMA_200'], line=dict(color='#ff9f43', width=1.5), name='EMA 200'
    ), row=1, col=1)
    
    # 3. Add Fibonacci Horizontal Projections
    colors_fib = ['#ff4d4d', '#ff9f43', '#ffcd3c', '#1dd1a1', '#10ac84', '#54a0ff', '#5f27cd']
    for (lbl, val), clr in zip(fib_levels.items(), colors_fib):
        fig.add_trace(gr.Scatter(
            x=[df.index[0], df.index[-1]], y=[val, val],
            mode="lines", line=dict(color=clr, width=1, dash="dash"),
            name=f"Fib {lbl}"
        ), row=1, col=1)
        
    # 4. Draw Volume Profile Bars (Horizontal projections aligned to the left of chart)
    norm_volumes = (volumes / volumes.max()) * (len(df) * 0.15)
    for idx in range(len(bin_centers)):
        fig.add_trace(gr.Scatter(
           x=[df.index[0], df.index[int(norm_volumes[idx])] if (not np.isnan(norm_volumes[idx]) and norm_volumes[idx] > 0) else df.index[0]], 
            y=[bin_centers[idx], bin_centers[idx]],
            mode="lines", line=dict(color="rgba(139, 148, 158, 0.15)", width=4),
            showlegend=False
        ), row=1, col=1)
        
    # Highlight POC Line
    fig.add_trace(gr.Scatter(
        x=[df.index[0], df.index[-1]], y=[poc_price, poc_price],
        mode="lines", line=dict(color="#00d2d3", width=1.5, dash="dot"), name="Volume POC"
    ), row=1, col=1)

    # 5. RSI Subplot Panel
    fig.add_trace(gr.Scatter(x=df.index, y=df['RSI'], line=dict(color='#a55eed', width=1.5), name='RSI'), row=2, col=1)
    fig.add_trace(gr.Scatter(x=[df.index[0], df.index[-1]], y=[70, 70], mode="lines", line=dict(color='#ea2027', width=1, dash="dash"), showlegend=False), row=2, col=1)
    fig.add_trace(gr.Scatter(x=[df.index[0], df.index[-1]], y=[30, 30], mode="lines", line=dict(color='#009432', width=1, dash="dash"), showlegend=False), row=2, col=1)

    # 6. MACD Subplot Panel
    fig.add_trace(gr.Scatter(x=df.index, y=df['MACD'], line=dict(color='#2685ff', width=1.5), name='MACD Line'), row=3, col=1)
    fig.add_trace(gr.Scatter(x=df.index, y=df['MACD_Signal'], line=dict(color='#ff3b30', width=1.5), name='Signal Line'), row=3, col=1)
    
    # Dynamic Colors for MACD Histogram bars
    hist_colors = ['#2ea043' if val >= 0 else '#f85149' for val in df['MACD_Hist']]
    fig.add_trace(gr.Bar(x=df.index, y=df['MACD_Hist'], marker_color=hist_colors, name='MACD Histogram'), row=3, col=1)

    # Design configuration
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="#0c1017",
        plot_bgcolor="#0c1017",
        height=800,
        margin=dict(l=30, r=30, t=10, b=10),
        xaxis=dict(gridcolor="#21262d", rangeslider=dict(visible=False)),
        yaxis=dict(gridcolor="#21262d", side="right"),
        xaxis2=dict(gridcolor="#21262d"),
        yaxis2=dict(gridcolor="#21262d", range=[10, 90], side="right"),
        xaxis3=dict(gridcolor="#21262d"),
        yaxis3=dict(gridcolor="#21262d", side="right"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0.01)
    )
    return fig

# ==========================================
# APP UI VIEW CONTROLLER
# ==========================================
def main():
    # Sidebar Setup
    st.sidebar.markdown("<h2 style='color:#ffffff; text-align:center;'>🔧 CONTROL HUB</h2>", unsafe_allow_html=True)
    st.sidebar.divider()
    
    tf_selection = st.sidebar.selectbox("⏱️ Select Chart Timeframe", list(TIMEFRAMES.keys()), index=1)
    st.sidebar.caption("Data sources will automatically adjust parsing periods to map specific window increments.")
    
    st.sidebar.divider()
    st.sidebar.markdown("### 🔔 Real-time Notifications")
    enable_popups = st.sidebar.checkbox("Enable Strategy Alert Banner", value=True)
    
    # Auto Refresh Engine
    st.sidebar.divider()
    st.sidebar.caption(f"Last updated trace loop: {datetime.now().strftime('%H:%M:%S')}")
    st.sidebar.caption("App configured to auto-recompute indices variables continuously.")
    
    # Main Heading
    st.markdown("<h1 style='text-align: center; color: #ffffff;'>📈 INDIAN INSTITUTIONAL INDEX DASHBOARD</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: #8b949e;'>Real-time Technical Strategy Engine & Algorithmic Signal Terminal</p>", unsafe_allow_html=True)
    st.divider()

    # Create UI Index Tabs
    tabs = st.tabs(list(INDICES.keys()))
    
    for tab, (index_name, ticker_sym) in zip(tabs, INDICES.items()):
        with tab:
            # Fetch & compute data matrices
            raw_data = fetch_index_data(ticker_sym, tf_selection)
            
            if raw_data is None or len(raw_data) < 5:
                st.error(f"Unable to read streaming frames for target {index_name}. Keep parameters baseline loose.")
                continue
                
            calculated_data = apply_indicators(raw_data)
            final_df = generate_signals(calculated_data)
            
            # Current Row Status Matrix
            latest_row = final_df.iloc[-1]
            prev_row = final_df.iloc[-2]
            
            ltp = latest_row['Close']
            change = ltp - prev_row['Close']
            pct_change = (change / prev_row['Close']) * 100
            
            # Sub-calculations modules
            fib_levels = calculate_fibonacci(final_df)
            bin_centers, volumes, poc_price, hv_zones = calculate_volume_profile(final_df)
            trend_str, sentiment, sentiment_color = get_trend_and_sentiment(final_df)
            
            # Render Live Notification Banner if triggered
            if enable_popups and latest_row['Signal'] in ["STRONG BUY", "BUY", "SELL", "STRONG SELL"]:
                st.toast(f"⚠️ {index_name} ({tf_selection}): {latest_row['Signal']} Signal detected at price {round(ltp,2)}!", icon="🔥")

            # TOP ROW METRIC DISPLAY PANELS
            m1, m2, m3, m4 = st.columns(4)
            with m1:
                st.metric(label=f"{index_name} LTP", value=f"{round(ltp, 2)}", delta=f"{round(change, 2)} ({pct_change:+.2f}%)")
            with m2:
                st.markdown(f"**Structural Trend Factor**<br><h3 style='color: #ffffff; margin-top:5px;'>{trend_str}</h3>", unsafe_allow_html=True)
            with m3:
                st.markdown(f"**Market Sentiment Gauge**<br><h3 style='color: {sentiment_color}; margin-top:5px;'>{sentiment}</h3>", unsafe_allow_html=True)
            with m4:
                # Dynamic Color Coding Strategy for Signal Badges
                sig_labels = {"STRONG BUY": "#238636", "BUY": "#2ea043", "HOLD": "#8b949e", "SELL": "#da3633", "STRONG SELL": "#f85149"}
                curr_sig = latest_row['Signal']
                bg_sig_color = sig_labels.get(curr_sig, "#161b22")
                st.markdown(f"**System Recommendation**<br><div style='background-color:{bg_sig_color}; padding:8px; border-radius:5px; text-align:center; color:white; font-weight:bold; margin-top:5px; font-size:18px;'>{curr_sig}</div>", unsafe_allow_html=True)

            st.divider()
            
            # MIDDLE WORKSPACE: CHARTING SECTION
            st.markdown(f"### 📊 TradingView Interactive Composite Workspace ({tf_selection})")
            chart_fig = plot_tradingview_chart(final_df, index_name, fib_levels, bin_centers, volumes, poc_price)
            st.plotly_chart(chart_fig, use_container_width=True, key=f"chart_{index_name}_{tf_selection}")
            
            st.divider()
            
            # LOWER ROW DATA TABLES AND STATS METRICS BLOCK
            col_b1, col_b2 = st.columns([1, 1])
            
            with col_b1:
                st.markdown("### 🧮 Auto Fibonacci Levels & Volume Profile Clusters")
                
                f_data = [{"Retracement Level": k, "Target Price Projection": round(v, 2)} for k, v in fib_levels.items()]
                fib_table = pd.DataFrame(f_data)
                
                st.dataframe(fib_table, use_container_width=True, hide_index=True)
                st.write(f"**Volume Point of Control (POC):** `{round(poc_price, 2)}` (Maximum Institutional Activity Zone)")
                
            with col_b2:
                st.markdown("### 📑 Algorithmic Signal Log History & Export")
                
                log_df = final_df[final_df['Signal'] != "HOLD"][['Open', 'High', 'Low', 'Close', 'RSI', 'Signal']].tail(10)
                # Reverse for latest entries sequence first
                log_df = log_df.iloc[::-1]
                
                if not log_df.empty:
                    st.dataframe(log_df.style.map(
                        lambda x: f"color: {sig_labels.get(x, '#ffffff')}; font-weight: bold;" if x in sig_labels else "color: #c9d1d9",
                        subset=['Signal']
                    ), use_container_width=True)
                    
                    # Setup CSV download link string buffer
                    csv_buffer = io.StringIO()
                    final_df.to_csv(csv_buffer)
                    st.download_button(
                        label=f"📥 Export Full Data History for {index_name} (CSV)",
                        data=csv_buffer.getvalue(),
                        file_name=f"{index_name.lower().replace(' ', '_')}_signals.csv",
                        mime="text/csv"
                    )
                else:
                    st.info("No active structural Buy/Sell indicators registered inside current validation frame.")

    # HTML Snippet injecting auto reload loop every 60 seconds
    st.markdown("""
        <script>
            setTimeout(function(){
                window.location.reload();
            }, 60000);
        </script>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
