import unittest
from uuid import uuid4

from mira.store import SourceRecord


class BrowserEligibilityTests(unittest.TestCase):
    def test_blocked_http_requires_separate_explicit_approval(self):
        from mira.live_browser import permitted

        source = SourceRecord(uuid4(), 'Example', 'website', 'https://example.org', None,
                              ('fetch', 'store_text'), {'allow_live_browser': True,
                              'browser_access_approval': {'reference': 'approval'}})
        self.assertTrue(permitted('https://example.org/page', sources=[source],
                                  source_ids={source.id}, reason='js'))
        self.assertFalse(permitted('https://example.org/page', sources=[source],
                                   source_ids={source.id}, reason='http_blocked'))

    def test_refuses_missing_permission_or_scope(self):
        from mira.live_browser import permitted
        source = SourceRecord(uuid4(), 'Example', 'website', 'https://example.org', None,
                              ('fetch',), {'allow_live_browser': True,
                              'browser_access_approval': {'reference': 'approval'}})
        self.assertFalse(permitted('https://example.org', sources=[source],
                                   source_ids={source.id}, reason='js'))
        self.assertFalse(permitted('https://other.example', sources=[source],
                                   source_ids={source.id}, reason='js'))
        self.assertFalse(permitted('https://example.org', sources=[source],
                                   source_ids=set(), reason='js'))
        self.assertFalse(permitted('https://example.org', sources=[source],
                                   source_ids={source.id}, reason='robots'))

    def test_rejects_non_public_browser_dns_addresses(self):
        from mira.live_browser import _public_addresses
        from mira.fetch import FetchRefused
        with self.assertRaises(FetchRefused):
            _public_addresses(['127.0.0.1'])
        self.assertEqual(_public_addresses(['8.8.8.8']), ['8.8.8.8'])

    def test_pinned_transport_refuses_unknown_host_before_network(self):
        from mira.live_browser import _PinnedTransport
        from mira.fetch import FetchRefused
        with self.assertRaises(FetchRefused):
            _PinnedTransport({}).get('https://example.org/robots.txt', {}, 1, 1024)

    def test_robots_transport_fail_closes_access_denials(self):
        from mira.live_browser import _robots_status
        for status in (301, 401, 403, 429):
            self.assertEqual(_robots_status(status), 503)
        self.assertEqual(_robots_status(404), 404)
        self.assertEqual(_robots_status(200), 200)

    def test_real_chromium_renders_javascript_and_click(self):
        import os
        from unittest.mock import patch
        from playwright.sync_api import Route
        from mira.fetch import RawResponse
        from mira.live_browser import _child
        source_id = uuid4()
        payload = {'url': 'https://example.org/page', 'source_ids': [str(source_id)], 'reason': 'js',
                   'remaining': 15, 'sources': [{'id': str(source_id), 'name': 'Example',
                   'source_type': 'website', 'base_url': 'https://example.org', 'jurisdiction_code': None,
                   'permitted_operations': ['fetch', 'store_text'], 'connector_config': {
                       'allow_live_browser': True, 'browser_access_approval': {'reference': 'test'},
                       'browser_actions': [{'type': 'click', 'selector': '#go'}]}}]}
        html = '<img src="https://tracking.invalid/pixel"><script src="https://tracking.invalid/track.js"></script><button id="go" onclick="document.body.insertAdjacentHTML(\'beforeend\',\'<p>clicked</p>\')">Go</button><script>document.body.insertAdjacentHTML("beforeend", "<p>dynamic</p>")</script>'
        def fulfill(route, **kwargs):
            route.fulfill(status=200, content_type='text/html', body=html)
        executable = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
        with patch.dict(os.environ, {'MIRA_BROWSER_EXECUTABLE': executable}), \
             patch('mira.live_browser.resolve_addresses', return_value=['8.8.8.8']), \
             patch('mira.live_browser._PinnedTransport.get', return_value=RawResponse(404, {}, b'')), \
             patch.object(Route, 'continue_', fulfill):
            result = _child(payload)
        import base64
        body = base64.b64decode(result['body']).decode()
        self.assertIn('<p>dynamic</p>', body)
        self.assertIn('<p>clicked</p>', body)
        self.assertEqual(result['provenance']['denied_requests'][0]['origin'], 'https://tracking.invalid')
        self.assertEqual(result['provenance']['omitted_resources'], [{'resource_type': 'image'}])

    def test_timeout_kills_child_process_group(self):
        import subprocess
        import sys
        from unittest.mock import patch
        from mira.fetch import AllowList, Fetcher
        from mira.live_browser import LiveBrowserAcquirer
        source = SourceRecord(uuid4(), 'Example', 'website', 'https://example.org', None,
                              ('fetch', 'store_text'), {'allow_live_browser': True,
                              'browser_access_approval': {'reference': 'approval'}})
        other = SourceRecord(uuid4(), 'Other', 'website', 'https://other.example', None,
                             ('fetch', 'store_text'), {'allow_live_browser': True,
                             'browser_access_approval': {'reference': 'approval'}})
        fetcher = Fetcher(AllowList([source, other]))
        real_popen = subprocess.Popen
        children = []
        def sleeper(*args, **kwargs):
            child = real_popen([sys.executable, '-c', 'import time; time.sleep(60)'], **kwargs)
            children.append(child)
            return child
        with patch.dict('os.environ', {'MIRA_ENABLE_LIVE_BROWSER': '1'}), patch('mira.live_browser.subprocess.Popen', side_effect=sleeper):
            with self.assertRaises(TimeoutError) as caught:
                LiveBrowserAcquirer(fetcher).acquire(
                    'https://example.org', sources=[source, other], source_ids={source.id, other.id},
                    timeout_seconds=.2, reason='js')
        self.assertTrue(caught.exception.request_sent)
        self.assertIsNotNone(children[0].poll())
        self.assertEqual(fetcher._blocked, set())
        self.assertEqual(fetcher._browser_interrupted, {source.id})
        self.assertTrue(fetcher._state('example.org').browser_policy_unknown)
        self.assertFalse(getattr(fetcher._state('other.example'), 'browser_policy_unknown', False))

    def test_preflight_refusal_is_not_charged(self):
        from mira.fetch import AllowList, Fetcher, FetchRefused
        from mira.live_browser import LiveBrowserAcquirer
        source = SourceRecord(uuid4(), 'Example', 'website', 'https://example.org', None,
                              ('fetch', 'store_text'), {})
        with self.assertRaises(FetchRefused) as caught:
            LiveBrowserAcquirer(Fetcher(AllowList([source]))).acquire(
                'https://example.org', sources=[source], source_ids={source.id},
                timeout_seconds=1, reason='js')
        self.assertFalse(caught.exception.request_sent)

    def test_real_chromium_obeys_robots_before_navigation(self):
        import os
        from unittest.mock import patch
        from playwright.sync_api import Route
        from mira.fetch import RawResponse, FetchFailed
        from mira.live_browser import _child
        source_id = uuid4()
        payload = {'url': 'https://example.org/page', 'source_ids': [str(source_id)], 'reason': 'js',
                   'remaining': 10, 'sources': [{'id': str(source_id), 'name': 'Example',
                   'source_type': 'website', 'base_url': 'https://example.org', 'jurisdiction_code': None,
                   'permitted_operations': ['fetch', 'store_text'], 'connector_config': {
                       'allow_live_browser': True, 'browser_access_approval': {'reference': 'test'}}}]}
        executable = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
        with patch.dict(os.environ, {'MIRA_BROWSER_EXECUTABLE': executable}), \
             patch('mira.live_browser.resolve_addresses', return_value=['8.8.8.8']), \
             patch('mira.live_browser._PinnedTransport.get', return_value=RawResponse(200, {}, b'User-agent: *\nDisallow: /\n')), \
             patch.object(Route, 'continue_') as continuation:
            with self.assertRaises(Exception):
                _child(payload)
            continuation.assert_not_called()

    def test_real_chromium_blocks_unapproved_redirect_before_network(self):
        import os
        from unittest.mock import patch
        from playwright.sync_api import Route
        from mira.fetch import RawResponse
        from mira.live_browser import _child
        source_id = uuid4()
        payload = {'url': 'https://example.org/page', 'source_ids': [str(source_id)], 'reason': 'js',
                   'remaining': 10, 'sources': [{'id': str(source_id), 'name': 'Example',
                   'source_type': 'website', 'base_url': 'https://example.org', 'jurisdiction_code': None,
                   'permitted_operations': ['fetch', 'store_text'], 'connector_config': {
                       'allow_live_browser': True, 'browser_access_approval': {'reference': 'test'}}}]}
        requested = []
        def redirect(route, **kwargs):
            requested.append(route.request.url)
            route.fulfill(status=302, headers={'location': 'https://unapproved.invalid/secret'})
        executable = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
        with patch.dict(os.environ, {'MIRA_BROWSER_EXECUTABLE': executable}), \
             patch('mira.live_browser.resolve_addresses', return_value=['8.8.8.8']), \
             patch('mira.live_browser._PinnedTransport.get', return_value=RawResponse(404, {}, b'')), \
             patch.object(Route, 'continue_', redirect):
            with self.assertRaises(Exception):
                _child(payload)
        self.assertEqual(requested, ['https://example.org/page'])

    def test_global_switch_is_required_even_for_approved_source(self):
        import os
        from unittest.mock import patch
        from mira.fetch import AllowList, Fetcher, FetchRefused
        from mira.live_browser import LiveBrowserAcquirer
        source = SourceRecord(uuid4(), 'Example', 'website', 'https://example.org', None,
                              ('fetch', 'store_text'), {'allow_live_browser': True,
                              'browser_access_approval': {'reference': 'approval'}})
        with patch.dict(os.environ, {'MIRA_ENABLE_LIVE_BROWSER': '0'}):
            with self.assertRaises(FetchRefused) as caught:
                LiveBrowserAcquirer(Fetcher(AllowList([source]))).acquire(
                    'https://example.org', sources=[source], source_ids={source.id},
                    timeout_seconds=1, reason='js')
        self.assertFalse(caught.exception.request_sent)

    def test_cancellation_kills_and_reaps_child(self):
        import subprocess
        import sys
        from unittest.mock import patch
        from mira.fetch import AllowList, Fetcher
        from mira.live_browser import LiveBrowserAcquirer
        source = SourceRecord(uuid4(), 'Example', 'website', 'https://example.org', None,
                              ('fetch', 'store_text'), {'allow_live_browser': True,
                              'browser_access_approval': {'reference': 'approval'}})
        real_popen = subprocess.Popen
        children = []
        def interrupting(*args, **kwargs):
            child = real_popen([sys.executable, '-c', 'import time; time.sleep(60)'], **kwargs)
            children.append(child)
            communicate = child.communicate
            calls = [0]
            def interrupted(*args, **kwargs):
                calls[0] += 1
                if calls[0] == 1:
                    raise KeyboardInterrupt()
                return communicate(*args, **kwargs)
            child.communicate = interrupted
            return child
        fetcher = Fetcher(AllowList([source]))
        with patch.dict('os.environ', {'MIRA_ENABLE_LIVE_BROWSER': '1'}), \
             patch('mira.live_browser.subprocess.Popen', side_effect=interrupting):
            with self.assertRaises(KeyboardInterrupt):
                LiveBrowserAcquirer(fetcher).acquire('https://example.org', sources=[source],
                    source_ids={source.id}, timeout_seconds=2, reason='js')
        self.assertIsNotNone(children[0].poll())
        self.assertEqual(fetcher._blocked, set())

    def test_challenge_stops_before_click(self):
        import os
        from unittest.mock import patch
        from playwright.sync_api import Locator, Route
        from mira.fetch import FetchFailed, RawResponse
        from mira.live_browser import _child
        source_id = uuid4()
        payload = {'url': 'https://example.org/page', 'source_ids': [str(source_id)], 'reason': 'js',
                   'remaining': 10, 'sources': [{'id': str(source_id), 'name': 'Example',
                   'source_type': 'website', 'base_url': 'https://example.org', 'jurisdiction_code': None,
                   'permitted_operations': ['fetch', 'store_text'], 'connector_config': {
                       'allow_live_browser': True, 'browser_access_approval': {'reference': 'test'},
                       'browser_actions': [{'type': 'click', 'selector': '#go'}]}}]}
        def fulfill(route, **kwargs):
            route.fulfill(status=200, content_type='text/html', body='<button id="go">CAPTCHA</button>')
        with patch.dict(os.environ, {'MIRA_BROWSER_EXECUTABLE': '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'}), \
             patch('mira.live_browser.resolve_addresses', return_value=['8.8.8.8']), \
             patch('mira.live_browser._PinnedTransport.get', return_value=RawResponse(404, {}, b'')), \
             patch.object(Route, 'continue_', fulfill), patch.object(Locator, 'click') as click:
            with self.assertRaisesRegex(FetchFailed, 'challenge'):
                _child(payload)
            click.assert_not_called()

    def test_real_chromium_pending_xhr_timeout_retains_sanitized_events(self):
        import os
        import subprocess
        import sys
        from unittest.mock import patch
        from mira.fetch import AllowList, Fetcher
        from mira.live_browser import LiveBrowserAcquirer
        source = SourceRecord(uuid4(), 'Example', 'website', 'https://example.org', None,
                              ('fetch', 'store_text'), {'allow_live_browser': True,
                              'browser_access_approval': {'reference': 'approval'},
                              'browser_actions': [{'type': 'wait', 'milliseconds': 3000}]})
        script = '''
import json, time
from unittest.mock import patch
from playwright.sync_api import Route
from mira.fetch import RawResponse
from mira.live_browser import _child

def fulfill(route, **kwargs):
    if route.request.resource_type == 'document':
        route.fulfill(status=200, content_type='text/html', body="<script>fetch('/pending?secret=token')</script>")
    else:
        time.sleep(60)
with patch('mira.live_browser.resolve_addresses', return_value=['8.8.8.8']), \\
     patch('mira.live_browser._PinnedTransport.get', return_value=RawResponse(404, {}, b'')), \\
     patch.object(Route, 'continue_', fulfill):
    json.dump(_child(json.load(__import__('sys').stdin)), __import__('sys').stdout)
'''
        real_popen = subprocess.Popen
        def fixture(*args, **kwargs):
            return real_popen([sys.executable, '-c', script], **kwargs)
        env = {'MIRA_ENABLE_LIVE_BROWSER': '1',
               'MIRA_BROWSER_EXECUTABLE': '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'}
        with patch.dict(os.environ, env), patch('mira.live_browser.subprocess.Popen', side_effect=fixture):
            with self.assertRaises(TimeoutError) as caught:
                LiveBrowserAcquirer(Fetcher(AllowList([source]))).acquire(
                    'https://example.org/page?secret=token', sources=[source], source_ids={source.id},
                    timeout_seconds=9, reason='js')
        diagnostics = caught.exception.diagnostics
        self.assertIn('dns_resolved', [event['stage'] for event in diagnostics])
        self.assertTrue(any(event['stage'] == 'request_allowed' and event.get('resource_type') in ('fetch', 'xhr')
                            and event.get('main') is False for event in diagnostics))
        self.assertNotIn('secret', repr(diagnostics))
        self.assertNotIn('token', repr(diagnostics))

    def test_failed_child_propagates_observed_robots_delay(self):
        import os
        import subprocess
        import sys
        from unittest.mock import patch
        from mira.fetch import AllowList, FetchFailed, Fetcher
        from mira.live_browser import LiveBrowserAcquirer
        source = SourceRecord(uuid4(), 'Example', 'website', 'https://example.org', None,
                              ('fetch', 'store_text'), {'allow_live_browser': True,
                              'browser_access_approval': {'reference': 'approval'}})
        script = '''
import json, sys
sys.stdin.read()
print('MIRA_BROWSER_EVENT ' + json.dumps({'stage':'rate_policy', 'host':'example.org', 'delay':60}), file=sys.stderr, flush=True)
print(json.dumps({'error':'challenge','refused':False,'request_sent':True}))
'''
        real_popen = subprocess.Popen
        def fixture(*args, **kwargs):
            return real_popen([sys.executable, '-c', script], **kwargs)
        fetcher = Fetcher(AllowList([source]))
        with patch.dict(os.environ, {'MIRA_ENABLE_LIVE_BROWSER': '1'}), \
             patch('mira.live_browser.subprocess.Popen', side_effect=fixture):
            with self.assertRaises(FetchFailed):
                LiveBrowserAcquirer(fetcher).acquire('https://example.org/page', sources=[source],
                    source_ids={source.id}, timeout_seconds=5, reason='js')
        self.assertEqual(fetcher._state('example.org').min_browser_delay, 60)

    def test_unknown_rate_policy_refuses_before_starting_child(self):
        import os
        from unittest.mock import patch
        from mira.fetch import AllowList, Fetcher, FetchRefused
        from mira.live_browser import LiveBrowserAcquirer
        source = SourceRecord(uuid4(), 'Example', 'website', 'https://example.org', None,
                              ('fetch', 'store_text'), {'allow_live_browser': True,
                              'browser_access_approval': {'reference': 'approval'}})
        fetcher = Fetcher(AllowList([source]))
        fetcher._state('example.org').browser_policy_unknown = True
        with patch.dict(os.environ, {'MIRA_ENABLE_LIVE_BROWSER': '1'}), \
             patch('mira.live_browser.subprocess.Popen') as popen:
            with self.assertRaises(FetchRefused) as caught:
                LiveBrowserAcquirer(fetcher).acquire('https://example.org/page', sources=[source],
                    source_ids={source.id}, timeout_seconds=5, reason='js')
        self.assertFalse(caught.exception.request_sent)
        popen.assert_not_called()
