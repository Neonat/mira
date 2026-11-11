"""Storage construction shared by worker and signed-in app; no database access."""
from collections.abc import Mapping
import os
from pathlib import Path

from mira.config import REPO_ROOT
from mira.originals import PrivateOriginalStore,RetentionPolicy
from mira.private_objects import PrivateObjectStore


class StorageConfigurationError(ValueError):
    pass


def worker_object_store():
    if os.environ.get('MIRA_ARTIFACT_STORAGE','local')=='local':
        return None
    if os.environ.get('MIRA_ARTIFACT_STORAGE')!='supabase':
        raise StorageConfigurationError('Unknown artifact storage backend')
    url=os.environ.get('SUPABASE_URL','')
    key=os.environ.get('MIRA_STORAGE_SERVICE_ROLE_KEY','')
    if not url or not key:
        raise StorageConfigurationError('Private storage worker configuration is incomplete')
    try:
        from supabase import create_client
        return PrivateObjectStore(create_client(url,key))
    except Exception:
        raise StorageConfigurationError('Private storage worker configuration is unavailable') from None


class OriginalStorage:
    def __init__(self,local,objects=None,*,backend='local',read_only=False):
        if backend not in ('local','supabase'):
            raise StorageConfigurationError('Unknown original storage backend')
        self.local,self.objects,self.backend=local,objects,backend
        self.policy=local.policy
        self.read_only=read_only

    def retain(self,ws,source,body,*,acquisition_method,content_type):
        if self.read_only:
            raise StorageConfigurationError('Original reader cannot upload')
        if self.backend=='local':
            return self.local.retain(ws,source,body,acquisition_method=acquisition_method,content_type=content_type)
        config=source.connector_config
        grant=config.get('original_retention') if isinstance(config,Mapping) else None
        if (not self.policy.enabled or 'store_text' not in source.permitted_operations
                or acquisition_method not in ('http_fetch','manual_import') or not isinstance(grant,Mapping)
                or grant.get('approved') is not True or not isinstance(grant.get('reference'),str)
                or not grant['reference'].strip()):
            return None
        if self.objects is None:
            raise StorageConfigurationError('Private original storage is unavailable')
        if type(body) is not bytes or len(body)>self.policy.max_bytes:
            raise ValueError('Original exceeds configured byte limit')
        identity=self.objects.put(ws,'original',body,content_type)
        return {**identity,'approval_reference':grant['reference']}

    def read(self,ws,identity):
        if not isinstance(identity,Mapping):
            raise ValueError('Invalid original identity')
        if identity.get('storage_kind')=='private_local':
            return self.local.read(ws,identity)
        if identity.get('storage_kind')!='private_supabase' or identity.get('purpose')!='original' or self.objects is None:
            raise ValueError('Original storage identity is unavailable')
        size=identity.get('size_bytes')
        if type(size) is not int or not 0<=size<=self.policy.max_bytes:
            raise ValueError('Original exceeds configured byte limit')
        return self.objects.read(ws,{k:v for k,v in identity.items() if k!='approval_reference'})


def original_store_from_env(*,client=None):
    local=PrivateOriginalStore(Path(os.environ.get('MIRA_ORIGINALS_DIR') or REPO_ROOT/'private-originals'),RetentionPolicy.from_env())
    backend=os.environ.get('MIRA_ARTIFACT_STORAGE','local')
    objects=PrivateObjectStore(client) if client is not None else worker_object_store() if backend!='local' else None
    return OriginalStorage(local,objects,backend=backend,read_only=client is not None)
