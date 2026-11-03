import csv
import io
import json
from datetime import date, datetime, timedelta
from pathlib import Path


def parse_nse_recent_listings(
    csv_text: str,
    today: date,
    lookback_days: int = 90,
) -> list[dict[str, str]]:
    if lookback_days < 1:
        raise ValueError("lookback_days must be positive")

    reader = csv.DictReader(io.StringIO(csv_text))
    if not reader.fieldnames:
        raise ValueError("NSE listing file has no header row")

    headers = {
        header.lstrip("\ufeff").strip().upper(): header
        for header in reader.fieldnames
    }
    required = {"SYMBOL", "SERIES", "DATE OF LISTING"}
    missing = required - headers.keys()
    if missing:
        raise ValueError(
            "NSE listing file is missing required columns: "
            + ", ".join(sorted(missing))
        )

    company_header = headers.get("NAME OF COMPANY") or headers.get(
        "NAME OF THE COMPANY"
    )
    earliest_date = today - timedelta(days=lookback_days - 1)
    listings_by_symbol = {}

    for row in reader:
        symbol = (row.get(headers["SYMBOL"]) or "").strip().upper()
        series = (row.get(headers["SERIES"]) or "").strip().upper()
        listed_on = _parse_listing_date(row.get(headers["DATE OF LISTING"]))
        if not symbol or not series or listed_on is None:
            continue
        if not earliest_date <= listed_on <= today:
            continue

        company = (row.get(company_header) or "").strip() if company_header else ""
        listing = {
            "symbol": symbol,
            "company": company,
            "series": series,
            "date_of_listing": listed_on.isoformat(),
        }
        listings_by_symbol[symbol] = listing

    return sorted(
        listings_by_symbol.values(),
        key=lambda listing: (listing["date_of_listing"], listing["symbol"]),
        reverse=True,
    )


def _parse_listing_date(value: str | None) -> date | None:
    if not value:
        return None
    cleaned = value.strip()
    for date_format in ("%d-%b-%Y", "%d-%b-%y", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(cleaned, date_format).date()
        except ValueError:
            continue
    try:
        return date.fromisoformat(cleaned)
    except ValueError:
        return None


def load_recent_listing_catalog(path: str | Path) -> list[dict[str, str]]:
    catalog_path = Path(path)
    try:
        data = json.loads(catalog_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []

    if not isinstance(data, dict) or not isinstance(data.get("listings"), list):
        raise ValueError("Recent-listing catalog has an invalid format")

    listings = data["listings"]
    for listing in listings:
        if (
            not isinstance(listing, dict)
            or not isinstance(listing.get("symbol"), str)
            or not isinstance(listing.get("company"), str)
            or not isinstance(listing.get("series"), str)
            or not isinstance(listing.get("date_of_listing"), str)
        ):
            raise ValueError("Recent-listing catalog contains an invalid entry")
    return listings


def save_recent_listing_catalog(
    path: str | Path,
    listings: list[dict[str, str]],
) -> None:
    catalog_path = Path(path)
    catalog_path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        {"listings": listings},
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    temporary_path = catalog_path.with_suffix(catalog_path.suffix + ".tmp")
    temporary_path.write_text(payload + "\n", encoding="utf-8")
    temporary_path.replace(catalog_path)
