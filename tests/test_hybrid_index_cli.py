import json
import os
from uuid import uuid4
import pytest

from mira.hybrid_index import main
from test_hybrid_archive_db import archive

def args():
    return ['--workspace',str(uuid4()),'--actor',str(uuid4()),'--jurisdiction','HK','--as-of','2026-11-04']

def test_preview_does_not_load_provider_or_database(capsys,monkeypatch):
    def forbidden(*a,**k):raise AssertionError('preview must be offline')
    assert main(args(),factory=forbidden,connector=forbidden)==0
    result=json.loads(capsys.readouterr().out)
    assert result['execute'] is False and result['max_tokens']==20000 and result['max_batches']==4

@pytest.mark.parametrize('extra',[['--max-tokens','0'],['--max-seconds','0'],['--max-seconds','301'],['--max-batches','1001'],['--batch-size','0']])
def test_invalid_bound_refused_before_provider(extra,capsys):
    def forbidden(*a,**k):raise AssertionError('invalid limits must not invoke a provider')
    assert main(args()+extra,factory=forbidden,connector=forbidden)==2
    assert 'refused' in capsys.readouterr().err.lower()

def test_explicit_execution_respects_disabled_factory(capsys):
    def forbidden(*a,**k):raise AssertionError('disabled factory must not connect')
    assert main(args()+['--execute'],factory=lambda:None,connector=forbidden)==2
    assert 'refused' in capsys.readouterr().err.lower()

@pytest.mark.skipif(not os.getenv('MIRA_TEST_DATABASE_URL'),reason='local PostgreSQL required')
def test_execute_real_scope_without_acquisition(archive,capsys,monkeypatch):
    from contextlib import nullcontext
    from test_hybrid_archive_db import retriever
    a=archive;a.passage('Saved manual evidence.')
    argv=['--workspace',str(a.ws),'--actor',str(a.user),'--jurisdiction','HK','--as-of','2026-11-04','--execute']
    # The trusted DSN is not used by the injected local fixture connection.
    monkeypatch.setenv('MIRA_WORKER_DATABASE_URL',os.environ['MIRA_TEST_DATABASE_URL'])
    code=main(argv,factory=lambda:retriever(a),connector=lambda dsn:nullcontext(a.conn))
    assert code==0
    result=json.loads(capsys.readouterr().out)
    assert result['status']=='complete' and result['indexed_passages']==1
