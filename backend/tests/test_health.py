"""API contract and health endpoint tests."""
from __future__ import annotations


def test_health_contract(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "healthy"
    assert "mode" in body
    assert body["mode"] in ("demo", "live")


def test_chat_required_fields(client):
    r = client.post(
        "/api/v1/chat",
        json={"user_id": "u1", "message": "Does my policy cover burst pipes?"},
    )
    assert r.status_code == 200
    body = r.json()
    # Mandatory contract fields.
    assert "response" in body
    assert "sources" in body and isinstance(body["sources"], list)
    assert "tool_calls" in body and isinstance(body["tool_calls"], list)
    assert "message_type" in body
    assert "data" in body


def test_chat_requires_user_id(client):
    r = client.post("/api/v1/chat", json={"message": "hi"})
    assert r.status_code == 422


def test_chat_empty_message_rejected(client):
    r = client.post("/api/v1/chat", json={"user_id": "u1", "message": ""})
    assert r.status_code == 422


def test_coverage_burst_pipes(client):
    r = client.post(
        "/api/v1/chat",
        json={"user_id": "u1", "message": "Does my policy cover burst pipes?"},
    ).json()
    assert r["message_type"] == "coverage_answer"
    assert r["data"]["verdict"] == "covered"
    assert any(s["id"] == "sec1" for s in r["sources"])
    # Citations reference a real passage.
    assert "$25,000" in r["sources"][0]["text"]


def test_request_id_echo(client):
    r = client.post(
        "/api/v1/chat",
        json={"user_id": "u1", "message": "hello", "request_id": "abc123"},
    ).json()
    assert r["request_id"] == "abc123"
