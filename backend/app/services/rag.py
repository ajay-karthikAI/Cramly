from __future__ import annotations

import json
import re

from app.schemas import AnswerDepth, Citation, ChatResponse, RetrievedChunk, SourceLabel
from app.services.documents import chunk_text
from app.services.llm import OpenAILearningClient


MIN_RELEVANT_SCORE = 0.10
PARTIAL_RELEVANT_SCORE = 0.12
STRONG_RELEVANT_SCORE = 0.24
ANSWER_CONTEXT_LIMIT = 8
SEARCH_CANDIDATE_LIMIT = 10
GENERAL_SOURCE_HEADING = "OpenAI general knowledge"


class RagService:
    def __init__(self, repo, llm: OpenAILearningClient):
        self.repo = repo
        self.llm = llm

    def ingest_document(self, document_id: str, text: str, chunks: list[dict] | None = None) -> dict:
        chunks = chunk_text(text) if chunks is None else chunks
        if not chunks:
            self.repo.update_document_status(document_id, "empty", 0)
            return {"chunks": 0, "embedding_metadata": {}}
        embeddings, metadata = self.llm.embed_texts([chunk["text"] for chunk in chunks])
        self.repo.insert_chunks(document_id, chunks, embeddings)
        self.repo.update_document_status(document_id, "indexed", len(chunks))
        return {"chunks": len(chunks), "embedding_metadata": metadata}

    def retrieve(
        self,
        question: str,
        user_id: str,
        limit: int = 5,
        document_id: str | None = None,
    ) -> tuple[list[RetrievedChunk], dict]:
        queries, rewrite_metadata = self._rewrite_queries(question)
        embeddings, embed_metadata = self.llm.embed_texts(queries)
        candidates: dict[str, RetrievedChunk] = {}
        search_limit = max(limit, SEARCH_CANDIDATE_LIMIT)

        for embedding in embeddings:
            rows = self.repo.search_chunks(user_id, embedding, limit=search_limit, document_id=document_id)
            for row in rows:
                chunk = RetrievedChunk(
                    id=row["id"],
                    document_id=row["document_id"],
                    document_name=row["document_name"],
                    section=row["section"],
                    text=row["text"],
                    score=float(row.get("score") or 0),
                )
                existing = candidates.get(chunk.id)
                if not existing or chunk.score > existing.score:
                    candidates[chunk.id] = chunk

        reranked = rerank_chunks(question, list(candidates.values()))
        filtered = [chunk for chunk in reranked if chunk.score >= MIN_RELEVANT_SCORE]
        metadata = {
            "embedding": embed_metadata,
            "query_rewrite": rewrite_metadata,
            "queries": queries,
            "candidate_count": len(candidates),
            "returned_count": len(filtered[:limit]),
            "thresholds": {
                "minimum": MIN_RELEVANT_SCORE,
                "partial": PARTIAL_RELEVANT_SCORE,
                "strong": STRONG_RELEVANT_SCORE,
            },
        }
        return filtered[:limit], metadata

    def answer(self, question: str, user_id: str, mode: str = "auto", depth: AnswerDepth = "standard") -> ChatResponse:
        retrieved, retrieval_metadata = self.retrieve(question, user_id, limit=ANSWER_CONTEXT_LIMIT)
        label = classify_source(mode, retrieved, question)
        metadata = {"retrieval": retrieval_metadata, "retrieved_count": len(retrieved), "depth": depth}

        if label == "general_openai":
            answer, chat_metadata = self._general_answer(question, depth)
            metadata["chat"] = chat_metadata
            return ChatResponse(
                answer=f"{GENERAL_SOURCE_HEADING}\n\n{answer}",
                source_label=label,
                general_explanation=answer,
                retrieved_chunks=[],
                metadata=metadata,
            )

        materials_answer, materials_metadata = self._materials_answer(question, retrieved, depth)
        metadata["materials_chat"] = materials_metadata
        citations = citations_for(retrieved)

        if label == "uploaded_materials":
            return ChatResponse(
                answer=f"From your materials\n\n{materials_answer}",
                source_label=label,
                from_materials=materials_answer,
                citations=citations,
                retrieved_chunks=retrieved,
                metadata=metadata,
            )

        general_answer, general_metadata = self._general_answer(question, depth)
        metadata["general_chat"] = general_metadata
        return ChatResponse(
            answer=f"From your materials\n\n{materials_answer}\n\n{GENERAL_SOURCE_HEADING}\n\n{general_answer}",
            source_label="hybrid",
            from_materials=materials_answer,
            general_explanation=general_answer,
            citations=citations,
            retrieved_chunks=retrieved,
            metadata=metadata,
        )

    def _materials_answer(self, question: str, chunks: list[RetrievedChunk], depth: AnswerDepth) -> tuple[str, dict]:
        if not chunks:
            return "I could not find matching uploaded material for that question.", {"provider": "none"}

        context = "\n\n".join(
            f"[Source {index}: {chunk.document_name} | {chunk.section}]\n{chunk.text}"
            for index, chunk in enumerate(chunks, start=1)
        )
        detail = depth_instruction(depth)
        prompt = (
            "Use only the uploaded-material excerpts below. If the excerpts are incomplete, say what is missing. "
            f"{detail} "
            "Use 2-4 short sections with useful headings. Include mechanisms, examples, and likely exam connections. "
            "Do not include internal source ids, UUIDs, "
            "chunk ids, or parenthesized citation codes in the student-facing answer.\n\n"
            f"Question: {question}\n\nUploaded-material excerpts:\n{context}"
        )
        return self.llm.chat(
            [
                {"role": "system", "content": "You are Cramly, a careful AI learning companion for students."},
                {"role": "user", "content": prompt},
            ]
        )

    def _general_answer(self, question: str, depth: AnswerDepth) -> tuple[str, dict]:
        detail = depth_instruction(depth)
        blueprint = general_answer_blueprint(depth)
        prompt = (
            "Answer from OpenAI general model knowledge only. Do not imply you found this in uploaded files, "
            "course notes, web pages, or live internet search. If a claim may depend on current facts, say the "
            "student should verify it with an up-to-date source. "
            f"{detail}\n\n"
            f"{blueprint}\n\n"
            f"Question: {question}"
        )
        return self.llm.chat(
            [
                {"role": "system", "content": "You are Cramly, a friendly tutor for exam prep."},
                {"role": "user", "content": prompt},
            ]
        )

    def _rewrite_queries(self, question: str) -> tuple[list[str], dict]:
        prompt = (
            "Rewrite this student question into search queries for retrieving course notes. "
            "Return JSON with a queries array of 2-4 concise queries. Include synonyms and academic wording. "
            "Keep the original meaning and do not answer the question.\n\n"
            f"Question: {question}"
        )
        try:
            content, metadata = self.llm.chat(
                [
                    {"role": "system", "content": "You improve retrieval queries for a study-notes RAG system."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0,
                json_mode=True,
            )
            data = json.loads(content)
            rewritten = [str(query).strip() for query in data.get("queries", []) if str(query).strip()]
        except Exception:
            rewritten = []
            metadata = {"provider": "fallback", "error": "query rewrite failed"}

        queries = [question]
        for query in rewritten:
            if query.lower() not in {value.lower() for value in queries}:
                queries.append(query)
        return queries[:4], metadata


def classify_source(mode: str, chunks: list[RetrievedChunk], question: str = "") -> SourceLabel:
    if mode == "general":
        return "general_openai"
    top_score = chunks[0].score if chunks else 0

    if mode == "materials":
        return "uploaded_materials" if chunks else "general_openai"
    if mode == "hybrid":
        return "hybrid" if chunks else "general_openai"

    lowered = question.lower()
    material_intent = any(
        phrase in lowered
        for phrase in [
            "my professor",
            "my notes",
            "uploaded",
            "from the notes",
            "according to",
            "lecture",
            "class notes",
            "study guide",
            "textbook",
            "pdf",
        ]
    )
    if material_intent and chunks and top_score >= PARTIAL_RELEVANT_SCORE:
        return "uploaded_materials"
    if top_score >= STRONG_RELEVANT_SCORE:
        return "uploaded_materials"
    if top_score >= PARTIAL_RELEVANT_SCORE:
        return "hybrid"
    return "general_openai"


def citations_for(chunks: list[RetrievedChunk]) -> list[Citation]:
    return [
        Citation(
            document_id=chunk.document_id,
            document_name=chunk.document_name,
            section=chunk.section,
            chunk_id=chunk.id,
            score=round(chunk.score, 4),
        )
        for chunk in chunks
    ]


def rerank_chunks(question: str, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
    question_terms = set(_terms(question))
    reranked = []
    for chunk in chunks:
        chunk_terms = set(_terms(chunk.text))
        overlap = len(question_terms & chunk_terms) / max(1, len(question_terms))
        section_bonus = 0.02 if any(label in chunk.section.lower() for label in ["page", "slide"]) else 0
        score = min(1.0, (chunk.score * 0.82) + (overlap * 0.16) + section_bonus)
        reranked.append(chunk.model_copy(update={"score": score}))
    return sorted(reranked, key=lambda chunk: chunk.score, reverse=True)


def depth_instruction(depth: AnswerDepth) -> str:
    if depth == "advanced":
        return (
            "Give a rigorous expert-level breakdown: define terms precisely, explain mechanisms, assumptions, edge cases, "
            "limitations, and how the concept connects to adjacent theory. Stay readable but do not oversimplify."
        )
    return (
        "Give a strong study-mode breakdown: define the idea, explain how it works, why it matters, and include "
        "an example or analogy. Be more detailed than a simple summary and aim for exam-ready understanding."
    )


def general_answer_blueprint(depth: AnswerDepth) -> str:
    if depth == "advanced":
        return (
            "Use these sections when helpful: Precise definition, Mechanism or model, Assumptions and limitations, "
            "Edge cases, Connections to adjacent concepts, and Research-level takeaway. Include equations, terminology, "
            "or technical distinctions only when they help understanding."
        )
    return (
        "Use these sections when helpful: Big idea, How it works, Why it matters, Example or analogy, Common mistake, "
        "and Quick self-check. Keep it clear, but give enough detail that a student can explain it back."
    )


def _terms(text: str) -> list[str]:
    stopwords = {
        "about",
        "after",
        "also",
        "and",
        "are",
        "because",
        "did",
        "does",
        "from",
        "how",
        "into",
        "say",
        "the",
        "their",
        "this",
        "what",
        "when",
        "where",
        "with",
    }
    return [term for term in re.findall(r"[a-zA-Z][a-zA-Z\-]{2,}", text.lower()) if term not in stopwords]
