import hashlib
import math
import re
from difflib import SequenceMatcher
from datetime import date, datetime, time, timezone
from typing import Any
from urllib.parse import urljoin


VIRTUAL_INVESTMENT = 5000.0


def parse_ipo_date(date_str: str | None, today: date | None = None) -> date | None:
    if not date_str or date_str.strip().lower() in {
        "-",
        "tbd",
        "upcoming",
        "closing soon",
        "closing today",
    }:
        return None

    reference_date = today or date.today()
    cleaned = re.sub(r"(?i)\b(\d{1,2})(st|nd|rd|th)\b", r"\1", date_str)
    cleaned = cleaned.replace(",", "").strip()
    full_year_formats = (
        "%d-%b-%Y",
        "%d %b %Y",
        "%d-%B-%Y",
        "%d %B %Y",
        "%d-%b-%y",
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%Y-%m-%d",
        "%b %d %Y",
        "%B %d %Y",
    )
    yearless_formats = (
        "%d-%b",
        "%d %b",
        "%d-%B",
        "%d %B",
        "%b %d",
        "%B %d",
    )

    for date_format in full_year_formats:
        try:
            return datetime.strptime(cleaned, date_format).date()
        except ValueError:
            continue

    for date_format in yearless_formats:
        try:
            return datetime.strptime(
                f"{cleaned} {reference_date.year}",
                f"{date_format} %Y",
            ).date()
        except ValueError:
            continue

    return None


def is_active_today_or_future(
    close_date_str: str | None, today: date | None = None
) -> bool:
    close_date = parse_ipo_date(close_date_str, today=today)
    return close_date is not None and close_date >= (today or date.today())


def parse_ipo_date_range(
    date_range: str | None, today: date | None = None
) -> tuple[date | None, date | None]:
    if not date_range:
        return None, None

    reference_date = today or date.today()
    month_names = (
        "jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
        "jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|"
        "nov(?:ember)?|dec(?:ember)?"
    )
    date_pattern = re.compile(
        rf"(?<!\d)(?P<day>\d{{1,2}})(?:st|nd|rd|th)?"
        rf"(?:\s*(?P<month>{month_names}))?"
        rf"(?:,?\s*(?P<year>20\d{{2}}))?(?!\d)",
        re.IGNORECASE,
    )
    matches = list(date_pattern.finditer(date_range.replace("–", "-").replace("—", "-")))
    if len(matches) < 2:
        return None, None

    month_lookup = {
        name.lower(): number
        for number, name in enumerate(
            ("January", "February", "March", "April", "May", "June", "July",
             "August", "September", "October", "November", "December"),
            start=1,
        )
    }

    def month_number(token: str | None) -> int | None:
        if not token:
            return None
        return next(
            (number for name, number in month_lookup.items() if name.startswith(token.lower())),
            9 if token.lower().startswith("sep") else None,
        )

    first, last = matches[0], matches[-1]
    start_day, end_day = int(first.group("day")), int(last.group("day"))
    end_month = month_number(last.group("month"))
    if end_month is None:
        return None, None
    explicit_start_month = month_number(first.group("month"))
    if explicit_start_month is None and start_day > end_day:
        start_month = 12 if end_month == 1 else end_month - 1
    else:
        start_month = explicit_start_month or end_month
    end_year = int(last.group("year")) if last.group("year") else reference_date.year
    try:
        close_date = date(end_year, end_month, end_day)
    except ValueError:
        return None, None
    if last.group("year") is None and (close_date - reference_date).days < -180:
        try:
            close_date = date(end_year + 1, end_month, end_day)
        except ValueError:
            return None, None

    start_year = int(first.group("year")) if first.group("year") else close_date.year
    if first.group("year") is None and (
        start_month > end_month or (explicit_start_month is None and end_month == 1 and start_day > end_day)
    ):
        start_year -= 1
    try:
        open_date = date(start_year, start_month, start_day)
    except ValueError:
        return None, None
    return open_date, close_date


def is_ipo_application_open(close_date: date | datetime, now: datetime) -> bool:
    close_day = close_date.date() if isinstance(close_date, datetime) else close_date
    if close_day > now.date():
        return True
    return close_day == now.date() and now.time().replace(tzinfo=None) < time(17, 0)


def parse_ipo_schedule_html(
    html: bytes | str,
    board: str,
    today: date | None = None,
    base_url: str = "https://www.chittorgarh.com",
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    from bs4 import BeautifulSoup

    reference_date = today or date.today()
    reference_time = now or datetime.combine(reference_date, time(12, 0))
    soup = BeautifulSoup(html, "html.parser")
    schedule = []
    matched_table = False
    seen = set()

    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if not rows:
            continue
        header_cells = rows[0].find_all(["th", "td"])
        headers = [cell.get_text(" ", strip=True).lower() for cell in header_cells]
        company_index = next(
            (i for i, header in enumerate(headers) if "company" in header),
            None,
        )
        date_index = next(
            (i for i, header in enumerate(headers) if "issue date" in header),
            None,
        )
        if company_index is None or date_index is None:
            continue
        matched_table = True

        for row in rows[1:]:
            cells = row.find_all(["th", "td"])
            if company_index >= len(cells):
                continue
            company_cell = cells[company_index]
            link = company_cell.find("a", href=True)
            if not link:
                continue
            company = re.sub(
                r"(?i)\s+IPO\s*$",
                "",
                link.get_text(" ", strip=True),
            ).strip()
            date_text = (
                cells[date_index].get_text(" ", strip=True)
                if date_index < len(cells)
                else company_cell.get_text(" ", strip=True).replace(
                    link.get_text(" ", strip=True),
                    " ",
                    1,
                )
            )
            opening, closing = parse_ipo_date_range(date_text, today=reference_date)
            key = normalize_ipo_name(company)
            if (
                not key
                or key in seen
                or opening is None
                or closing is None
                or not is_ipo_application_open(closing, reference_time)
            ):
                continue
            status = (
                "Ongoing (Closing Today)"
                if closing == reference_date
                else "Ongoing (Open)"
                if opening <= reference_date
                else "Upcoming"
            )
            schedule.append(
                {
                    "Company": company,
                    "Type": board,
                    "Open Date": opening,
                    "Close Date": closing,
                    "Status": status,
                    "IPO Details URL": urljoin(base_url, link["href"]),
                }
            )
            seen.add(key)

    if not matched_table:
        raise ValueError(
            f"The {board} IPO schedule no longer has the expected Company and Issue Date columns."
        )
    return schedule


def normalize_ipo_name(name: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", " ", name.lower())
    normalized = re.sub(
        r"\b(ipo|limited|ltd|private|pvt|incorporated|india)\b",
        " ",
        normalized,
    )
    return " ".join(normalized.split())


def parse_ipo_gmp_html(html: bytes | str) -> list[dict[str, Any]]:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    records = []
    matched_tables = 0

    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if not rows:
            continue
        headers = [
            cell.get_text(" ", strip=True).lower()
            for cell in rows[0].find_all(["th", "td"])
        ]
        indices = {
            "company": next(
                (i for i, header in enumerate(headers) if "company" in header),
                None,
            ),
            "gmp": next((i for i, header in enumerate(headers) if "gmp" in header), None),
            "price": next(
                (i for i, header in enumerate(headers) if "price band" in header),
                None,
            ),
            "gain": next(
                (i for i, header in enumerate(headers) if "est. gain" in header or "estimated gain" in header),
                None,
            ),
        }
        if any(indices[key] is None for key in ("company", "gmp", "price")):
            continue
        matched_tables += 1
        heading = table.find_previous(["h2", "h3", "h4"])
        heading_text = heading.get_text(" ", strip=True).lower() if heading else ""
        if "sme" in heading_text:
            board = "SME"
        elif "mainboard" in heading_text:
            board = "Mainboard"
        else:
            board = "Mainboard" if matched_tables == 1 else "SME"

        for row in rows[1:]:
            cells = row.find_all(["th", "td"])
            required_indices = [indices[key] for key in ("company", "gmp", "price")]
            if max(required_indices) >= len(cells):
                continue
            company_cell = cells[indices["company"]]
            company_link = company_cell.find("a", href=True)
            company = (
                company_link.get_text(" ", strip=True)
                if company_link
                else company_cell.get_text(" ", strip=True)
            )
            company = re.sub(r"\s+(?:Open|Closed)\s*$", "", company, flags=re.IGNORECASE).strip()
            gmp_text = cells[indices["gmp"]].get_text(" ", strip=True)
            gmp_match = re.search(
                r"([+\-\u2212]?)\s*₹?\s*([\d,]+(?:\.\d+)?)",
                gmp_text,
            )
            gmp_value = (
                float(gmp_match.group(2).replace(",", ""))
                * (-1 if gmp_match.group(1) in {"-", "\u2212"} else 1)
                if gmp_match
                else None
            )
            price_text = cells[indices["price"]].get_text(" ", strip=True)
            price_values = re.findall(r"[\d,]+(?:\.\d+)?", price_text)
            if not company or not price_values:
                continue
            price = float(price_values[-1].replace(",", ""))
            gain_percent = None
            if indices["gain"] is not None and indices["gain"] < len(cells):
                gain_match = re.search(
                    r"\(([-+]?\d+(?:\.\d+)?)\s*%\)",
                    cells[indices["gain"]].get_text(" ", strip=True),
                )
                if gain_match:
                    gain_percent = float(gain_match.group(1))
            if gain_percent is None and gmp_value is not None and price > 0:
                gain_percent = round(gmp_value / price * 100, 2)
            records.append(
                {
                    "Company": company,
                    "Type": board,
                    "GMP (₹)": gmp_value,
                    "Issue Price (₹)": price,
                    "Est Gain %": gain_percent,
                    "GMP Source URL": urljoin(
                        "https://ipowatch.in",
                        company_link["href"],
                    )
                    if company_link
                    else "https://ipowatch.in/ipo-grey-market-premium-latest-ipo-gmp/",
                }
            )

    if not matched_tables:
        raise ValueError("The live GMP page no longer has the expected company, GMP, and price columns.")
    return records


def match_ipo_gmp(
    company: str, board: str, gmp_records: list[dict[str, Any]]
) -> dict[str, Any] | None:
    key = normalize_ipo_name(company)
    candidates = [
        record
        for record in gmp_records
        if record.get("Type") == board and normalize_ipo_name(record["Company"])
    ]
    exact = [
        record
        for record in candidates
        if normalize_ipo_name(record["Company"]) == key
    ]
    if len(exact) == 1:
        return exact[0]
    ranked = sorted(
        (
            (SequenceMatcher(None, key, normalize_ipo_name(record["Company"])).ratio(), record)
            for record in candidates
        ),
        key=lambda item: item[0],
        reverse=True,
    )
    if not ranked or ranked[0][0] < 0.78:
        return None
    if len(ranked) > 1 and ranked[0][0] - ranked[1][0] < 0.04:
        return None
    return ranked[0][1]


def parse_ipo_detail_html(html: bytes | str) -> dict[str, Any]:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    kpis: dict[str, float] = {}
    financial_rows: dict[str, list[float | None]] = {}
    annual_periods: list[tuple[int, int]] = []

    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if not rows:
            continue
        first_cells = rows[0].find_all(["th", "td"])
        headers = [cell.get_text(" ", strip=True) for cell in first_cells]
        header_text = " ".join(headers).lower()
        if "kpi" in header_text:
            for row in rows[1:]:
                cells = row.find_all(["th", "td"])
                if len(cells) < 2:
                    continue
                label = re.sub(r"[^a-z/]+", " ", cells[0].get_text(" ", strip=True).lower()).strip()
                number = _parse_financial_number(cells[1].get_text(" ", strip=True))
                if number is None:
                    continue
                if label == "roe":
                    kpis["roe"] = number
                elif label == "roce":
                    kpis["roce"] = number
                elif "debt/equity" in label or "debt equity" in label:
                    kpis["debt_equity"] = number
                elif "pat margin" in label or "profit margin" in label:
                    kpis["pat_margin"] = number
                elif label in {"p e", "pe"}:
                    kpis["pe"] = number
            continue

        period_columns = [
            (int(year_match.group(0)), index)
            for index, header in enumerate(headers)
            if re.search(r"\bmar(?:ch)?\b", header, re.IGNORECASE)
            and (year_match := re.search(r"\b20\d{2}\b", header))
        ]
        if period_columns:
            annual_periods = sorted(period_columns, reverse=True)

        for row in rows[1:]:
            cells = row.find_all(["th", "td"])
            if len(cells) < 2:
                continue
            raw_label = cells[0].get_text(" ", strip=True)
            label = re.sub(
                r"[^a-z]+",
                " ",
                raw_label.lower(),
            ).strip()
            raw_value = cells[1].get_text(" ", strip=True)
            if "price band" in label:
                prices = re.findall(r"[\d,]+(?:\.\d+)?", raw_value)
                if prices:
                    kpis["issue_price"] = float(prices[-1].replace(",", ""))
                    kpis["price_band"] = raw_value
            elif "lot size" in label:
                kpis["lot_size"] = raw_value
            elif "total issue size" in label or label == "issue size":
                kpis["issue_size"] = raw_value
            if "total income" in label or "revenue from operations" in label or label == "revenue":
                key = "revenue"
            elif "profit after tax" in label or label == "pat":
                key = "pat"
            else:
                continue
            financial_rows[key] = [
                _parse_financial_number(cell.get_text(" ", strip=True))
                for cell in cells
            ]

    for key, output_key in (("revenue", "latest_revenue"), ("pat", "latest_pat")):
        values = financial_rows.get(key, [])
        if annual_periods:
            latest_index = annual_periods[0][1]
            previous_index = annual_periods[1][1] if len(annual_periods) > 1 else None
            if latest_index < len(values):
                kpis[output_key] = values[latest_index]
            if previous_index is not None and previous_index < len(values):
                kpis[f"previous_{key}"] = values[previous_index]
    if annual_periods:
        kpis["financial_year"] = annual_periods[0][0]
        if len(annual_periods) > 1:
            kpis["previous_financial_year"] = annual_periods[1][0]
    return kpis


def _parse_financial_number(value: str) -> float | None:
    cleaned = value.strip().replace(",", "").replace("₹", "").replace("%", "").replace("x", "")
    if not cleaned or cleaned in {"-", "—", "–", "NA", "N/A"}:
        return None
    negative = cleaned.startswith("(") and cleaned.endswith(")")
    cleaned = cleaned.strip("() ")
    match = re.search(r"[-+]?\d+(?:\.\d+)?", cleaned)
    if not match:
        return None
    try:
        number = float(match.group(0))
    except ValueError:
        return None
    return -abs(number) if negative else number


def evaluate_ipo_recommendation(
    fundamentals: dict[str, Any],
    gmp: float | None,
    issue_price: float | None,
) -> dict[str, str]:
    revenue = fundamentals.get("latest_revenue")
    profit = fundamentals.get("latest_pat")
    previous_revenue = fundamentals.get("previous_revenue")
    previous_profit = fundamentals.get("previous_pat")
    roe = fundamentals.get("roe")
    roce = fundamentals.get("roce")
    debt_equity = fundamentals.get("debt_equity")
    pat_margin = fundamentals.get("pat_margin")
    estimate = (
        round(gmp / issue_price * 100, 2)
        if gmp is not None and issue_price and issue_price > 0
        else None
    )

    reasons = []
    fundamental_ready = revenue is not None and profit is not None
    severe_red_flags = []
    if not fundamental_ready:
        reasons.append("latest annual revenue and profit are not both available in the issuer financials")
    elif revenue <= 0 or profit <= 0:
        reasons.append("latest annual revenue or profit is not positive")
    if (
        revenue is not None
        and previous_revenue is not None
        and previous_revenue > 0
        and revenue < previous_revenue * 0.8
    ):
        decline = (previous_revenue - revenue) / previous_revenue * 100
        severe_red_flags.append(f"reported annual revenue fell by {decline:.1f}% year over year")
    if (
        profit is not None
        and previous_profit is not None
        and previous_profit > 0
        and profit < previous_profit * 0.5
    ):
        decline = (previous_profit - profit) / previous_profit * 100
        severe_red_flags.append(f"reported annual PAT fell by {decline:.1f}% year over year")

    positive_checks = 0
    available_checks = 0
    passed_checks = []
    failed_checks = []
    for value, threshold, label in (
        (roe, 8, "ROE ≥ 8%"),
        (roce, 10, "ROCE ≥ 10%"),
        (pat_margin, 0, "positive PAT margin"),
        (None if debt_equity is None else 2 - debt_equity, 0, "debt/equity ≤ 2"),
    ):
        if value is not None:
            available_checks += 1
            passed = value >= threshold
            positive_checks += int(passed)
            if passed:
                passed_checks.append(label)
            else:
                failed_checks.append(label)
                reasons.append(f"{label} is not met")
    if roe is not None and roe < 0:
        severe_red_flags.append("ROE is negative")
    if roce is not None and roce < 0:
        severe_red_flags.append("ROCE is negative")
    if pat_margin is not None and pat_margin < 0:
        severe_red_flags.append("PAT margin is negative")
    if debt_equity is not None and debt_equity > 2:
        severe_red_flags.append("debt/equity is above 2")
    if available_checks < 2:
        reasons.append("fewer than two supporting profitability or leverage ratios are available")
    elif positive_checks < 2:
        reasons.append("fewer than two profitability or leverage checks passed")
    if gmp is None:
        reasons.append("a current GMP reading is not available")
    elif gmp <= 0:
        reasons.append(f"GMP is ₹{gmp:,.2f}, so there is no positive grey-market premium")
    elif estimate is not None and estimate < 10:
        reasons.append(f"indicative GMP gain is {estimate:.2f}%, below the 10% screening threshold")
    elif estimate is None:
        reasons.append("the issue price is unavailable, so the indicative GMP gain cannot be calculated")
    if severe_red_flags:
        reasons.extend(severe_red_flags)

    apply = (
        fundamental_ready
        and revenue > 0
        and profit > 0
        and not severe_red_flags
        and available_checks >= 2
        and positive_checks >= 2
        and gmp is not None
        and gmp > 0
        and estimate is not None
        and estimate >= 10
    )
    if apply:
        reasons = [
            f"FY{fundamentals.get('financial_year', '')} revenue ₹{revenue:,.2f} and PAT ₹{profit:,.2f} are positive",
            f"{positive_checks} of {available_checks} checks passed: {', '.join(passed_checks)}",
            f"GMP ₹{gmp:,.2f} implies an unofficial estimated gain of {estimate:.2f}%",
        ]
        if failed_checks:
            reasons.append(f"Checks below the screen: {', '.join(failed_checks)}")
    fundamental_pass = (
        fundamental_ready
        and revenue > 0
        and profit > 0
        and not severe_red_flags
        and available_checks >= 2
        and positive_checks >= 2
    )
    revenue_yoy = (
        f"{(revenue - previous_revenue) / previous_revenue * 100:+.1f}%"
        if revenue is not None and previous_revenue is not None and previous_revenue > 0
        else "not available"
    )
    pat_yoy = (
        f"{(profit - previous_profit) / previous_profit * 100:+.1f}%"
        if profit is not None and previous_profit is not None and previous_profit > 0
        else "not available"
    )
    return {
        "Recommendation": "APPLY" if apply else "AVOID",
        "Fundamental Status": "Pass" if fundamental_pass else "Fail / Incomplete",
        "Analysis & Rationale": "; ".join(reasons),
        "Fundamental Summary": (
            f"FY{fundamentals.get('financial_year', 'N/A')} revenue: "
            f"{'₹{:,.2f}'.format(revenue) if revenue is not None else 'not reported'}; "
            f"revenue YoY: {revenue_yoy}; "
            f"PAT: {'₹{:,.2f}'.format(profit) if profit is not None else 'not reported'}; "
            f"PAT YoY: {pat_yoy}; "
            f"ROE: {'{:.2f}%'.format(roe) if roe is not None else 'not reported'}; "
            f"ROCE: {'{:.2f}%'.format(roce) if roce is not None else 'not reported'}; "
            f"PAT margin: {'{:.2f}%'.format(pat_margin) if pat_margin is not None else 'not reported'}; "
            f"debt/equity: {'{:.2f}'.format(debt_equity) if debt_equity is not None else 'not reported'}."
        ),
    }


def parse_ipo_html(html: bytes | str, today: date | None = None) -> list[dict[str, Any]]:
    from bs4 import BeautifulSoup

    reference_date = today or date.today()
    soup = BeautifulSoup(html, "html.parser")
    ipo_records = []
    seen = set()
    matched_live_table = False

    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        header_row = next(
            (row for row in rows if row.find_all(["th", "td"])),
            None,
        )
        if header_row is None:
            continue
        headers = [
            cell.get_text(" ", strip=True).lower()
            for cell in header_row.find_all(["th", "td"])
        ]
        name_index = next(
            (
                index
                for index, header in enumerate(headers)
                if "company" in header or "ipo name" in header or header == "name"
            ),
            next(
                (index for index, header in enumerate(headers) if header == "ipo"),
                None,
            ),
        )
        indices = {
            "name": name_index,
            "gmp": next((i for i, header in enumerate(headers) if "gmp" in header), None),
            "price": next((i for i, header in enumerate(headers) if "price" in header), None),
            "open": next((i for i, header in enumerate(headers) if "open" in header), None),
            "close": next(
                (i for i, header in enumerate(headers) if "clos" in header),
                None,
            ),
            "type": next((i for i, header in enumerate(headers) if "type" in header or "category" in header), None),
        }
        if any(indices[key] is None for key in ("name", "gmp", "price", "open", "close")):
            continue
        matched_live_table = True

        for row in rows[rows.index(header_row) + 1 :]:
            cells = row.find_all("td")
            required_indices = [indices[key] for key in ("name", "gmp", "price", "open", "close")]
            if not cells or max(required_indices) >= len(cells):
                continue
            raw_name = cells[indices["name"]].get_text(" ", strip=True)
            open_date = cells[indices["open"]].get_text(" ", strip=True)
            close_date = cells[indices["close"]].get_text(" ", strip=True)
            company = re.sub(
                r"(?i)\s*(?:SME\s*)?IPO(?:U|C|L|O)?\s*$",
                "",
                raw_name,
            )
            company = re.sub(r"(?i)\s*(?:SME|NSE|BSE)\s*$", "", company).strip(" -")
            company_key = re.sub(r"\s+", " ", company).casefold()
            if (
                not company_key
                or company_key in seen
                or not is_active_today_or_future(close_date, today=reference_date)
            ):
                continue

            gmp_text = cells[indices["gmp"]].get_text(" ", strip=True)
            price_text = cells[indices["price"]].get_text(" ", strip=True)
            gmp_match = re.search(r"[-+]?\s*₹?\s*([\d,]+(?:\.\d+)?)", gmp_text)
            price_matches = re.findall(r"[\d,]+(?:\.\d+)?", price_text)
            gmp_value = (
                float(gmp_match.group(1).replace(",", ""))
                * (-1 if "-" in gmp_match.group(0) else 1)
                if gmp_match
                else 0.0
            )
            issue_price = float(price_matches[-1].replace(",", "")) if price_matches else 0.0
            percent_match = re.search(r"\(([-+]?\d+(?:\.\d+)?)\s*%\)", gmp_text)
            gain_percent = (
                float(percent_match.group(1))
                if percent_match
                else round(gmp_value / issue_price * 100, 1)
                if issue_price > 0
                else 0.0
            )
            parsed_close = parse_ipo_date(close_date, today=reference_date)
            parsed_open = parse_ipo_date(open_date, today=reference_date)
            if parsed_close == reference_date:
                status = "Ongoing (Closing Today)"
            elif parsed_open and parsed_open <= reference_date:
                status = "Ongoing (Open)"
            else:
                status = "Upcoming"
            is_sme = "SME" in raw_name.upper()
            if indices["type"] is not None and indices["type"] < len(cells):
                is_sme = is_sme or "SME" in cells[indices["type"]].get_text(" ", strip=True).upper()
            ipo_records.append(
                {
                    "Company": company,
                    "Status": status,
                    "Type": "SME" if is_sme else "Mainboard",
                    "Issue Price (₹)": issue_price,
                    "GMP (₹)": gmp_value,
                    "Est Gain %": gain_percent,
                    "Lot Size": "Not reported",
                    "Subscription": "-",
                    "Open Date": open_date,
                    "Close Date": close_date,
                    "Recommendation": "NOT RATED",
                    "Analysis & Rationale": (
                        f"Estimated listing premium of {gain_percent:.1f}% "
                        "based on the source's grey-market figure; GMP is unofficial. "
                        "Company fundamentals were not verified, so no apply/avoid call is made."
                    ),
                }
            )
            seen.add(company_key)

    if not matched_live_table:
        raise ValueError("The live IPO page no longer contains a table with the expected columns.")
    return ipo_records


def assess_fundamentals(info: dict[str, Any]) -> dict[str, Any]:
    def numeric_value(key: str) -> float | None:
        value = info.get(key)
        if isinstance(value, bool):
            return None
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return number if math.isfinite(number) else None

    net_income = numeric_value("netIncomeToCommon")
    profit_margin = numeric_value("profitMargins")
    roe = numeric_value("returnOnEquity")
    debt_to_equity = numeric_value("debtToEquity")
    sector_text = " ".join(
        str(info.get(key) or "") for key in ("sector", "industry")
    ).lower()
    is_financial_company = any(
        term in sector_text
        for term in ("bank", "financial", "insurance", "capital markets")
    )

    checks: list[tuple[str, bool]] = []
    red_flags: list[str] = []
    if net_income is not None:
        checks.append(("Positive net income", net_income > 0))
        if net_income <= 0:
            red_flags.append("reported net income is not positive")
    if profit_margin is not None:
        checks.append(("Positive profit margin", profit_margin > 0))
        if profit_margin <= 0:
            red_flags.append("reported profit margin is not positive")
    if roe is not None:
        checks.append(("ROE at least 8%", roe >= 0.08))
        if roe < 0:
            red_flags.append("reported ROE is negative")
    if debt_to_equity is not None and not is_financial_company:
        checks.append(("Debt-to-equity at or below 100%", debt_to_equity <= 100))
        if debt_to_equity > 200:
            red_flags.append("debt-to-equity exceeds 200%")

    positive_checks = sum(passed for _, passed in checks)
    buy_eligible = (
        len(checks) >= 2 and positive_checks >= 2 and not red_flags
    )
    if buy_eligible:
        status = "Pass"
        summary = "At least two available fundamental checks passed with no severe red flags."
    elif red_flags:
        status = "Fail"
        summary = "; ".join(red_flags)
    else:
        status = "Insufficient data"
        summary = "At least two positive fundamental checks could not be verified."

    return {
        "status": status,
        "buy_eligible": buy_eligible,
        "summary": summary,
        "checks": checks,
        "net_income": net_income,
        "profit_margin": profit_margin,
        "roe": roe,
        "debt_to_equity": debt_to_equity,
        "is_financial_company": is_financial_company,
    }


def build_virtual_trade(
    call: dict[str, Any], called_at: datetime | None = None
) -> dict[str, Any]:
    entry_price = float(call["entry_price"])
    target_price = float(call["target_price"])
    stop_loss = float(call["stop_loss"])
    if (
        not all(math.isfinite(value) for value in (entry_price, target_price, stop_loss))
        or entry_price <= 0
        or target_price <= entry_price
        or stop_loss <= 0
        or stop_loss >= entry_price
    ):
        raise ValueError("A BUY call needs a positive entry, target above entry, and stop-loss.")

    timestamp = called_at or datetime.now(timezone.utc)
    identity = "|".join(
        (
            timestamp.date().isoformat(),
            str(call["ticker"]).upper(),
            str(call["source"]),
            str(call["horizon"]),
        )
    )
    trade_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    return {
        "id": trade_id,
        "called_at": timestamp.isoformat(),
        "ticker": str(call["ticker"]).upper(),
        "company": str(call.get("company") or call["ticker"]),
        "source": str(call["source"]),
        "horizon": str(call["horizon"]),
        "entry_price": round(entry_price, 2),
        "quote_as_of": str(call.get("quote_as_of") or ""),
        "target_price": round(target_price, 2),
        "stop_loss": round(stop_loss, 2),
        "virtual_investment": VIRTUAL_INVESTMENT,
        "quantity": round(VIRTUAL_INVESTMENT / entry_price, 6),
        "fundamental_status": str(call.get("fundamental_status", "Pass")),
        "fundamental_summary": str(call.get("fundamental_summary", "")),
    }


def sync_virtual_trades(
    calls: list[dict[str, Any]],
    bin_id: str,
    master_key: str,
    http: Any = None,
    called_at: datetime | None = None,
) -> dict[str, int]:
    if not bin_id or not master_key:
        raise ValueError("Set JSONBIN_BIN_ID and JSONBIN_MASTER_KEY to enable trade logging.")
    if http is None:
        import requests

        http = requests

    base_url = f"https://api.jsonbin.io/v3/b/{bin_id}"
    headers = {
        "X-Master-Key": master_key,
        "Content-Type": "application/json",
    }
    existing_trades = fetch_virtual_trades(bin_id, master_key, http=http)
    existing_ids = {
        item.get("id")
        for item in existing_trades
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    new_trades = []
    for call in calls:
        trade = build_virtual_trade(call, called_at=called_at)
        if trade["id"] not in existing_ids:
            new_trades.append(trade)
            existing_ids.add(trade["id"])

    if new_trades:
        update = http.put(
            base_url,
            headers=headers,
            json={"trades": [*existing_trades, *new_trades]},
            timeout=15,
        )
        update.raise_for_status()

    return {"added": len(new_trades), "duplicates": len(calls) - len(new_trades)}


def fetch_virtual_trades(bin_id: str, master_key: str, http: Any = None) -> list[dict[str, Any]]:
    if not bin_id or not master_key:
        raise ValueError("Set JSONBIN_BIN_ID and JSONBIN_MASTER_KEY to load the virtual portfolio.")
    if http is None:
        import requests

        http = requests

    response = http.get(
        f"https://api.jsonbin.io/v3/b/{bin_id}/latest",
        headers={"X-Master-Key": master_key},
        timeout=15,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("The JSONBin response is not a valid object.")
    record = payload.get("record")
    if not isinstance(record, dict) or not isinstance(record.get("trades"), list):
        raise ValueError('The JSONBin must contain an object with a "trades" array.')
    required_fields = {
        "id",
        "ticker",
        "entry_price",
        "target_price",
        "stop_loss",
        "virtual_investment",
        "quantity",
    }
    if any(
        not isinstance(trade, dict) or not required_fields.issubset(trade)
        for trade in record["trades"]
    ):
        raise ValueError("The JSONBin trades array contains an invalid trade record.")
    for trade in record["trades"]:
        try:
            entry_price = float(trade["entry_price"])
            target_price = float(trade["target_price"])
            stop_loss = float(trade["stop_loss"])
            investment = float(trade["virtual_investment"])
            quantity = float(trade["quantity"])
        except (TypeError, ValueError) as exc:
            raise ValueError("The JSONBin contains a trade with invalid numeric values.") from exc
        if (
            not isinstance(trade["ticker"], str)
            or not all(
                math.isfinite(value)
                for value in (entry_price, target_price, stop_loss, investment, quantity)
            )
            or entry_price <= 0
            or target_price <= entry_price
            or stop_loss <= 0
            or stop_loss >= entry_price
            or investment <= 0
            or quantity <= 0
        ):
            raise ValueError("The JSONBin contains an invalid virtual trade.")
    return record["trades"]
