import streamlit as st
import yfinance as yf
import pandas as pd
import ta
import feedparser
from textblob import TextBlob

st.set_page_config(page_title="NSE Live Tracker & Advisor", layout="wide")

# Universe of top liquid NSE stocks
MONITORED_STOCKS = [
    "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK", "HINDUNILVR",
    "ITC", "SBIN", "BHARTIARTL", "KOTAKBANK", "LT", "AXISBANK",
    "ASIANPAINT", "MARUTI", "SUNPHARMA", "TITAN", "BAJFINANCE",
    "TATAMOTORS", "TATASTEEL", "NTPC", "POWERGRID", "M&M",
    "ADANIENT", "ADANIPORTS", "COALINDIA", "BAJAJFINSV", "WIPRO",
    "ULTRACEMCO", "ONGC", "HCLTECH", "TECHM", "DIVISLAB",
    "VEDL", "ZOMATO", "PAYTM", "JIOFIN", "HAL", "BEL", "BHEL",
    "IRCTC", "RVNL", "IREDA", "SUZLON", "YESBANK", "IDEA", "DLF",
    "INDUSINDBK", "NESTLEIND", "GRASIM", "HEROMOTOCO", "EICHERMOT"
]

@st.cache_data(ttl=60)  # Auto-refreshes data every 60 seconds
def get_live_market_movers():
    """Fetches real-time intraday quotes for monitored stocks and sorts gainers/losers."""
    tickers = [f"{s}.NS" for s in MONITORED_STOCKS]
    try:
        # Download 2-day 1-minute/daily data in bulk for fast speed
        data = yf.download(tickers, period="2d", interval="1d", progress=False)["Close"]
        
        records = []
        for symbol in MONITORED_STOCKS:
            t = f"{symbol}.NS"
            if t in data.columns and len(data[t].dropna()) >= 2:
                prev_close = data[t].dropna().iloc[-2]
                current_price = data[t].dropna().iloc[-1]
                change = current_price - prev_close
                pct_change = (change / prev_close) * 100
                records.append({
                    "Stock": symbol,
                    "Live Price (₹)": round(current_price, 2),
                    "Change (₹)": round(change, 2),
                    "% Change": round(pct_change, 2)
                })
        
        df = pd.DataFrame(records)
        gainers = df.sort_values(by="% Change", ascending=False).head(10).reset_index(drop=True)
        losers = df.sort_values(by="% Change", ascending=True).head(10).reset_index(drop=True)
        return gainers, losers
    except Exception as e:
        return pd.DataFrame(), pd.DataFrame()

def fetch_news_sentiment(symbol):
    """Parses Google News RSS feed for the stock."""
    url = f"https://news.google.com/rss/search?q={symbol}+stock+market+india&hl=en-IN&gl=IN&ceid=IN:en"
    feed = feedparser.parse(url)
    
    articles = []
    total_polarity = 0
    for entry in feed.entries[:5]:
        title = entry.title
        score = TextBlob(title).sentiment.polarity
        total_polarity += score
        articles.append({"title": title, "link": entry.link, "score": score})
        
    avg_score = (total_polarity / len(articles)) if articles else 0
    return avg_score, articles

# --- UI HEADER ---
st.title("⚡ NSE Real-Time Market Pulse & Decision Engine")
st.caption("Live Market Movers • Intraday Prices • Technicals • Fundamentals • Sentiment")

# --- SECTION 1: TOP 10 GAINERS & LOSERS ---
st.subheader("📊 Today's Market Movers (Auto-refresh every 60s)")
g_col, l_col = st.columns(2)

gainers_df, losers_df = get_live_market_movers()

with g_col:
    st.markdown("##### 🟢 Top 10 Gainers")
    if not gainers_df.empty:
        # Style dataframe with green highlight
        st.dataframe(
            gainers_df.style.format({"Live Price (₹)": "₹{:.2f}", "Change (₹)": "+{:.2f}", "% Change": "+{:.2f}%"}),
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info("Fetching live data...")

with l_col:
    st.markdown("##### 🔴 Top 10 Losers")
    if not losers_df.empty:
        # Style dataframe with red highlight
        st.dataframe(
            losers_df.style.format({"Live Price (₹)": "₹{:.2f}", "Change (₹)": "{:.2f}", "% Change": "{:.2f}%"}),
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info("Fetching live data...")

st.markdown("---")

# --- SECTION 2: STOCK ANALYSIS & CALL GENERATOR ---
st.subheader("🔍 Deep-Dive Stock Analysis & Buy/Sell Call")

c1, c2 = st.columns([3, 1])
with c1:
    selected_stock = st.selectbox(
        "Type or select stock symbol:",
        options=sorted(MONITORED_STOCKS),
        index=None,
        placeholder="Start typing stock name (e.g., RELIANCE, TATAMOTORS, HDFCBANK)...",
        accept_new_options=True
    )
with c2:
    exchange = st.selectbox("Exchange:", ["NSE (.NS)", "BSE (.BO)"])

suffix = ".NS" if "NSE" in exchange else ".BO"

if st.button("Generate Signal & Analysis", type="primary"):
    if not selected_stock:
        st.warning("Please select or enter a stock ticker first.")
    else:
        ticker_symbol = selected_stock.strip().upper() + suffix
        with st.spinner(f"Fetching real-time order data and fundamentals for {ticker_symbol}..."):
            try:
                stock = yf.Ticker(ticker_symbol)
                hist = stock.history(period="1y")
                
                # Retrieve real-time quote via fast_info
                fast = getattr(stock, "fast_info", None)
                if fast and hasattr(fast, "last_price") and fast.last_price:
                    live_price = fast.last_price
                    prev_close = fast.previous_close or hist["Close"].iloc[-2]
                else:
                    live_price = hist["Close"].iloc[-1]
                    prev_close = hist["Close"].iloc[-2]

                day_change = live_price - prev_close
                day_pct = (day_change / prev_close) * 100

                info = stock.info

                if hist.empty or len(hist) < 50:
                    st.error("Insufficient market history to generate technical indicators.")
                else:
                    # 1. Technicals Calculation
                    hist["RSI"] = ta.momentum.RSIIndicator(hist["Close"], window=14).rsi()
                    hist["SMA_50"] = ta.trend.SMAIndicator(hist["Close"], window=50).sma_indicator()
                    hist["SMA_200"] = ta.trend.SMAIndicator(hist["Close"], window=200).sma_indicator()
                    macd = ta.trend.MACD(hist["Close"])
                    hist["MACD"] = macd.macd()
                    hist["MACD_Signal"] = macd.macd_signal()

                    latest = hist.iloc[-1]
                    rsi = latest["RSI"]
                    sma_50 = latest["SMA_50"]
                    sma_200 = latest["SMA_200"]

                    # 2. News Sentiment
                    sentiment_score, news_items = fetch_news_sentiment(selected_stock)

                    # 3. Short-Term Logic
                    st_score = 0
                    st_reasons = []

                    if rsi < 35:
                        st_score += 1
                        st_reasons.append(f"RSI oversold ({rsi:.1f}), strong bounce likelihood.")
                    elif rsi > 70:
                        st_score -= 1
                        st_reasons.append(f"RSI overbought ({rsi:.1f}), pullback risk.")
                    else:
                        st_reasons.append(f"RSI is neutral ({rsi:.1f}).")

                    if latest["MACD"] > latest["MACD_Signal"]:
                        st_score += 1
                        st_reasons.append("MACD is positive above signal line (bullish momentum).")
                    else:
                        st_score -= 1
                        st_reasons.append("MACD is below signal line (bearish momentum).")

                    if live_price > sma_50:
                        st_score += 1
                        st_reasons.append(f"Price is trading above 50-day SMA (₹{sma_50:.2f}).")
                    else:
                        st_score -= 1
                        st_reasons.append(f"Price is trading below 50-day SMA (₹{sma_50:.2f}).")

                    if sentiment_score > 0.05:
                        st_score += 1
                        st_reasons.append("Live news flow is positive.")
                    elif sentiment_score < -0.05:
                        st_score -= 1
                        st_reasons.append("Live news flow reflects negative market chatter.")

                    st_call = "BUY" if st_score >= 1 else ("SELL" if st_score <= -1 else "HOLD")

                    # 4. Long-Term Logic
                    lt_score = 0
                    lt_reasons = []

                    roe = info.get("returnOnEquity")
                    debt_equity = info.get("debtToEquity")

                    if roe and roe > 0.15:
                        lt_score += 1
                        lt_reasons.append(f"Healthy ROE of {roe*100:.1f}%.")
                    elif roe and roe < 0.08:
                        lt_score -= 1
                        lt_reasons.append(f"Weak capital efficiency: ROE of {roe*100:.1f}%.")

                    if debt_equity is not None:
                        if debt_equity < 100:
                            lt_score += 1
                            lt_reasons.append("Balance sheet is safe: Low Debt-to-Equity (< 1.0).")
                        else:
                            lt_score -= 1
                            lt_reasons.append("Elevated debt leverage on balance sheet.")

                    if pd.notna(sma_200):
                        if live_price > sma_200:
                            lt_score += 1
                            lt_reasons.append(f"Price above 200-day SMA (₹{sma_200:.2f}) confirming secular uptrend.")
                        else:
                            lt_score -= 1
                            lt_reasons.append(f"Price below 200-day SMA (₹{sma_200:.2f}) indicating macro downtrend.")

                    lt_call = "BUY" if lt_score >= 1 else ("SELL" if lt_score <= -1 else "HOLD")

                    # --- RENDER RESULTS ---
                    company_name = info.get("longName", ticker_symbol)
                    st.markdown("### " + company_name)
                    
                    # Live Price Metric Card
                    st.metric(
                        label="Live Traded Price (LTP)",
                        value=f"₹{live_price:,.2f}",
                        delta=f"{day_change:+,.2f} ({day_pct:+.2f}%)"
                    )

                    r_col1, r_col2 = st.columns(2)
                    with r_col1:
                        st.markdown("#### ⚡ Short-Term Outlook (1–4 Weeks)")
                        if st_call == "BUY": st.success("### ACTION: BUY")
                        elif st_call == "SELL": st.error("### ACTION: SELL")
                        else: st.warning("### ACTION: HOLD")

                        st.markdown("**Why?**")
                        for r in st_reasons: st.write(f"- {r}")

                    with r_col2:
                        st.markdown("#### 🏛️ Long-Term Outlook (6–18 Months)")
                        if lt_call == "BUY": st.success("### ACTION: BUY")
                        elif lt_call == "SELL": st.error("### ACTION: SELL")
                        else: st.warning("### ACTION: HOLD")

                        st.markdown("**Why?**")
                        for r in lt_reasons: st.write(f"- {r}")

                    # News Feed
                    st.markdown("---")
                    st.markdown("#### 📰 Recent Headlines Scanned")
                    for n in news_items:
                        badge = "🟢 Positive" if n["score"] > 0.05 else ("🔴 Negative" if n["score"] < -0.05 else "⚪ Neutral")
                        st.markdown(f"**[{badge}]** [{n['title']}]({n['link']})")

            except Exception as e:
                st.error(f"Error analyzing ticker: {e}")