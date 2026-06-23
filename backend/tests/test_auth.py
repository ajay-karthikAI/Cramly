import pytest

from app.repository import MemoryRepository
from app.services.auth import (
    AuthError,
    create_access_token,
    hash_password,
    normalize_email,
    verify_access_token,
    verify_password,
)


def test_password_hashing_and_session_token_round_trip():
    password_hash = hash_password("correct horse battery")
    token = create_access_token("user-123", "test-secret", 10)

    assert password_hash != "correct horse battery"
    assert verify_password("correct horse battery", password_hash)
    assert not verify_password("wrong password", password_hash)
    assert verify_access_token(token, "test-secret") == "user-123"
    assert normalize_email(" Student@Example.com ") == "student@example.com"

    with pytest.raises(AuthError):
        normalize_email("not-an-email")


def test_memory_repository_keeps_user_documents_and_weak_topics_private():
    repo = MemoryRepository()
    alice = repo.create_user("alice@example.com", "hash-a")
    bob = repo.create_user("bob@example.com", "hash-b")

    alice_doc = repo.create_document(alice["id"], "alice-notes.txt", "local-a", "Light reactions", ["light"])
    bob_doc = repo.create_document(bob["id"], "bob-notes.txt", "local-b", "Ionic bonds", ["bonds"])
    repo.insert_chunks(alice_doc["id"], [{"section": "chunk 1", "text": "Chlorophyll captures light."}], [[1.0, 0.0]])
    repo.insert_chunks(bob_doc["id"], [{"section": "chunk 1", "text": "Ions transfer electrons."}], [[0.0, 1.0]])

    assert repo.get_document(bob["id"], alice_doc["id"]) is None
    assert [document["name"] for document in repo.list_documents(alice["id"])] == ["alice-notes.txt"]
    assert repo.search_chunks(alice["id"], [1.0, 0.0])[0]["document_name"] == "alice-notes.txt"

    repo.record_quiz_attempt(
        alice["id"],
        "quiz-a",
        [{"question_id": "q1", "topic": "photosynthesis", "correct": False}],
    )
    repo.record_quiz_attempt(
        bob["id"],
        "quiz-b",
        [{"question_id": "q1", "topic": "bonding", "correct": False}],
    )

    assert repo.weak_topics(alice["id"])[0]["topic"] == "photosynthesis"
    assert repo.weak_topics(bob["id"])[0]["topic"] == "bonding"
