from datetime import date, datetime, timedelta
import hashlib
import json
from uuid import uuid4

from sqlalchemy import (JSON, Date, DateTime, ForeignKey, ForeignKeyConstraint, Index, String, Text,
                        UniqueConstraint, create_engine, delete, func, select, text, update)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from finsight.schema import now


def utc():
    return now().replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class Run(Base):
    __tablename__ = "research_runs"
    __table_args__ = (Index("ix_run_history","ticker","created_at"),)
    id: Mapped[str] = mapped_column(String(36),primary_key=True)
    fingerprint: Mapped[str | None] = mapped_column(String(64),unique=True)
    ticker: Mapped[str] = mapped_column(String(12))
    as_of: Mapped[date] = mapped_column(Date)
    request: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime,default=utc)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime)


class Event(Base):
    __tablename__ = "pipeline_events"
    id: Mapped[int] = mapped_column(primary_key=True,autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("research_runs.id",ondelete="CASCADE"),index=True)
    status: Mapped[str] = mapped_column(String(20))
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime,default=utc)


class CompanyRow(Base):
    __tablename__ = "companies"
    cik: Mapped[int] = mapped_column(primary_key=True,autoincrement=False)
    payload: Mapped[dict] = mapped_column(JSON)


class SecCacheRow(Base):
    __tablename__ = "sec_source_cache"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    stored_at: Mapped[datetime] = mapped_column(DateTime)
    payload: Mapped[dict] = mapped_column(JSON)


class Report(Base):
    __tablename__ = "analysis_reports"
    run_id: Mapped[str] = mapped_column(ForeignKey("research_runs.id",ondelete="CASCADE"),primary_key=True)
    cik: Mapped[int] = mapped_column(ForeignKey("companies.cik"),index=True)
    payload: Mapped[dict] = mapped_column(JSON)


class ClaimRow(Base):
    __tablename__ = "analysis_claims"
    run_id: Mapped[str] = mapped_column(ForeignKey("analysis_reports.run_id",ondelete="CASCADE"),primary_key=True)
    claim_id: Mapped[str] = mapped_column(String(24),primary_key=True)
    status: Mapped[str] = mapped_column(String(24))
    payload: Mapped[dict] = mapped_column(JSON)


class EvidenceRow(Base):
    __tablename__ = "document_chunks"
    run_id: Mapped[str] = mapped_column(ForeignKey("analysis_reports.run_id",ondelete="CASCADE"),primary_key=True)
    evidence_id: Mapped[str] = mapped_column(String(64),primary_key=True)
    document_id: Mapped[str] = mapped_column(String(64),index=True)
    payload: Mapped[dict] = mapped_column(JSON)


class EvidenceLink(Base):
    __tablename__ = "claim_evidence"
    __table_args__ = (
        UniqueConstraint("run_id","claim_id","evidence_id","relation"),
        ForeignKeyConstraint(("run_id","claim_id"),("analysis_claims.run_id","analysis_claims.claim_id"),
                             name="fk_evidence_link_claim",ondelete="CASCADE"),
        ForeignKeyConstraint(("run_id","evidence_id"),("document_chunks.run_id","document_chunks.evidence_id"),
                             name="fk_evidence_link_chunk",ondelete="CASCADE"),
    )
    id: Mapped[int] = mapped_column(primary_key=True,autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("analysis_reports.run_id",ondelete="CASCADE"),index=True)
    claim_id: Mapped[str] = mapped_column(String(24))
    evidence_id: Mapped[str] = mapped_column(String(64))
    relation: Mapped[str] = mapped_column(String(12))


class Feedback(Base):
    __tablename__ = "user_feedback"
    id: Mapped[int] = mapped_column(primary_key=True,autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("analysis_reports.run_id",ondelete="CASCADE"),index=True)
    score: Mapped[int]
    note: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime,default=utc)


FINAL = {"completed","partial","failed"}


def mysql_engine(config):
    return create_engine(config.db_url,pool_pre_ping=True,pool_recycle=1200,
                         connect_args={"connect_timeout":5,"read_timeout":20,"write_timeout":20})


def stamp(value):
    return value.isoformat()+"Z" if value else None


class Repository:
    def __init__(self, engine, lease_seconds):
        self.engine = engine
        self.session = sessionmaker(engine,expire_on_commit=False)
        self.lease_seconds = lease_seconds

    def health(self):
        with self.engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            conn.execute(select(Run.id).limit(1))

    def sec_cache_read(self, key, max_age=None):
        with self.session() as session:
            row = session.get(SecCacheRow, key)
            if row and (max_age is None or utc() - row.stored_at <= max_age):
                return row.payload
        return None

    def latest_cached_facts(self, cik):
        with self.session() as session:
            rows = session.execute(select(SecCacheRow.key,SecCacheRow.stored_at).where(SecCacheRow.payload["cik"].as_integer() == cik)).all()
            for key, _ in sorted(rows,key=lambda item:item[1],reverse=True):
                row = session.get(SecCacheRow,key)
                if isinstance(row.payload.get("facts"),dict):
                    return row.payload
        return None

    def sec_cache_write(self, key, payload):
        values = {"key": key, "payload": payload, "stored_at": utc()}
        with self.session.begin() as session:
            if self.engine.dialect.name == "mysql":
                from sqlalchemy.dialects.mysql import insert
                stmt = insert(SecCacheRow).values(**values)
                session.execute(stmt.on_duplicate_key_update(payload=stmt.inserted.payload, stored_at=stmt.inserted.stored_at))
            else:
                session.merge(SecCacheRow(**values))

    def submit(self, request):
        payload = request.model_dump(mode="json")
        fingerprint = hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()
        self.expire()
        run_id = str(uuid4())
        try:
            with self.session.begin() as s:
                s.add(Run(id=run_id,fingerprint=fingerprint,ticker=request.ticker,as_of=request.as_of,
                          request=payload,status="pending",lease_until=utc()+timedelta(seconds=4*self.lease_seconds)))
            return run_id,True
        except IntegrityError:
            with self.session() as s:
                existing = s.scalar(select(Run.id).where(Run.fingerprint==fingerprint))
            if existing:
                return existing,False
            raise

    def expire(self):
        with self.session.begin() as s:
            s.execute(update(Run).where(Run.lease_until < utc(),Run.status.not_in(FINAL)).values(
                status="failed",fingerprint=None,lease_until=None))

    def event(self, run_id, status, message):
        with self.session.begin() as s:
            run = s.get(Run,run_id,with_for_update=True)
            if run and run.status not in FINAL:
                run.status = status
                run.lease_until = utc()+timedelta(seconds=self.lease_seconds)
                s.add(Event(run_id=run_id,status=status,message=message))

    def finish(self, run_id, report, status, message):
        if report is not None:
            def encode(value):
                if isinstance(value,(date,datetime)): return value.isoformat()
                raise TypeError(f"Unsupported report value: {type(value).__name__}")
            report = json.loads(json.dumps(report,default=encode,allow_nan=False))
        with self.session.begin() as s:
            run = s.get(Run,run_id,with_for_update=True)
            if not run or run.status in FINAL:
                return
            if report:
                company = report["company"]
                if self.engine.dialect.name == "mysql":
                    from sqlalchemy.dialects.mysql import insert
                    stmt = insert(CompanyRow).values(cik=company["cik"],payload=company)
                    s.execute(stmt.on_duplicate_key_update(payload=stmt.inserted.payload))
                else:
                    s.merge(CompanyRow(cik=company["cik"],payload=company))
                s.flush()
                payload = {k:v for k,v in report.items() if k not in {"claims","evidence","chunks"}}
                s.add(Report(run_id=run_id,cik=company["cik"],payload=payload))
                s.flush()
                s.add_all(ClaimRow(run_id=run_id,claim_id=c["id"],status=c["status"],payload=c)
                          for c in report["claims"])
                s.add_all(EvidenceRow(run_id=run_id,evidence_id=e["id"],document_id=e["document_id"],payload=e)
                          for e in [*report["evidence"],*report["chunks"]])
                s.flush()
                for claim in report["claims"]:
                    for relation, ids in (("support",claim["evidence_ids"]),("counter",claim["counter_ids"])):
                        s.add_all(EvidenceLink(run_id=run_id,claim_id=claim["id"],evidence_id=e,relation=relation) for e in ids)
            run.status = status
            run.lease_until,run.fingerprint = None,None
            s.add(Event(run_id=run_id,status=status,message=message))

    def get(self, run_id):
        self.expire()
        with self.session() as s:
            row = s.get(Run,run_id)
            return self._run(row) if row else None

    @staticmethod
    def _run(row):
        return {"id":row.id,"status":row.status,"ticker":row.ticker,"as_of":str(row.as_of),
                "created_at":stamp(row.created_at),"request":row.request}

    def events(self, run_id):
        with self.session() as s:
            rows = s.scalars(select(Event).where(Event.run_id==run_id).order_by(Event.id))
            return [{"status":r.status,"message":r.message,"at":stamp(r.created_at)} for r in rows]

    def report(self, run_id):
        with self.session() as s:
            row = s.get(Report,run_id)
            if not row:
                return None
            claims = [r.payload for r in s.scalars(select(ClaimRow).where(ClaimRow.run_id==run_id))]
            claims.sort(key=lambda x:int(x["id"][1:]))
            ids = {i for c in claims for i in [*c["evidence_ids"],*c["counter_ids"]]}
            evidence = [r.payload for r in s.scalars(select(EvidenceRow).where(
                EvidenceRow.run_id==run_id,EvidenceRow.evidence_id.in_(ids)))] if ids else []
            return {"id":run_id,**row.payload,"claims":claims,"evidence":evidence}

    def dashboard(self):
        with self.session() as s:
            companies = s.scalar(select(func.count(func.distinct(Report.cik))))
            count = s.scalar(select(func.count()).select_from(Report))
            latest = s.scalar(select(Report).join(Run).order_by(Run.created_at.desc()).limit(1))
            evidence_count = s.scalar(select(func.count()).select_from(EvidenceRow))
            claim_count = s.scalar(select(func.count()).select_from(ClaimRow))
        return {"companies":companies,"reports":count,"evidence_count":evidence_count,"claim_count":claim_count,"latest_scores":latest.payload.get("scores") if latest else None,
                "latest_cost_usd":latest.payload.get("estimated_cost_usd") if latest else None}

    def history(self, ticker=None, after=None, limit=50, *, q=None, status=None, offset=0, oldest=False):
        self.expire()
        name = CompanyRow.payload["name"].as_string()
        industry = CompanyRow.payload["industry"].as_string()
        stmt = (select(Run, name, industry).outerjoin(Report, Report.run_id == Run.id)
                .outerjoin(CompanyRow, CompanyRow.cik == Report.cik)
                .order_by(Run.created_at.asc() if oldest else Run.created_at.desc(), Run.id)
                .offset(offset).limit(limit))
        if ticker:
            stmt = stmt.where(Run.ticker == ticker)
        if q:
            term = q.casefold()
            stmt = stmt.where(func.lower(Run.ticker).contains(term, autoescape=True)
                              | func.lower(name).contains(term, autoescape=True))
        if after:
            stmt = stmt.where(Run.as_of >= after)
        if status:
            stmt = stmt.where(Run.status.in_(status))
        with self.session() as session:
            return [self._run(run) | {"company_name": company_name, "industry": sector}
                    for run, company_name, sector in session.execute(stmt)]

    def delete(self, run_id):
        with self.session.begin() as s:
            return bool(s.execute(delete(Run).where(Run.id==run_id,Run.status.in_(FINAL))).rowcount)

    def feedback(self, run_id, score, note):
        with self.session.begin() as s:
            if not s.get(Report,run_id):
                return False
            s.add(Feedback(run_id=run_id,score=score,note=note))
            return True

    def company(self, cik):
        with self.session() as s:
            row = s.get(CompanyRow,cik)
            return row.payload if row else None

    def financials(self, cik):
        with self.session() as s:
            stmt = select(Report).join(Run).where(Report.cik==cik).order_by(Run.created_at.desc()).limit(1)
            row = s.scalar(stmt)
            return {k:row.payload[k] for k in ("facts","ratios")} if row else None
