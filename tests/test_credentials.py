"""A BYOK lease must not expose keys across actors, requests or restarts."""
from pathlib import Path
import json
import threading
import time
import uuid
import tempfile

import pytest

USER=str(uuid.UUID(int=1));OTHER=str(uuid.UUID(int=2))
WORKSPACE=str(uuid.UUID(int=3));RUN=str(uuid.UUID(int=4))
KEY='private-provider-key-for-this-request'


def broker(clock=None):
    from mira.credential_broker import CredentialBroker,RunOwner
    def authorize(token,workspace,run):
        if token not in ('owner-token','other-token'):
            raise ValueError('private invalid token body')
        return RunOwner(USER if token=='owner-token' else OTHER,workspace,run,'queued')
    return CredentialBroker(authorize,capability='worker-only-capability',clock=clock or time.monotonic)


def test_lease_can_only_be_claimed_once_by_bound_worker():
    from mira.credentials import CredentialError
    b=broker();handle=b.put('owner-token',WORKSPACE,RUN,{'openai':KEY})
    with pytest.raises(CredentialError):
        b.claim(handle,WORKSPACE,OTHER,RUN,'worker-only-capability')
    with pytest.raises(CredentialError):
        b.claim(handle,WORKSPACE,USER,RUN,'wrong-capability')
    assert b.claim(handle,WORKSPACE,USER,RUN,'worker-only-capability')=={'openai':KEY}
    with pytest.raises(CredentialError):
        b.claim(handle,WORKSPACE,USER,RUN,'worker-only-capability')


@pytest.mark.parametrize('workspace,run',[(str(uuid.UUID(int=9)),RUN),(WORKSPACE,str(uuid.UUID(int=9)))])
def test_worker_cannot_move_a_lease_to_a_different_request(workspace,run):
    from mira.credentials import CredentialError
    b=broker();h=b.put('owner-token',WORKSPACE,RUN,{'openai':KEY})
    with pytest.raises(CredentialError):b.claim(h,workspace,USER,run,'worker-only-capability')
    assert b.claim(h,WORKSPACE,USER,RUN,'worker-only-capability')['openai']==KEY


def test_expired_and_restarted_broker_never_recover_provider_keys():
    from mira.credentials import CredentialError
    now=[0.];b=broker(lambda:now[0]);h=b.put('owner-token',WORKSPACE,RUN,{'openai':KEY})
    now[0]=3600
    with pytest.raises(CredentialError):b.claim(h,WORKSPACE,USER,RUN,'worker-only-capability')
    fresh=broker()
    with pytest.raises(CredentialError):fresh.claim(h,WORKSPACE,USER,RUN,'worker-only-capability')


def test_cancel_can_only_revoke_the_owners_pending_lease():
    from mira.credentials import CredentialError
    b=broker();h=b.put('owner-token',WORKSPACE,RUN,{'openai':KEY})
    with pytest.raises(CredentialError):b.revoke('other-token',h)
    b.revoke('owner-token',h)
    with pytest.raises(CredentialError):b.claim(h,WORKSPACE,USER,RUN,'worker-only-capability')


@pytest.mark.parametrize('keys',[{'unrecognised':KEY},{'openai':''},{'openai':'x'*9000},{'openai':'private\nkey'}])
def test_invalid_key_payloads_fail_without_echoing_secrets(keys):
    from mira.credentials import CredentialError
    b=broker()
    with pytest.raises(CredentialError) as e:b.put('owner-token',WORKSPACE,RUN,keys)
    assert KEY not in str(e.value) and 'private' not in str(e.value)


def test_authentication_errors_never_echo_provider_or_access_token_values():
    from mira.credentials import CredentialError
    b=broker()
    with pytest.raises(CredentialError) as e:b.put('private-access-token',WORKSPACE,RUN,{'openai':KEY})
    assert 'private' not in str(e.value) and KEY not in repr(e.value)


def test_real_socket_transport_and_worker_capability_file(tmp_path):
    from mira.credentials import BrokerClient,CredentialError
    from mira.credential_worker import claim_keys
    from mira.credential_broker import serve_broker
    b=broker()
    # macOS AF_UNIX addresses are shorter than pytest's nested temporary paths.
    with tempfile.TemporaryDirectory(prefix='mira-test-',dir='/tmp') as short_root, serve_broker(b,Path(short_root)/'broker') as service:
        client=BrokerClient(str(service.client_socket))
        h=client.put('owner-token',WORKSPACE,RUN,{'openai':KEY})
        assert claim_keys(h,WORKSPACE,USER,RUN,socket_path=str(service.worker_socket),
                          capability_path=str(service.capability_path))=={'openai':KEY}
        assert all(KEY.encode() not in p.read_bytes() for p in service.directory.iterdir() if p.is_file())
        assert service.client_socket.stat().st_mode & 0o777==0o600
        with pytest.raises(CredentialError):
            claim_keys(h,WORKSPACE,USER,RUN,socket_path=str(service.worker_socket),capability_path=str(service.capability_path))
    assert not service.client_socket.exists() and not service.worker_socket.exists()


def test_expired_keys_are_removed_while_broker_is_idle():
    from mira.credential_broker import serve_broker
    now=[0.];b=broker(lambda:now[0]);b.put('owner-token',WORKSPACE,RUN,{'openai':KEY})
    with tempfile.TemporaryDirectory(prefix='mira-test-',dir='/tmp') as short_root, serve_broker(b,Path(short_root)/'broker'):
        now[0]=3601
        deadline=time.monotonic()+1
        while b._entries and time.monotonic()<deadline:time.sleep(.01)
        assert not b._entries


def test_two_claimers_cannot_both_receive_the_same_key():
    from mira.credentials import CredentialError
    b=broker();h=b.put('owner-token',WORKSPACE,RUN,{'openai':KEY});results=[]
    def claim():
        try:results.append(b.claim(h,WORKSPACE,USER,RUN,'worker-only-capability'))
        except CredentialError:results.append(None)
    threads=[threading.Thread(target=claim) for _ in range(2)]
    for t in threads:t.start()
    for t in threads:t.join()
    assert results.count({'openai':KEY})==1 and results.count(None)==1


def test_shutdown_rejects_submission_that_was_waiting_for_auth():
    from mira.credential_broker import CredentialBroker,RunOwner
    from mira.credentials import CredentialError
    entered=threading.Event();resume=threading.Event();errors=[]
    def authorize(*_):
        entered.set();resume.wait(1)
        return RunOwner(USER,WORKSPACE,RUN,'queued')
    b=CredentialBroker(authorize)
    def submit():
        try:b.put('owner-token',WORKSPACE,RUN,{'openai':KEY})
        except CredentialError:errors.append('refused')
    thread=threading.Thread(target=submit);thread.start();assert entered.wait(1)
    b.close();resume.set();thread.join(timeout=1)
    assert errors==['refused'] and not b._entries


def test_partial_local_frame_has_a_total_deadline():
    import socket
    from mira.credentials import _receive_frame,CredentialError
    left,right=socket.socketpair();stopped=threading.Event()
    def drip():
        try:
            while not stopped.wait(.01):right.sendall(b'x')
        except OSError:pass
    thread=threading.Thread(target=drip,daemon=True);thread.start()
    started=time.monotonic()
    try:
        with pytest.raises(CredentialError):_receive_frame(left,timeout_seconds=.05)
        assert time.monotonic()-started<.3
    finally:stopped.set();left.close();right.close();thread.join(timeout=1)
