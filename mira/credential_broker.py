"""Local in-memory BYOK leases with authenticated submission and one worker claim."""
from __future__ import annotations

from collections.abc import Callable,Mapping
from contextlib import contextmanager
from dataclasses import dataclass,field
import hmac
import json
import os
from pathlib import Path
import secrets
import socketserver
import subprocess
import sys
import threading
import time
from urllib.parse import urlencode,urlsplit
import urllib.request
from uuid import UUID

from mira.credentials import CredentialError,MAX_MESSAGE_BYTES,_receive_frame


@dataclass(frozen=True)
class RunOwner:
    user_id: str
    workspace_id: str
    run_id: str
    status: str


@dataclass
class _Lease:
    owner: RunOwner
    deadline: float
    keys: dict[str,str]=field(repr=False)


class CredentialBroker:
    """No provider credentials survive this object's process lifetime."""
    def __init__(self,authorize: Callable[[str,str,str],RunOwner],*,capability: str | None=None,
                 clock: Callable[[],float]=time.monotonic,ttl_seconds: int=3600):
        if not 0<ttl_seconds<=3600:raise ValueError('invalid credential lifetime')
        self._authorize=authorize;self._clock=clock;self._ttl=ttl_seconds
        self._capability=capability or secrets.token_urlsafe(32)
        self._entries: dict[str,_Lease]={};self._lock=threading.RLock();self._closed=False

    def _expire(self):
        for handle,lease in list(self._entries.items()):
            if lease.deadline<=self._clock():
                lease.keys.clear();del self._entries[handle]

    def _owner(self,token,workspace,run):
        try:
            workspace=str(UUID(workspace));run=str(UUID(run))
            if not isinstance(token,str) or not 1<=len(token)<=16384:raise ValueError('token')
            owner=self._authorize(token,workspace,run)
            if (owner.workspace_id!=workspace or owner.run_id!=run
                    or str(UUID(owner.user_id))!=owner.user_id):raise ValueError('binding')
            return owner
        except Exception:raise CredentialError('Credential request refused') from None

    def put(self,token: str,workspace: str,run: str,keys: Mapping[str,str]) -> str:
        with self._lock:
            if self._closed:raise CredentialError('Credential request refused')
        owner=self._owner(token,workspace,run)
        if owner.status!='queued':raise CredentialError('Credential request refused')
        if not isinstance(keys,dict) or not 1<=len(keys)<=3:raise CredentialError('Credential request refused')
        clean={}
        for name,key in keys.items():
            if (name not in ('openai','anthropic','exa') or not isinstance(key,str)
                    or not 8<=len(key.strip())<=8192 or any(c in key for c in ('\n','\r','\0'))):
                raise CredentialError('Credential request refused')
            clean[name]=key.strip()
        with self._lock:
            if self._closed:raise CredentialError('Credential request refused')
            self._expire()
            if (len(self._entries)>=256 or sum(v.owner.user_id==owner.user_id for v in self._entries.values())>=8):
                raise CredentialError('Too many pending credential requests')
            handle=secrets.token_urlsafe(32)
            self._entries[handle]=_Lease(owner,self._clock()+self._ttl,clean)
            return handle

    def claim(self,handle: str,workspace: str,user: str,run: str,capability: str) -> dict[str,str]:
        with self._lock:
            self._expire()
            lease=self._entries.get(handle)
            if (not isinstance(capability,str) or not hmac.compare_digest(capability.encode(),self._capability.encode())
                    or lease is None or (workspace,user,run)!=(lease.owner.workspace_id,lease.owner.user_id,lease.owner.run_id)):
                raise CredentialError('Worker credential request refused')
            del self._entries[handle]
            keys=dict(lease.keys);lease.keys.clear()
            return keys

    def revoke(self,token: str,handle: str) -> None:
        with self._lock:
            self._expire();lease=self._entries.get(handle)
            if lease is None:return
        owner=self._owner(token,lease.owner.workspace_id,lease.owner.run_id)
        if owner.user_id!=lease.owner.user_id:raise CredentialError('Credential request refused')
        with self._lock:
            if self._entries.get(handle) is lease:
                lease.keys.clear();del self._entries[handle]

    def close(self):
        with self._lock:
            self._closed=True
            for lease in self._entries.values():lease.keys.clear()
            self._entries.clear()

    def _discard_pending(self,handle: str):
        """Rollback a lease whose handle could not be delivered to its caller."""
        with self._lock:
            lease=self._entries.pop(handle,None)
            if lease is not None:lease.keys.clear()


class SupabaseRunAuthorizer:
    """Verify Auth and current analyst/admin ownership through ordinary RLS reads."""
    def __init__(self,url: str,anon_key: str,opener=None,*,timeout_seconds: float=4):
        parsed=urlsplit(url)
        if (parsed.username or parsed.password or parsed.query or parsed.fragment
                or not (parsed.scheme=='https' or (parsed.scheme=='http' and parsed.hostname in ('127.0.0.1','localhost')))):
            raise ValueError('unsupported Auth endpoint')
        if not 0<timeout_seconds<=4:raise ValueError('unsupported Auth deadline')
        self._url=url.rstrip('/');self._anon=anon_key
        self._opener=opener;self._timeout=timeout_seconds

    def _read(self,path,token):
        request=urllib.request.Request(self._url+path,headers={'apikey':self._anon,'Authorization':'Bearer '+token})
        with self._opener.open(request,timeout=5) as response:raw=response.read(MAX_MESSAGE_BYTES+1)
        if len(raw)>MAX_MESSAGE_BYTES:raise ValueError('oversize')
        return json.loads(raw)

    def __call__(self,token: str,workspace: str,run: str) -> RunOwner:
        try:
            if self._opener is None:
                value={'url':self._url,'anon':self._anon,'token':token,'workspace':workspace,'run':run}
                result=subprocess.run([sys.executable,'-c',_AUTH_SCRIPT],input=json.dumps(value).encode(),
                    capture_output=True,timeout=self._timeout,check=True,env={'PATH':os.defpath})
                if len(result.stdout)>MAX_MESSAGE_BYTES:raise ValueError('oversize')
                result=json.loads(result.stdout)
                return RunOwner(str(UUID(result['user_id'])),str(UUID(result['workspace_id'])),str(UUID(result['run_id'])),result['status'])
            user=self._read('/auth/v1/user',token);uid=str(UUID(user['id']))
            query=urlencode({'id':'eq.'+run,'workspace_id':'eq.'+workspace,'created_by':'eq.'+uid,
                'select':'id,workspace_id,created_by,status','limit':'1'})
            rows=self._read('/rest/v1/analysis_runs?'+query,token)
            if not isinstance(rows,list) or len(rows)!=1:raise ValueError('run')
            row=rows[0]
            query=urlencode({'workspace_id':'eq.'+workspace,'user_id':'eq.'+uid,'select':'role','limit':'1'})
            members=self._read('/rest/v1/workspace_members?'+query,token)
            if not members or members[0]['role'] not in ('analyst','admin'):raise ValueError('role')
            if (row['id'],row['workspace_id'],row['created_by'])!=(run,workspace,uid):raise ValueError('binding')
            return RunOwner(uid,workspace,run,row['status'])
        except Exception:raise CredentialError('Credential request refused') from None


_AUTH_SCRIPT=r'''
import json,sys,urllib.request,urllib.parse,uuid
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None
try:
    v=json.load(sys.stdin);opener=urllib.request.build_opener(NoRedirect())
    ws=str(uuid.UUID(v['workspace']));run=str(uuid.UUID(v['run']))
    def read(path):
        req=urllib.request.Request(v['url']+path,headers={'apikey':v['anon'],'Authorization':'Bearer '+v['token']})
        with opener.open(req,timeout=3) as response:raw=response.read(65537)
        if len(raw)>65536:raise ValueError()
        return json.loads(raw)
    uid=str(uuid.UUID(read('/auth/v1/user')['id']))
    q=urllib.parse.urlencode({'id':'eq.'+run,'workspace_id':'eq.'+ws,'created_by':'eq.'+uid,
        'select':'id,workspace_id,created_by,status','limit':'1'})
    rows=read('/rest/v1/analysis_runs?'+q)
    if not isinstance(rows,list) or len(rows)!=1:raise ValueError()
    row=rows[0]
    if (row['id'],row['workspace_id'],row['created_by'])!=(run,ws,uid):raise ValueError()
    q=urllib.parse.urlencode({'workspace_id':'eq.'+ws,'user_id':'eq.'+uid,'select':'role','limit':'1'})
    members=read('/rest/v1/workspace_members?'+q)
    if not isinstance(members,list) or len(members)!=1 or members[0]['role'] not in ('analyst','admin'):raise ValueError()
    print(json.dumps({'user_id':uid,'workspace_id':ws,'run_id':run,'status':row['status']}))
except Exception:sys.exit(1)
'''


@dataclass(frozen=True)
class BrokerService:
    directory: Path
    client_socket: Path
    worker_socket: Path
    capability_path: Path


@contextmanager
def serve_broker(broker: CredentialBroker,directory: Path):
    """Two bounded local endpoints. The only written secret is a worker capability."""
    directory=directory.absolute()
    if len(os.fsencode(directory/'worker.sock'))>=104:
        raise CredentialError('Use a shorter local broker directory, such as one under /tmp')
    if directory.exists():raise CredentialError('Use a new private broker directory')
    directory.mkdir(parents=True,mode=0o700)
    directory.chmod(0o700)
    service=BrokerService(directory,directory/'client.sock',directory/'worker.sock',directory/'worker.capability')
    fd=os.open(service.capability_path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    with os.fdopen(fd,'w') as handle:handle.write(broker._capability)
    class Server(socketserver.ThreadingUnixStreamServer):
        daemon_threads=True
        block_on_close=False
        def handle_error(self,*args):pass  # Never print request payloads or raw exceptions.
    def handler(worker):
        class Handler(socketserver.StreamRequestHandler):
            timeout=5
            def handle(self):
                result={'ok':False};created_handle=None
                try:
                    raw=_receive_frame(self.request)
                    if len(raw)>MAX_MESSAGE_BYTES or not raw.endswith(b'\n'):raise ValueError('framing')
                    data=json.loads(raw)
                    if not isinstance(data,dict):raise ValueError('shape')
                    operation=data.get('operation')
                    if worker and operation=='claim' and set(data)=={'operation','handle','workspace_id','user_id','run_id','capability'}:
                        keys=broker.claim(data['handle'],data['workspace_id'],data['user_id'],data['run_id'],data['capability'])
                        result={'ok':True,'keys':keys}
                    elif not worker and operation=='put' and set(data)=={'operation','access_token','workspace_id','run_id','keys'}:
                        created_handle=broker.put(data['access_token'],data['workspace_id'],data['run_id'],data['keys'])
                        result={'ok':True,'handle':created_handle}
                    elif not worker and operation=='revoke' and set(data)=={'operation','access_token','handle'}:
                        broker.revoke(data['access_token'],data['handle']);result={'ok':True}
                except Exception:pass
                try:self.wfile.write(json.dumps(result,separators=(',',':')).encode()+b'\n')
                except OSError:
                    if created_handle is not None:broker._discard_pending(created_handle)
        return Handler
    servers=[];threads=[];stopping=threading.Event()
    def sweep():
        while not stopping.wait(.2):
            with broker._lock:broker._expire()
    try:
        for path,worker in ((service.client_socket,False),(service.worker_socket,True)):
            server=Server(str(path),handler(worker));path.chmod(0o600)
            servers.append(server)
            thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':0.05},daemon=True)
            thread.start();threads.append(thread)
        cleaner=threading.Thread(target=sweep,daemon=True);cleaner.start();threads.append(cleaner)
        yield service
    finally:
        stopping.set()
        for server in servers:server.shutdown();server.server_close()
        for thread in threads:thread.join(timeout=1)
        broker.close()
        for path in (service.client_socket,service.worker_socket,service.capability_path):path.unlink(missing_ok=True)


def run_broker(directory: Path | None=None) -> None:
    """Explicit local service; does not import database or start a research worker."""
    import signal
    directory=directory or Path('/tmp')/('mira-byok-'+secrets.token_hex(6))
    try:
        authorize=SupabaseRunAuthorizer(os.environ['SUPABASE_URL'],os.environ['SUPABASE_ANON_KEY'])
    except (KeyError,ValueError):raise SystemExit('Configure the local Auth URL and anon key before starting the broker') from None
    def stop(*_):raise KeyboardInterrupt
    previous=signal.signal(signal.SIGTERM,stop)
    try:
        with serve_broker(CredentialBroker(authorize),directory) as service:
            print(json.dumps({'client_socket':str(service.client_socket),'worker_socket':str(service.worker_socket),
                'capability_path':str(service.capability_path)}),flush=True)
            threading.Event().wait()
    except KeyboardInterrupt:pass
    except (OSError,CredentialError):raise SystemExit('Local credential service could not start; use a new short private directory') from None
    finally:signal.signal(signal.SIGTERM,previous)
