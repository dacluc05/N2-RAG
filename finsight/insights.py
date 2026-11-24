"""Observations derived from the normalized financial snapshot, including old reports."""
from datetime import date

from finsight.verification import PERIOD_DATE, period_date


def vi_number(value: float, places: int = 2) -> str:
    return f"{value:,.{places}f}".translate(str.maketrans(",.",".,"))


def percent(value: float) -> str:
    return vi_number(value,1)+"%"


def money(value: float) -> str:
    if abs(value)>=1e9:
        return vi_number(value/1e9)+" tỷ USD"
    if abs(value)>=1e6:
        return vi_number(value/1e6)+" triệu USD"
    return vi_number(value,0)+" USD"


def signals(report: dict) -> list[dict]:
    by_key = {}
    for fact in report["facts"]:
        if fact["unit"]=="USD" and fact["period"] in ("FY","Q"):
            key = (fact["key"],fact["period"],fact["end"])
            previous = by_key.get(key)
            if previous is None or fact["filed"] > previous["filed"]:
                by_key[key] = fact
    output = []
    for period in ("Q","FY"):
        revenue = sorted((f for (key,p,_),f in by_key.items() if key=="revenue" and p==period),
                         key=lambda f:f["end"],reverse=True)
        if not revenue:
            continue
        current = revenue[0]
        end = date.fromisoformat(current["end"])
        prior = next((f for f in revenue[1:] if 330<=(end-date.fromisoformat(f["end"])).days<=390),None)
        if prior is None or prior["value"]<=0:
            continue
        growth = 100*(current["value"]/prior["value"]-1)
        title = "Quý gần nhất" if period=="Q" else "Năm tài chính gần nhất"
        change = "tăng" if growth>=0 else "giảm"
        narrative = f"Doanh thu đạt {money(current['value'])}, {change} {percent(abs(growth))} so với cùng kỳ."
        gross = by_key.get(("gross_profit",period,current["end"]))
        prior_gross = by_key.get(("gross_profit",period,prior["end"]))
        inputs = [current,prior]
        if gross and prior_gross and current["value"]>0:
            margin = gross["value"]/current["value"]*100
            comparison = margin-prior_gross["value"]/prior["value"]*100
            direction = "tăng" if comparison>=0 else "giảm"
            narrative += f" Biên gộp {percent(margin)}, {direction} {vi_number(abs(comparison),1)} điểm phần trăm."
            inputs.extend((gross,prior_gross))
        output.append({"title":title,"period":period,"end":current["end"],"prior_end":prior["end"],
                       "text":narrative,"inputs":inputs})
    return output


def investment(report: dict) -> dict:
    """Use only the saved report so old reports retain their original data cutoff."""
    evidence = {item["id"]: item for item in report["evidence"]}
    claims = []
    for claim in report["claims"]:
        if claim["status"] != "SUPPORTED" or claim["role"] == "computed":
            continue
        sources = [evidence[item] for item in claim["evidence_ids"] if item in evidence]
        filing_dates = {item["published"] for item in sources if item.get("report_end")}
        period_ends = {item["report_end"] for item in sources if item.get("report_end")}
        if sources and not any(period_date(stamp) in filing_dates - period_ends
                               for stamp in PERIOD_DATE.findall(claim["claim"]["text"])):
            claims.append(claim)
    drivers = [c["id"] for c in claims if c["claim"]["dimension"] in {"industry", "growth", "moat"}
               and c["claim"]["stance"] != "negative"]
    risks = [c["id"] for c in claims if c["claim"]["dimension"] == "risk" or c["claim"]["stance"] == "negative"
             or (c["claim"]["dimension"] == "company" and "khách hàng" in c["claim"]["text"].lower()
                 and "phụ thuộc" in c["claim"]["text"].lower())]

    eps = [f for f in report["facts"] if f["key"] == "eps_diluted" and f["period"] == "FY"
           and f["unit"].endswith("/shares")]
    latest = max((f["end"] for f in eps), default=None)
    market = report.get("market") or {}
    currency = market.get("currency")
    candidates = [f for f in eps if f["end"] == latest and (not currency or f["unit"] == f"{currency}/shares")]
    earnings = candidates[0] if len(candidates) == 1 and candidates[0]["value"] > 0 else None
    cutoff = date.fromisoformat(report["request"]["as_of"])
    price = max((row for row in market.get("observations", [])
                 if row.get("close") and row["close"] > 0
                 and 0 <= (cutoff - date.fromisoformat(row["date"])).days <= 7),
                key=lambda row: row["date"], default=None)
    return {"signals": signals(report), "driver_ids": [cid for cid in drivers if cid not in risks][:3], "risk_ids": risks[:3],
            "eps": earnings, "price": {**price, "currency": currency, "url": market.get("url")} if price and currency else None}
