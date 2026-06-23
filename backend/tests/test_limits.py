from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from app import main as main_module
from app.config import CHAT_QUESTION_MAX_LENGTH
from app.repository import MemoryRepository
from app.schemas import ChatResponse
from app.services.auth import create_access_token


class StubRag:
    def answer(self, question: str, user_id: str, mode: str = "auto", depth: str = "standard") -> ChatResponse:
        return ChatResponse(
            answer="Test answer",
            source_label="general_openai",
            general_explanation="Test answer",
            metadata={"provider": "test"},
        )


@pytest.fixture()
def limits_api(monkeypatch):
    repo = MemoryRepository()
    user = repo.create_user("student@example.com", "hash")
    settings = replace(
        main_module.settings,
        allow_demo_mode=True,
        daily_chat_limit=100,
        daily_upload_limit=100,
        daily_generation_limit=100,
        auth_rate_limit_per_minute=0,
        ai_rate_limit_per_minute=0,
    )
    monkeypatch.setattr(main_module, "settings", settings)
    monkeypatch.setattr(main_module, "repo", repo)
    monkeypatch.setattr(main_module, "rag", StubRag())
    main_module.rate_limiter.reset()
    token = create_access_token(user["id"], settings.jwt_secret, 10)
    headers = {"Authorization": f"Bearer {token}"}

    with TestClient(main_module.app) as client:
        yield client, repo, user, headers

    main_module.rate_limiter.reset()


def test_oversized_upload_is_rejected_before_document_creation(limits_api, monkeypatch):
    client, repo, user, headers = limits_api
    monkeypatch.setattr(main_module, "settings", replace(main_module.settings, max_upload_bytes=4))

    response = client.post(
        "/api/uploads",
        headers=headers,
        files={"file": ("notes.txt", b"too large", "text/plain")},
    )

    assert response.status_code == 413
    assert "Upload exceeds" in response.json()["detail"]
    assert repo.list_documents(user["id"]) == []


def test_overlong_chat_question_fails_validation(limits_api):
    client, _, _, headers = limits_api

    response = client.post(
        "/api/chat",
        headers=headers,
        json={"question": "x" * (CHAT_QUESTION_MAX_LENGTH + 1)},
    )

    assert response.status_code == 422


def test_daily_chat_quota_returns_429_after_configured_limit(limits_api, monkeypatch):
    client, _, _, headers = limits_api
    monkeypatch.setattr(main_module, "settings", replace(main_module.settings, daily_chat_limit=1))

    first = client.post("/api/chat", headers=headers, json={"question": "Explain cells."})
    second = client.post("/api/chat", headers=headers, json={"question": "Explain ATP."})

    assert first.status_code == 200
    assert second.status_code == 429
    assert second.json()["detail"] == "Daily chat limit reached. Try again tomorrow."


def test_rate_limiter_returns_429_on_burst_requests(limits_api, monkeypatch):
    client, _, _, headers = limits_api
    monkeypatch.setattr(
        main_module,
        "settings",
        replace(main_module.settings, ai_rate_limit_per_minute=1, daily_chat_limit=100),
    )

    first = client.post("/api/chat", headers=headers, json={"question": "Explain cells."})
    second = client.post("/api/chat", headers=headers, json={"question": "Explain ATP."})

    assert first.status_code == 200
    assert second.status_code == 429
    assert second.json()["detail"] == "Too many requests. Please wait briefly and try again."
