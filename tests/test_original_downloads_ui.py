"""Review controls return approved bytes using the signed-in client only."""
from contextlib import nullcontext
from importlib.util import spec_from_file_location, module_from_spec
from pathlib import Path
from types import SimpleNamespace

from test_original_access import Client, Query, access_fixture


def test_review_download_uses_current_auth_and_frozen_identity(access_fixture, monkeypatch):
    ws,user,vid,store,tables=access_fixture
    tables['document_versions'][0]['title']='Circular'
    class UI:
        downloads=[]
        notes=[]
        def expander(self,*args,**kwargs): return nullcontext()
        def caption(self,*args): pass
        def write(self,*args): pass
        def button(self,*args,**kwargs): return True
        def info(self,value): self.notes.append(value)
        def download_button(self,label,data,**kwargs): self.downloads.append(data)
    def in_(self,key,values):
        self.rows=[r for r in self.rows if str(r.get(key)) in set(map(str,values))]
        return self
    monkeypatch.setattr(Query,'in_',in_,raising=False)
    spec=spec_from_file_location('mira_review_ui',Path(__file__).resolve().parents[1]/'app/streamlit_app.py')
    app=module_from_spec(spec); spec.loader.exec_module(app)
    ui=UI(); monkeypatch.setattr(app,'st',ui)
    monkeypatch.setenv('MIRA_ORIGINALS_DIR',str(store.root))
    frozen={'document_version_id':str(vid),'acquisition_provenance':tables['document_versions'][0]['metadata']}
    snapshot={'evidence_bundle':{'passages':{'P':frozen}}}
    app._original_downloads(Client(tables,user),str(ws),'run',snapshot,True)
    assert ui.downloads==[b'original']
    tables['workspace_members']=[]
    app._original_downloads(Client(tables,user),str(ws),'run',snapshot,True)
    assert ui.downloads==[b'original'] and ui.notes
    # A signed snapshot cannot silently download a different current identity.
    tables['document_versions'][0]['metadata']={'original_retained':True,'retained_original':{'sha256':'b'*64}}
    app._original_downloads(Client(tables,user),str(ws),'run',snapshot,True)
    assert ui.downloads==[b'original']


def test_signed_download_rejects_identity_changed_between_listing_and_read(access_fixture,monkeypatch):
    from copy import deepcopy
    from mira.store import SourceRecord
    ws,user,vid,store,tables=access_fixture
    tables['document_versions'][0]['title']='Circular'
    original=deepcopy(tables['document_versions'][0]['metadata'])
    grant=tables['sources'][0]['connector_config']
    new=store.retain(ws,SourceRecord(__import__('uuid').uuid4(),'Fixture','website',None,None,('store_text',),grant),
        b'changed bytes',acquisition_method='http_fetch',content_type='application/pdf')
    class RacingClient(Client):
        reads=0
        def table(self,name):
            if name=='document_versions':
                self.reads+=1
                if self.reads==2:
                    self.tables[name][0]['metadata']={'original_retained':True,'retained_original':new}
            return super().table(name)
    def in_(self,key,values):
        self.rows=[r for r in self.rows if str(r.get(key)) in set(map(str,values))]
        return self
    monkeypatch.setattr(Query,'in_',in_,raising=False)
    spec=spec_from_file_location('mira_review_ui_race',Path(__file__).resolve().parents[1]/'app/streamlit_app.py')
    app=module_from_spec(spec);spec.loader.exec_module(app)
    downloads=[];notes=[]
    app.st=SimpleNamespace(expander=lambda *a,**k:nullcontext(),caption=lambda *a:None,
        write=lambda *a:None,button=lambda *a,**k:True,info=notes.append,
        download_button=lambda label,data,**kwargs:downloads.append(data))
    monkeypatch.setenv('MIRA_ORIGINALS_DIR',str(store.root))
    snapshot={'evidence_bundle':{'passages':{'p':{'document_version_id':str(vid),'acquisition_provenance':original}}}}
    app._original_downloads(RacingClient(tables,user),str(ws),'run',snapshot,True)
    assert not downloads and notes
