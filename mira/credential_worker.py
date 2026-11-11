"""Trusted-worker-only redemption; the client app never imports this module."""
from mira.credentials import CredentialError,_exchange,_private_path


def claim_keys(handle: str,workspace_id: str,user_id: str,run_id: str,*,socket_path: str,
               capability_path: str) -> dict[str,str]:
    """Called after rechecking the run actor and current workspace membership."""
    try:capability=_private_path(capability_path,is_socket=False).read_text().strip()
    except OSError:raise CredentialError('Worker credential service unavailable') from None
    result=_exchange(socket_path,{'operation':'claim','handle':handle,'workspace_id':workspace_id,
        'user_id':user_id,'run_id':run_id,'capability':capability})
    keys=result.get('keys')
    if not isinstance(keys,dict) or not keys or not all(
            k in ('openai','anthropic','exa') and isinstance(v,str) and 8<=len(v)<=8192
            and not any(c in v for c in ('\n','\r','\0')) for k,v in keys.items()):
        raise CredentialError('Worker credential request refused')
    return keys
