from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from contextlib import asynccontextmanager
from datetime import date
from urllib.parse import quote
from urllib.parse import urlsplit
import hmac
import logging
import re
from typing import Literal

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Response
from fastapi.responses import JSONResponse
from pydantic import Field
from sqlalchemy.exc import SQLAlchemyError

from finsight import __version__
from finsight.config import settings
from finsight.financials import dcf
from finsight.pipeline import Pipeline
from finsight.insights import investment, signals
from finsight.reporting import export
from finsight.schema import Model, Request
from finsight.research import Brave, CONTEXT_SITES, SEC_HOSTS, canonical, check_source, context_hit, context_query
from finsight.provenance import evidence_fact, highlighted_pdf_page, inline_fact_location
from finsight.storage import Repository, mysql_engine
from finsight.transport import Budget, Http, ProviderError

log = logging.getLogger(__name__)


class FeedbackRequest(Model):
    score: int = Field(ge=1,le=5)
    note: str = Field("",max_length=2000)


class DCFRequest(Model):
    fcff: float
    growth: float
    discount: float
    terminal_growth: float
    net_debt: float
    shares: float
    years: int = Field(5,ge=1,le=15)


def create_app(config=None, repository=None, pipeline=None):
    cfg = config or settings()
    repo = repository or Repository(mysql_engine(cfg),cfg.max_analysis_seconds+60)
    runner = pipeline or Pipeline(cfg, repository=repo)

    @asynccontextmanager
    async def lifespan(app):
        with ThreadPoolExecutor(max_workers=1,thread_name_prefix="finsight") as executor:
            app.state.executor = executor
            yield
        repo.engine.dispose()

    def authorize(authorization: str | None = Header(None)):
        expected = cfg.api_token.get_secret_value()
        if expected and not hmac.compare_digest((authorization or "").encode(),("Bearer "+expected).encode()):
            raise HTTPException(401,"Thiếu hoặc sai mã truy cập")

    app = FastAPI(title="FinSight Intelligence V2",version=__version__,lifespan=lifespan,
                  dependencies=[Depends(authorize)])

    @app.exception_handler(SQLAlchemyError)
    async def database_error(_, exc):
        from fastapi.responses import JSONResponse
        log.error("Database request failed: %s",type(exc).__name__)
        return JSONResponse({"detail":"MySQL chưa sẵn sàng. Kiểm tra .env, dịch vụ và migration."},503)

    @app.exception_handler(ProviderError)
    async def provider_error(_, exc):
        from fastapi.responses import JSONResponse
        return JSONResponse({"detail":str(exc)},502)

    def work(run_id, req):
        try:
            report = runner.run(req,lambda state,message:repo.event(run_id,state,message))
            # Persist only JSON primitives, including coverage dates.
            from fastapi.encoders import jsonable_encoder
            repo.finish(run_id,jsonable_encoder(report),report["status"],"Phiên phân tích đã kết thúc.")
        except Exception as exc:
            log.error("Run %s failed (%s)",run_id,type(exc).__name__)
            try:
                repo.finish(run_id,None,"failed",str(exc) if isinstance(exc,ProviderError)
                            else "Có lỗi xử lý. Kiểm tra trạng thái MySQL và cấu hình nguồn.")
            except SQLAlchemyError:
                log.error("Could not record terminal status for run %s",run_id)

    def require_run(run_id):
        obj = repo.get(run_id)
        if obj is None:
            raise HTTPException(404,"Không tìm thấy phiên phân tích")
        return obj

    def require_report(run_id):
        obj = repo.report(run_id)
        if obj is None:
            raise HTTPException(404,"Phiên chưa có báo cáo")
        return obj

    @app.get("/api/v1/health")
    def health():
        repo.health()
        return {"status":"ready","mysql":"ready","version":__version__}

    @app.get("/api/v1/system/status")
    def system():
        repo.health()
        return {"mysql":"ready","sec_configured":bool(cfg.sec_user_agent),
                "brave_configured":bool(cfg.brave_search_api_key.get_secret_value()),
                "gemini_configured":bool(cfg.gemini_model and cfg.gemini_api_key.get_secret_value()),
                "embedding_enabled":cfg.embedding_enabled,
                "market_persistence":cfg.persist_market}

    @app.get("/api/v1/dashboard")
    def dashboard():
        return repo.dashboard()

    @app.get("/api/v1/companies/search")
    def companies(q: str=Query(min_length=1,max_length=100)):
        with httpx.Client() as client:
            return runner.sec(client,Budget(25,0,0)).search(q.strip())

    @app.get("/api/v1/companies/{cik}")
    def company(cik: int):
        item = repo.company(cik)
        if not item:
            raise HTTPException(404,"Chưa có hồ sơ lưu cho CIK này")
        return item

    @app.get("/api/v1/companies/{cik}/financials")
    def financials(cik: int):
        item = repo.financials(cik)
        if not item:
            raise HTTPException(404,"Chưa có dữ liệu tài chính lưu cho CIK này")
        return item

    @app.post("/api/v1/analysis",status_code=202)
    def analyze(req: Request):
        run_id,created = repo.submit(req)
        if created:
            app.state.executor.submit(work,run_id,req)
        return {"id":run_id,"created":created}

    @app.get("/api/v1/analysis/{run_id}")
    def analysis(run_id: str):
        return require_run(run_id)

    @app.get("/api/v1/analysis/{run_id}/progress")
    def progress(run_id: str):
        return {"run":require_run(run_id),"events":repo.events(run_id)}

    @app.get("/api/v1/analysis/{run_id}/claims")
    def claims(run_id: str):
        return require_report(run_id)["claims"]

    @app.get("/api/v1/analysis/{run_id}/evidence")
    def evidence(run_id: str):
        return require_report(run_id)["evidence"]

    @app.get("/api/v1/analysis/{run_id}/evidence/{evidence_id}/location")
    def fact_location(run_id: str, evidence_id: str):
        report = require_report(run_id)
        item = next((e for e in report["evidence"] if e["id"] == evidence_id),None)
        fact = evidence_fact(report,evidence_id)
        if fact is None or (item is not None and item["kind"] != "xbrl"):
            raise HTTPException(404,"Không tìm thấy số liệu XBRL")
        filing = next((entry["url"] for entry in report.get("filings", [])
                       if entry["accession"] == fact.accession), fact.url)
        url = canonical(filing)
        if not url or urlsplit(url).hostname not in SEC_HOSTS or not cfg.sec_user_agent:
            return {"url":url,"located":False}
        try:
            check_source(url,SEC_HOSTS)
            with httpx.Client() as client:
                source,_ = Http(client,Budget(12,0,0),runner.sec_rate,"SEC",7).get(
                    url,"fact_location",headers={"User-Agent":cfg.sec_user_agent},max_bytes=14_000_000)
            location = inline_fact_location(source,fact)
        except ProviderError as exc:
            if exc.category in {"lỗi kết nối hoặc timeout", "hết thời gian"} or exc.category.startswith(
                ("giới hạn tốc độ", "lỗi máy chủ")
            ):
                raise HTTPException(503, "Tạm thời chưa tải được hồ sơ SEC.") from None
            location = None
        except (ValueError, OSError):
            location = None
        if location is None:
            return {"url":url,"located":False}
        target = url + "#" + quote(location.anchor, safe="")
        return {"url":target,"located":True,"source_row":asdict(location)}

    @app.get("/api/v1/analysis/{run_id}/evidence/{evidence_id}/pdf")
    def evidence_pdf(run_id: str, evidence_id: str, claim_id: str | None = Query(None, max_length=100)):
        report = require_report(run_id)
        item = next((entry for entry in report["evidence"] if entry["id"] == evidence_id), None)
        if item is None:
            raise HTTPException(404, "Không tìm thấy nguồn")
        url = canonical(item["url"])
        page = re.match(r"trang\s+(\d+)", item.get("locator") or "", re.I)
        if not url or not page:
            raise HTTPException(422, "Nguồn chưa có vị trí trang PDF")
        quote_text = next((
            ref["quote"] for claim in report["claims"] if claim_id is None or claim["id"] == claim_id
            for ref in claim["claim"]["references"] if ref["evidence_id"] == evidence_id
        ), "")
        if not quote_text:
            quote_text = " ".join(item["text"].split()[1:21])
        try:
            check_source(url, SEC_HOSTS | set(cfg.allowed_source_hosts))
            agent = cfg.sec_user_agent
            if urlsplit(url).hostname in SEC_HOSTS and not agent:
                raise ValueError("Thiếu SEC_USER_AGENT")
            with httpx.Client() as client:
                raw, _ = Http(client, Budget(18, 0, 0), runner.sec_rate, "Nguồn", 8).get(
                    url, "evidence_pdf", headers={"User-Agent": agent or "FinSight Intelligence V2"},
                    max_bytes=14_000_000)
            content = highlighted_pdf_page(raw, int(page[1]), quote_text)
        except (ValueError, OSError, RuntimeError, ProviderError):
            raise HTTPException(422, "Chưa đối chiếu được đoạn trích trong PDF gốc") from None
        return Response(content, media_type="application/pdf",
                        headers={"Content-Disposition": f'inline; filename="source-page-{page[1]}.pdf"'})

    @app.post("/api/v1/analysis/{run_id}/evidence/{evidence_id}/check")
    def source_check(run_id: str, evidence_id: str):
        report = require_report(run_id)
        item = next((e for e in report["evidence"] if e["id"] == evidence_id),None)
        if item is None:
            raise HTTPException(404,"Không tìm thấy bằng chứng")
        url = canonical(item["url"])
        try:
            check_source(url,SEC_HOSTS | set(cfg.allowed_source_hosts))
            if urlsplit(url).hostname in SEC_HOSTS and not cfg.sec_user_agent:
                raise ValueError("Thiếu SEC_USER_AGENT")
            with httpx.Client() as c:
                Http(c,Budget(18,0,0),runner.sec_rate,"Nguồn",8).get(
                    url,"check",headers={"User-Agent":cfg.sec_user_agent or "FinSight Intelligence V2"},
                    max_bytes=14_000_000)
        except (ValueError,OSError,ProviderError):
            return {"reachable":False,"message":"Hiện chưa truy cập được tài liệu nguồn."}
        return {"reachable":True,"message":"URL nguồn đang phản hồi. Bản trích lưu theo thời điểm nghiên cứu."}

    @app.get("/api/v1/reports")
    def history(ticker: str|None=Query(None,max_length=12), after: date|None=None,
                limit: int=Query(50,ge=1,le=200), q: str|None=Query(None,max_length=100),
                status: list[str]|None=Query(None,max_length=12), offset: int=Query(0,ge=0), oldest: bool=False):
        return repo.history(ticker.upper() if ticker else None, after, limit,
                            q=q.strip() if q else None, status=status, offset=offset, oldest=oldest)

    @app.get("/api/v1/reports/{run_id}")
    def get_report(run_id: str):
        return require_report(run_id)

    @app.get("/api/v1/reports/{run_id}/signals")
    def report_signals(run_id: str):
        return signals(require_report(run_id))

    @app.get("/api/v1/reports/{run_id}/investment")
    def report_investment(run_id: str):
        return investment(require_report(run_id))

    @app.get("/api/v1/reports/{run_id}/context/{group}")
    def report_context(run_id: str, group: Literal["news", "social"]):
        report = require_report(run_id)
        if cfg.search_provider != "brave" or not cfg.brave_web_search_enabled or not cfg.brave_search_api_key.get_secret_value():
            raise HTTPException(503, "Cần bật Brave Web Search để tìm nguồn.")
        company = report["company"]
        hits = {}
        unavailable = []
        hosts = CONTEXT_SITES[group] if group == "social" else (None,)
        with httpx.Client() as client:
            brave = Brave(Http(client, Budget(20, 5, 0), runner.brave_rate, "Brave", 5), cfg)
            for host in hosts:
                try:
                    found = brave.search(context_query(company["name"], company["ticker"], group, host), group, "web")
                except ProviderError:
                    if host is None:
                        raise
                    unavailable.append(host)
                    continue
                for hit in found:
                    hostname = urlsplit(hit.url).hostname or ""
                    if context_hit(hit.url, group) and (host is None or hostname == host or hostname.endswith("." + host)):
                        hits.setdefault(hit.url, {"url":hit.url, "title":hit.title})
        if len(unavailable) == len(hosts):
            raise HTTPException(502, "Brave chưa phản hồi cho các nguồn mạng xã hội.")
        return JSONResponse({"results": list(hits.values()), "unavailable": unavailable},
                            headers={"Cache-Control": "no-store"})

    @app.get("/api/v1/reports/{run_id}/export")
    def get_export(run_id: str, format: Literal["json","md","pdf"]="json"):
        report = require_report(run_id)
        try:
            data,mime = export(report,format,cfg.pdf_font_path)
        except ValueError as exc:
            raise HTTPException(422,str(exc)) from exc
        return Response(data,media_type=mime,headers={
            "Content-Disposition":f'attachment; filename="{report["company"]["ticker"]}-V2.{format}"'})

    @app.post("/api/v1/reports/{run_id}/rerun",status_code=202)
    def rerun(run_id: str):
        return analyze(Request.model_validate(require_run(run_id)["request"]))

    @app.delete("/api/v1/reports/{run_id}",status_code=204)
    def delete_report(run_id: str):
        require_run(run_id)
        if not repo.delete(run_id):
            raise HTTPException(409,"Phiên vẫn đang chạy")
        return Response(status_code=204)

    @app.post("/api/v1/reports/{run_id}/feedback",status_code=201)
    def feedback(run_id: str, feedback: FeedbackRequest):
        if not repo.feedback(run_id,feedback.score,feedback.note):
            raise HTTPException(404,"Phiên chưa có báo cáo")
        return {"status":"saved"}

    @app.post("/api/v1/valuation/dcf")
    def valuation(inputs: DCFRequest):
        try:
            return dcf(**inputs.model_dump())
        except ValueError as exc:
            raise HTTPException(422,str(exc)) from exc

    return app


app = create_app()
