from app.schemas import RetrievedChunk
from app.services.rag import citations_for, classify_source


def test_chat_source_classifier_labels_material_general_and_hybrid():
    strong = [
        RetrievedChunk(
            id="c1",
            document_id="d1",
            document_name="notes.txt",
            section="page 2",
            text="relevant",
            score=0.91,
        )
    ]
    partial = [strong[0].model_copy(update={"score": 0.12})]

    assert classify_source("auto", strong) == "uploaded_materials"
    assert classify_source("auto", partial) == "hybrid"
    assert classify_source("general", strong) == "general_openai"
    assert classify_source("auto", [strong[0].model_copy(update={"score": 0.12})], "what did my professor say?") == "uploaded_materials"


def test_citations_keep_document_and_chunk_identity():
    chunks = [
        RetrievedChunk(
            id="chunk-1",
            document_id="doc-1",
            document_name="lecture.pdf",
            section="page 4, chunk 2",
            text="ATP and NADPH appear in the light reactions.",
            score=0.84,
        )
    ]

    citation = citations_for(chunks)[0]

    assert citation.document_name == "lecture.pdf"
    assert citation.section == "page 4, chunk 2"
    assert citation.chunk_id == "chunk-1"
