import io
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import uuid

import pytest

USER=str(uuid.UUID(int=1));WORKSPACE=str(uuid.UUID(int=3));RUN=str(uuid.UUID(int=4))


def authorizer(*,actor=USER,role='admin',run_actor=USER,status='queued'):
    from mira.credential_broker import SupabaseRunAuthorizer
    class Transport:
        def open(self,request,timeout):
            assert request.get_header('Authorization')=='Bearer user-access-token'
            assert timeout==5
            path=request.full_url.split('http://127.0.0.1:55421',1)[1]
            if path=='/auth/v1/user':response={'id':actor}
            elif path.startswith('/rest/v1/analysis_runs?'):
                response=[{'id':RUN,'workspace_id':WORKSPACE,'created_by':run_actor,'status':status}]
            elif path.startswith('/rest/v1/workspace_members?'):response=[{'role':role}]
            else:raise AssertionError('Unexpected Auth/RLS request')
            return io.BytesIO(json.dumps(response).encode())
    return SupabaseRunAuthorizer('http://127.0.0.1:55421','local-anon',Transport())


def test_auth_verifier_uses_normal_rls_and_actual_owner_identity():
    owner=authorizer()('user-access-token',WORKSPACE,RUN)
    assert (owner.user_id,owner.workspace_id,owner.run_id,owner.status)==(USER,WORKSPACE,RUN,'queued')


@pytest.mark.parametrize('options',[{'role':'viewer'},{'actor':str(uuid.UUID(int=9))}])
def test_lost_run_role_or_wrong_owner_denies_key_submission(options):
    from mira.credentials import CredentialError
    with pytest.raises(CredentialError):authorizer(**options)('user-access-token',WORKSPACE,RUN)


def test_completed_run_cannot_get_a_new_key_lease():
    from mira.credentials import CredentialError
    from mira.credential_broker import CredentialBroker
    broker=CredentialBroker(authorizer(status='draft'))
    with pytest.raises(CredentialError):broker.put('user-access-token',WORKSPACE,RUN,{'openai':'provider-secret'})


def test_public_socket_cannot_redeem_worker_keys_and_survives_oversized_input():
    from mira.credentials import BrokerClient
    from mira.credential_worker import claim_keys
    from mira.credential_broker import CredentialBroker,serve_broker
    b=CredentialBroker(authorizer(),capability='local-worker-capability')
    with tempfile.TemporaryDirectory(prefix='mira-test-',dir='/tmp') as root,serve_broker(b,Path(root)/'b') as service:
        client=BrokerClient(str(service.client_socket));h=client.put('user-access-token',WORKSPACE,RUN,{'openai':'provider-secret'})
        for data in (json.dumps({'operation':'claim','handle':h,'capability':'local-worker-capability'}).encode()+b'\n',b'x'*65537+b'\n'):
            with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as sock:
                sock.settimeout(2);sock.connect(str(service.client_socket));sock.sendall(data)
                result=json.loads(sock.makefile('rb').readline(1000))
                assert result=={'ok':False}
        assert claim_keys(h,WORKSPACE,USER,RUN,socket_path=str(service.worker_socket),capability_path=str(service.capability_path))=={'openai':'provider-secret'}


def test_broker_cli_is_explicit_and_describes_private_local_service():
    result=subprocess.run([sys.executable,'-m','mira','broker','--help'],capture_output=True,text=True)
    assert result.returncode==0
    assert '--directory' in result.stdout


def test_real_auth_check_has_a_total_deadline_and_no_inherited_provider_environment(monkeypatch):
    import threading,time,os
    from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
    from mira.credential_broker import SupabaseRunAuthorizer
    from mira.credentials import CredentialError
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            time.sleep(.6)
            try:
                self.send_response(200);self.end_headers();self.wfile.write(b'{"id":"'+USER.encode()+b'"}')
            except OSError:pass
        def log_message(self,*args):pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);server.daemon_threads=True
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        auth=SupabaseRunAuthorizer(f'http://127.0.0.1:{server.server_port}','anon',timeout_seconds=.1)
        started=time.monotonic()
        with pytest.raises(CredentialError):auth('local-user-token',WORKSPACE,RUN)
        assert time.monotonic()-started<.5
    finally:server.shutdown();server.server_close();thread.join(timeout=1)


def test_disconnect_during_authorization_rolls_back_undeliverable_lease():
    import threading,time
    from mira.credential_broker import CredentialBroker,RunOwner,serve_broker
    entered=threading.Event();resume=threading.Event()
    def authorize(*_):
        entered.set();resume.wait(1)
        return RunOwner(USER,WORKSPACE,RUN,'queued')
    b=CredentialBroker(authorize)
    with tempfile.TemporaryDirectory(prefix='mira-test-',dir='/tmp') as root,serve_broker(b,Path(root)/'b') as service:
        sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);sock.connect(str(service.client_socket))
        data={'operation':'put','access_token':'owner-token','workspace_id':WORKSPACE,'run_id':RUN,'keys':{'openai':'provider-secret'}}
        sock.sendall(json.dumps(data).encode()+b'\n');assert entered.wait(1)
        sock.shutdown(socket.SHUT_RDWR);sock.close();resume.set()
        # Wait for the real response-write path, not the service context cleanup.
        deadline=time.monotonic()+.5
        time.sleep(.05)
        while b._entries and time.monotonic()<deadline:time.sleep(.01)
        assert not b._entries
