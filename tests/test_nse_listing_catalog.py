import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from nse_listing_catalog import (
    load_recent_listing_catalog,
    parse_nse_recent_listings,
    save_recent_listing_catalog,
)


class RecentNseListingTests(unittest.TestCase):
    def test_parser_returns_recent_valid_listings_and_ignores_stale_or_future_rows(self):
        csv_text = """ SYMBOL, SERIES, DATE OF LISTING, NAME OF COMPANY
NEWCO, EQ, 01-Nov-2026, New Company Limited
SMECO, SM, 20-Oct-2026, SME Company Limited
OLDCO, EQ, 01-Jul-2026, Old Company Limited
FUTURE, EQ, 04-Nov-2026, Future Listing Limited
NODATE, EQ, , No Date Limited
"""

        listings = parse_nse_recent_listings(
            csv_text,
            today=date(2026, 11, 3),
            lookback_days=30,
        )

        self.assertEqual(
            listings,
            [
                {
                    "symbol": "NEWCO",
                    "company": "New Company Limited",
                    "series": "EQ",
                    "date_of_listing": "2026-11-01",
                },
                {
                    "symbol": "SMECO",
                    "company": "SME Company Limited",
                    "series": "SM",
                    "date_of_listing": "2026-10-20",
                },
            ],
        )

    def test_parser_rejects_unexpected_nse_file_shape(self):
        with self.assertRaisesRegex(ValueError, "missing required columns"):
            parse_nse_recent_listings(
                "SYMBOL,COMPANY\nABC,ABC Limited\n",
                today=date(2026, 11, 3),
            )

    def test_catalog_round_trips_and_missing_file_is_empty(self):
        listing = {
            "symbol": "NEWCO",
            "company": "New Company Limited",
            "series": "EQ",
            "date_of_listing": "2026-11-01",
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "nested" / "recent_listings.json"

            self.assertEqual(load_recent_listing_catalog(path), [])
            save_recent_listing_catalog(path, [listing])

            self.assertEqual(load_recent_listing_catalog(path), [listing])
            self.assertEqual(
                json.loads(path.read_text(encoding="utf-8")),
                {"listings": [listing]},
            )

    def test_catalog_rejects_malformed_entries(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "recent_listings.json"
            path.write_text('{"listings": [{"symbol": "ABC"}]}', encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "invalid entry"):
                load_recent_listing_catalog(path)
