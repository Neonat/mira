"""Eligibility checks for explicitly approved live-browser acquisition."""
from __future__ import annotations

from uuid import UUID

from mira.fetch import AllowList, FetchRefused
from mira.store import SourceRecord


def permitted(url: str, *, sources: list[SourceRecord], source_ids: set[UUID], reason: str) -> bool:
    """Check configuration and task scope without making any network requests."""
    if reason not in {'js', 'http_blocked'}:
        return False
    try:
        source = AllowList(sources).source_for(url)
    except (FetchRefused, ValueError):
        return False
    config = source.connector_config
    approval = config.get('browser_access_approval')
    if (source.id not in source_ids or 'store_text' not in source.permitted_operations
            or config.get('allow_live_browser') is not True or not isinstance(approval, dict)
            or not isinstance(approval.get('reference'), str) or not approval['reference'].strip()):
        return False
    return reason != 'http_blocked' or approval.get('allow_http_block_fallback') is True


def _public_addresses(addresses: list[str]) -> list[str]:
    import ipaddress
    if not addresses:
        raise FetchRefused('host has no addresses')
    for address in addresses:
        if not ipaddress.ip_address(address.split('%')[0]).is_global:
            raise FetchRefused('host resolves to a non-public address')
    return addresses


class _PinnedTransport:
    """Robots-only transport with destination addresses fixed before connecting."""
    def __init__(self, addresses: dict[str, list[str]]) -> None:
        self.addresses = addresses

    def get(self, url: str, headers: dict[str, str], timeout: float, max_bytes: int):
        import http.client
        import socket
        import ssl
        from urllib.parse import urlsplit
        from mira.fetch import RawResponse

        parts = urlsplit(url)
        host = (parts.hostname or '').lower()
        if host not in self.addresses:
            raise FetchRefused('unknown pinned host')
        addresses = _public_addresses(self.addresses[host])
        port = parts.port or (443 if parts.scheme == 'https' else 80)

        class Connection(http.client.HTTPConnection):
            def connect(self):
                sock = socket.create_connection((addresses[0], port), self.timeout)
                if parts.scheme == 'https':
                    try:
                        sock = ssl.create_default_context().wrap_socket(sock, server_hostname=host)
                    except BaseException:
                        sock.close()
                        raise
                self.sock = sock

        connection = Connection(host, port, timeout=timeout)
        try:
            target = parts.path or '/'
            if parts.query:
                target += '?' + parts.query
            connection.request('GET', target, headers={**headers, 'Host': parts.netloc})
            response = connection.getresponse()
            _event('robots_response', host=host, status=response.status)
            body = response.read(max_bytes + 1)
            status = 503 if len(body) > max_bytes else _robots_status(response.status)
            return RawResponse(status, {k.lower(): v for k, v in response.getheaders()}, body)
        finally:
            connection.close()


def _robots_status(status: int) -> int:
    return 503 if 300 <= status < 400 or status in (401, 403, 429) else status


from dataclasses import dataclass
from datetime import UTC, datetime
import base64
import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from urllib.parse import urlsplit

from mira.fetch import FetchedPage, FetchFailed, Fetcher, MIN_DELAY_SECONDS, USER_AGENT, resolve_addresses


@dataclass(frozen=True)
class LiveBrowserResult:
    page: FetchedPage
    provenance: dict


class LiveBrowserAcquirer:
    def __init__(self, fetcher: Fetcher) -> None:
        self.fetcher = fetcher

    def acquire(self, url: str, *, sources: list[SourceRecord], source_ids: set[UUID],
                timeout_seconds: float, reason: str) -> LiveBrowserResult:
        if os.environ.get('MIRA_ENABLE_LIVE_BROWSER') != '1' or not permitted(url, sources=sources, source_ids=source_ids, reason=reason):
            exc = FetchRefused('live browser is not approved')
            exc.request_sent = False
            raise exc
        if timeout_seconds <= 0:
            exc = TimeoutError('browser deadline reached')
            exc.request_sent = False
            raise exc
        deadline = time.monotonic() + timeout_seconds
        target = AllowList(sources).source_for(url)
        selected = [target]
        interrupted = getattr(self.fetcher, '_browser_interrupted', set())
        if target.id in interrupted:
            exc = FetchRefused('browser channel unavailable after interruption')
            exc.request_sent = False
            raise exc
        hosts = sorted({host for s in selected for host in
                        ([urlsplit(s.base_url).hostname] if s.base_url else []) +
                        list(s.connector_config.get('extra_hosts', [])) if host})
        locks = []
        states = []
        try:
            for host in hosts:
                state = self.fetcher._state(host.lower())
                if not state.lock.acquire(timeout=max(0, deadline - time.monotonic())):
                    raise TimeoutError('browser host lock deadline reached')
                locks.append(state.lock)
                states.append(state)
                if getattr(state, 'browser_policy_unknown', False):
                    exc = FetchRefused('browser rate policy is unknown after interruption')
                    exc.request_sent = False
                    raise exc
            for state in states:
                delay = max(MIN_DELAY_SECONDS, *(float(s.connector_config.get('crawl_delay_seconds', 0) or 0) for s in selected), getattr(state, 'min_browser_delay', 0),
                            float(state.robots.crawl_delay(USER_AGENT) or 0) if state.robots else 0)
                wait = (state.last_request + delay - time.monotonic()) if state.last_request is not None else 0
                if wait > 0:
                    if time.monotonic() + wait >= deadline:
                        raise TimeoutError('browser rate limit deadline reached')
                    time.sleep(wait)
            payload = {'url': url, 'source_ids': [str(i) for i in source_ids], 'reason': reason,
                       'sources': [{'id': str(s.id), 'name': s.name, 'source_type': s.source_type,
                                    'base_url': s.base_url, 'jurisdiction_code': s.jurisdiction_code,
                                    'permitted_operations': list(s.permitted_operations),
                                    'connector_config': s.connector_config} for s in selected],
                       'remaining': max(0, deadline - time.monotonic())}
            process = subprocess.Popen([sys.executable, '-m', 'mira.live_browser', '--child'],
                                       stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       start_new_session=True)
            try:
                out, stderr = process.communicate(json.dumps(payload).encode(), timeout=max(0.001, deadline-time.monotonic()))
            except BaseException as error:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                _, stderr = process.communicate()
                error.diagnostics = _parse_events(stderr)
                _apply_rate_events(error.diagnostics, hosts, states)
                for state in states:
                    state.browser_policy_unknown = True
                interrupted.add(target.id)
                self.fetcher._browser_interrupted = interrupted
                if isinstance(error, subprocess.TimeoutExpired):
                    exc = TimeoutError('browser deadline reached')
                    exc.diagnostics = error.diagnostics
                    raise exc from error
                raise
            diagnostics = _parse_events(stderr)
            _apply_rate_events(diagnostics, hosts, states)
            if process.returncode:
                for state in states:
                    state.browser_policy_unknown = True
                exc = FetchFailed('live browser subprocess failed')
                exc.diagnostics = diagnostics
                raise exc
            result = json.loads(out)
            if 'error' in result:
                exc = FetchRefused(result['error']) if result.get('refused') else FetchFailed(result['error'])
                exc.request_sent = result.get('request_sent', True)
                exc.diagnostics = diagnostics
                raise exc
            source = next(s for s in selected if str(s.id) == result['source_id'])
            for state in states:
                state.min_browser_delay = max(getattr(state, 'min_browser_delay', 0), result['max_delay'])
            page = FetchedPage(result['url'], url, source, 'html', 'text/html',
                               base64.b64decode(result['body']), datetime.fromisoformat(result['fetched_at']))
            result['provenance']['progress_events'] = diagnostics
            return LiveBrowserResult(page, result['provenance'])
        except BaseException as exc:
            if not hasattr(exc, 'request_sent'):
                exc.request_sent = True
            raise
        finally:
            for state in states:
                state.last_request = time.monotonic()
            for lock in reversed(locks):
                lock.release()


_CHILD_STATE = {'request_sent': False}
_EVENT_PREFIX = 'MIRA_BROWSER_EVENT '
_EVENT_LIMIT = 256
_event_count = 0


def _event(stage: str, **fields) -> None:
    global _event_count
    if _event_count >= _EVENT_LIMIT or (stage != 'rate_policy' and _event_count >= 128):
        return
    _event_count += 1
    allowed = {k: v for k, v in fields.items() if k in ('host', 'status', 'resource_type', 'main', 'delay')}
    print(_EVENT_PREFIX + json.dumps({'stage': stage, **allowed}, separators=(',', ':')), file=sys.stderr, flush=True)


def _parse_events(stderr: bytes) -> list[dict]:
    events = []
    valid = {'child_start', 'dns_resolved', 'robots_response', 'request_allowed', 'request_denied',
             'resource_omitted', 'main_response', 'dom_ready', 'rate_policy'}
    for line in stderr.decode('utf-8', 'replace').splitlines():
        if not line.startswith(_EVENT_PREFIX) or len(line) > 1024:
            continue
        try:
            event = json.loads(line[len(_EVENT_PREFIX):])
        except (ValueError, TypeError):
            continue
        if isinstance(event, dict) and event.get('stage') in valid and set(event) <= {'stage', 'host', 'status', 'resource_type', 'main', 'delay'}:
            events.append(event)
    return events[:_EVENT_LIMIT]


def _apply_rate_events(events, hosts, states):
    import math
    state_by_host = dict(zip((host.lower() for host in hosts), states))
    for event in events:
        delay = event.get('delay')
        state = state_by_host.get(event.get('host'))
        if (event.get('stage') == 'rate_policy' and state is not None and
                isinstance(delay, (int, float)) and math.isfinite(delay) and delay >= 0):
            state.min_browser_delay = max(getattr(state, 'min_browser_delay', 0), delay)


def _child(payload: dict) -> dict:
    _event('child_start')
    from playwright.sync_api import sync_playwright
    from mira.fetch import AllowList, MAX_REDIRECTS

    sources = [SourceRecord(UUID(s['id']), s['name'], s['source_type'], s['base_url'],
                            s['jurisdiction_code'], tuple(s['permitted_operations']), s['connector_config'])
               for s in payload['sources']]
    source_ids = {UUID(i) for i in payload['source_ids']}
    allow = AllowList(sources)
    target_source = allow.source_for(payload['url'])
    # Only the initial source and explicitly configured extra hosts are in scope.
    hosts = {(urlsplit(target_source.base_url).hostname or '').lower()}
    hosts.update(str(h).lower() for h in target_source.connector_config.get('extra_hosts', []))
    addresses = {h: _public_addresses(resolve_addresses(h)) for h in hosts if h}
    _event('dns_resolved', host=urlsplit(target_source.base_url).hostname)
    policy = Fetcher(allow, transport=_PinnedTransport(addresses), resolver=lambda h: addresses.get(h, []))
    config = target_source.connector_config
    actions = config.get('browser_actions', [])
    if not isinstance(actions, list) or len(actions) > 3:
        raise FetchRefused('invalid browser actions')
    rules = ', '.join([f'MAP {h} {addresses[h][0]}' for h in addresses] + ['MAP * ~NOTFOUND'])
    requests = []
    denied_requests = []
    omitted_resources = []
    total_requests = [0]
    reported_policy_hosts = set()
    action_log = []
    byte_count = [0]
    exceeded = [False]
    denial = [None]
    access_denial = [None]
    main_status = [None]
    raw_hash = [None]
    start = time.monotonic()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, executable_path=os.environ.get('MIRA_BROWSER_EXECUTABLE'),
                                    args=['--no-proxy-server', '--disable-quic', '--disable-features=WebRtcHideLocalIpsWithMdns',
                                          '--force-webrtc-ip-handling-policy=disable_non_proxied_udp',
                                          '--host-resolver-rules=' + rules])
        context = browser.new_context(user_agent=USER_AGENT, java_script_enabled=True, service_workers='block',
                                      accept_downloads=False)
        page = context.new_page()
        context.on('page', lambda popup: popup.close() if popup != page else None)
        context.add_init_script("Object.defineProperty(window, 'RTCPeerConnection', {value: undefined, configurable: false}); Object.defineProperty(window, 'webkitRTCPeerConnection', {value: undefined, configurable: false});")
        def on_response(response):
            if response.status in (401, 403, 429):
                access_denial[0] = response.status
            if response.request.is_navigation_request() and response.frame == page.main_frame:
                _event('main_response', status=response.status)
        page.on('response', on_response)
        context.add_init_script("document.addEventListener('submit', e => e.preventDefault(), true); Object.defineProperty(HTMLFormElement.prototype, 'submit', {value: function() {}, configurable: false}); Object.defineProperty(HTMLFormElement.prototype, 'requestSubmit', {value: function() {}, configurable: false});")
        page.set_default_timeout(max(1, int(payload['remaining'] * 1000)))
        cdp = context.new_cdp_session(page)
        cdp.send('Network.enable')
        def on_bytes(event):
            byte_count[0] += max(event.get('encodedDataLength', 0), event.get('dataLength', 0))
            if byte_count[0] > 15_000_000:
                exceeded[0] = True
                try:
                    page.close()
                except Exception:
                    pass
        cdp.on('Network.dataReceived', on_bytes)
        def route_request(route):
            request = route.request
            try:
                total_requests[0] += 1
                if total_requests[0] > 100:
                    denial[0] = 'browser request limit exceeded'
                    route.abort()
                    return
                if request.resource_type in ('image', 'font', 'media') and request.method in ('GET', 'HEAD'):
                    omitted_resources.append({'resource_type': request.resource_type})
                    _event('resource_omitted', resource_type=request.resource_type)
                    route.abort()
                    return
                if request.method not in ('GET', 'HEAD'):
                    raise FetchRefused('browser method denied')
                if request.is_navigation_request():
                    hop, previous = 0, request.redirected_from
                    while previous is not None:
                        hop += 1
                        previous = previous.redirected_from
                    if hop > MAX_REDIRECTS:
                        raise FetchRefused('browser redirect limit exceeded')
                source = allow.source_for(request.url)
                host = (urlsplit(request.url).hostname or '').lower()
                if source.id != target_source.id or source.id not in source_ids or host not in addresses:
                    raise FetchRefused('browser request outside source scope')
                policy._check_addresses(request.url)
                robots_allowed = policy._robots_allow(request.url, source)
                state = policy._state(urlsplit(request.url).netloc.lower())
                observed_delay = max(MIN_DELAY_SECONDS, float(source.connector_config.get('crawl_delay_seconds', 0) or 0),
                                     float(state.robots.crawl_delay(USER_AGENT) or 0) if state.robots else 0)
                if host not in reported_policy_hosts:
                    _event('rate_policy', host=host, delay=observed_delay)
                    reported_policy_hosts.add(host)
                if not robots_allowed:
                    raise FetchRefused('robots disallows browser request')
                with state.lock:
                    delay = max(MIN_DELAY_SECONDS, float(source.connector_config.get('crawl_delay_seconds', 0) or 0),
                                float(state.robots.crawl_delay(USER_AGENT) or 0) if state.robots else 0)
                    if state.last_request is not None:
                        wait = state.last_request + delay - time.monotonic()
                        if wait > 0:
                            time.sleep(wait)
                    state.last_request = time.monotonic()
                requests.append({'origin': f'{urlsplit(request.url).scheme}://{urlsplit(request.url).netloc}', 'method': request.method,
                                 'resource_type': request.resource_type})
                if request.is_navigation_request() and request.frame == page.main_frame:
                    _CHILD_STATE['request_sent'] = True
                _event('request_allowed', host=host, resource_type=request.resource_type,
                       main=request.is_navigation_request() and request.frame == page.main_frame)
                route.continue_()
            except Exception as exc:
                parts = urlsplit(request.url)
                _event('request_denied', host=parts.hostname or '', resource_type=request.resource_type,
                       main=request.is_navigation_request() and request.frame == page.main_frame)
                denied_requests.append({'origin': f'{parts.scheme}://{parts.netloc}', 'resource_type': request.resource_type})
                if request.method not in ('GET', 'HEAD') or (request.is_navigation_request() and request.frame == page.main_frame):
                    denial[0] = str(exc)
                route.abort()
        context.route('**/*', route_request)
        context.route_web_socket('**/*', lambda ws: ws.close())
        try:
            response = page.goto(payload['url'], wait_until='domcontentloaded',
                                 timeout=max(1, int(payload['remaining'] * 1000)))
            if response is None or response.status != 200:
                raise FetchFailed('browser navigation returned non-200 status')
            _event('dom_ready')
            main_status[0] = response.status
            try:
                raw_hash[0] = hashlib.sha256(response.body()).hexdigest()
            except Exception:
                pass
            _checked_body(page, config)
            for action in actions:
                if not isinstance(action, dict) or action.get('type') not in ('click', 'wait'):
                    raise FetchRefused('invalid browser action')
                if action['type'] == 'wait':
                    ms = action.get('milliseconds')
                    if not isinstance(ms, int) or not 0 <= ms <= 3000:
                        raise FetchRefused('invalid browser wait')
                    page.wait_for_timeout(ms)
                    action_log.append({'type': 'wait', 'milliseconds': ms})
                else:
                    selector = action.get('selector')
                    if not isinstance(selector, str) or not selector or len(selector) > 200:
                        raise FetchRefused('invalid browser selector')
                    locator = page.locator(selector).first
                    if locator.evaluate("e => !!e.closest('form') || ['INPUT','TEXTAREA','SELECT'].includes(e.tagName)"):
                        raise FetchRefused('form interaction denied')
                    locator.click()
                    action_log.append({'type': 'click', 'selector': selector})
                _checked_body(page, config)
                if access_denial[0] is not None or denial[0]:
                    raise FetchFailed('browser encountered access denial or unsafe request')
            body = _checked_body(page, config)
            if exceeded[0]:
                raise FetchFailed('browser resource limit exceeded')
            if access_denial[0] is not None:
                raise FetchFailed('browser encountered access denial or rate limit')
            if denial[0]:
                raise FetchRefused('browser resource denied')
            final_url = page.url
            if allow.source_for(final_url).id != target_source.id:
                raise FetchRefused('browser final URL outside source scope')
            delay = max([MIN_DELAY_SECONDS, float(config.get('crawl_delay_seconds', 0) or 0)] +
                        [float(s.robots.crawl_delay(USER_AGENT) or 0) for s in policy._hosts.values() if s.robots])
            return {'url': final_url, 'source_id': str(target_source.id), 'body': base64.b64encode(body).decode(),
                    'fetched_at': datetime.now(UTC).isoformat(), 'max_delay': delay,
                    'provenance': {'acquisition_method': 'live_browser', 'browser_engine': 'chromium',
                                   'javascript_enabled': True, 'requested_url': payload['url'], 'final_url': final_url,
                                   'initial_navigation_response_sha256': raw_hash[0], 'initial_navigation_status': main_status[0],
                                   'final_navigation_response_sha256': None, 'final_navigation_status': None,
                                   'rendered_dom_sha256': hashlib.sha256(body).hexdigest(),
                                   'approval_reference': config['browser_access_approval']['reference'],
                                   'actions': action_log, 'requests': requests, 'denied_requests': denied_requests,
                                   'omitted_resources': omitted_resources,
                                   'observed_network_bytes': byte_count[0],
                                   'original_retained': False, 'elapsed_seconds': time.monotonic()-start}}
        finally:
            context.close()
            browser.close()


def _checked_body(page, config: dict) -> bytes:
    body = page.content().encode()
    if len(body) > 2_000_000:
        raise FetchFailed('browser resource limit exceeded')
    text = body.decode('utf-8', 'replace').lower()
    markers = ['captcha', 'access denied', 'verify you are human', 'sign in to continue']
    markers += [str(x).lower() for x in config.get('block_markers', [])]
    if page.locator('input[type=\"password\"]').count() or any(m and m in text for m in markers):
        raise FetchFailed('browser encountered access denial or challenge')
    return body


if __name__ == '__main__' and sys.argv[1:] == ['--child']:
    import threading
    payload = json.load(sys.stdin)
    timer = threading.Timer(max(0.001, float(payload['remaining'])), lambda: os.killpg(os.getpgrp(), signal.SIGKILL))
    timer.daemon = True
    timer.start()
    try:
        output = _child(payload)
    except Exception as exc:
        output = {'error': str(exc)[:300], 'refused': isinstance(exc, FetchRefused), 'request_sent': _CHILD_STATE['request_sent']}
    json.dump(output, sys.stdout)
