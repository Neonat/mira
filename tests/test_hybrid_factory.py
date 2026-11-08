"""Credentials alone never turn optional embedding calls on."""
import pytest
from mira.runner import hybrid_from_env


def test_default_off_even_with_existing_credential(monkeypatch):
    monkeypatch.delenv('MIRA_ENABLE_HYBRID_RETRIEVAL',raising=False)
    monkeypatch.setenv('OPENAI_API_KEY','fixture-never-sent')
    assert hybrid_from_env() is None


def test_enabled_requires_explicit_model_identity(monkeypatch):
    monkeypatch.setenv('MIRA_ENABLE_HYBRID_RETRIEVAL','1')
    monkeypatch.delenv('MIRA_EMBEDDING_MODEL',raising=False)
    monkeypatch.delenv('MIRA_EMBEDDING_REVISION',raising=False)
    with pytest.raises(ValueError,match='explicit embedding model and revision'):
        hybrid_from_env()
