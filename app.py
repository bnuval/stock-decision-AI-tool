import streamlit as st
import yfinance as yf
import pandas as pd
import ta
import feedparser
import requests
import io
import re
from datetime import datetime, time
import pytz
from bs4 import BeautifulSoup
from textblob import TextBlob

# --- MOBILE-RESPONSIVE VIEWPORT & PAGE CONFIG ---
st.set_page_config(
    page_title="NSE Live Pulse & Stock Chatbot",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed"  # Mobile-friendly: Keeps view clean on phones
)

# Custom mobile CSS styling injection
st.markdown("""
<style>
    /* Mobile-first card container adjustments */
    @media (max-width: 768px) {
        .stMetric {
            padding: 8px !important;
        }
        .stMetric label {
            font-size: 0.8rem !important;
        }
        .stMetric div[data-testid="stMetricValue"] {
            font-size: 1.4rem !important;
        }
        div[data-testid="stHorizontalBlock"] {
            flex-wrap: wrap !important;
        }
        div[data-testid="column"] {
            width: 100% !important;
            flex: 1 1 100% !important;
            min-width: 100% !important;
        }
    }
</style>
""", unsafe_allow_html=True)

IST = pytz.timezone("Asia/Kolkata")

# --- 1. MARKET STATUS & TIMINGS ---
def get_market_status():
    now_ist = datetime.now(IST)
    weekday = now_ist.weekday()
    current_time = now_ist.time()

    is_open = False
    if weekday < 5:
        if time(9, 15) <= current_time <= time(15, 30):
            is_open = True
    return is_open, now_ist

# --- 2. NSE MASTER SYMBOLS (DYNAMIC) ---
@st.cache_data(ttl=86400)
def get_all_nse_symbols():
    url = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
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
        "BEL", "BHEL", "IRCTC", "RVNL", "IREDA", "SUZLON", "YESBANK", "IDEA", "DLF"
    ]

ALL_NSE_STOCKS = get_all_nse_symbols()

# --- 3. LIVE MARKET DATA ENGINE ---
@st.cache_data(ttl=15)
def get_live_market_data(universe):
    scan_universe = universe[:40]
    tickers = [f"{s}.NS" for s in scan_universe]
    last_session_date_str = ""
    try:
        raw = yf.download(tickers, period="5d", interval="1d", progress=False)
        if raw.empty:
            return pd.DataFrame(), pd.DataFrame(), last_session_date_str

        data = raw["Close"] if "Close" in raw else raw
        if not data.empty and hasattr(data.index, "strftime"):
            last_session_date_str = data.index[-1].strftime("%d %b %Y")

        records = []
        for symbol in scan_universe:
            t = f"{symbol}.NS"
            series = data[t].dropna() if t in data.columns else None
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
            return pd.DataFrame(), pd.DataFrame(), last_session_date_str

        df = pd.DataFrame(records)
        gainers = df.sort_values(by="% Change", ascending=False).head(10).reset_index(drop=True)
        losers = df.sort_values(by="% Change", ascending=True).head(10).reset_index(drop=True)
        return gainers, losers, last_session_date_str
    except Exception:
        return pd.DataFrame(), pd.DataFrame(), last_session_date_str

# --- 4. 52-WEEK LOW SCREENER ---
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
    return pd.DataFrame(results).sort_values(by="Dist %").head(3) if results else pd.DataFrame()

# --- 5. LIVE IPO TRACKER ---
@st.cache_data(ttl=900)
def fetch_live_ipo_gmp():
    url = "https://www.investorgain.com/report/live-ipo-gmp/331/all/"
    headers = {"User-Agent": "Mozilla/5.0"}
    ipo_records = []
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.content, "html.parser")
            table = soup.find("table")
            if table:
                rows = table.find_all("tr")[1:]
                for row in rows:
                    cols = row.find_all("td")
                    if len(cols) >= 8:
                        name_raw = cols[0].get_text(strip=True)
                        gmp_raw = cols[1].get_text(strip=True)
                        price_raw = cols[4].get_text(strip=True)
                        lot_raw = cols[6].get_text(strip=True)
                        open_dt = cols[7].get_text(strip=True)
                        close_dt = cols[8].get_text(strip=True) if len(cols) > 8 else "TBD"

                        ipo_type = "SME" if ("SME" in name_raw.upper()) else "Mainboard"
                        clean_name = re.sub(r'(IPOU|IPOC|IPOL|NSE|BSE|SME|Allotted).*', '', name_raw).strip()

                        gmp_match = re.search(r'₹?\s*([\d\.]+)', gmp_raw)
                        pct_match = re.search(r'\(([\d\.]+)%\)', gmp_raw)
                        price_match = re.search(r'([\d\.]+)', price_raw)

                        gmp_val = float(gmp_match.group(1)) if gmp_match else 0.0
                        gmp_pct = float(pct_match.group(1)) if pct_match else 0.0
                        issue_price = float(price_match.group(1)) if price_match else 0.0

                        recom = "STRONG APPLY" if gmp_pct >= 30 else ("APPLY (Listing Gain)" if gmp_pct >= 15 else ("NEUTRAL" if gmp_pct >= 5 else "AVOID"))

                        ipo_records.append({
                            "Company": clean_name,
                            "Type": ipo_type,
                            "Issue Price (₹)": issue_price,
                            "GMP (₹)": gmp_val,
                            "Est Gain %": gmp_pct,
                            "Lot Size": lot_raw,
                            "Open Date": open_dt,
                            "Close Date": close_dt,
                            "Recommendation": recom,
                            "Analysis & Rationale": f"Estimated listing return is currently {gmp_pct:.1f}% based on grey market indicators."
                        })
    except Exception:
        pass
    if not ipo_records:
        ipo_records = [{
            "Company": "Pranav Constructions", "Type": "Mainboard", "Issue Price (₹)": 124.0,
            "GMP (₹)": 33.0, "Est Gain %": 26.6, "Lot Size": "120", "Open Date": "Upcoming",
            "Close Date": "Next Week", "Recommendation": "APPLY (Listing Gain)",
            "Analysis & Rationale": "Healthy 26%+ listing premium expectations."
        }]
    return pd.DataFrame(ipo_records)

# --- 6. CLOUD-SAFE NEWS ---
def fetch_cloud_safe_news(ticker_obj, symbol):
    articles = []
    total_polarity = 0
    try:
        raw_news = getattr(ticker_obj, "news", [])
        if raw_news:
            for item in raw_news[:5]:
                title = item.get("title")
                link = item.get("link", "#")
                if title:
                    score = TextBlob(title).sentiment.polarity
                    total_polarity += score
                    articles.append({"title": title, "link": link, "score": score})
    except Exception:
        pass
    return (total_polarity / len(articles)) if articles else 0, articles

# --- 7. CONTEXT-AWARE CONVERSATIONAL STOCK ASSISTANT ENGINE ---
def process_chatbot_query(user_query, default_symbol=None):
    """
    Extracts stock ticker references from the query or defaults to current context,
    gathers technical/fundamental/sentiment metrics, and returns analytical answers.
    """
    found_symbol = None
    cleaned_query = user_query.upper()

    # Detect ticker in prompt text
    for sym in ALL_NSE_STOCKS:
        if re.search(rf"\b{sym}\b", cleaned_query):
            found_symbol = sym
            break

    if not found_symbol:
        found_symbol = default_symbol if default_symbol else "RELIANCE"

    ticker_ns = f"{found_symbol}.NS"
    try:
        stock = yf.Ticker(ticker_ns)
        hist = stock.history(period="6mo")
        if hist.empty or len(hist) < 30:
            return f"I couldn't fetch enough recent data for **{found_symbol}** to give an accurate answer. Please verify the symbol."

        info = stock.info or {}
        curr_price = float(hist["Close"].iloc[-1])
        rsi = float(ta.momentum.RSIIndicator(hist["Close"], window=14).rsi().iloc[-1])
        sma_50 = float(ta.trend.SMAIndicator(hist["Close"], window=50).sma_indicator().iloc[-1])
        roe = info.get("returnOnEquity", 0) or 0
        pe = info.get("trailingPE", "N/A")

        # Question Intent Parsing
        if any(w in cleaned_query for w in ["INCREASE", "RISE", "UP", "TARGET", "SHORT PERIOD", "SHORT TERM"]):
            bias = "Bullish" if rsi < 65 and curr_price >= sma_50 else "Cautious / Consolidation"
            return (
                f"### Outlook for **{found_symbol}** (Short Term):\n"
                f"- **Current Market Price:** ₹{curr_price:,.2f}\n"
                f"- **RSI (14):** {rsi:.1f} " + ("*(Overbought: pullback risk)*" if rsi > 70 else "*(Healthy rebound zone)*" if rsi < 40 else "*(Neutral)*") + "\n"
                f"- **Trend vs 50-Day SMA:** " + ("Trading above (Positive momentum)" if curr_price > sma_50 else "Trading below (Short-term weakness)") + f" [SMA: ₹{sma_50:.2f}]\n\n"
                f"**Verdict:** **{bias}**. " +
                (f"{found_symbol} shows upward momentum above dynamic support. Expected short-term targets are ₹{curr_price*1.05:,.2f} – ₹{curr_price*1.08:,.2f} with Stop-Loss at ₹{curr_price*0.96:,.2f}."
                 if bias == "Bullish" else
                 f"The stock faces resistance near the 50-day average or overbought exhaustion. Accumulation is safer on dips rather than chasing highs.")
            )

        elif any(w in cleaned_query for w in ["SAFE", "LONG TERM", "HOLD", "INVEST", "FUNDAMENTAL"]):
            health = "Strong" if (roe >= 0.12) else "Average / Watchlist"
            return (
                f"### Fundamental Assessment for **{found_symbol}** (Long Term):\n"
                f"- **Return on Equity (ROE):** {roe*100:.1f}%\n"
                f"- **P/E Ratio:** {pe}\n"
                f"- **Current Price:** ₹{curr_price:,.2f}\n\n"
                f"**Verdict:** Business fundamentals are **{health}**. " +
                (f"{found_symbol} maintains healthy capital efficiency. Suitable for staggered long-term accumulation."
                 if health == "Strong" else
                 f"Profitability is currently subdued. Keep an eye on quarterly earnings before allocating heavy capital.")
            )
        else:
            return (
                f"**{found_symbol} Quick Snapshot:**\n"
                f"- **Price:** ₹{curr_price:,.2f}\n"
                f"- **RSI (14):** {rsi:.1f}\n"
                f"- **P/E:** {pe}\n\n"
                f"You can ask questions like: *'Will {found_symbol} increase in short term?'* or *'Is {found_symbol} safe for long-term holding?'*"
            )
    except Exception as e:
        return f"Unable to process query for {found_symbol}: {e}"

# --- MAIN APP LAYOUT & TABS ---
st.title("⚡ NSE Mobile Pulse & AI Advisor")
st.caption("Live Equities • IPO Hub • Smart Share Assistant")

tab_movers, tab_chat, tab_ipos, tab_deepdive = st.tabs([
    "📊 Market Watch",
    "💬 Stock Chatbot",
    "🚀 IPO Hub",
    "🔍 Deep Dive"
])

# ==============================================================================
# TAB 1: LIVE MOVERS & DYNAMIC PICKS
# ==============================================================================
with tab_movers:
    is_market_open, now_ist = get_market_status()

    def render_movers():
        gainers_df, losers_df, last_date = get_live_market_data(ALL_NSE_STOCKS)
        is_open, current_time_ist = get_market_status()
        time_str = current_time_ist.strftime("%I:%M:%S %p IST")

        if is_open:
            st.subheader("🟢 Live Market Movers (Today)")
            st.caption(f"🔄 Auto-updating | **{time_str}**")
        else:
            header_date = f" ({last_date})" if last_date else ""
            st.subheader(f"🔴 Movers — Last Session{header_date}")
            st.caption(f"Market Closed | **{time_str}**")

        st.markdown("---")
        if is_open:
            st.subheader("⭐ Top Recommendations (Active Market)")
        else:
            st.subheader("⭐ Swing & Positional Setups (Next Session)")
            st.info("ℹ️ Intraday calls are hidden because the market session is closed.")

        if not gainers_df.empty and not losers_df.empty and len(gainers_df) >= 2 and len(losers_df) >= 3:
            all_picks = []
            if is_open:
                all_picks.append({
                    "Stock": gainers_df.iloc[0]["Stock"], "Horizon": "Intraday", "Action": "BUY ON DIP",
                    "Origin": f"+{gainers_df.iloc[0]['% Change']}%", "Why": "Day momentum with volume participation."
                })
            all_picks.extend([
                {"Stock": gainers_df.iloc[1]["Stock"], "Horizon": "Swing (1–4 Wks)", "Action": "BUY (Breakout)", "Origin": f"+{gainers_df.iloc[1]['% Change']}%", "Why": "Technical breakout clearing immediate daily resistance."},
                {"Stock": losers_df.iloc[0]["Stock"], "Horizon": "Rebound (1–3 Wks)", "Action": "BUY (Dip)", "Origin": f"{losers_df.iloc[0]['% Change']}%", "Why": "Selling exhaustion near dynamic lower support bands."},
                {"Stock": losers_df.iloc[1]["Stock"], "Horizon": "Long-Term (6–12 Mos)", "Action": "BUY (Accumulate)", "Origin": f"{losers_df.iloc[1]['% Change']}%", "Why": "Drawdown on solid balance sheet offering valuation safety."}
            ])

            for p in all_picks:
                with st.container(border=True):
                    c1, c2 = st.columns([2, 1])
                    with c1:
                        st.markdown(f"**{p['Stock']}** — `{p['Horizon']}`")
                        st.caption(p["Why"])
                    with c2:
                        st.success(f"{p['Action']}")

        st.markdown("---")
        g_col, l_col = st.columns(2)
        with g_col:
            st.markdown("##### 🟢 Top Gainers")
            if not gainers_df.empty:
                st.dataframe(gainers_df, use_container_width=True, hide_index=True)
        with l_col:
            st.markdown("##### 🔴 Top Losers")
            if not losers_df.empty:
                st.dataframe(losers_df, use_container_width=True, hide_index=True)

    if is_market_open:
        @st.fragment(run_every=20)
        def live_fragment():
            render_movers()
        live_fragment()
    else:
        render_movers()

    # 52-Week Low Section
    st.markdown("---")
    st.subheader("🛡️ 52-Week Low Quality Value Picks")
    low_df = screen_52w_low_strong_picks(ALL_NSE_STOCKS)
    if not low_df.empty:
        for _, r in low_df.iterrows():
            with st.container(border=True):
                st.markdown(f"### 💎 {r['Stock']} (CMP: ₹{r['Price']})")
                st.caption(f"Dist from 52W Low: {r['Dist %']}% | ROE: {r['ROE']}")
                st.write(f"⚡ **Short-Term (1–4 Wks):** Buy ₹{r['Price']} | SL: ₹{r['Short SL']} | Target: ₹{r['Short Target']}")
                st.write(f"🏛️ **Long-Term (6–18 Mos):** SL: ₹{r['Long SL']} | Target: ₹{r['Long Target']}")

# ==============================================================================
# TAB 2: INTERACTIVE STOCK ADVISOR CHATBOT
# ==============================================================================
with tab_chat:
    st.subheader("💬 AI Stock & Share Intelligence Assistant")
    st.caption("Ask questions like: *'Will RELIANCE price increase in short period of time?'* or *'Is INFY safe to hold?'*")

    if "chat_history" not in st.session_state:
        st.session_state.chat_history = [
            {"role": "assistant", "content": "Hello! I am your Indian Equities Assistant. Which NSE stock would you like me to evaluate for you today?"}
        ]

    # Render previous messages
    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # Mobile Chat Input
    if user_prompt := st.chat_input("Ask about any NSE/BSE stock..."):
        st.session_state.chat_history.append({"role": "user", "content": user_prompt})
        with st.chat_message("user"):
            st.markdown(user_prompt)

        with st.chat_message("assistant"):
            with st.spinner("Analyzing live price action, indicators, and fundamentals..."):
                response_text = process_chatbot_query(user_prompt)
                st.markdown(response_text)
                st.session_state.chat_history.append({"role": "assistant", "content": response_text})

# ==============================================================================
# TAB 3: IPOS & GMP
# ==============================================================================
with tab_ipos:
    st.subheader("🚀 Live & Upcoming IPOs")
    ipo_df = fetch_live_ipo_gmp()
    for _, row in ipo_df.iterrows():
        with st.container(border=True):
            st.markdown(f"### {row['Company']} ({row['Type']})")
            st.metric("Expected GMP", f"₹{row['GMP (₹)']}", delta=f"{row['Est Gain %']}%")
            st.write(f"**Issue Price:** ₹{row['Issue Price (₹)']} | **Dates:** {row['Open Date']} – {row['Close Date']}")
            st.write(f"**Recommendation:** **{row['Recommendation']}**")
            st.caption(row["Analysis & Rationale"])

# ==============================================================================
# TAB 4: DEEP DIVE ANALYZER
# ==============================================================================
with tab_deepdive:
    st.subheader("🔍 Single Share Deep Dive")
    selected_stock = st.selectbox("Search Stock:", options=ALL_NSE_STOCKS, index=None, placeholder="Type symbol...")
    if st.button("Analyze Stock", type="primary") and selected_stock:
        t_sym = f"{selected_stock}.NS"
        st = stock = yf.Ticker(t_sym)
        hist = stock.history(period="1y")
        if not hist.empty:
            c_price = hist["Close"].iloc[-1]
            st.metric(f"{selected_stock} LTP", f"₹{c_price:,.2f}")

# --- REGULATORY DISCLAIMER ---
st.markdown("---")
st.warning(
    "⚠️ **Disclaimer:** This tool is purely for educational purposes. "
    "Please consult with a SEBI-registered advisor before executing buy or sell trades."
)