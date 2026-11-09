"""Bounded discovery metadata from the Australian Federal Register API.

The returned pages describe metadata, not the legislation itself. Public links
are constructed only from validated identifiers and dates, never API URLs.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime
from urllib.parse import parse_qsl, urlsplit

from mira.extract import Extracted, Link

_ID = re.compile(r'[A-Za-z0-9]{1,64}\Z')
_MAX_BYTES = 15_000_000
_MAX_RECORDS = 1000


def is_register_api_url(url: str) -> bool:
    try:
        p = urlsplit(url)
        if (p.scheme != 'https' or p.hostname != 'api.prod.legislation.gov.au'
                or p.username is not None or p.password is not None
                or p.port not in (None, 443) or p.fragment):
            return False
        if re.fullmatch(r'/v1/Titles/[A-Za-z0-9]{1,64}', p.path):
            return True
        if p.path != '/v1/Versions':
            return False
        query = parse_qsl(p.query, keep_blank_values=True, max_num_fields=50)
        return sum(k == '$filter' and bool(v.strip()) for k, v in query) == 1
    except (ValueError, TypeError):
        return False


def _date(value: object) -> date | None:
    if value is None:
        return None
    if not isinstance(value, str) or not re.fullmatch(
        r'\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?)?', value
    ):
        raise ValueError('invalid date')
    return datetime.fromisoformat(value.replace('Z', '+00:00')).date()


def _identifier(value: object) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ValueError('invalid identifier')
    return value


def _optional_string(record: dict, key: str) -> str | None:
    value = record.get(key)
    if value is not None and not isinstance(value, str):
        raise ValueError(f'invalid {key}')
    return value


def extract_register_json(body: bytes, url: str) -> Extracted:
    if not is_register_api_url(url):
        return Extracted(title=url, status='unsupported', pages=[], error='unsupported Register API URL')
    try:
        if not isinstance(body, bytes) or len(body) > _MAX_BYTES:
            raise ValueError('invalid or oversized body')
        data = json.loads(body)
        if not isinstance(data, dict):
            raise ValueError('expected object')
        title_route = '/v1/Titles/' in urlsplit(url).path
        if title_route:
            title_id = _identifier(data.get('id'))
            if title_id != urlsplit(url).path.rsplit('/', 1)[-1]:
                raise ValueError('title identity mismatch')
            name = _optional_string(data, 'name') or title_id
            versions = data.get('versions')
            if versions is None:
                versions = []
        else:
            name = 'Federal Register versions'
            versions = data.get('value')
        if not isinstance(versions, list) or len(versions) > _MAX_RECORDS:
            raise ValueError('invalid versions collection')
        links: list[Link] = []
        lines = ['Federal Register discovery metadata only; not legal text.', f'Instrument: {name}']
        for v in versions:
            if not isinstance(v, dict):
                raise ValueError('invalid version')
            ident = _identifier(v.get('titleId'))
            if title_route and ident != title_id:
                raise ValueError('version identity mismatch')
            register_id = v.get('registerId')
            if register_id is not None:
                _identifier(register_id)
            start = _date(v.get('start'))
            retrospective = _date(v.get('retrospectiveStart'))
            registered = _date(v.get('registeredAt'))
            for key in ('end', 'retrospectiveEnd'):
                _date(v.get(key))
            label = _optional_string(v, 'name') or name
            compilation = _optional_string(v, 'compilationNumber')
            documents = v.get('documents')
            if documents is not None and (not isinstance(documents, list) or len(documents) > _MAX_RECORDS):
                raise ValueError('invalid documents')
            context = (f'Instrument {ident}; compilation {compilation or "unknown"}; register ID '
                       f'{register_id or "unknown"}; effective start {start or "unknown"}; '
                       f'retrospective start {retrospective or "unknown"}; registeredAt {registered or "unknown"}. '
                       'Discovery metadata only; not legal text.')
            lines.append(context)
            basis = f'Federal Register API registeredAt in {url}' if registered else None
            viewer_index=len(links)
            if start:
                prefix = f'https://www.legislation.gov.au/{ident}/{start.isoformat()}'
                links.append(Link(prefix + '/text', f'{label} dated viewer', context + ' Representation: viewer.', registered, basis))
            for doc in documents or []:
                if not isinstance(doc, dict):
                    raise ValueError('invalid document')
                for key in ('titleId', 'registerId'):
                    if doc.get(key) is not None:
                        _identifier(doc[key])
                if doc.get('titleId') not in (None, ident) or doc.get('registerId') not in (None, register_id):
                    raise ValueError('document identity mismatch')
                for key in ('type', 'format', 'fileName'):
                    _optional_string(doc, key)
                for key in ('volumeNumber', 'rectificationVersionNumber', 'uniqueTypeNumber'):
                    if doc.get(key) is not None and type(doc[key]) is not int:
                        raise ValueError(f'invalid {key}')
                _optional_string(doc, 'versionType')
                if (start and doc.get('type') == 'Primary' and doc.get('format') in ('Pdf','Epub')
                        and all(doc.get(key) in (None, 0) for key in
                                ('volumeNumber', 'rectificationVersionNumber', 'uniqueTypeNumber'))
                        and doc.get('versionType') is None):
                    date_part = (retrospective or start).isoformat()
                    suffix='pdf' if doc['format']=='Pdf' else 'epub/OEBPS/document_1/document_1.html'
                    target = prefix + f'/{date_part}/text/original/{suffix}'
                    links.append(Link(target, f'{label} {doc["format"]}', context + f' Representation: primary {doc["format"]}.', registered, basis))
            # A viewer is a fallback discovery destination, never a replacement
            # for a known full publication representation.
            if start and len(links)>viewer_index+1:
                del links[viewer_index]
        result = Extracted(title=name, status='complete', pages=['\n'.join(lines)], links=links)
        result.metadata = {'native_record': data, 'role': 'discovery_metadata'}
        return result
    except (ValueError, TypeError, UnicodeDecodeError, RecursionError) as exc:
        return Extracted(title=url, status='failed', pages=[], error=f'invalid Register metadata: {exc}')
