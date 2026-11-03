import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from nse_listing_catalog import parse_nse_recent_listings, save_recent_listing_catalog


NSE_EQUITY_MASTER_URL = (
    "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"
)
CATALOG_PATH = PROJECT_ROOT / "data" / "recent_listings.json"


def main() -> None:
    response = requests.get(
        NSE_EQUITY_MASTER_URL,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"
            )
        },
        timeout=30,
    )
    response.raise_for_status()
    csv_text = response.content.decode("utf-8-sig")
    today = datetime.now(ZoneInfo("Asia/Kolkata")).date()
    listings = parse_nse_recent_listings(csv_text, today=today)
    save_recent_listing_catalog(CATALOG_PATH, listings)
    print(f"Updated recent NSE listing catalog with {len(listings)} shares.")


if __name__ == "__main__":
    main()
