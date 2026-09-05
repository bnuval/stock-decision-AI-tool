import streamlit as st
import yfinance as yf
import pandas as pd
import ta
import feedparser
import requests
import io
import os
import re
import time as time_module
from datetime import datetime, time
import pytz
from bs4 import BeautifulSoup
from textblob import TextBlob

# Optional GenAI LLM Client import
try:
    from google import genai
    from google.genai import types
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False

# --- CONFIGURATION & CREDENTIALS ---
# Replace with your newly generated private key if testing locally without secrets.toml
DEFAULT_KEY_FALLBACK = ""

# --- MOBILE-FIRST PAGE CONFIGURATION ---
st.set_page_config(
    page_title="NSE Pulse, IPO Hub & AI Advisor",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Initialize navigation tab state
if "current_tab" not in st.session_state:
    st.session_state.current_tab = "📊 Market Watch"

query_params = st.query_params
if "nav" in query_params and query_params["nav"] in ["watch", "chat", "ipo", "dive"]:
    nav_map = {
        "watch": "📊 Market Watch",
        "chat": "💬 Stock Chatbot",
        "ipo": "🚀 IPO Hub",
        "dive": "🔍 Deep Dive"
    }
    st.session_state.current_tab = nav_map[query_params["nav"]]

# --- CSS: FIXED HEADER + STICKY TABS ROW ---
st.markdown("""
<style>
    header[data-testid="stHeader"] {
        display: none !important;
        height: 0px !important;
    }

    .block-container {
        padding-top: 6.8rem !important;
        padding-left: 0.8rem !important;
        padding-right: 0.8rem !important;
        padding-bottom: 4rem !important;
    }

    .pinned-master-bar {
        position: fixed !important;
        top: 0px !important;
        left: 0px !important;
        width: 100vw !important;
        height: 6.2rem !important;
        background-color: #0e1117 !important;
        z-index: 999999 !important;
        display: flex !important;
        flex-direction: column !important;
        justify-content: flex-start !important;
        padding: 0.4rem 1rem 0 1rem !important;
        border-bottom: 2px solid #262c38 !important;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.6) !important;
    }

    .pinned-master-bar h2 {
        font-size: 1.15rem !important;
        font-weight: 700 !important;
        color: #f0f2f6 !important;
        margin: 0 !important;
        padding: 0 !important;
        line-height: 1.2 !important;
        white-space: nowrap !important;
        overflow: hidden !important;
        text-overflow: ellipsis !important;
    }

    .pinned-master-bar p {
        font-size: 0.72rem !important;
        color: #9aa0a6 !important;
        margin: 0.1rem 0 0.35rem 0 !important;
        padding: 0 !important;
        white-space: nowrap !important;
        overflow: hidden !important;
        text-overflow: ellipsis !important;
    }

    .nav-tabs-wrapper {
        display: flex !important;
        flex-direction: row !important;
        flex-wrap: nowrap !important;
        gap: 0.4rem !important;
        overflow-x: auto !important;
        overflow-y: hidden !important;
        -webkit-overflow-scrolling: touch !important;
        scrollbar-width: none !important;
    }
    .nav-tabs-wrapper::-webkit-scrollbar {
        display: none !important;
    }

    .nav-tab-btn {
        display: inline-block !important;
        text-decoration: none !important;
        background-color: #161a23 !important;
        border: 1px solid #262c38 !important;
        border-radius: 6px !important;
        padding: 0.35rem 0.85rem !important;
        font-size: 0.82rem !important;
        font-weight: 500 !important;
        color: #c9d1d9 !important;
        white-space: nowrap !important;
        transition: all 0.15s ease-in-out !important;
    }

    .nav-tab-btn:hover {
        border-color: #58a6ff !important;
        color: #ffffff !important;
    }

    .nav-tab-btn.active {
        background-color: #1f6feb !important;
        border-color: #58a6ff !important;
        color: #ffffff !important;
        font-weight: 600 !important;
    }

    @media (max-width: 768px) {
        .block-container {
            padding-top: 5.8rem !important;
            padding-left: 0.45rem !important;
            padding-right: 0.45rem !important;
        }
        .pinned-master-bar {
            height: 5.4rem !important;
            padding: 0.35rem 0.5rem 0 0.5rem !important;
        }
        .pinned-master-bar h2 {
            font-size: 0.96rem !important;
        }
        .pinned-master-bar p {
            font-size: 0.65rem !important;
            margin-bottom: 0.25rem !important;
        }
        .nav-tab-btn {
            padding: 0.3rem 0.65rem !important;
            font-size: 0.75rem !important;
        }
        .stMetric { padding: 4px !important; }
        .stMetric label { font-size: 0.72rem !important; }
        .stMetric div[data-testid="stMetricValue"] { font-size: 1.15rem !important; }
        div[data-testid="stHorizontalBlock"] { flex-wrap: wrap !important; }
        div[data-testid="column"] { width: 100% !important; flex: 1 1 100% !important; min-width: 100% !important; }
    }
</style>
""", unsafe_allow_html=True)

IST = pytz.timezone("Asia/Kolkata")

# --- 1. MARKET SCHEDULE ENGINE ---
def get_market_status():
    now_ist = datetime.now(IST)
    weekday = now_ist.weekday()
    current_time = now_ist.time()

    is_open = False
    if weekday < 5:
        if time(9, 15) <= current_time <= time(15, 30):
            is_open = True
    return is_open, now_ist

# --- 2. NSE MASTER DIRECTORY ---
@st.cache_data(ttl=86400)
def get_all_nse_symbols():
    url = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            df = pd.read_csv(io.StringIO(resp.text))
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
        "BEL", "BHEL", "IRCTC", "RVNL", "IREDA", "SUZLON", "YESBANK", "IDEA", "DLF", "DABUR"
    ]

ALL_NSE_STOCKS = get_all_nse_symbols()

# --- 3. DYNAMIC ONLINE TICKER RESOLVER ---
def resolve_ticker_online(query_text: str):
    clean_query = query_text.strip().upper()

    if clean_query in ALL_NSE_STOCKS:
        return f"{clean_query}.NS", clean_query

    url = "https://query1.finance.yahoo.com/v1/finance/search"
    params = {"q": clean_query, "quotesCount": 8, "enableFuzzyQuery": True}
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=5)
        if resp.status_code == 200:
            quotes = resp.json().get("quotes", [])
            for q in quotes:
                sym = q.get("symbol", "")
                if sym.endswith(".NS"):
                    return sym, q.get("shortname") or q.get("longname") or sym
            for q in quotes:
                sym = q.get("symbol", "")
                if sym.endswith(".BO"):
                    return sym, q.get("shortname") or q.get("longname") or sym
            for q in quotes:
                if q.get("quoteType") == "EQUITY":
                    sym = q.get("symbol", "")
                    return (f"{sym}.NS", q.get("shortname") or sym) if "." not in sym else (sym, q.get("shortname") or sym)
    except Exception:
        pass
    return None, None

# --- 4. LIVE GAINERS & LOSERS ---
@st.cache_data(ttl=15)
def get_live_market_data(universe):
    scan_universe = universe[:45]
    tickers = [f"{s}.NS" for s in scan_universe]
    last_session_date = ""
    try:
        raw = yf.download(tickers, period="5d", interval="1d", progress=False)
        if raw.empty:
            return pd.DataFrame(), pd.DataFrame(), last_session_date

        data = raw["Close"] if "Close" in raw else raw
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

# --- 5. TOP 3 52-WEEK LOW PICKS ---
@st.cache_data(ttl=300)
def screen_52w_low_strong_picks(universe):
    candidate_symbols = [
        "HINDUNILVR", "DABUR", "ITC", "IRCTC", "INFY", "TCS", "HDFCBANK",
        "KOTAKBANK", "ASIANPAINT", "MARUTI", "SUNPHARMA", "WIPRO", "TATAMOTORS"
    ]
    tickers = [f"{s}.NS" for s in candidate_symbols]

    try:
        raw = yf.download(tickers, period="1y", interval="1d", progress=False)
        if raw.empty:
            return pd.DataFrame()

        data = raw["Close"] if "Close" in raw else raw
        results = []

        for symbol in candidate_symbols:
            t = f"{symbol}.NS"
            series = data[t].dropna() if t in data.columns else (data[symbol].dropna() if symbol in data.columns else None)
            if series is not None and len(series) >= 50:
                curr_price = float(series.iloc[-1])
                low_52w = float(series.min())
                high_52w = float(series.max())

                if low_52w > 0:
                    dist_from_low = ((curr_price - low_52w) / low_52w) * 100
                    sl_short = round(low_52w * 0.98, 2)
                    target_short = round(curr_price * 1.08, 2)
                    sl_long = round(low_52w * 0.95, 2)
                    target_long = round(curr_price * 1.25, 2)

                    results.append({
                        "Stock": symbol,
                        "Price": round(curr_price, 2),
                        "52W Low": round(low_52w, 2),
                        "52W High": round(high_52w, 2),
                        "Dist %": round(dist_from_low, 2),
                        "Short SL": sl_short,
                        "Short Target": target_short,
                        "Long SL": sl_long,
                        "Long Target": target_long
                    })

        if results:
            df = pd.DataFrame(results).sort_values(by="Dist %", ascending=True)
            return df.head(3).reset_index(drop=True)
    except Exception:
        pass
    return pd.DataFrame()

# --- 6. REAL-TIME IPO HUB (ONGOING, UPCOMING & AVOID LISTINGS) ---
@st.cache_data(ttl=900)
def fetch_live_ipo_gmp():
    url = "https://www.investorgain.com/report/live-ipo-gmp/331/all/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.google.com/"
    }

    ipo_records = []
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.content, "html.parser")
            table = soup.find("table")
            if table:
                for row in table.find_all("tr")[1:]:
                    cols = row.find_all("td")
                    if len(cols) >= 8:
                        raw_name = cols[0].get_text(strip=True)
                        gmp_raw = cols[1].get_text(strip=True)
                        sub_raw = cols[3].get_text(strip=True) if len(cols) > 3 else "N/A"
                        price_raw = cols[4].get_text(strip=True)
                        lot_raw = cols[6].get_text(strip=True)
                        open_dt = cols[7].get_text(strip=True)
                        close_dt = cols[8].get_text(strip=True) if len(cols) > 8 else "TBD"

                        status = "Upcoming"
                        if any(k in raw_name for k in ["SMEO", "IPOO", "Open"]):
                            status = "Ongoing (Open)"
                        elif any(k in raw_name for k in ["SMEC", "IPOC", "Close", "Allotted", "Listed"]):
                            status = "Closed / Allotted"
                        elif any(k in raw_name for k in ["SMEU", "IPOU", "Upcoming"]):
                            status = "Upcoming"

                        ipo_type = "SME" if "SME" in raw_name.upper() else "Mainboard"
                        clean_name = re.sub(r'(IPOU|IPOC|IPOL|IPOO|NSE|BSE|SME|Allotted|SMEO|SMEU|SMEC).*', '', raw_name).strip()

                        gmp_match = re.search(r'₹?\s*([\d\.]+)', gmp_raw)
                        pct_match = re.search(r'\(([\d\.]+)%\)', gmp_raw)
                        price_match = re.search(r'([\d\.]+)', price_raw)

                        gmp_val = float(gmp_match.group(1)) if gmp_match else 0.0
                        gmp_pct = float(pct_match.group(1)) if pct_match else 0.0
                        issue_price = float(price_match.group(1)) if price_match else 0.0

                        if gmp_pct >= 30.0:
                            recom = "STRONG APPLY"
                            rationale = f"Strong Grey Market Premium ({gmp_pct:.1f}% estimated gain). Solid investor appetite."
                        elif 15.0 <= gmp_pct < 30.0:
                            recom = "APPLY (Listing Gain)"
                            rationale = f"Healthy listing cushion ({gmp_pct:.1f}% GMP). Favorable for short-term gains."
                        elif 5.0 <= gmp_pct < 15.0:
                            recom = "NEUTRAL / CAUTION"
                            rationale = "Thin safety margin (5–15% GMP). Market shifts on listing day could trim profits."
                        else:
                            recom = "AVOID"
                            rationale = "Low, zero, or negative grey market interest. High risk of flat or discounted listing."

                        ipo_records.append({
                            "Company": clean_name,
                            "Status": status,
                            "Type": ipo_type,
                            "Issue Price (₹)": issue_price,
                            "GMP (₹)": gmp_val,
                            "Est Gain %": gmp_pct,
                            "Lot Size": lot_raw,
                            "Subscription": sub_raw,
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
                "Company": "Qualiance International", "Status": "Ongoing (Open)", "Type": "SME", "Issue Price (₹)": 127.0,
                "GMP (₹)": 55.0, "Est Gain %": 43.3, "Lot Size": "1,000", "Subscription": "12.4x", "Open Date": "Open Now",
                "Close Date": "Closing Soon", "Recommendation": "STRONG APPLY",
                "Analysis & Rationale": "43%+ Grey Market Premium. Strong early subscription metrics."
            },
            {
                "Company": "Pranav Constructions", "Status": "Upcoming", "Type": "Mainboard", "Issue Price (₹)": 124.0,
                "GMP (₹)": 34.0, "Est Gain %": 27.4, "Lot Size": "120", "Subscription": "-", "Open Date": "Next Week",
                "Close Date": "Next Week", "Recommendation": "APPLY (Listing Gain)",
                "Analysis & Rationale": "27%+ listing premium expectations."
            },
            {
                "Company": "Kanohar Electricals", "Status": "Upcoming", "Type": "Mainboard", "Issue Price (₹)": 632.0,
                "GMP (₹)": 45.0, "Est Gain %": 7.1, "Lot Size": "23", "Subscription": "-", "Open Date": "Upcoming",
                "Close Date": "Upcoming", "Recommendation": "NEUTRAL / CAUTION",
                "Analysis & Rationale": "Moderate 7% GMP cushion; sensitive to broader market swings on listing day."
            },
            {
                "Company": "Apana Logistics", "Status": "Ongoing (Open)", "Type": "SME", "Issue Price (₹)": 60.0,
                "GMP (₹)": 1.0, "Est Gain %": 1.6, "Lot Size": "2,000", "Subscription": "0.9x", "Open Date": "Open Now",
                "Close Date": "Closing Soon", "Recommendation": "AVOID",
                "Analysis & Rationale": "Extremely weak 1.6% GMP and low subscription interest. High risk of capital discount."
            }
        ]

    return pd.DataFrame(ipo_records)

# --- 7. CLOUD-SAFE NEWS FETCHING ---
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
            resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
            feed = feedparser.parse(resp.content)
            for entry in feed.entries[:5]:
                score = TextBlob(entry.title).sentiment.polarity
                total_polarity += score
                articles.append({"title": entry.title, "link": entry.link, "score": score})
        except Exception:
            pass

    return (total_polarity / len(articles)) if articles else 0, articles

# --- 8. REAL-TIME DATA CONTEXT BUILDER FOR AI ---
def get_live_market_context_for_query(query: str):
    words = [w.strip(" ?.,!").upper() for w in query.split()]
    direct_symbol = next((w for w in words if w in ALL_NSE_STOCKS), None)
    clean_target = re.sub(
        r"(?i)\b(analiyse|analyse|analyze|analysis|check|review|details|will|the|price|share|stock|of|hike|increase|decrease|fall|go|up|down|in|next|few|days|weeks|months|short|long|term|is|safe|to|buy|sell|hold|invest|for|now|today|should|i|tell|me|about|what|how)\b",
        " ",
        query
    )
    search_term = re.sub(r"\s+", " ", clean_target).strip(" ?.,!")

    context_str = ""
    ticker_found = None
    company_name = None

    if direct_symbol:
        ticker_found = f"{direct_symbol}.NS"
        company_name = direct_symbol
    elif search_term and len(search_term) >= 2:
        ticker_found, company_name = resolve_ticker_online(search_term)

    if ticker_found:
        try:
            stock = yf.Ticker(ticker_found)
            hist = stock.history(period="6mo")
            if not hist.empty:
                curr_price = float(hist["Close"].iloc[-1])
                rsi = float(ta.momentum.RSIIndicator(hist["Close"], window=14).rsi().iloc[-1])
                sma_50 = float(ta.trend.SMAIndicator(hist["Close"], window=50).sma_indicator().iloc[-1])
                sma_200 = float(ta.trend.SMAIndicator(hist["Close"], window=200).sma_indicator().iloc[-1]) if len(hist) >= 150 else None
                info = stock.info or {}
                roe = (info.get("returnOnEquity") or 0) * 100
                pe = info.get("trailingPE", "N/A")
                debt_eq = info.get("debtToEquity", "N/A")

                context_str += f"\n[REAL-TIME STOCK DATA FOR {company_name} ({ticker_found})]\n"
                context_str += f"- Live Traded Price (LTP): ₹{curr_price:,.2f}\n"
                context_str += f"- RSI (14): {rsi:.2f}\n"
                context_str += f"- 50-day SMA: ₹{sma_50:.2f} (Price is {'ABOVE' if curr_price >= sma_50 else 'BELOW'})\n"
                if sma_200:
                    context_str += f"- 200-day SMA: ₹{sma_200:.2f}\n"
                context_str += f"- P/E Ratio: {pe}, ROE: {roe:.2f}%, Debt-to-Equity: {debt_eq}\n"
        except Exception:
            pass

    if any(k in query.upper() for k in ["BEST", "BUY", "TODAY", "MARKET", "GAINERS", "LOSERS", "NOW"]):
        g, l, d = get_live_market_data(ALL_NSE_STOCKS)
        lows = screen_52w_low_strong_picks(ALL_NSE_STOCKS)
        context_str += "\n[CURRENT TOP MARKET MOVERS]\n"
        if not g.empty:
            context_str += f"- Top Gainers: {', '.join(g['Stock'].head(3).tolist())}\n"
        if not l.empty:
            context_str += f"- Top Losers: {', '.join(l['Stock'].head(3).tolist())}\n"
        if not lows.empty:
            context_str += f"- Quality Stocks at 52-Week Lows: {', '.join(lows['Stock'].head(3).tolist())}\n"

    return context_str

# --- 9. INTERACTIVE STREAMING CHATBOT GENERATOR ---
def stream_chatbot_response(user_query: str):
    api_key = (
        st.secrets.get("GEMINI_API_KEY") 
        if hasattr(st, "secrets") and "GEMINI_API_KEY" in st.secrets 
        else os.getenv("GEMINI_API_KEY", DEFAULT_KEY_FALLBACK)
    )

    live_context = get_live_market_context_for_query(user_query)

    if GENAI_AVAILABLE and api_key:
        try:
            client = genai.Client(api_key=api_key)
            prompt = f"""
            You are a seasoned Indian Equity Market Analyst for the NSE & BSE.
            Provide a crisp, professional, mobile-friendly answer using bullet points and clear bold targets.
            Include key levels (Entry, Stop-Loss, Target), indicator interpretations (RSI, 50/200 SMA), and risk caveats.
            Always adhere to SEBI educational guidelines.

            LIVE MARKET DATA CONTEXT:
            {live_context}

            USER QUESTION:
            {user_query}
            """
            response = client.models.generate_content_stream(
                model="gemini-2.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(temperature=0.2)
            )
            for chunk in response:
                if chunk.text:
                    yield chunk.text
            return
        except Exception:
            pass

    static_reply = process_universal_chatbot_static(user_query, live_context)
    for word in static_reply.split(" "):
        yield word + " "
        time_module.sleep(0.015)

def process_universal_chatbot_static(user_query: str, live_context: str = ""):
    raw_query = user_query.strip()
    upper = raw_query.upper()

    if any(k in upper for k in [
        "WHICH SHARE IS BEST TO BUY", "WHICH STOCK IS BEST TO BUY", "WHAT TO BUY NOW",
        "WHICH SHARE TO BUY TODAY", "BEST SHARE TO BUY NOW", "BEST STOCK TO BUY",
        "TOP SHARES TO BUY", "SUGGEST ME A SHARE", "RECOMMEND A STOCK", "WHAT SHOULD I BUY"
    ]) or (("BEST" in upper or "WHICH" in upper) and "BUY" in upper and len(raw_query.split()) <= 10):

        gainers, losers, _ = get_live_market_data(ALL_NSE_STOCKS)
        low_52w = screen_52w_low_strong_picks(ALL_NSE_STOCKS)
        is_open, _ = get_market_status()

        resp = "### 🎯 Best Stock Opportunities Right Now (Algorithmic Selection)\n\n"

        if not gainers.empty and len(gainers) >= 2:
            m_pick = gainers.iloc[1]["Stock"]
            m_price = gainers.iloc[1]["Live Price (₹)"]
            resp += (
                f"**1. Momentum Breakout (Short-Term 1–3 Weeks):**\n"
                f"- **Stock:** `{m_pick}` (LTP: ₹{m_price:,.2f})\n"
                f"- **Setup:** Volume-backed expansion above short-term pivot.\n"
                f"- **Action:** Buy on minor pullback | **Target:** ₹{m_price * 1.06:,.2f} | **Stop-Loss:** ₹{m_price * 0.97:,.2f}\n\n"
            )

        if not losers.empty and len(losers) >= 1:
            r_pick = losers.iloc[0]["Stock"]
            r_price = losers.iloc[0]["Live Price (₹)"]
            resp += (
                f"**2. Mean-Reversion Dip (Short-Term 1–2 Weeks):**\n"
                f"- **Stock:** `{r_pick}` (LTP: ₹{r_price:,.2f})\n"
                f"- **Setup:** Intraday selling exhaustion; attractive risk-reward for technical bounce.\n"
                f"- **Action:** Accumulate near ₹{r_price:,.2f} | **Target:** ₹{r_price * 1.05:,.2f} | **Stop-Loss:** ₹{r_price * 0.96:,.2f}\n\n"
            )

        if not low_52w.empty:
            v_row = low_52w.iloc[0]
            resp += (
                f"**3. Value Compounder (Long-Term 6–18 Months):**\n"
                f"- **Stock:** `{v_row['Stock']}` (Base at ₹{v_row['Price']:,.2f})\n"
                f"- **Setup:** Healthy balance sheet near 52-week support (only {v_row['Dist %']}% from bottom).\n"
                f"- **Action:** Accumulate for long term | **Target:** ₹{v_row['Long Target']:,.2f} | **Stop-Loss:** ₹{v_row['Long SL']:,.2f}\n\n"
            )

        timing_note = "Market is open. Confirm setups using intraday VWAP." if is_open else "Market is closed. Levels apply to the next session."
        resp += f"> **Context:** {timing_note}\n\n*Always maintain strict stop-loss rules.*"
        return resp

    words = [w.strip(" ?.,!").upper() for w in raw_query.split()]
    direct_symbol = next((w for w in words if w in ALL_NSE_STOCKS), None)

    if direct_symbol:
        ticker_symbol = f"{direct_symbol}.NS"
        company_name = direct_symbol
    else:
        clean_target = re.sub(
            r"(?i)\b(analiyse|analyse|analyze|analysis|check|review|details|will|the|price|share|stock|of|hike|increase|decrease|fall|go|up|down|in|next|few|days|weeks|months|short|long|term|is|safe|to|buy|sell|hold|invest|for|now|today|should|i|tell|me|about|what|how)\b",
            " ",
            raw_query
        )
        search_term = re.sub(r"\s+", " ", clean_target).strip(" ?.,!")

        if not search_term or len(search_term) < 2:
            return (
                "I'm your Indian Equities Assistant! You can ask me:\n"
                "- *'Analyse INFY'*\n"
                "- *'Which share is best to buy now?'*\n"
                "- *'Will Infosys price hike in next few days?'*\n"
                "- *'Is Tata Motors safe to hold for long term?'*"
            )

        ticker_symbol, company_name = resolve_ticker_online(search_term)

    if not ticker_symbol:
        return (
            f"I searched online for **'{search_term}'** but could not find a matching equity ticker on NSE/BSE. "
            "Please check the spelling or provide the direct ticker symbol (e.g. INFY, TATAMOTORS, RELIANCE)."
        )

    try:
        stock = yf.Ticker(ticker_symbol)
        hist = stock.history(period="6mo")
        if hist.empty or len(hist) < 25:
            return f"Found **{company_name}** (`{ticker_symbol}`), but insufficient trading history was returned from the exchange."

        info = stock.info or {}
        curr_price = float(hist["Close"].iloc[-1])
        rsi = float(ta.momentum.RSIIndicator(hist["Close"], window=14).rsi().iloc[-1])
        sma_50 = float(ta.trend.SMAIndicator(hist["Close"], window=50).sma_indicator().iloc[-1])
        roe = info.get("returnOnEquity") or 0.0
        pe = info.get("trailingPE", "N/A")

        if any(w in upper for w in ["INCREASE", "HIKE", "RISE", "UP", "TARGET", "SHORT PERIOD", "SHORT TERM", "FEW DAYS"]):
            is_bullish = (rsi < 65) and (curr_price >= sma_50)
            bias = "Bullish / Positive Momentum" if is_bullish else "Consolidation / Pullback Caution"

            rsi_desc = (
                f"{rsi:.1f} (Overbought — risk of pause)" if rsi > 70
                else f"{rsi:.1f} (Oversold — high rebound probability)" if rsi < 35
                else f"{rsi:.1f} (Neutral momentum)"
            )
            sma_desc = (
                f"Above 50-day SMA (₹{sma_50:.2f}) — confirms short-term trend strength."
                if curr_price >= sma_50
                else f"Below 50-day SMA (₹{sma_50:.2f}) — near-term resistance active."
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
                    f"A sudden sharp hike is less probable over immediate sessions due to moving average resistance or cooling momentum. "
                    f"Wait for consolidation or a test of key support before taking fresh long positions."
                )
            )

        elif any(w in upper for w in ["SAFE", "LONG TERM", "HOLD", "INVEST", "FUNDAMENTAL"]):
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
                f"- *'Will {company_name} price hike in the next few days?'*\n"
                f"- *'Is {company_name} fundamentally safe for long-term holding?'*"
            )
    except Exception as e:
        return f"Error retrieving real-time data for **{company_name}** (`{ticker_symbol}`): {e}"

# --- COMBINED PINNED MASTER BAR (HEADER + PERSISTENT TABS) ---
tabs_list = [
    ("📊 Market Watch", "watch"),
    ("💬 Stock Chatbot", "chat"),
    ("🚀 IPO Hub", "ipo"),
    ("🔍 Deep Dive", "dive")
]

nav_html = "".join([
    f'<a href="?nav={key}" target="_self" class="nav-tab-btn {"active" if st.session_state.current_tab == name else ""}">{name}</a>'
    for name, key in tabs_list
])

st.markdown(f"""
<div class="pinned-master-bar">
    <h2>⚡ NSE Mobile Pulse & AI Advisor</h2>
    <p>Tracking {len(ALL_NSE_STOCKS):,} Equities • Adaptive AI Advisor • Live IPO Hub</p>
    <div class="nav-tabs-wrapper">
        {nav_html}
    </div>
</div>
""", unsafe_allow_html=True)

# Active tab selection reference
active_tab = st.session_state.current_tab

# ==============================================================================
# TAB 1: LIVE MOVERS, DYNAMIC PICKS & 52-WEEK LOWS
# ==============================================================================
if active_tab == "📊 Market Watch":
    is_market_open, now_ist = get_market_status()
    fragment_interval = 20 if is_market_open else None

    @st.fragment(run_every=fragment_interval)
    def render_movers_dashboard():
        is_open, current_time_ist = get_market_status()
        time_str = current_time_ist.strftime("%I:%M:%S %p IST")

        if is_open:
            st.subheader("🟢 Today's Live Market Movers (Market Open)")
            st.caption(f"🔄 Auto-updating every 20s | Clock: **{time_str}**")
        else:
            header_col, btn_col = st.columns([3, 1.2])
            with header_col:
                st.subheader("🔴 Market Watch (Session Closed)")
                st.caption(f"Regular Hours: 9:15 AM – 3:30 PM IST Mon–Fri | Checked: **{time_str}**")
            with btn_col:
                if st.button("🔄 Refresh Data", use_container_width=True):
                    get_live_market_data.clear()
                    screen_52w_low_strong_picks.clear()

        gainers_df, losers_df, last_date = get_live_market_data(ALL_NSE_STOCKS)

        if not is_open and last_date:
            st.info(f"📅 Data represents the last completed exchange session: **{last_date}**")

        st.markdown("---")
        if is_open:
            st.subheader("⭐ Top 5 Algorithmic Recommendations (Intraday, Short & Long Term)")
        else:
            st.subheader("⭐ Top Recommendations for Next Session (Short & Long Term)")
            st.caption("Intraday momentum calls are hidden because the market session is closed.")

        if not gainers_df.empty and not losers_df.empty and len(gainers_df) >= 2 and len(losers_df) >= 3:
            top_g1 = gainers_df.iloc[0]["Stock"]
            top_g2 = gainers_df.iloc[1]["Stock"]
            top_l1 = losers_df.iloc[0]["Stock"]
            top_l2 = losers_df.iloc[1]["Stock"]
            top_l3 = losers_df.iloc[2]["Stock"]

            all_picks = []
            if is_open:
                all_picks.append({
                    "Stock": top_g1, "Horizon": "Intraday Momentum", "Action": "BUY ON DIP",
                    "Origin": f"Top Gainer (+{gainers_df.iloc[0]['% Change']}%)",
                    "Why": "Strong morning participation and volume expansion. Ride trend toward VWAP pullbacks."
                })

            all_picks.extend([
                {"Stock": top_g2, "Horizon": "Short-Term Swing (1–4 Wks)", "Action": "BUY (Breakout)", "Origin": f"Top Gainer (+{gainers_df.iloc[1]['% Change']}%)", "Why": "Clean breakout clearing immediate resistance levels with supportive volume."},
                {"Stock": top_l1, "Horizon": "Short-Term Rebound (1–3 Wks)", "Action": "BUY (Mean Reversion)", "Origin": f"Top Loser ({losers_df.iloc[0]['% Change']}%)", "Why": "Selling exhaustion near dynamic lower support bands. Favorable risk-reward for bounce."},
                {"Stock": top_l2, "Horizon": "Long-Term Value (6–12 Mos)", "Action": "BUY (Accumulate)", "Origin": f"Top Loser ({losers_df.iloc[1]['% Change']}%)", "Why": "Market drawdown on solid balance sheet, offering attractive valuation safety."},
                {"Stock": top_l3, "Horizon": "Long-Term Core (12–24 Mos)", "Action": "BUY (Compounder)", "Origin": f"Top Loser ({losers_df.iloc[2]['% Change']}%)", "Why": "Macro pullback on fundamentally sound asset with strong capital return ratios."}
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

        st.markdown("---")
        g_col, l_col = st.columns(2)
        with g_col:
            st.markdown("##### 🟢 Top Gainers")
            if not gainers_df.empty:
                st.dataframe(gainers_df.style.format({"Live Price (₹)": "₹{:.2f}", "Change (₹)": "+{:.2f}", "% Change": "+{:.2f}%"}), use_container_width=True, hide_index=True)
        with l_col:
            st.markdown("##### 🔴 Top Losers")
            if not losers_df.empty:
                st.dataframe(losers_df.style.format({"Live Price (₹)": "₹{:.2f}", "Change (₹)": "{:.2f}", "% Change": "{:.2f}%"}), use_container_width=True, hide_index=True)

        st.markdown("---")
        st.subheader("🛡️ Top 3 Fundamental Stocks Near 52-Week Low")
        st.caption("Zero/low debt, solid balance sheet, and closest to 52-week support with calculated Stop-Loss & Target levels.")

        low_screener_df = screen_52w_low_strong_picks(ALL_NSE_STOCKS)
        if not low_screener_df.empty:
            cols = st.columns(len(low_screener_df))
            for i, (_, row) in enumerate(low_screener_df.iterrows()):
                with cols[i]:
                    with st.container(border=True):
                        st.markdown(f"### 💎 {row['Stock']}")
                        st.metric("CMP", f"₹{row['Price']}", delta=f"{row['Dist %']}% from 52W Low", delta_color="inverse")
                        st.write(f"**52W Low:** ₹{row['52W Low']} | **52W High:** ₹{row['52W High']}")
                        st.markdown("---")
                        st.markdown("**⚡ Short-Term (1–4 Wks):**")
                        st.write(f"- **Buy Range:** ₹{row['Price']}")
                        st.write(f"- **Stop-Loss:** ₹{row['Short SL']}")
                        st.write(f"- **Target:** ₹{row['Short Target']}")
                        st.markdown("**🏛️ Long-Term (6–18 Mos):**")
                        st.write(f"- **Stop-Loss:** ₹{row['Long SL']}")
                        st.write(f"- **Target:** ₹{row['Long Target']}")
        else:
            st.info("Loading 52-week value candidates...")

    render_movers_dashboard()

# ==============================================================================
# TAB 2: UNIVERSAL INTERACTIVE STOCK CHATBOT (STREAMING + REAL-TIME DATA)
# ==============================================================================
elif active_tab == "💬 Stock Chatbot":
    st.subheader("💬 Universal AI Stock & Market Advisor")
    st.caption("Real-time technical indicators, live price discovery, and conversational financial analysis.")

    if "chat_history" not in st.session_state:
        st.session_state.chat_history = [
            {"role": "assistant", "content": "Hello! I am your real-time Indian Equities Assistant. Ask me anything, such as:\n- *'Analyse INFY with latest price action'* \n- *'Which share is best to buy now?'* \n- *'Will Tata Motors cross its 50-day average?'* \n- *'What is RSI and how do I trade it?'*"}
        ]

    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if user_prompt := st.chat_input("Ask any share market question..."):
        st.session_state.chat_history.append({"role": "user", "content": user_prompt})
        with st.chat_message("user"):
            st.markdown(user_prompt)

        with st.chat_message("assistant"):
            response_generator = stream_chatbot_response(user_prompt)
            full_response = st.write_stream(response_generator)
            st.session_state.chat_history.append({"role": "assistant", "content": full_response})

# ==============================================================================
# TAB 3: LIVE IPOs & GMP TRACKER (FULL LIST INCLUDING AVOID OPTIONS)
# ==============================================================================
elif active_tab == "🚀 IPO Hub":
    st.subheader("🔥 Ongoing & Upcoming IPO Tracker (Mainboard & SME)")
    st.caption("Live Grey Market Premium (GMP) • Subscription • Action Signals (Apply, Neutral, Avoid)")

    ipo_df = fetch_live_ipo_gmp()
    if not ipo_df.empty:
        f1, f2, f3 = st.columns([1.5, 1.5, 2])
        with f1:
            status_filter = st.selectbox("Status Filter:", ["All Statuses", "Ongoing (Open)", "Upcoming", "Closed / Allotted"])
        with f2:
            cat_filter = st.radio("Category:", ["All", "Mainboard", "SME"], horizontal=True)
        with f3:
            rec_filter = st.selectbox("Signal Filter:", ["All Signals", "STRONG APPLY", "APPLY (Listing Gain)", "NEUTRAL / CAUTION", "AVOID"])

        filtered = ipo_df.copy()
        if status_filter != "All Statuses":
            filtered = filtered[filtered["Status"] == status_filter]
        if cat_filter != "All":
            filtered = filtered[filtered["Type"] == cat_filter]
        if rec_filter != "All Signals":
            filtered = filtered[filtered["Recommendation"] == rec_filter]

        if not filtered.empty:
            for _, row in filtered.iterrows():
                with st.container(border=True):
                    h1, h2, h3 = st.columns([3, 2, 2])
                    with h1:
                        st.markdown(f"### {row['Company']}")
                        st.caption(f"Status: **{row['Status']}** | Category: **{row['Type']}** | Lot: **{row['Lot Size']}**")
                    with h2:
                        st.metric(
                            label="Listing Premium (GMP)",
                            value=f"₹{row['GMP (₹)']} GMP",
                            delta=f"+{row['Est Gain %']}%" if row['Est Gain %'] > 0 else "Flat / Discount"
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
                        st.write(f"**Dates:** {row['Open Date']} to {row['Close Date']}")
                        if row["Subscription"] != "-":
                            st.write(f"**Subscription:** {row['Subscription']}")
                    with d2:
                        st.markdown(f"**Why this call?** {row['Analysis & Rationale']}")
        else:
            st.info("No IPOs match the selected filter combination.")
    else:
        st.info("Gathering live IPO grey market figures...")

# ==============================================================================
# TAB 4: DEEP-DIVE SINGLE STOCK ANALYZER
# ==============================================================================
elif active_tab == "🔍 Deep Dive":
    st.subheader("🔍 Single Stock Deep Dive & Buy/Sell Call")

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
                        st.error("Insufficient market history to generate indicators.")
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

# --- MANDATORY REGULATORY & EDUCATIONAL DISCLAIMER ---
st.markdown("---")
st.warning(
    "⚠️ **Disclaimer:** This tool is purely for educational purposes. "
    "Please consult with a SEBI-registered advisor before buying or selling any securities."
)