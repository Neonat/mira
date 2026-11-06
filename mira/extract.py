"""Text, links and passages from fetched pages (PRD v2 AG06).

Plain code, no model: HTML through the standard-library parser, PDF through
``pypdf``, RSS/Atom through ``xml.etree``. Passages are split at paragraph
boundaries so a citation points at a readable span with character offsets.
"""

from __future__ import annotations

import io
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date, datetime
from email.utils import parsedate_to_datetime
from html import unescape
from html.parser import HTMLParser
from typing import Literal
from urllib.parse import urldefrag, urljoin, urlsplit

from mira.fetch import FetchedPage

EXTRACTION_VERSION = "extract/1"
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
            return extract_html(page.body, page.url)
        if page.kind == "pdf":
            return extract_pdf(page.body, page.url)
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

    @property
    def length(self) -> int:
        return sum(len(part) for part in self.parts)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
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
    seen: set[str] = set()
    for link_url, text, position in parser.links:
        if link_url in seen:
            continue
        seen.add(link_url)
        context = " ".join(raw[max(0, position - 160): position + len(text) + 160].split())
        links.append(Link(link_url, text, context, find_date(context)))
    text = _tidy(raw)
    title = " ".join((parser.h1 or parser.title or url).split())
    return Extracted(title=title, status="complete" if text else "partial", pages=[text] if text else [],
                     links=links, published=parser.published,
                     published_basis=f"publication meta tag in {url}" if parser.published else None)


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
    return Extracted(title=title, status=status, pages=pages, published=published, published_basis=basis)


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
    return Extracted(title=title, status="complete", pages=[text] if text else [], links=links)


# --- Dates and passages ----------------------------------------------------------

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
