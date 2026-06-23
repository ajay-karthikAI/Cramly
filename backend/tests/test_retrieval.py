from app.repository import MemoryRepository
from app.services.documents import extract_keywords
from app.services.llm import OpenAILearningClient
from app.services.rag import RagService
from app.config import Settings


def _settings():
    return Settings(
        openai_api_key=None,
        openai_model="test-chat",
        openai_embedding_model="test-embed",
        database_url=None,
        s3_endpoint_url=None,
        s3_access_key_id=None,
        s3_secret_access_key=None,
        s3_bucket="test",
        cors_origins=[],
        local_storage_path="storage",
        jwt_secret="test-secret",
        access_token_minutes=60,
        allow_demo_mode=True,
    )


def test_ingestion_and_retrieval_prioritizes_matching_notes():
    repo = MemoryRepository()
    rag = RagService(repo, OpenAILearningClient(_settings()))
    text = "Photosynthesis uses chlorophyll to capture light. The Calvin cycle builds sugar."
    user = repo.create_user("student@example.com", "hash")
    doc = repo.create_document(user["id"], "bio.txt", "local", text, extract_keywords(text))

    result = rag.ingest_document(doc["id"], text)
    chunks, _ = rag.retrieve("What did my professor say about chlorophyll?", user["id"])

    assert result["chunks"] == 1
    assert chunks[0].document_name == "bio.txt"
    assert "chlorophyll" in chunks[0].text.lower()
