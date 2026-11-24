import os
from pathlib import Path
import time

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
import pytest

from conftest import CUT
from finsight.api import create_app
from finsight.config import settings
from finsight.research import Brave, SearchHit
from finsight.schema import Request
from finsight.storage import Base, Repository, mysql_engine
from finsight.transport import ProviderError


def sqlite_repository(path):
    engine = create_engine("sqlite:///"+path.as_posix(),connect_args={"check_same_thread":False})
    @event.listens_for(engine,"connect")
    def enable_foreign_keys(dbapi, _):
        dbapi.execute("PRAGMA foreign_keys = ON")
    Base.metadata.create_all(engine)
    return Repository(engine,60)


@pytest.fixture
def repo(tmp_path):
    return sqlite_repository(tmp_path / "finsight.sqlite")


def wait(client, run_id):
    for _ in range(150):
        response = client.get(f"/api/v1/analysis/{run_id}/progress").json()
        if response["run"]["status"] in {"completed","partial","failed"}:
            return response
        time.sleep(.035)
    pytest.fail("Job chưa kết thúc")


def integration(repo,config,pipeline):
    with TestClient(create_app(config,repo,pipeline)) as client:
        assert client.get("/api/v1/health").status_code==200
        req = {"ticker":"exmp","as_of":str(CUT)}
        job = client.post("/api/v1/analysis",json=req)
        assert job.status_code==202
        run_id = job.json()["id"]
        progress = wait(client,run_id)
        assert progress["run"]["status"]=="partial", progress
        report = client.get(f"/api/v1/reports/{run_id}").json()
        assert report["company"]["cik"]==123
        assert "company" in report["scores"]["covered_dimensions"]
        assert [point["topic"] for point in report["lead_assessment"]] == ["overall","health","business","valuation","conditions","gaps"]
        assert next(p for p in report["lead_assessment"] if p["topic"] == "overall")["mode"] == "fallback"
        assert "Lợi nhuận" in client.get(f"/api/v1/reports/{run_id}/export?format=md").text
        raw = client.get(f"/api/v1/reports/{run_id}/export?format=pdf")
        assert raw.status_code==200 and raw.content.startswith(b"%PDF")
        from io import BytesIO
        from pypdf import PdfReader
        pdf = PdfReader(BytesIO(raw.content))
        assert "Tóm tắt" in "".join(p.extract_text() for p in pdf.pages)
        assert any(page.get("/Annots") for page in pdf.pages)
        assert client.get(f"/api/v1/reports/{run_id}/export").json()["company"]["ticker"]=="EXMP"
        assert client.get(f"/api/v1/analysis/{run_id}/evidence").json()
        assert client.get("/api/v1/companies/123/financials").json()["facts"]
        assert client.get("/api/v1/reports?ticker=EXMP").json()
        matched = client.get("/api/v1/reports", params={"q": "Example Component", "status": "partial"}).json()
        assert [item["id"] for item in matched] == [run_id]
        assert matched[0]["company_name"]
        assert client.get("/api/v1/reports", params={"q": "Example Component", "offset": 1}).json() == []
        assert isinstance(client.get(f"/api/v1/reports/{run_id}/signals").json(), list)
        assert client.get("/api/v1/dashboard").json()["evidence_count"] > 0
        assert client.get("/api/v1/dashboard").json()["reports"] >= 1
        assert client.post(f"/api/v1/reports/{run_id}/feedback",json={"score":5,"note":"Tiếng Việt"}).status_code==201
        assert client.delete(f"/api/v1/reports/{run_id}").status_code==204
        assert client.get(f"/api/v1/reports/{run_id}").status_code==404


def test_full_api_mock(config,pipeline,repo):
    integration(repo,config,pipeline)


def test_sec_cache_survives_runs_and_respects_as_of(pipeline, repo):
    pipeline.repository = repo
    request = Request(ticker="EXMP", as_of=CUT)
    first = pipeline.run(request, lambda *_: None)
    second = pipeline.run(request, lambda *_: None)
    assert first["retrieval"]["sec_fetched"] == second["retrieval"]["sec_reused"] == 1
    assert not second["retrieval"]["sec_fetched"]
    assert second["usage"]["SEC:facts_reused"] == 1
    assert "Tài liệu:document" not in second["usage"]
    assert first["facts"] == second["facts"]
    from datetime import timedelta
    older_cutoff = CUT.replace(day=1) - timedelta(days=1)
    older = pipeline.run(Request(ticker="EXMP", as_of=older_cutoff), lambda *_: None)
    assert not older["retrieval"]["sec_reused"]
    assert not older["facts"]
    assert not older["evidence"]


def test_report_context_filters_to_posts_and_articles(config, pipeline, repo, monkeypatch):
    from pydantic import SecretStr

    cfg = config.model_copy(update={"search_provider": "brave", "brave_search_api_key": SecretStr("test")})
    def search(_, query, group, method):
        assert "EXMP" in query and method == "web"
        return [
            SearchHit("https://www.reuters.com/technology/example", group, "News"),
            SearchHit("https://www.cnbc.com/quotes/EXMP", group, "Quote page"),
            SearchHit("https://www.reddit.com/r/stocks/comments/abc/example", group, "Post"),
            SearchHit("https://www.reddit.com/r/stocks/", group, "Forum"),
            SearchHit("https://reddit.com.example.org/comments/abc/", group, "Lookalike"),
        ]

    monkeypatch.setattr(Brave, "search", search)
    with TestClient(create_app(cfg, repo, pipeline)) as client:
        run_id = client.post("/api/v1/analysis", json={"ticker": "EXMP", "as_of": str(CUT)}).json()["id"]
        wait(client, run_id)
        for group, title in (("news", "News"), ("social", "Post")):
            response = client.get(f"/api/v1/reports/{run_id}/context/{group}")
            assert response.headers["Cache-Control"] == "no-store"
            assert [item["title"] for item in response.json()["results"]] == [title]
        assert "context" not in client.get(f"/api/v1/reports/{run_id}").json()


def test_analysis_collects_both_groups_and_saves_grounded_agent_output(config, pipeline, repo, monkeypatch):
    import httpx
    from pydantic import SecretStr
    from finsight import research
    from finsight.schema import ContextAssessment, ContextObservation

    cfg = config.model_copy(update={"search_provider":"brave", "brave_search_api_key":SecretStr("test"),
                                   "max_search_requests_per_run":4})
    pipeline.config = cfg
    original_client = pipeline.client_factory
    news = "https://www.reuters.com/technology/example"
    social = "https://www.reddit.com/r/stocks/comments/abc/example"
    future = "https://www.reuters.com/technology/future"
    original_resolver = research.socket.getaddrinfo

    def resolve(host, *args, **kwargs):
        if host in {"www.reuters.com", "www.reddit.com"}:
            return [(None, None, None, None, ("8.8.8.8", 443))]
        return original_resolver(host, *args, **kwargs)

    monkeypatch.setattr(research.socket, "getaddrinfo", resolve)
    quote = "Example Components announced a change in its distributor network."

    def client_factory(**kwargs):
        original = original_client(**kwargs)
        def respond(req):
            if req.url.host == "api.search.brave.com":
                query = req.url.params["q"]
                urls = [social] if "site:reddit.com" in query else [] if "inurl:" in query else [news, future]
                return httpx.Response(200, json={"web":{"results":[{"url":url} for url in urls]}})
            if str(req.url) in {news, social, future}:
                stamp = "2024-12-01" if str(req.url) == future else "2024-11-02"
                body = f'<article><p>{quote}</p></article>' if str(req.url) != social else f'<div slot="text-body">{quote}</div>'
                return httpx.Response(200, text=f'<html><meta name="date" content="{stamp}"><body>{body}</body></html>',
                                      headers={"Content-Type":"text/html"})
            return original.send(req)
        return httpx.Client(transport=httpx.MockTransport(respond), **kwargs)

    pipeline.client_factory = client_factory
    original_model = pipeline.model_factory
    def model_factory(*args):
        model = original_model(*args)
        original_ask = model.ask
        def ask(instruction, payload, schema):
            if schema is ContextAssessment:
                assert {source["group"] for source in payload["sources"]} == {"news","social"}
                assert all(source["url"] != future for source in payload["sources"])
                return ContextAssessment(observations=[
                    ContextObservation(source_id=source["id"], text="Nguồn đề cập thay đổi mạng lưới phân phối.",
                                       quote=quote) for source in payload["sources"]
                ])
            return original_ask(instruction, payload, schema)
        model.ask = ask
        return model
    pipeline.model_factory = model_factory

    with TestClient(create_app(cfg, repo, pipeline)) as client:
        run_id = client.post("/api/v1/analysis", json={"ticker":"EXMP", "as_of":str(CUT)}).json()["id"]
        wait(client, run_id)
        report = client.get(f"/api/v1/reports/{run_id}").json()
        assert report["agents"]["external_context"] == {"status":"ready","count":2}
        for group, url in (("news",news),("social",social)):
            assert report["external_context"][group]["observations"][0]["url"] == url
        assert all(source["url"] not in {news,social} for source in report["evidence"])
        assert "Bối cảnh báo chí và mạng xã hội" in client.get(f"/api/v1/reports/{run_id}/export?format=md").text


def test_mysql_unavailable_is_503(config,pipeline):
    bad = config.model_copy(update={"mysql_port":1})
    repo = Repository(mysql_engine(bad),60)
    with TestClient(create_app(config,repo,pipeline)) as c:
        assert c.get("/api/v1/health").status_code==503


def test_dedup_while_active(repo):
    req=Request(ticker="EXMP",as_of=CUT)
    run_id,created=repo.submit(req)
    assert created is True
    assert repo.submit(req)==(run_id,False)
    repo.finish(run_id,None,"failed","Fixture")
    assert repo.submit(req)[0]!=run_id


def test_gemini_unavailable_keeps_sec_evidence(config,pipeline):
    def fail(*args):
        raise ProviderError("Gemini","hết quota")
    pipeline.model_factory=fail
    report=pipeline.run(Request(ticker="EXMP",as_of=CUT),lambda *args:None)
    assert report["status"]=="partial"
    assert any("Gemini" in w for w in report["warnings"])
    assert report["claims"] and all(c["role"]=="computed" for c in report["claims"])
    assert all(p["mode"] == "fallback" for p in report["lead_assessment"])
    assert not report["summary_ids"]
    assert len(report["scores"]["covered_dimensions"])<8


def test_matching_company_by_cik(pipeline):
    from finsight.transport import Budget
    with pipeline.client_factory(follow_redirects=False) as client:
        sec = pipeline.sec(client,Budget(10,0,0))
        assert len(sec.search("Example Component"))==2
        assert sec.company("EXMP",CUT)[0].cik==123
        with pytest.raises(ProviderError):
            sec.company("EXM",CUT)


@pytest.mark.mysql
@pytest.mark.skipif(os.getenv("FINSIGHT_MYSQL_TEST")!="1",reason="Cần MySQL test riêng và migration")
def test_mysql_roundtrip(config,pipeline):
    runtime = settings()
    assert runtime.mysql_database.endswith("_test"),"Chỉ chạy trên database kiểm thử được chỉ định."
    repo=Repository(mysql_engine(runtime),60)
    with repo.engine.connect() as conn:
        assert "8." in conn.scalar(text("SELECT VERSION()"))
    integration(repo,config,pipeline)


def test_dashboard_loads(monkeypatch):
    import httpx
    from streamlit.testing.v1 import AppTest
    def stub(method,url,**kwargs):
        payload = [] if url.endswith("/reports") else {"mysql":"ready","sec_configured":True,
            "brave_configured":False,"gemini_configured":False,"embedding_enabled":False}
        return httpx.Response(200,json=payload,request=httpx.Request(method,url))
    monkeypatch.setattr(httpx,"request",stub)
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "frontend/Home.py").run(timeout=15)
    assert not app.exception
    assert app.title[0].value=="Tổng quan nghiên cứu"


def test_sec_stale_cache_is_used_only_when_refresh_fails(pipeline,repo):
    import hashlib
    from datetime import timedelta
    pipeline.repository = repo
    key = hashlib.sha256(b"stale-fixture").hexdigest()
    repo.sec_cache_write(key,{"cik":123,"facts":{}})
    from finsight.transport import Budget
    warnings = []
    def fail(): raise ProviderError("SEC","timeout")
    payload = pipeline.cached_sec("stale-fixture",fail,warnings,Budget(10,0,0),"facts",max_age=timedelta(seconds=-1))
    assert payload["cik"] == 123
    assert "bản lưu trước" in warnings[0]
    refreshed = pipeline.cached_sec("stale-fixture",lambda:{"cik":123,"new":True},[],Budget(10,0,0),"facts",max_age=timedelta(seconds=-1))
    assert refreshed["new"] is True


def test_repository_saves_pipeline_dates_without_api_encoder(repo,pipeline):
    request = Request(ticker="EXMP",as_of=CUT)
    report = pipeline.run(request,lambda *_:None)
    run_id,created = repo.submit(request)
    assert created
    repo.finish(run_id,report,report["status"],"Validated")
    saved = repo.report(run_id)
    assert isinstance(saved["scores"]["latest_publication"],str)
    assert saved["claims"]


def test_latest_cached_facts_uses_company_and_newest_snapshot(repo):
    repo.sec_cache_write("a"*64,{"cik":123,"facts":{"old":{}}})
    repo.sec_cache_write("b"*64,{"cik":124,"facts":{"wrong":{}}})
    repo.sec_cache_write("c"*64,{"cik":123,"facts":{"new":{}}})
    assert "new" in repo.latest_cached_facts(123)["facts"]
    assert repo.latest_cached_facts(999) is None
