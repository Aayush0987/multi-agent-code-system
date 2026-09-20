"""API tests: agents are mocked so these verify session handling, the
pause/decide/resume flow, validation, and access control -- not LLM output."""
from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

import api.server as server_module
import graph.supervisor as supervisor_module
from api.sessions import SessionStore
from graph.trace import log_event


def _fake_critique_invoke(sub_input, config=None):
    log_event("coder", event="wrote_code", round=1, reason="initial", diff="")
    log_event("tester", event="ran_tests", round=1, passed=True, exit_code=0, stderr_excerpt="")
    log_event("reviewer", event="reviewed", round=1, verdict="approve", reason="fine")
    return {
        "code": "def f(): pass",
        "test_result": {"passed": True, "stdout": "", "stderr": "", "exit_code": 0},
        "review_verdict": "approve",
        "review_feedback": "fine",
        "critique_round": 1,
        "critique_history": [],
        "trace": [],
    }


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(supervisor_module, "make_plan", lambda task: "plan")
    monkeypatch.setattr(supervisor_module._critique_loop_graph, "invoke", _fake_critique_invoke)
    monkeypatch.setattr(server_module, "store", SessionStore(max_active=2))
    monkeypatch.delenv("ACCESS_CODE", raising=False)
    return TestClient(server_module.app)


def _wait_for(client, sid, status, headers=None, timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        snap = client.get(f"/api/sessions/{sid}", headers=headers).json()
        if snap["status"] == status:
            return snap
        time.sleep(0.05)
    raise AssertionError(f"never reached {status}: last={snap['status']} error={snap['error']}")


def test_full_flow_pause_then_approve(client):
    sid = client.post("/api/sessions", json={"task": "do a thing"}).json()["id"]

    snap = _wait_for(client, sid, "awaiting_human")
    assert snap["checkpoint"]["code"] == "def f(): pass"
    assert snap["checkpoint"]["steps_remaining"] == 2
    agents = [e["agent"] for e in snap["events"]]
    assert {"system", "supervisor", "coder", "tester", "reviewer"} <= set(agents)

    assert client.post(f"/api/sessions/{sid}/decision", json={"decision": "approve"}).status_code == 200
    done = _wait_for(client, sid, "done")
    assert done["result"]["human_decision"] == "approve"
    assert done["result"]["code"] == "def f(): pass"
    assert done["checkpoint"] is None


def test_events_are_incremental(client):
    sid = client.post("/api/sessions", json={"task": "x"}).json()["id"]
    first = _wait_for(client, sid, "awaiting_human")
    later = client.get(f"/api/sessions/{sid}", params={"since": first["next"]}).json()
    assert later["events"] == []


def test_reject_requires_feedback_and_loops_back(client):
    sid = client.post("/api/sessions", json={"task": "x"}).json()["id"]
    _wait_for(client, sid, "awaiting_human")

    assert client.post(f"/api/sessions/{sid}/decision", json={"decision": "reject"}).status_code == 422

    ok = client.post(f"/api/sessions/{sid}/decision", json={"decision": "reject", "feedback": "faster"})
    assert ok.status_code == 200
    snap = _wait_for(client, sid, "awaiting_human")
    assert snap["checkpoint"]["supervisor_step"] == 2


def test_cannot_decide_when_not_waiting(client):
    sid = client.post("/api/sessions", json={"task": "x"}).json()["id"]
    _wait_for(client, sid, "awaiting_human")
    client.post(f"/api/sessions/{sid}/decision", json={"decision": "approve"})
    _wait_for(client, sid, "done")
    assert client.post(f"/api/sessions/{sid}/decision", json={"decision": "approve"}).status_code == 409


def test_validation_and_unknown_session(client):
    assert client.post("/api/sessions", json={"task": ""}).status_code == 422
    assert client.post("/api/sessions", json={"task": "x" * 5000}).status_code == 422
    assert client.post("/api/sessions", json={"task": "x", "supervisor_max_steps": 99}).status_code == 422
    assert client.get("/api/sessions/nope").status_code == 404


def test_concurrent_session_limit(client):
    for _ in range(2):
        assert client.post("/api/sessions", json={"task": "x"}).status_code == 200
    assert client.post("/api/sessions", json={"task": "x"}).status_code == 429


def test_access_code_enforced(client, monkeypatch):
    monkeypatch.setenv("ACCESS_CODE", "s3cret")
    assert client.post("/api/sessions", json={"task": "x"}).status_code == 401
    assert client.post("/api/sessions", json={"task": "x"}, headers={"X-Access-Code": "wrong"}).status_code == 401
    good = client.post("/api/sessions", json={"task": "x"}, headers={"X-Access-Code": "s3cret"})
    assert good.status_code == 200
    assert client.get("/api/health").json()["access_code_required"] is True


def test_unexpected_failure_is_reported_not_swallowed(client, monkeypatch):
    def boom(task):
        raise RuntimeError("model exploded")

    monkeypatch.setattr(supervisor_module, "make_plan", boom)
    sid = client.post("/api/sessions", json={"task": "x"}).json()["id"]
    snap = _wait_for(client, sid, "error")
    assert "model exploded" in snap["error"]
