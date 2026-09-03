import streamlit as st
import yfinance as yf
import pandas as pd
import ta
import feedparser
import requests
from textblob import TextBlob

# Page layout configuration
st.set_page_config(
    page_title="NSE Live Tracker & Decision Tool",
    page_icon="📈",
    layout="wide"
)

# Core stock universe for Top 10 Gainers / Losers and Auto-complete
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

@st.cache_data(ttl=60)
def get_live_market_movers():
    """Fetches real-time intraday quotes for universe and ranks gainers/losers."""
    tickers = [f"{s}.NS" for s in MONITORED_STOCKS]
    try:
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
    except Exception:
        return pd.DataFrame(), pd.DataFrame()

def fetch_cloud_safe_news(ticker_obj, symbol):
    """
    Fetches news using yfinance built-in feed first.
    Falls back to Google News RSS with browser User-Agent to prevent 403 blocks in the cloud.
    """
    articles = []
    total_polarity = 0

    # 1. Primary Method: yfinance news API
    try:
        raw_news = getattr(ticker_obj, "news", [])
        if raw_news:
            for item in raw_news[:5]:
                title = item.get("title")
                link = item.get("link", "#")
                # Handle newer yfinance schema structures
                if not title and "content" in item and isinstance(item["content"], dict):
                    title = item["content"].get("title")
                    link = item["content"].get("canonicalUrl", {}).get("url", link)

                if title:
                    score = TextBlob(title).sentiment.polarity
                    total_polarity += score
                    articles.append({"title": title, "link": link, "score": score})
    except Exception:
        pass

    # 2. Fallback Method: RSS feed with explicit browser User-Agent headers
    if not articles:
        try:
            url = f"https://news.google.com/rss/search?q={symbol}+stock+market+india&hl=en-IN&gl=IN&ceid=IN:en"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            resp = requests.get(url, headers=headers, timeout=5)
            feed = feedparser.parse(resp.content)
            for entry in feed.entries[:5]:
                title = entry.title
                score = TextBlob(title).sentiment.polarity
                total_polarity += score
                articles.append({"title": title, "link": entry.link, "score": score})
        except Exception:
            pass

    avg_score = (total_polarity / len(articles)) if articles else 0
    return avg_score, articles


# --- UI HEADER ---
st.title("⚡ NSE Real-Time Market Pulse & Decision Engine")
st.caption("Live Movers (Top 10) • Real-Time LTP • Quantitative Signals • Fundamental Checks • Cloud News")

# --- SECTION 1: TOP 10 GAINERS & LOSERS ---
st.subheader("📊 Today's Market Movers (Auto-refresh every 60s)")
g_col, l_col = st.columns(2)

gainers_df, losers_df = get_live_market_movers()

with g_col:
    st.markdown("##### 🟢 Top 10 Gainers")
    if not gainers_df.empty:
        st.dataframe(
            gainers_df.style.format({
                "Live Price (₹)": "₹{:.2f}",
                "Change (₹)": "+{:.2f}",
                "% Change": "+{:.2f}%"
            }),
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info("Loading live market data...")

with l_col:
    st.markdown("##### 🔴 Top 10 Losers")
    if not losers_df.empty:
        st.dataframe(
            losers_df.style.format({
                "Live Price (₹)": "₹{:.2f}",
                "Change (₹)": "{:.2f}",
                "% Change": "{:.2f}%"
            }),
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info("Loading live market data...")

st.markdown("---")

# --- SECTION 2: STOCK ANALYSIS & CALL GENERATOR ---
st.subheader("🔍 Deep-Dive Stock Analysis & Buy/Sell Call")

col_search, col_exch = st.columns([3, 1])
with col_search:
    selected_stock = st.selectbox(
        "Type or select stock symbol (e.g., RELIANCE, TATAMOTORS, HDFCBANK):",
        options=sorted(MONITORED_STOCKS),
        index=None,
        placeholder="Start typing stock name...",
        accept_new_options=True
    )
with col_exch:
    exchange = st.selectbox("Exchange:", ["NSE (.NS)", "BSE (.BO)"])

suffix = ".NS" if "NSE" in exchange else ".BO"

if st.button("Generate Signal & Analysis", type="primary"):
    if not selected_stock:
        st.warning("Please select or enter a stock ticker first.")
    else:
        ticker_symbol = selected_stock.strip().upper() + suffix
        with st.spinner(f"Retrieving order books, technicals, and news for {ticker_symbol}..."):
            try:
                stock = yf.Ticker(ticker_symbol)
                hist = stock.history(period="1y")

                # Live price extraction via fast_info with fallback
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
                    st.error("Insufficient market history for this ticker to calculate technical metrics.")
                else:
                    # 1. Technical Indicators
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

                    # 2. Cloud-safe News & Sentiment
                    sentiment_score, news_items = fetch_cloud_safe_news(stock, selected_stock)

                    # 3. Short-Term Signal Framework
                    st_score = 0
                    st_reasons = []

                    if rsi < 35:
                        st_score += 1
                        st_reasons.append(f"RSI is oversold at {rsi:.1f}, indicating high rebound probability.")
                    elif rsi > 70:
                        st_score -= 1
                        st_reasons.append(f"RSI is overbought at {rsi:.1f}, signaling short-term exhaustion.")
                    else:
                        st_reasons.append(f"RSI is balanced at {rsi:.1f}.")

                    if latest["MACD"] > latest["MACD_Signal"]:
                        st_score += 1
                        st_reasons.append("Bullish momentum: MACD line holds above the signal line.")
                    else:
                        st_score -= 1
                        st_reasons.append("Bearish momentum: MACD line trades below the signal line.")

                    if live_price > sma_50:
                        st_score += 1
                        st_reasons.append(f"Price is trading above 50-day moving average (₹{sma_50:.2f}).")
                    else:
                        st_score -= 1
                        st_reasons.append(f"Price is trading below 50-day moving average (₹{sma_50:.2f}).")

                    if sentiment_score > 0.05:
                        st_score += 1
                        st_reasons.append(f"Live news flow sentiment is positive (+{sentiment_score:.2f}).")
                    elif sentiment_score < -0.05:
                        st_score -= 1
                        st_reasons.append(f"Live news flow sentiment is cautious/negative ({sentiment_score:.2f}).")
                    else:
                        st_reasons.append("Market news sentiment is currently neutral.")

                    st_call = "BUY" if st_score >= 1 else ("SELL" if st_score <= -1 else "HOLD")

                    # 4. Long-Term Signal Framework
                    lt_score = 0
                    lt_reasons = []

                    roe = info.get("returnOnEquity")
                    debt_equity = info.get("debtToEquity")

                    if roe and roe > 0.15:
                        lt_score += 1
                        lt_reasons.append(f"Strong profitability: Return on Equity (ROE) is {roe*100:.1f}%.")
                    elif roe and roe < 0.08:
                        lt_score -= 1
                        lt_reasons.append(f"Subdued capital returns: ROE is {roe*100:.1f}%.")

                    if debt_equity is not None:
                        if debt_equity < 100:
                            lt_score += 1
                            lt_reasons.append("Conservative leverage: Debt-to-Equity is safe (< 1.0).")
                        else:
                            lt_score -= 1
                            lt_reasons.append("Elevated debt: Higher leverage on the balance sheet.")

                    if pd.notna(sma_200):
                        if live_price > sma_200:
                            lt_score += 1
                            lt_reasons.append(f"Structural secular uptrend (Above 200-day SMA of ₹{sma_200:.2f}).")
                        else:
                            lt_score -= 1
                            lt_reasons.append(f"Macro multi-month downtrend (Below 200-day SMA of ₹{sma_200:.2f}).")

                    lt_call = "BUY" if lt_score >= 1 else ("SELL" if lt_score <= -1 else "HOLD")

                    # 5. Presentation
                    st.markdown("---")
                    company_name = info.get("longName", ticker_symbol)
                    st.subheader(company_name)

                    st.metric(
                        label="Live Traded Price (LTP)",
                        value=f"₹{live_price:,.2f}",
                        delta=f"{day_change:+,.2f} ({day_pct:+.2f}%)"
                    )

                    r_col1, r_col2 = st.columns(2)
                    with r_col1:
                        st.markdown("#### ⚡ Short-Term Outlook (1–4 Weeks)")
                        if st_call == "BUY":
                            st.success("### ACTION: BUY")
                        elif st_call == "SELL":
                            st.error("### ACTION: SELL")
                        else:
                            st.warning("### ACTION: HOLD")

                        st.markdown("**Why?**")
                        for r in st_reasons:
                            st.write(f"- {r}")

                    with r_col2:
                        st.markdown("#### 🏛️ Long-Term Outlook (6–18 Months)")
                        if lt_call == "BUY":
                            st.success("### ACTION: BUY")
                        elif lt_call == "SELL":
                            st.error("### ACTION: SELL")
                        else:
                            st.warning("### ACTION: HOLD")

                        st.markdown("**Why?**")
                        for r in lt_reasons:
                            st.write(f"- {r}")

                    # 6. Headlines Section
                    st.markdown("---")
                    st.markdown("#### 📰 Recent Headlines Scanned")
                    if news_items:
                        for n in news_items:
                            badge = "🟢 Positive" if n["score"] > 0.05 else ("🔴 Negative" if n["score"] < -0.05 else "⚪ Neutral")
                            st.markdown(f"**[{badge}]** [{n['title']}]({n['link']})")
                    else:
                        st.info("No recent news headlines found for this symbol.")

            except Exception as e:
                st.error(f"Error analyzing ticker: {e}")