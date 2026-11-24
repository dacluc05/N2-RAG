from datetime import date

import httpx
import numpy as np
import pytest

from conftest import CUT, END, QUOTE, COUNTER, evidence, xbrl
from finsight.financials import normalize, calculate, calculate_quarterly, dcf
from finsight.rag import Hybrid
from finsight.research import Brave, check_source, canonical, extract, paragraph_chunks, plans
from finsight.schema import Draft, Fact, Numeric, Reference, Review
from finsight.transport import Budget, Http, ProviderError, Rate
from finsight.verification import verify


def ratio(rows,key,end=END):
    return next(x for x in rows if x.key==key and x.end==end)


def test_financial_formulas():
    facts,changes = normalize(xbrl(),CUT,4)
    values = calculate(facts)
    assert ratio(values,"revenue_growth").value == pytest.approx(20)
    assert ratio(values,"gross_margin").value == pytest.approx(30)
    assert ratio(values,"fcf").value == 20
    assert ratio(values,"current_ratio").value == 2
    assert ratio(values,"net_debt").value is None
    assert ratio(values,"roe").value is None
    assert changes == []


def test_period_and_currency():
    facts,_ = normalize(xbrl(),CUT,3)
    revenue = { (f.period,f.unit,f.end):f.value for f in facts if f.key=="revenue"}
    assert revenue[("FY","USD",END)]==120
    assert revenue[("Q","USD",END)]==33
    assert revenue[("YTD","USD",END)]==83
    assert revenue[("FY","EUR",END)]==110


def test_restated_only_after_publication():
    old, _ = normalize(xbrl(),CUT,3)
    new, changes = normalize(xbrl(),date(2024,12,7),3)
    assert ratio(calculate(old),"revenue_growth").value == pytest.approx(20)
    assert ratio(calculate(new),"revenue_growth").value == pytest.approx(25)
    assert changes[0]["resolved"]
    assert changes[0]["prior"]["value"] == 120


def test_bank_and_valuation_rules():
    facts,_ = normalize(xbrl(),CUT,3)
    assert ratio(calculate(facts,"6021"),"current_ratio").value is None
    assert ratio(calculate(facts,"3590",{"market_cap":120,"currency":"USD","url":"https://example.com"}),"pe").value == 10
    assert ratio(calculate(facts,"3590",{"market_cap":120,"currency":"EUR","url":"https://example.com"}),"pe").value is None


def test_dcf_and_sensitivity():
    result=dcf(100,0,.1,0,100,10)
    assert result["base"]["per_share"] == pytest.approx(90)
    assert len(result["sensitivity"])==9
    with pytest.raises(ValueError):
        dcf(100,0,.1,.1,0,10)


def check(draft, provided, numbers=(), **kwargs):
    return verify(draft,"C1","financial",cik=123,as_of=CUT,provided=provided,numbers=list(numbers),**kwargs)


def test_numeric_contradiction():
    facts,_ = normalize(xbrl(),CUT,3)
    draft = Draft(dimension="growth",text="Doanh thu tăng 40%.",references=[Reference(evidence_id="D:0",quote=QUOTE)],
                  numeric=Numeric(key="revenue_growth",end=END,unit="%",value=40))
    assert check(draft,[evidence()],calculate(facts)).status=="CONTRADICTED"


@pytest.mark.parametrize("source",[
    evidence(cik=42),evidence(published=date(2025,1,1)),evidence(published=None),
    evidence(persist=False),evidence(text=COUNTER),evidence(published=date(2020,1,1))
])
def test_bad_provenance_and_recency(source):
    claim = Draft(dimension="company",text="Hiện nay công ty bán linh kiện.",references=[Reference(evidence_id="D:0",quote=QUOTE)])
    assert check(claim,[source]).status=="UNVERIFIED"


def test_url_and_literal_quote_do_not_prove_relevance():
    claim = Draft(dimension="company",text="Công ty dẫn đầu toàn ngành.",references=[Reference(evidence_id="D:0",quote=QUOTE)])
    def review(*args):
        return Review(status="UNVERIFIED",reason="Đoạn trích không nói tới thị phần.")
    assert check(claim,[evidence()],review=review).status=="UNVERIFIED"


def test_counter_evidence_is_reachable():
    claim = Draft(dimension="company",text="Công ty mở chuỗi bán lẻ.",references=[Reference(evidence_id="D:0",quote=QUOTE)])
    def review(_draft,_excerpts,counters):
        assert counters[0].text == COUNTER
        return Review(status="CONTRADICTED",reason="Hồ sơ ghi đã rút khỏi bán lẻ.",counter_ids=["D:1"])
    result = check(claim,[evidence()],review=review,counters=[evidence("D:1",COUNTER)])
    assert result.counter_ids==["D:1"]
    assert result.status=="CONTRADICTED"


def test_real_faiss_with_controlled_vectors_and_temporal_rag():
    a = evidence()
    b = evidence("D:1",COUNTER)
    future = evidence("D:2",QUOTE,published=date(2025,1,1))
    def encode(texts,normalize_embeddings):
        return np.array([[1,0] if "component" in x.lower() else [0,1] for x in texts],dtype=np.float32)
    hybrid = Hybrid([a,b,future],CUT,123,"test",encoder=encode)
    assert hybrid.warning==""
    assert [x.id for x in hybrid.retrieve("components",2)] == ["D:0","D:1"]
    assert hybrid.retrieve("components",2,since=date(2024,11,4)) == []


def test_brave_context_and_web_never_return_snippets(config):
    config = config.model_copy(update={"brave_search_api_key":__import__("pydantic").SecretStr("test-secret")})
    def respond(req):
        assert req.headers["X-Subscription-Token"]=="test-secret"
        if "/context" in req.url.path:
            assert req.url.params["context_threshold_mode"]=="strict"
            return httpx.Response(200,json={"grounding":{"generic":[{"url":"https://example.com/a#frag","snippets":["private"]}]}})
        return httpx.Response(200,json={"web":{"results":[{"url":"https://example.com/a?utm_source=test","description":"private"}]}})
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        brave = Brave(Http(client,Budget(10,2,0),Rate(10_000),"Brave",1),config)
        a=brave.search("Example", "counter","context")[0]
        b=brave.search("Example", "counter","web")[0]
        assert a==b
        assert a.__dict__=={"url":"https://example.com/a","tier":"counter","title":"", "excerpt":"", "published":""}


def test_brave_quota_and_retry_budget(config):
    config = config.model_copy(update={"brave_search_api_key":__import__("pydantic").SecretStr("test-secret")})
    budget = Budget(10,1,0)
    with httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(429))) as c:
        with pytest.raises(ProviderError,match="hết ngân sách"):
            Brave(Http(c,budget,Rate(10_000),"Brave",1),config).search("Example","official","web")
    assert budget.counts["Brave:web"] == 1


def test_source_validation_and_inaccessible_document(monkeypatch):
    assert not canonical("https://example.com:8443/x")
    assert not canonical("https://sec.gov@10.0.0.1/")
    with pytest.raises(ValueError):
        check_source("https://localhost",{"sec.gov"})
    import finsight.research
    monkeypatch.setattr(finsight.research.socket,"getaddrinfo",
                        lambda *a,**kw:[(None,None,None,None,("192.168.1.4",443))])
    with pytest.raises(ValueError):
        check_source("https://example.com",{"example.com"})
    with httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(404))) as c:
        with pytest.raises(ProviderError,match="404"):
            Http(c,Budget(2,0,0),Rate(10_000),"Tài liệu",1).get("https://example.com/file","document")


def test_pdf_keeps_page_and_does_not_infer_missing_cells():
    import pymupdf
    with pymupdf.open() as doc:
        page=doc.new_page()
        page.insert_text((30,40),"Unaudited financial table (USD millions). Revenue column 120; missing cells are blank.")
        doc.new_page()
        _,published,parts=extract(doc.tobytes(),"application/pdf")
    assert published is None and len(parts)==1
    assert parts[0][0]=="trang 1"
    assert "USD millions" in parts[0][1]


def test_tier_configuration_and_bounded_plans():
    assert len(list(plans("Example","EXMP","standard",[2]*6)))==6
    assert len(list(plans("Example","EXMP","deep",[2]*6)))==12

def test_nvda_quarter_comparison_requires_both_periods_and_valid_source():
    current, prior = date(2026, 7, 26), date(2025, 7, 27)
    filed = date(2026, 8, 26)
    as_of = date(2026, 11, 12)
    facts = []
    for start, end, rev, gross in [
        (date(2026, 4, 27), current, 96221, 72142),
        (date(2025, 4, 28), prior, 46743, 33853),
    ]:
        for key, value in (("revenue", rev), ("gross_profit", gross)):
            facts.append(Fact(key=key, value=value, unit="USD", start=start, end=end,
                              filed=filed, period="Q", concept=key, accession="fixture", url="https://example.org"))
    facts.append(facts[0].model_copy(update={"period": "YTD", "value": 177837}))
    ratios = calculate_quarterly(facts)
    margin = ratio(ratios, "gross_margin", current)
    assert margin.period == "Q"
    assert margin.value == pytest.approx(100 * 72142 / 96221)
    assert ratio(ratios, "revenue_growth", current).value == pytest.approx(100 * (96221 / 46743 - 1))
    assert not any(row.key == "gross_margin" and row.end == current for row in calculate_quarterly(
        [*facts, facts[0].model_copy(update={"value": 96000})]
    ))
    quote = "Gross margin | 75.0 | % | 72.4 | %"
    source = evidence(text=quote, published=filed)
    draft = Draft(dimension="financial", text="Biên lợi nhuận gộp 75,0% so với 72,4% cùng kỳ.",
                  numeric=Numeric(key="gross_margin", end=current, unit="%", value=75, period="Q"),
                  comparisons=[Numeric(key="gross_margin", end=prior, unit="%", value=72.4, period="Q")],
                  references=[Reference(evidence_id=source.id, quote=quote)])

    def assess(item, values=ratios, review=None):
        return verify(item, "C1", "financial", cik=123, as_of=as_of, provided=[source],
                      numbers=values, review=review)

    review = lambda *_: Review(status="SUPPORTED", reason="Khớp hai kỳ trong hồ sơ.")
    assert assess(draft, review=review).status == "SUPPORTED"
    assert assess(draft).reason_code == "REVIEW_PENDING"
    assert assess(draft.model_copy(update={"comparisons": []})).reason_code == "INCOMPLETE_COMPARISON"
    assert assess(draft.model_copy(update={"references": []})).reason_code == "MISSING_SOURCE"
    assert assess(draft, [margin]).reason_code == "MISSING_NUMERIC"
    wrong = draft.model_copy(update={
        "text": "Biên lợi nhuận gộp 75,0% so với 72,0% cùng kỳ.",
        "comparisons": [draft.comparisons[0].model_copy(update={"value": 72})],
    })
    assert assess(wrong, review=review).status == "CONTRADICTED"
    annual = margin.model_copy(update={"period": "FY"})
    unspecified = draft.model_copy(update={"numeric": draft.numeric.model_copy(update={"period": None})})
    assert assess(unspecified, [*ratios, annual]).reason_code == "AMBIGUOUS_NUMERIC"
    assert assess(draft, [*ratios, annual], review).status == "SUPPORTED"
    revenue = draft.model_copy(update={
        "text": "Doanh thu 96.221 triệu USD.",
        "numeric": Numeric(key="revenue", end=current, unit="USD", value=96221, period="Q"),
        "comparisons": [],
    })
    absolute = facts[0].model_copy(update={"value": 96_221_000_000})
    assert assess(revenue, [absolute]).reason_code == "NUMERIC_SCALE"
def test_recent_leadership_disclosures_are_prioritized():
    from datetime import date
    from finsight.agents import leadership_updates
    from conftest import evidence

    cutoff = date(2026, 11, 13)
    filing = evidence(text="Item 5.02. The Board accepted the resignation of its Chief Executive Officer.",
                      published=date(2026, 11, 12)).model_copy(update={"kind":"8-K"})
    old = filing.model_copy(update={"published":date(2026, 8, 1)})
    future = filing.model_copy(update={"published":date(2026, 11, 14)})
    assert leadership_updates([old, future, filing], cutoff) == [filing]



def test_search_excerpt_requires_date_cutoff_and_explicit_provenance():
    from finsight.research import SearchHit, context_excerpt
    from datetime import date
    url = "https://www.reddit.com/r/stocks/comments/abc/company"
    text = "Community members discuss the company's outlook and competitive position."
    assert context_excerpt(SearchHit(url,"social","Post",text,""),"social",date(2024,11,3)) is None
    assert context_excerpt(SearchHit(url,"social","Post",text,"2024-11-04"),"social",date(2024,11,3)) is None
    result = context_excerpt(SearchHit(url,"social","Post",text,"2024-11-02"),"social",date(2024,11,3))
    assert result["source_type"] == "search_excerpt"
    assert result["text"] == text


@pytest.mark.parametrize("text,wrong_text,key,period,table", [
    (
        "Ngày 28/09/2024, tiền mặt, tương đương tiền và chứng khoán nợ đạt 56.586 triệu USD.",
        "Ngày 28/09/2024, tiền mặt, tương đương tiền và chứng khoán nợ đạt 22.443 triệu USD.",
        "cash", "instant",
        "| Sep 28, 2024 | Jan 28, 2024\n| (In millions)\n"
        "Cash and cash equivalents | $ | 22,443 | $ | 10,605\n"
        "Cash, cash equivalents, and marketable debt securities | $ | 56,586 | $ | 49,670",
    ),
    (
        "Năm kết thúc 28/09/2024, doanh thu mảng Compute & Networking đạt 193.479 triệu USD "
        "và mảng Graphics đạt 22.459 triệu USD.",
        "Năm kết thúc 28/09/2024, doanh thu mảng Compute & Networking đạt 22.459 triệu USD "
        "và mảng Graphics đạt 193.479 triệu USD.",
        "revenue", "FY",
        "| Compute & Networking | Graphics | Total\n| (In millions)\n"
        "Year Ended Sep 28, 2024\nRevenue | $ | 193,479 | $ | 22,459 | $ | 215,938",
    ),
])
def test_scoped_sec_table_verification(text, wrong_text, key, period, table):
    end = date(2024, 9, 28)
    source = evidence(text=table).model_copy(update={"report_end": end, "kind": "10-K"})
    draft = Draft(
        dimension="financial", text=text,
        numeric=Numeric(key=key, value=0, unit="USD", end=end, period=period),
        references=[Reference(evidence_id=source.id, quote=table.splitlines()[-1])],
    )
    assert check(draft, [source]).status == "SUPPORTED"
    assert check(draft.model_copy(update={"text": wrong_text}), [source]).status == "CONTRADICTED"
    if key == "revenue":
        segment_first = draft.model_copy(update={
            "text": "Năm kết thúc 28/09/2024, mảng Compute & Networking đạt doanh thu "
                    "193.479 triệu USD và mảng Graphics đạt doanh thu 22.459 triệu USD."
        })
        assert check(segment_first, [source]).status == "SUPPORTED"
        without_headers = source.model_copy(update={"text": table.splitlines()[-1]})
        result = check(segment_first, [without_headers])
        assert result.status == "UNVERIFIED" and result.reason_code == "NUMERIC_SCOPE"
    written_date = draft.model_copy(update={"text": text.replace("28/09/2024", "28 tháng 9 năm 2024")})
    assert check(written_date, [source]).status == "SUPPORTED"
    invalid_date = draft.model_copy(update={"text": text.replace("28/09/2024", "31 tháng 9 năm 2024")})
    assert check(invalid_date, [source]).status == "UNVERIFIED"
    wrong_date = draft.model_copy(update={"text": text.replace("28/09/2024", "27/09/2024")})
    assert check(wrong_date, [source]).status == "UNVERIFIED"
    wrong_unit = source.model_copy(update={"text": table.replace("(In millions)", "(In thousands)")})
    assert check(draft, [wrong_unit]).status == "UNVERIFIED"


def test_cash_with_marketable_securities_in_filing_prose():
    end = date(2024, 9, 28)
    quote = ("balances of cash, cash equivalents and marketable securities, "
             "which totaled $136.9 billion as of September 28, 2024")
    source = evidence(text=quote).model_copy(update={"report_end": end, "kind": "10-K"})
    draft = Draft(
        dimension="financial",
        text="Tại ngày 28/09/2024, tiền, tương đương tiền và chứng khoán thị trường đạt 136.9 tỷ USD.",
        numeric=Numeric(key="cash", value=136900000000, unit="USD", end=end, period="instant"),
        references=[Reference(evidence_id=source.id, quote=quote)],
    )
    assert check(draft, [source]).status == "SUPPORTED"
    for before, after in [("136.9", "136,9"), ("136.9", "139.6"), ("136.9", "136,91"), ("28/09", "27/09")]:
        changed = draft.model_copy(update={"text": draft.text.replace(before, after)})
        assert check(changed, [source]).status == ("SUPPORTED" if after == "136,9" else "UNVERIFIED")


def test_overlap_starts_at_full_word_and_preserves_citable_offset():
    prefix = "alpha " * 10
    quote = "principal competitive factors in this market"
    text = prefix + quote + " " + "hardware " * 20
    chunks = list(paragraph_chunks(text, 90, 29))
    assert any(chunk.startswith(quote) for _, chunk in chunks)
    assert all(text[offset:offset + len(chunk)] == chunk for offset, chunk in chunks)


def test_chunker_advances_through_unbroken_text_without_losing_characters():
    text = "x" * 53
    chunks = list(paragraph_chunks(text, 20, 18))
    assert "".join(chunk for _, chunk in chunks) == text
