"""UI-safe local credential transport. Provider keys are never persisted here."""
from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import stat
import time
from collections.abc import Mapping

MAX_MESSAGE_BYTES=65536


class CredentialError(RuntimeError):
    """Safe message only: never include keys, tokens or server error bodies."""


def _receive_frame(sock: socket.socket,*,timeout_seconds: float=5) -> bytes:
    deadline=time.monotonic()+timeout_seconds
    data=bytearray()
    try:
        while len(data)<=MAX_MESSAGE_BYTES:
            remaining=deadline-time.monotonic()
            if remaining<=0:raise ValueError('deadline')
            sock.settimeout(remaining)
            chunk=sock.recv(min(4096,MAX_MESSAGE_BYTES+1-len(data)))
            if not chunk:raise ValueError('framing')
            data.extend(chunk)
            if b'\n' in chunk:
                if len(data)>MAX_MESSAGE_BYTES or not data.endswith(b'\n'):raise ValueError('framing')
                return bytes(data)
        raise ValueError('oversize')
    except (OSError,ValueError):raise CredentialError('Credential request refused or local service unavailable') from None


def _private_path(path: str, *, is_socket: bool) -> Path:
    p=Path(path)
    try:
        info=p.lstat()
        valid=stat.S_ISSOCK(info.st_mode) if is_socket else stat.S_ISREG(info.st_mode)
        if (not p.is_absolute() or not valid or info.st_uid!=os.getuid()
                or stat.S_IMODE(info.st_mode)!=0o600):
            raise CredentialError('Local credential service unavailable')
    except OSError:
        raise CredentialError('Local credential service unavailable') from None
    return p


def _exchange(path: str, request: dict) -> dict:
    _private_path(path,is_socket=True)
    try:
        data=json.dumps(request,separators=(',',':')).encode()+b'\n'
        if len(data)>MAX_MESSAGE_BYTES:raise ValueError('oversize')
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as sock:
            sock.settimeout(5);sock.connect(path);sock.sendall(data)
            raw=_receive_frame(sock)
        if len(raw)>MAX_MESSAGE_BYTES or not raw.endswith(b'\n'):raise ValueError('framing')
        result=json.loads(raw)
        if not isinstance(result,dict) or result.get('ok') is not True:raise ValueError('refused')
        return result
    except (OSError,ValueError,TypeError):
        raise CredentialError('Credential request refused or local service unavailable') from None


class BrokerClient:
    """Only authenticated put/revoke are available on the client socket."""
    def __init__(self,socket_path: str | None=None):
        self.socket_path=socket_path or os.environ.get('MIRA_BROKER_SOCKET','')
        if not self.socket_path:raise CredentialError('Local credential service is not configured')

    def put(self,access_token: str,workspace_id: str,run_id: str,keys: Mapping[str,str]) -> str:
        response=_exchange(self.socket_path,{'operation':'put','access_token':access_token,
            'workspace_id':workspace_id,'run_id':run_id,'keys':dict(keys)})
        handle=response.get('handle')
        if not isinstance(handle,str) or not 32<=len(handle)<=128:
            raise CredentialError('Credential request refused')
        return handle

    def revoke(self,access_token: str,handle: str) -> None:
        _exchange(self.socket_path,{'operation':'revoke','access_token':access_token,'handle':handle})


