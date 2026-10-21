"""Local HTML/PDF ingestion. No database credentials required."""
import argparse
import hashlib
import http.client
import ipaddress
import json
import re
import socket
import ssl
import sys
import time
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

VERSION = 'html-v1'
HOSTS = {'www.mas.gov.sg', 'mas.gov.sg'}
USER_AGENT = 'MiraResearch/0.1'
MAX_BYTES = 2_000_000


class IngestionError(ValueError):
    pass


def checked_url(url):
    parts = urlsplit(url)
    if (parts.scheme != 'https' or parts.hostname not in HOSTS
            or parts.username or parts.password or parts.port not in (None, 443)):
        raise IngestionError('Only HTTPS URLs on the configured MAS hosts are allowed.')
    return urlunsplit((parts.scheme, parts.netloc, parts.path or '/', parts.query, ''))


class PublicHTTPS(http.client.HTTPSConnection):
    """Connect to a validated IP while retaining hostname TLS verification."""
    def connect(self):
        addresses = socket.getaddrinfo(self.host, 443, type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
            raise IngestionError('Host resolved to a non-public address.')
        # Pin the validated numeric IP; do not resolve the hostname a second time.
        raw = socket.create_connection((addresses[0][4][0], 443), self.timeout)
        try:
            self.sock = self._context.wrap_socket(raw, server_hostname=self.host)
        except Exception:
            raw.close()
            raise


def request(url):
    url = checked_url(url)
    parts = urlsplit(url)
    connection = PublicHTTPS(parts.hostname, timeout=15, context=ssl.create_default_context())
    try:
        connection.request('GET', urlunsplit(('', '', parts.path, parts.query, '')),
                           headers={'User-Agent': USER_AGENT, 'Accept-Encoding': 'identity'})
        response = connection.getresponse()
        data = response.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise IngestionError('Response exceeds the 2 MB limit.')
        if response.getheader('Content-Encoding', 'identity').lower() != 'identity':
            raise IngestionError('Unexpected compressed response.')
        return response.status, dict((k.lower(), v) for k, v in response.getheaders()), data
    finally:
        connection.close()


def robots_for(url):
    parts = urlsplit(url)
    robots_url = urlunsplit((parts.scheme, parts.netloc, '/robots.txt', '', ''))
    for _ in range(4):
        status, headers, data = request(robots_url)
        if status in (301, 302, 303, 307, 308) and headers.get('location'):
            robots_url = checked_url(urljoin(robots_url, headers['location']))
            continue
        if status != 200:
            raise IngestionError(f'Cannot verify robots policy (HTTP {status}); fetch stopped.')
        robots_text = data.decode('utf-8', errors='replace')
        if not re.search(r'^\s*user-agent\s*:', robots_text, re.I | re.M):
            raise IngestionError('Unrecognised robots response; fetch stopped.')
        policy = RobotFileParser()
        policy.parse(robots_text.splitlines())
        return policy
    raise IngestionError('Too many robots redirects.')


def fetch(url):
    policies = {}
    for _ in range(5):
        url = checked_url(url)
        host = urlsplit(url).netloc
        if host not in policies:
            policies[host] = robots_for(url)
        policy = policies[host]
        if not policy.can_fetch(USER_AGENT, url):
            raise IngestionError('robots.txt does not permit this URL.')
        delay = max(1, policy.crawl_delay(USER_AGENT) or 0)
        rate = policy.request_rate(USER_AGENT)
        if rate and rate.requests:
            delay = max(delay, rate.seconds / rate.requests)
        if delay > 30:
            raise IngestionError('Source requires a delay above this single-page tool limit.')
        time.sleep(delay)
        status, headers, data = request(url)
        if status in (301, 302, 303, 307, 308) and headers.get('location'):
            url = checked_url(urljoin(url, headers['location']))
            continue
        if status != 200:
            raise IngestionError(f'Page fetch failed (HTTP {status}).')
        content_type = headers.get('content-type', '')
        if content_type.split(';')[0].strip().lower() not in ('text/html', 'application/xhtml+xml'):
            raise IngestionError('Only HTML is supported in this first slice; PDF is not yet implemented.')
        charset = re.search(r'charset=["\']?([^;\s"\']+)', content_type, re.I)
        return url, data.decode(charset.group(1) if charset else 'utf-8'), 'live'
    raise IngestionError('Too many page redirects.')


class PageParser(HTMLParser):
    SKIP = {'script', 'style', 'nav', 'footer', 'header', 'aside', 'noscript', 'template'}
    VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.main = []
        self.body = []
        self.title = []
        self.heading = []
        self.metadata = {}
        self.has_main = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'meta':
            key = attrs.get('property', attrs.get('name', '')).lower()
            self.metadata[key] = attrs.get('content', '')
        if tag not in self.VOID:
            self.stack.append(tag)
        if tag in ('main', 'article'):
            self.has_main = True
        if tag in ('p', 'div', 'li', 'h1', 'h2', 'h3', 'br', 'section'):
            self.add_text('\n')

    def handle_endtag(self, tag):
        if tag in ('p', 'div', 'li', 'h1', 'h2', 'h3', 'section'):
            self.add_text('\n')
        if tag in self.stack:
            self.stack = self.stack[:len(self.stack) - 1 - self.stack[::-1].index(tag)]

    def add_text(self, text):
        if any(tag in self.SKIP for tag in self.stack):
            return
        if 'body' in self.stack:
            self.body.append(text)
        if 'main' in self.stack or 'article' in self.stack:
            self.main.append(text)

    def handle_data(self, data):
        if 'title' in self.stack:
            self.title.append(data)
        if 'h1' in self.stack:
            self.heading.append(data)
        self.add_text(data)


def clean(parts):
    return '\n'.join(line for raw in ''.join(parts).splitlines()
                     if (line := ' '.join(raw.split())))


def passages(text, size=1000):
    if size < 50:
        raise IngestionError('Passage size must be at least 50 characters.')
    result = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            boundary = text.rfind(' ', start + size // 2, end)
            if boundary > start:
                end = boundary
        result.append({'passage_number': len(result) + 1, 'content': text[start:end],
                       'char_start': start, 'char_end': end, 'extraction_version': VERSION})
        start = end
        while start < len(text) and text[start].isspace():
            start += 1
    return result


def extract(html, url, origin='fixture', size=1000):
    url = checked_url(url)
    parser = PageParser()
    parser.feed(html)
    title = clean(parser.heading) or parser.metadata.get('og:title') or clean(parser.title)
    text = clean(parser.main if parser.has_main else parser.body)
    blocked_title = re.search(
        r'service.*unavailable|access denied|request rejected|just a moment|verify.*human|captcha',
        title or '', re.I)
    if blocked_title:
        raise IngestionError('Source returned a service-unavailable or access-challenge page, not evidence.')
    if not title or len(text) < 80:
        raise IngestionError('No usable article text/title; page may require JavaScript or be blocked.')
    raw_date = parser.metadata.get('article:published_time') or parser.metadata.get('datepublished')
    published = None
    if raw_date:
        try:
            date = datetime.fromisoformat(raw_date.replace('Z', '+00:00'))
            # Do not invent a time zone or substitute retrieval time.
            if date.tzinfo is not None:
                published = date.isoformat()
        except ValueError:
            pass
    digest = hashlib.sha256(text.encode('utf-8')).hexdigest()
    return {
        'schema_version': 1,
        'source_key': 'mas',
        'document': {'canonical_url': url, 'title': title, 'document_type': 'regulation'},
        'document_version': {
            'content_sha256': digest, 'source_url': url, 'title': title,
            'published_at': published, 'retrieved_at': datetime.now(timezone.utc).isoformat(),
            'extraction_status': 'partial', 'extracted_text': text, 'extraction_version': VERSION,
            'metadata': {'origin': origin, 'raw_publication_date': raw_date,
                         'raw_html_sha256': hashlib.sha256(html.encode('utf-8')).hexdigest(),
                         'date_warning': None if published else 'Publication date/timezone not established.',
                         'extraction_warning': 'HTML-only extraction; linked PDFs and completeness are not assessed.'}},
        'passages': passages(text, size),
    }


def save(bundle, directory):
    directory.mkdir(parents=True, exist_ok=True)
    # Include metadata (excluding observation time) so date/title corrections survive.
    stable = json.loads(json.dumps(bundle))
    del stable['document_version']['retrieved_at']
    key = hashlib.sha256(json.dumps(stable, sort_keys=True).encode()).hexdigest()
    path = directory / f'{key}.json'
    from mira.storage import atomic_bytes
    payload = (json.dumps(bundle, indent=2, ensure_ascii=False) + '\n').encode()
    if path.exists():
        previous = json.loads(path.read_text())
        previous['document_version'].pop('retrieved_at', None)
        if previous != stable:
            raise IngestionError('Existing snapshot is inconsistent; restore it before retrying.')
        return path, 'unchanged'
    # Concurrent attempts may differ only in retrieved_at. The batch lock serialises
    # normal use; direct callers may safely observe the already-published snapshot.
    try:
        created = atomic_bytes(path, payload, immutable=True)
    except ValueError:
        previous = json.loads(path.read_text())
        previous['document_version'].pop('retrieved_at', None)
        if previous != stable:
            raise
        created = False
    return path, 'saved' if created else 'unchanged'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', required=True, help='MAS source URL (also required for local fixtures)')
    local = parser.add_mutually_exclusive_group()
    local.add_argument('--html-file', type=Path, help='Extract local HTML instead of fetching')
    local.add_argument('--pdf-file', type=Path, help='Extract a local PDF with page citations')
    parser.add_argument('--fixture', action='store_true', help='Label synthetic inputs as fixtures')
    parser.add_argument('--output-dir', type=Path, default=Path('data/ingestion'))
    parser.add_argument('--passage-size', type=int, default=1000)
    args = parser.parse_args()
    try:
        from mira.pipeline import process_item
        local_path = args.html_file or args.pdf_file
        bundle = process_item({
            'url': args.url,
            'kind': 'html' if args.html_file else 'pdf' if args.pdf_file else 'url',
            'path': str(local_path.resolve()) if local_path else None,
            'origin': 'fixture' if args.fixture else 'local' if local_path else 'live',
            'passage_size': args.passage_size,
        }, args.output_dir)
        path, status = save(bundle, args.output_dir)
        print(json.dumps({'status': status, 'path': str(path), 'passages': len(bundle['passages'])}))
        return 0
    except (ValueError, OSError, http.client.HTTPException, LookupError) as error:
        print(json.dumps({'status': 'failed', 'error': str(error)}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
