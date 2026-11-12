"""Validated per-run restrictions. None of these fields grants source access."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict,dataclass,fields
import re
from urllib.parse import urlsplit
from uuid import UUID

from mira.topics import CYBERSECURITY, CYBER_SOURCE_HOST


@dataclass(frozen=True)
class ResearchSettings:
    source_ids: tuple[str,...] | None=None
    enable_exa: bool=False
    enable_browser: bool=False
    retrieval: str='keyword'
    max_analysis_batches: int=8
    credential_mode: str='operator'
    credential_handle: str | None=None
    archive_only: bool=False

    def __post_init__(self):
        if self.source_ids is not None:
            try:
                if not isinstance(self.source_ids,(tuple,list)) or not 1<=len(self.source_ids)<=64:raise ValueError()
                ids=tuple(str(UUID(value)) for value in self.source_ids)
                if len(set(ids))!=len(ids):raise ValueError()
            except (ValueError,TypeError,AttributeError):raise ValueError('Invalid source selection') from None
            object.__setattr__(self,'source_ids',ids)
        if type(self.enable_exa) is not bool or type(self.enable_browser) is not bool:
            raise ValueError('Invalid acquisition options')
        if self.retrieval not in ('keyword','hybrid'):raise ValueError('Invalid retrieval method')
        if type(self.archive_only) is not bool:
            raise ValueError('Invalid archive-only option')
        if self.archive_only and (self.enable_exa or self.enable_browser or self.retrieval!='keyword'):
            raise ValueError('Archive-only research requires saved keyword retrieval')
        if type(self.max_analysis_batches) is not int or not 1<=self.max_analysis_batches<=64:
            raise ValueError('Analysis depth must be between 1 and 64 batches')
        if self.credential_mode not in ('operator','byok'):raise ValueError('Invalid credential mode')
        if self.credential_handle is not None and (self.credential_mode!='byok'
                or not isinstance(self.credential_handle,str)
                or re.fullmatch(r'[A-Za-z0-9_-]{32,128}',self.credential_handle) is None):
            raise ValueError('Invalid request credential handle')

    @classmethod
    def from_dict(cls,value: Mapping | None) -> ResearchSettings:
        if value is None:return cls()
        if not isinstance(value,Mapping) or set(value)-{field.name for field in fields(cls)}:
            raise ValueError('Unsupported research settings')
        return cls(**dict(value))

    def as_dict(self) -> dict:
        value=asdict(self)
        value['source_ids']=list(self.source_ids) if self.source_ids is not None else None
        if not self.archive_only:
            value.pop('archive_only')
        return value


def restrict_sources(sources, settings: ResearchSettings | None, jurisdictions, *, topic="AML/CFT"):
    """Intersect an active workspace allow-list with the selected topic, markets and sources."""
    if topic == CYBERSECURITY:
        sources = [source for source in sources if source.jurisdiction_code == "AE"
                   and urlsplit(source.base_url or "").hostname == CYBER_SOURCE_HOST]
    if settings is None:
        return list(sources)
    eligible = [source for source in sources
                if source.jurisdiction_code is None or source.jurisdiction_code in jurisdictions]
    if settings.source_ids is None:
        return eligible
    selected = set(settings.source_ids)
    if not selected <= {str(source.id) for source in eligible}:
        raise ValueError('Selected source is inactive, unavailable or outside the requested topic and markets')
    return [source for source in eligible if str(source.id) in selected]
