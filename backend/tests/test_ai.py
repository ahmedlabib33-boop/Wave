from app.db import Session, Source


def test_ai_brief_needs_server_side_groq_key(client, monkeypatch):
    monkeypatch.setattr("app.ai.configured", lambda: False)
    response = client.post("/api/ai/brief", json={"question": "Summarize current source availability.", "language": "en"})
    assert response.status_code == 409
    assert "GROQ_API_KEY" in response.json()["detail"]


def test_ai_brief_uses_bounded_attributed_context_and_never_creates_observations(client, monkeypatch):
    seen = {}

    async def completion(payload):
        seen.update(payload)
        return "No current object observations are stored in the supplied hub context."

    monkeypatch.setattr("app.ai.configured", lambda: True)
    monkeypatch.setattr("app.ai.request_completion", completion)
    response = client.post("/api/ai/brief", json={"question": "What is known now?", "language": "en"})
    assert response.status_code == 200
    result = response.json()
    assert result["provider"] == "Groq"
    assert result["observation_count_included"] == 0
    assert "No current object" in result["analysis"]
    assert '"raw":' not in seen["messages"][1]["content"]
    assert client.get("/api/observations").json() == []
    with Session() as db:
        source = db.get(Source, "groq_ai")
        assert source.status == "available" and source.last_count == 0
