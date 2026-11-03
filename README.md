# NSE Pulse

## Run the Streamlit app

Install the packages in `requirements.txt`, then run:

```powershell
python -m streamlit run app.py
```

## Optional Gemini and JSONBin configuration

For local development, create `.streamlit/secrets.toml` beside `app.py` (the file is ignored by Git):

```toml
GEMINI_API_KEY = "your-gemini-api-key"
JSONBIN_BIN_ID = "your-jsonbin-bin-id"
JSONBIN_MASTER_KEY = "your-jsonbin-master-key"
```

Alternatively, set `GEMINI_API_KEY`, `JSONBIN_BIN_ID`, and `JSONBIN_MASTER_KEY` as environment variables. Do not commit credentials.

Create a private JSONBin containing this initial record before enabling paper-trade logging:

```json
{"trades": []}
```

The app records each eligible BUY call once per day, source, ticker, and investment horizon. Each record uses a virtual ₹5,000 investment and stores the quote snapshot, target, stop-loss, and fundamental-screen result. The Virtual Portfolio tab shows mark-to-market performance at the latest available daily price. It is a paper-trading estimate, not a broker execution or an audited record of whether a target or stop was touched intraday.

BUY calls are gated by a transparent Yahoo Finance screen: at least two available checks must pass (positive net income, positive profit margin, ROE of at least 8%, and—outside financial companies—debt/equity at or below 100%), with no severe negative earnings, margins, ROE, or debt red flag. Missing or weak data prevents an automated BUY entry; it does not replace independent financial research.

The IPO Hub combines upcoming and ongoing issue schedules and issuer financials from Chittorgarh with current GMP and price-band data from IPOWatch. It refreshes its cached source data every five minutes, fetches independent issuer financial pages in parallel, and caches those details for 15 minutes. It shows the page-fetch time and removes an IPO after its application closing date (including at the 5 PM IST application cutoff on the closing day). It does not fall back to stale hard-coded listings.

The IPO **APPLY** screen requires positive latest reported annual revenue and profit, at least two available profitability/leverage checks to pass (ROE ≥ 8%, ROCE ≥ 10%, positive PAT margin, and debt/equity ≤ 2), no severe red flags (negative ROE, ROCE, or PAT margin, debt/equity above 2, revenue down more than 20% year over year, or PAT down more than 50%), and a positive unofficial GMP implying an estimated gain of at least 10%. Missing or weak data results in **AVOID** with the missing evidence or failed checks shown as the reason. These are transparent educational screening thresholds, not a guarantee of listing gains or personalized investment advice. GMP is unofficial, can change without notice, and may be absent from the source even while an IPO is open; verify the issuer's RHP and the current application dates before acting.
