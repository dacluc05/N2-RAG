"""Read public news articles and posts from their original URLs."""

from datetime import date
import hashlib
import json
import re
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from finsight.transport import DocumentRedirect

ARTICLE_TYPES = {"Article", "NewsArticle", "ReportageNewsArticle", "AnalysisNewsArticle",
                 "BlogPosting", "SocialMediaPosting", "DiscussionForumPosting"}
BODY_SELECTORS = (
    '[itemprop="articleBody"]', '[data-testid="article-body"]',
    '.ArticleBody-articleBody', '.RichTextStoryBody', 'article',
)
DATE_SELECTORS = (
    'meta[property="article:published_time"]', '[itemprop="datePublished"]',
    'meta[name="pubdate"]', 'meta[name="date"]',
)


def _nodes(value):
    if isinstance(value, list):
        for item in value:
            yield from _nodes(item)
    elif isinstance(value, dict):
        yield value
        for key in ("@graph", "mainEntity"):
            yield from _nodes(value.get(key))


def _stamp(value):
    if isinstance(value, str):
        try:
            return date.fromisoformat(value.strip()[:10])
        except ValueError:
            pass
    return None


def _publication(soup, schema, group):
    for selector in DATE_SELECTORS:
        for tag in soup.select(selector):
            stamp = _stamp(tag.get("content") or tag.get("datetime") or tag.get_text(strip=True))
            if stamp:
                return stamp
    for item in schema:
        stamp = _stamp(item.get("datePublished"))
        if stamp:
            return stamp
    root = soup.select_one("shreddit-post[created-timestamp]") if group == "social" else soup.select_one("article")
    if root:
        time = root.select_one("time[datetime]")
        return _stamp(root.get("created-timestamp") or (time.get("datetime") if time else None))
    return None


def _structured_article(soup, url, canonical):
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(script.get_text() or "")
        except (ValueError, RecursionError):
            continue
        for item in _nodes(data):
            kinds = item.get("@type")
            kinds = kinds if isinstance(kinds, list) else [kinds]
            if not any(isinstance(kind, str) and kind.rsplit("/", 1)[-1] in ARTICLE_TYPES for kind in kinds):
                continue
            page = item.get("url") or item.get("mainEntityOfPage")
            if isinstance(page, dict):
                page = page.get("@id")
            if isinstance(page, str) and canonical(urljoin(url, page)).split("?")[0].rstrip("/") != url.split("?")[0].rstrip("/"):
                continue
            yield item


def _article_text(soup, schema, group):
    selectors = ('[slot="text-body"]', '[data-testid="tweetText"]',
                 '[itemprop="articleBody"]') if group == "social" else BODY_SELECTORS
    candidates = []
    for selector in selectors:
        for body in soup.select(selector):
            for extra in body.select("script,style,nav,footer,aside,form,[hidden],[aria-hidden='true']"):
                extra.decompose()
            if group == "social":
                candidates.append(body.get_text(" ", strip=True))
                continue
            paragraphs = [p.get_text(" ", strip=True) for p in body.find_all("p")]
            text = " ".join(dict.fromkeys(p for p in paragraphs if len(p) >= 35))
            if not text and selector != "article":
                text = body.get_text(" ", strip=True)
            candidates.append(text)
    if group == "news":
        for item in schema:
            body = item.get("articleBody")
            if isinstance(body, str):
                candidates.append(BeautifulSoup(body, "html.parser").get_text(" ", strip=True))
    candidates = [" ".join(body.split()) for body in candidates]
    minimum = 20 if group == "social" else 50
    return next((body[:2600] for body in candidates if len(body) >= minimum), "")


def read_context_article(http, url, group, as_of, canonical, context_hit, check_source):
    source_url = url
    seen = set()
    for _ in range(4):
        if not url or url in seen or not context_hit(url, group):
            raise ValueError("Chuyển hướng ra ngoài nguồn bài được hỗ trợ")
        seen.add(url)
        host = urlsplit(url).hostname
        check_source(url, {host})
        try:
            raw, headers = http.get(url, "document", headers={
                "Accept": "text/html,application/xhtml+xml",
                "User-Agent": "FinSight Intelligence (public article reader)",
            }, max_bytes=5_000_000, attempts=1, report_redirect=True)
        except DocumentRedirect as exc:
            if not exc.location:
                raise ValueError("Chuyển hướng thiếu địa chỉ bài gốc") from exc
            url = canonical(urljoin(url, exc.location))
            continue
        break
    else:
        raise ValueError("Quá nhiều chuyển hướng khi mở bài gốc")

    if not any(kind in headers.get("content-type", "").lower() for kind in ("html", "xhtml")):
        raise ValueError("Bài gốc không trả về HTML")
    soup = BeautifulSoup(raw, "html.parser")
    schema = list(_structured_article(soup, url, canonical))
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    if re.search(r"^(?:access denied|just a moment|verify you are human|sign in|log in)(?:\b|$)", title, re.I):
        raise ValueError("Trang yêu cầu xác thực hoặc đăng nhập")
    if any(item.get("isAccessibleForFree") in (False, "false", "False") for item in schema):
        raise ValueError("Bài gốc yêu cầu quyền truy cập")
    published = _publication(soup, schema, group)
    if not published:
        raise ValueError("Bài gốc thiếu ngày công bố")
    if published > as_of:
        raise ValueError("Đăng sau ngày chốt")
    body = _article_text(soup, schema, group)
    if not body:
        raise ValueError("Bài gốc không có nội dung đọc được trong HTML trả về")
    return {
        "id": hashlib.sha256(source_url.encode()).hexdigest()[:16],
        "group": group,
        "title": (title or host)[:180],
        "url": url,
        "published": published.isoformat(),
        "text": body,
        "source_type": "original",
    }
