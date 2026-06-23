from datetime import datetime, timezone

from app.repository import MemoryRepository


def test_flashcards_are_saved_due_and_reviewed():
    repo = MemoryRepository()
    user = repo.create_user("student@example.com", "hash")

    saved = repo.save_flashcards(
        user["id"],
        [
            {
                "question": "What is retrieval practice?",
                "answer": "Actively recalling information without looking at notes.",
                "topic": "study skills",
                "source_label": "general_openai",
            }
        ],
    )

    assert repo.list_flashcards(user["id"])[0]["question"] == "What is retrieval practice?"
    assert repo.due_flashcards(user["id"])[0]["id"] == saved[0]["id"]

    reviewed = repo.review_flashcard(user["id"], saved[0]["id"], "good")

    assert reviewed is not None
    assert reviewed["interval_days"] >= 1
    assert datetime.fromisoformat(reviewed["due_at"]).date() > datetime.now(timezone.utc).date()
    assert repo.due_flashcards(user["id"]) == []


def test_quizzes_study_plans_and_attempt_details_are_persisted():
    repo = MemoryRepository()
    user = repo.create_user("student@example.com", "hash")

    questions = [
        {
            "id": "q1",
            "type": "multiple_choice",
            "prompt": "Which choice best describes RAG?",
            "choices": ["Retrieval plus generation", "Only memorization", "Only OCR", "Only storage"],
            "answer": "Retrieval plus generation",
            "topic": "rag",
            "explanation": "RAG retrieves context before generating an answer.",
        }
    ]
    repo.save_quiz(user["id"], "quiz-1", "general_openai", questions, {"provider": "test"})
    repo.save_study_plan(user["id"], ["Review RAG"], ["rag"], {"source": "test"})
    repo.record_quiz_attempt(
        user["id"],
        "quiz-1",
        [
            {
                "question_id": "q1",
                "topic": "rag",
                "selected_answer": "Only memorization",
                "correct_answer": "Retrieval plus generation",
                "correct": False,
            }
        ],
    )

    assert repo.list_quizzes(user["id"])[0]["questions"][0]["answer"] == "Retrieval plus generation"
    assert repo.list_study_plans(user["id"])[0]["focus_topics"] == ["rag"]
    assert repo.weak_topics(user["id"])[0]["topic"] == "rag"
