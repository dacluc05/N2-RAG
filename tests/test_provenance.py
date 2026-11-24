from datetime import date

from finsight.provenance import evidence_link, highlighted_pdf_page, inline_fact_anchor, inline_fact_location, inline_fact_text_fragment, marked_excerpt
from finsight.insights import signals
from finsight.schema import Draft, Evidence, Fact, Reference, Review
from finsight.verification import reported_percentage_matches, verify


def test_fragment_encoding_and_pdf_fallback():
    link,kind = evidence_link("https://example.org/report.html#old","Cost fell year-over-year, before taxes.")
    assert kind=="text"
    assert link.endswith("#:~:text=Cost%20fell%20year%2Dover%2Dyear%2C%20before%20taxes.")
    assert evidence_link("https://example.org/report.pdf","Any quoted paragraph",
                         locator="trang 12 · đoạn 2")==("https://example.org/report.pdf#page=12","page")


def test_marked_excerpt_escapes_original_markup_and_handles_line_breaks():
    assert marked_excerpt("<script>Revenue\nrose</script>","Revenue rose") == (
        "&lt;script&gt;<mark>Revenue\nrose</mark>&lt;/script&gt;")
    assert "<mark>" not in marked_excerpt("Different text","Not present")


def test_inline_fact_matches_consolidated_period_unit_and_value():
    def context(id, end, dimension=""):
        return f"""<xbrli:context id="{id}"><xbrli:entity>{dimension}</xbrli:entity>
        <xbrli:period><xbrli:startDate>2025-01-01</xbrli:startDate>
        <xbrli:endDate>{end}</xbrli:endDate></xbrli:period></xbrli:context>"""

    def entry(id,ctx,unit,amount):
        return f"""<ix:nonfraction id="{id}" name="us-gaap:Revenues" scale="6"
             contextRef="{ctx}" unitRef="{unit}">{amount}</ix:nonfraction>"""

    raw = ("<html>"+context("wrong","2024-12-31")+context("correct","2025-12-31")
           +context("segment","2025-12-31","<xbrli:segment/>")
           +'<xbrli:unit id="USD"><xbrli:measure>iso4217:USD</xbrli:measure></xbrli:unit>'
           +entry("old","wrong","USD","1,200")+entry("segment-fact","segment","USD","1,200")
           +entry("not-equal","correct","USD","1,201")+entry("no-unit","correct","EUR","1,200")
           +entry("narrative","correct","USD","1,200")
           +"<table><tr><td>Total revenue</td><td>"+entry("exact","correct","USD","1,200")
           +"</td><td>1,050</td></tr></table></html>").encode()
    fact = Fact(key="revenue",value=1_200_000_000,unit="USD",start=date(2025,1,1),
                end=date(2025,12,31),filed=date(2026,1,20),period="FY",
                concept="us-gaap:Revenues",accession="fixture",url="https://example.org")
    assert inline_fact_anchor(raw,fact)=="exact"
    location = inline_fact_location(raw, fact)
    assert location is not None
    assert location.cells == ["Total revenue", "1,200", "1,050"]
    assert location.selected_cell == 1
    assert location.rendered == "1,200"


def test_quoted_rounding_is_accepted_without_accepting_wrong_numbers():
    assert reported_percentage_matches("Tăng 65%.",["Growth was 65%."],65,65.4735)
    assert reported_percentage_matches("Tăng 65,5%.",["Growth was 65.5%."],65.5,65.4735)
    assert not reported_percentage_matches("Tăng 65%.",["Growth was 65%."],65,65.6)
    assert not reported_percentage_matches("Tăng 65%.",["Growth was 65.47%."],65,65.4735)


def test_filing_date_cannot_be_verified_as_period_end():
    source = Evidence(
        id="q2", company_cik=1, document_id="doc", title="10-Q", url="https://example.org",
        locator="Risk Factors", published=date(2026, 8, 26), report_end=date(2026, 7, 26),
        text="Export controls can affect demand.", quality="primary", kind="10-Q", content_hash="fixture",
    )
    draft = Draft(
        dimension="risk", text="Quý kết thúc ngày 26/08/2026 ghi nhận rủi ro kiểm soát xuất khẩu.",
        references=[Reference(evidence_id=source.id, quote=source.text)],
    )
    kwargs = dict(cik=1, as_of=date(2026, 11, 13), provided=[source], numbers=[],
                  review=lambda *_: Review(status="SUPPORTED", reason="Khớp nội dung."))
    assert verify(draft, "C1", "risk", **kwargs).reason_code == "FILING_DATE_AS_PERIOD"
    corrected = draft.model_copy(update={"text": draft.text.replace("26/08/2026", "26/07/2026")})
    assert verify(corrected, "C1", "risk", **kwargs).status == "SUPPORTED"


def test_quarter_signal_compares_same_quarter_and_ignores_ytd():
    def f(key,end,period,value):
        return {"key":key,"end":end,"period":period,"value":value,"unit":"USD",
                "filed":"2026-08-26","url":"https://example.org"}
    report={"facts":[f("revenue","2026-07-26","Q",96e9),f("revenue","2026-07-26","YTD",177e9),
                     f("revenue","2025-07-27","Q",48e9),f("gross_profit","2026-07-26","Q",72e9),
                     f("gross_profit","2025-07-27","Q",36e9)]}
    result=signals(report)
    assert len(result)==1
    assert "96,00 tỷ USD" in result[0]["text"]
    assert "100,0%" in result[0]["text"]
    assert result[0]["prior_end"]=="2025-07-27"


def test_highlighted_pdf_keeps_cited_original_page():
    import pymupdf

    phrase = "Operating cash flow was 145 million."
    with pymupdf.open() as source:
        source.new_page().insert_text((50, 50), "Cover page")
        source.new_page().insert_text((50, 50), phrase)
        raw = source.tobytes()
    with pymupdf.open(stream=highlighted_pdf_page(raw, 2, phrase), filetype="pdf") as result:
        assert result.page_count == 1
        page = result[0]
        assert phrase in page.get_text()
        assert page.first_annot.type[1] == "Highlight"


def test_text_fragment_locates_repeated_value_in_original_document():
    from bs4 import BeautifulSoup

    source = """<div hidden>132,175</div><p id="first">132,175</p>
    <h2>Consolidated statement of cash flows</h2><p id="later">132,175</p>"""
    first = BeautifulSoup(source, "html.parser")
    assert inline_fact_text_fragment(first, first.find(id="first"), "132,175") == "132%2C175"
    later = BeautifulSoup(source, "html.parser")
    assert inline_fact_text_fragment(later, later.find(id="later"), "132,175") == (
        "Consolidated%20statement%20of%20cash%20flows,132%2C175"
    )

    ambiguous = BeautifulSoup("<p>132,175</p><p id='target'>132,175</p>", "html.parser")
    assert inline_fact_text_fragment(ambiguous, ambiguous.find(id="target"), "132,175") is None
