"""Guest access uses real Postgres roles and the normal prepared report worker."""
import secrets
from datetime import timedelta
from uuid import uuid4

import psycopg
import pytest

from mira.db import acting_as
from mira.prepared_reporting import execute_prepared_request
from test_preparation_store_db import DSN, conn, prepared, workspace

pytestmark = pytest.mark.skipif(not DSN, reason="MIRA_TEST_DATABASE_URL not set")


def rpc(conn, function, *args, role="anon"):
    with conn.transaction():
        conn.execute(f"set local role {role}")
        parameters = ", ".join(["%s"] * len(args))
        return conn.execute(f"select public.{function}({parameters}) as result", args).fetchone()["result"]


@pytest.fixture
def ready(conn, prepared):
    store, job, payload = prepared
    snapshot = store.publish_job(job, payload)
    request = store.request_report(job["workspace_id"], job["actor_id"], job["brief"], job["source_ids"], "seed-report")
    result = execute_prepared_request(conn, "unused", request["id"])
    assert result["status"] == "ready", result
    return store, job, snapshot, result["report_id"]


def open_window(conn, job, report_id, link):
    with acting_as(conn, job["actor_id"]):
        return rpc(conn, "open_guest_demo", report_id, link, role="authenticated")


def test_guest_access_pins_snapshot_and_uses_prepared_worker(conn, ready):
    store, job, snapshot, report_id = ready
    link, receipt = secrets.token_hex(32), secrets.token_hex(32)
    ws = job["workspace_id"]
    window = open_window(conn, job, report_id, link)
    timing = conn.execute("select expires_at-opened_at as duration from private.guest_demo_windows where id=%s",
                          (window["id"],)).fetchone()
    assert timing["duration"] == timedelta(hours=1)

    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        rpc(conn, "open_guest_demo", report_id, link)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with acting_as(conn, uuid4()):
            rpc(conn, "close_guest_demo", ws, role="authenticated")
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with conn.transaction():
            conn.execute("set local role anon")
            conn.execute("select html from public.prepared_reports")

    later = store.enqueue_job(ws, job["actor_id"], job["source_ids"], job["brief"], {}, {}, {}, "later")
    assert rpc(conn, "guest_demo_info", link)["jurisdictions"] == ["HK"]
    assert rpc(conn, "guest_demo_submit", link, receipt) == "queued"
    assert rpc(conn, "guest_demo_submit", link, receipt) == "queued"
    assert rpc(conn, "guest_demo_result", link, secrets.token_hex(32), True) is None
    guest_requests = conn.execute("select id from public.prepared_report_requests where workspace_id=%s and idempotency_key like 'guest-demo:%%'",
                                  (ws,)).fetchall()
    assert len(guest_requests) == 1
    request_id = guest_requests[0]["id"]
    pins = conn.execute("select snapshot_id,job_id from public.prepared_report_request_scopes where request_id=%s",
                        (request_id,)).fetchall()
    assert len(pins) == len(job["source_ids"])
    assert all(row["snapshot_id"] == snapshot["id"] and row["job_id"] is None for row in pins)
    result = execute_prepared_request(conn, "unused", request_id)
    assert result["status"] == "ready"
    assert rpc(conn, "guest_demo_result", link, receipt, False) == {"status": "ready"}
    report = rpc(conn, "guest_demo_result", link, receipt, True)
    assert set(report) == {"status", "html"}
    assert "human evidence review pending" in report["html"].lower()
    assert conn.execute("select status from public.preparation_jobs where id=%s", (later["id"],)).fetchone()["status"] == "queued"

    with acting_as(conn, job["actor_id"]):
        rpc(conn, "close_guest_demo", ws, role="authenticated")
    assert rpc(conn, "guest_demo_info", link) is None
    assert rpc(conn, "guest_demo_result", link, receipt, True) is None
    assert rpc(conn, "guest_demo_submit", link, secrets.token_hex(32)) is None
    assert conn.execute("select status from public.prepared_report_requests where id=%s",
                        (request_id,)).fetchone()["status"] == "ready"


def test_guest_expiry_rotation_and_later_correction(conn, ready):
    _, job, snapshot, report_id = ready
    link, replacement, receipt = (secrets.token_hex(32) for _ in range(3))
    window = open_window(conn, job, report_id, link)
    conn.execute("""update private.guest_demo_windows
                    set opened_at=statement_timestamp()-interval '2 hours',
                        expires_at=statement_timestamp()-interval '1 hour' where id=%s""", (window["id"],))
    assert rpc(conn, "guest_demo_submit", link, receipt) is None
    window = open_window(conn, job, report_id, replacement)
    new_link = secrets.token_hex(32)
    open_window(conn, job, report_id, new_link)
    assert rpc(conn, "guest_demo_info", replacement) is None
    assert rpc(conn, "guest_demo_submit", new_link, receipt) == "queued"
    fid = next(iter(snapshot["payload"]["evidence_input"]["findings"]))
    with acting_as(conn, job["actor_id"]):
        conn.execute("select public.review_prepared_fact(%s,%s,'correction_requested','Check original evidence')",
                     (snapshot["id"], fid))
    assert rpc(conn, "guest_demo_info", new_link) is None
    assert rpc(conn, "guest_demo_result", new_link, receipt, True) is None
    assert rpc(conn, "guest_demo_submit", new_link, secrets.token_hex(32)) is None
