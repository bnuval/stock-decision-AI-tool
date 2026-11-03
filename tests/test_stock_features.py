import unittest
from datetime import date, datetime, timezone
from unittest.mock import Mock

from stock_features import (
    assess_fundamentals,
    build_virtual_trade,
    evaluate_ipo_recommendation,
    evaluate_stock_signal,
    is_active_today_or_future,
    match_ipo_gmp,
    parse_ipo_html,
    parse_ipo_date,
    parse_ipo_date_range,
    parse_ipo_detail_html,
    parse_ipo_gmp_html,
    parse_ipo_schedule_html,
    sync_virtual_trades,
)


class IpoDateTests(unittest.TestCase):
    def test_parses_full_and_yearless_dates(self):
        today = date(2026, 11, 3)
        self.assertEqual(parse_ipo_date("05-Nov-2026", today), date(2026, 11, 5))
        self.assertEqual(parse_ipo_date("Nov 5", today), date(2026, 11, 5))
        self.assertEqual(parse_ipo_date("5-Nov", today), date(2026, 11, 5))

    def test_missing_or_expired_close_dates_are_not_active(self):
        today = date(2026, 11, 3)
        self.assertTrue(is_active_today_or_future("03-Nov-2026", today))
        self.assertFalse(is_active_today_or_future("02-Nov-2026", today))
        self.assertFalse(is_active_today_or_future("TBD", today))

    def test_date_range_parses_same_month_cross_month_and_yearless_ranges(self):
        today = date(2026, 11, 3)
        self.assertEqual(
            parse_ipo_date_range("02 - 04 Nov, 2026", today),
            (date(2026, 11, 2), date(2026, 11, 4)),
        )
        self.assertEqual(
            parse_ipo_date_range("30 Oct - 03 Nov", today),
            (date(2026, 10, 30), date(2026, 11, 3)),
        )
        self.assertEqual(
            parse_ipo_date_range("29-2 Nov", today),
            (date(2026, 10, 29), date(2026, 11, 2)),
        )

    def test_schedule_includes_only_ongoing_and_future_issues(self):
        html = """
        <table>
          <tr><th>Company</th><th>Issue Date</th></tr>
          <tr><td colspan="2"><a href="/ipo/acme-ipo/1/">Acme</a><span>O</span><span>02 - 04 Nov</span></td></tr>
          <tr><td colspan="2"><a href="/ipo/closing-today/2/">Closing Today</a><span>CT</span><span>30 Oct - 03 Nov</span></td></tr>
          <tr><td colspan="2"><a href="/ipo/expired-ipo/3/">Expired Ltd</a><span>P</span><span>28 - 30 Oct</span></td></tr>
          <tr><td colspan="2"><a href="/ipo/future-ipo/4/">Future Co</a><span>10 - 12 Nov</span></td></tr>
        </table>
        """
        results = parse_ipo_schedule_html(
            html,
            board="SME",
            today=date(2026, 11, 3),
        )
        self.assertEqual(
            [row["Company"] for row in results],
            ["Acme", "Closing Today", "Future Co"],
        )
        self.assertEqual(results[0]["Status"], "Ongoing (Open)")
        self.assertEqual(results[1]["Status"], "Ongoing (Closing Today)")
        self.assertEqual(results[2]["Status"], "Upcoming")
        self.assertEqual(results[0]["IPO Details URL"], "https://www.chittorgarh.com/ipo/acme-ipo/1/")
        after_application_cutoff = parse_ipo_schedule_html(
            html,
            board="SME",
            today=date(2026, 11, 3),
            now=datetime(2026, 11, 3, 17, 0),
        )
        self.assertEqual(
            [row["Company"] for row in after_application_cutoff],
            ["Acme", "Future Co"],
        )

    def test_ipo_html_selects_columns_filters_stale_rows_and_parses_price_bands(self):
        html = """
        <table>
          <tr><th>IPO GMP</th><th>Company Name</th><th>Issue Price Band</th>
              <th>Opening Date</th><th>Closing Date</th><th>Category</th></tr>
          <tr><td>₹15 (15%)</td><td>Acme SME IPO</td><td>₹100 - ₹110</td>
              <td>01-Nov-2026</td><td>05-Nov-2026</td><td>SME</td></tr>
          <tr><td>₹20 (20%)</td><td>Expired Ltd IPO</td><td>₹100 - ₹110</td>
              <td>01-Oct-2026</td><td>02-Oct-2026</td><td>Mainboard</td></tr>
          <tr><td>₹5</td><td>Date Unknown IPO</td><td>₹50</td>
              <td>TBD</td><td>TBD</td><td>Mainboard</td></tr>
        </table>
        """
        results = parse_ipo_html(html, today=date(2026, 11, 3))
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["Company"], "Acme")
        self.assertEqual(results[0]["Issue Price (₹)"], 110)
        self.assertEqual(results[0]["Type"], "SME")
        self.assertEqual(results[0]["Status"], "Ongoing (Open)")
        self.assertEqual(results[0]["Recommendation"], "NOT RATED")

    def test_ipo_parser_reports_changed_source_markup(self):
        with self.assertRaisesRegex(ValueError, "expected columns"):
            parse_ipo_html("<html><body>Source layout changed</body></html>")

    def test_gmp_parser_extracts_live_values_and_issue_board(self):
        html = """
        <h2>Current Mainboard IPO</h2>
        <table>
          <tr><th>Company</th><th>GMP*</th><th>Price Band</th><th>Est. Gain</th><th>Date</th></tr>
          <tr><td><a href="/acme-ipo/">Acme Ltd</a> Open</td><td>₹15</td>
              <td>₹100 - ₹110</td><td>₹125 (13.64%)</td><td>2-4 Nov</td></tr>
        </table>
        <h2>Current SME IPO</h2>
        <table>
          <tr><th>Company</th><th>GMP*</th><th>Price Band</th><th>Est. Gain</th></tr>
          <tr><td>Beta Open</td><td>₹-5</td><td>₹50</td><td>₹45 (-10%)</td></tr>
        </table>
        """
        results = parse_ipo_gmp_html(html)
        self.assertEqual(results[0]["Type"], "Mainboard")
        self.assertEqual(results[0]["GMP (₹)"], 15)
        self.assertEqual(results[0]["Issue Price (₹)"], 110)
        self.assertEqual(results[0]["Est Gain %"], 13.64)
        self.assertEqual(results[1]["Type"], "SME")
        self.assertEqual(results[1]["GMP (₹)"], -5)
        self.assertEqual(match_ipo_gmp("Acme", "Mainboard", results), results[0])

    def test_ipo_detail_parser_reads_price_band_and_restated_financials(self):
        html = """
        <table>
          <tr><th>IPO Date</th><td>2 to 4 Nov, 2026</td></tr>
          <tr><th>Price Band</th><td>₹88 to ₹94</td></tr>
          <tr><th>Lot Size</th><td>1,200 Shares</td></tr>
        </table>
        <table>
          <tr><th>KPI</th><th>Jun 30, 2026</th><th>Mar 31, 2026</th></tr>
          <tr><td>ROE</td><td>7.92%</td><td>38.03%</td></tr>
          <tr><td>ROCE</td><td>8.93%</td><td>46.34%</td></tr>
          <tr><td>Debt/Equity</td><td>0.98</td><td>1.11</td></tr>
          <tr><td>PAT Margin</td><td>11.48%</td><td>9.52%</td></tr>
        </table>
        <table>
          <tr><th>Period Ended</th><th>30 Jun 2026</th><th>31 Mar 2026</th><th>31 Mar 2025</th></tr>
          <tr><td>Total Income</td><td>30.49</td><td>115.31</td><td>81.58</td></tr>
          <tr><td>Profit After Tax</td><td>3.48</td><td>10.97</td><td>4.50</td></tr>
        </table>
        """
        result = parse_ipo_detail_html(html)
        self.assertEqual(result["issue_price"], 94)
        self.assertEqual(result["lot_size"], "1,200 Shares")
        self.assertEqual(result["latest_revenue"], 115.31)
        self.assertEqual(result["previous_revenue"], 81.58)
        self.assertEqual(result["latest_pat"], 10.97)
        self.assertEqual(result["roe"], 7.92)
        self.assertEqual(result["debt_equity"], 0.98)

    def test_ipo_recommendation_requires_both_fundamentals_and_gmp(self):
        fundamentals = {
            "latest_revenue": 115.31,
            "latest_pat": 10.97,
            "financial_year": 2026,
            "roe": 25,
            "roce": 20,
            "debt_equity": 0.8,
            "pat_margin": 9.5,
        }
        apply = evaluate_ipo_recommendation(fundamentals, gmp=15, issue_price=100)
        self.assertEqual(apply["Recommendation"], "APPLY")
        self.assertEqual(apply["Fundamental Status"], "Pass")

        weak_gmp = evaluate_ipo_recommendation(fundamentals, gmp=5, issue_price=100)
        self.assertEqual(weak_gmp["Recommendation"], "AVOID")
        high_debt = evaluate_ipo_recommendation(
            {**fundamentals, "debt_equity": 2.5},
            gmp=25,
            issue_price=100,
        )
        self.assertEqual(high_debt["Recommendation"], "AVOID")
        self.assertIn("above 2", high_debt["Analysis & Rationale"])
        declining = evaluate_ipo_recommendation(
            {
                **fundamentals,
                "latest_revenue": 70,
                "previous_revenue": 100,
                "latest_pat": 10,
                "previous_pat": 30,
            },
            gmp=25,
            issue_price=100,
        )
        self.assertEqual(declining["Recommendation"], "AVOID")
        self.assertIn("annual PAT fell", declining["Analysis & Rationale"])
        missing_financials = evaluate_ipo_recommendation({}, gmp=25, issue_price=100)
        self.assertEqual(missing_financials["Recommendation"], "AVOID")
        self.assertIn("revenue and profit", missing_financials["Analysis & Rationale"])


class FundamentalTests(unittest.TestCase):
    def test_profitable_company_passes_with_two_positive_checks(self):
        result = assess_fundamentals(
            {
                "netIncomeToCommon": 100,
                "profitMargins": 0.12,
                "returnOnEquity": 0.2,
                "debtToEquity": 50,
                "sector": "Technology",
            }
        )
        self.assertTrue(result["buy_eligible"])
        self.assertEqual(result["status"], "Pass")

    def test_missing_or_negative_fundamentals_do_not_pass(self):
        self.assertFalse(assess_fundamentals({})["buy_eligible"])
        result = assess_fundamentals(
            {
                "netIncomeToCommon": -1,
                "profitMargins": -0.02,
                "returnOnEquity": 0.2,
                "debtToEquity": 20,
            }
        )
        self.assertFalse(result["buy_eligible"])
        self.assertEqual(result["status"], "Fail")

    def test_financial_sector_does_not_apply_industrial_debt_threshold(self):
        result = assess_fundamentals(
            {
                "netIncomeToCommon": 100,
                "profitMargins": 0.1,
                "returnOnEquity": 0.12,
                "debtToEquity": 900,
                "sector": "Financial Services",
            }
        )
        self.assertTrue(result["buy_eligible"])


class VirtualTradeTests(unittest.TestCase):
    def setUp(self):
        self.call = {
            "ticker": "TCS.NS",
            "company": "TCS",
            "source": "Deep Dive",
            "horizon": "Short term",
            "entry_price": 100,
            "target_price": 108,
            "stop_loss": 95,
            "fundamental_status": "Pass",
            "fundamental_summary": "Checks passed",
        }
        self.called_at = datetime(2026, 11, 3, 10, tzinfo=timezone.utc)

    def test_trade_uses_fixed_virtual_investment_and_is_repeatable(self):
        trade = build_virtual_trade(self.call, called_at=self.called_at)
        self.assertEqual(trade["virtual_investment"], 5000)
        self.assertEqual(trade["quantity"], 50)
        self.assertEqual(trade["target_price"], 108)
        self.assertEqual(
            trade["id"],
            build_virtual_trade(self.call, called_at=self.called_at)["id"],
        )

    def test_trade_rejects_targets_or_stops_on_the_wrong_side(self):
        invalid_call = {**self.call, "target_price": 99}
        with self.assertRaises(ValueError):
            build_virtual_trade(invalid_call, called_at=self.called_at)
        invalid_call = {**self.call, "stop_loss": 101}
        with self.assertRaises(ValueError):
            build_virtual_trade(invalid_call, called_at=self.called_at)

    def test_jsonbin_sync_appends_once_and_skips_duplicate(self):
        http = Mock()
        get_response = Mock()
        get_response.json.return_value = {"record": {"trades": []}}
        http.get.return_value = get_response
        http.put.return_value = Mock()

        result = sync_virtual_trades(
            [self.call, self.call],
            "bin-id",
            "master-key",
            http=http,
            called_at=self.called_at,
        )

        self.assertEqual(result, {"added": 1, "duplicates": 1})
        http.put.assert_called_once()
        self.assertEqual(
            len(http.put.call_args.kwargs["json"]["trades"]),
            1,
        )

    def test_jsonbin_requires_expected_record_shape(self):
        http = Mock()
        response = Mock()
        response.json.return_value = {"record": []}
        http.get.return_value = response
        with self.assertRaisesRegex(ValueError, "trades"):
            sync_virtual_trades([self.call], "bin-id", "master-key", http=http)


class StockSignalTests(unittest.TestCase):
    def setUp(self):
        self.indicators = {
            "price": 120.0,
            "sma_50": 110.0,
            "sma_200": 100.0,
            "rsi": 60.0,
            "macd_bullish": True,
            "macd_bearish": False,
            "recent_bullish_cross": True,
            "volume_ratio": 1.5,
            "breakout": True,
            "atr": 5.0,
        }
        self.fundamentals = {"buy_eligible": True, "status": "Pass"}

    def test_confirmed_swing_buy_uses_atr_levels(self):
        result = evaluate_stock_signal(self.indicators, self.fundamentals)
        self.assertEqual(result["swing_action"], "BUY")
        self.assertEqual(result["long_term_action"], "BUY")
        self.assertEqual(result["swing_entry"], 120.0)
        self.assertEqual(result["swing_stop"], 110.0)
        self.assertEqual(result["swing_target"], 135.0)
        self.assertEqual(result["long_stop"], 105.0)
        self.assertEqual(result["long_target"], 150.0)
        self.assertEqual(result["risk_reward"], 1.5)

    def test_long_term_buy_does_not_require_swing_breakout_or_volume(self):
        indicators = self.indicators | {
            "breakout": False,
            "volume_ratio": 0.8,
            "recent_bullish_cross": False,
        }
        result = evaluate_stock_signal(indicators, self.fundamentals)
        self.assertEqual(result["long_term_action"], "BUY")
        self.assertEqual(result["swing_action"], "WATCH")

    def test_missing_long_history_never_generates_buy(self):
        indicators = self.indicators | {"sma_200": None}
        result = evaluate_stock_signal(indicators, self.fundamentals)
        self.assertEqual(result["swing_action"], "WATCH")
        self.assertEqual(result["long_term_action"], "HOLD / WATCH")
        self.assertEqual(result["swing_target"], 135.0)

    def test_extreme_atr_cannot_create_buy_with_invalid_stop_levels(self):
        indicators = self.indicators | {"atr": 50.0}
        result = evaluate_stock_signal(indicators, self.fundamentals)
        self.assertEqual(result["swing_action"], "WATCH")
        self.assertEqual(result["long_term_action"], "HOLD / WATCH")
        self.assertIsNone(result["swing_stop"])
        self.assertIsNone(result["long_stop"])

    def test_exit_requires_downtrend_bearish_momentum_and_failed_fundamentals(self):
        indicators = self.indicators | {
            "price": 80.0,
            "sma_50": 90.0,
            "sma_200": 100.0,
            "macd_bullish": False,
            "macd_bearish": True,
            "recent_bullish_cross": False,
        }
        fundamentals = {"buy_eligible": False, "status": "Fail"}
        result = evaluate_stock_signal(indicators, fundamentals)
        self.assertEqual(result["swing_action"], "EXIT / AVOID")
        self.assertTrue(result["exit_signal"])

    def test_failed_fundamentals_block_buys_and_incomplete_numbers_are_safe(self):
        failed = evaluate_stock_signal(
            self.indicators,
            {"buy_eligible": False, "status": "Fail"},
        )
        self.assertEqual(failed["swing_action"], "WATCH")
        self.assertEqual(failed["long_term_action"], "HOLD / WATCH")

        invalid = self.indicators | {"price": "not a price"}
        result = evaluate_stock_signal(invalid, self.fundamentals)
        self.assertEqual(result["swing_action"], "WATCH")


if __name__ == "__main__":
    unittest.main()
