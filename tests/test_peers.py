from datetime import date
from types import SimpleNamespace

from conftest import CUT, END, xbrl
from finsight.financials import calculate, normalize
from finsight.pipeline import Pipeline
from finsight.schema import Company, Fact, Request
from finsight.transport import Budget


def test_peers_require_matching_scope_and_cik():
    company=Company(ticker="EXMP",cik=123,name="Example Components")
    twin=Company(ticker="EXMA",cik=123,name="Example Components A")
    peer=Company(ticker="PAIR",cik=124,name="Peer Components")
    far=Company(ticker="FAR",cik=125,name="Different fiscal year")
    data=xbrl(125)
    for group in data["facts"]["us-gaap"].values():
        for rows in group["units"].values():
            for row in rows:
                row["end"]="2024-01-02"
    sec=SimpleNamespace(
        company=lambda ticker,_:[{"EXMA":twin,"PAIR":peer,"FAR":far}[ticker],[]],
        facts=lambda cik:xbrl(cik) if cik!=125 else data,
    )
    request=Request(ticker="EXMP",as_of=CUT,peers=["exma","pair","far"])
    facts,_=normalize(xbrl(),CUT,3)
    warnings=[]
    comparison=Pipeline.peers(sec,company,facts,request,warnings)
    assert [x["ticker"] for x in comparison]==["PAIR"]
    assert comparison[0]["end"]==str(END)
    assert comparison[0]["revenue"]==120
    assert "cùng doanh nghiệp" in warnings[0]
    assert "±92" in warnings[1]


def test_market_uses_share_count_public_at_price_date(config):
    request = Request(ticker="EXMP", as_of=CUT, market_reference={
        "close": 20, "date": CUT, "url": "https://example.com/price",
    })
    company = Company(ticker="EXMP", cik=123, name="Example Components")
    shares = Fact(key="shares", value=10, unit="shares", end=END, filed=date(2024,11,1),
                  concept="dei:EntityCommonStockSharesOutstanding", accession="fixture",
                  url="https://example.com/filing", period="instant")
    future = shares.model_copy(update={"end":CUT, "filed":date(2024,11,5), "value":100})
    market = Pipeline(config).market_snapshot(company, [shares, future], request, Budget(10,0,0), [])
    assert market["market_cap"] == 200
    assert market["market_cap_date"] == str(CUT)


def test_debt_current_aggregate_does_not_double_count_short_debt():
    facts, _ = normalize(xbrl(), CUT, 3)
    for key, value in {"debt_current_total":999, "debt_current":999, "debt_noncurrent":7469,
                       "cash":10605}.items():
        facts.append(Fact(key=key, value=value, unit="USD", end=END, filed=CUT,
                          concept=f"us-gaap:{key}", accession="fixture",
                          url="https://example.com/filing", period="instant"))
    values = {r.key: r for r in calculate(facts) if r.end == END}
    assert values["net_debt"].value == -2137
    assert values["reported_debt"].value == 8468
    assert not any("/us-gaap:debt_current/" in ref for ref in values["net_debt"].inputs)
    partial = {r.key: r for r in calculate([f for f in facts if f.key != "debt_current_total"]) if r.end == END}
    assert partial["net_debt"].value is None
    assert partial["reported_debt"].value == 8468
    assert partial["reported_debt"].reason
