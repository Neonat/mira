"""Identity of verified fixed Australian Register publication representations."""
from __future__ import annotations

import re
from datetime import date
from urllib.parse import urlsplit

_ROUTE = re.compile(
    r'/([A-Za-z0-9]{1,64})/(\d{4}-\d{2}-\d{2})/(\d{4}-\d{2}-\d{2})'
    r'/text/original/(pdf|epub/OEBPS/document_1/document_1\.html)\Z'
)


def register_publication(url: str) -> dict[str, str] | None:
    """Recognize only the verified fixed PDF and HTML routes, including fragments."""
    try:
        if not isinstance(url, str) or any(ord(char) <= 32 or ord(char) == 127 for char in url):
            return None
        parts = urlsplit(url)
        if (parts.scheme != 'https' or parts.hostname != 'www.legislation.gov.au'
                or parts.username is not None or parts.password is not None
                or parts.port not in (None, 443) or '?' in url.split('#', 1)[0]):
            return None
        match = _ROUTE.fullmatch(parts.path)
        if not match:
            return None
        title_id, start, retrospective_start, representation = match.groups()
        date.fromisoformat(start)
        date.fromisoformat(retrospective_start)
        return {'title_id': title_id, 'start': start, 'retrospective_start': retrospective_start,
                'representation': 'pdf' if representation == 'pdf' else 'html'}
    except (ValueError, TypeError, AttributeError):
        return None


def register_document_key(url: str) -> str | None:
    publication = register_publication(url)
    if publication is None:
        return None
    return '/'.join(publication[key] for key in ('title_id', 'start', 'retrospective_start'))


def is_publication_pdf(url: str) -> bool:
    publication = register_publication(url)
    return publication is not None and publication['representation'] == 'pdf'


def is_register_viewer(url: str) -> bool:
    """Known public title/viewer routes are discovery pages, not legal text."""
    try:
        parts=urlsplit(url)
        if (parts.scheme!='https' or parts.hostname!='www.legislation.gov.au'
                or parts.username is not None or parts.password is not None
                or parts.port not in (None,443)):
            return False
        return re.fullmatch(r'/[A-Za-z0-9]{1,64}(?:/(?:latest|\d{4}-\d{2}-\d{2})(?:/text)?)?/?',parts.path) is not None
    except (ValueError,TypeError):
        return False
