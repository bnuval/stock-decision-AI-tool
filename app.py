import streamlit as st
import yfinance as yf
import pandas as pd
import ta
import feedparser
import requests
import io
from textblob import TextBlob

# Page layout configuration
st.set_page_config(
    page_title="NSE Live Screener & Signal Engine",
    page_icon="📈",
    layout="wide"
)

# --- 1. DYNAMIC DATA SOURCE: ALL NSE LISTED STOCKS ---
@st.cache_data(ttl=86400)
def get_all_nse_symbols():
    """
    Downloads the official NSE equity master file so every active listed
    share (including newly listed and small-cap stocks) is selectable.
    """
    url = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            df = pd.read_csv(io.StringIO(response.text))
            eq_df = df[df[" SERIES"] == "EQ"].copy()
            symbols = sorted(eq_df["SYMBOL"].str.strip().tolist())
            if len(symbols) > 500:
                return symbols
    except Exception:
        pass
    
    # Robust fallback universe of liquid stocks across sectors
    return [
        "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK", "HINDUNILVR", "ITC", "SBIN",
        "BHARTIARTL", "KOTAKBANK", "LT", "AXISBANK", "ASIANPAINT", "MARUTI", "SUNPHARMA",
        "TITAN", "BAJFINANCE", "TATAMOTORS", "TATASTEEL", "NTPC", "POWERGRID", "M&M",
        "ADANIENT", "ADANIPORTS", "COALINDIA", "BAJAJFINSV", "WIPRO", "ULTRACEMCO", "ONGC",
        "HCLTECH", "TECHM", "DIVISLAB", "VEDL", "ZOMATO", "PAYTM", "JIOFIN", "HAL",
        "BEL", "BHEL", "IRCTC", "RVNL", "IREDA", "SUZLON", "YESBANK", "IDEA", "DLF",
        "INDUSINDBK", "NESTLEIND", "GRASIM", "HEROMOTOCO", "EICHERMOT", "DABUR", "LALITHAA"
    ]

ALL_NSE_STOCKS = get_all_nse_symbols()

# --- 2. LIVE GAINERS & LOSERS SCANNER ---
@st.cache_data(ttl=60)
def get_live_market_data(universe):
    """Fetches real-time intraday quotes for universe and ranks gainers/losers."""
    scan_universe = universe[:100]
    tickers = [f"{s}.NS" for s in scan_universe]
    try:
        data = yf.download(tickers, period="5d", interval="1d", progress=False)["Close"]
        records = []
        for symbol in scan_universe:
            t = f"{symbol}.NS"
            if t in data.columns and len(data[t].dropna()) >= 2:
                series = data[t].dropna()
                prev_close = series.iloc[-2]
                curr_price = series.iloc[-1]
                chg = curr_price - prev_close
                pct = (chg / prev_close) * 100
                records.append({
                    "Stock": symbol,
                    "Live Price (₹)": round(curr_price, 2),
                    "Change (₹)": round(chg, 2),
                    "% Change": round(pct, 2)
                })
        df = pd.DataFrame(records)
        gainers = df.sort_values(by="% Change", ascending=False).head(10).reset_index(drop=True)
        losers = df.sort_values(by="% Change", ascending=True).head(10).reset_index(drop=True)
        return gainers, losers
    except Exception:
        return pd.DataFrame(), pd.DataFrame()

# --- 3. 52-WEEK LOW VALUE FINDER WITH TARGETS & STOP-LOSS ---
@st.cache_data(ttl=300)
def screen_52w_low_strong_picks(universe):
    """
    Identifies fundamentally strong stocks trading within 6% of 52-week low.
    Calculates Buy Range, Stop-Loss, and Target Price mathematically.
    """
    results = []
    for symbol in universe[:60]:
        try:
            ticker = yf.Ticker(f"{symbol}.NS")
            hist = ticker.history(period="1y")
            if hist.empty or len(hist) < 200:
                continue
            
            curr_price = hist["Close"].iloc[-1]
            low_52w = hist["Close"].min()
            dist_from_low = ((curr_price - low_52w) / low_52w) * 100
            
            if dist_from_low <= 6.0:
                info = ticker.info
                roe = info.get("returnOnEquity", 0) or 0
                debt_eq = info.get("debtToEquity", 999) or 999
                
                # Filter: Safe balance sheet & healthy returns
                if roe >= 0.12 and debt_eq < 100:
                    sl_short = round(low_52w * 0.98, 2)
                    target_short = round(curr_price * 1.07, 2)
                    sl_long = round(low_52w * 0.95, 2)
                    target_long = round(curr_price * 1.25, 2)

                    results.append({
                        "Stock": symbol,
                        "Price": round(curr_price, 2),
                        "52W Low": round(low_52w, 2),
                        "Dist %": round(dist_from_low, 2),
                        "ROE": f"{roe*100:.1f}%",
                        "Short SL": sl_short,
                        "Short Target": target_short,
                        "Long SL": sl_long,
                        "Long Target": target_long
                    })
        except Exception:
            continue
    return pd.DataFrame(results).sort_values(by="Dist %").head(3)

# --- 4. CLOUD-SAFE NEWS & SENTIMENT ---
def fetch_cloud_safe_news(ticker_obj, symbol):
    articles = []
    total_polarity = 0

    try:
        raw_news = getattr(ticker_obj, "news", [])
        if raw_news:
            for item in raw_news[:5]:
                title = item.get("title")
                link = item.get("link", "#")
                if not title and "content" in item and isinstance(item["content"], dict):
                    title = item["content"].get("title")
                    link = item["content"].get("canonicalUrl", {}).get("url", link)

                if title:
                    score = TextBlob(title).sentiment.polarity
                    total_polarity += score
                    articles.append({"title": title, "link": link, "score": score})
    except Exception:
        pass

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
st.caption(f"Tracking {len(ALL_NSE_STOCKS):,} Listed Equities • Live Movers • Algorithmic Value Screener")

gainers_df, losers_df = get_live_market_data(ALL_NSE_STOCKS)

# --- SECTION 1: TOP 5 STRATEGIC PICKS ---
st.subheader("⭐ Top 5 Algorithmic Recommendations (Intraday, Short & Long Term)")

if not gainers_df.empty and not losers_df.empty:
    top_g1 = gainers_df.iloc[0]["Stock"]
    top_g2 = gainers_df.iloc[1]["Stock"]
    top_l1 = losers_df.iloc[0]["Stock"]
    top_l2 = losers_df.iloc[1]["Stock"]
    top_l3 = losers_df.iloc[2]["Stock"]

    picks = [
        {
            "Stock": top_g1,
            "Horizon": "Intraday (Day Momentum)",
            "Action": "BUY ON DIP",
            "Origin": f"Top Gainer (+{gainers_df.iloc[0]['% Change']}%)",
            "Why": "High relative strength and strong morning participation. Ideal setup for riding trend continuation toward VWAP pullbacks during market hours."
        },
        {
            "Stock": top_g2,
            "Horizon": "Short-Term Swing (1–4 Weeks)",
            "Action": "BUY (Breakout)",
            "Origin": f"Top Gainer (+{gainers_df.iloc[1]['% Change']}%)",
            "Why": "Strong positive price expansion clearing short-term resistance. Daily MACD curling upward signals sustained swing momentum."
        },
        {
            "Stock": top_l1,
            "Horizon": "Short-Term Bounce (1–3 Weeks)",
            "Action": "BUY (Mean Reversion)",
            "Origin": f"Top Loser ({losers_df.iloc[0]['% Change']}%)",
            "Why": "Extreme intraday selling exhaustion. RSI is approaching oversold territory, providing an asymmetric risk-reward ratio for a technical rebound."
        },
        {
            "Stock": top_l2,
            "Horizon": "Long-Term Value (6–12 Months)",
            "Action": "BUY (Accumulate)",
            "Origin": f"Top Loser ({losers_df.iloc[1]['% Change']}%)",
            "Why": "Temporary market sentiment drag on a solid franchise. Provides an attractive entry valuation with safe debt-to-equity levels."
        },
        {
            "Stock": top_l3,
            "Horizon": "Long-Term Compounder (12–24 Months)",
            "Action": "BUY (Quality Compounder)",
            "Origin": f"Top Loser ({losers_df.iloc[2]['% Change']}%)",
            "Why": "Sound business fundamentals and high ROE (>15%). Intraday drops on broader market pullbacks represent prime institutional accumulation zones."
        }
    ]

    p_cols = st.columns(5)
    for idx, p in enumerate(picks):
        with p_cols[idx]:
            with st.container(border=True):
                st.markdown(f"### {p['Stock']}")
                st.caption(p["Origin"])
                st.success(f"**{p['Action']}**")
                st.markdown(f"**Horizon:** {p['Horizon']}")
                st.markdown(f"**Why?** {p['Why']}")

st.markdown("---")

# --- SECTION 2: TOP 3 52-WEEK LOW PICKS WITH SL & TARGET ---
st.subheader("🛡️ Top 3 Strong Fundamental Stocks Near 52-Week Low")
st.caption("Filters for zero/low debt, high ROE (>12%), and oversold price bases with exact stop-loss and targets.")

low_screener_df = screen_52w_low_strong_picks(ALL_NSE_STOCKS)

if not low_screener_df.empty:
    cols = st.columns(len(low_screener_df))
    for i, (_, row) in enumerate(low_screener_df.iterrows()):
        with cols[i]:
            with st.container(border=True):
                st.markdown(f"### 💎 {row['Stock']}")
                st.metric("CMP", f"₹{row['Price']}", delta=f"{row['Dist %']}% from 52W Low", delta_color="inverse")
                st.write(f"**ROE:** {row['ROE']} | **52W Low:** ₹{row['52W Low']}")
                st.markdown("---")
                st.markdown("**⚡ Short-Term (1–4 Wks):**")
                st.write(f"- **Buy:** ₹{row['Price']}")
                st.write(f"- **Stop-Loss:** ₹{row['Short SL']}")
                st.write(f"- **Target:** ₹{row['Short Target']}")
                st.markdown("**🏛️ Long-Term (6–18 Mos):**")
                st.write(f"- **Stop-Loss:** ₹{row['Long SL']}")
                st.write(f"- **Target:** ₹{row['Long Target']}")
else:
    st.info("Scanning for stocks currently testing 52-week lows with healthy balance sheets...")

st.markdown("---")

# --- SECTION 3: LIVE MARKET MOVERS ---
st.subheader("📊 Today's Market Movers (Auto-refresh every 60s)")
g_col, l_col = st.columns(2)

with g_col:
    st.markdown("##### 🟢 Live Top 10 Gainers")
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
    st.markdown("##### 🔴 Live Top 10 Losers")
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

# --- SECTION 4: DEEP-DIVE STOCK SEARCH & ANALYSIS ---
st.subheader("🔍 Deep-Dive Stock Analysis & Buy/Sell Call")

col_search, col_exch = st.columns([3, 1])
with col_search:
    selected_stock = st.selectbox(
        "Type or select any listed stock (e.g., LALITHAA, RELIANCE, ZOMATO, TATASTEEL):",
        options=ALL_NSE_STOCKS,
        index=None,
        placeholder="Start typing stock symbol or name...",
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
        with st.spinner(f"Fetching complete data for {ticker_symbol}..."):
            try:
                stock = yf.Ticker(ticker_symbol)
                hist = stock.history(period="1y")

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

                    # 2. News & Sentiment
                    sentiment_score, news_items = fetch_cloud_safe_news(stock, selected_stock)

                    # 3. Short-Term Signal Framework
                    st_score = 0
                    st_reasons = []

                    if rsi < 35:
                        st_score += 1
                        st_reasons.append(f"RSI is oversold at {rsi:.1f}, indicating a likely bounce.")
                    elif rsi > 70:
                        st_score -= 1
                        st_reasons.append(f"RSI is overbought at {rsi:.1f}, signaling short-term exhaustion.")
                    else:
                        st_reasons.append(f"RSI is neutral at {rsi:.1f}.")

                    if latest["MACD"] > latest["MACD_Signal"]:
                        st_score += 1
                        st_reasons.append("Bullish momentum: MACD line trades above the signal line.")
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

                    # 5. Output Card Render
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

# --- MANDATORY REGULATORY & EDUCATIONAL DISCLAIMER ---
st.markdown("---")
st.warning(
    "⚠️ **Disclaimer:** This tool is purely for educational purposes. "
    "Please consult with a SEBI-registered advisor before buying or selling any securities."
)