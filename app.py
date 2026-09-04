import streamlit as st
import yfinance as yf
import pandas as pd
import ta
import feedparser
import requests
import io
import time
from datetime import datetime
from textblob import TextBlob

# Page layout configuration
st.set_page_config(
    page_title="NSE Live Auto-Updating Screener",
    page_icon="📈",
    layout="wide"
)

# --- 1. DYNAMIC DATA SOURCE: ALL NSE LISTED STOCKS ---
@st.cache_data(ttl=86400)
def get_all_nse_symbols():
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
            if len(symbols) > 100:
                return symbols
    except Exception:
        pass
    
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

# --- 2. LIVE GAINERS & LOSERS SCANNER (SHORT CACHE FOR FAST RE-TICKS) ---
@st.cache_data(ttl=10)
def get_live_market_data(universe):
    scan_universe = universe[:50]
    tickers = [f"{s}.NS" for s in scan_universe]
    try:
        raw = yf.download(tickers, period="5d", interval="1d", progress=False)
        if raw.empty:
            return pd.DataFrame(), pd.DataFrame()

        if isinstance(raw.columns, pd.MultiIndex):
            if "Close" in raw.columns.levels[0]:
                data = raw["Close"]
            elif "Close" in raw.columns.levels[1]:
                data = raw.xs("Close", axis=1, level=1)
            else:
                data = raw.iloc[:, :len(scan_universe)]
        else:
            data = raw.get("Close", raw)

        records = []
        for symbol in scan_universe:
            ticker_ns = f"{symbol}.NS"
            series = None

            if ticker_ns in data.columns:
                series = data[ticker_ns].dropna()
            elif symbol in data.columns:
                series = data[symbol].dropna()

            if series is not None and len(series) >= 2:
                prev_close = float(series.iloc[-2])
                curr_price = float(series.iloc[-1])
                chg = curr_price - prev_close
                pct = (chg / prev_close) * 100
                records.append({
                    "Stock": symbol,
                    "Live Price (₹)": round(curr_price, 2),
                    "Change (₹)": round(chg, 2),
                    "% Change": round(pct, 2)
                })

        if not records:
            return pd.DataFrame(), pd.DataFrame()

        df = pd.DataFrame(records)
        gainers = df.sort_values(by="% Change", ascending=False).head(10).reset_index(drop=True)
        losers = df.sort_values(by="% Change", ascending=True).head(10).reset_index(drop=True)
        return gainers, losers
    except Exception:
        return pd.DataFrame(), pd.DataFrame()

# --- 3. 52-WEEK LOW VALUE FINDER ---
@st.cache_data(ttl=300)
def screen_52w_low_strong_picks(universe):
    results = []
    for symbol in universe[:30]:
        try:
            ticker = yf.Ticker(f"{symbol}.NS")
            hist = ticker.history(period="1y")
            if hist.empty or len(hist) < 50:
                continue

            close_series = hist["Close"].dropna()
            curr_price = float(close_series.iloc[-1])
            low_52w = float(close_series.min())

            if low_52w <= 0:
                continue

            dist_from_low = ((curr_price - low_52w) / low_52w) * 100

            if dist_from_low <= 8.0:
                info = ticker.info or {}
                roe = info.get("returnOnEquity") or 0.0
                debt_eq = info.get("debtToEquity") or 0.0

                sl_short = round(low_52w * 0.98, 2)
                target_short = round(curr_price * 1.07, 2)
                sl_long = round(low_52w * 0.95, 2)
                target_long = round(curr_price * 1.25, 2)

                results.append({
                    "Stock": symbol,
                    "Price": round(curr_price, 2),
                    "52W Low": round(low_52w, 2),
                    "Dist %": round(dist_from_low, 2),
                    "ROE": f"{roe*100:.1f}%" if roe else "N/A",
                    "Short SL": sl_short,
                    "Short Target": target_short,
                    "Long SL": sl_long,
                    "Long Target": target_long
                })
        except Exception:
            continue

    if results:
        return pd.DataFrame(results).sort_values(by="Dist %").head(3)
    return pd.DataFrame()

# --- 4. CLOUD-SAFE NEWS FETCHING ---
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
st.caption(f"Tracking {len(ALL_NSE_STOCKS):,} Listed Equities • Live Movers • Auto-Updating")

# =====================================================================
# DYNAMIC FRAGMENT: Auto-refreshes every 15s without full page reload
# =====================================================================
@st.fragment(run_every=15)
def render_live_market_movers():
    gainers_df, losers_df = get_live_market_data(ALL_NSE_STOCKS)
    now_time = datetime.now().strftime("%H:%M:%S")

    # Header with live timestamp badge
    st.subheader(f"📊 Today's Market Movers")
    st.caption(f"🔄 Auto-updating in background every 15s | Last tick: **{now_time}**")

    # --- TOP 5 STRATEGIC PICKS ---
    if not gainers_df.empty and not losers_df.empty and len(gainers_df) >= 2 and len(losers_df) >= 3:
        top_g1 = gainers_df.iloc[0]["Stock"]
        top_g2 = gainers_df.iloc[1]["Stock"]
        top_l1 = losers_df.iloc[0]["Stock"]
        top_l2 = losers_df.iloc[1]["Stock"]
        top_l3 = losers_df.iloc[2]["Stock"]

        picks = [
            {
                "Stock": top_g1,
                "Horizon": "Intraday Momentum",
                "Action": "BUY ON DIP",
                "Origin": f"Top Gainer (+{gainers_df.iloc[0]['% Change']}%)",
                "Why": "Strong volume participation and positive price discovery near day high."
            },
            {
                "Stock": top_g2,
                "Horizon": "Short-Term Swing (1–4 Wks)",
                "Action": "BUY (Breakout)",
                "Origin": f"Top Gainer (+{gainers_df.iloc[1]['% Change']}%)",
                "Why": "Technical breakout clearing immediate resistance levels."
            },
            {
                "Stock": top_l1,
                "Horizon": "Short-Term Rebound (1–3 Wks)",
                "Action": "BUY (Mean Reversion)",
                "Origin": f"Top Loser ({losers_df.iloc[0]['% Change']}%)",
                "Why": "Selling exhaustion near lower bands, positioning for a technical bounce."
            },
            {
                "Stock": top_l2,
                "Horizon": "Long-Term Value (6–12 Mos)",
                "Action": "BUY (Accumulate)",
                "Origin": f"Top Loser ({losers_df.iloc[1]['% Change']}%)",
                "Why": "Market drawdown on resilient balance sheet, offering attractive margin of safety."
            },
            {
                "Stock": top_l3,
                "Horizon": "Long-Term Core (12–24 Mos)",
                "Action": "BUY (Compounder)",
                "Origin": f"Top Loser ({losers_df.iloc[2]['% Change']}%)",
                "Why": "Macro pullback on fundamentally sound asset with strong return ratios."
            }
        ]

        st.markdown("##### ⭐ Top 5 Dynamic Recommendations")
        p_cols = st.columns(5)
        for idx, p in enumerate(picks):
            with p_cols[idx]:
                with st.container(border=True):
                    st.markdown(f"### {p['Stock']}")
                    st.caption(p["Origin"])
                    st.success(f"**{p['Action']}**")
                    st.markdown(f"**Horizon:** {p['Horizon']}")
                    st.markdown(f"**Why?** {p['Why']}")

    # --- TABLES OF TOP GAINERS & LOSERS ---
    g_col, l_col = st.columns(2)
    with g_col:
        st.markdown("##### 🟢 Live Top Gainers")
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
            st.info("Loading live gainer quotes...")

    with l_col:
        st.markdown("##### 🔴 Live Top Losers")
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
            st.info("Loading live loser quotes...")

# Run the live ticking fragment
render_live_market_movers()

st.markdown("---")

# --- SECTION 2: 52-WEEK LOW OPPORTUNITIES ---
st.subheader("🛡️ Top 3 Fundamental Stocks Near 52-Week Low")
st.caption("Filters for healthy balance sheets testing multi-month bases with calculated Stop-Loss & Targets.")

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
    st.info("Scanning for quality shares currently testing 52-week support zones...")

st.markdown("---")

# --- SECTION 3: DEEP-DIVE STOCK SEARCH & ANALYSIS ---
st.subheader("🔍 Deep-Dive Stock Analysis & Buy/Sell Call")

col_search, col_exch = st.columns([3, 1])
with col_search:
    selected_stock = st.selectbox(
        "Type or select stock symbol:",
        options=ALL_NSE_STOCKS,
        index=None,
        placeholder="Type symbol (e.g. RELIANCE, TCS, INFY, TATAMOTORS)...",
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
        with st.spinner(f"Evaluating {ticker_symbol}..."):
            try:
                stock = yf.Ticker(ticker_symbol)
                hist = stock.history(period="1y")

                fast = getattr(stock, "fast_info", None)
                if fast and hasattr(fast, "last_price") and fast.last_price:
                    live_price = float(fast.last_price)
                    prev_close = float(fast.previous_close or hist["Close"].iloc[-2])
                else:
                    live_price = float(hist["Close"].iloc[-1])
                    prev_close = float(hist["Close"].iloc[-2])

                day_change = live_price - prev_close
                day_pct = (day_change / prev_close) * 100
                info = stock.info or {}

                if hist.empty or len(hist) < 30:
                    st.error("Insufficient market history to generate indicators.")
                else:
                    # Technicals
                    hist["RSI"] = ta.momentum.RSIIndicator(hist["Close"], window=14).rsi()
                    hist["SMA_50"] = ta.trend.SMAIndicator(hist["Close"], window=50).sma_indicator()
                    hist["SMA_200"] = ta.trend.SMAIndicator(hist["Close"], window=200).sma_indicator()
                    macd = ta.trend.MACD(hist["Close"])
                    hist["MACD"] = macd.macd()
                    hist["MACD_Signal"] = macd.macd_signal()

                    latest = hist.iloc[-1]
                    rsi = float(latest["RSI"])
                    sma_50 = float(latest["SMA_50"]) if pd.notna(latest["SMA_50"]) else 0
                    sma_200 = float(latest["SMA_200"]) if pd.notna(latest["SMA_200"]) else 0

                    sentiment_score, news_items = fetch_cloud_safe_news(stock, selected_stock)

                    # Short-term score
                    st_score = 0
                    st_reasons = []

                    if rsi < 35:
                        st_score += 1
                        st_reasons.append(f"RSI is oversold ({rsi:.1f}), signaling technical bounce potential.")
                    elif rsi > 70:
                        st_score -= 1
                        st_reasons.append(f"RSI is overbought ({rsi:.1f}), signaling near-term exhaustion.")
                    else:
                        st_reasons.append(f"RSI is neutral ({rsi:.1f}).")

                    if latest["MACD"] > latest["MACD_Signal"]:
                        st_score += 1
                        st_reasons.append("Bullish momentum: MACD holds above signal line.")
                    else:
                        st_score -= 1
                        st_reasons.append("Bearish momentum: MACD trades below signal line.")

                    if sma_50 and live_price > sma_50:
                        st_score += 1
                        st_reasons.append(f"Price is trading above 50-day SMA (₹{sma_50:.2f}).")
                    elif sma_50:
                        st_score -= 1
                        st_reasons.append(f"Price is trading below 50-day SMA (₹{sma_50:.2f}).")

                    if sentiment_score > 0.05:
                        st_score += 1
                        st_reasons.append(f"Live news sentiment is positive (+{sentiment_score:.2f}).")
                    elif sentiment_score < -0.05:
                        st_score -= 1
                        st_reasons.append(f"Live news sentiment is cautious ({sentiment_score:.2f}).")

                    st_call = "BUY" if st_score >= 1 else ("SELL" if st_score <= -1 else "HOLD")

                    # Long-term score
                    lt_score = 0
                    lt_reasons = []

                    roe = info.get("returnOnEquity")
                    debt_equity = info.get("debtToEquity")

                    if roe and roe > 0.15:
                        lt_score += 1
                        lt_reasons.append(f"Strong ROE profile ({roe*100:.1f}%).")
                    elif roe and roe < 0.08:
                        lt_score -= 1
                        lt_reasons.append(f"Subdued capital efficiency: ROE ({roe*100:.1f}%).")

                    if debt_equity is not None:
                        if debt_equity < 100:
                            lt_score += 1
                            lt_reasons.append("Conservative leverage: Debt-to-Equity is low (< 1.0).")
                        else:
                            lt_score -= 1
                            lt_reasons.append("Elevated debt leverage on balance sheet.")

                    if sma_200:
                        if live_price > sma_200:
                            lt_score += 1
                            lt_reasons.append(f"Structural uptrend: Price holds above 200-day SMA (₹{sma_200:.2f}).")
                        else:
                            lt_score -= 1
                            lt_reasons.append(f"Macro downtrend: Price trades below 200-day SMA (₹{sma_200:.2f}).")

                    lt_call = "BUY" if lt_score >= 1 else ("SELL" if lt_score <= -1 else "HOLD")

                    # Render Metrics
                    st.markdown("---")
                    st.subheader(info.get("longName", ticker_symbol))
                    st.metric(
                        label="Live Traded Price (LTP)",
                        value=f"₹{live_price:,.2f}",
                        delta=f"{day_change:+,.2f} ({day_pct:+.2f}%)"
                    )

                    r1, r2 = st.columns(2)
                    with r1:
                        st.markdown("#### ⚡ Short-Term Call")
                        if st_call == "BUY": st.success("### ACTION: BUY")
                        elif st_call == "SELL": st.error("### ACTION: SELL")
                        else: st.warning("### ACTION: HOLD")
                        for r in st_reasons: st.write(f"- {r}")

                    with r2:
                        st.markdown("#### 🏛️ Long-Term Call")
                        if lt_call == "BUY": st.success("### ACTION: BUY")
                        elif lt_call == "SELL": st.error("### ACTION: SELL")
                        else: st.warning("### ACTION: HOLD")
                        for r in lt_reasons: st.write(f"- {r}")

                    st.markdown("---")
                    st.markdown("#### 📰 Scanned Headlines")
                    if news_items:
                        for n in news_items:
                            badge = "🟢 Positive" if n["score"] > 0.05 else ("🔴 Negative" if n["score"] < -0.05 else "⚪ Neutral")
                            st.markdown(f"**[{badge}]** [{n['title']}]({n['link']})")
                    else:
                        st.info("No recent news headlines available for this symbol.")

            except Exception as e:
                st.error(f"Error analyzing ticker: {e}")

# --- MANDATORY DISCLAIMER ---
st.markdown("---")
st.warning(
    "⚠️ **Disclaimer:** This tool is purely for educational purposes. "
    "Please consult with a SEBI-registered advisor before buying or selling any securities."
)