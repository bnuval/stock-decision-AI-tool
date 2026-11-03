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
    evaluate_stock_signal,
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

# --- APP THEME AND RESPONSIVE NAVIGATION ---
st.markdown("""
<style>
    header[data-testid="stHeader"] {
        display: none !important;
        height: 0px !important;
    }

    .block-container {
        max-width: 1440px !important;
        padding: 8.6rem 2rem 4rem !important;
        margin: 0 auto !important;
    }

    .pinned-master-bar {
        position: fixed !important;
        top: 0 !important;
        left: 0 !important;
        width: 100vw !important;
        min-height: 7.4rem !important;
        background: linear-gradient(112deg, #10243b 0%, #173754 68%, #164f59 100%) !important;
        z-index: 1000 !important;
        display: flex !important;
        flex-direction: column !important;
        justify-content: center !important;
        gap: 0.65rem !important;
        padding: 0.75rem max(1.25rem, calc((100vw - 1360px) / 2)) 0.65rem !important;
        border-bottom: 3px solid #2bb7a5 !important;
        box-shadow: 0 8px 26px rgba(16, 36, 59, 0.14) !important;
    }

    .brand-row {
        display: flex !important;
        align-items: center !important;
        gap: 0.75rem !important;
        min-width: 0 !important;
    }

    .brand-mark {
        width: 2.45rem !important;
        height: 2.45rem !important;
        display: grid !important;
        place-items: center !important;
        flex: 0 0 auto !important;
        border: 1px solid rgba(255, 255, 255, 0.18) !important;
        border-radius: 0.8rem !important;
        background: rgba(255, 255, 255, 0.11) !important;
        font-size: 1.2rem !important;
    }

    .pinned-master-bar h2 {
        font-size: 1.18rem !important;
        font-weight: 700 !important;
        color: #ffffff !important;
        margin: 0 !important;
        padding: 0 !important;
        line-height: 1.2 !important;
        white-space: nowrap !important;
        overflow: hidden !important;
        text-overflow: ellipsis !important;
    }

    .pinned-master-bar .brand-copy h2 {
        color: #ffffff !important;
    }

    .pinned-master-bar p {
        font-size: 0.72rem !important;
        color: #c3d3df !important;
        margin: 0.18rem 0 0 !important;
        padding: 0 !important;
        white-space: nowrap !important;
        overflow: hidden !important;
        text-overflow: ellipsis !important;
    }

    .brand-meta {
        margin-left: auto !important;
        color: #d3e2ea !important;
        font-size: 0.76rem !important;
        white-space: nowrap !important;
    }

    .brand-meta strong {
        color: #ffffff !important;
        font-size: 0.9rem !important;
        margin-right: 0.2rem !important;
    }

    .nav-tabs-wrapper {
        display: flex !important;
        flex-direction: row !important;
        flex-wrap: nowrap !important;
        gap: 0.45rem !important;
        overflow-x: auto !important;
        overflow-y: hidden !important;
        padding-bottom: 0.05rem !important;
        -webkit-overflow-scrolling: touch !important;
        scrollbar-width: none !important;
    }
    .nav-tabs-wrapper::-webkit-scrollbar {
        display: none !important;
    }

    .nav-tab-btn {
        display: inline-block !important;
        text-decoration: none !important;
        background-color: rgba(255, 255, 255, 0.08) !important;
        border: 1px solid rgba(255, 255, 255, 0.16) !important;
        border-radius: 0.55rem !important;
        padding: 0.38rem 0.78rem !important;
        font-size: 0.78rem !important;
        font-weight: 500 !important;
        color: #e2edf3 !important;
        white-space: nowrap !important;
        transition: background-color 0.15s ease, border-color 0.15s ease !important;
    }

    .nav-tab-btn:hover {
        background-color: rgba(255, 255, 255, 0.16) !important;
        border-color: rgba(255, 255, 255, 0.38) !important;
        color: #ffffff !important;
    }

    .nav-tab-btn.active {
        background-color: #14877f !important;
        border-color: #55c5b7 !important;
        color: #ffffff !important;
        font-weight: 600 !important;
    }

    .block-container h1,
    .block-container h2,
    .block-container h3 {
        letter-spacing: -0.025em !important;
        color: #18324b !important;
    }

    .block-container h3 {
        font-size: 1.45rem !important;
        margin-bottom: 0.25rem !important;
    }

    div[data-testid="stVerticalBlockBorderWrapper"] {
        border-radius: 0.9rem !important;
        border-color: #e0e7ef !important;
        box-shadow: 0 3px 14px rgba(25, 50, 75, 0.045) !important;
    }

    div[data-testid="stMetric"] {
        border: 1px solid #e2e8ef !important;
        border-radius: 0.8rem !important;
        padding: 0.9rem 1rem !important;
        background: #ffffff !important;
    }

    div[data-testid="stMetricLabel"] p {
        color: #66788a !important;
        font-size: 0.78rem !important;
        font-weight: 600 !important;
    }

    div[data-testid="stMetricValue"] {
        color: #18324b !important;
        font-weight: 650 !important;
    }

    .stButton > button,
    .stLinkButton > a {
        border-radius: 0.65rem !important;
        font-weight: 600 !important;
        transition: transform 0.15s ease, box-shadow 0.15s ease !important;
    }

    .stButton > button:hover,
    .stLinkButton > a:hover {
        transform: translateY(-1px) !important;
        box-shadow: 0 4px 12px rgba(20, 135, 127, 0.14) !important;
    }

    div[data-testid="stDataFrame"] {
        border: 1px solid #e0e7ef !important;
        border-radius: 0.75rem !important;
        overflow: hidden !important;
    }

    div[data-testid="stAlert"] {
        border-radius: 0.75rem !important;
    }

    .app-disclaimer {
        margin: 1.75rem 0 0 !important;
        padding: 0.9rem 1rem !important;
        border: 1px solid #f1d7a7 !important;
        border-left: 4px solid #d99a2b !important;
        border-radius: 0.7rem !important;
        background: #fffaf0 !important;
        color: #634b22 !important;
        font-size: 0.84rem !important;
    }

    @media (max-width: 768px) {
        .block-container {
            padding: 8.1rem 0.8rem 3rem !important;
        }
        .pinned-master-bar {
            min-height: 7.15rem !important;
            gap: 0.55rem !important;
            padding: 0.6rem 0.75rem 0.55rem !important;
        }
        .pinned-master-bar h2 {
            font-size: 1.02rem !important;
        }
        .pinned-master-bar p {
            font-size: 0.66rem !important;
        }
        .brand-mark {
            width: 2.15rem !important;
            height: 2.15rem !important;
        }
        .brand-meta { display: none !important; }
        .nav-tab-btn {
            padding: 0.34rem 0.62rem !important;
            font-size: 0.73rem !important;
        }
        .block-container h3 { font-size: 1.25rem !important; }
        div[data-testid="stMetric"] { padding: 0.7rem !important; }
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

# --- 5. SHARED TECHNICAL SIGNALS AND CONFIRMED BUY SCREEN ---
def calculate_stock_signal(history: pd.DataFrame, fundamentals: dict) -> dict:
    indicators = {
        "price": None,
        "sma_50": None,
        "sma_200": None,
        "rsi": None,
        "macd_bullish": None,
        "macd_bearish": None,
        "recent_bullish_cross": None,
        "volume_ratio": None,
        "breakout": None,
        "atr": None,
    }
    if history.empty or not {"Close", "High", "Low", "Volume"}.issubset(history.columns):
        return evaluate_stock_signal(indicators, fundamentals)

    history = (
        history[["Close", "High", "Low", "Volume"]]
        .apply(pd.to_numeric, errors="coerce")
        .dropna()
    )
    if history.empty:
        return evaluate_stock_signal(indicators, fundamentals)
    close = history["Close"].dropna()
    if close.empty:
        return evaluate_stock_signal(indicators, fundamentals)
    high = history["High"].reindex(close.index)
    low = history["Low"].reindex(close.index)
    volume = history["Volume"].reindex(close.index)
    indicators["price"] = float(close.iloc[-1])

    if len(close) >= 50:
        indicators["sma_50"] = float(close.rolling(50).mean().iloc[-1])
    if len(close) >= 200:
        indicators["sma_200"] = float(close.rolling(200).mean().iloc[-1])
        indicators["rsi"] = float(ta.momentum.RSIIndicator(close, window=14).rsi().iloc[-1])
        macd = ta.trend.MACD(close)
        macd_line = macd.macd()
        macd_signal = macd.macd_signal()
        if pd.notna(macd_line.iloc[-1]) and pd.notna(macd_signal.iloc[-1]):
            indicators["macd_bullish"] = bool(macd_line.iloc[-1] > macd_signal.iloc[-1])
            indicators["macd_bearish"] = bool(macd_line.iloc[-1] < macd_signal.iloc[-1])
            crosses = (macd_line > macd_signal) & (
                macd_line.shift(1) <= macd_signal.shift(1)
            )
            indicators["recent_bullish_cross"] = bool(crosses.tail(5).any())
        previous_volume = volume.iloc[-21:-1].mean()
        if pd.notna(previous_volume) and previous_volume > 0 and pd.notna(volume.iloc[-1]):
            indicators["volume_ratio"] = float(volume.iloc[-1] / previous_volume)
        previous_high = high.iloc[-21:-1].max()
        if len(high) >= 21 and pd.notna(previous_high):
            indicators["breakout"] = bool(close.iloc[-1] > previous_high)
        atr = ta.volatility.AverageTrueRange(
            high=high,
            low=low,
            close=close,
            window=14,
        ).average_true_range()
        if pd.notna(atr.iloc[-1]):
            indicators["atr"] = float(atr.iloc[-1])

    return evaluate_stock_signal(indicators, fundamentals)


def extract_ticker_history(raw: pd.DataFrame, ticker: str) -> pd.DataFrame:
    if isinstance(raw.columns, pd.MultiIndex):
        for level in range(raw.columns.nlevels):
            if ticker in raw.columns.get_level_values(level):
                history = raw.xs(ticker, axis=1, level=level)
                if {"Close", "High", "Low", "Volume"}.issubset(history.columns):
                    return history
        return pd.DataFrame()
    return raw if {"Close", "High", "Low", "Volume"}.issubset(raw.columns) else pd.DataFrame()


@st.cache_data(ttl=300)
def screen_confirmed_buy_picks(universe):
    universe_symbols = set(universe)
    candidate_symbols = [
        "HINDUNILVR", "DABUR", "ITC", "IRCTC", "INFY", "TCS", "HDFCBANK",
        "KOTAKBANK", "ASIANPAINT", "MARUTI", "SUNPHARMA", "WIPRO", "TATAMOTORS",
        "RELIANCE", "LT", "ICICIBANK", "AXISBANK", "SBIN"
    ]
    candidate_symbols = [symbol for symbol in candidate_symbols if symbol in universe_symbols]
    if not candidate_symbols:
        return pd.DataFrame()
    tickers = [f"{s}.NS" for s in candidate_symbols]

    try:
        raw = yf.download(
            tickers,
            period="2y",
            interval="1d",
            progress=False,
            auto_adjust=True,
            group_by="ticker",
        )
        if raw.empty:
            return pd.DataFrame()

        results = []

        for symbol in candidate_symbols:
            t = f"{symbol}.NS"
            history = extract_ticker_history(raw, t)
            if len(history) < 200:
                continue
            technical_signal = calculate_stock_signal(
                history,
                {"buy_eligible": True, "status": "Pass"},
            )
            if technical_signal["swing_action"] != "BUY":
                continue
            fundamentals = get_fundamental_snapshot(t)
            signal = calculate_stock_signal(history, fundamentals)
            if signal["swing_action"] != "BUY":
                continue

            close = history["Close"].dropna()
            recent = history.loc[close.index].tail(252)
            current_price = float(close.iloc[-1])
            low_52w = float(recent["Low"].min())
            high_52w = float(recent["High"].max())
            results.append({
                "Stock": symbol,
                "Price": current_price,
                "52W Low": round(low_52w, 2),
                "52W High": round(high_52w, 2),
                "Dist %": round((current_price - low_52w) / low_52w * 100, 2),
                "RSI": round(float(ta.momentum.RSIIndicator(close, window=14).rsi().iloc[-1]), 1),
                "Technical Setup": "Trend aligned; 20-session breakout, recent MACD cross, RSI and volume confirmed.",
                "Technical Verdict": "🟢 Confirmed swing setup",
                "Fundamental Status": fundamentals["status"],
                "Fundamental Summary": fundamentals["summary"],
                "Short SL": signal["swing_stop"],
                "Short Target": signal["swing_target"],
                "Long SL": signal["long_stop"],
                "Long Target": signal["long_target"],
            })

        if results:
            df = pd.DataFrame(results).sort_values(by="RSI", ascending=True)
            return df.head(3).reset_index(drop=True)
    except Exception as exc:
        st.warning(f"Could not complete the confirmed-signal scan: {exc}")
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
        "technical_signal": None,
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
            hist = stock.history(period="2y")

            if hist.empty:
                sme_sym = ticker_found.replace(".NS", "-SM.NS")
                sme_stock = yf.Ticker(sme_sym)
                sme_hist = sme_stock.history(period="2y")
                if not sme_hist.empty:
                    stock = sme_stock
                    hist = sme_hist
                    info = stock.info or {}
                    context_dict["fundamentals"] = assess_fundamentals(info)

            if not hist.empty:
                context_dict["price"] = float(hist["Close"].iloc[-1])
                context_dict["quote_as_of"] = hist.index[-1].strftime("%d %b %Y")
                signal = calculate_stock_signal(hist, context_dict["fundamentals"])
                context_dict["technical_signal"] = signal
                rsi_value = ta.momentum.RSIIndicator(hist["Close"], window=14).rsi().iloc[-1]
                sma_value = ta.trend.SMAIndicator(hist["Close"], window=50).sma_indicator().iloc[-1]
                context_dict["rsi"] = float(rsi_value) if pd.notna(rsi_value) else None
                context_dict["sma_50"] = float(sma_value) if pd.notna(sma_value) else None

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
            signal = context_dict["technical_signal"]
            if signal:
                lines.append(
                    f"- Verified signal engine: swing {signal['swing_action']}; "
                    f"long-term {signal['long_term_action']}."
                )
                lines.append(
                    "- Engine reasons: " + "; ".join(signal["reasons"])
                )
                if signal["swing_entry"] is not None:
                    lines.append(
                        f"- ATR-based swing entry / target / stop: "
                        f"₹{signal['swing_entry']:,.2f} / ₹{signal['swing_target']:,.2f} / "
                        f"₹{signal['swing_stop']:,.2f}."
                    )
                if signal["long_target"] is not None:
                    lines.append(
                        f"- ATR-based long-term target / stop: "
                        f"₹{signal['long_target']:,.2f} / ₹{signal['long_stop']:,.2f}."
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
        Treat the verified signal engine as authoritative for every actionable call.
        Do not issue BUY unless the selected horizon's engine action is BUY.
        Do not issue SELL unless the engine says EXIT / AVOID; SELL means exit/avoid an existing position, never short-selling.
        If the user asks for an actionable stock call, end with exactly one line:
        Signal: BUY, Signal: HOLD, or Signal: SELL. Use the ATR-based engine levels only.
        Never invent target/stop levels or report BUY when history is insufficient.
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
            ai_reply = record_chatbot_buy_if_eligible(ai_reply, context, user_query)
            for word in ai_reply.split(" "):
                yield word + " "
                time_module.sleep(0.01)
            return
        else:
            yield f"⚠️ *(AI API Notice: {ai_reply}. Switching to built-in market analysis engine...)*\n\n"

    static_reply = process_universal_chatbot_static(user_query, context)
    static_reply = record_chatbot_buy_if_eligible(static_reply, context, user_query)
    for word in static_reply.split(" "):
        yield word + " "
        time_module.sleep(0.015)


def record_chatbot_buy_if_eligible(reply: str, context: dict, user_query: str = "") -> str:
    signal_match = re.search(
        r"(?im)^\s*(?:[-*]\s*)?(?:\*\*)?Signal(?:\*\*)?\s*:\s*(BUY|HOLD|SELL)\b",
        reply,
    )
    if not signal_match:
        actionable_query = re.search(
            r"\b(?:buy|sell|recommend|should i|target|trade)\b",
            user_query,
            re.IGNORECASE,
        )
        unsupported_action = re.search(r"\b(?:BUY|SELL)\b", reply, re.IGNORECASE)
        is_confirmed_watchlist = reply.startswith(
            "### 🎯 Stocks passing the confirmed swing screen"
        )
        if actionable_query and unsupported_action and not is_confirmed_watchlist:
            return (
                "The response did not include a valid, engine-checked signal, so no "
                "actionable BUY or SELL is issued. Review the stock's Deep Dive signal "
                "or provide a specific stock for evaluation.\n\n**Signal: HOLD**"
            )
        return reply

    requested_action = signal_match.group(1).upper()
    signal = context.get("technical_signal") or {}
    long_term = bool(re.search(r"\blong[\s-]*term\b", user_query, re.IGNORECASE))
    engine_action = signal.get(
        "long_term_action" if long_term else "swing_action",
        "HOLD / WATCH",
    )
    if requested_action == "BUY" and engine_action != "BUY":
        reasons = signal.get("reasons") or ["At least 200 sessions of valid price and volume history are required."]
        return (
            "### Verified signal check\n\n"
            f"The requested BUY is withheld: the {('long-term' if long_term else 'swing')} "
            f"engine currently says **{engine_action}**.\n\n"
            + "\n".join(f"- {reason}" for reason in reasons)
            + "\n\n**Signal: HOLD**"
        )
    if requested_action == "SELL" and not signal.get("exit_signal", False):
        return (
            "### Verified signal check\n\n"
            "The engine does not confirm an EXIT / AVOID condition. This tool does not "
            "recommend short-selling.\n\n**Signal: HOLD**"
        )
    if requested_action != "BUY":
        if requested_action == "SELL":
            return f"{reply}\n\n**Note:** SELL here means exit/avoid an existing position, not short-selling."
        return reply

    ticker = context.get("ticker")
    entry_price = context.get("price")
    fundamentals = context.get("fundamentals") or assess_fundamentals({})
    entry_price = signal.get("swing_entry")
    target_price = signal.get("long_target" if long_term else "swing_target")
    stop_loss = signal.get("long_stop" if long_term else "swing_stop")
    if not ticker or entry_price is None or target_price is None or stop_loss is None:
        return (
            "### Verified signal check\n\n"
            "The BUY cannot be recorded because verified price history or ATR-based "
            "risk levels are unavailable.\n\n**Signal: HOLD**"
        )
    reply = re.sub(
        r"(?im)^.*(?:target(?:\s+price)?|stop[\s-]*loss).*$",
        "",
        reply,
    ).strip()
    register_buy_calls(
        [
            make_buy_call(
                ticker,
                context.get("company") or ticker,
                "Stock Chatbot",
                "Long-term" if long_term else "Short-term swing",
                float(entry_price),
                float(target_price),
                float(stop_loss),
                fundamentals,
                quote_as_of=context.get("quote_as_of"),
            )
        ]
    )
    return (
        f"{reply}\n\n"
        "**Verified engine signal: BUY.**\n"
        f"**Verified ATR-based paper trade:** ₹{float(entry_price):,.2f} entry | "
        f"₹{float(target_price):,.2f} target | ₹{float(stop_loss):,.2f} stop-loss | "
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

        confirmed_picks = screen_confirmed_buy_picks(ALL_NSE_STOCKS)
        is_open, _, _ = get_market_status()

        resp = "### 🎯 Stocks passing the confirmed swing screen\n\n"
        buy_calls = []
        for index, (_, row) in enumerate(confirmed_picks.iterrows(), 1):
            symbol = row["Stock"]
            entry_price = float(row["Price"])
            fundamentals = get_fundamental_snapshot(f"{symbol}.NS")
            target_price = float(row["Short Target"])
            stop_loss = float(row["Short SL"])
            buy_calls.append(
                make_buy_call(
                    f"{symbol}.NS",
                    symbol,
                    "Stock Chatbot confirmed screen",
                    "Short-term swing",
                    entry_price,
                    target_price,
                    stop_loss,
                    fundamentals,
                )
            )
            resp += (
                f"**{index}. `{symbol}` — short-term swing**\n"
                "- **Confirmed setup:** BUY\n"
                f"- **Entry snapshot / target / stop:** ₹{entry_price:,.2f} / "
                f"₹{target_price:,.2f} / ₹{stop_loss:,.2f}\n"
                f"- **Technical setup:** {row['Technical Setup']}\n"
                f"- {format_fundamental_assessment(fundamentals)}\n\n"
            )

        if confirmed_picks.empty:
            resp += (
                "No candidate currently passes all trend, breakout, momentum, volume, "
                "and fundamental checks. Daily movers alone are not buy recommendations.\n\n"
            )
        timing_note = "Market is open." if is_open else "Market is closed; prices may be from the last completed session."
        resp += (
            f"> {timing_note} ATR-based stop and target levels are heuristic estimates, "
            f"not guarantees. Each eligible BUY uses ₹{VIRTUAL_INVESTMENT:,.0f} of virtual capital."
        )
        register_buy_calls(buy_calls)
        return resp

    if comp and any(w in upper for w in [
        "INCREASE", "HIKE", "RISE", "UP", "DOWN", "FALL", "TARGET",
        "SHORT PERIOD", "SHORT TERM", "LONG TERM", "BUY", "SELL", "SAFE",
        "HOLD", "INVEST",
    ]):
        curr_price = context.get("price") or 0.0
        fundamentals = context.get("fundamentals") or assess_fundamentals({})
        technical_signal = context.get("technical_signal") or {}
        long_term = bool(re.search(r"\blong[\s-]*term\b", upper))
        engine_action = technical_signal.get(
            "long_term_action" if long_term else "swing_action",
            "HOLD / WATCH",
        )
        display_action = "SELL" if engine_action == "EXIT / AVOID" else (
            "BUY" if engine_action == "BUY" else "HOLD"
        )
        target_key = "long_target" if long_term else "swing_target"
        stop_key = "long_stop" if long_term else "swing_stop"
        reasons_key = "long_term_reasons" if long_term else "reasons"
        reasons = technical_signal.get(reasons_key) or [
            "At least 200 sessions of valid price and volume history are required."
        ]
        target_price = technical_signal.get(target_key)
        stop_loss = technical_signal.get(stop_key)
        rsi_value = context.get("rsi")
        sma_50 = context.get("sma_50")

        return (
            f"### {'Long-Term' if long_term else 'Swing'} Outlook for **{comp}** (`{ticker}`)\n\n"
            f"- **Latest available price snapshot:** ₹{curr_price:,.2f}\n"
            f"- **14-Day RSI:** {f'{rsi_value:.1f}' if rsi_value is not None else 'Unavailable'}\n"
            f"- **50-Day SMA:** {f'₹{sma_50:,.2f}' if sma_50 is not None else 'Unavailable'}\n"
            f"- **Horizon:** {'Long-term' if long_term else 'Swing'}\n\n"
            f"**Engine verdict:** **{engine_action}**\n\n"
            + "\n".join(f"- {reason}" for reason in reasons)
            + (
                f"\n\n**ATR-based target / stop:** ₹{target_price:,.2f} / ₹{stop_loss:,.2f}"
                if display_action == "BUY" and target_price is not None and stop_loss is not None
                else ""
            )
            + f"\n\n{format_fundamental_assessment(fundamentals)}\n\n**Signal: {display_action}**"
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
            f"**Fundamental profile:** **{health}** based on available ROE data. "
            "Fundamentals alone do not establish an entry signal; check the technical "
            "horizon signal before considering a trade.\n\n"
            f"{format_fundamental_assessment(context.get('fundamentals') or assess_fundamentals({}))}"
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
    <div class="brand-row">
        <div class="brand-mark">⚡</div>
        <div class="brand-copy">
            <h2>NSE Pulse</h2>
            <p>Market intelligence · IPO insights · virtual tracking</p>
        </div>
        <div class="brand-meta"><strong>{len(ALL_NSE_STOCKS):,}</strong> equities tracked</div>
    </div>
    <nav class="nav-tabs-wrapper" aria-label="Main navigation">
        {nav_html}
    </nav>
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
                    screen_confirmed_buy_picks.clear()

        gainers_df, losers_df, last_date = get_live_market_data(ALL_NSE_STOCKS)

        if not is_open and last_date:
            st.info(f"📅 Showing price data from the last completed exchange session: **{last_date}**")

        st.markdown("---")
        st.subheader("📈 Daily market movers")
        st.caption(
            "Daily gainers and losers are context only—not BUY/SELL signals. "
            "The confirmed swing screen below requires trend, breakout, momentum, "
            "volume and fundamental checks."
        )

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
        st.subheader("🛡️ Confirmed swing BUY setups")
        st.caption(
            "A BUY requires price above rising 50- and 200-day averages, a 20-session "
            "breakout, recent bullish MACD crossover, RSI 50–70, volume at least "
            "1.2× its prior 20-session average, and passing fundamentals. "
            "Stops and targets use ATR; this heuristic has not been backtested."
        )

        low_screener_df = screen_confirmed_buy_picks(ALL_NSE_STOCKS)
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
                            "Confirmed swing screen",
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
                            "Confirmed swing screen",
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
                        st.metric("CMP", f"₹{row['Price']}", delta=f"{row['Dist %']}% above 52W Low")
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
            st.info("No stocks currently meet every confirmed swing BUY condition.")

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

                    technical_signal = calculate_stock_signal(hist, fundamentals)
                    rsi_value = ta.momentum.RSIIndicator(hist["Close"], window=14).rsi().iloc[-1]
                    sma_value = ta.trend.SMAIndicator(hist["Close"], window=50).sma_indicator().iloc[-1]
                    rsi = float(rsi_value) if pd.notna(rsi_value) else None
                    sma_50 = float(sma_value) if pd.notna(sma_value) else None
                    sentiment_score, news_items = fetch_cloud_safe_news(stock, clean_ticker)
                    st_call = technical_signal["swing_action"]
                    lt_call = technical_signal["long_term_action"]
                    st_reasons = technical_signal["reasons"]
                    lt_reasons = technical_signal["long_term_reasons"]

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
                        elif st_call == "EXIT / AVOID": st.error("### ACTION: EXIT / AVOID")
                        else: st.warning("### ACTION: WATCH")
                        for r in st_reasons: st.write(f"- {r}")
                        if st_call == "BUY":
                            short_target = technical_signal["swing_target"]
                            short_stop = technical_signal["swing_stop"]
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
                        elif lt_call == "EXIT / AVOID": st.error("### ACTION: EXIT / AVOID")
                        else: st.warning("### ACTION: HOLD / WATCH")
                        for r in lt_reasons: st.write(f"- {r}")
                        if lt_call == "BUY":
                            long_target = technical_signal["long_target"]
                            long_stop = technical_signal["long_stop"]
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
                    st.caption(
                        f"News sentiment score: {sentiment_score:+.2f}. "
                        "This is informational and is not part of the BUY/EXIT trigger."
                    )
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
        if st.button("Refresh portfolio", icon=":material/refresh:"):
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
                metric_cols[0].metric(
                    "Virtual amount priced",
                    f"₹{total_invested:,.2f}",
                    border=True,
                )
                metric_cols[1].metric(
                    "Latest virtual value",
                    f"₹{total_current_value:,.2f}",
                    delta=f"₹{total_current_value - total_invested:,.2f}",
                    border=True,
                )
                metric_cols[2].metric(
                    "Currently profitable",
                    f"{profitable_trades}/{priced_trades}",
                    delta=f"{profitable_trades / priced_trades:.0%} mark-to-market win rate",
                    border=True,
                )
            st.dataframe(
                pd.DataFrame(portfolio_rows),
                width="stretch",
                hide_index=True,
            )
        else:
            st.info("No virtual BUY calls have been saved to this JSONBin yet.")

# --- MANDATORY REGULATORY & EDUCATIONAL DISCLAIMER ---
st.markdown(
    '<div class="app-disclaimer"><strong>Educational use only.</strong> '
    "Signals and IPO screens are informational, not personalized investment advice. "
    "Verify source data and consult a SEBI-registered advisor before making investment decisions."
    "</div>",
    unsafe_allow_html=True,
)