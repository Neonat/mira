"""Reader-facing publication destinations; never rewrite stored evidence URLs."""
import re
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit


_SFC_READER_ROUTES = {
    "/edistributionWeb/api/circular/content": ("EC", "/edistributionWeb/gateway/EN/circular/doc"),
    "/edistributionWeb/api/news/content": ("PR", "/edistributionWeb/gateway/EN/news-and-announcements/news/doc"),
}


def reader_source_url(url: str) -> str:
    """Map verified English SFC content endpoints to the same public document.

    Other endpoints, languages and ambiguous parameters retain their original
    destination. This projection does not change acquisition or evidence identity.
    """
    try:
        parts = urlsplit(url)
        route = _SFC_READER_ROUTES.get(parts.path)
        if parts.scheme != "https" or parts.netloc.lower() != "apps.sfc.hk" or route is None:
            return url
        query = parse_qs(parts.query, keep_blank_values=True, max_num_fields=2)
    except ValueError:
        return url
    if set(query) != {"refNo", "lang"} or query["lang"] != ["EN"] or len(query["refNo"]) != 1:
        return url
    prefix, path = route
    reference = query["refNo"][0]
    if not re.fullmatch(r"[0-9]{2}" + prefix + r"[0-9]+", reference):
        return url
    return urlunsplit(("https", "apps.sfc.hk", path, urlencode({"refNo": reference}), parts.fragment))
