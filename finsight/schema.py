from datetime import date, datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def now() -> datetime:
    return datetime.now(timezone.utc)


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class MarketReference(Model):
    close: float = Field(gt=0)
    date: date
    currency: Literal["USD"] = "USD"
    url: str = Field(pattern=r"^https://[^\s]+$", max_length=500)


class Request(Model):
    ticker: str = Field(pattern=r"^[A-Z][A-Z0-9.\-]{0,11}$")
    as_of: date = Field(default_factory=lambda: now().date())
    years: int = Field(10, ge=2, le=10)
    mode: Literal["standard", "deep"] = "standard"
    search_budget: int | None = Field(None, ge=0, le=50)
    peers: list[str] = Field(default_factory=list, max_length=3)
    market_reference: MarketReference | None = None

    @field_validator("ticker", mode="before")
    @classmethod
    def normalize_ticker(cls, value):
        return value.strip().upper() if isinstance(value, str) else value

    @field_validator("peers")
    @classmethod
    def peer_tickers(cls, values):
        import re
        tickers = [v.strip().upper() for v in values]
        if any(not re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,11}",v) for v in tickers):
            raise ValueError("Mã cổ phiếu đối chiếu không hợp lệ")
        return list(dict.fromkeys(tickers))

    @field_validator("as_of")
    @classmethod
    def no_future(cls, value):
        if value > now().date():
            raise ValueError("Mốc dữ liệu nằm trong tương lai")
        return value

    @model_validator(mode="after")
    def reference_date(self):
        if self.market_reference and not 0 <= (self.as_of - self.market_reference.date).days <= 7:
            raise ValueError("Ngày giá phải nằm trong 7 ngày tính đến mốc báo cáo.")
        return self


class Company(Model):
    ticker: str
    cik: int
    name: str
    sic: str = ""
    industry: str = ""
    exchange: str = ""


class Filing(Model):
    accession: str
    form: str
    filed: date
    end: date
    url: str


class Fact(Model):
    key: str
    value: float
    unit: str
    start: date | None = None
    end: date
    filed: date
    period: Literal["FY", "Q", "YTD", "instant"]
    concept: str
    accession: str
    url: str
    fiscal_year: int | None = None
    fiscal_period: str = ""
    form: str = ""


class Ratio(Model):
    period: Literal["FY", "Q"] = "FY"
    key: str
    value: float | None
    unit: str
    end: date | None
    formula: str
    inputs: list[str] = Field(default_factory=list)
    reason: str = ""
    filed: date | None = None


class Evidence(Model):
    id: str
    company_cik: int
    document_id: str
    title: str
    url: str
    locator: str
    published: date | None
    text: str
    quality: Literal["primary", "approved", "external"]
    content_hash: str
    kind: str
    report_end: date | None = None
    index: int = 0
    ingested_at: datetime = Field(default_factory=now)
    persist: bool = True


Dimension = Literal["company", "financial", "growth", "moat", "industry", "governance", "risk", "valuation"]
Status = Literal["SUPPORTED", "PARTIALLY_SUPPORTED", "CONTRADICTED", "UNVERIFIED", "NOT_APPLICABLE"]


class Reference(Model):
    evidence_id: str
    quote: str = Field(min_length=12, max_length=450)


class Numeric(Model):
    @field_validator("key", mode="before", check_fields=False)
    @classmethod
    def canonical_key(cls, value):
        from finsight.financials import canonical_metric
        return canonical_metric(value)

    period: Literal["FY", "Q", "YTD", "instant"] | None = None
    key: str
    value: float
    unit: str
    end: date


class Draft(Model):
    dimension: Dimension
    text: str = Field(min_length=5, max_length=500)
    stance: Literal["positive", "negative", "neutral"] = "neutral"
    references: list[Reference] = Field(default_factory=list, max_length=8)
    numeric: Numeric | None = None
    comparisons: list[Numeric] = Field(default_factory=list, max_length=4)


class Drafts(Model):
    claims: list[Draft] = Field(max_length=6)


class ContextObservation(Model):
    source_id: str
    text: str = Field(min_length=10, max_length=400)
    quote: str = Field(default="", max_length=450)
    dimension: Dimension = "risk"
    reason: str = Field(default="", max_length=500)


class ContextAssessment(Model):
    observations: list[ContextObservation] = Field(max_length=6)


class Review(Model):
    status: Literal["SUPPORTED", "PARTIALLY_SUPPORTED", "CONTRADICTED", "UNVERIFIED"]
    reason: str = Field(max_length=500)
    counter_ids: list[str] = Field(default_factory=list,max_length=3)


class ReviewItem(Review):
    claim_id: str


class Reviews(Model):
    items: list[ReviewItem] = Field(max_length=60)


class Selection(Model):
    claim_ids: list[str] = Field(max_length=16)


class LeadPoint(Model):
    topic: Literal["overall", "health", "business", "valuation", "conditions", "gaps"]
    text: str = Field(min_length=10, max_length=1800)
    claim_ids: list[str] = Field(default_factory=list, max_length=12)
    context_ids: list[str] = Field(default_factory=list, max_length=3)


class LeadAssessment(Model):
    points: list[LeadPoint] = Field(max_length=6)


class Verified(Model):
    reason_code: str = ""
    id: str
    role: str
    claim: Draft
    status: Status
    reason: str
    evidence_ids: list[str] = Field(default_factory=list)
    counter_ids: list[str] = Field(default_factory=list)
