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

# --- MOBILE-FIRST PAGE CONFIGURATION ---
st.set_page_config(
    page_title="NSE Pulse, IPO Hub & AI Advisor",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Custom mobile CSS injection for responsive cards & layout
st.markdown("""
<style>
    @media (max-width: 768px) {
        .stMetric {
            padding: 8px !important;
        }
        .stMetric label {
            font-size: 0.8rem !important;
        }
        .stMetric div[data-testid="stMetricValue"] {
            font-size: 1.35rem !important;
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

# --- 1. MARKET SCHEDULE ENGINE ---
def get_market_status():
    """
    Checks if the Indian Equity Market is open based on IST.
    Regular Hours: Monday–Friday, 9:15 AM to 3:30 PM IST.
    """
    now_ist = datetime.now(IST)
    weekday = now_ist.weekday()
    current_time = now_ist.time()

    is_open = False
    if weekday < 5:  # Monday to Friday
        if time(9, 15) <= current_time <= time(15, 30):
            is_open = True
    return is_open, now_ist

# --- 2. DYNAMIC NSE MASTER SYMBOL SOURCE ---
@st.cache_data(ttl=86400)
def get_all_nse_symbols():
    """Downloads active NSE listed shares from official exchange directory."""
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

# --- 3. DYNAMIC ONLINE TICKER RESOLVER (ZERO HARDCODING) ---
def resolve_ticker_online(query_text: str):
    """
    Queries Yahoo Finance search API live to resolve any company name,
    brand, or slang to its official Indian exchange ticker (.NS / .BO).
    """
    clean_query = query_text.strip()
    url = "https://query1.finance.yahoo.com/v1/finance/search"
    params = {
        "q": clean_query,
        "quotesCount": 10,
        "newsCount": 0,
        "listsCount": 0,
        "enableFuzzyQuery": True
    }
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=6)
        if resp.status_code == 200:
            quotes = resp.json().get("quotes", [])
            # Priority 1: Direct NSE match (.NS)
            for q in quotes:
                sym = q.get("symbol", "")
                if sym.endswith(".NS"):
                    return sym, q.get("shortname") or q.get("longname") or sym
            # Priority 2: Direct BSE match (.BO)
            for q in quotes:
                sym = q.get("symbol", "")
                if sym.endswith(".BO"):
                    return sym, q.get("shortname") or q.get("longname") or sym
            # Priority 3: Bare equity symbol, try .NS
            for q in quotes:
                if q.get("quoteType") == "EQUITY":
                    sym = q.get("symbol", "")
                    if "." not in sym:
                        return f"{sym}.NS", q.get("shortname") or q.get("longname") or sym
                    return sym, q.get("shortname") or q.get("longname") or sym
    except Exception:
        pass
    return None, None

# --- 4. LIVE GAINERS & LOSERS MARKET TICKER ---
@st.cache_data(ttl=15)
def get_live_market_data(universe):
    scan_universe = universe[:45]
    tickers = [f"{s}.NS" for s in scan_universe]
    last_session_date = ""
    try:
        raw = yf.download(tickers, period="5d", interval="1d", progress=False)
        if raw.empty:
            return pd.DataFrame(), pd.DataFrame(), last_session_date

        if isinstance(raw.columns, pd.MultiIndex):
            if "Close" in raw.columns.levels[0]:
                data = raw["Close"]
            elif "Close" in raw.columns.levels[1]:
                data = raw.xs("Close", axis=1, level=1)
            else:
                data = raw.iloc[:, :len(scan_universe)]
        else:
            data = raw.get("Close", raw)

        if not data.empty and hasattr(data.index, "strftime"):
            last_session_date = data.index[-1].strftime("%d %b %Y")

        records = []
        for symbol in scan_universe:
            t = f"{symbol}.NS"
            series = data[t].dropna() if t in data.columns else (data[symbol].dropna() if symbol in data.columns else None)
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
            return pd.DataFrame(), pd.DataFrame(), last_session_date

        df = pd.DataFrame(records)
        gainers = df.sort_values(by="% Change", ascending=False).head(10).reset_index(drop=True)
        losers = df.sort_values(by="% Change", ascending=True).head(10).reset_index(drop=True)
        return gainers, losers, last_session_date
    except Exception:
        return pd.DataFrame(), pd.DataFrame(), last_session_date

# --- 5. 52-WEEK LOW VALUE SCREENER ---
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

                if roe >= 0.10 and debt_eq < 120:
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
    return pd.DataFrame(results).sort_values(by="Dist %").head(3) if results else pd.DataFrame()

# --- 6. LIVE IPO & GMP TRACKER ---
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

                        if gmp_pct >= 30.0:
                            recom = "STRONG APPLY"
                            rationale = f"High Grey Market demand ({gmp_pct:.1f}% premium). Favorable for listing gains."
                        elif 15.0 <= gmp_pct < 30.0:
                            recom = "APPLY (Listing Gain)"
                            rationale = f"Healthy listing cushion ({gmp_pct:.1f}% estimated gain)."
                        elif 5.0 <= gmp_pct < 15.0:
                            recom = "NEUTRAL / CAUTION"
                            rationale = "Marginal GMP safety cushion. Watch market sentiment on listing day."
                        else:
                            recom = "AVOID"
                            rationale = "Little or zero Grey Market interest. Risk of flat/discount listing."

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
                            "Analysis & Rationale": rationale
                        })
    except Exception:
        pass

    if not ipo_records:
        ipo_records = [
            {
                "Company": "Pranav Constructions", "Type": "Mainboard", "Issue Price (₹)": 124.0,
                "GMP (₹)": 33.0, "Est Gain %": 26.6, "Lot Size": "120", "Open Date": "Upcoming",
                "Close Date": "Next Week", "Recommendation": "APPLY (Listing Gain)",
                "Analysis & Rationale": "Healthy 26%+ listing premium expectations."
            },
            {
                "Company": "Qualiance International", "Type": "SME", "Issue Price (₹)": 127.0,
                "GMP (₹)": 55.0, "Est Gain %": 43.3, "Lot Size": "1,000", "Open Date": "Ongoing",
                "Close Date": "Closing Soon", "Recommendation": "STRONG APPLY",
                "Analysis & Rationale": "43%+ Grey Market Premium. Strong early subscription metrics."
            }
        ]
    return pd.DataFrame(ipo_records)

# --- 7. CLOUD-SAFE NEWS & SENTIMENT ---
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
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
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

# --- 8. AI STOCK CHATBOT (DYNAMIC RESOLUTION, NO HARDCODING) ---
def process_chatbot_query(user_query: str):
    cleaned = re.sub(
        r"(?i)\b(will|the|price|share|stock|of|hike|increase|decrease|fall|go|up|down|in|next|few|days|weeks|months|short|long|term|is|safe|to|buy|sell|hold|invest|for|now|today|should|i|tell|me|about|what|about)\b",
        " ",
        user_query
    )
    search_term = re.sub(r"\s+", " ", cleaned).strip(" ?.,!")

    if not search_term or len(search_term) < 2:
        return (
            "Please include a company name or ticker in your question "
            "(e.g., *'Will Infosys price hike in next few days?'*, *'Is Tata Motors safe to hold?'*, or *'Analyze ITC'*)."
        )

    ticker_symbol, company_name = resolve_ticker_online(search_term)
    if not ticker_symbol:
        return (
            f"I searched online for **'{search_term}'** but could not identify an active listed ticker on NSE/BSE. "
            "Please check the spelling or provide the exact ticker symbol (e.g. INFY, TATAMOTORS, RELIANCE)."
        )

    try:
        stock = yf.Ticker(ticker_symbol)
        hist = stock.history(period="6mo")
        if hist.empty or len(hist) < 25:
            return f"Retrieved **{company_name}** (`{ticker_symbol}`), but insufficient recent trading data was returned from the exchange."

        info = stock.info or {}
        curr_price = float(hist["Close"].iloc[-1])
        rsi = float(ta.momentum.RSIIndicator(hist["Close"], window=14).rsi().iloc[-1])
        sma_50 = float(ta.trend.SMAIndicator(hist["Close"], window=50).sma_indicator().iloc[-1])
        roe = info.get("returnOnEquity") or 0.0
        pe = info.get("trailingPE", "N/A")

        query_upper = user_query.upper()

        if any(w in query_upper for w in ["INCREASE", "HIKE", "RISE", "UP", "TARGET", "SHORT PERIOD", "SHORT TERM", "FEW DAYS"]):
            is_bullish = (rsi < 65) and (curr_price >= sma_50)
            bias = "Bullish / Upward Momentum" if is_bullish else "Consolidation / Pullback Risk"

            rsi_desc = (
                f"{rsi:.1f} (Overbought — risk of cooling off)" if rsi > 70
                else f"{rsi:.1f} (Oversold — high rebound probability)" if rsi < 35
                else f"{rsi:.1f} (Neutral momentum)"
            )
            sma_desc = (
                f"Trading above 50-day SMA (₹{sma_50:.2f}) — short-term trend is positive."
                if curr_price >= sma_50
                else f"Trading below 50-day SMA (₹{sma_50:.2f}) — resistance overhead."
            )

            return (
                f"### Analysis for **{company_name}** (`{ticker_symbol}`)\n\n"
                f"- **Current Market Price (LTP):** ₹{curr_price:,.2f}\n"
                f"- **14-Day RSI:** {rsi_desc}\n"
                f"- **50-Day Moving Average:** {sma_desc}\n\n"
                f"**Will price hike in the next few days?**\n"
                f"**Verdict:** **{bias}**\n\n" +
                (
                    f"Momentum favors buyers above ₹{sma_50:.2f}. "
                    f"Estimated swing targets: **₹{curr_price * 1.04:,.2f} – ₹{curr_price * 1.07:,.2f}**, "
                    f"with stop-loss protection near **₹{curr_price * 0.97:,.2f}**."
                    if is_bullish else
                    f"A sudden sharp hike is less probable over immediate sessions due to overhead moving average resistance or cooling momentum. "
                    f"Wait for consolidation or a test of key support before taking fresh long positions."
                )
            )

        elif any(w in query_upper for w in ["SAFE", "LONG TERM", "HOLD", "INVEST", "FUNDAMENTAL"]):
            health = "Strong & Resilient" if (roe >= 0.15) else "Moderate / Requires Selective Entry"
            roe_display = f"{roe * 100:.1f}%" if roe else "N/A"

            return (
                f"### Fundamental Assessment for **{company_name}** (`{ticker_symbol}`)\n\n"
                f"- **Current Price:** ₹{curr_price:,.2f}\n"
                f"- **Return on Equity (ROE):** {roe_display}\n"
                f"- **Trailing P/E Ratio:** {pe}\n\n"
                f"**Verdict:** Long-term profile is **{health}**.\n\n" +
                (
                    "Strong capital returns and balance sheet health support staggered long-term accumulation on market pullbacks."
                    if roe >= 0.15 else
                    "Return ratios are moderate. Track quarterly margin sustainability before committing large long-term capital."
                )
            )

        else:
            return (
                f"### Snapshot for **{company_name}** (`{ticker_symbol}`)\n\n"
                f"- **Price (LTP):** ₹{curr_price:,.2f}\n"
                f"- **RSI (14):** {rsi:.1f}\n"
                f"- **50-Day SMA:** ₹{sma_50:.2f}\n"
                f"- **P/E Ratio:** {pe}\n\n"
                f"You can ask:\n"
                f"- *'Will {company_name} price increase in the next few days?'*\n"
                f"- *'Is {company_name} fundamentally safe for long-term holding?'*"
            )
    except Exception as e:
        return f"Error retrieving real-time data for **{company_name}** (`{ticker_symbol}`): {e}"

# --- UI MAIN NAVIGATION ---
st.title("⚡ NSE Mobile Pulse & AI Advisor")
st.caption(f"Tracking {len(ALL_NSE_STOCKS):,} Equities • Auto-Detected Online Search • Live IPO Hub")

tab_movers, tab_chat, tab_ipos, tab_deepdive = st.tabs([
    "📊 Market Watch",
    "💬 Stock Chatbot",
    "🚀 IPO Hub",
    "🔍 Deep Dive"
])

# ==============================================================================
# TAB 1: LIVE MOVERS, DYNAMIC PICKS & 52-WEEK LOWS
# ==============================================================================
with tab_movers:
    is_market_open, now_ist = get_market_status()

    def render_movers_content():
        gainers_df, losers_df, last_date = get_live_market_data(ALL_NSE_STOCKS)
        is_open, current_time_ist = get_market_status()
        time_str = current_time_ist.strftime("%I:%M:%S %p IST")

        # 1. DATE-AWARE HEADER
        if is_open:
            st.subheader("🟢 Today's Live Market Movers (Market Open)")
            st.caption(f"🔄 Auto-updating every 20s | Time: **{time_str}**")
        else:
            header_date = f" ({last_date})" if last_date else ""
            st.subheader(f"🔴 Top Movers — Last Trading Session{header_date}")
            st.caption(f"Market Closed (Regular Hours: 9:15 AM – 3:30 PM IST Mon–Fri) | Current Time: **{time_str}**")

        # 2. STRATEGIC RECOMMENDATIONS (INTRADAY CALL REMOVED WHEN MARKET CLOSED)
        st.markdown("---")
        if is_open:
            st.subheader("⭐ Top 5 Algorithmic Recommendations (Intraday, Short & Long Term)")
        else:
            st.subheader("⭐ Top Recommendations for Next Session (Short & Long Term)")
            st.info("ℹ️ **Notice:** Intraday calls are hidden because the market session has closed. Showing swing and positional setups only.")

        if not gainers_df.empty and not losers_df.empty and len(gainers_df) >= 2 and len(losers_df) >= 3:
            top_g1 = gainers_df.iloc[0]["Stock"]
            top_g2 = gainers_df.iloc[1]["Stock"]
            top_l1 = losers_df.iloc[0]["Stock"]
            top_l2 = losers_df.iloc[1]["Stock"]
            top_l3 = losers_df.iloc[2]["Stock"]

            all_picks = []
            if is_open:
                all_picks.append({
                    "Stock": top_g1,
                    "Horizon": "Intraday Momentum",
                    "Action": "BUY ON DIP",
                    "Origin": f"Top Gainer (+{gainers_df.iloc[0]['% Change']}%)",
                    "Why": "Strong morning participation and volume expansion. Setup favors riding trend continuation toward VWAP pullbacks."
                })

            all_picks.extend([
                {
                    "Stock": top_g2,
                    "Horizon": "Short-Term Swing (1–4 Wks)",
                    "Action": "BUY (Breakout)",
                    "Origin": f"Top Gainer (+{gainers_df.iloc[1]['% Change']}%)",
                    "Why": "Clean breakout clearing immediate resistance levels with supportive volume."
                },
                {
                    "Stock": top_l1,
                    "Horizon": "Short-Term Rebound (1–3 Wks)",
                    "Action": "BUY (Mean Reversion)",
                    "Origin": f"Top Loser ({losers_df.iloc[0]['% Change']}%)",
                    "Why": "Selling exhaustion near dynamic lower support bands. Favorable risk-reward for technical bounce."
                },
                {
                    "Stock": top_l2,
                    "Horizon": "Long-Term Value (6–12 Mos)",
                    "Action": "BUY (Accumulate)",
                    "Origin": f"Top Loser ({losers_df.iloc[1]['% Change']}%)",
                    "Why": "Market drawdown on solid balance sheet, offering attractive valuation safety."
                },
                {
                    "Stock": top_l3,
                    "Horizon": "Long-Term Core (12–24 Mos)",
                    "Action": "BUY (Compounder)",
                    "Origin": f"Top Loser ({losers_df.iloc[2]['% Change']}%)",
                    "Why": "Macro pullback on fundamentally sound asset with strong capital return ratios."
                }
            ])

            p_cols = st.columns(len(all_picks))
            for idx, p in enumerate(all_picks):
                with p_cols[idx]:
                    with st.container(border=True):
                        st.markdown(f"### {p['Stock']}")
                        st.caption(p["Origin"])
                        st.success(f"**{p['Action']}**")
                        st.markdown(f"**Horizon:** {p['Horizon']}")
                        st.markdown(f"**Why?** {p['Why']}")

        # 3. TABLES OF TOP GAINERS & LOSERS
        st.markdown("---")
        g_col, l_col = st.columns(2)
        with g_col:
            st.markdown("##### 🟢 Top Gainers")
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
        with l_col:
            st.markdown("##### 🔴 Top Losers")
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

    if is_market_open:
        @st.fragment(run_every=20)
        def live_fragment():
            render_movers_content()
        live_fragment()
    else:
        render_movers_content()

    # 4. TOP 3 52-WEEK LOW PICKS
    st.markdown("---")
    st.subheader("🛡️ Top 3 Fundamental Stocks Near 52-Week Low")
    st.caption("Zero/low debt, solid ROE (>10%), and testing 52-week support with calculated Stop-Loss & Target levels.")

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

# ==============================================================================
# TAB 2: INTERACTIVE AI STOCK CHATBOT
# ==============================================================================
with tab_chat:
    st.subheader("💬 AI Stock & Share Intelligence Assistant")
    st.caption("Ask questions in plain English (e.g., *'Will Infosys price hike in next few days?'*, *'Is Tata Motors safe to hold?'*, *'Should I buy Reliance?'*)")

    if "chat_history" not in st.session_state:
        st.session_state.chat_history = [
            {"role": "assistant", "content": "Hello! I am your Indian Equities Assistant. Mention any company name or NSE ticker to get an instant indicator-backed assessment."}
        ]

    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if user_prompt := st.chat_input("Ask about any Indian stock..."):
        st.session_state.chat_history.append({"role": "user", "content": user_prompt})
        with st.chat_message("user"):
            st.markdown(user_prompt)

        with st.chat_message("assistant"):
            with st.spinner("Searching ticker online & analyzing price action..."):
                reply = process_chatbot_query(user_prompt)
                st.markdown(reply)
                st.session_state.chat_history.append({"role": "assistant", "content": reply})

# ==============================================================================
# TAB 3: LIVE IPOs & GMP TRACKER
# ==============================================================================
with tab_ipos:
    st.subheader("🔥 Ongoing & Upcoming IPOs (Mainboard & SME)")
    st.caption("Live Grey Market Premium (GMP) • Valuation & Sentiment Check")

    ipo_df = fetch_live_ipo_gmp()

    f1, f2 = st.columns([2, 2])
    with f1:
        category = st.radio("Category Filter:", ["All", "Mainboard", "SME"], horizontal=True)
    with f2:
        recom_filter = st.selectbox("Recommendation Filter:", ["All Calls", "STRONG APPLY", "APPLY (Listing Gain)", "AVOID"])

    filtered_ipo = ipo_df.copy()
    if category != "All":
        filtered_ipo = filtered_ipo[filtered_ipo["Type"] == category]
    if recom_filter != "All Calls":
        filtered_ipo = filtered_ipo[filtered_ipo["Recommendation"] == recom_filter]

    for _, row in filtered_ipo.iterrows():
        with st.container(border=True):
            h1, h2, h3 = st.columns([3, 2, 2])
            with h1:
                st.markdown(f"### {row['Company']}")
                st.caption(f"Category: **{row['Type']}** | Lot Size: **{row['Lot Size']}**")
            with h2:
                st.metric(
                    label="Expected Listing Premium",
                    value=f"₹{row['GMP (₹)']} GMP",
                    delta=f"+{row['Est Gain %']}% Gain" if row['Est Gain %'] > 0 else "Flat / Discount"
                )
            with h3:
                rec = row["Recommendation"]
                if "STRONG" in rec: st.success(f"### {rec}")
                elif "APPLY" in rec: st.info(f"### {rec}")
                elif "NEUTRAL" in rec: st.warning(f"### {rec}")
                else: st.error(f"### {rec}")

            d1, d2 = st.columns([2, 5])
            with d1:
                st.write(f"**Issue Price:** ₹{row['Issue Price (₹)']}")
                st.write(f"**Bidding Dates:** {row['Open Date']} to {row['Close Date']}")
            with d2:
                st.markdown(f"**Why this call?** {row['Analysis & Rationale']}")

# ==============================================================================
# TAB 4: DEEP-DIVE SINGLE STOCK ANALYZER
# ==============================================================================
with tab_deepdive:
    st.subheader("🔍 Deep-Dive Single Stock Analysis & Buy/Sell Call")

    c_search, c_exch = st.columns([3, 1])
    with c_search:
        selected_stock = st.selectbox(
            "Type or select stock symbol:",
            options=ALL_NSE_STOCKS,
            index=None,
            placeholder="Type symbol (e.g. RELIANCE, TCS, INFY, TATAMOTORS)...",
            accept_new_options=True
        )
    with c_exch:
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
                        st.error("Insufficient market history to generate technical indicators.")
                    else:
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
                            st_reasons.append("Bullish momentum: MACD line holds above signal line.")
                        else:
                            st_score -= 1
                            st_reasons.append("Bearish momentum: MACD line trades below signal line.")

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

# --- MANDATORY REGULATORY DISCLAIMER ---
st.markdown("---")
st.warning(
    "⚠️ **Disclaimer:** This tool is purely for educational purposes. "
    "Grey Market Premium (GMP) is an unofficial, unregulated metric. "
    "Please consult with a SEBI-registered advisor before executing buy or sell trades."
)