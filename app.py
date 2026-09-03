import streamlit as st
import yfinance as yf
import pandas as pd
import ta
import feedparser
from textblob import TextBlob

# Set layout
st.set_page_config(page_title="NSE/BSE Signal Analyzer", layout="wide")
st.title("📈 NSE / BSE Stock Decision & Advisory by AI Engine by Balmukund Nuval")
st.caption("Auto-suggest stocks + Technicals + Fundamentals + Live News Sentiment")

# Predefined list of popular NSE/BSE stocks for auto-complete suggestions
POPULAR_STOCKS = [
    "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK", "HINDUNILVR",
    "ITC", "SBIN", "BHARTIARTL", "KOTAKBANK", "LT", "AXISBANK",
    "ASIANPAINT", "MARUTI", "SUNPHARMA", "TITAN", "BAJFINANCE",
    "TATAMOTORS", "TATASTEEL", "NTPC", "POWERGRID", "M&M",
    "ADANIENT", "ADANIPORTS", "COALINDIA", "BAJAJFINSV", "WIPRO",
    "ULTRACEMCO", "ONGC", "HCLTECH", "TECHM", "DIVISLAB",
    "VEDL", "ZOMATO", "PAYTM", "JIOFIN", "HAL", "BEL", "BHEL",
    "IRCTC", "RVNL", "IREDA", "SUZLON", "YESBANK", "IDEA"
]

def fetch_news_sentiment(symbol):
    url = f"https://news.google.com/rss/search?q={symbol}+stock+share+market&hl=en-IN&gl=IN&ceid=IN:en"
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

# --- Input Area with Auto-Suggest ---
col_input1, col_input2 = st.columns([3, 1])

with col_input1:
    # This acts as an auto-suggest text field:
    # Users can start typing letters, pick from suggestions, OR type any other ticker
    selected_stock = st.selectbox(
        "Type or select stock symbol (e.g. TATA, REL, INFY):",
        options=sorted(POPULAR_STOCKS),
        index=None,
        placeholder="Start typing stock name (e.g., RELIANCE, TATAMOTORS)...",
        accept_new_options=True
    )

with col_input2:
    market = st.selectbox("Select Exchange:", ["NSE (.NS)", "BSE (.BO)"])

suffix = ".NS" if "NSE" in market else ".BO"

if st.button("Run Complete Analysis", type="primary"):
    if not selected_stock:
        st.warning("Please type or select a stock symbol first.")
    else:
        ticker_symbol = selected_stock.strip().upper() + suffix
        with st.spinner(f"Analyzing {ticker_symbol} across technicals, balance sheet, and live news..."):
            try:
                stock = yf.Ticker(ticker_symbol)
                hist = stock.history(period="1y")
                info = stock.info

                if hist.empty or len(hist) < 50:
                    st.error("Could not fetch data for this ticker. Please ensure the symbol name is correct.")
                else:
                    # 1. Technical Indicators Calculation
                    hist["RSI"] = ta.momentum.RSIIndicator(hist["Close"], window=14).rsi()
                    hist["SMA_50"] = ta.trend.SMAIndicator(hist["Close"], window=50).sma_indicator()
                    hist["SMA_200"] = ta.trend.SMAIndicator(hist["Close"], window=200).sma_indicator()
                    macd = ta.trend.MACD(hist["Close"])
                    hist["MACD"] = macd.macd()
                    hist["MACD_Signal"] = macd.macd_signal()

                    latest = hist.iloc[-1]
                    current_price = latest["Close"]
                    rsi = latest["RSI"]
                    sma_50 = latest["SMA_50"]
                    sma_200 = latest["SMA_200"]

                    # 2. News Sentiment Analysis
                    sentiment_avg, news_items = fetch_news_sentiment(selected_stock)

                    # 3. Short-Term Decision Logic
                    st_score = 0
                    st_reasons = []

                    if rsi < 35:
                        st_score += 1
                        st_reasons.append(f"RSI is oversold at {rsi:.1f}, indicating high bounce potential.")
                    elif rsi > 70:
                        st_score -= 1
                        st_reasons.append(f"RSI is overbought at {rsi:.1f}, indicating pullback exhaustion.")
                    else:
                        st_reasons.append(f"RSI is neutral at {rsi:.1f}.")

                    if latest["MACD"] > latest["MACD_Signal"]:
                        st_score += 1
                        st_reasons.append("MACD line is above signal line (bullish momentum).")
                    else:
                        st_score -= 1
                        st_reasons.append("MACD line is below signal line (bearish momentum).")

                    if current_price > sma_50:
                        st_score += 1
                        st_reasons.append(f"Price (₹{current_price:.2f}) trades above the 50-day moving average.")
                    else:
                        st_score -= 1
                        st_reasons.append(f"Price (₹{current_price:.2f}) trades below the 50-day moving average.")

                    if sentiment_avg > 0.05:
                        st_score += 1
                        st_reasons.append("Market news sentiment is positive.")
                    elif sentiment_avg < -0.05:
                        st_score -= 1
                        st_reasons.append("Market news sentiment is cautious/negative.")

                    st_call = "BUY" if st_score >= 1 else ("SELL" if st_score <= -1 else "HOLD")

                    # 4. Long-Term Decision Logic
                    lt_score = 0
                    lt_reasons = []

                    roe = info.get("returnOnEquity")
                    debt_equity = info.get("debtToEquity")

                    if roe is not None:
                        if roe > 0.15:
                            lt_score += 1
                            lt_reasons.append(f"Healthy ROE: {roe*100:.1f}%.")
                        elif roe < 0.08:
                            lt_score -= 1
                            lt_reasons.append(f"Weak capital return: ROE is {roe*100:.1f}%.")

                    if debt_equity is not None:
                        if debt_equity < 100:
                            lt_score += 1
                            lt_reasons.append("Conservative leverage: Debt-to-Equity is safely below 1.0.")
                        else:
                            lt_score -= 1
                            lt_reasons.append("Higher financial leverage: Debt-to-Equity is elevated.")

                    if pd.notna(sma_200):
                        if current_price > sma_200:
                            lt_score += 1
                            lt_reasons.append(f"Long-term uptrend active (Above 200-day SMA of ₹{sma_200:.2f}).")
                        else:
                            lt_score -= 1
                            lt_reasons.append(f"Multi-month downtrend (Below 200-day SMA of ₹{sma_200:.2f}).")

                    lt_call = "BUY" if lt_score >= 1 else ("SELL" if lt_score <= -1 else "HOLD")

                    # 5. Output Cards
                    st.markdown("---")
                    company_title = info.get("longName", ticker_symbol)
                    st.subheader(f"{company_title} — CMP: ₹{current_price:,.2f}")

                    res_left, res_right = st.columns(2)

                    with res_left:
                        st.markdown("### ⚡ Short-Term Call (1 to 4 Weeks)")
                        if st_call == "BUY":
                            st.success(f"## ACTION: {st_call}")
                        elif st_call == "SELL":
                            st.error(f"## ACTION: {st_call}")
                        else:
                            st.warning(f"## ACTION: {st_call}")

                        st.markdown("**Why this call?**")
                        for r in st_reasons:
                            st.write(f"- {r}")

                    with res_right:
                        st.markdown("### 🏛️ Long-Term Call (6 to 18 Months)")
                        if lt_call == "BUY":
                            st.success(f"## ACTION: {lt_call}")
                        elif lt_call == "SELL":
                            st.error(f"## ACTION: {lt_call}")
                        else:
                            st.warning(f"## ACTION: {lt_call}")

                        st.markdown("**Why this call?**")
                        for r in lt_reasons:
                            st.write(f"- {r}")

                    # 6. Headlines
                    st.markdown("---")
                    st.markdown("### 📰 Recent Scanned Headlines")
                    for item in news_items:
                        tag = "🟢 Positive" if item["score"] > 0.05 else ("🔴 Negative" if item["score"] < -0.05 else "⚪ Neutral")
                        st.markdown(f"**[{tag}]** [{item['title']}]({item['link']})")

            except Exception as err:
                st.error(f"Execution Error: {err}")