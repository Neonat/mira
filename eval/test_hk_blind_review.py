import json

import pytest

from eval.hk_blind_review import build_pack, digest, local_connection_info, render_review


def test_blind_pack_whitelists_scope_fields_and_escapes_saved_markup():
    row = {
        "id": "p", "version_id": "v", "source_key": "hkma", "published_at": None,
        "content_sha256": "text-hash", "content": "Saved text with <markup>.",
        "title": "Publication", "source_url": "https://example.test/",
        "page_number": 2, "passage_number": 1, "draft_label": 1,
    }
    scope = {
        "jurisdiction": "HK", "as_of": "2026-11-04", "eligible_passages": 1,
        "corpus_sha256": digest([["p", "v", "hkma", None, "text-hash"]]),
    }
    manifest = {
        "scopes": {"S01": scope},
        "cases": [{"id": "R01", "scope": "S01", "question": "Question?", "expected_support": "Private answer"}],
    }
    guide = {"selection": "fixture", "shortlists": {"R01": ["p"]},
             "context": {"v": ["Circular", "Source context"]}, "draft_label": 1}
    pack = build_pack(manifest, {"S01": [row]})
    rendered = render_review("{{PACK_DATA}}\n{{REVIEW_GUIDE}}", pack, guide)
    assert "Private answer" not in rendered
    assert "draft_label" not in rendered
    assert "<" not in rendered
    packed, presented_guide = map(json.loads, rendered.splitlines())
    assert packed["passages"]["p"]["content"] == row["content"]
    assert presented_guide["shortlists"]["R01"] == ["p"]

    scope["corpus_sha256"] = "changed"
    with pytest.raises(ValueError, match="drifted"):
        build_pack(manifest, {"S01": [row]})


@pytest.mark.parametrize("dsn", [
    "postgresql://db.example.test/postgres",
    "host=localhost hostaddr=192.0.2.1 dbname=postgres",
    "dbname=postgres",
])
def test_connection_requires_an_explicit_local_host(dsn):
    with pytest.raises(ValueError, match="loopback"):
        local_connection_info(dsn)


def test_connection_pins_localhost_to_loopback():
    assert "hostaddr=127.0.0.1" in local_connection_info("host=localhost dbname=postgres")
