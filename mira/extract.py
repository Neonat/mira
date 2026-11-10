"""Text, links and passages from fetched pages (PRD v2 AG06).

Plain code, no model: HTML through the standard-library parser, PDF through
``pypdf``, RSS/Atom through ``xml.etree``. Passages are split at paragraph
boundaries so a citation points at a readable span with character offsets.
"""

from __future__ import annotations

import io
import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date, datetime
from email.utils import parsedate_to_datetime
from html import escape, unescape
from html.parser import HTMLParser
from typing import Literal
from urllib.parse import parse_qsl, urlencode, urldefrag, urljoin, urlsplit

from mira.fetch import FetchedPage

EXTRACTION_VERSION = "extract/2"
ExtractionStatus = Literal["complete", "partial", "failed", "unsupported"]

BLOCK_TAGS = {
    "p", "div", "section", "article", "main", "li", "ul", "ol", "table", "tr", "td", "th", "h1", "h2", "h3",
    "h4", "h5", "h6", "br", "hr", "dd", "dt", "blockquote", "pre", "header", "footer", "aside",
}
SKIP_TAGS = {"script", "style", "noscript", "svg", "template", "iframe", "form", "button", "select"}
CHROME_TAGS = {"nav", "header", "footer"}


@dataclass(frozen=True)
class Link:
    url: str
    text: str
    context: str
    published: date | None = None
    date_source: str | None = None


@dataclass
class Extracted:
    title: str
    status: ExtractionStatus
    pages: list[str]
    links: list[Link] = field(default_factory=list)
    published: date | None = None
    error: str | None = None
    published_basis: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)

    @property
    def text(self) -> str:
        return "\n\n".join(self.pages)


@dataclass(frozen=True)
class PassageSpan:
    number: int
    content: str
    page_number: int | None
    char_start: int
    char_end: int


def extract(page: FetchedPage) -> Extracted:
    try:
        if page.kind == "html":
            result=extract_html(page.body, page.url)
            from mira.publication_routes import is_register_viewer
            if is_register_viewer(page.url):
                result.metadata.update(role='discovery_metadata',representation='viewer')
            return result
        if page.kind == "pdf":
            return extract_pdf(page.body, page.url)
        if page.kind == "json":
            from mira.australia import is_register_api_url, extract_register_json
            if is_register_api_url(page.url):
                return extract_register_json(page.body, page.url)
            return extract_sfc_json(page.body, page.url)
        return extract_feed(page.body, page.url)
    except Exception as exc:  # a broken page must stay visible, never an empty success (AG06)
        return Extracted(title=page.url, status="failed", pages=[], error=f"{type(exc).__name__}: {exc}")


# --- HTML ------------------------------------------------------------------------


class _HtmlText(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.parts: list[str] = []
        self.title = ""
        self.h1 = ""
        self.published: date | None = None
        self.links: list[tuple[str, str, int]] = []
        self._skip = 0
        self._chrome = 0
        self._in_title = False
        self._in_h1 = False
        self._href: str | None = None
        self._link_text: list[str] = []
        self._link_pos = 0
        self.records: list[tuple[int, int]] = []
        self._record_starts: list[tuple[str, int]] = []
        self.article_published: date | None = None
        self._article_depth = 0
        self._article_paragraph_depth = 0
        self.article_paragraphs: list[str] = []
        self._paragraph_depth = 0
        self.paragraphs: list[str] = []
        self._list_depth = 0
        self._table_depth = 0
        self.listing_records: set[tuple[int, int]] = set()

    @property
    def length(self) -> int:
        return sum(len(part) for part in self.parts)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag in ("ul", "ol"):
            self._list_depth += 1
        if tag == "table":
            self._table_depth += 1
        if tag == "article":
            self._article_depth += 1
        if tag == "p":
            self._paragraph_depth += 1
            self.paragraphs.append("")
        if tag == "p" and self._article_depth:
            self._article_paragraph_depth += 1
            self.article_paragraphs.append("")
        if tag == "meta" and (values.get("property") or "").lower() == "article:published_time":
            self.article_published = parse_date(values.get("content") or "")
        if tag in ("tr", "li", "article"):
            self._record_starts.append((tag, self.length))
        if tag in SKIP_TAGS:
            self._skip += 1
        elif tag in CHROME_TAGS:
            self._chrome += 1
        if tag == "title":
            self._in_title = True
        elif tag == "h1":
            self._in_h1 = True
        elif tag == "meta" and self.published is None:
            name = (values.get("property") or values.get("name") or "").lower()
            if name in ("article:published_time", "dcterms.date", "dc.date", "date", "publish-date"):
                self.published = parse_date(values.get("content") or "")
        elif tag == "a" and values.get("href") and not self._skip and not self._chrome:
            self._href = values["href"]
            self._link_text = []
            self._link_pos = self.length
        if tag in BLOCK_TAGS and not self._skip:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag == "p" and self._paragraph_depth:
            self._paragraph_depth -= 1
        if tag == "p" and self._article_paragraph_depth:
            self._article_paragraph_depth -= 1
        if tag == "article" and self._article_depth:
            self._article_depth -= 1
        if tag in ("tr", "li", "article"):
            for index in range(len(self._record_starts) - 1, -1, -1):
                if self._record_starts[index][0] == tag:
                    _, start = self._record_starts.pop(index)
                    record = (start, self.length)
                    self.records.append(record)
                    if (tag == "li" and self._list_depth) or (tag == "tr" and self._table_depth):
                        self.listing_records.add(record)
                    break
        if tag in ("ul", "ol") and self._list_depth:
            self._list_depth -= 1
        if tag == "table" and self._table_depth:
            self._table_depth -= 1
        if tag in SKIP_TAGS:
            self._skip = max(0, self._skip - 1)
        elif tag in CHROME_TAGS:
            self._chrome = max(0, self._chrome - 1)
        if tag == "title":
            self._in_title = False
        elif tag == "h1":
            self._in_h1 = False
        elif tag == "a" and self._href is not None:
            text = " ".join("".join(self._link_text).split())
            url = urldefrag(urljoin(self.base_url, self._href.strip()))[0]
            if text and url.startswith(("http://", "https://")):
                self.links.append((url, text, self._link_pos))
            self._href = None
        if tag in BLOCK_TAGS and not self._skip:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data
        if self._paragraph_depth and self._href is None and not self._skip and not self._chrome:
            self.paragraphs[-1] += data
        if self._article_paragraph_depth and self._href is None and not self._skip and not self._chrome:
            self.article_paragraphs[-1] += data
        if self._skip:
            return
        if self._in_h1:
            self.h1 += data
        if self._href is not None:
            self._link_text.append(data)
        if not self._chrome:
            self.parts.append(data)


def _tidy(text: str) -> str:
    lines = [" ".join(line.split()) for line in text.splitlines()]
    text = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def extract_html(body: bytes, url: str) -> Extracted:
    parser = _HtmlText(url)
    parser.feed(_decode(body))
    parser.close()
    raw = "".join(parser.parts)
    links = []
    dated_records: set[tuple[int, int]] = set()
    seen: set[str] = set()
    for link_url, text, position in parser.links:
        if link_url in seen:
            continue
        seen.add(link_url)
        records = [(start, end) for start, end in parser.records if start <= position < end]
        if records:
            start, end = min(records, key=lambda span: span[1] - span[0])
            context = " ".join(raw[start:end].split())
            dates = {find_date(match.group()) for pattern in DATE_PATTERNS for match in pattern.finditer(context)} - {None}
            published = next(iter(dates)) if len(dates) == 1 else None
            if published and (start, end) in parser.listing_records:
                dated_records.add((start, end))
        else:
            context = " ".join(raw[max(0, position - 160): position + len(text) + 160].split())
            published = None
        links.append(Link(link_url, text, context, published,
                          f"publication date in enclosing table/list record at {url}" if published else None))
    text = _tidy(raw)
    title = " ".join((parser.h1 or parser.title or url).split())
    paragraphs = [" ".join(part.split()) for part in parser.article_paragraphs]
    substantive_article = (parser.article_published is not None and parser.published == parser.article_published
                           and sum(len(part) >= 40 for part in paragraphs) >= 2)
    heading = " ".join((parser.h1 or parser.title).split()).lower()
    index_heading = bool(re.search(r"\b(?:circulars|notices|ordinances|guidelines|consultations|publications|archive|index|disciplinary actions)\b", heading))
    body_text = " ".join(parser.paragraphs)
    substantive_body = (any(len(" ".join(p.split())) >= 80 for p in parser.paragraphs)
                        or bool(re.search(r"\b(?:must|shall|required|requires|should)\b", body_text, re.IGNORECASE)))
    listing = len(dated_records) >= 2 and index_heading and not substantive_body and not substantive_article
    basis = f"publication meta tag in {url}" if parser.published else None
    grounding = {"role": "publication" if substantive_article else "listing" if listing else "unknown",
                 "date_scope": "publication" if substantive_article else "container" if listing else "unknown",
                 "date_basis": basis if substantive_article or listing else None}
    return Extracted(title=title, status="complete" if text else "partial", pages=[text] if text else [],
                     links=links, published=parser.published, published_basis=basis,
                     metadata={"claim_grounding": grounding})


def _decode(body: bytes) -> str:
    head = body[:2048].decode("ascii", errors="ignore").lower()
    match = re.search(r'charset=["\']?([a-z0-9_-]+)', head)
    for encoding in ([match.group(1)] if match else []) + ["utf-8", "cp1252"]:
        try:
            return body.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            continue
    return body.decode("utf-8", errors="replace")


# --- PDF -------------------------------------------------------------------------


def extract_pdf(body: bytes, url: str) -> Extracted:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(body))
    pages = [_tidy(page.extract_text() or "") for page in reader.pages]
    title = ""
    if reader.metadata and reader.metadata.title:
        title = str(reader.metadata.title)
    if not title:
        first = next((page for page in pages if page), "")
        title = first.split("\n", 1)[0][:200] if first else url
    if not any(pages):
        return Extracted(title=title, status="unsupported", pages=[], error="no extractable text (scanned PDF?)")
    status: ExtractionStatus = "complete" if all(pages) else "partial"
    published = None
    basis = None
    # HKMA circulars put the issue date on a standalone line before the salutation.
    # Never treat a filename, PDF creation date, or an effective date in the body as publication.
    if urlsplit(url).hostname == "brdr.hkma.gov.hk" and "Dear" in pages[0][:2000]:
        header = pages[0][:2000].split("Dear", 1)[0]
        dates = [line.strip() for line in header.splitlines()
                 if re.fullmatch(r"\d{1,2}\s+[A-Za-z]+\s+\d{4}", line.strip())]
        if len(set(dates)) == 1:
            published = find_date(dates[0])
            basis = f"HKMA circular header: {dates[0]}" if published else None
    return Extracted(title=title, status=status, pages=pages, published=published, published_basis=basis,
                     metadata={"claim_grounding": {"role": "publication",
                         "date_scope": "publication" if published else "unknown", "date_basis": basis}})


# --- RSS / Atom ------------------------------------------------------------------


def extract_feed(body: bytes, url: str) -> Extracted:
    root = ET.fromstring(body)
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    links: list[Link] = []
    title = (root.findtext("channel/title") or root.findtext("atom:title", namespaces=ns) or url).strip()
    for item in root.iter("item"):
        link_url = (item.findtext("link") or "").strip()
        item_title = " ".join((item.findtext("title") or "").split())
        published = parse_date(item.findtext("pubDate") or "")
        if link_url and item_title:
            summary = " ".join(unescape(re.sub(r"<[^>]+>", " ", item.findtext("description") or "")).split())[:300]
            links.append(Link(urljoin(url, link_url), item_title, summary, published,
                              f"RSS pubDate in {url}" if published else None))
    for entry in root.iter("{http://www.w3.org/2005/Atom}entry"):
        link = entry.find("atom:link", ns)
        link_url = link.get("href", "") if link is not None else ""
        entry_title = " ".join((entry.findtext("atom:title", namespaces=ns) or "").split())
        published = parse_date(entry.findtext("atom:published", namespaces=ns) or "")
        if link_url and entry_title:
            links.append(Link(urljoin(url, link_url), entry_title, "", published,
                              f"Atom published in {url}" if published else None))
    text = "\n".join(f"{link.published or ''} {link.text}".strip() for link in links)
    return Extracted(title=title, status="complete", pages=[text] if text else [], links=links,
                     metadata={"claim_grounding": {"role": "listing", "date_scope": "container", "date_basis": None}})


# --- Dates and passages ----------------------------------------------------------


def extract_sfc_json(body: bytes, url: str) -> Extracted:
    """Read the public SFC service used by its JavaScript publication pages."""
    parts = urlsplit(url)
    match = re.fullmatch(r"/edistributionWeb/api/(circular|news|consultation)/(search|content)", parts.path)
    if parts.hostname != "apps.sfc.hk" or match is None:
        return Extracted(title=url, status="unsupported", pages=[], error="unsupported publication JSON format")
    kind, operation = match.groups()
    data = json.loads(body)
    if operation == "search":
        links = []
        for item in data["items"]:
            if kind == "consultation":
                # The consultation search pairs the paper and its conclusions.
                # Both official routes use cpRefNo; the conclusion PDF is a
                # separate publication with its own title and issue date.
                reference = item.get("cpRefNo")
                title = item.get("cpTitle")
                published = parse_date(item.get("cpIssueDate") or "")
                if reference and title:
                    target = f"https://apps.sfc.hk/edistributionWeb/api/consultation/content?" + urlencode({"refNo": reference, "lang": "EN"})
                    links.append(Link(target, title, title, published, "SFC public publication listing" if published else None))
                    if item.get("ccRefNo") and item.get("ccTitle"):
                        concluded = parse_date(item.get("ccIssueDate") or "")
                        target = f"https://apps.sfc.hk/edistributionWeb/api/consultation/conclusion?" + urlencode({"refNo": reference, "lang": "EN"})
                        links.append(Link(target, item["ccTitle"], item["ccTitle"], concluded,
                                          "SFC public conclusions listing" if concluded else None))
                continue
            reference = item.get("refNo") or item.get("newsRefNo") or item.get("consultationRefNo")
            title = item.get("title")
            if not reference or not title:
                continue
            published = parse_date(item.get("releasedDate") or item.get("issueDate") or "")
            target = f"https://apps.sfc.hk/edistributionWeb/api/{kind}/content?" + urlencode({"refNo": reference, "lang": "EN"})
            links.append(Link(target, title, title, published, "SFC public publication listing" if published else None))
        query = dict(parse_qsl(parts.query))
        page_number = int(query.get("pageNo", "0"))
        page_size = int(query.get("pageSize", "100"))
        if (page_number + 1) * page_size < int(data.get("total", len(data["items"]))):
            query["pageNo"] = str(page_number + 1)
            links.append(Link(parts._replace(query=urlencode(query)).geturl(), "Next SFC publication results", kind))
        # An index supplies discovery links, while claims cite the full publications.
        return Extracted(title=f"SFC {kind} publication index", status="complete", pages=[], links=links,
                         metadata={"claim_grounding": {"role": "listing", "date_scope": "container", "date_basis": None}})
    title = str(data.get("title") or url)
    html = data.get("html")
    if not isinstance(html, str) or not html.strip():
        return Extracted(title=title, status="unsupported", pages=[], error="SFC response has no publication text")
    result = extract_html((f"<h1>{escape(title)}</h1>" + html).encode(), url)
    date_field = "releasedDate" if data.get("releasedDate") else "issueDate"
    result.published = parse_date(data.get(date_field) or "")
    result.published_basis = f"SFC public API {date_field}" if result.published else None
    result.metadata["claim_grounding"] = {"role": "publication",
        "date_scope": "publication" if result.published else "unknown", "date_basis": result.published_basis}
    return result

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}
DATE_PATTERNS = (
    re.compile(r"\b(\d{1,2})\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(\d{4})\b", re.I),
    re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b"),
)


def find_date(text: str) -> date | None:
    match = DATE_PATTERNS[0].search(text)
    if match:
        try:
            return date(int(match.group(3)), MONTHS[match.group(2)[:3].lower()], int(match.group(1)))
        except ValueError:
            pass
    match = DATE_PATTERNS[1].search(text)
    if match:
        try:
            return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except ValueError:
            pass
    return None


def parse_date(value: str) -> date | None:
    value = value.strip()
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        pass
    try:
        return parsedate_to_datetime(value).date()
    except (TypeError, ValueError, IndexError):
        return find_date(value)


def split_passages(extracted: Extracted, max_chars: int = 1200) -> list[PassageSpan]:
    """Split each page at blank lines, packing whole paragraphs up to ``max_chars``.

    Character offsets are into ``extracted.text``; page numbers are set for PDFs.
    """
    ranges: list[tuple[int | None, int, int]] = []
    offset = 0
    is_pdf = len(extracted.pages) > 1
    for page_index, page in enumerate(extracted.pages):
        page_number = page_index + 1 if is_pdf else None
        chunk: tuple[int, int] | None = None
        for match in re.finditer(r"\S[\s\S]*?(?=\n\s*\n|\Z)", page):
            start, end = match.start(), match.end()
            if chunk and end - chunk[0] > max_chars:
                ranges.append((page_number, offset + chunk[0], offset + chunk[1]))
                chunk = None
            while end - start > max_chars:
                cut = page.rfind(" ", start, start + max_chars)
                cut = cut if cut > start else start + max_chars
                ranges.append((page_number, offset + start, offset + cut))
                start = cut + 1
            chunk = (chunk[0], end) if chunk else (start, end)
        if chunk:
            ranges.append((page_number, offset + chunk[0], offset + chunk[1]))
        offset += len(page) + 2
    text = extracted.text
    spans = []
    for page_number, start, end in ranges:
        content = text[start:end].strip()
        if content:
            spans.append(PassageSpan(len(spans) + 1, content, page_number, start, end))
    return spans
