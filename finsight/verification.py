import math
import re
from datetime import date, timedelta

from finsight.schema import Draft, Evidence, Fact, Ratio, Verified


def flat(text: str) -> str:
    return " ".join(text.casefold().split())


PERCENTAGE = re.compile(r"(?<![\d.,])([+-]?\d+(?:[.,]\d+)?)\s*(?:\|+\s*)?%")
DATE_STAMP = r"\b(?:\d{4}-\d{2}-\d{2}|\d{1,2}[/-]\d{1,2}[/-]\d{4}|\d{1,2}\s+tháng\s+\d{1,2}\s+năm\s+\d{4})\b"
CLAIM_DATE = re.compile(DATE_STAMP, re.I)
PERIOD_DATE = re.compile(r"kết thúc(?:\s+vào)?(?:\s+ngày)?\s+(" + DATE_STAMP + ")", re.I)


def period_date(stamp: str) -> str:
    parts = [int(part) for part in re.findall(r"\d+", stamp)]
    if len(stamp.split("-", 1)[0]) == 4 and "-" in stamp:
        year, month, day = parts
    else:
        day, month, year = parts
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return ""


def stated_percentages_match(text: str, values: list[float]) -> bool:
    displayed = [match[1].replace(",", ".") for match in PERCENTAGE.finditer(text)]
    if len(displayed) != len(values):
        return False
    # Match each displayed value at its own precision, including repeated percentages.
    for raw in sorted(displayed, key=lambda value: -len(value.partition(".")[2])):
        tolerance = .5 * 10 ** -len(raw.partition(".")[2]) + 1e-10
        nearest = min(range(len(values)), key=lambda index: abs(values[index] - float(raw)))
        if abs(values[nearest] - float(raw)) > tolerance:
            return False
        values.pop(nearest)
    return True


def reported_percentage_matches(text: str, quotes: list[str], claimed: float, actual: float) -> bool:
    def displays(passage):
        for match in PERCENTAGE.finditer(passage):
            raw = match[1].replace(",",".")
            if float(raw) == claimed:
                yield len(raw.partition(".")[2])

    # Accept rounding only if the same stated precision appears in the claim and original excerpt.
    precision = set(displays(text)) & {digits for q in quotes for digits in displays(q)}
    return any(abs(claimed-actual) <= .5*10**(-digits)+1e-10 for digits in precision)



CASH_WITH_SECURITIES = re.compile(
    r"(?:tiền mặt|tiền),?\s*(?:và\s+)?tương đương tiền\s+và\s+chứng khoán (?:nợ|thị trường|có thể giao dịch)|cash,?\s+cash equivalents,?\s+and marketable (?:debt )?securities",
    re.I,
)
SEGMENT_REVENUE = re.compile(
    r"\bdoanh thu\s+(?:của\s+)?(?:mảng|phân khúc|bộ phận)\b"
    r"|\b(?:mảng|phân khúc|bộ phận)\b[^.;:\n]{0,120}\bdoanh thu\b",
    re.I,
)
USD_DISPLAY = re.compile(r"(?<![\d.,])(\d{1,3}(?:\.\d{3})+|\d+)(?:,(\d+)|\.(\d{1,2}))?\s+(triệu|tỷ)\s+USD\b", re.I)
TABLE_NUMBER = re.compile(r"\d{1,3}(?:,\d{3})+|\d+")
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def table_cells(line):
    return [cell.strip() for cell in line.split("|") if cell.strip() and cell.strip() != "$"]


def table_amounts(cells):
    if not cells or not all(TABLE_NUMBER.fullmatch(cell) for cell in cells):
        return []
    return [int(cell.replace(",", "")) * 1_000_000 for cell in cells]


def displayed_amount(match):
    scale = 1_000_000 if match[4].lower() == "triệu" else 1_000_000_000
    fraction = match[2] or match[3] or ""
    value = float(match[1].replace(".", "") + "." + fraction) * scale
    return value, scale / (2 * 10 ** len(fraction))


CASH_TOTAL_IN_PROSE = re.compile(
    r"cash,? cash equivalents,? and marketable (?:debt )?securities"
    r"(?:,? which)? (?:totaled|totalled|amounted to|were) "
    r"\$([\d,]+(?:\.\d+)?) (million|billion) as of "
    r"([A-Za-z]+ \d{1,2}, \d{4})\b",
    re.I,
)
FULL_MONTHS = ("January", "February", "March", "April", "May", "June",
               "July", "August", "September", "October", "November", "December")


def cash_prose_matches(quote, end, amount):
    dates = {f"{month} {end.day}, {end.year}".casefold()
             for month in (MONTHS[end.month - 1], FULL_MONTHS[end.month - 1])}
    displayed, claim_precision = displayed_amount(amount)
    for match in CASH_TOTAL_IN_PROSE.finditer(flat(quote)):
        if match[3].casefold() not in dates:
            continue
        number = match[1].replace(",", "")
        scale = 1_000_000_000 if match[2].lower() == "billion" else 1_000_000
        reported = float(number) * scale
        source_precision = scale / (2 * 10 ** len(number.partition(".")[2]))
        # The filing rounds the prose amount. Only corroborate at shared precision.
        if claim_precision >= source_precision and abs(displayed - reported) <= claim_precision:
            yield True


def scoped_financial_result(draft, excerpts, as_of):
    """Check the same scoped amount in a filing table or an explicit cash-total disclosure."""
    cash = bool(CASH_WITH_SECURITIES.search(draft.text))
    segment = bool(SEGMENT_REVENUE.search(draft.text))
    if cash == segment:
        return None
    measures = [n for n in [draft.numeric, *draft.comparisons] if n]
    if any(n.unit != "USD" for n in measures):
        return None
    amounts = list(USD_DISPLAY.finditer(draft.text))
    if not amounts or (cash and len(amounts) != 1) or len(re.findall(r"\bUSD\b", draft.text, re.I)) != len(amounts):
        return None
    outcomes = set()
    for source, quote in excerpts:
        end = source.report_end
        if source.quality != "primary" or source.kind not in {"10-K", "10-Q", "10-K/A", "10-Q/A"} or not end:
            continue
        if any(n.end != end or n.period not in ({None, "instant"} if cash else {None, "FY"})
               for n in measures):
            continue
        dates = CLAIM_DATE.findall(draft.text)
        if not dates or {period_date(stamp) for stamp in dates} != {end.isoformat()}:
            continue
        if re.search(r"hiện (?:nay|tại)|mới nhất|\bcurrently\b|\btoday\b", draft.text, re.I) and end < as_of - timedelta(days=370):
            continue
        date_label = f"{MONTHS[end.month - 1]} {end.day}, {end.year}"
        if cash:
            outcomes.update(cash_prose_matches(quote, end, amounts[0]))
        lines = source.text.splitlines()
        for index, line in enumerate(lines):
            cells = table_cells(line)
            if len(cells) < 2 or flat(line) not in flat(quote):
                continue
            values = table_amounts(cells[1:])
            if not values:
                continue
            header = [table_cells(row) for row in lines[max(0, index-5):index]]
            if not any(row and re.fullmatch(r"\(in millions\)", row[0], re.I) for row in header):
                continue
            if cash and flat(cells[0]) == "cash, cash equivalents, and marketable debt securities":
                if not any(len(row) == len(values) and row[0] == date_label for row in header):
                    continue
                actual = [values[0]]
            elif segment and flat(cells[0]) == "revenue":
                if not any(row and row[0] == "Year Ended " + date_label for row in header):
                    continue
                columns = next((row for row in header if len(row) == len(values) and flat(row[-1]) == "total"), [])
                if not columns or sum(values[:-1]) != values[-1]:
                    continue
                actual = []
                seen_columns = set()
                start = 0
                for amount in amounts:
                    prefix = flat(draft.text[start:amount.start()])
                    matching = [(label, value) for label, value in zip(columns[:-1], values[:-1])
                                if re.search(r"(?<!\w)" + re.escape(flat(label)) + r"(?!\w)", prefix)]
                    if len(matching) == 1 and matching[0][0] not in seen_columns:
                        label, value = matching[0]
                        seen_columns.add(label)
                        actual.append(value)
                    start = amount.end()
                if len(actual) != len(amounts):
                    continue
            else:
                continue
            outcomes.add(all(abs(displayed - value) <= rounding for (displayed, rounding), value in
                             zip(map(displayed_amount, amounts), actual)))
    return next(iter(outcomes)) if len(outcomes) == 1 else None



def numeric_contract_issue(draft):
    """Validate what the agent encoded before treating a mismatch as a factual error."""
    measures = [n for n in [draft.numeric, *draft.comparisons] if n]
    dates = {period_date(stamp) for stamp in CLAIM_DATE.findall(draft.text)}
    if dates and any(n.end.isoformat() not in dates for n in measures):
        return "NUMERIC_PERIOD", "Kỳ khai báo để kiểm chứng không khớp ngày trong câu nhận định."
    text = flat(draft.text)
    period = "YTD" if re.search(r"lũy kế|year.to.date|six months|nine months", text) else (
        "Q" if re.search(r"\bquý\b|\bquarter\b", text) else
        "FY" if re.search(r"năm tài chính|fiscal year", text) else None)
    if period and any(n.period and n.period not in {period, "instant"} for n in measures):
        return "NUMERIC_PERIOD", "Loại kỳ khai báo không khớp kỳ được mô tả trong nhận định."
    if re.search(r"\b(?:mảng|phân khúc|bộ phận|segment|iphone|ipad|mac|services|graphics|compute|data center)\b", text):
        return "NUMERIC_SCOPE", "Nhận định có phạm vi sản phẩm hoặc phân khúc; không dùng số toàn doanh nghiệp để phản bác."
    if re.search(r"điểm phần trăm|percentage points|basis points|điểm cơ bản", text):
        return "NUMERIC_SCOPE", "Cần đối chiếu mức thay đổi theo điểm phần trăm, không so trực tiếp với tỷ lệ phần trăm."
    if re.search(r"dự kiến|dự báo|ước tính|forecast|guidance|adjusted|non.gaap|điều chỉnh", text):
        return "NUMERIC_SCOPE", "Cần số đối chiếu cùng cơ sở dự báo hoặc điều chỉnh với nhận định."
    labels = {
        "revenue": r"doanh thu|revenue|sales",
        "net_income": r"lợi nhuận (?:ròng|sau thuế)|net income",
        "operating_income": r"(?:lợi nhuận|thu nhập) (?:từ )?hoạt động|operating income",
        "gross_profit": r"lợi nhuận gộp|gross profit",
        "cash": r"tiền|cash",
        "ocf": r"dòng tiền.*(?:hoạt động|kinh doanh)|operating cash",
        "fcf": r"dòng tiền tự do|free cash",
    }
    for n in measures:
        if n.key in labels and not re.search(labels[n.key], text):
            return "NUMERIC_SCOPE", "Tên chỉ tiêu gửi kiểm chứng không khớp nội dung câu nhận định."
        if n.key in labels and re.search(r"tăng trưởng|tăng.*%|giảm.*%|growth", text) and n.unit == "USD" and not USD_DISPLAY.search(draft.text):
            return "NUMERIC_SCOPE", "Nhận định nói về tốc độ thay đổi nhưng chỉ tiêu khai báo là số tiền tuyệt đối."
    amounts = list(USD_DISPLAY.finditer(draft.text))
    usd = [n for n in measures if n.unit == "USD"]
    if amounts and usd:
        if len(amounts) != len(usd):
            return "INCOMPLETE_COMPARISON", "Chưa khai báo đủ chỉ tiêu cho từng số tiền trong nhận định."
        for amount, n in zip(amounts, usd):
            value, rounding = displayed_amount(amount)
            if abs(value - n.value) > rounding:
                if any(math.isclose(n.value * scale, value, rel_tol=.001) for scale in (1e6, 1e9)):
                    return "NUMERIC_SCALE", "Giá trị gửi kiểm chứng chưa được quy đổi về USD tuyệt đối."
                return "NUMERIC_TEXT_MISMATCH", "Số gửi kiểm chứng khác số được viết trong câu; chưa thể kết luận câu bị phản bác."
    return None


def has_interpretation(text):
    return bool(re.search(r"cho thấy|phản ánh|chứng tỏ|chứng minh|vì vậy|do đó|nhờ|dẫn đến|rủi ro|triển vọng|an toàn|bền vững|shows|indicates|therefore|because", text, re.I))

def verify(draft: Draft, claim_id: str, role: str, *, cik: int, as_of: date,
           provided: list[Evidence], numbers: list[Fact | Ratio], review=None,
           counters: list[Evidence] | None = None, tolerance=.001) -> Verified:
    admissible = {e.id:e for e in provided if e.company_cik == cik and e.published
                  and e.published <= as_of and e.persist}
    evidence, excerpts = [], []
    current = bool(re.search(r"hiện (?:nay|tại)|mới nhất|\bcurrently\b|\btoday\b", draft.text, re.I))
    for ref in draft.references:
        e = admissible.get(ref.evidence_id)
        if e and flat(ref.quote) in flat(e.text) and (not current or e.published >= as_of-timedelta(days=370)):
            evidence.append(e.id)
            excerpts.append((e,ref.quote))
    used = list(dict.fromkeys(evidence))
    opponents = [e for e in (counters or []) if e.company_cik == cik and e.published
                 and e.published <= as_of and e.persist and e.id not in used
                 and (not current or e.published >= as_of-timedelta(days=370))]

    def result(status, reason, counter_ids=None, *, code=""):
        return Verified(id=claim_id,role=role,claim=draft,status=status,reason=reason,reason_code=code,
                        evidence_ids=used,counter_ids=counter_ids or [])

    if not used:
        return result("UNVERIFIED", "Không có trích đoạn hợp lệ được lưu cho nhận định.", code="MISSING_SOURCE")
    filings = [e for e, _ in excerpts if e.report_end and e.kind in
               {"10-K", "10-Q", "10-K/A", "10-Q/A", "20-F", "40-F", "20-F/A", "40-F/A"}]
    filing_dates = {e.published.isoformat() for e in filings}
    period_ends = {e.report_end.isoformat() for e in filings}
    if any(period_date(stamp) in filing_dates - period_ends for stamp in PERIOD_DATE.findall(draft.text)):
        return result("UNVERIFIED", "Nhận định dùng ngày nộp hồ sơ làm ngày kết thúc kỳ.",
                      code="FILING_DATE_AS_PERIOD")
    if role != "computed" and re.search(r"dự kiến|dự báo|ước tính|forecast|guidance|adjusted|non.gaap|điều chỉnh", draft.text, re.I) and (draft.numeric or USD_DISPLAY.search(draft.text)):
        return result("UNVERIFIED", "Cần số đối chiếu cùng cơ sở dự báo hoặc điều chỉnh với nhận định.", code="NUMERIC_SCOPE")
    if CASH_WITH_SECURITIES.search(draft.text) or SEGMENT_REVENUE.search(draft.text):
        checked = scoped_financial_result(draft, excerpts, as_of)
        if checked is True and not has_interpretation(draft.text) and len(excerpts) == len(draft.references):
            return result("SUPPORTED", "Số liệu khớp phạm vi, đơn vị và kỳ trong trích dẫn SEC.",
                          code="SCOPED_TABLE_MATCH")
        if checked is True:
            return result("PARTIALLY_SUPPORTED", "Số liệu đúng phạm vi đã khớp; phần suy luận hoặc nguồn dẫn còn lại chưa được xác minh.",
                          code="PARTIAL_NUMERIC_CHECK")
        if checked is False:
            return result("CONTRADICTED", "Số liệu khác giá trị trong đúng dòng và cột của bảng SEC.",
                          code="SCOPED_TABLE_MISMATCH")
        return result("UNVERIFIED", "Chưa xác định được phạm vi hoặc kỳ tương ứng trong trích dẫn SEC.",
                      code="NUMERIC_SCOPE")
    if draft.numeric:
        if role != "computed":
            issue = numeric_contract_issue(draft)
            if issue:
                code, reason = issue
                return result("UNVERIFIED", reason, code=code)
        measures = [draft.numeric, *draft.comparisons]
        percentages = [n.value for n in measures if n.unit == "%"]
        if role != "computed" and not stated_percentages_match(draft.text, percentages):
            return result("UNVERIFIED", "Chưa có đủ chỉ số và kỳ cho từng tỷ lệ trong nhận định.",
                          code="INCOMPLETE_COMPARISON")
        for n in measures:
            # A consolidated metric cannot refute a segment, customer share or broader cash measure.
            scope_mismatch = (
                n.key == "cash" and re.search(r"chứng khoán|marketable", draft.text, re.I)
                or n.key == "revenue" and re.search(
                    r"khách hàng.{0,80}(?:chiếm|tỷ trọng)|%\s*(?:tổng )?doanh thu",
                    draft.text, re.I)
            )
            if scope_mismatch:
                return result("UNVERIFIED", "Chỉ tiêu khai báo có phạm vi khác câu nhận định; cần đối chiếu đúng dòng trong nguồn.",
                              code="NUMERIC_SCOPE")
            if current and n.end < as_of - timedelta(days=370):
                return result("UNVERIFIED", "Kỳ tài chính quá cũ cho nhận định hiện tại.", code="NUMERIC_PERIOD")
            allowed_periods = {n.period} if n.period else {"FY", "Q", "instant"}
            values = {(x.period, x.value) for x in numbers
                      if (x.key, x.unit, x.end) == (n.key, n.unit, n.end)
                      and x.period in allowed_periods and x.value is not None and x.filed
                      and x.end <= x.filed <= as_of}
            if not values:
                return result("UNVERIFIED", f"Đã có nguồn trích dẫn, chưa có số chuẩn hóa để đối chiếu kỳ {n.end:%d/%m/%Y}.",
                              code="MISSING_NUMERIC")
            if len(values) != 1:
                return result("UNVERIFIED", f"Có nhiều kết quả hoặc loại kỳ trùng ngày {n.end:%d/%m/%Y}; chưa xác định được số dùng để đối chiếu.",
                              code="AMBIGUOUS_NUMERIC")
            _, actual = next(iter(values))
            rounding = n.unit == "%" and reported_percentage_matches(
                draft.text, [quote for _, quote in excerpts], n.value, actual,
            )
            rel_tol = 1e-9 if n.unit == "%" else tolerance
            if not math.isclose(n.value, actual, rel_tol=rel_tol, abs_tol=0.0001) and not rounding:
                if n.unit == "USD" and any(
                    re.search(label, draft.text, re.I) and math.isclose(n.value * scale, actual, rel_tol=tolerance)
                    for label, scale in ((r"triệu\s+USD\b", 1e6), (r"tỷ\s+USD\b", 1e9))
                ):
                    return result("UNVERIFIED", "Giá trị gửi kiểm chứng chưa được quy đổi về USD tuyệt đối.",
                                  code="NUMERIC_SCALE")
                return result("CONTRADICTED", f"Số khai báo {n.value:g} {n.unit} khác số đối chiếu {actual:g} {n.unit} của chỉ tiêu {n.key} cùng kỳ {n.end:%d/%m/%Y}.",
                              code="NUMERIC_MISMATCH")
        if role == "computed":
            return result("SUPPORTED", "Nhận định do Python tạo trực tiếp từ dữ liệu SEC đã chuẩn hóa.")
    elif draft.comparisons:
        return result("UNVERIFIED", "Nhận định so sánh thiếu chỉ số hoặc kỳ chính.", code="INCOMPLETE_COMPARISON")
    if not draft.numeric and draft.dimension in {"financial","growth","valuation"} and re.search(
            r"\d[\d.,]*\s*(?:%|USD\b|EUR\b|tỷ\b|triệu\b)|\$\s*\d",draft.text,re.I):
        return result("UNVERIFIED","Nhận định số thiếu chỉ số, đơn vị và kỳ có cấu trúc để đối chiếu.")
    if len(excerpts) != len(draft.references):
        return result("PARTIALLY_SUPPORTED","Một số trích đoạn hoặc ID nguồn không hợp lệ.")
    if review is None:
        return result("UNVERIFIED","Có trích đoạn hợp lệ, chưa đánh giá đoạn trích có đủ để hỗ trợ nhận định.", code="REVIEW_PENDING")
    assessment = review(draft,excerpts,opponents[:3])
    candidates = {e.id for e in opponents[:3]}
    counter_ids = list(dict.fromkeys(i for i in assessment.counter_ids if i in candidates))
    if assessment.status == "CONTRADICTED" and not counter_ids:
        return result("UNVERIFIED","Chưa chỉ ra đoạn bằng chứng trái chiều hợp lệ.")
    return result(assessment.status,assessment.reason,counter_ids)


def coverage(claims: list[Verified], dimensions: list[str], changes: list[dict], evidence: list[Evidence]):
    accepted = [c for c in claims if c.status == "SUPPORTED"]
    return {
        "supported":len(accepted),"total_claims":len(claims),
        "supported_rate":len(accepted)/len(claims) if claims else None,
        "covered_dimensions":sorted({c.claim.dimension for c in accepted}),
        "total_dimensions":len(dimensions),
        "unresolved_conflicts":sum(not x["resolved"] for x in changes),
        "contradicted_claims":sum(c.status == "CONTRADICTED" for c in claims),
        "primary_evidence":sum(e.quality == "primary" for e in evidence),
        "latest_publication":max((e.published for e in evidence if e.published),default=None),
    }
