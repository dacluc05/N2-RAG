from dataclasses import dataclass
from datetime import date
import hashlib
import ipaddress
import json
import re
import socket
from urllib.parse import urlsplit, urlunsplit

from bs4 import BeautifulSoup

from finsight.context_reader import read_context_article
from finsight.schema import Evidence
from finsight.transport import Budget, Http, ProviderError


TIERS = (
    ("official", "site:sec.gov annual report 10-K 10-Q proxy statement", "investor relations filetype:pdf annual report"),
    ("financial", "annual results revenue earnings cash flow", "financial statements liquidity debt capital expenditure"),
    ("industry", "business model segments competition industry market share", "competitors alternatives customer disclosures industry trends -site:sec.gov"),
    ("risk", "regulatory litigation supply chain risks", "regulator government supply chain export controls litigation -site:sec.gov"),
    ("market", "stock market earnings outlook news", "market sentiment investor expectations"),
    ("counter", "investigation concerns downside challenges", "contrary results restatement competitive pressure"),
)
SEC_HOSTS = {"www.sec.gov", "sec.gov"}
CONTEXT_SITES = {
    "news": ("reuters.com", "cnbc.com", "apnews.com", "ft.com", "wsj.com", "bloomberg.com", "finance.yahoo.com", "theguardian.com", "bbc.com"),
    "social": ("reddit.com", "stocktwits.com", "x.com"),
}


def context_query(name: str, ticker: str, group: str, host: str | None = None) -> str:
    company = re.sub(r"[^\w .&,-]", " ", name).strip()[:100]
    if host and group == "social":
        path = {"reddit.com": " inurl:comments", "x.com": " inurl:status", "stocktwits.com": " inurl:message"}[host]
        return f"{ticker} site:{host}{path}"
    if host:
        return f'("{company}" OR "{ticker}") (earnings OR regulation OR competition OR outlook) site:{host}'
    sites = " OR ".join(f"site:{host}" for host in CONTEXT_SITES[group])
    return f'("{company}" OR "{ticker}") (earnings OR regulation OR competition OR CEO OR leadership) ({sites})'


def context_hit(url: str, group: str) -> bool:
    parsed = urlsplit(url)
    if not context_host(parsed.hostname or "", group):
        return False
    if group == "news":
        path = parsed.path.casefold()
        if path.startswith(("/quote/", "/quotes/", "/markets/companies/", "/profile/", "/data/")):
            return False
        return path.strip("/").count("/") > 0 or bool(re.match(r"/(?:article|content)/[^/]+", path))
    return bool(re.search(r"/(?:comments|status|message)/[\w-]+", parsed.path))


def context_host(host: str, group: str) -> bool:
    return any(host == site or host.endswith("." + site) for site in CONTEXT_SITES[group])


def plans(name: str, ticker: str, mode: str, limits: list[int]):
    prefix = '"' + re.sub(r'[^\w .&,-]', ' ', name)[:100] + f'" {ticker}'
    for index, (tier, *variants) in enumerate(TIERS):
        if limits[index]:
            yield tier, f"{prefix} {variants[0]}", "web"
    if mode == "deep":
        for index, (tier, *variants) in enumerate(TIERS):
            for n in range(1, limits[index]):
                yield tier, f"{prefix} {variants[n % len(variants)]}", "context" if n == 1 else "web"


def canonical(url: str) -> str:
    try:
        p = urlsplit(url)
        if (p.scheme.lower() != "https" or not p.hostname or p.username or p.password
                or p.port not in (None, 443) or "\\" in url or any(c.isspace() for c in url)):
            return ""
        # Keep nontracking queries because some sites use query parameters to identify documents.
        query = "&".join(x for x in p.query.split("&") if x and not x.lower().startswith(("utm_", "fbclid=")))
        return urlunsplit(("https", p.hostname.lower().rstrip("."), p.path or "/", query, ""))
    except (ValueError, TypeError, AttributeError):
        return ""


@dataclass(frozen=True)
class SearchHit:
    url: str
    tier: str
    title: str = ""
    excerpt: str = ""
    published: str = ""


class Brave:
    def __init__(self, http, config, *, attempts=3):
        self.http, self.config = http, config
        self.attempts = attempts

    def search(self, query: str, tier: str, method: str) -> list[SearchHit]:
        cfg = self.config
        secret = cfg.brave_search_api_key.get_secret_value()
        if not secret:
            raise ProviderError("Brave", "thiếu BRAVE_SEARCH_API_KEY")
        params = {"q":query, "country":cfg.brave_country, "search_lang":cfg.brave_search_lang}
        if method == "context":
            endpoint = "llm/context"
            params.update(maximum_number_of_urls=cfg.brave_results_per_query,
                          maximum_number_of_tokens=cfg.brave_llm_context_max_tokens,
                          context_threshold_mode="strict" if tier in {"official","counter"} else cfg.brave_context_threshold)
        else:
            endpoint = "web/search"
            params.update(count=cfg.brave_results_per_query, extra_snippets="true", safesearch="moderate")
        raw, _ = self.http.get("https://api.search.brave.com/res/v1/" + endpoint, method,
            headers={"X-Subscription-Token":secret,"Accept":"application/json"}, params=params,
            max_bytes=2_000_000, attempts=self.attempts)
        payload = json.loads(raw)
        if method == "context":
            records = payload.get("grounding", {}).get("generic", [])
        else:
            records = payload.get("web", {}).get("results", [])
        hits = {}
        for record in records:
            url = canonical(record.get("url"))
            if url:
                hits.setdefault(url, SearchHit(url, tier, BeautifulSoup(
                    str(record.get("title") or ""), "html.parser").get_text(" ", strip=True)[:200],
                    BeautifulSoup(str(record.get("description") or "") if tier in {"news", "social"} else "", "html.parser").get_text(" ", strip=True)[:1800],
                    str(record.get("page_age") or "")))
        return list(hits.values())



def context_excerpt(hit: SearchHit, group: str, as_of: date):
    """Search extracts are limited context, never equivalent to reading the source."""
    try:
        published = date.fromisoformat(hit.published[:10])
    except (ValueError, TypeError):
        return None
    if published > as_of or len(hit.excerpt.strip()) < 50 or not context_hit(hit.url, group):
        return None
    return {"id":hashlib.sha256(hit.url.encode()).hexdigest()[:16], "group":group,
            "title":hit.title, "url":hit.url, "published":str(published),
            "text":hit.excerpt, "source_type":"search_excerpt"}

def ddgs_search(query: str, tier: str, count: int, budget: Budget):
    from ddgs import DDGS
    budget.charge("DDGS", "web")
    with DDGS(timeout=min(8, budget.remaining())) as client:
        records = client.text(query, max_results=count)
    urls = dict.fromkeys(canonical(r.get("href")) for r in records)
    return [SearchHit(url,tier) for url in urls if url]


def check_source(url: str, allowed: set[str]):
    host = urlsplit(url).hostname
    if host not in allowed:
        raise ValueError("Tên miền chưa được cấu hình để đọc tài liệu")
    ips = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    if not ips or not all(ipaddress.ip_address(x[4][0]).is_global for x in ips):
        raise ValueError("Địa chỉ mạng không công khai")


def paragraph_chunks(text: str, size: int, overlap: int):
    offset = 0
    while offset < len(text):
        end = min(len(text), offset + size)
        if end < len(text):
            # Keep the cut at a word boundary when the window contains one.
            split = next((i for i in range(end, offset, -1) if text[i].isspace()), None)
            if split is not None:
                end = split
        chunk = text[offset:end].lstrip()
        if chunk:
            yield end - len(chunk), chunk.rstrip()
        if end >= len(text):
            break
        next_offset = max(offset, end - overlap)
        # Preserve the whole word at the start of the overlap. For an
        # uninterrupted token longer than the window, always advance.
        while next_offset > offset and not text[next_offset - 1].isspace() and not text[next_offset].isspace():
            next_offset -= 1
        if next_offset == offset:
            next_offset = end
        while next_offset < len(text) and text[next_offset].isspace():
            next_offset += 1
        offset = next_offset


def publication_date(soup) -> date | None:
    stamp = soup.select_one(
        'meta[property="article:published_time"],meta[itemprop="datePublished"],meta[name="date"],time[datetime]'
    )
    stamp = stamp or soup.select_one("shreddit-post[created-timestamp]")
    try:
        return date.fromisoformat(
            (stamp.get("content") or stamp.get("datetime") or stamp.get("created-timestamp") or "")[:10]
        ) if stamp else None
    except ValueError:
        return None


def extract(raw: bytes, content_type: str) -> tuple[str, date | None, list[tuple[str,str]]]:
    if raw.startswith(b"%PDF-") and "pdf" in content_type:
        import pymupdf
        parts = []
        with pymupdf.open(stream=raw, filetype="pdf") as document:
            for page in list(document)[:110]:
                body = page.get_text(sort=True).strip()
                if len(body) >= 50:
                    parts.append((f"trang {page.number+1}",body))
        return "", None, parts
    if "html" not in content_type and "text/plain" not in content_type:
        raise ValueError("Định dạng tài liệu chưa được hỗ trợ")
    if "text/plain" in content_type:
        return "", None, [("văn bản",raw.decode("utf-8",errors="replace"))]
    soup = BeautifulSoup(raw, "html.parser")
    title = soup.title.get_text(" ",strip=True)[:200] if soup.title else ""
    published = publication_date(soup)
    for tag in soup.find_all(["script","style","nav","iframe","noscript","header","footer","ix:header","ix:hidden"]):
        tag.decompose()
    for table in soup.find_all("table"):
        rows = [" | ".join(cell.get_text(" ",strip=True) for cell in row.find_all(["th","td"],recursive=False))
                for row in table.find_all("tr")]
        table.replace_with("\n" + "\n".join(x for x in rows if x.strip(" |")) + "\n")
    main = soup.find("article") or soup.find("main") or soup.body or soup
    parts = []
    heading = "nội dung"
    buffer = []
    for line in main.get_text("\n",strip=True).splitlines():
        clean = " ".join(line.split())
        if re.match(r"^item\s+(?:\d+[a-z]?|\d+\.\d+)\s*[.\-:]",clean,re.I) and len(clean)<140:
            if buffer:
                parts.append((heading,"\n".join(buffer)))
            heading, buffer = clean, []
        if clean:
            buffer.append(clean)
    if buffer:
        parts.append((heading,"\n".join(buffer)))
    return title, published, parts


def context_document(http: Http, url: str, group: str, as_of: date):
    url = canonical(url)
    if not url or not context_hit(url, group):
        return None
    return read_context_article(http, url, group, as_of, canonical, context_hit, check_source)


class Ingest:
    def __init__(self, http: Http, config):
        self.http, self.config = http, config
        self.allowed = SEC_HOSTS | set(config.allowed_source_hosts)

    def load(self, cik: int, url: str, *, title="", filed=None, report_end=None, kind="web", cap=250):
        url = canonical(url)
        if not url:
            raise ValueError("URL tài liệu không hợp lệ")
        check_source(url, self.allowed)
        host = urlsplit(url).hostname
        sec = host in SEC_HOSTS
        path = urlsplit(url).path
        if sec and not path.lower().startswith(f"/archives/edgar/data/{cik}/"):
            raise ValueError("Hồ sơ SEC không thuộc CIK đã chọn")
        if sec and not self.config.sec_user_agent:
            raise ProviderError("SEC", "thiếu SEC_USER_AGENT")
        raw, headers = self.http.get(url,"document",
            headers={"User-Agent":self.config.sec_user_agent or "FinSight Intelligence V2",
                     "Accept":"text/html,application/pdf,text/plain"}, max_bytes=14_000_000)
        actual_title, page_date, sections = extract(raw,headers.get("content-type","").lower())
        if not sections:
            raise ValueError("Không trích được văn bản. PDF scan cần kiểm tra thủ công.")
        persist = (sec and filed is not None) or host in self.config.persist_source_hosts
        quality = "primary" if sec else "approved" if persist else "external"
        document_id = hashlib.sha256(f"{cik}|{url}".encode()).hexdigest()[:24]
        rows = []
        for section,text in sections:
            for offset,chunk in paragraph_chunks(text,self.config.rag_chunk_size,self.config.rag_chunk_overlap):
                if len(chunk) < 30:
                    continue
                idx = len(rows)
                digest = hashlib.sha256(chunk.encode()).hexdigest()
                rows.append(Evidence(id=f"{document_id}:{idx}",company_cik=cik,document_id=document_id,
                    title=title or actual_title or host,url=url,locator=f"{section} · đoạn {idx+1} · ký tự {offset}",
                    published=filed or page_date,text=chunk,quality=quality,content_hash=digest,
                    kind=kind,report_end=report_end,index=idx,persist=persist))
                if len(rows) >= cap:
                    return rows
        return rows
