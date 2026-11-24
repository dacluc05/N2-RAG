from datetime import date
from finsight import agents
from finsight.schema import Company, Draft, Verified, LeadAssessment, LeadPoint, ContextAssessment, ContextObservation

COMPANY = Company(ticker="EXMP",cik=123,name="Example")
CUT = date(2024,11,3)

def test_lead_receives_unverified_conflicts_and_context_without_upgrading_them():
    claims = [Verified(id="C1",role="risk",claim=Draft(dimension="risk",text="Giả thuyết cần kiểm tra."),
                       status="UNVERIFIED",reason="Thiếu nguồn"),
              Verified(id="C2",role="financial",claim=Draft(dimension="financial",text="Số liệu đang có mâu thuẫn."),
                       status="CONTRADICTED",reason="Không khớp số chuẩn hóa")]
    class Model:
        def ask(self,instruction,payload,schema):
            from finsight.schema import Reviews
            if schema is Reviews: return Reviews(items=[])
            if "requested_topics" in payload: return LeadAssessment(points=[])
            assert {c["status"] for c in payload["verified"]} == {"UNVERIFIED","CONTRADICTED"}
            assert payload["external_context"][0]["id"] == "N1"
            return LeadAssessment(points=[LeadPoint(topic="overall",text="Đánh giá còn bất định vì có số liệu bị phản bác.",
                claim_ids=["C1","C2"],context_ids=["N1"])])
    result = agents.lead(Model(),COMPANY,CUT,claims,[{"id":"N1","verification_status":"UNVERIFIED"}])
    assert len(result) == 6
    assert result[0]["confidence"] == "conflicted"
    assert result[0]["context_ids"] == ["N1"]
    assert all(p["mode"] == "fallback" for p in result[1:])


def test_context_preserves_missing_response_and_invalid_quote_as_unverified():
    documents = [{"id":key,"text":"Original text with enough substance to discuss company outlook.",
                  "group":"news","published":"2024-11-02","source_type":"search_excerpt","title":"Source","url":"https://example.com/"+key}
                 for key in ("a","b")]
    class Model:
        def ask(self,*args):
            return ContextAssessment(observations=[ContextObservation(source_id="a",text="Nhận xét chưa đủ căn cứ để xác nhận.",quote="Invented quote not in source")])
    result = agents.analyze_context(Model(),COMPANY,CUT,documents)
    assert len(result) == 2
    assert result[0]["verification_status"] == "UNVERIFIED"
    assert result[0]["quote"] == ""
    assert result[1]["analysis_status"] == "pending"


def test_link_only_cannot_become_an_assertion():
    source = {"id":"a","text":"","title":"Unverified headline","published":"","group":"social","source_type":"link_only"}
    class Model:
        def ask(self,*args):
            return ContextAssessment(observations=[ContextObservation(source_id="a",text="Sự kiện chắc chắn đã xảy ra và gây tác động lớn.")])
    item = agents.analyze_context(Model(),COMPANY,CUT,[source])[0]
    assert "Sự kiện chắc chắn" not in item["observation"]
    assert item["confidence"] == "insufficient"


def test_context_keeps_more_than_three_sources_per_group(config, pipeline, monkeypatch):
    from pydantic import SecretStr
    from finsight.research import Brave, SearchHit
    from finsight.schema import Request
    from finsight.transport import Budget
    import finsight.pipeline as module
    pipeline.config = config.model_copy(update={"search_provider":"brave","brave_search_api_key":SecretStr("test")})
    def search(self,query,group,method):
        prefix = "https://www.reuters.com/technology/" if group == "news" else "https://www.reddit.com/r/stocks/comments/"
        return [SearchHit(prefix+str(i),group,"Source", "Company outlook discussed in this publicly indexed search excerpt.","2024-11-02") for i in range(8)]
    monkeypatch.setattr(Brave,"search",search)
    def blocked(*args): raise ValueError("Không đọc được trang gốc")
    monkeypatch.setattr(module,"context_document",blocked)
    status, docs = pipeline.collect_context(None,Budget(10,5,0),COMPANY,Request(ticker="EXMP",as_of=CUT))
    assert len(docs) == 16
    assert all(status[group]["queued"] == 8 for group in ("news","social"))
    assert all(source["source_type"] == "search_excerpt" for source in docs)


def test_lead_whole_paragraph_audit_prevents_false_high_confidence():
    from finsight.schema import Reviews, ReviewItem
    claims = [Verified(id="C1",role="risk",claim=Draft(dimension="governance",text="Hội đồng giám sát rủi ro."),status="SUPPORTED",reason="Nguồn hỗ trợ")]
    class Model:
        def ask(self,instruction,payload,schema):
            if schema is Reviews:
                return Reviews(items=[ReviewItem(claim_id="business:0",status="PARTIALLY_SUPPORTED",reason="Nguồn quản trị không chứng minh lợi thế CUDA.")])
            if "requested_topics" in payload: return LeadAssessment(points=[])
            return LeadAssessment(points=[LeadPoint(topic="business",text="CUDA tạo rào cản chuyển đổi lớn cho khách hàng.",claim_ids=["C1"])])
    result = agents.lead(Model(),COMPANY,CUT,claims)
    point = next(p for p in result if p["topic"] == "business")
    assert point["confidence"] == "moderate"
    assert point["verification_status"] == "PARTIALLY_SUPPORTED"
    assert "không chứng minh" in point["basis"]


def test_numeric_aliases_do_not_merge_non_equivalent_concepts():
    from finsight.schema import Numeric
    def metric(key): return Numeric(key=key,value=1,unit="USD",end=CUT).key
    assert metric("net_cash_provided_by_operating_activities") == "ocf"
    assert metric("total_operating_expenses") == "operating_expenses"
    assert metric("cash_and_marketable_debt_securities") != "cash"


def test_embedding_cache_encodes_only_new_content(tmp_path):
    import numpy as np
    from finsight.rag import Hybrid
    from finsight.schema import Evidence
    def chunk(text,index):
        import hashlib
        digest = hashlib.sha256(text.encode()).hexdigest()
        return Evidence(id=str(index),company_cik=123,document_id="doc",title="Test",url="https://example.com",locator="test",published=CUT,text=text,quality="primary",content_hash=digest,kind="10-K",index=index)
    calls = []
    def encode(texts,**kwargs):
        calls.append(list(texts))
        return np.array([[1.,0.,0.] for _ in texts],dtype="float32")
    rows = [chunk("Company growth and products",0),chunk("Company cash flow and debt",1)]
    first = Hybrid(rows,CUT,123,"test-model",encoder=encode,cache_dir=tmp_path)
    assert first.vectors_created == 2
    second = Hybrid(rows,CUT,123,"test-model",encoder=encode,cache_dir=tmp_path)
    assert second.vectors_reused == 2 and second.vectors_created == 0
    third = Hybrid(rows+[chunk("New risk disclosure",2)],CUT,123,"test-model",encoder=encode,cache_dir=tmp_path)
    assert third.vectors_reused == 2 and third.vectors_created == 1
    assert len(calls) == 2 and calls[1] == ["New risk disclosure"]


def test_lead_missing_sentence_review_cannot_certify_paragraph():
    from finsight.schema import Reviews, ReviewItem
    claims = [Verified(id="C1",role="risk",claim=Draft(dimension="governance",text="Hội đồng giám sát rủi ro."),status="SUPPORTED",reason="Nguồn hỗ trợ")]
    class Model:
        def ask(self,instruction,payload,schema):
            if schema is Reviews:
                assert len(payload["items"]) == 2
                assert "reason" not in payload["items"][0]["claims"][0]
                return Reviews(items=[ReviewItem(claim_id="business:0",status="SUPPORTED",reason="Nguồn hỗ trợ câu đầu.")])
            if "requested_topics" in payload: return LeadAssessment(points=[])
            return LeadAssessment(points=[LeadPoint(topic="business",text="Hội đồng giám sát rủi ro. CUDA tạo lợi thế vượt trội.",claim_ids=["C1"])])
    point = next(p for p in agents.lead(Model(),COMPANY,CUT,claims) if p["topic"] == "business")
    assert point["verification_status"] == "UNVERIFIED"
    assert point["confidence"] == "low"
    assert point["sentence_checks"][1]["status"] == "UNVERIFIED"
