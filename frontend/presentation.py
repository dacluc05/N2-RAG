"""Vietnamese labels and formatting for report views."""
from datetime import date
import re

from finsight.insights import vi_number

METRICS = {
    "revenue": "Doanh thu", "gross_profit": "Lợi nhuận gộp",
    "operating_income": "Lợi nhuận hoạt động", "net_income": "Lợi nhuận ròng",
    "eps_diluted": "Lãi pha loãng trên mỗi cổ phiếu",
    "assets": "Tổng tài sản", "liabilities": "Tổng nợ phải trả", "equity": "Vốn chủ sở hữu",
    "cash": "Tiền và tương đương tiền", "ocf": "Dòng tiền hoạt động",
    "capex": "Chi đầu tư", "current_assets": "Tài sản ngắn hạn",
    "current_liabilities": "Nợ ngắn hạn", "debt_current": "Nợ dài hạn đến hạn trả",
    "debt_noncurrent": "Nợ vay dài hạn", "short_borrowings": "Vay ngắn hạn",
    "shares": "Cổ phiếu đang lưu hành", "da": "Khấu hao và phân bổ",
    "pretax": "Lợi nhuận trước thuế", "tax": "Chi phí thuế thu nhập",
    "revenue_growth": "Tăng trưởng doanh thu", "net_income_growth": "Tăng trưởng lợi nhuận ròng",
    "gross_margin": "Biên lợi nhuận gộp", "operating_margin": "Biên lợi nhuận hoạt động",
    "net_margin": "Biên lợi nhuận ròng", "roe": "Tỷ suất sinh lời trên vốn chủ sở hữu (ROE)",
    "roa": "Tỷ suất sinh lời trên tài sản (ROA)", "roic": "Tỷ suất sinh lời trên vốn đầu tư (ROIC)",
    "current_ratio": "Hệ số thanh toán hiện hành", "debt_equity": "Nợ vay trên vốn chủ sở hữu",
    "net_debt": "Nợ vay ròng", "fcf": "Dòng tiền tự do", "fcf_margin": "Biên dòng tiền tự do",
    "cash_conversion": "Dòng tiền hoạt động trên lợi nhuận ròng",
    "pe": "Giá trên lợi nhuận (P/E)", "pb": "Giá trên giá trị sổ sách (P/B)",
    "p_fcf": "Giá trên dòng tiền tự do (P/FCF)", "ev_ebitda": "Giá trị doanh nghiệp trên EBITDA",
}
PERIODS = {"FY": "Năm tài chính", "Q": "Quý", "YTD": "Lũy kế từ đầu năm", "instant": "Tại thời điểm"}
FORMULA_TERMS = METRICS | {
    "average": "Bình quân", "interest_bearing_debt": "Nợ vay chịu lãi",
    "invested_capital": "Vốn đầu tư", "prior_invested_capital": "Vốn đầu tư kỳ trước",
    "market_cap": "Vốn hóa thị trường",
    "operating_expenses": "Chi phí hoạt động",
    "operating_expenses_growth": "Tăng trưởng chi phí hoạt động",
}


def metric_name(key):
    return METRICS.get(key, "Chỉ tiêu khác")


def vi_date(value):
    return date.fromisoformat(str(value)[:10]).strftime("%d/%m/%Y") if value else "—"


def vi_unit(unit):
    if unit == "shares":
        return "cổ phiếu"
    if unit.endswith("/shares"):
        return unit.removesuffix("/shares") + "/cổ phiếu"
    return "lần" if unit == "x" else unit


def value_text(value, unit, *, include_unit=True):
    if value is None:
        return "Chưa có số liệu"
    places = 0 if unit not in {"%", "x"} and value == int(value) else 2
    return vi_number(value, places) + ((" " + vi_unit(unit)) if include_unit else "")


def formula_text(formula):
    def translate(match):
        token = match[0]
        if token.startswith("prior_") and token[6:] in FORMULA_TERMS:
            return FORMULA_TERMS[token[6:]] + " kỳ trước"
        return FORMULA_TERMS.get(token, token)
    return re.sub(r"[a-z_]+", translate, formula)


def fact_title(fact):
    return f"{metric_name(fact['key'])} · {vi_date(fact['end'])}"
