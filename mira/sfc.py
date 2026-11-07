"""Requests for the SFC's public publication-search service."""

from urllib.parse import parse_qs, urlsplit

SEARCH_KINDS = ("circular", "news", "consultation")


def search_payload(url: str) -> dict[str, object] | None:
    parts = urlsplit(url)
    if parts.hostname != "apps.sfc.hk" or parts.path not in (
        f"/edistributionWeb/api/{kind}/search" for kind in SEARCH_KINDS
    ):
        return None
    query = parse_qs(parts.query)
    year = query.get("year", ["all"])[0]
    category = query.get("category", ["all"])[0]
    payload = {
        "lang": "EN", "category": category,
        "year": "all" if year == "all" else int(year), "month": "all",
        "cntCatKeySeq": "all", "pageNo": max(0, int(query.get("pageNo", ["0"])[0])),
        "pageSize": min(100, max(1, int(query.get("pageSize", ["100"])[0]))),
        "sort": {"field": "issueDate", "order": "desc"},
    }
    if "/consultation/" in parts.path and category == "all":
        payload.pop("category")
    return payload
