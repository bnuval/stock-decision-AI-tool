import streamlit as st
import yfinance as yf
import pandas as pd
import ta
import feedparser
import requests
import io
import os
import re
import json
import time as time_module
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, time, date
from pathlib import Path
import pytz
from textblob import TextBlob
from stock_features import (
    VIRTUAL_INVESTMENT,
    assess_fundamentals,
    build_virtual_trade,
    fetch_virtual_trades,
    evaluate_ipo_recommendation,
    is_ipo_application_open,
    is_active_today_or_future as ipo_is_active,
    match_ipo_gmp,
    parse_ipo_detail_html,
    parse_ipo_gmp_html,
    parse_ipo_date as parse_ipo_date_value,
    parse_ipo_schedule_html,
    sync_virtual_trades,
)

# --- MOBILE-FIRST PAGE CONFIGURATION ---
st.set_page_config(
    page_title="NSE Pulse, IPO Hub & AI Advisor",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed"
)

IST = pytz.timezone("Asia/Kolkata")

# Initialize navigation and generation states
if "current_tab" not in st.session_state:
    st.session_state.current_tab = "📊 Market Watch"

if "active_stock" not in st.session_state:
    st.session_state.active_stock = {"symbol": None, "company": None}

if "is_generating" not in st.session_state:
    st.session_state.is_generating = False

query_params = st.query_params
if "nav" in query_params and query_params["nav"] in ["watch", "chat", "ipo", "dive", "portfolio"]:
    nav_map = {
        "watch": "📊 Market Watch",
        "chat": "💬 Stock Chatbot",
        "ipo": "🚀 IPO Hub",
        "dive": "🔍 Deep Dive",
        "portfolio": "📒 Virtual Portfolio",
    }
    st.session_state.current_tab = nav_map[query_params["nav"]]

# --- CSS: FIXED HEADER + PERSISTENT TABS ROW ---
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

# --- 1. MARKET SCHEDULE & NSE/BSE TRADING HOLIDAYS ENGINE ---
NSE_TRADING_HOLIDAYS = {
    # 2026 Official NSE/BSE Equity Trading Calendar
    date(2026, 1, 26): "Republic Day",
    date(2026, 3, 3): "Holi",
    date(2026, 3, 20): "Id-Ul-Fitr (Ramzan Id)",
    date(2026, 3, 27): "Ram Navami",
    date(2026, 4, 3): "Good Friday",
    date(2026, 4, 14): "Dr. Baba Saheb Ambedkar Jayanti",
    date(2026, 5, 1): "Maharashtra Day",
    date(2026, 5, 27): "Bakri Id",
    date(2026, 6, 26): "Muharram",
    date(2026, 9, 14): "Ganesh Chaturthi",
    date(2026, 10, 2): "Mahatma Gandhi Jayanti",
    date(2026, 10, 20): "Dussehra",
    date(2026, 11, 10): "Diwali-Balipratipada",
    date(2026, 11, 24): "Prakash Gurpurb Sri Guru Nanak Dev Jayanti",
    date(2026, 12, 25): "Christmas",
}

def get_market_status():
    """
    Evaluates current time against market trading hours, weekends,
    and verified exchange public holidays.
    """
    now_ist = datetime.now(IST)
    today_date = now_ist.date()
    weekday = now_ist.weekday()
    current_time = now_ist.time()

    # Check 1: Weekends (Saturday=5, Sunday=6)
    if weekday >= 5:
        return False, now_ist, "Weekend (Saturday/Sunday)"

    # Check 2: NSE Public & Exchange Trading Holidays
    if today_date in NSE_TRADING_HOLIDAYS:
        return False, now_ist, f"Public Holiday ({NSE_TRADING_HOLIDAYS[today_date]})"

    # Check 3: Regular Trading Session (09:15 to 15:30 IST)
    if time(9, 15) <= current_time <= time(15, 30):
        return True, now_ist, "Regular Session Open"
    elif current_time < time(9, 15):
        return False, now_ist, "Pre-Market (Opens at 9:15 AM)"
    else:
        return False, now_ist, "Market Closed (Post 3:30 PM)"

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
        "BEL", "BHEL", "IRCTC", "RVNL", "IREDA", "SUZLON", "YESBANK", "IDEA", "DLF", "DABUR", "KEI", "COMMITTED"
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
                    "Latest Price (₹)": round(curr_price, 2),
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

# --- 5. TOP 3 PICKS: 52-WEEK LOW + TECHNICAL CONFLUENCE FILTER ---
@st.cache_data(ttl=300)
def screen_52w_low_strong_picks(universe):
    candidate_symbols = [
        "HINDUNILVR", "DABUR", "ITC", "IRCTC", "INFY", "TCS", "HDFCBANK",
        "KOTAKBANK", "ASIANPAINT", "MARUTI", "SUNPHARMA", "WIPRO", "TATAMOTORS",
        "RELIANCE", "LT", "ICICIBANK", "AXISBANK", "SBIN"
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
            if series is not None and len(series) >= 60:
                curr_price = float(series.iloc[-1])
                low_52w = float(series.min())
                high_52w = float(series.max())

                if low_52w <= 0:
                    continue

                dist_from_low = ((curr_price - low_52w) / low_52w) * 100

                if dist_from_low > 18.0:
                    continue

                rsi_series = ta.momentum.RSIIndicator(series, window=14).rsi()
                rsi_val = float(rsi_series.iloc[-1]) if not rsi_series.empty else 50.0

                ema_20_series = ta.trend.EMAIndicator(series, window=20).ema_indicator()
                ema_20 = float(ema_20_series.iloc[-1]) if not ema_20_series.empty else curr_price

                macd_obj = ta.trend.MACD(series)
                macd_line = float(macd_obj.macd().iloc[-1])
                macd_sig = float(macd_obj.macd_signal().iloc[-1])

                rsi_ok = (30.0 <= rsi_val <= 65.0)
                momentum_ok = (curr_price >= ema_20 * 0.985) or (macd_line >= macd_sig)

                tech_score = 0
                tech_notes = []

                if rsi_ok:
                    tech_score += 1
                    tech_notes.append(f"RSI ({rsi_val:.1f}) in healthy reversal zone")
                if curr_price >= ema_20:
                    tech_score += 1
                    tech_notes.append(f"Trading above 20-day EMA (₹{ema_20:.2f})")
                if macd_line >= macd_sig:
                    tech_score += 1
                    tech_notes.append("MACD holds bullish crossover")

                if tech_score >= 2 and momentum_ok:
                    fundamentals = get_fundamental_snapshot(f"{symbol}.NS")
                    if not fundamentals["buy_eligible"]:
                        continue

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
                        "RSI": round(rsi_val, 1),
                        "Technical Setup": " • ".join(tech_notes),
                        "Technical Verdict": "🟢 Bullish Reversal",
                        "Fundamental Status": fundamentals["status"],
                        "Fundamental Summary": fundamentals["summary"],
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

# --- DATE PARSER FOR ROLLING EXPIRATION ---
def parse_ipo_date(date_str: str) -> date | None:
    return parse_ipo_date_value(date_str, today=datetime.now(IST).date())

def is_active_today_or_future(close_date_str: str) -> bool:
    return ipo_is_active(close_date_str, today=datetime.now(IST).date())

# --- 6. LIVE IPO HUB ---
def request_ipo_company_fundamentals(details_url: str):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Referer": "https://www.chittorgarh.com/",
    }
    response = requests.get(details_url, headers=headers, timeout=10)
    response.raise_for_status()
    return parse_ipo_detail_html(response.content)


@st.cache_data(ttl=900)
def fetch_ipo_fundamentals(detail_urls: tuple[str, ...]):
    results = {}
    with ThreadPoolExecutor(max_workers=min(4, len(detail_urls))) as executor:
        detail_requests = {
            executor.submit(request_ipo_company_fundamentals, url): url
            for url in detail_urls
        }
        for future in as_completed(detail_requests):
            url = detail_requests[future]
            try:
                results[url] = {"fundamentals": future.result(), "error": None}
            except (requests.RequestException, ValueError) as exc:
                results[url] = {"fundamentals": {}, "error": str(exc)}
    return results


@st.cache_data(ttl=300)
def fetch_live_ipo_gmp():
    """Fetch active IPO schedules, current GMP, and issuer financials."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Referer": "https://www.chittorgarh.com/",
    }
    today = datetime.now(IST).date()
    schedule_sources = {
        "Mainboard": "https://www.chittorgarh.com/ipo/ipo_dashboard.asp",
        "SME": "https://www.chittorgarh.com/ipo/ipo_dashboard.asp?a=sme",
    }
    session = requests.Session()
    session.headers.update(headers)
    ipo_records = []
    for board, url in schedule_sources.items():
        response = session.get(url, timeout=15)
        response.raise_for_status()
        ipo_records.extend(
            parse_ipo_schedule_html(
                response.content,
                board=board,
                today=today,
                now=datetime.now(IST),
            )
        )

    if not ipo_records:
        return pd.DataFrame(), "No upcoming or currently open IPOs were found."

    gmp_error = None
    try:
        gmp_response = session.get(
            "https://ipowatch.in/ipo-grey-market-premium-latest-ipo-gmp/",
            timeout=15,
        )
        gmp_response.raise_for_status()
        gmp_records = parse_ipo_gmp_html(gmp_response.content)
    except (requests.RequestException, ValueError) as exc:
        gmp_records = []
        gmp_error = f"Live GMP could not be verified: {exc}"

    page_fetched_at = datetime.now(IST).strftime("%d %b %Y, %I:%M %p IST")
    for ipo in ipo_records:
        gmp_record = match_ipo_gmp(ipo["Company"], ipo["Type"], gmp_records)
        ipo["GMP (₹)"] = gmp_record["GMP (₹)"] if gmp_record else None
        ipo["Issue Price (₹)"] = gmp_record["Issue Price (₹)"] if gmp_record else None
        ipo["Est Gain %"] = gmp_record["Est Gain %"] if gmp_record else None
        ipo["GMP Source URL"] = (
            gmp_record["GMP Source URL"] if gmp_record else "https://ipowatch.in/"
        )

    fundamentals_by_url = fetch_ipo_fundamentals(
        tuple(ipo["IPO Details URL"] for ipo in ipo_records)
    )
    for ipo in ipo_records:
        detail = fundamentals_by_url[ipo["IPO Details URL"]]
        fundamentals = detail["fundamentals"]
        if detail["error"]:
            ipo["Fundamental Source Status"] = (
                f"Issuer financials unavailable: {detail['error']}"
            )
        else:
            ipo["Fundamental Source Status"] = (
                "Issuer financial tables loaded"
                if any(
                    key in fundamentals
                    for key in (
                        "latest_revenue",
                        "latest_pat",
                        "roe",
                        "roce",
                        "debt_equity",
                        "pat_margin",
                    )
                )
                else "No financial ratios or annual figures found"
            )

        if ipo["Issue Price (₹)"] is None:
            ipo["Issue Price (₹)"] = fundamentals.get("issue_price")
        ipo["Price Band"] = fundamentals.get("price_band", "Not reported")
        ipo["Lot Size"] = fundamentals.get("lot_size", "Not reported")
        ipo["Issue Size"] = fundamentals.get("issue_size", "Not reported")
        ipo["Est Gain %"] = (
            round(ipo["GMP (₹)"] / ipo["Issue Price (₹)"] * 100, 2)
            if ipo["GMP (₹)"] is not None
            and ipo["Issue Price (₹)"] is not None
            and ipo["Issue Price (₹)"] > 0
            else None
        )
        recommendation = evaluate_ipo_recommendation(
            fundamentals,
            ipo["GMP (₹)"],
            ipo["Issue Price (₹)"],
        )
        ipo.update(recommendation)
        ipo["Fundamental Summary"] = (
            f"{recommendation['Fundamental Summary']} "
            f"Data status: {ipo['Fundamental Source Status']}."
        )
        ipo["Page Fetched At"] = page_fetched_at
        ipo["Fundamental Source URL"] = ipo["IPO Details URL"]

    return pd.DataFrame(ipo_records), gmp_error

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

# --- 8. API KEY RETRIEVAL ---
def get_gemini_api_key():
    return get_private_setting("GEMINI_API_KEY")

# --- 8A. FUNDAMENTALS AND VIRTUAL TRADE LEDGER ---
@st.cache_data(ttl=900, max_entries=256)
def get_fundamental_snapshot(ticker: str) -> dict:
    try:
        info = yf.Ticker(ticker).info or {}
    except Exception as exc:
        result = assess_fundamentals({})
        result["summary"] = f"Fundamental data unavailable ({type(exc).__name__})."
        return result
    return assess_fundamentals(info)


def get_private_setting(name: str) -> str:
    value = os.getenv(name, "").strip()
    if value:
        return value

    secrets_path = Path(__file__).parent / ".streamlit" / "secrets.toml"
    if secrets_path.is_file():
        return str(st.secrets.get(name, "")).strip()
    return ""


def format_fundamental_assessment(fundamentals: dict) -> str:
    values = []
    for key, label, multiplier, suffix in (
        ("roe", "ROE", 100, "%"),
        ("profit_margin", "Profit margin", 100, "%"),
        ("debt_to_equity", "Debt/equity", 1, "%"),
        ("net_income", "Net income", 1 / 1e7, " Cr"),
    ):
        value = fundamentals.get(key)
        if value is not None:
            values.append(f"{label}: {value * multiplier:,.1f}{suffix}")
    detail = " | ".join(values) if values else "Metrics unavailable"
    checks = " | ".join(
        f"{'✓' if passed else '✗'} {label}"
        for label, passed in fundamentals.get("checks", [])
    )
    check_detail = f" Checks: {checks}." if checks else ""
    return (
        f"**Fundamentals: {fundamentals['status']}** — "
        f"{fundamentals['summary']} ({detail}).{check_detail}"
    )


def make_buy_call(
    ticker: str,
    company: str,
    source: str,
    horizon: str,
    entry_price: float,
    target_price: float,
    stop_loss: float,
    fundamentals: dict,
    quote_as_of: str | None = None,
) -> dict:
    return {
        "ticker": ticker,
        "company": company,
        "source": source,
        "horizon": horizon,
        "entry_price": entry_price,
        "target_price": target_price,
        "stop_loss": stop_loss,
        "fundamental_status": fundamentals["status"],
        "fundamental_summary": fundamentals["summary"],
        "quote_as_of": quote_as_of or datetime.now(IST).strftime("%d %b %Y"),
    }


def register_buy_calls(calls: list[dict]) -> None:
    eligible_calls = [
        call
        for call in calls
        if call.get("fundamental_status") == "Pass"
        and call.get("entry_price")
        and call.get("target_price")
        and call.get("stop_loss")
    ]
    if not eligible_calls:
        return

    bin_id = get_private_setting("JSONBIN_BIN_ID")
    master_key = get_private_setting("JSONBIN_MASTER_KEY")
    if not bin_id or not master_key:
        if not st.session_state.get("jsonbin_config_notice_shown", False):
            st.info("Paper-trade logging is not configured. Set JSONBIN_BIN_ID and JSONBIN_MASTER_KEY to save BUY calls.")
            st.session_state.jsonbin_config_notice_shown = True
        return

    called_at = datetime.now(IST)
    logged_ids = st.session_state.setdefault("logged_virtual_call_ids", set())
    pending_calls = [
        call
        for call in eligible_calls
        if build_virtual_trade(call, called_at=called_at)["id"] not in logged_ids
    ]
    if not pending_calls:
        return

    try:
        result = sync_virtual_trades(
            pending_calls,
            bin_id,
            master_key,
            called_at=called_at,
        )
    except (requests.RequestException, ValueError) as exc:
        st.error(f"Could not save the paper trade to JSONBin: {exc}")
        return

    logged_ids.update(
        build_virtual_trade(call, called_at=called_at)["id"]
        for call in pending_calls
    )
    if result["added"]:
        st.success(
            f"Logged {result['added']} virtual BUY call(s), ₹{VIRTUAL_INVESTMENT:,.0f} each."
        )


@st.cache_data(ttl=60, max_entries=64)
def get_latest_trade_prices(tickers: tuple[str, ...]) -> dict[str, float]:
    if not tickers:
        return {}
    data = yf.download(
        list(tickers),
        period="5d",
        interval="1d",
        progress=False,
        auto_adjust=False,
    )
    if data.empty:
        return {}
    closes = data["Close"] if "Close" in data.columns else data
    prices = {}
    if isinstance(closes, pd.Series) and len(tickers) == 1:
        values = closes.dropna()
        if not values.empty:
            return {tickers[0]: float(values.iloc[-1])}
    for ticker in tickers:
        if ticker in closes.columns:
            values = closes[ticker].dropna()
        else:
            continue
        if not values.empty:
            prices[ticker] = float(values.iloc[-1])
    return prices


# --- 9. CONVERSATIONAL ENTITY & CONTEXT RESOLVER ---
def get_live_market_context_for_query(query: str):
    normalized = re.sub(r"[()\[\],.?/:;!]", " ", query).upper()
    tokens = [w.strip() for w in normalized.split() if w.strip()]

    ticker_found = None
    company_name = None

    for t in tokens:
        if t in ALL_NSE_STOCKS:
            ticker_found = f"{t}.NS"
            company_name = t
            break

    if not ticker_found:
        clean_target = re.sub(
            r"(?i)\b(what|is|the|current|last|year|quarter|annual|net|profit|revenue|margin|analiyse|analyse|analyze|analysis|check|review|details|will|price|share|stock|of|hike|increase|decrease|fall|go|up|down|in|next|few|days|weeks|months|short|long|term|safe|to|buy|sell|hold|invest|for|now|today|should|i|tell|me|about|how|it|this|that|same|stock|company)\b",
            " ",
            query
        )
        search_term = re.sub(r"[()\[\],.?/:;!]", " ", clean_target)
        search_term = re.sub(r"\s+", " ", search_term).strip()

        if search_term and len(search_term) >= 3:
            ticker_found, company_name = resolve_ticker_online(search_term)

    if not ticker_found and st.session_state.active_stock.get("symbol"):
        padded_query = f" {normalized} "
        pronoun_cues = [" IT ", " THIS ", " THAT ", " ITS ", " SAME ", " THE STOCK ", " THE SHARE ", " THE COMPANY ", " HOLD IT "]
        is_follow_up = any(cue in padded_query for cue in pronoun_cues) or (
            any(w in normalized for w in ["BUY", "SELL", "HOLD", "SAFE", "TARGET", "PE", "PROFIT", "REVENUE", "HIKE", "FALL"]) 
            and len(tokens) <= 7
        )
        if is_follow_up:
            ticker_found = st.session_state.active_stock["symbol"]
            company_name = st.session_state.active_stock["company"]

    if ticker_found and company_name:
        st.session_state.active_stock = {"symbol": ticker_found, "company": company_name}

    context_dict = {
        "ticker": ticker_found,
        "company": company_name,
        "price": None,
        "quote_as_of": None,
        "rsi": None,
        "sma_50": None,
        "pe": None,
        "roe": None,
        "net_income_cr": None,
        "revenue_cr": None,
        "ebitda_cr": None,
        "eps": None,
        "profit_margin": None,
        "fundamentals": assess_fundamentals({}),
        "context_text": ""
    }

    if ticker_found:
        try:
            stock = yf.Ticker(ticker_found)
            info = stock.info or {}
            context_dict["fundamentals"] = assess_fundamentals(info)
            hist = stock.history(period="3mo")

            if hist.empty:
                sme_sym = ticker_found.replace(".NS", "-SM.NS")
                sme_stock = yf.Ticker(sme_sym)
                sme_hist = sme_stock.history(period="3mo")
                if not sme_hist.empty:
                    stock = sme_stock
                    hist = sme_hist
                    info = stock.info or {}
                    context_dict["fundamentals"] = assess_fundamentals(info)

            if not hist.empty:
                context_dict["price"] = float(hist["Close"].iloc[-1])
                context_dict["quote_as_of"] = hist.index[-1].strftime("%d %b %Y")
                context_dict["rsi"] = float(ta.momentum.RSIIndicator(hist["Close"], window=14).rsi().iloc[-1])
                context_dict["sma_50"] = float(ta.trend.SMAIndicator(hist["Close"], window=50).sma_indicator().iloc[-1])

            context_dict["pe"] = info.get("trailingPE", "N/A")
            context_dict["roe"] = round((info.get("returnOnEquity") or 0) * 100, 2)
            context_dict["eps"] = info.get("trailingEps")

            net_inc = info.get("netIncomeToCommon")
            if net_inc:
                context_dict["net_income_cr"] = round(net_inc / 1e7, 2)

            rev = info.get("totalRevenue")
            if rev:
                context_dict["revenue_cr"] = round(rev / 1e7, 2)

            ebitda = info.get("ebitda")
            if ebitda:
                context_dict["ebitda_cr"] = round(ebitda / 1e7, 2)

            pm = info.get("profitMargins")
            if pm:
                context_dict["profit_margin"] = round(pm * 100, 2)

            lines = [f"[VERIFIED METRICS FOR ACTIVE STOCK: {company_name} ({ticker_found})]"]
            if context_dict["price"]:
                lines.append(
                    f"- Latest available price snapshot: ₹{context_dict['price']:,.2f} "
                    f"({context_dict['quote_as_of']})"
                )
            if context_dict["net_income_cr"]:
                lines.append(f"- Annual Net Profit (Net Income): ₹{context_dict['net_income_cr']:,.2f} Crores")
            if context_dict["revenue_cr"]:
                lines.append(f"- Annual Revenue: ₹{context_dict['revenue_cr']:,.2f} Crores")
            if context_dict["ebitda_cr"]:
                lines.append(f"- EBITDA: ₹{context_dict['ebitda_cr']:,.2f} Crores")
            if context_dict["profit_margin"]:
                lines.append(f"- Profit Margin: {context_dict['profit_margin']}%")
            if context_dict["eps"]:
                lines.append(f"- EPS: ₹{context_dict['eps']}")
            if context_dict["rsi"]:
                lines.append(f"- 14-day RSI: {context_dict['rsi']:.1f}")
            if context_dict["sma_50"]:
                lines.append(f"- 50-day SMA: ₹{context_dict['sma_50']:,.2f}")
            if context_dict["pe"]:
                lines.append(f"- Trailing P/E: {context_dict['pe']}")
            lines.append(
                "- Fundamental screen: "
                f"{context_dict['fundamentals']['status']} — "
                f"{context_dict['fundamentals']['summary']}"
            )

            context_dict["context_text"] = "\n".join(lines)
        except Exception:
            pass

    return context_dict

# --- 10. BULLETPROOF FLASH CALLER ---
def call_gemini_rest_api(prompt: str, api_key: str):
    target_models = [
        "gemini-3.6-flash",
        "gemini-3.5-flash-lite",
        "gemini-3.7-flash"
    ]

    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": api_key
    }
    payload = {
        "contents": [{"parts": [{"text": prompt}]}]
    }

    last_error = ""

    for model_name in target_models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=12)
            if resp.status_code == 200:
                result = resp.json()
                candidates = result.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts:
                        return parts[0].get("text", "")
            elif resp.status_code == 429:
                last_error = f"{model_name} (Rate limited 429)"
                continue
            else:
                last_error = f"{model_name} -> HTTP {resp.status_code}: {resp.text}"
        except Exception as e:
            last_error = f"{model_name} -> {str(e)}"

    try:
        list_url = "https://generativelanguage.googleapis.com/v1beta/models"
        list_resp = requests.get(list_url, headers=headers, timeout=8)
        if list_resp.status_code == 200:
            for m in list_resp.json().get("models", []):
                name = m.get("name", "").replace("models/", "")
                methods = m.get("supportedGenerationMethods", [])
                if "generateContent" in methods and "flash" in name.lower() and "pro" not in name.lower():
                    run_url = f"https://generativelanguage.googleapis.com/v1beta/models/{name}:generateContent"
                    resp = requests.post(run_url, headers=headers, json=payload, timeout=12)
                    if resp.status_code == 200:
                        parts = resp.json().get("candidates", [])[0].get("content", {}).get("parts", [])
                        if parts:
                            return parts[0].get("text", "")
    except Exception:
        pass

    return f"ERROR: {last_error}"

# --- 11. STREAMING CHATBOT ORCHESTRATOR WITH DIALOGUE MEMORY ---
def stream_chatbot_response(user_query: str):
    api_key = get_gemini_api_key()
    context = get_live_market_context_for_query(user_query)

    recent_history = ""
    if "chat_history" in st.session_state and len(st.session_state.chat_history) > 1:
        for turn in st.session_state.chat_history[-4:]:
            role = "User" if turn["role"] == "user" else "Assistant"
            recent_history += f"{role}: {turn['content']}\n"

    if api_key:
        prompt = f"""
        You are an Indian Equity Market & Financial Intelligence Analyst for the NSE/BSE.
        Provide a concise, direct, professional answer to the user's latest question.
        Use clean markdown bullet points, bold financial totals in ₹ Crores or %, and clear key support/resistance levels.
        Check the verified fundamental screen before making any BUY recommendation.
        If the user asks for an actionable stock call, end with exactly one line:
        Signal: BUY, Signal: HOLD, or Signal: SELL.
        A BUY must include a numeric Target Price higher than the verified entry price.
        Never report a BUY when the fundamental screen fails or has insufficient data.
        If the user uses pronouns like "it", "this share", or refers back to the prior topic, answer in relation to the active stock.
        If the user switched to a completely different stock, address the new stock immediately.

        RECENT CONVERSATION HISTORY:
        {recent_history}

        VERIFIED LATEST PRICE SNAPSHOT AND FUNDAMENTALS FOR ACTIVE ASSET:
        {context['context_text']}

        LATEST USER QUESTION:
        {user_query}
        """
        ai_reply = call_gemini_rest_api(prompt, api_key)
        if ai_reply and not ai_reply.startswith("ERROR:"):
            ai_reply = record_chatbot_buy_if_eligible(ai_reply, context)
            for word in ai_reply.split(" "):
                yield word + " "
                time_module.sleep(0.01)
            return
        else:
            yield f"⚠️ *(AI API Notice: {ai_reply}. Switching to built-in market analysis engine...)*\n\n"

    static_reply = process_universal_chatbot_static(user_query, context)
    static_reply = record_chatbot_buy_if_eligible(static_reply, context)
    for word in static_reply.split(" "):
        yield word + " "
        time_module.sleep(0.015)


def record_chatbot_buy_if_eligible(reply: str, context: dict) -> str:
    signal_match = re.search(
        r"(?im)^\s*(?:[-*]\s*)?(?:\*\*)?Signal(?:\*\*)?\s*:\s*(BUY|HOLD|SELL)\b",
        reply,
    )
    if not signal_match or signal_match.group(1).upper() != "BUY":
        return reply

    ticker = context.get("ticker")
    entry_price = context.get("price")
    fundamentals = context.get("fundamentals") or assess_fundamentals({})
    if not ticker:
        return reply
    if not entry_price or not fundamentals["buy_eligible"]:
        reason = fundamentals["summary"] if not fundamentals["buy_eligible"] else "No verified stock price is available."
        reply = re.sub(
            r"(?im)^(\s*(?:[-*]\s*)?(?:\*\*)?Signal(?:\*\*)?\s*:\s*)BUY\b",
            r"\1HOLD",
            reply,
            count=1,
        )
        return f"{reply}\n\n**BUY call withheld:** {reason}"

    target_match = re.search(
        r"(?im)^.*?target(?:\s+price)?[^\d\n]*₹?\s*([\d,]+(?:\.\d+)?)",
        reply,
    )
    target_price = (
        float(target_match.group(1).replace(",", ""))
        if target_match
        else round(float(entry_price) * 1.08, 2)
    )
    if target_price <= float(entry_price):
        target_price = round(float(entry_price) * 1.08, 2)
    stop_loss = round(float(entry_price) * 0.95, 2)
    register_buy_calls(
        [
            make_buy_call(
                ticker,
                context.get("company") or ticker,
                "Stock Chatbot",
                "Chatbot call",
                float(entry_price),
                target_price,
                stop_loss,
                fundamentals,
                quote_as_of=context.get("quote_as_of"),
            )
        ]
    )
    return (
        f"{reply}\n\n"
        f"**Paper trade snapshot:** ₹{float(entry_price):,.2f} entry | "
        f"₹{target_price:,.2f} target | ₹{stop_loss:,.2f} stop-loss | "
        f"₹{VIRTUAL_INVESTMENT:,.0f} virtual investment."
    )


def process_universal_chatbot_static(user_query: str, context: dict):
    upper = user_query.upper()
    comp = context.get("company")
    ticker = context.get("ticker")

    if any(w in upper for w in ["PROFIT", "REVENUE", "INCOME", "EARNING", "FINANCIAL", "RESULTS", "EBITDA", "MARGIN"]):
        if comp:
            net_profit_str = f"₹{context['net_income_cr']:,.2f} Crores" if context.get("net_income_cr") else "See latest annual report filings"
            rev_str = f"₹{context['revenue_cr']:,.2f} Crores" if context.get("revenue_cr") else "N/A"
            margin_str = f"{context['profit_margin']}%" if context.get("profit_margin") else "N/A"
            eps_str = f"₹{context['eps']}" if context.get("eps") else "N/A"
            pe_str = f"{context['pe']}" if context.get("pe") else "N/A"

            return (
                f"### 📊 Financial Performance Snapshot: **{comp}** (`{ticker}`)\n\n"
                f"- **Annual Net Profit (Net Income):** **{net_profit_str}**\n"
                f"- **Annual Revenue (Turnover):** **{rev_str}**\n"
                f"- **Net Profit Margin:** **{margin_str}**\n"
                f"- **Earnings Per Share (EPS):** **{eps_str}**\n"
                f"- **P/E Valuation Ratio:** **{pe_str}**\n\n"
                f"> **Context:** Corporate earnings reflect consolidated full-year performance. For quarterly breakdowns, track quarterly filing announcements on NSE/BSE."
            )

    if any(k in upper for k in [
        "WHICH SHARE IS BEST TO BUY", "WHICH STOCK IS BEST TO BUY", "WHAT TO BUY NOW",
        "WHICH SHARE TO BUY TODAY", "BEST SHARE TO BUY NOW", "BEST STOCK TO BUY",
        "TOP SHARES TO BUY", "SUGGEST ME A SHARE", "RECOMMEND A STOCK", "WHAT SHOULD I BUY"
    ]) or (("BEST" in upper or "WHICH" in upper) and "BUY" in upper and len(user_query.split()) <= 10):

        gainers, losers, _ = get_live_market_data(ALL_NSE_STOCKS)
        low_52w = screen_52w_low_strong_picks(ALL_NSE_STOCKS)
        is_open, _, _ = get_market_status()

        resp = "### 🎯 Watchlist candidates based on recent price moves\n\n"
        buy_calls = []
        candidates = []
        if not gainers.empty and len(gainers) >= 2:
            candidates.append(
                (
                    gainers.iloc[1]["Stock"],
                    float(gainers.iloc[1]["Latest Price (₹)"]),
                    "Short-term momentum",
                    1.06,
                    0.97,
                    "Recent positive price move; daily data does not confirm volume or a breakout.",
                )
            )

        if not losers.empty and len(losers) >= 1:
            candidates.append(
                (
                    losers.iloc[0]["Stock"],
                    float(losers.iloc[0]["Latest Price (₹)"]),
                    "Short-term rebound",
                    1.05,
                    0.96,
                    "Recent negative price move; a decline alone does not confirm selling exhaustion.",
                )
            )

        if not low_52w.empty:
            v_row = low_52w.iloc[0]
            candidates.append(
                (
                    v_row["Stock"],
                    float(v_row["Price"]),
                    "Long-term 52-week value screen",
                    float(v_row["Long Target"]) / float(v_row["Price"]),
                    float(v_row["Long SL"]) / float(v_row["Price"]),
                    f"52-week support and technical screen ({v_row['Technical Setup']}).",
                )
            )

        for index, (symbol, entry_price, horizon, target_factor, stop_factor, reason) in enumerate(candidates, 1):
            fundamentals = get_fundamental_snapshot(f"{symbol}.NS")
            target_price = round(entry_price * target_factor, 2)
            stop_loss = round(entry_price * stop_factor, 2)
            if fundamentals["buy_eligible"]:
                signal = "BUY"
                buy_calls.append(
                    make_buy_call(
                        f"{symbol}.NS",
                        symbol,
                        "Stock Chatbot watchlist",
                        horizon,
                        entry_price,
                        target_price,
                        stop_loss,
                        fundamentals,
                    )
                )
            else:
                signal = "HOLD"
            resp += (
                f"**{index}. `{symbol}` — {horizon}**\n"
                f"- **Signal:** {signal}\n"
                f"- **Entry snapshot / target / stop:** ₹{entry_price:,.2f} / "
                f"₹{target_price:,.2f} / ₹{stop_loss:,.2f}\n"
                f"- **Reason:** {reason}\n"
                f"- {format_fundamental_assessment(fundamentals)}\n\n"
            )

        if not candidates:
            resp += "No candidates are available because the latest price data could not be loaded.\n\n"
        timing_note = "Market is open." if is_open else "Market is closed; prices may be from the last completed session."
        resp += f"> {timing_note} Each eligible BUY uses ₹{VIRTUAL_INVESTMENT:,.0f} of virtual capital."
        register_buy_calls(buy_calls)
        return resp

    if comp and any(w in upper for w in ["INCREASE", "HIKE", "RISE", "UP", "TARGET", "SHORT PERIOD", "SHORT TERM", "FEW DAYS"]):
        curr_price = context.get("price") or 0.0
        rsi = context.get("rsi") or 50.0
        sma_50 = context.get("sma_50") or curr_price
        is_bullish = (rsi < 65) and (curr_price >= sma_50)
        fundamentals = context.get("fundamentals") or assess_fundamentals({})
        is_buy = is_bullish and fundamentals["buy_eligible"]
        bias = "Bullish / Positive Momentum" if is_bullish else "Consolidation / Pullback Caution"
        signal = "BUY" if is_buy else "HOLD"
        target_price = round(curr_price * 1.06, 2)

        return (
            f"### Short-Term Outlook for **{comp}** (`{ticker}`)\n\n"
            f"- **Latest available price snapshot:** ₹{curr_price:,.2f}\n"
            f"- **14-Day RSI:** {rsi:.1f} " + ("*(Overbought)*" if rsi > 70 else "*(Oversold)*" if rsi < 35 else "*(Neutral)*") + "\n"
            f"- **50-Day Moving Average:** ₹{sma_50:,.2f} (" + ("Price is Above" if curr_price >= sma_50 else "Price is Below") + ")\n\n"
            f"**Verdict:** **{bias}**\n\n" +
            (
                f"Estimated swing target: **₹{target_price:,.2f}**, with stop-loss protection near **₹{curr_price * 0.95:,.2f}**."
                if is_bullish else
                f"A sudden sharp hike is less probable over immediate sessions due to moving average resistance or cooling momentum. Wait for consolidation before taking fresh long positions."
            ) + f"\n\n{format_fundamental_assessment(fundamentals)}\n\n**Signal:** {signal}"
        )

    if comp and any(w in upper for w in ["SAFE", "LONG TERM", "HOLD", "INVEST", "FUNDAMENTAL"]):
        roe = context.get("roe") or 0.0
        pe = context.get("pe")
        curr_price = context.get("price") or 0.0
        health = "Strong & Resilient" if roe >= 15.0 else "Moderate"

        return (
            f"### Fundamental Assessment for **{comp}** (`{ticker}`)\n\n"
            f"- **Current Price:** ₹{curr_price:,.2f}\n"
            f"- **Return on Equity (ROE):** {roe}%\n"
            f"- **Trailing P/E Ratio:** {pe}\n\n"
            f"**Verdict:** Long-term profile is **{health}**.\n\n" +
            (
                "Strong capital returns and balance sheet health support staggered long-term accumulation on pullbacks."
                if roe >= 15.0 else
                "Return ratios are moderate. Track upcoming quarterly margin sustainability before committing long-term capital."
            ) + f"\n\n{format_fundamental_assessment(context.get('fundamentals') or assess_fundamentals({}))}"
        )

    if comp:
        return (
            f"### Snapshot for **{comp}** (`{ticker}`)\n\n"
            f"- **Latest available price snapshot:** ₹{context.get('price', 0.0):,.2f}\n"
            f"- **Annual Net Profit:** ₹{context.get('net_income_cr', 0.0):,.2f} Crores\n"
            f"- **RSI (14):** {context.get('rsi', 0.0):.1f}\n"
            f"- **Trailing P/E:** {context.get('pe', 'N/A')}\n\n"
            f"{format_fundamental_assessment(context.get('fundamentals') or assess_fundamentals({}))}\n\n"
            f"You can ask:\n"
            f"- *'What is the current year profit of {comp}?'*\n"
            f"- *'Will {comp} price increase in the next few days?'*\n"
            f"- *'Is {comp} fundamentally safe to hold?'*"
        )

    return (
        "Please mention a specific stock or query. For example:\n"
        "- *'What is current year profit of Reliance?'*\n"
        "- *'Which share is best to buy now?'*\n"
        "- *'Analyse INFY'* \n"
        "- *'Will Tata Motors price hike in the next few days?'*"
    )

# --- COMBINED PINNED MASTER BAR ---
tabs_list = [
    ("📊 Market Watch", "watch"),
    ("💬 Stock Chatbot", "chat"),
    ("🚀 IPO Hub", "ipo"),
    ("🔍 Deep Dive", "dive"),
    ("📒 Virtual Portfolio", "portfolio"),
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

active_tab = st.session_state.current_tab

# ==============================================================================
# TAB 1: LIVE MOVERS, DYNAMIC PICKS & 52-WEEK LOW (HOLIDAY-AWARE)
# ==============================================================================
if active_tab == "📊 Market Watch":
    is_market_open, now_ist, session_reason = get_market_status()
    fragment_interval = 20 if is_market_open else None

    @st.fragment(run_every=fragment_interval)
    def render_movers_dashboard():
        is_open, current_time_ist, status_msg = get_market_status()
        time_str = current_time_ist.strftime("%I:%M:%S %p IST")

        if is_open:
            st.subheader("🟢 Today's Market Movers (Market Open)")
            st.caption(f"🔄 Refreshing every 20s; prices use Yahoo Finance's latest daily bar | Clock: **{time_str}**")
        else:
            header_col, btn_col = st.columns([3, 1.2])
            with header_col:
                st.subheader(f"🔴 Market Watch (Closed — {status_msg})")
                st.caption(f"Regular Hours: 9:15 AM – 3:30 PM IST Mon–Fri | Checked: **{time_str}**")
            with btn_col:
                if st.button("🔄 Refresh Data", use_container_width=True):
                    get_live_market_data.clear()
                    screen_52w_low_strong_picks.clear()

        gainers_df, losers_df, last_date = get_live_market_data(ALL_NSE_STOCKS)

        if not is_open and last_date:
            st.info(f"📅 Showing price data from the last completed exchange session: **{last_date}**")

        st.markdown("---")
        if is_open:
            st.subheader("⭐ Top 5 Algorithmic Recommendations (Intraday, Short & Long Term)")
        else:
            st.subheader("⭐ Top Recommendations for Next Active Session (Short & Long Term)")
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
                    "Price": float(gainers_df.iloc[0]["Latest Price (₹)"]),
                    "Target %": 6, "Stop %": 3,
                    "Origin": f"Top Gainer (+{gainers_df.iloc[0]['% Change']}%)",
                    "Why": "Strong recent price momentum; daily data does not confirm intraday volume or VWAP."
                })

            all_picks.extend([
                {"Stock": top_g2, "Price": float(gainers_df.iloc[1]["Latest Price (₹)"]), "Target %": 8, "Stop %": 4, "Horizon": "Short-Term Swing (1–4 Wks)", "Action": "BUY (Momentum)", "Origin": f"Top Gainer ({gainers_df.iloc[1]['% Change']:+.2f}%)", "Why": "Recent price momentum; this screen does not validate volume or resistance breakouts."},
                {"Stock": top_l1, "Price": float(losers_df.iloc[0]["Latest Price (₹)"]), "Target %": 5, "Stop %": 4, "Horizon": "Short-Term Rebound (1–3 Wks)", "Action": "BUY (Watch for Reversal)", "Origin": f"Top Loser ({losers_df.iloc[0]['% Change']:.2f}%)", "Why": "Price has declined; a decline alone does not confirm selling exhaustion or a reversal."},
                {"Stock": top_l2, "Price": float(losers_df.iloc[1]["Latest Price (₹)"]), "Target %": 12, "Stop %": 8, "Horizon": "Long-Term Value (6–12 Mos)", "Action": "BUY (Accumulate)", "Origin": f"Top Loser ({losers_df.iloc[1]['% Change']:.2f}%)", "Why": "Price weakness; fundamentals are checked below before any BUY call is recorded."},
                {"Stock": top_l3, "Price": float(losers_df.iloc[2]["Latest Price (₹)"]), "Target %": 20, "Stop %": 12, "Horizon": "Long-Term Core (12–24 Mos)", "Action": "BUY (Accumulate)", "Origin": f"Top Loser ({losers_df.iloc[2]['% Change']:.2f}%)", "Why": "Price weakness; fundamentals are checked below before any BUY call is recorded."}
            ])

            buy_calls = []
            p_cols = st.columns(len(all_picks))
            for idx, p in enumerate(all_picks):
                fundamentals = get_fundamental_snapshot(f"{p['Stock']}.NS")
                entry_price = p["Price"]
                target_price = round(entry_price * (1 + p["Target %"] / 100), 2)
                stop_loss = round(entry_price * (1 - p["Stop %"] / 100), 2)
                eligible = fundamentals["buy_eligible"]
                if eligible:
                    buy_calls.append(
                        make_buy_call(
                            f"{p['Stock']}.NS",
                            p["Stock"],
                            "Market Watch",
                            p["Horizon"],
                            entry_price,
                            target_price,
                            stop_loss,
                            fundamentals,
                            quote_as_of=last_date or None,
                        )
                    )
                with p_cols[idx]:
                    with st.container(border=True):
                        st.markdown(f"### {p['Stock']}")
                        st.caption(p["Origin"])
                        if eligible:
                            st.success(f"**{p['Action']}**")
                        else:
                            st.warning("**HOLD — BUY blocked by fundamentals**")
                        st.markdown(f"**Horizon:** {p['Horizon']}")
                        st.markdown(f"**Why?** {p['Why']}")
                        st.markdown(f"**Entry snapshot:** ₹{entry_price:,.2f}")
                        st.markdown(f"**Target / Stop:** ₹{target_price:,.2f} / ₹{stop_loss:,.2f}")
                        st.caption(format_fundamental_assessment(fundamentals))
                        if eligible:
                            st.caption(f"Paper trade: ₹{VIRTUAL_INVESTMENT:,.0f} virtual allocation")
            register_buy_calls(buy_calls)
        else:
            st.info("Not enough daily price history is available to produce market-mover calls.")

        st.markdown("---")
        g_col, l_col = st.columns(2)
        with g_col:
            st.markdown("##### 🟢 Top Gainers")
            if not gainers_df.empty:
                st.dataframe(gainers_df.style.format({"Latest Price (₹)": "₹{:.2f}", "Change (₹)": "+{:.2f}", "% Change": "+{:.2f}%"}), use_container_width=True, hide_index=True)
        with l_col:
            st.markdown("##### 🔴 Top Losers")
            if not losers_df.empty:
                st.dataframe(losers_df.style.format({"Latest Price (₹)": "₹{:.2f}", "Change (₹)": "{:.2f}", "% Change": "{:.2f}%"}), use_container_width=True, hide_index=True)

        st.markdown("---")
        st.subheader("🛡️ Top 3 Value Picks (52W Low Support + Bullish Technical Confirmation)")
        st.caption("Candidates must be near 52-week support, pass the RSI/EMA/MACD screen, and pass the available-fundamentals check.")

        low_screener_df = screen_52w_low_strong_picks(ALL_NSE_STOCKS)
        if not low_screener_df.empty:
            cols = st.columns(len(low_screener_df))
            value_buy_calls = []
            for i, (_, row) in enumerate(low_screener_df.iterrows()):
                fundamentals = get_fundamental_snapshot(f"{row['Stock']}.NS")
                value_buy_calls.extend(
                    [
                        make_buy_call(
                            f"{row['Stock']}.NS",
                            row["Stock"],
                            "52-week value screen",
                            "Short-term (1–4 weeks)",
                            float(row["Price"]),
                            float(row["Short Target"]),
                            float(row["Short SL"]),
                            fundamentals,
                            quote_as_of=last_date or None,
                        ),
                        make_buy_call(
                            f"{row['Stock']}.NS",
                            row["Stock"],
                            "52-week value screen",
                            "Long-term (6–18 months)",
                            float(row["Price"]),
                            float(row["Long Target"]),
                            float(row["Long SL"]),
                            fundamentals,
                            quote_as_of=last_date or None,
                        ),
                    ]
                )
                with cols[i]:
                    with st.container(border=True):
                        st.markdown(f"### 💎 {row['Stock']}")
                        st.metric("CMP", f"₹{row['Price']}", delta=f"{row['Dist %']}% from 52W Low", delta_color="inverse")
                        st.write(f"**52W Low:** ₹{row['52W Low']} | **52W High:** ₹{row['52W High']}")
                        st.success(f"**{row['Technical Verdict']}**")
                        st.caption(f"⚡ **Setup:** {row['Technical Setup']}")
                        st.caption(format_fundamental_assessment(fundamentals))
                        st.markdown("---")
                        st.markdown("**⚡ Short-Term (1–4 Wks):**")
                        st.write(f"- **Buy Range:** ₹{row['Price']}")
                        st.write(f"- **Stop-Loss:** ₹{row['Short SL']}")
                        st.write(f"- **Target:** ₹{row['Short Target']}")
                        st.markdown("**🏛️ Long-Term (6–18 Mos):**")
                        st.write(f"- **Stop-Loss:** ₹{row['Long SL']}")
                        st.write(f"- **Target:** ₹{row['Long Target']}")
            register_buy_calls(value_buy_calls)
        else:
            st.info("No candidates currently fulfill both the 52-week support threshold AND the bullish technical buy criteria.")

    render_movers_dashboard()

# ==============================================================================
# TAB 2: UNIVERSAL INTERACTIVE STOCK CHATBOT (INPUT-LOCKED DURING PROCESSING)
# ==============================================================================
elif active_tab == "💬 Stock Chatbot":
    st.subheader("💬 Universal AI Stock & Market Advisor")

    if st.session_state.active_stock.get("company"):
        st.caption(f"📍 Active Context: **{st.session_state.active_stock['company']}** (`{st.session_state.active_stock['symbol']}`) | Ask follow-ups or introduce any new stock.")
    else:
        st.caption("Real-time technical indicators, live price discovery, and multi-turn financial dialogue.")

    if "chat_history" not in st.session_state:
        st.session_state.chat_history = [
            {"role": "assistant", "content": "Hello! I am your real-time Indian Equities Assistant. You can ask consecutive questions in the same context, for example:\n1. *'What is current year profit of KEI Wires?'*\n2. *'Is it safe to buy it now?'*\n\nOr ask about a new stock whenever you like!"}
        ]

    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    chat_placeholder = "Processing answer, please wait..." if st.session_state.is_generating else "Ask any share market question..."
    user_prompt = st.chat_input(
        chat_placeholder,
        disabled=st.session_state.is_generating
    )

    if user_prompt and not st.session_state.is_generating:
        st.session_state.chat_history.append({"role": "user", "content": user_prompt})
        with st.chat_message("user"):
            st.markdown(user_prompt)

        st.session_state.is_generating = True

        with st.chat_message("assistant"):
            with st.status("⏳ **Processing now...** Fetching live NSE metrics & analyzing data", expanded=True) as status_box:
                time_module.sleep(0.3)
                status_box.update(label="⚡ Generating analysis...", state="running")
                response_generator = stream_chatbot_response(user_prompt)
                full_response = st.write_stream(response_generator)
                status_box.update(label="✅ Analysis complete", state="complete", expanded=False)

            st.session_state.chat_history.append({"role": "assistant", "content": full_response})

        st.session_state.is_generating = False
        st.rerun()

# ==============================================================================
# TAB 3: LIVE IPOs & GMP TRACKER
# ==============================================================================
elif active_tab == "🚀 IPO Hub":
    @st.fragment(run_every=60)
    def render_live_ipo_dashboard():
        h_col1, h_col2 = st.columns([3, 1])
        with h_col1:
            st.subheader("Upcoming and ongoing IPOs")
            st.caption(
                "Issue schedules and issuer financials are checked against public IPO records. "
                "GMP is an unofficial grey-market estimate, not a traded exchange price. "
                "Applications closing today are removed after 5 PM IST."
            )
        with h_col2:
            if st.button("Refresh IPO data", icon=":material/refresh:", use_container_width=True):
                fetch_live_ipo_gmp.clear()
                st.rerun()

        try:
            ipo_df, ipo_message = fetch_live_ipo_gmp()
        except requests.RequestException as exc:
            st.error(f"Could not load live IPO data: {exc}")
            return
        except (ValueError, KeyError) as exc:
            st.error(f"The live IPO feed could not be parsed: {exc}")
            return

        if not ipo_df.empty:
            now_ist = datetime.now(IST)
            ipo_df = ipo_df[
                ipo_df["Close Date"].apply(
                    lambda close_date: is_ipo_application_open(close_date, now_ist)
                )
            ].copy()

        if ipo_message and not ipo_df.empty:
            st.warning(ipo_message)

        if not ipo_df.empty:
            f1, f2, f3 = st.columns([1.5, 1.5, 2])
            with f1:
                status_filter = st.selectbox(
                    "Issue status",
                    ["All open and upcoming", "Ongoing (Closing Today)", "Ongoing (Open)", "Upcoming"],
                    key="ipo_status_flt"
                )
            with f2:
                cat_filter = st.selectbox(
                    "Issue category",
                    ["All", "Mainboard", "SME"],
                    key="ipo_cat_flt"
                )
            with f3:
                rec_filter = st.selectbox(
                    "Screening call",
                    ["All calls", "APPLY", "AVOID"],
                    key="ipo_rec_flt_v3"
                )

            filtered = ipo_df.copy()
            if status_filter != "All open and upcoming":
                filtered = filtered[filtered["Status"] == status_filter]
            if cat_filter != "All":
                filtered = filtered[filtered["Type"] == cat_filter]
            if rec_filter != "All calls":
                filtered = filtered[filtered["Recommendation"] == rec_filter]

            if not filtered.empty:
                status_order = {"Ongoing (Closing Today)": 0, "Ongoing (Open)": 1, "Upcoming": 2}
                filtered["_status_order"] = filtered["Status"].map(status_order)
                filtered = filtered.sort_values(
                    ["_status_order", "Close Date", "Company"],
                    ascending=[True, True, True],
                )
                fetched_at = filtered["Page Fetched At"].iloc[0]
                st.caption(
                    f"Last fetched: **{fetched_at}** | Automatic refresh: every 5 minutes. "
                    "A source may update its GMP less frequently."
                )
                for _, row in filtered.iterrows():
                    with st.container(border=True):
                        h1, h2, h3 = st.columns([2.5, 1.5, 2])
                        with h1:
                            st.markdown(f"### {row['Company']}")
                            close_date = row["Close Date"].strftime("%d %b %Y")
                            open_date = row["Open Date"].strftime("%d %b %Y")
                            st.caption(
                                f"**{row['Status']}** · {row['Type']} · "
                                f"Opens {open_date} · Closes {close_date}"
                            )
                        with h2:
                            gmp = row["GMP (₹)"]
                            gain = row["Est Gain %"]
                            st.metric(
                                "Latest GMP (unofficial)",
                                f"₹{gmp:,.2f}" if pd.notna(gmp) else "Unavailable",
                                delta=f"Estimated gain {gain:.2f}%" if pd.notna(gain) else None,
                            )
                        with h3:
                            if row["Recommendation"] == "APPLY":
                                st.success("### APPLY")
                            else:
                                st.error("### AVOID")
                            st.caption(row["Analysis & Rationale"])

                        d1, d2 = st.columns([1, 2])
                        with d1:
                            issue_price = row["Issue Price (₹)"]
                            st.write(
                                "**Price band:** "
                                f"{row['Price Band'] if row['Price Band'] != 'Not reported' else (f'₹{issue_price:,.2f}' if pd.notna(issue_price) else 'Not reported')}"
                            )
                            st.write(f"**Lot size:** {row['Lot Size']}")
                            st.write(f"**Issue size:** {row['Issue Size']}")
                        with d2:
                            st.write(f"**Fundamentals:** {row['Fundamental Summary']}")
                            if row["Fundamental Source Status"] != "Issuer financial tables loaded":
                                st.caption(f"Data note: {row['Fundamental Source Status']}")
                            link1, link2 = st.columns(2)
                            with link1:
                                st.link_button(
                                    "Issuer financials and offer details",
                                    row["Fundamental Source URL"],
                                    use_container_width=True,
                                )
                            with link2:
                                st.link_button(
                                    "GMP source",
                                    row["GMP Source URL"],
                                    use_container_width=True,
                                )
            else:
                st.info("No open or upcoming IPOs match the selected filters.")
            st.caption(
                "Rule-based screening only: APPLY requires positive latest reported annual revenue and profit, "
                "at least two passing reported profitability/leverage checks, and an indicative GMP gain of "
                "at least 10%, with no major financial red flags or sharp annual declines. "
                "Missing or weak evidence results in AVOID. This is educational screening, not "
                "personalized investment advice; verify the RHP and your own risk tolerance before applying."
            )
        else:
            st.info(ipo_message or "There are no upcoming or ongoing IPOs with an application window still open.")

    render_live_ipo_dashboard()

# ==============================================================================
# TAB 4: DEEP-DIVE SINGLE STOCK ANALYZER (SME & CANDLE PRIORITIZED)
# ==============================================================================
elif active_tab == "🔍 Deep Dive":
    st.subheader("🔍 Single Stock Deep Dive & Buy/Sell Call")

    c_search, c_exch = st.columns([3, 1])
    with c_search:
        selected_stock = st.selectbox(
            "Type or select stock symbol:",
            options=ALL_NSE_STOCKS,
            index=None,
            placeholder="Type symbol (e.g. RELIANCE, COMMITTED, TCS, INFY, KEI)...",
            accept_new_options=True
        )
    with c_exch:
        exchange = st.selectbox("Exchange:", ["NSE (.NS)", "BSE (.BO)"])

    suffix = ".NS" if "NSE" in exchange else ".BO"

    if st.button("Generate Signal & Analysis", type="primary"):
        if not selected_stock:
            st.warning("Please select or enter a stock ticker first.")
        else:
            raw_input = selected_stock.strip().upper()
            clean_ticker = re.sub(r"\.(NSE|NS|BSE|BO)$", "", raw_input).strip()
            ticker_symbol = f"{clean_ticker}{suffix}"

            with st.spinner(f"Evaluating {ticker_symbol}..."):
                try:
                    stock = yf.Ticker(ticker_symbol)
                    hist = stock.history(period="1y")

                    if hist.empty or len(hist) < 5:
                        sme_symbol = f"{clean_ticker}-SM.NS"
                        sme_stock = yf.Ticker(sme_symbol)
                        sme_hist = sme_stock.history(period="1y")
                        if not sme_hist.empty and len(sme_hist) >= 5:
                            ticker_symbol = sme_symbol
                            stock = sme_stock
                            hist = sme_hist

                    if hist.empty or len(hist) < 5:
                        resolved_sym, _ = resolve_ticker_online(clean_ticker)
                        if resolved_sym:
                            ticker_symbol = resolved_sym
                            stock = yf.Ticker(ticker_symbol)
                            hist = stock.history(period="1y")

                    if hist.empty or len(hist) < 5:
                        st.error(f"Could not retrieve trading data for '{clean_ticker}'. Please verify the stock symbol.")
                        st.stop()

                    live_price = float(hist["Close"].iloc[-1])
                    prev_close = float(hist["Close"].iloc[-2]) if len(hist) >= 2 else live_price

                    day_change = live_price - prev_close
                    day_pct = (day_change / prev_close) * 100 if prev_close else 0.0
                    info = stock.info or {}
                    fundamentals = assess_fundamentals(info)

                    hist["RSI"] = ta.momentum.RSIIndicator(hist["Close"], window=14).rsi()
                    hist["SMA_50"] = ta.trend.SMAIndicator(hist["Close"], window=50).sma_indicator()
                    hist["SMA_200"] = ta.trend.SMAIndicator(hist["Close"], window=200).sma_indicator()
                    macd = ta.trend.MACD(hist["Close"])
                    hist["MACD"] = macd.macd()
                    hist["MACD_Signal"] = macd.macd_signal()

                    latest = hist.iloc[-1]
                    rsi = float(latest["RSI"]) if pd.notna(latest["RSI"]) else 50.0
                    sma_50 = float(latest["SMA_50"]) if pd.notna(latest["SMA_50"]) else live_price
                    sma_200 = float(latest["SMA_200"]) if pd.notna(latest["SMA_200"]) else None

                    sentiment_score, news_items = fetch_cloud_safe_news(stock, clean_ticker)

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

                    if debt_equity is not None and not fundamentals["is_financial_company"]:
                        if debt_equity < 100:
                            lt_score += 1
                            lt_reasons.append("Conservative leverage: Debt-to-Equity is low (< 1.0).")
                        else:
                            lt_score -= 1
                            lt_reasons.append("Elevated debt leverage on balance sheet.")
                    elif fundamentals["is_financial_company"]:
                        lt_reasons.append("Debt-to-equity is not used for financial-sector companies.")

                    if sma_200 is not None:
                        if live_price > sma_200:
                            lt_score += 1
                            lt_reasons.append(f"Structural uptrend: Price holds above 200-day SMA (₹{sma_200:.2f}).")
                        else:
                            lt_score -= 1
                            lt_reasons.append(f"Macro downtrend: Price trades below 200-day SMA (₹{sma_200:.2f}).")
                    else:
                        lt_reasons.append("200-day SMA unavailable; price trend was not scored.")

                    lt_call = "BUY" if lt_score >= 1 else ("SELL" if lt_score <= -1 else "HOLD")
                    if st_call == "BUY" and not fundamentals["buy_eligible"]:
                        st_call = "HOLD"
                        st_reasons.append(
                            f"BUY blocked: fundamentals {fundamentals['status'].lower()} — {fundamentals['summary']}."
                        )
                    if lt_call == "BUY" and not fundamentals["buy_eligible"]:
                        lt_call = "HOLD"
                        lt_reasons.append(
                            f"BUY blocked: fundamentals {fundamentals['status'].lower()} — {fundamentals['summary']}."
                        )

                    st.markdown("---")
                    display_name = info.get("longName") or info.get("shortName") or ticker_symbol
                    st.subheader(f"{display_name} (`{ticker_symbol}`)")
                    st.caption(format_fundamental_assessment(fundamentals))
                    st.metric(
                        label="Latest available price snapshot",
                        value=f"₹{live_price:,.2f}",
                        delta=f"{day_change:+,.2f} ({day_pct:+.2f}%)"
                    )

                    r1, r2 = st.columns(2)
                    deep_dive_buy_calls = []
                    with r1:
                        st.markdown("#### ⚡ Short-Term Call")
                        if st_call == "BUY": st.success("### ACTION: BUY")
                        elif st_call == "SELL": st.error("### ACTION: SELL")
                        else: st.warning("### ACTION: HOLD")
                        for r in st_reasons: st.write(f"- {r}")
                        if st_call == "BUY":
                            short_target = round(live_price * 1.08, 2)
                            short_stop = round(live_price * 0.95, 2)
                            st.write(f"- **Target:** ₹{short_target:,.2f} | **Stop-loss:** ₹{short_stop:,.2f}")
                            deep_dive_buy_calls.append(
                                make_buy_call(
                                    ticker_symbol,
                                    display_name,
                                    "Deep Dive",
                                    "Short-term",
                                    live_price,
                                    short_target,
                                    short_stop,
                                    fundamentals,
                                    quote_as_of=hist.index[-1].strftime("%d %b %Y"),
                                )
                            )

                    with r2:
                        st.markdown("#### 🏛️ Long-Term Call")
                        if lt_call == "BUY": st.success("### ACTION: BUY")
                        elif lt_call == "SELL": st.error("### ACTION: SELL")
                        else: st.warning("### ACTION: HOLD")
                        for r in lt_reasons: st.write(f"- {r}")
                        if lt_call == "BUY":
                            long_target = round(live_price * 1.25, 2)
                            long_stop = round(live_price * 0.90, 2)
                            st.write(f"- **Target:** ₹{long_target:,.2f} | **Stop-loss:** ₹{long_stop:,.2f}")
                            deep_dive_buy_calls.append(
                                make_buy_call(
                                    ticker_symbol,
                                    display_name,
                                    "Deep Dive",
                                    "Long-term",
                                    live_price,
                                    long_target,
                                    long_stop,
                                    fundamentals,
                                    quote_as_of=hist.index[-1].strftime("%d %b %Y"),
                                )
                            )
                    register_buy_calls(deep_dive_buy_calls)

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

# ==============================================================================
# TAB 5: VIRTUAL BUY-CALL TRACKER
# ==============================================================================
elif active_tab == "📒 Virtual Portfolio":
    st.subheader("📒 Virtual BUY-call portfolio")
    st.caption(
        f"Every eligible BUY call is simulated with ₹{VIRTUAL_INVESTMENT:,.0f}. "
        "P&L and win rate use the latest available daily price, not intraday target/stop history."
    )
    bin_id = get_private_setting("JSONBIN_BIN_ID")
    master_key = get_private_setting("JSONBIN_MASTER_KEY")
    if not bin_id or not master_key:
        st.info("Configure JSONBIN_BIN_ID and JSONBIN_MASTER_KEY to view the shared portfolio.")
    else:
        refresh_col, _ = st.columns([1, 4])
        with refresh_col:
            if st.button("🔄 Refresh portfolio"):
                get_latest_trade_prices.clear()
        try:
            trades = fetch_virtual_trades(bin_id, master_key)
        except (requests.RequestException, ValueError, KeyError) as exc:
            st.error(f"Could not load the JSONBin portfolio: {exc}")
            trades = []
            prices = {}
        else:
            tickers = tuple(sorted({trade["ticker"] for trade in trades if trade.get("ticker")}))
            try:
                prices = get_latest_trade_prices(tickers)
            except Exception as exc:
                st.error(f"Could not retrieve latest stock prices: {exc}")
                prices = {}

        if trades:
            portfolio_rows = []
            total_invested = 0.0
            total_current_value = 0.0
            profitable_trades = 0
            priced_trades = 0
            for trade in trades:
                ticker = trade.get("ticker", "")
                entry_price = float(trade.get("entry_price") or 0)
                investment = float(trade.get("virtual_investment") or VIRTUAL_INVESTMENT)
                quantity = float(trade.get("quantity") or 0)
                current_price = prices.get(ticker)
                current_value = current_price * quantity if current_price is not None else None
                pnl = current_value - investment if current_value is not None else None
                if pnl is not None:
                    priced_trades += 1
                    total_invested += investment
                    total_current_value += current_value
                    profitable_trades += pnl > 0
                status = (
                    "Price unavailable"
                    if current_price is None
                    else "At/above target"
                    if current_price >= float(trade["target_price"])
                    else "At/below stop"
                    if current_price <= float(trade["stop_loss"])
                    else "Open"
                )
                portfolio_rows.append(
                    {
                        "Call time (IST)": trade.get("called_at", ""),
                        "Quote date": trade.get("quote_as_of", ""),
                        "Stock": trade.get("company", ticker),
                        "Source": trade.get("source", ""),
                        "Horizon": trade.get("horizon", ""),
                        "Entry (₹)": entry_price,
                        "Target (₹)": float(trade["target_price"]),
                        "Stop-loss (₹)": float(trade["stop_loss"]),
                        "Latest (₹)": current_price,
                        "Virtual amount (₹)": investment,
                        "P&L (₹)": pnl,
                        "Status": status,
                        "Fundamentals": trade.get("fundamental_status", "Unknown"),
                    }
                )

            if priced_trades:
                metric_cols = st.columns(3)
                metric_cols[0].metric("Virtual amount priced", f"₹{total_invested:,.2f}")
                metric_cols[1].metric(
                    "Latest virtual value",
                    f"₹{total_current_value:,.2f}",
                    delta=f"₹{total_current_value - total_invested:,.2f}",
                )
                metric_cols[2].metric(
                    "Currently profitable",
                    f"{profitable_trades}/{priced_trades}",
                    delta=f"{profitable_trades / priced_trades:.0%} mark-to-market win rate",
                )
            st.dataframe(
                pd.DataFrame(portfolio_rows),
                width="stretch",
                hide_index=True,
            )
        else:
            st.info("No virtual BUY calls have been saved to this JSONBin yet.")

# --- MANDATORY REGULATORY & EDUCATIONAL DISCLAIMER ---
st.markdown("---")
st.warning(
    "⚠️ **Disclaimer:** This tool is purely for educational purposes. "
    "Please consult with a SEBI-registered advisor before buying or selling any securities."
)