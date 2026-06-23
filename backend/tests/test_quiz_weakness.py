from app.repository import MemoryRepository
from app.services.llm import OpenAILearningClient
from app.services.study import StudyService
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


def test_quiz_generation_and_weak_topic_tracking():
    repo = MemoryRepository()
    study = StudyService(repo, OpenAILearningClient(_settings()))
    user = repo.create_user("student@example.com", "hash")

    quiz = study.quiz("photosynthesis", 2)
    repo.record_quiz_attempt(
        user["id"],
        quiz.id,
        [
            {"question_id": quiz.questions[0].id, "topic": "photosynthesis", "correct": False},
            {"question_id": quiz.questions[1].id, "topic": "photosynthesis", "correct": True},
        ],
    )
    weak = study.weak_topics(user["id"])

    assert quiz.questions
    assert all(question.type == "multiple_choice" for question in quiz.questions)
    assert all(len(question.choices) == 4 for question in quiz.questions)
    assert all(question.answer in question.choices for question in quiz.questions)
    assert weak[0].topic == "photosynthesis"
    assert weak[0].misses == 1
    assert "Review photosynthesis" in weak[0].recommendation
