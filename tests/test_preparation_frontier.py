from contextlib import contextmanager
from datetime import date
from types import SimpleNamespace

from mira.preparation_runtime import FrontierAdapter


class Store:
    def __init__(self):
        self.entries = []
    def put_frontier(self, job, source_id, entries):
        self.entries.extend(entries)
    def pending_frontier(self, job, source_ids, limit, start_date=None, as_of_date=None):
        return self.entries[:limit]
    def finish_frontier(self, job, source_id, url, status, error=None):
        self.entries[0]['status'] = status


def test_frontier_retains_date_and_origin_across_adapter_instances():
    store = Store()
    @contextmanager
    def factory():
        yield store
    source = SimpleNamespace(id='source')
    allow = SimpleNamespace(source_for=lambda url: source)
    job = {'id': 'job', 'source_ids': ['source']}
    first = FrontierAdapter(factory, job, allow)
    link = SimpleNamespace(url='https://example.test/doc', text='Title', context='Context',
                           published=date(2025, 1, 2), date_source='listing date')
    first.record([link], 'https://example.test/index', 'version')
    second = FrontierAdapter(factory, job, allow)
    item = second.pending(['source'], 5)[0]
    assert item.published == date(2025, 1, 2)
    assert item.date_source == 'listing date'
    assert store.entries[0]['origin']['document_version_id'] == 'version'
    second.finish(item.url, 'acquired')
    assert store.entries[0]['status'] == 'acquired'


def test_scout_persists_discovery_before_exposing_candidates():
    from mira.agents.scout import _ScoutRun
    events = []
    frontier = SimpleNamespace(record=lambda links, url, version: events.append(('persist', links[0].url)))
    scout = SimpleNamespace(frontier=frontier, fetcher=SimpleNamespace(allow=SimpleNamespace(allows=lambda url: True)))
    run = _ScoutRun.__new__(_ScoutRun)
    run.scout, run.seen, run.discovery, run.discovery_omitted, run.origins = scout, set(), [], 0, {}
    link = SimpleNamespace(url='https://example.test/doc', published=None)
    run._record_discovery([link], 'https://example.test/index', None)
    assert events == [('persist', link.url)]
    assert run.discovery[0]['reason'] == 'candidate'
