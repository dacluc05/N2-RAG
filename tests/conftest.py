from datetime import date
import hashlib

import httpx
import pytest

from finsight.config import Settings
from finsight.pipeline import Pipeline
from finsight.schema import Draft, Drafts, Evidence, LeadAssessment, LeadPoint, Reference, Review
from finsight.transport import ProviderError

CUT = date(2024,11,4)
END = date(2024,9,28)
ACC = "0000000123-24-000001"
URL = "https://www.sec.gov/Archives/edgar/data/123/000000012324000001/report.htm"
QUOTE = "The company sells industrial components through a distributor network."
COUNTER = "The company exited all retail storefronts before the end of the year."


def xbrl(cik=123):
    def row(value, start="2023-10-01", end="2024-09-28", **kwargs):
        return {"val":value,"start":start,"end":end,"filed":"2024-11-01","form":"10-K",
                "accn":ACC,"fy":2024,"fp":"FY",**kwargs}

    previous = row(100,"2022-09-25","2023-09-30")
    future = row(125) | {"filed":"2024-12-05","form":"10-K/A","accn":"0000000123-24-000002"}
    quarter = row(33,"2024-06-30")
    ytd = row(83,"2023-12-30")
    return {"cik":cik,"facts":{"us-gaap":{
        "Revenues":{"units":{"USD":[previous,row(120),future,quarter,ytd],"EUR":[row(110)]}},
        "NetIncomeLoss":{"units":{"USD":[row(12)]}},
        "GrossProfit":{"units":{"USD":[row(36)]}},
        "NetCashProvidedByUsedInOperatingActivities":{"units":{"USD":[row(25)]}},
        "PaymentsToAcquirePropertyPlantAndEquipment":{"units":{"USD":[row(5)]}},
        "AssetsCurrent":{"units":{"USD":[row(80,None)]}},
        "LiabilitiesCurrent":{"units":{"USD":[row(40,None)]}},
    }}}


def evidence(identifier="D:0",text=QUOTE,*,published=date(2024,11,1),cik=123,persist=True):
    return Evidence(id=identifier,document_id="D",company_cik=cik,title="Example filing",
                    url=URL,locator="Item 1 · đoạn 1",published=published,text=text,
                    quality="primary",content_hash=hashlib.sha256(text.encode()).hexdigest(),
                    kind="10-K",persist=persist)


class MockModel:
    def __init__(self, config, budget):
        self.budget = budget

    def ask(self, instruction, payload, model):
        self.budget.charge("Gemini","generate")
        if model is Drafts and instruction.startswith("Vai trò Mô hình"):
            source = next((e for e in payload["sources"] if QUOTE in e["text"]),None)
            if source:
                return Drafts(claims=[Draft(dimension="company",text="Công ty bán linh kiện công nghiệp qua nhà phân phối.",
                                     references=[Reference(evidence_id=source["id"],quote=QUOTE)])])
        if model is Drafts:
            return Drafts(claims=[])
        from finsight.schema import Reviews, ReviewItem
        if model is Reviews:
            return Reviews(items=[ReviewItem(claim_id=item["claim_id"],status="SUPPORTED",reason="Trích đoạn hỗ trợ nhận định.") for item in payload["items"]])
        if model is Review:
            return Review(status="SUPPORTED",reason="Trích đoạn mô tả hoạt động phân phối linh kiện.")
        if model is LeadAssessment and "requested_topics" in payload:
            return LeadAssessment(points=[])
        if model is LeadAssessment:
            ids = [c["id"] for c in payload["verified"] if c["dimension"] == "company"]
            financial = next(c["id"] for c in payload["verified"] if c["dimension"] == "financial")
            return LeadAssessment(points=[
                LeadPoint(topic="health", text="Doanh nghiệp có mô hình phân phối qua đối tác.", claim_ids=[*ids, financial]),
                LeadPoint(topic="valuation", text="Định giá thiếu nguồn đối chiếu.", claim_ids=ids),
            ])

    def close(self):
        return None


@pytest.fixture
def config():
    return Settings(_env_file=None,sec_user_agent="Test Fixture tests@example.invalid",
                    embedding_enabled=False,market_enabled=False,search_provider="off",
                    max_analysis_seconds=30,gemini_requests_per_minute=60000)


@pytest.fixture
def pipeline(config, monkeypatch):
    import finsight.research
    resolver = finsight.research.socket.getaddrinfo
    def resolve(host,*args,**kwargs):
        if host == "www.sec.gov":
            return [(None,None,None,None,("8.8.8.8",443))]
        return resolver(host,*args,**kwargs)
    monkeypatch.setattr(finsight.research.socket,"getaddrinfo",resolve)

    def respond(req):
        if req.url.path.endswith("company_tickers_exchange.json"):
            return httpx.Response(200,json={"fields":["cik","name","ticker","exchange"],"data":[
                [123,"Example Components","EXMP","NYSE"],[124,"Example Component Holdings","EXMH","Nasdaq"]]})
        if req.url.path.endswith("/submissions/CIK0000000123.json"):
            return httpx.Response(200,json={"sic":"3590","sicDescription":"Industrial components","filings":{"recent":{
                "form":["10-K"],"filingDate":["2024-11-01"],"reportDate":["2024-09-28"],
                "accessionNumber":[ACC],"primaryDocument":["report.htm"]}}})
        if req.url.path.endswith("/companyfacts/CIK0000000123.json"):
            return httpx.Response(200,json=xbrl())
        if str(req.url)==URL:
            html = "<html><title>Mock Form 10-K</title><body><h2>Item 1. Business</h2>" + QUOTE + "</body></html>"
            return httpx.Response(200,text=html,headers={"Content-Type":"text/html"})
        return httpx.Response(404)

    transport = httpx.MockTransport(respond)
    return Pipeline(config,client_factory=lambda **kw:httpx.Client(transport=transport,**kw),model_factory=MockModel)
