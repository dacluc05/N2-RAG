from collections import defaultdict
from datetime import date
from math import isfinite
from typing import Iterable

from finsight.schema import Fact, Ratio

# Each alias is intentionally equivalent or used as a fallback when the preferred
# issuer-wide US-GAAP concept is absent. Debt legs remain separate.
CONCEPTS = {
    "revenue": ("RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet"),
    "gross_profit": ("GrossProfit",),
    "research_and_development_expense": ("ResearchAndDevelopmentExpense",),
    "operating_income": ("OperatingIncomeLoss",),
    "operating_expenses": ("OperatingExpenses",),
    "net_income": ("NetIncomeLoss",),
    "eps_diluted": ("EarningsPerShareDiluted",),
    "assets": ("Assets",),
    "liabilities": ("Liabilities",),
    "equity": ("StockholdersEquity",),
    "cash": ("CashAndCashEquivalentsAtCarryingValue",),
    "ocf": ("NetCashProvidedByUsedInOperatingActivities",),
    "capex": ("PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets"),
    "current_assets": ("AssetsCurrent",),
    "current_liabilities": ("LiabilitiesCurrent",),
    "debt_current": ("LongTermDebtCurrent",),
    "debt_current_total": ("DebtCurrent",),
    "debt_noncurrent": ("LongTermDebtNoncurrent",),
    "long_term_debt_total": ("LongTermDebt",),
    "short_borrowings": ("ShortTermBorrowings",),
    "interest_expense": ("InterestExpense", "InterestExpenseNonoperating", "InterestAndDebtExpense"),
    "consolidated_profit": ("ProfitLoss",),
    "shares": ("CommonStockSharesOutstanding", "EntityCommonStockSharesOutstanding"),
    "da": ("DepreciationDepletionAndAmortization", "DepreciationDepletionAndAmortizationPropertyPlantAndEquipment"),
    "pretax": ("IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",),
    "tax": ("IncomeTaxExpenseBenefit",),
}
INSTANT = {"assets", "liabilities", "equity", "cash", "current_assets", "current_liabilities",
           "debt_current", "debt_current_total", "debt_noncurrent", "long_term_debt_total", "short_borrowings", "shares"}
FORMS = {"10-K", "10-K/A", "10-Q", "10-Q/A", "20-F", "20-F/A", "40-F", "40-F/A"}


def normalize(payload: dict, as_of: date, years: int) -> tuple[list[Fact], list[dict]]:
    taxonomies = payload.get("facts", {})
    cik = int(payload["cik"])
    candidates = defaultdict(list)
    for key, aliases in CONCEPTS.items():
        for priority, tag in enumerate(aliases):
            ns = "dei" if tag.startswith("Entity") else "us-gaap"
            for unit, rows in taxonomies.get(ns, {}).get(tag, {}).get("units", {}).items():
                if key == "shares":
                    acceptable = unit == "shares"
                elif key == "eps_diluted":
                    acceptable = len(unit.split("/")) == 2 and unit.endswith("/shares") and unit[:3].isupper()
                else:
                    acceptable = len(unit) == 3 and unit.isalpha() and unit.isupper()
                if not acceptable:
                    continue
                for row in rows:
                    if row.get("form") not in FORMS or not row.get("filed") or not row.get("accn"):
                        continue
                    value = row.get("val")
                    if type(value) not in (float, int) or not isfinite(value):
                        continue
                    end, filed = date.fromisoformat(row["end"]), date.fromisoformat(row["filed"])
                    if filed > as_of or end > as_of or filed < end:
                        continue
                    if end.year < as_of.year - years - 1:
                        continue
                    start = date.fromisoformat(row["start"]) if row.get("start") else None
                    days = (end - start).days + 1 if start else 0
                    if key in INSTANT and not start:
                        period = "instant"
                    elif key not in INSTANT and 330 <= days <= 390:
                        period = "FY"
                    elif key not in INSTANT and 70 <= days <= 110:
                        period = "Q"
                    elif key not in INSTANT and 140 <= days <= 305:
                        period = "YTD"
                    else:
                        continue
                    acc = row["accn"]
                    fiscal_year = row.get("fy") if 0 <= (filed - end).days <= 180 else None
                    fact = Fact(key=key, value=value, unit=unit, start=start, end=end,
                                filed=filed, period=period, concept=f"{ns}:{tag}", accession=acc,
                                fiscal_year=fiscal_year, fiscal_period=row.get("fp", "") if fiscal_year else "",
                                form=row["form"],
                                url=f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}/{acc}-index.html")
                    candidates[key, start, end, unit].append((priority, fact))
    facts, changes = [], []
    for matches in candidates.values():
        best_priority = min(priority for priority, _ in matches)
        comparable = sorted((f for p, f in matches if p == best_priority),
                            key=lambda f: (f.filed, f.form.endswith("/A"), f.accession))
        current = comparable[-1]
        previous = next((f for f in reversed(comparable[:-1]) if f.value != current.value), None)
        if previous:
            changes.append({"key": current.key, "end": str(current.end), "unit": current.unit,
                            "current": current.model_dump(mode="json"), "prior": previous.model_dump(mode="json"),
                            "resolved": previous.filed < current.filed and previous.accession != current.accession})
        facts.append(current)
    return sorted(facts, key=lambda f: (f.end, f.key, f.period, f.unit), reverse=True), changes


FORMULAS = {
    "revenue_growth": "100 × (revenue / prior_revenue − 1)",
    "net_income_growth": "100 × (net_income / prior_net_income − 1)",
    "operating_expenses_growth": "100 × (operating_expenses / prior_operating_expenses − 1)",
    "research_and_development_expense_growth": "100 × (research_and_development_expense / prior_research_and_development_expense − 1)",
    "gross_margin": "100 × gross_profit / revenue",
    "operating_margin": "100 × operating_income / revenue",
    "net_margin": "100 × net_income / revenue",
    "roe": "100 × net_income / average(equity, prior_equity)",
    "roa": "100 × net_income / average(assets, prior_assets)",
    "roic": "100 × operating_income × (1 − tax / pretax) / average(invested_capital, prior_invested_capital)",
    "current_ratio": "current_assets / current_liabilities",
    "debt_equity": "interest_bearing_debt / equity",
    "net_debt": "interest_bearing_debt − cash",
    "reported_debt": "reported_current_debt + reported_noncurrent_debt",
    "reported_debt_less_cash": "reported_debt − cash",
    "interest_coverage": "operating_income / interest_expense",
    "fcf": "ocf − capex",
    "fcf_margin": "100 × (ocf − capex) / revenue",
    "cash_conversion": "ocf / net_income",
    "pe": "market_cap / net_income",
    "pb": "market_cap / equity",
    "p_fcf": "market_cap / (ocf − capex)",
    "ev_ebitda": "(market_cap + interest_bearing_debt − cash) / (operating_income + da)",
}
VALUATION = {"pe", "pb", "p_fcf", "ev_ebitda"}
RESTRICTED = {"gross_margin", "operating_margin", "roic", "current_ratio", "debt_equity",
              "net_debt", "reported_debt", "reported_debt_less_cash", "interest_coverage",
              "fcf", "fcf_margin", "p_fcf", "ev_ebitda"}


def calculate(facts: Iterable[Fact], sic: str = "", market: dict | None = None,
              preferred_unit: str = "USD") -> list[Ratio]:
    annual, balances = defaultdict(dict), defaultdict(dict)
    for f in facts:
        if f.unit == preferred_unit and f.period in {"FY", "instant"}:
            group = annual if f.period == "FY" else balances
            if f.key not in group[f.end] or group[f.end][f.key].filed < f.filed:
                group[f.end][f.key] = f
    years = sorted(annual, reverse=True) or [None]
    result = []
    finance = sic.isdigit() and 6000 <= int(sic) <= 6799
    for end in years:
        current = {**annual[end], **balances[end]}
        prior_end = next((d for d in years if end and d and 330 <= (end - d).days <= 390), None)
        prior = {**annual[prior_end], **balances[prior_end]}
        market_value = market.get("market_cap") if market and market.get("currency") == preferred_unit and end == years[0] else None

        def item(key, source=current):
            return source[key].value if key in source else None

        def op(function, *args):
            if None in args:
                return None
            value = function(*args)
            return value if value is not None and isfinite(value) else None

        def div(n, d, scale=1):
            return op(lambda a, b: a * scale / b if b > 0 else None, n, d)

        def avg(key):
            return op(lambda a, b: (a+b)/2 if min(a,b) > 0 else None, item(key), item(key, prior))

        def debt_keys(source):
            if "debt_current_total" in source and "debt_noncurrent" in source:
                return ["debt_current_total", "debt_noncurrent"]
            if "long_term_debt_total" in source and "short_borrowings" in source:
                return ["long_term_debt_total", "short_borrowings"]
            if "debt_current_total" in source:
                return ["debt_current_total", "debt_noncurrent"]
            if "long_term_debt_total" in source:
                return ["long_term_debt_total", "short_borrowings"]
            return ["debt_current", "debt_noncurrent", "short_borrowings"]

        def debt(source):
            return op(lambda *legs: sum(legs), *(item(k, source) for k in debt_keys(source)))

        def invested(source):
            return op(lambda d,e,c: d+e-c, debt(source), item("equity", source), item("cash", source))

        revenue, income, operating = map(item, ("revenue", "net_income", "operating_income"))
        margin_profit_key = "net_income" if income is not None else "consolidated_profit"
        fcf = op(lambda a,b:a-b, item("ocf"), item("capex"))
        net_debt = op(lambda a,b:a-b, debt(current), item("cash"))
        known_debt_keys = [key for key in debt_keys(current) if key in current]
        reported_debt = sum(item(key) for key in known_debt_keys) if known_debt_keys else None
        tax_rate = div(item("tax"), item("pretax"))
        nopat = op(lambda a,b:a*(1-b) if 0 <= b <= 1 else None, operating, tax_rate)
        ebitda = op(lambda a,b:a+b, operating, item("da"))
        result_values = {
            "revenue_growth": (op(lambda x:x-100, div(revenue, item("revenue", prior),100)), "%", ["revenue"]),
            "net_income_growth": (op(lambda x:x-100, div(income,item("net_income",prior),100)), "%", ["net_income"]),
            "gross_margin": (div(item("gross_profit"),revenue,100), "%", ["gross_profit","revenue"]),
            "operating_margin": (div(operating,revenue,100), "%", ["operating_income","revenue"]),
            "net_margin": (div(item(margin_profit_key),revenue,100), "%", [margin_profit_key,"revenue"]),
            "roe": (div(income,avg("equity"),100), "%", ["net_income","equity"]),
            "roa": (div(income,avg("assets"),100), "%", ["net_income","assets"]),
            "roic": (div(nopat,op(lambda a,b:(a+b)/2 if min(a,b)>0 else None,invested(current),invested(prior)),100),
                     "%", ["operating_income","tax","pretax","equity","cash",*debt_keys(current)]),
            "current_ratio": (div(item("current_assets"),item("current_liabilities")), "x", ["current_assets","current_liabilities"]),
            "debt_equity": (div(debt(current),item("equity")), "x", [*debt_keys(current),"equity"]),
            "net_debt": (net_debt, preferred_unit, [*debt_keys(current),"cash"]),
            "reported_debt": (reported_debt, preferred_unit, known_debt_keys),
            "reported_debt_less_cash": (op(lambda a,b:a-b,reported_debt,item("cash")), preferred_unit, [*known_debt_keys,"cash"]),
            "interest_coverage": (div(operating,item("interest_expense")), "x", ["operating_income","interest_expense"]),
            "fcf": (fcf, preferred_unit, ["ocf","capex"]),
            "fcf_margin": (div(fcf,revenue,100), "%", ["ocf","capex","revenue"]),
            "cash_conversion": (div(item("ocf"),income), "x", ["ocf","net_income"]),
            "pe": (div(market_value,income), "x", ["market_cap","net_income"]),
            "pb": (div(market_value,item("equity")), "x", ["market_cap","equity"]),
            "p_fcf": (div(market_value,fcf), "x", ["market_cap","ocf","capex"]),
            "ev_ebitda": (div(op(lambda a,b:a+b,market_value,net_debt),ebitda), "x",
                           ["market_cap","cash",*debt_keys(current),"operating_income","da"]),
        }
        for key, (value, unit, input_keys) in result_values.items():
            if key in VALUATION and end != years[0]:
                continue
            reason = ""
            formula = FORMULAS[key]
            if key == "net_margin" and margin_profit_key == "consolidated_profit":
                formula = "100 × consolidated_profit / revenue"
                if value is not None:
                    reason = "Dùng lợi nhuận hợp nhất theo hồ sơ SEC."
            if finance and key in RESTRICTED:
                value, reason = None, "Tỷ số này không áp dụng theo bộ quy tắc SIC ngành tài chính."
            elif key in {"reported_debt", "reported_debt_less_cash"} and debt(current) is None and value is not None:
                reason = "Chỉ cộng các khoản nợ đã xác định. Có thể còn khoản nợ chưa thu thập được."
            elif value is None and key in {"net_debt","debt_equity","roic"} and debt(current) is None:
                reason = "Chưa đủ cấu phần nợ để tính. Xem chỉ tiêu nợ đã xác định."
            elif value is None and key in VALUATION and market_value is None:
                reason = "Chưa có vốn hóa thị trường cùng tiền tệ tại mốc báo cáo."
            elif value is None:
                reason = "Thiếu đầu vào cùng kỳ và tiền tệ hoặc mẫu số không dương."
            use_prior = key in {"revenue_growth","net_income_growth","roe","roa","roic"}
            input_facts = [current[k] for k in input_keys if k in current]
            if use_prior:
                prior_keys = ["equity","cash",*debt_keys(prior)] if key == "roic" else input_keys
                input_facts.extend(prior[k] for k in prior_keys if k in prior)
            refs = [fact_id(f) for f in input_facts]
            if "market_cap" in input_keys and market_value is not None:
                refs.append(market["url"])
                if market.get("shares_fact_id"):
                    refs.append(market["shares_fact_id"])
            result.append(Ratio(key=key,value=value,unit=unit,end=end,formula=formula,
                                inputs=refs, reason=reason,
                                filed=max((f.filed for f in input_facts),default=None)))
    return result


def calculate_quarterly(facts: Iterable[Fact], sic: str = "", preferred_unit: str = "USD") -> list[Ratio]:
    """Calculate comparable standalone quarters, without borrowing YTD or FY inputs."""
    quarters = defaultdict(lambda: defaultdict(list))
    for fact in facts:
        if fact.period == "Q" and fact.start and fact.unit == preferred_unit:
            quarters[fact.start, fact.end][fact.key].append(fact)

    finance = sic.isdigit() and 6000 <= int(sic) <= 6799
    margins = {"gross_margin": "gross_profit", "operating_margin": "operating_income",
               "net_margin": "net_income"}
    result = []

    def unique(group, key):
        items = group.get(key, [])
        if items and len({item.value for item in items}) == 1:
            return max(items, key=lambda item: item.filed)
        return None

    for (start, end), group in sorted(quarters.items(), reverse=True):
        revenue = unique(group, "revenue")
        prior_groups = [previous for (prior_start, prior_end), previous in quarters.items()
                        if 357 <= (start - prior_start).days <= 378
                        and 357 <= (end - prior_end).days <= 378
                        and abs((end - start).days - (prior_end - prior_start).days) <= 7]
        prior = prior_groups[0] if len(prior_groups) == 1 else {}
        pairs = [(key, unique(group, numerator), revenue) for key, numerator in margins.items()
                 if not finance or key not in RESTRICTED]
        pairs.extend((key, unique(group, metric), unique(prior, metric))
                     for key, metric in (("revenue_growth", "revenue"),
                                         ("net_income_growth", "net_income"),
                                         ("operating_expenses_growth", "operating_expenses"),
                                         ("research_and_development_expense_growth", "research_and_development_expense")))
        for key, numerator, denominator in pairs:
            if numerator is None or denominator is None or denominator.value <= 0:
                continue
            value = 100 * (numerator.value / denominator.value - (1 if key.endswith("_growth") else 0))
            if isfinite(value):
                result.append(Ratio(
                    key=key, value=value, unit="%", end=end, period="Q", formula=FORMULAS[key],
                    inputs=[fact_id(numerator), fact_id(denominator)], filed=max(numerator.filed, denominator.filed),
                ))
    return result


def fact_id(fact: Fact) -> str:
    return f"{fact.accession}/{fact.concept}/{fact.start or '-'}/{fact.end}/{fact.unit}"


def dcf(fcff: float, growth: float, discount: float, terminal_growth: float, net_debt: float,
        shares: float, years: int = 5) -> dict:
    if (not all(isfinite(x) for x in (fcff,growth,discount,terminal_growth,net_debt,shares))
            or shares <= 0 or fcff <= 0 or not 1 <= years <= 15 or not -1 < growth <= 1
            or not -1 < terminal_growth < discount <= 1 or discount <= 0):
        raise ValueError("Giả định DCF không hợp lệ")

    def scenario(wacc, terminal):
        if wacc <= max(0, terminal):
            return None
        flows = [fcff * (1+growth)**i for i in range(1, years+1)]
        tv = flows[-1]*(1+terminal)/(wacc-terminal)
        enterprise = sum(x/(1+wacc)**i for i,x in enumerate(flows,1)) + tv/(1+wacc)**years
        equity = enterprise-net_debt
        per_share = equity/shares
        if not all(isfinite(x) for x in (tv,enterprise,equity,per_share)):
            return None
        return {"terminal_value": tv, "enterprise_value": enterprise,
                "equity_value": equity, "per_share": per_share}

    base = scenario(discount,terminal_growth)
    if base is None:
        raise ValueError("Kịch bản DCF vượt giới hạn số học")
    return {"assumptions":{"fcff":fcff,"growth":growth,"discount":discount,"terminal_growth":terminal_growth,
                           "net_debt":net_debt,"shares":shares,"years":years},
            "base":base,
            "sensitivity":[{"discount":discount+w,"terminal_growth":terminal_growth+g,
                            "valuation":scenario(discount+w,terminal_growth+g)}
                           for w in (-.01,0,.01) for g in (-.01,0,.01)]}


METRIC_ALIASES = {
    "net_cash_provided_by_operating_activities":"ocf",
    "net_cash_provided_by_used_in_operating_activities":"ocf",
    "operating_cash_flow":"ocf", "free_cash_flow":"fcf",
    "total_operating_expenses":"operating_expenses",
    "net_profit":"net_income", "revenue_growth_rate":"revenue_growth",
}

def canonical_metric(value):
    if not isinstance(value,str): return value
    key = value.strip()
    lookup = {concept.casefold():name for name,concepts in CONCEPTS.items() for concept in concepts}
    return METRIC_ALIASES.get(key.casefold(),lookup.get(key.split(":")[-1].casefold(),key))
