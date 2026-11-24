"""Links and safe excerpts for evidence already associated with a report."""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from html import escape
import re
from urllib.parse import quote, urldefrag, urlsplit

from bs4 import BeautifulSoup, NavigableString

from finsight.financials import fact_id
from finsight.schema import Fact


def encode_fragment(text: str) -> str:
    return quote(text,safe="").replace("-","%2D")


def evidence_link(url: str, excerpt: str = "", *, kind: str = "", locator: str = "") -> tuple[str,str]:
    if urlsplit(url).scheme != "https":
        return "", "unavailable"
    if kind == "pdf" or urlsplit(url).path.lower().endswith(".pdf"):
        page = re.match(r"trang\s+(\d+)",locator,re.I)
        return (urldefrag(url)[0]+"#page="+page[1],"page") if page else (url,"document")
    words = excerpt.split()
    if kind != "xbrl" and len(words) >= 3:
        parts = [" ".join(words)] if len(words) <= 24 else [" ".join(words[:9])," ".join(words[-9:])]
        return urldefrag(url)[0]+"#:~:text="+",".join(map(encode_fragment,parts)), "text"
    return url,"document"


def marked_excerpt(body: str, excerpt: str) -> str:
    """Find the quoted tokens across line breaks and escape all source markup."""
    words = excerpt.split()
    if not words:
        return escape(body)
    match = re.search(r"\s+".join(map(re.escape,words)),body,re.I)
    if not match:
        return escape(body)
    start,end = match.span()
    return escape(body[:start])+"<mark>"+escape(body[start:end])+"</mark>"+escape(body[end:])


def fact_evidence_id(fact: Fact) -> str:
    return "X:" + sha256(fact_id(fact).encode()).hexdigest()[:24]


def evidence_fact(report: dict, evidence_id: str) -> Fact | None:
    revisions = [entry[key] for entry in report.get("changes", []) for key in ("prior", "current")]
    for item in [*report["facts"], *revisions]:
        fact = Fact.model_validate(item)
        if evidence_id == fact_evidence_id(fact):
            return fact
    return None


def local_name(tag):
    return (tag.name or "").rsplit(":",1)[-1]


@dataclass
class InlineFactLocation:
    anchor: str
    rendered: str
    cells: list[str]
    selected_cell: int | None
    text_fragment: str | None = None


def inline_fact_text_fragment(soup, target, rendered: str) -> str | None:
    """Point to the verified occurrence, even if the number is repeated later."""
    hidden_tags = {"ix:hidden", "ix:header", "script", "style", "hidden"}
    for tag in soup.find_all(
        lambda tag: tag.name in hidden_tags or tag.has_attr("hidden")
        or re.search(r"(?:^|;)\s*(?:display\s*:\s*none|visibility\s*:\s*hidden)\b",
                     tag.get("style", ""), re.I)
    ):
        if tag.parent:
            tag.decompose()
    if not target.parent or not rendered:
        return None

    before = []
    for node in soup.descendants:
        if node is target:
            break
        if type(node) is NavigableString and (part := " ".join(node.split())):
            before.append(part)
    else:
        return None

    preceding = " ".join(before).casefold()
    term = rendered.casefold()
    last = preceding.rfind(term)
    if last == -1:
        return encode_fragment(rendered)

    # A short, unique start phrase after the previous occurrence keeps the
    # range from selecting the same value in a different row or statement.
    tail = preceding[last + len(term):][-1200:]
    visible = " ".join(" ".join(part.split()) for part in soup.stripped_strings).casefold()
    for part in reversed(before):
        folded = part.casefold()
        if len(folded) > len(tail) or not tail.endswith(folded):
            break
        if 3 <= len(part.split()) <= 16 and len(part) <= 140 and visible.count(folded) == 1:
            return encode_fragment(part) + "," + encode_fragment(rendered)
        tail = tail[:-len(folded)].rstrip()
    return None


def inline_fact_location(raw: bytes, fact: Fact) -> InlineFactLocation | None:
    """Locate the consolidated iXBRL value by concept, unit, period and numeric value."""
    soup = BeautifulSoup(raw,"html.parser")
    contexts = {}
    units = {}
    for tag in soup.find_all(["xbrli:context","context","xbrli:unit","unit"],id=True):
        if local_name(tag)=="unit":
            measures = [x.get_text(strip=True).rsplit(":",1)[-1] for x in tag.find_all(
                lambda x:local_name(x)=="measure")]
            units[tag["id"]] = "/".join(measures)
            continue
        if tag.find(lambda x:local_name(x) in {"segment","scenario","explicitmember","typedmember"}):
            continue
        dates = {local_name(x):x.get_text(strip=True) for x in tag.find_all(
            lambda x:local_name(x) in {"startdate","enddate","instant"})}
        contexts[tag["id"]] = (dates.get("startdate"),dates.get("enddate") or dates.get("instant"))
    expected_period = (str(fact.start) if fact.start else None,str(fact.end))
    matches = []
    for tag in soup.find_all(["ix:nonfraction","nonfraction"],id=True):
        if (tag.get("name","").casefold()!=fact.concept.casefold()
                or contexts.get(tag.get("contextref"))!=expected_period
                or units.get(tag.get("unitref"))!=fact.unit
                or tag.find_parent(["ix:hidden","hidden","ix:header"])):
            continue
        rendered = tag.get_text(strip=True)
        try:
            value = Decimal(rendered.replace(",","").replace(" ","")) * Decimal(10)**int(tag.get("scale",0))
            if tag.get("sign")=="-":
                value *= -1
        except (InvalidOperation,ValueError,OverflowError):
            continue
        if value == Decimal(str(fact.value)):
            cell = tag.find_parent(["td", "th"])
            row = cell.find_parent("tr") if cell else None
            cells = row.find_all(["td", "th"], recursive=False) if row else []
            selected = next((index for index, candidate in enumerate(cells) if candidate is cell), None)
            texts = [" ".join(candidate.stripped_strings)[:500] for candidate in cells]
            matches.append((InlineFactLocation(tag["id"], rendered, texts, selected), tag))
    if not matches:
        return None
    chosen, target = next((match for match in matches if match[0].selected_cell is not None), matches[0])
    chosen.text_fragment = inline_fact_text_fragment(soup, target, chosen.rendered)
    return chosen


def inline_fact_anchor(raw: bytes, fact: Fact) -> str | None:
    location = inline_fact_location(raw, fact)
    return location.anchor if location else None

def highlighted_pdf_page(raw: bytes, page_number: int, passage: str) -> bytes:
    """Return the cited original PDF page with a highlight on one unambiguous match."""
    import pymupdf

    phrase = " ".join(passage.split())
    if not raw.startswith(b"%PDF-") or not phrase:
        raise ValueError("Không xác định được đoạn trích PDF")
    with pymupdf.open(stream=raw, filetype="pdf") as source:
        if source.needs_pass or not 1 <= page_number <= source.page_count:
            raise ValueError("Không tìm thấy trang PDF")
        original = source[page_number - 1]
        normalized = " ".join(original.get_text().split()).casefold()
        if normalized.count(phrase.casefold()) != 1:
            raise ValueError("Không định vị được một đoạn trích duy nhất trên trang PDF")
        with pymupdf.open() as excerpt:
            excerpt.insert_pdf(source, from_page=page_number - 1, to_page=page_number - 1,
                               links=False, annots=False, widgets=False)
            page = excerpt[0]
            areas = page.search_for(phrase, quads=True)
            if not areas:
                raise ValueError("Không định vị được đoạn trích trên trang PDF")
            page.add_highlight_annot(areas).update()
            return excerpt.tobytes(garbage=4, deflate=True)
