from dataclasses import replace

from fastapi.testclient import TestClient

from app import main as main_module
from app.repository import MemoryRepository
from app.schemas import RetrievedChunk
from app.services.auth import create_access_token


class StubRag:
    def __init__(self):
        self.calls: list[tuple[str, str]] = []

    def retrieve(self, question: str, user_id: str):
        self.calls.append((question, user_id))
        return (
            [
                RetrievedChunk(
                    id="chunk-1",
                    document_id="doc-1",
                    document_name="lecture.pdf",
                    section="page 4, chunk 2",
                    text="ATP and NADPH appear in the light reactions.",
                    score=0.84,
                )
            ],
            {
                "embedding": {"provider": "test"},
                "query_rewrite": {"provider": "test"},
                "queries": [question],
                "candidate_count": 1,
                "returned_count": 1,
                "thresholds": {"minimum": 0.1, "partial": 0.12, "strong": 0.24},
            },
        )


def _dev_rag_client(monkeypatch, *, enabled: bool):
    repo = MemoryRepository()
    user = repo.create_user("student@example.com", "hash")
    settings = replace(
        main_module.settings,
        allow_demo_mode=True,
        enable_dev_rag=enabled,
        openai_model="test-chat-model",
        openai_embedding_model="test-embedding-model",
    )
    rag = StubRag()
    monkeypatch.setattr(main_module, "settings", settings)
    monkeypatch.setattr(main_module, "repo", repo)
    monkeypatch.setattr(main_module, "rag", rag)
    token = create_access_token(user["id"], settings.jwt_secret, 10)
    headers = {"Authorization": f"Bearer {token}"}
    return repo, user, settings, rag, headers


def test_dev_rag_is_blocked_when_flag_is_false(monkeypatch):
    _, _, _, rag, headers = _dev_rag_client(monkeypatch, enabled=False)

    with TestClient(main_module.app) as client:
        response = client.get("/api/dev/rag?question=What%20is%20ATP%3F", headers=headers)

    assert response.status_code == 404
    assert response.json()["detail"] == "Dev RAG inspector is disabled."
    assert rag.calls == []


def test_dev_rag_preserves_response_shape_when_flag_is_true(monkeypatch):
    _, user, settings, rag, headers = _dev_rag_client(monkeypatch, enabled=True)

    with TestClient(main_module.app) as client:
        response = client.get("/api/dev/rag?question=What%20is%20ATP%3F", headers=headers)

    expected_metadata = {
        "embedding": {"provider": "test"},
        "query_rewrite": {"provider": "test"},
        "queries": ["What is ATP?"],
        "candidate_count": 1,
        "returned_count": 1,
        "thresholds": {"minimum": 0.1, "partial": 0.12, "strong": 0.24},
    }
    expected_chunk = {
        "id": "chunk-1",
        "document_id": "doc-1",
        "document_name": "lecture.pdf",
        "section": "page 4, chunk 2",
        "text": "ATP and NADPH appear in the light reactions.",
        "score": 0.84,
    }

    assert response.status_code == 200
    assert response.json() == {
        "question": "What is ATP?",
        "embedding": expected_metadata,
        "pipeline": [
            "extract text",
            "chunk with LangChain splitter or fallback",
            "embed with OpenAI embeddings",
            "store/search pgvector",
            "answer with source label",
        ],
        "retrieved_chunks": [expected_chunk],
        "openai": {
            "chat_model": settings.openai_model,
            "embedding_model": settings.openai_embedding_model,
            "demo_mode": settings.demo_mode,
        },
    }
    assert rag.calls == [("What is ATP?", user["id"])]
