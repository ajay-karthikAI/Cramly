from app.config import Settings
from app.repository import MemoryRepository
from app.services.documents import extract_keywords
from app.services.llm import OpenAILearningClient
from app.services.rag import RagService, classify_source, depth_instruction, general_answer_blueprint, rerank_chunks
from app.schemas import RetrievedChunk


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


def test_sample_course_notes_retrieve_expected_page():
    repo = MemoryRepository()
    rag = RagService(repo, OpenAILearningClient(_settings()))
    user = repo.create_user("eval@example.com", "hash")
    notes = """
    [page 1]
    Cellular respiration harvests energy from glucose.

    [page 4]
    Rubisco fixes carbon dioxide during the Calvin cycle. This carbon fixation step starts sugar building in photosynthesis.

    [page 9]
    Meiosis creates genetic variation through crossing over and independent assortment.
    """
    doc = repo.create_document(user["id"], "sample-biology-notes.pdf", "local", notes, extract_keywords(notes))
    rag.ingest_document(doc["id"], notes)

    chunks, metadata = rag.retrieve("How does Rubisco fix carbon dioxide in the Calvin cycle?", user["id"])

    assert chunks
    assert chunks[0].section.startswith("page 4")
    assert "rubisco" in chunks[0].text.lower()
    assert metadata["candidate_count"] >= 1


def test_unrelated_sample_notes_do_not_force_material_answer():
    chunks = [
        RetrievedChunk(
            id="c1",
            document_id="d1",
            document_name="history.pdf",
            section="page 2",
            text="The Roman Republic used consuls and a senate.",
            score=0.05,
        )
    ]

    assert classify_source("auto", chunks, "Explain chlorophyll fluorescence") == "general_openai"


def test_reranking_prefers_keyword_overlap_and_depth_prompts_are_distinct():
    chunks = [
        RetrievedChunk(
            id="weak",
            document_id="d1",
            document_name="bio.pdf",
            section="page 1",
            text="Plants use energy in many processes.",
            score=0.20,
        ),
        RetrievedChunk(
            id="strong",
            document_id="d1",
            document_name="bio.pdf",
            section="page 4",
            text="Chlorophyll absorbs photons during photosynthesis light reactions.",
            score=0.18,
        ),
    ]

    reranked = rerank_chunks("How does chlorophyll absorb photons in photosynthesis?", chunks)

    assert reranked[0].id == "strong"
    assert "exam-ready" in depth_instruction("standard")
    assert "expert-level" in depth_instruction("advanced")
    assert "Common mistake" in general_answer_blueprint("standard")
    assert "Assumptions and limitations" in general_answer_blueprint("advanced")
