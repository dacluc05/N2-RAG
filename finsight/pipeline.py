from datetime import date, timedelta
from pathlib import Path
import hashlib
from time import perf_counter
from urllib.parse import urlsplit

import httpx

from finsight import __version__, agents
from finsight.financials import VALUATION, calculate, calculate_quarterly, fact_id, normalize
from finsight.insights import money, percent, vi_number
from finsight.market import yahoo_market
from finsight.rag import Hybrid
from finsight.research import Brave, CONTEXT_SITES, Ingest, SEC_HOSTS, context_document, context_excerpt, context_hit, context_host, context_query, ddgs_search, plans
from finsight.schema import Draft, Evidence, Numeric, Reference, Review, now
from sqlalchemy.exc import SQLAlchemyError
from finsight.sec import SEC
from finsight.transport import Budget, Http, ProviderError, Rate
from finsight.verification import coverage, flat, verify

SEMICONDUCTOR_PEERS = ("AMD", "AVGO", "NVDA")

def estimated_cost(usage, cfg):
    rate_cards = {
        "Brave:web":(cfg.brave_web_usd_per_1000,1000),
        "Brave:context":(cfg.brave_context_usd_per_1000,1000),
        "gemini_input_tokens":(cfg.gemini_input_usd_per_million,1_000_000),
        "gemini_output_tokens":(cfg.gemini_output_usd_per_million,1_000_000),
    }
    active = [(usage[key],price,scale) for key,(price,scale) in rate_cards.items() if usage.get(key)]
    if any(price is None for _,price,_ in active) or usage.get("model",0) and not usage.get("gemini_input_tokens"):
        return None
    return round(sum(n*price/scale for n,price,scale in active),6)


class Pipeline:
    def __init__(self, config, *, client_factory=httpx.Client, model_factory=agents.Gemini,
                 market_factory=yahoo_market, repository=None):
        self.config = config
        self.client_factory, self.model_factory, self.market_factory = client_factory, model_factory, market_factory
        self.repository = repository
        self.sec_rate = Rate(5)
        self.brave_rate = Rate(config.brave_requests_per_second)

    def sec(self, client, budget, warnings=None):
        loader = None
        if warnings is not None:
            def loader(load):
                return self.cached_sec("tickers:v1", load, warnings, budget, "directory", max_age=timedelta(days=1))
        return SEC(Http(client,budget,self.sec_rate,"SEC",self.config.sec_timeout_seconds),
                   self.config.sec_user_agent, loader)

    def cached_sec(self, identity, loader, warnings, budget, kind, *, max_age=None):
        key = hashlib.sha256(identity.encode()).hexdigest()
        if self.repository is not None:
            try:
                cached = self.repository.sec_cache_read(key, max_age)
                if cached is not None:
                    budget.counts[f"SEC:{kind}_reused"] += 1
                    return cached
            except SQLAlchemyError:
                warnings.append("Kho SEC chưa đọc được. Phiên tiếp tục tải từ SEC.")
        try:
            payload = loader()
        except (ProviderError, ValueError, KeyError, OSError):
            if self.repository is not None and max_age is not None:
                try:
                    stale = self.repository.sec_cache_read(key)
                except SQLAlchemyError:
                    stale = None
                if stale is not None:
                    warnings.append("SEC: tải mới thất bại; dùng bản lưu trước của " + kind + ", chưa xác nhận cập nhật mới nhất.")
                    budget.counts[f"SEC:{kind}_stale_reused"] += 1
                    return stale
            raise
        if self.repository is not None:
            try:
                self.repository.sec_cache_write(key, payload)
            except SQLAlchemyError:
                warnings.append("Chưa lưu được dữ liệu vào kho SEC.")
        budget.counts[f"SEC:{kind}_fetched"] += 1
        return payload

    def filing_chunks(self, ingestion, company, filing, warnings, budget):
        cfg = self.config
        key = (f"filing:v2:{company.cik}:{filing.accession}:{filing.url}:{filing.filed}:{filing.end}:"
               f"{cfg.rag_chunk_size}:{cfg.rag_chunk_overlap}")

        def load():
            rows = ingestion.load(company.cik, filing.url, title=f"{company.name} · {filing.form}",
                                  filed=filing.filed, report_end=filing.end, kind=filing.form, cap=650)
            if not rows:
                raise ValueError("Hồ sơ không có đoạn văn bản sử dụng được")
            return {"chunks": [row.model_dump(mode="json") for row in rows]}

        payload = self.cached_sec(key, load, warnings, budget, "filing")
        return [Evidence.model_validate(row) for row in payload["chunks"]]

    def company_facts(self, sec, company, filings, warnings, budget):
        identity = ",".join(sorted(f.accession for f in filings if f.form.startswith(("10-", "20-", "40-"))))

        cache_identity = f"facts:v1:{company.cik}:{identity}"
        cached = None
        if self.repository is not None:
            try:
                cached = self.repository.sec_cache_read(hashlib.sha256(cache_identity.encode()).hexdigest())
                if cached is None:
                    cached = self.repository.latest_cached_facts(company.cik)
            except SQLAlchemyError:
                pass

        def load():
            timeout, attempts = sec.http.timeout, sec.attempts
            if cached is not None:
                sec.http.timeout, sec.attempts = min(timeout,8), 1
            try:
                payload = sec.facts(company.cik)
            finally:
                sec.http.timeout, sec.attempts = timeout, attempts
            if int(payload["cik"]) != company.cik:
                raise ProviderError("SEC", "CIK nguồn không khớp")
            if not isinstance(payload.get("facts"), dict):
                raise ValueError("Dữ liệu XBRL sai cấu trúc")
            return payload

        try:
            return self.cached_sec(cache_identity, load, warnings, budget, "facts",max_age=timedelta(hours=1))
        except (ProviderError,ValueError,KeyError,OSError):
            if cached is None: raise
            warnings.append("SEC: dùng bản số liệu gần nhất đã lưu của doanh nghiệp; chưa xác nhận các hồ sơ mới. Dữ liệu vẫn được lọc theo ngày chốt.")
            budget.counts["SEC:facts_stale_reused"] += 1
            return cached

    def run(self, request, event):
        cfg = self.config
        started = perf_counter()
        warnings = []
        budget = Budget(cfg.max_analysis_seconds,
                        min(cfg.max_search_requests_per_run,request.search_budget if request.search_budget is not None
                            else cfg.max_search_requests_per_run),cfg.max_gemini_calls)
        event("collecting","Đang xác định ticker và tải hồ sơ SEC.")
        with self.client_factory(follow_redirects=False) as client:
            sec = self.sec(client,budget,warnings)
            company, filings = sec.company(request.ticker,request.as_of)
            try:
                financial_payload = self.company_facts(sec, company, filings, warnings, budget)
            except (ProviderError, KeyError, ValueError) as exc:
                financial_payload = {"cik":company.cik}
                warnings.append(str(exc) if isinstance(exc,ProviderError) else "Dữ liệu XBRL sai cấu trúc.")
            event("validating","Chuẩn hóa dữ liệu SEC theo kỳ, ngày công bố và đơn vị.")
            facts, changes = normalize(financial_payload,request.as_of,request.years)
            official = {f.accession:f.url for f in filings}
            facts = [f.model_copy(update={"url":official.get(f.accession,f.url)}) for f in facts]
            if not facts:
                warnings.append("Chưa có dữ liệu US-GAAP chuẩn hóa cho mốc đã chọn.")
            market = self.market_snapshot(company, facts, request, budget, warnings)
            ratios = calculate(facts,company.sic,market)
            ratios.extend(calculate_quarterly(facts, company.sic))
            peers = self.peers(sec,company,facts,request,warnings,
                               facts_loader=lambda peer, records: self.company_facts(sec, peer, records, warnings, budget),
                               market_loader=lambda peer, rows: self.market_snapshot(peer, rows, request, budget, warnings))
            event("collecting","Đang tìm bài báo và bài đăng công khai theo mã doanh nghiệp.")
            context, documents = self.collect_context(client, budget, company, request)
            chunks = self.collect(client,budget,company,filings,request,warnings)
        event("retrieving","Xây chỉ mục truy xuất theo mốc dữ liệu và công ty.")
        rag = Hybrid([c for c in chunks if c.persist],request.as_of,company.cik,cfg.embedding_model if cfg.embedding_enabled else None,
                     cache_dir=Path(__file__).resolve().parents[1] / ".cache" / "embeddings")
        if rag.warning:
            warnings.append(rag.warning)
        audited = {c.id:c for c in rag.chunks}
        verified = []
        outputs = {}
        self.computed(company,facts,ratios,request,audited,verified,market)
        model = None
        event("analyzing","Các agent phân tích thị trường, tài chính, lợi thế và rủi ro.")
        try:
            model = self.model_factory(cfg,budget)
        except ProviderError as exc:
            warnings.append(str(exc))
        observations = []
        for offset in range(0,len(documents),6):
            batch = documents[offset:offset+6]
            if not model or budget.model_calls - budget.counts["model"] <= 8:
                observations.extend(agents.pending_context(source,"Chưa đủ lượt gọi; nguồn được giữ, không coi là đã phân tích.") for source in batch)
                continue
            try:
                observations.extend(agents.analyze_context(model,company,request.as_of,batch))
            except ProviderError as exc:
                warnings.append(f"Phân tích bối cảnh: {exc}")
                observations.extend(agents.pending_context(source,str(exc)) for source in batch)
        for group, details in context.items():
            details["observations"] = [item for item in observations if item["group"] == group]
            if details["observations"]:
                count = sum(item["analysis_status"] == "analyzed" for item in details["observations"])
                details["analyzed"] = count
                details["pending"] = len(details["observations"]) - count
                details["status"] = "ready" if count == len(details["observations"]) else "partial" if count else "agent_failed"
        for group, details in context.items():
            if details["status"] in {"agent_failed", "agent_unavailable", "search_failed"}:
                label = "Báo chí" if group == "news" else "Mạng xã hội"
                warnings.append(label + ": " + details.get("error", "Chưa hoàn tất phân tích bối cảnh"))
        draft_groups = []
        counter_evidence = rag.retrieve("restatement litigation regulatory risks competition declining demand",
                                        cfg.rag_top_k,since=request.as_of-timedelta(days=950))
        if model:
            for role in agents.ROLES:
                try:
                    drafts, shown = agents.specialist(model,role,company,request.as_of,rag,ratios,cfg.rag_top_k,market,
                                                       facts=facts,peers=peers)
                    draft_groups.append((role,drafts,shown))
                    outputs[role] = {"status":"ready" if drafts else "insufficient","count":len(drafts),"sources_reviewed":len(shown)}
                except ProviderError as exc:
                    warnings.append(f"{role}: {exc}")
                    outputs[role] = {"status":"failed","count":0}
            for role in agents.ROLES:
                if outputs.get(role,{}).get("status") != "failed" or budget.model_calls-budget.counts["model"] <= 6:
                    continue
                try:
                    drafts, shown = agents.specialist(model,role,company,request.as_of,rag,ratios,cfg.rag_top_k,market,facts=facts,peers=peers)
                    draft_groups.append((role,drafts,shown))
                    outputs[role] = {"status":"ready" if drafts else "insufficient","count":len(drafts),"sources_reviewed":len(shown),"recovered":True}
                    warnings[:] = [warning for warning in warnings if not warning.startswith(role+": ")]
                except ProviderError:
                    pass
            for _ in range(cfg.max_agent_rounds if request.mode=="deep" else min(cfg.max_agent_rounds,1)):
                candidates = [d for _,ds,_ in draft_groups for d in ds]
                if not candidates or not counter_evidence:
                    break
                try:
                    objections = agents.challenge(model,company,candidates,counter_evidence)
                    draft_groups.append(("risk",objections,counter_evidence))
                    outputs["cross_examination"] = {"status":"ready","count":len(objections)}
                except ProviderError as exc:
                    warnings.append(f"Phản biện: {exc}")
                    break
        event("verifying","Đối chiếu nhận định với số liệu, trích đoạn và bằng chứng trái chiều.")
        review_cache = {}
        review_items = []
        for role, drafts, shown in draft_groups:
            for draft in drafts:
                preliminary = verify(draft,"pending",role,cik=company.cik,as_of=request.as_of,
                                     provided=shown,numbers=[*facts,*ratios],counters=counter_evidence,
                                     tolerance=cfg.numeric_relative_tolerance)
                if preliminary.reason_code != "REVIEW_PENDING":
                    continue
                identity = hashlib.sha256(draft.model_dump_json().encode()).hexdigest()[:16]
                if any(item["claim_id"] == identity for item in review_items):
                    continue
                review_items.append({"claim_id":identity,"draft":draft.model_dump(),
                    "passages":[{"id":e.id,"quote":ref.quote,"text":e.text,
                                 "published":e.published,"report_end":e.report_end}
                                for ref in draft.references for e in shown
                                if e.id == ref.evidence_id and e.id in preliminary.evidence_ids],
                    "counter_sources":agents.source_payload(counter_evidence[:3])})
        for offset in range(0,len(review_items),8):
            if budget.model_calls - budget.counts["model"] <= 4:
                warnings.append("Dành lượt gọi còn lại cho Lead; một số nhận định chưa được kiểm chứng độc lập.")
                break
            try:
                review_cache.update(agents.review_many(model,company,request.as_of,review_items[offset:offset+8]))
            except ProviderError as exc:
                warnings.append(f"Kiểm chứng theo nhóm: {exc}")
        seen_drafts = set()
        numbers = [*facts, *ratios]
        for role, drafts, shown in draft_groups:
            for draft in drafts:
                identity = (draft.dimension, flat(draft.text),
                            tuple(sorted((r.evidence_id, flat(r.quote)) for r in draft.references)),
                            tuple(n.model_dump_json() for n in [draft.numeric, *draft.comparisons] if n))
                if identity in seen_drafts:
                    continue
                seen_drafts.add(identity)
                def reviewer(claim, excerpts, opponents):
                    return review_cache.get(hashlib.sha256(claim.model_dump_json().encode()).hexdigest()[:16], Review(status="UNVERIFIED",
                        reason="Chưa hoàn tất kiểm chứng độc lập; nhận định vẫn được giữ để phân tích có điều kiện."))

                try:
                    result = verify(draft,f"C{len(verified)+1}",role,cik=company.cik,as_of=request.as_of,
                                    provided=shown,numbers=numbers,review=reviewer,counters=counter_evidence,
                                    tolerance=cfg.numeric_relative_tolerance)
                except ProviderError as exc:
                    warnings.append(f"Kiểm chứng: {exc}")
                    result = verify(draft,f"C{len(verified)+1}",role,cik=company.cik,as_of=request.as_of,
                                    provided=shown,numbers=numbers,tolerance=cfg.numeric_relative_tolerance)
                refs = [r for r in result.claim.references if r.evidence_id in result.evidence_ids]
                # Omit all model wording from temporary evidence, including failed reviews that could echo it.
                if any(not e.persist and e.id in {r.evidence_id for r in result.claim.references} for e in shown):
                    continue
                result.claim.references = refs
                verified.append(result)
        linked_text = {flat(c.claim.text) for c in verified if c.evidence_ids or c.counter_ids}
        verified = [c for c in verified if c.status != "UNVERIFIED" or c.evidence_ids
                    or c.counter_ids or flat(c.claim.text) not in linked_text]
        event("generating","Tổng hợp các nhận định đã kiểm chứng.")
        scores = coverage(verified,list(agents.DIMENSIONS),changes,list(audited.values()))
        accepted = [c for c in verified if c.status=="SUPPORTED"]
        editorial = [c for c in accepted if c.role != "computed"]
        if not editorial and facts:
            warnings.append("Chưa có nhận định chuyên môn đã kiểm chứng. Báo cáo hiện chỉ xác nhận số liệu chuẩn hóa.")
        picked = [c.id for c in editorial[:6]]
        assessment = []
        outputs["lead"] = {"status":"insufficient","count":0}
        topic_coverage = {d:{"total":sum(c.claim.dimension == d for c in verified),
            "supported":sum(c.claim.dimension == d and c.status == "SUPPORTED" for c in verified),
            "agent_status":outputs.get(next(role for role, (_, dims, _) in agents.ROLES.items() if d in dims),{}).get("status","unavailable")}
            for d in agents.DIMENSIONS}
        if model and (verified or documents):
            try:
                assessment = agents.lead(model,company,request.as_of,verified,
                                         [item for details in context.values() for item in details["observations"]],topic_coverage)
                outputs["lead"] = {"status":"ready" if all(p.get("mode") == "model" and p.get("verification_status") == "SUPPORTED" for p in assessment) else "partial","count":sum(p.get("mode") == "model" for p in assessment)}
            except ProviderError as exc:
                warnings.append(f"Tổng hợp: {exc}")
                outputs["lead"] = {"status":"failed","count":0}
        if not assessment:
            assessment = agents.lead_fallback(verified,[],topic_coverage)
        outputs["external_context"] = {
            "status":"ready" if any(item.get("analyzed",0) for item in context.values()) and not any(item.get("pending",0) for item in context.values()) else
                     "partial" if any(item.get("analyzed",0) for item in context.values()) else
                     "failed" if any(item["status"] in {"agent_failed","agent_unavailable","search_failed"}
                                     for item in context.values()) else "insufficient",
            "count":sum(item.get("analyzed",0) for item in context.values()),
        }
        if model:
            model.close()
        outputs["verification"] = {"status":"ready" if any(c.role != "computed" and c.status=="SUPPORTED" for c in verified)
                                    else "insufficient","count":len(verified)}
        annual = {f.end for f in facts if f.period=="FY" and f.key=="revenue"}
        shown_facts = sorted(annual or {f.end for f in facts if f.period=="FY"},reverse=True)[:request.years]
        lower = min(shown_facts,default=request.as_of-timedelta(days=365*request.years))
        has_all = len(scores["covered_dimensions"]) == len(agents.DIMENSIONS)
        used = {i for c in verified for i in [*c.evidence_ids,*c.counter_ids]}
        status = "completed" if has_all and not warnings and facts else "partial" if (facts or accepted) else "failed"
        if status == "failed":
            warnings.append("Chưa có đủ dữ liệu đã xác minh để tạo báo cáo phân tích.")
        return {
            "version":__version__,"created_at":now().isoformat(),"request":request.model_dump(mode="json"),
            "company":company.model_dump(mode="json"),"status":status,
            "facts":[f.model_dump(mode="json") for f in facts if f.end >= lower],
            "ratios":[r.model_dump(mode="json") for r in ratios if r.end and r.end >= lower],
            "filings":[f.model_dump(mode="json") for f in filings[:50]],"market":market,
            "claims":[c.model_dump(mode="json") for c in verified],
            "evidence":[e.model_dump(mode="json") for e in audited.values() if e.id in used],
            "chunks":[e.model_dump(mode="json",exclude={"text"}) for e in audited.values() if e.id not in used and e.kind!="xbrl"],
            "changes":changes,"scores":scores,"topic_coverage":topic_coverage,"summary_ids":picked,"lead_assessment":assessment,
            "retrieval":{"collected_chunks":len(chunks),"indexed_chunks":len(rag.chunks),
                         "indexed_documents":len({c.document_id for c in rag.chunks}),
                         "cited_documents":len({c.document_id for c in rag.chunks if c.id in used}),
                         "vectors_reused":rag.vectors_reused,"vectors_created":rag.vectors_created,
                         "sec_stale_reused":budget.counts["SEC:facts_stale_reused"],
                         "sec_reused":budget.counts["SEC:filing_reused"],
                         "sec_fetched":budget.counts["SEC:filing_fetched"]},
            "agents":outputs,"peers":peers,"external_context":context,
            "diagnostics":{"model_responses":getattr(model,"trace",[])},
            "warnings":list(dict.fromkeys(warnings)),"usage":dict(budget.counts),
            "elapsed_seconds":round(perf_counter()-started,2),"estimated_cost_usd":estimated_cost(budget.counts,cfg),
        }

    def market_snapshot(self, company, facts, request, budget, warnings):
        cfg = self.config
        ref = request.market_reference if company.ticker == request.ticker else None
        market = {}
        if ref:
            market = {"url":ref.url, "currency":ref.currency, "observations":[{"close":ref.close,"date":str(ref.date)}],
                      "snapshot_date":str(request.as_of), "source":"manual"}
        elif cfg.market_enabled and cfg.persist_market and request.as_of == now().date():
            try:
                budget.charge("Yahoo","history")
                market = self.market_factory(company.ticker,request.as_of,False,budget.remaining())
            except Exception as exc:
                warnings.append(f"{company.ticker}: Yahoo Finance không khả dụng ({type(exc).__name__}).")
        if not market:
            return {}
        market = {key: value for key, value in market.items() if key != "market_cap"}
        last = max((row for row in market.get("observations", [])
                    if row.get("close") and row["close"] > 0
                    and 0 <= (request.as_of - date.fromisoformat(row["date"])).days <= 7),
                   key=lambda row: row["date"], default=None)
        if last and market.get("currency") == "USD":
            price_date = date.fromisoformat(last["date"])
            eligible = [f for f in facts if f.key == "shares" and f.unit == "shares" and f.value > 0
                        and f.filed <= price_date and 0 <= (price_date - f.end).days <= 120]
            shares = max(eligible, key=lambda f: (f.end, f.filed), default=None)
            if shares and 0 < last["close"] * shares.value < float("inf"):
                market.update(market_cap=last["close"] * shares.value, market_cap_date=last["date"],
                              shares_fact_id=fact_id(shares),
                              scope="Vốn hóa ước tính từ giá đóng cửa và số cổ phiếu SEC đã công bố tại ngày giá. Bội số dùng năm tài chính gần nhất.")
            else:
                warnings.append(f"{company.ticker}: có giá nhưng thiếu số cổ phiếu SEC phù hợp để tính vốn hóa.")
        return market

    @staticmethod
    def peers(sec, company, facts, request, warnings, *, facts_loader=None, market_loader=None):
        target = max((f.end for f in facts if f.key=="revenue" and f.period=="FY" and f.unit=="USD"),default=None)
        if target is None:
            return []
        comparisons = []
        tickers = request.peers or (SEMICONDUCTOR_PEERS if company.sic == "3674" else ())
        seen = {company.cik}
        for ticker in tickers:
            if ticker == company.ticker:
                continue
            try:
                peer,filings = sec.company(ticker,request.as_of)
                if peer.cik in seen:
                    warnings.append(f"{ticker}: cùng doanh nghiệp (CIK) với mã chính.")
                    continue
                if not request.peers and peer.sic != company.sic:
                    continue
                seen.add(peer.cik)
                payload = facts_loader(peer, filings) if facts_loader else sec.facts(peer.cik)
                peer_facts,_ = normalize(payload,request.as_of,request.years)
                candidates = [f for f in peer_facts if target and f.key=="revenue" and f.period=="FY"
                              and f.unit=="USD" and abs((f.end-target).days)<=92]
                if not candidates:
                    warnings.append(f"{ticker}: thiếu doanh thu USD theo năm trong ±92 ngày so với kỳ chính.")
                    continue
                base = min(candidates,key=lambda f:abs((f.end-target).days))
                peer_market = market_loader(peer, peer_facts) if market_loader else {}
                ratios = calculate(peer_facts,peer.sic,peer_market)
                keys = {"operating_margin","gross_margin","revenue_growth","fcf_margin","roic","net_margin"} | VALUATION
                values = {r.key:r.value for r in ratios if r.end==base.end and r.key in keys}
                filing = next((f.url for f in filings if f.accession==base.accession),base.url)
                comparisons.append({"ticker":ticker,"cik":peer.cik,"name":peer.name,"main_end":str(target),
                                    "end":str(base.end),"unit":base.unit,"revenue":base.value,"ratios":values,"url":filing,
                                    "same_sic":bool(company.sic and peer.sic == company.sic),
                                    "market_url":peer_market.get("url"),"price_date":peer_market.get("market_cap_date")})
            except (ProviderError,KeyError,ValueError) as exc:
                warnings.append(f"{ticker}: dữ liệu đối chiếu chưa sẵn sàng ({type(exc).__name__}).")
        return comparisons

    def collect_context(self, client, budget, company, request):
        cfg = self.config
        status = {group: {"status":"disabled","found":0,"read":0,"observations":[]}
                  for group in ("news","social")}
        documents = []
        if cfg.search_provider != "brave" or not cfg.brave_web_search_enabled or not cfg.brave_search_api_key.get_secret_value():
            return status, documents
        brave = Brave(Http(client, budget, self.brave_rate, "Brave", 5), cfg, attempts=1)
        origin = Http(client, budget, self.sec_rate, "Nguồn bối cảnh", 4)
        for group, details in status.items():
            if budget.counts["search"] >= budget.searches:
                details["status"] = "search_budget"
                continue
            hits = {}
            hosts = (None, "finance.yahoo.com") if group == "news" else CONTEXT_SITES[group]
            errors = []
            for host in hosts:
                if group == "news" and host and budget.searches - budget.counts["search"] <= 1:
                    break
                if budget.counts["search"] >= budget.searches:
                    break
                try:
                    found = {hit.url: hit for hit in brave.search(
                        context_query(company.name, company.ticker, group, host), group, "web")
                             if context_hit(hit.url, group)}
                    hits = {**found, **hits} if group == "news" and host else {**hits, **found}
                except (ProviderError, ValueError) as exc:
                    errors.append(str(exc) if isinstance(exc, ProviderError) else "Brave trả phản hồi sai định dạng.")
                    if isinstance(exc, ProviderError) and ("xác thực" in exc.category or "hết" in exc.category):
                        break
                    continue
                details["status"] = "empty"
            details["found"] = len(hits)
            if errors:
                details["error"] = errors[0]
                if details["status"] != "empty":
                    details["status"] = "search_failed"
            selected = []
            unreadable = {}
            excerpts = []
            attempted = 0
            blocked_hosts = set()
            excluded = set()
            for url in hits:
                host = urlsplit(url).hostname
                if host in blocked_hosts or attempted >= 12:
                    fallback = context_excerpt(hits[url], group, request.as_of)
                    if fallback:
                        excerpts.append(fallback)
                    continue
                attempted += 1
                try:
                    document = context_document(origin, url, group, request.as_of)
                except (ProviderError, ValueError, OSError) as exc:
                    reason = exc.category if isinstance(exc, ProviderError) else (
                        str(exc) if type(exc) is ValueError else "Không kết nối được trang gốc")
                    unreadable[reason] = unreadable.get(reason, 0) + 1
                    if reason == "Đăng sau ngày chốt":
                        excluded.add(url)
                    if isinstance(exc, ProviderError) and any(code in exc.category for code in ("401", "403", "429")):
                        blocked_hosts.add(host)
                    fallback = context_excerpt(hits[url], group, request.as_of) if reason != "Đăng sau ngày chốt" else None
                    if fallback:
                        excerpts.append(fallback)
                    continue
                if document and all(item["text"] != document["text"] for item in selected):
                    selected.append(document)
                elif not document:
                    reason = "Định dạng hoặc đường dẫn không đọc được"
                    unreadable[reason] = unreadable.get(reason, 0) + 1
            details["unreadable_reasons"] = unreadable
            details["read"] = len(selected)
            details["attempted"] = attempted
            details["links"] = [{"url":hit.url,"title":hit.title} for hit in hits.values()]
            selected_urls = {item["url"] for item in selected}
            fallback = [item for item in excerpts if item["url"] not in selected_urls]
            details["excerpts"] = len(fallback)
            selected.extend(fallback)
            included = {item["url"] for item in selected}
            for url, hit in hits.items():
                if url in included or url in excluded: continue
                try:
                    if hit.published and date.fromisoformat(hit.published[:10]) > request.as_of:
                        excluded.add(url)
                        continue
                except ValueError:
                    pass
                selected.append({"id":hashlib.sha256(url.encode()).hexdigest()[:16],"url":url,
                    "title":hit.title,"group":group,"published":"","text":"","source_type":"link_only"})
            details["excluded_after_cutoff"] = len(excluded)
            details["queued"] = len(selected)
            if hits:
                details["status"] = "pending_agent" if selected else "unreadable"
            documents.extend(selected)
        return status, documents

    def collect(self, client, budget, company, filings, request, warnings):
        cfg = self.config
        ingestion = Ingest(Http(client,budget,self.sec_rate,"Tài liệu",cfg.sec_timeout_seconds),cfg)
        brave = Brave(Http(client,budget,self.brave_rate,"Brave",12),cfg)
        targets = []
        for kinds in ({"10-K","20-F","40-F"},{"10-Q"},{"DEF 14A"},{"8-K"},{"10-K/A","10-Q/A","20-F/A","40-F/A"}):
            chosen = [f for f in filings if f.form in kinds]
            targets.extend(chosen[:2 if request.mode=="deep" or kinds & {"10-K","10-Q"} else 1])
        chunks, seen = [], set()
        for filing in targets:
            seen.add(filing.url)
            try:
                chunks.extend(self.filing_chunks(ingestion, company, filing, warnings, budget))
            except (ProviderError,ValueError,OSError) as exc:
                warnings.append(f"{filing.form} {filing.filed}: {exc}")
        if request.as_of < now().date() or cfg.search_provider=="off" or budget.searches==0 or not ingestion.allowed - SEC_HOSTS:
            return chunks
        if not cfg.brave_search_api_key.get_secret_value() and not cfg.search_fallback_enabled:
            warnings.append("Chưa cấu hình khóa Brave. Hồ sơ SEC vẫn được sử dụng.")
            return chunks
        found = {f.url:f for f in filings}
        downloads = {"sec": 0, "external": 0}
        external_limit = 3 if ingestion.allowed - SEC_HOSTS else 0
        search_plan = list(plans(company.name,company.ticker,request.mode,cfg.search_tier_limits))
        if any(context_host(host, "news") for host in ingestion.allowed & set(cfg.persist_source_hosts)):
            search_plan.insert(0, ("news", context_query(company.name, company.ticker, "news"), "web"))
        for tier, query, method in search_plan:
            if budget.counts["search"] >= budget.searches:
                break
            if method=="web" and not cfg.brave_web_search_enabled:
                method = "context" if cfg.brave_llm_context_enabled else ""
            if method=="context" and not cfg.brave_llm_context_enabled:
                method = "web" if cfg.brave_web_search_enabled else ""
            if not method:
                continue
            try:
                hits = brave.search(query,tier,method)
            except (ProviderError,ValueError) as exc:
                warnings.append(str(exc) if isinstance(exc,ProviderError) else "Brave trả phản hồi sai định dạng.")
                if isinstance(exc,ProviderError) and exc.category in {"hết ngân sách","hết thời gian"}:
                    break
                if not cfg.search_fallback_enabled:
                    if isinstance(exc,ProviderError) and ("xác thực" in exc.category or "429" in exc.category):
                        break
                    continue
                try:
                    hits = ddgs_search(query,tier,cfg.brave_results_per_query,budget)
                except Exception as fallback_error:
                    warnings.append(f"DDGS không khả dụng ({type(fallback_error).__name__}).")
                    break
            for hit in hits:
                host = urlsplit(hit.url).hostname
                if not host or hit.url in seen or host not in ingestion.allowed or context_host(host, "social"):
                    continue
                group = "sec" if host in SEC_HOSTS else "external"
                filing = found.get(hit.url)
                if group == "sec" and not filing:
                    continue
                if downloads[group] >= (8-external_limit if group == "sec" else external_limit):
                    continue
                seen.add(hit.url)
                downloads[group] += 1
                try:
                    kind = filing.form if filing else "news" if context_host(host, "news") else tier
                    if filing:
                        chunks.extend(self.filing_chunks(ingestion, company, filing, warnings, budget)[:120])
                    else:
                        chunks.extend(ingestion.load(company.cik, hit.url, kind=kind, cap=120))
                except (ProviderError,ValueError,OSError):
                    warnings.append("Một tài liệu tìm được không thể đọc hoặc không thuộc doanh nghiệp.")
        return chunks

    @staticmethod
    def computed(company,facts,ratios,request,audited,verified,market=None):
        labels = {"revenue":"Doanh thu","net_income":"Lợi nhuận ròng","revenue_growth":"Tăng trưởng doanh thu",
                  "operating_margin":"Biên lợi nhuận hoạt động","fcf":"Dòng tiền tự do","ocf":"Dòng tiền hoạt động",
                  "current_ratio":"Hệ số thanh toán hiện hành","net_debt":"Nợ ròng","interest_coverage":"Khả năng trả lãi",
                  "pe":"P/E","pb":"P/B","p_fcf":"P/FCF","ev_ebitda":"EV/EBITDA"}
        fact_map = {fact_id(f):f for f in facts}
        market_source = None
        if market and market.get("shares_fact_id") in fact_map and market.get("market_cap_date"):
            date_price = date.fromisoformat(market["market_cap_date"])
            price = next(row["close"] for row in market["observations"] if row["date"] == str(date_price))
            body = f"Giá tham chiếu {vi_number(price)} USD ngày {date_price:%d/%m/%Y}."
            digest = hashlib.sha256((market["url"] + body).encode()).hexdigest()
            market_source = Evidence(id="M:"+digest[:24], company_cik=company.cik, document_id=digest[:24],
                                     title="Giá nhập thủ công" if market.get("source")=="manual" else "Giá Yahoo Finance",
                                     url=market["url"], locator="Giá tham chiếu", published=date_price, text=body,
                                     quality="external", kind="market", content_hash=digest)
        annual_ends = sorted({f.end for f in facts if f.period=="FY"},reverse=True)
        for end in annual_ends[:1]:
            for key,label in labels.items():
                values = [x for x in [*facts,*ratios] if x.key==key and x.end==end and x.value is not None
                          and x.period=="FY" and (not hasattr(x,"accession") or x.unit=="USD")]
                if len(values)!=1:
                    continue
                value = values[0]
                inputs = [value] if hasattr(value,"accession") else [fact_map[i] for i in value.inputs if i in fact_map]
                if key in VALUATION:
                    if market_source is None:
                        continue
                refs = []
                evidence_list = []
                for f in inputs:
                    fid = hashlib.sha256(fact_id(f).encode()).hexdigest()[:24]
                    body = f"{f.concept} | {f.value:,.8g} {f.unit} | kỳ kết thúc {f.end} | công bố {f.filed}"
                    e = Evidence(id=f"X:{fid}",company_cik=company.cik,document_id=f.accession,
                                 title=f"{company.name} · SEC XBRL",url=f.url,locator=f.concept,
                                 published=f.filed,text=body,quality="primary",kind="xbrl",report_end=f.end,
                                 content_hash=hashlib.sha256(body.encode()).hexdigest())
                    audited[e.id] = e
                    evidence_list.append(e)
                    refs.append(Reference(evidence_id=e.id,quote=body))
                if key in VALUATION:
                    audited[market_source.id] = market_source
                    evidence_list.append(market_source)
                    refs.append(Reference(evidence_id=market_source.id, quote=market_source.text))
                dimension = "growth" if key=="revenue_growth" else "valuation" if key in VALUATION else "financial"
                formatted = (money(value.value) if value.unit == "USD" else percent(value.value)
                             if value.unit == "%" else vi_number(value.value) + " lần")
                text = f"{label} kỳ kết thúc {end:%d/%m/%Y} là {formatted}."
                if key in VALUATION:
                    text = f"{label} là {formatted}, dùng giá ngày {market_source.published:%d/%m/%Y} và kết quả năm kết thúc {end:%d/%m/%Y}."
                draft = Draft(dimension=dimension,text=text,
                              references=refs,numeric=Numeric(key=key,value=value.value,unit=value.unit,end=end,period=value.period))
                verified.append(verify(draft,f"C{len(verified)+1}","computed",cik=company.cik,
                                       as_of=request.as_of,provided=evidence_list,numbers=[value]))
