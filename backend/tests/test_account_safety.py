from dataclasses import replace
import uuid

import pytest
from fastapi.testclient import TestClient

from app import main as main_module
from app.repository import MemoryRepository
from app.services.auth import create_access_token, hash_password, verify_password


OLD_PASSWORD = "old-password-123"
NEW_PASSWORD = "new-password-456"


@pytest.fixture()
def safety_api(monkeypatch):
    repo = MemoryRepository()
    settings = replace(
        main_module.settings,
        invite_code=None,
        auth_rate_limit_per_minute=100,
        ai_rate_limit_per_minute=100,
    )
    monkeypatch.setattr(main_module, "settings", settings)
    monkeypatch.setattr(main_module, "repo", repo)
    main_module.rate_limiter.reset()

    with TestClient(main_module.app) as client:
        yield client, repo, settings

    main_module.rate_limiter.reset()


def _register(client: TestClient, email: str = "student@example.com", password: str = OLD_PASSWORD):
    response = client.post("/api/auth/register", json={"email": email, "password": password})
    assert response.status_code == 200
    body = response.json()
    return body["user"], {"Authorization": f"Bearer {body['access_token']}"}


def test_change_password_succeeds_with_correct_current_password(safety_api):
    client, repo, _ = safety_api
    user, headers = _register(client)

    response = client.post(
        "/api/auth/change-password",
        headers=headers,
        json={"current_password": OLD_PASSWORD, "new_password": NEW_PASSWORD},
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    updated_user = repo.get_user_by_id(user["id"])
    assert updated_user is not None
    assert verify_password(NEW_PASSWORD, updated_user["password_hash"])


def test_change_password_fails_with_wrong_current_password(safety_api):
    client, repo, _ = safety_api
    user, headers = _register(client)

    response = client.post(
        "/api/auth/change-password",
        headers=headers,
        json={"current_password": "wrong-password", "new_password": NEW_PASSWORD},
    )

    assert response.status_code == 400
    unchanged_user = repo.get_user_by_id(user["id"])
    assert unchanged_user is not None
    assert verify_password(OLD_PASSWORD, unchanged_user["password_hash"])


def test_old_password_no_longer_works_after_change(safety_api):
    client, _, _ = safety_api
    _, headers = _register(client)

    changed = client.post(
        "/api/auth/change-password",
        headers=headers,
        json={"current_password": OLD_PASSWORD, "new_password": NEW_PASSWORD},
    )
    old_login = client.post("/api/auth/login", json={"email": "student@example.com", "password": OLD_PASSWORD})
    new_login = client.post("/api/auth/login", json={"email": "student@example.com", "password": NEW_PASSWORD})

    assert changed.status_code == 200
    assert old_login.status_code == 401
    assert new_login.status_code == 200
    assert new_login.json()["access_token"]


def test_account_deletion_removes_user_access_and_owned_data(safety_api):
    client, repo, settings = safety_api
    alice = repo.create_user("alice@example.com", hash_password(OLD_PASSWORD))
    bob = repo.create_user("bob@example.com", hash_password(OLD_PASSWORD))
    alice_headers = {"Authorization": f"Bearer {create_access_token(alice['id'], settings.jwt_secret, 10)}"}

    alice_doc = repo.create_document(alice["id"], "alice-notes.txt", "local-a", "Light reactions", ["light"])
    bob_doc = repo.create_document(bob["id"], "bob-notes.txt", "local-b", "Ionic bonds", ["bonds"])
    repo.insert_chunks(alice_doc["id"], [{"section": "chunk 1", "text": "Chlorophyll captures light."}], [[1.0, 0.0]])
    repo.insert_chunks(bob_doc["id"], [{"section": "chunk 1", "text": "Ions transfer electrons."}], [[0.0, 1.0]])
    repo.save_flashcards(
        alice["id"],
        [{"question": "What captures light?", "answer": "Chlorophyll", "topic": "biology", "source_label": "uploaded_materials"}],
    )
    repo.save_quiz(
        alice["id"],
        str(uuid.uuid4()),
        "uploaded_materials",
        [{"id": "q1", "type": "multiple_choice", "prompt": "Question", "choices": ["A"], "answer": "A", "topic": "biology", "explanation": "Because."}],
        {"source": "test"},
    )
    repo.save_study_plan(alice["id"], ["Review biology"], ["biology"], {"source": "test"})
    repo.record_quiz_attempt(alice["id"], "quiz-a", [{"question_id": "q1", "topic": "biology", "correct": False}])
    repo.increment_daily_usage(alice["id"], "chat", "2026-06-23")

    deleted = client.delete("/api/auth/account", headers=alice_headers)
    old_session = client.get("/api/auth/me", headers=alice_headers)

    assert deleted.status_code == 200
    assert deleted.json() == {"ok": True}
    assert old_session.status_code == 401
    assert repo.get_user_by_id(alice["id"]) is None
    assert repo.list_documents(alice["id"]) == []
    assert repo.search_chunks(alice["id"], [1.0, 0.0]) == []
    assert repo.list_flashcards(alice["id"]) == []
    assert repo.list_quizzes(alice["id"]) == []
    assert repo.list_study_plans(alice["id"]) == []
    assert repo.weak_topics(alice["id"]) == []
    assert repo.get_daily_usage(alice["id"], "chat", "2026-06-23") == 0
    assert repo.get_user_by_id(bob["id"]) is not None
    assert repo.get_document(bob["id"], bob_doc["id"]) is not None


def test_document_deletion_only_deletes_owned_documents(safety_api):
    client, repo, settings = safety_api
    alice = repo.create_user("alice@example.com", hash_password(OLD_PASSWORD))
    bob = repo.create_user("bob@example.com", hash_password(OLD_PASSWORD))
    alice_headers = {"Authorization": f"Bearer {create_access_token(alice['id'], settings.jwt_secret, 10)}"}
    bob_headers = {"Authorization": f"Bearer {create_access_token(bob['id'], settings.jwt_secret, 10)}"}
    alice_doc = repo.create_document(alice["id"], "alice-notes.txt", "local-a", "Light reactions", ["light"])
    bob_doc = repo.create_document(bob["id"], "bob-notes.txt", "local-b", "Ionic bonds", ["bonds"])
    repo.insert_chunks(alice_doc["id"], [{"section": "chunk 1", "text": "Chlorophyll captures light."}], [[1.0, 0.0]])
    repo.insert_chunks(bob_doc["id"], [{"section": "chunk 1", "text": "Ions transfer electrons."}], [[0.0, 1.0]])

    denied = client.delete(f"/api/documents/{alice_doc['id']}", headers=bob_headers)

    assert denied.status_code == 404
    assert repo.get_document(alice["id"], alice_doc["id"]) is not None
    assert repo.get_document(bob["id"], bob_doc["id"]) is not None
    deleted = client.delete(f"/api/documents/{alice_doc['id']}", headers=alice_headers)

    assert deleted.status_code == 200
    assert deleted.json() == {"ok": True}
    assert repo.get_document(alice["id"], alice_doc["id"]) is None
    assert repo.search_chunks(alice["id"], [1.0, 0.0]) == []
    assert repo.get_document(bob["id"], bob_doc["id"]) is not None
    assert repo.search_chunks(bob["id"], [0.0, 1.0])[0]["document_name"] == "bob-notes.txt"


def test_invite_code_not_required_when_unconfigured(safety_api):
    client, _, _ = safety_api

    response = client.post("/api/auth/register", json={"email": "open@example.com", "password": OLD_PASSWORD})

    assert response.status_code == 200
    assert response.json()["access_token"]


def test_invite_code_required_when_configured(safety_api, monkeypatch):
    client, _, settings = safety_api
    monkeypatch.setattr(main_module, "settings", replace(settings, invite_code="beta-123"))

    missing = client.post("/api/auth/register", json={"email": "missing@example.com", "password": OLD_PASSWORD})
    wrong = client.post(
        "/api/auth/register",
        json={"email": "wrong@example.com", "password": OLD_PASSWORD, "invite_code": "not-it"},
    )
    correct = client.post(
        "/api/auth/register",
        json={"email": "correct@example.com", "password": OLD_PASSWORD, "invite_code": "beta-123"},
    )

    assert missing.status_code == 403
    assert wrong.status_code == 403
    assert correct.status_code == 200
    assert correct.json()["access_token"]
