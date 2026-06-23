from typing import Literal

from pydantic import BaseModel, Field

from app.config import CHAT_QUESTION_MAX_LENGTH, TOPIC_MAX_LENGTH


SourceLabel = Literal["uploaded_materials", "general_openai", "hybrid"]
AnswerDepth = Literal["standard", "advanced"]


class UserCreate(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=8, max_length=128)
    invite_code: str | None = Field(default=None, max_length=128)


class UserLogin(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=8, max_length=128)


class UserOut(BaseModel):
    id: str
    email: str
    created_at: str | None = None


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=8, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class SuccessResponse(BaseModel):
    ok: bool = True


class Citation(BaseModel):
    document_id: str
    document_name: str
    section: str
    chunk_id: str
    score: float = 0


class RetrievedChunk(BaseModel):
    id: str
    document_id: str
    document_name: str
    section: str
    text: str
    score: float = 0


class DocumentOut(BaseModel):
    id: str
    name: str
    status: str
    chunks: int = 0
    keywords: list[str] = []
    storage_key: str | None = None
    created_at: str | None = None


class ChatRequest(BaseModel):
    question: str = Field(min_length=2, max_length=CHAT_QUESTION_MAX_LENGTH)
    mode: Literal["auto", "materials", "general", "hybrid"] = "auto"
    depth: AnswerDepth = "standard"


class ChatResponse(BaseModel):
    answer: str
    source_label: SourceLabel
    from_materials: str | None = None
    general_explanation: str | None = None
    citations: list[Citation] = []
    retrieved_chunks: list[RetrievedChunk] = []
    metadata: dict = {}


class FlashcardRequest(BaseModel):
    topic: str | None = Field(default=None, max_length=TOPIC_MAX_LENGTH)
    document_id: str | None = None
    source: Literal["auto", "materials", "general"] = "auto"
    count: int = Field(default=6, ge=1, le=12)


class Flashcard(BaseModel):
    id: str | None = None
    question: str
    answer: str
    source_label: SourceLabel
    topic: str
    interval_days: int = 0
    due_at: str | None = None
    last_reviewed_at: str | None = None
    created_at: str | None = None


class FlashcardResponse(BaseModel):
    cards: list[Flashcard]
    metadata: dict = {}


class FlashcardReviewIn(BaseModel):
    rating: Literal["again", "hard", "good", "easy"]


class QuizRequest(BaseModel):
    topic: str | None = Field(default=None, max_length=TOPIC_MAX_LENGTH)
    document_id: str | None = None
    source: Literal["auto", "materials", "general"] = "auto"
    count: int = Field(default=5, ge=1, le=10)


class QuizQuestion(BaseModel):
    id: str
    type: Literal["multiple_choice"]
    prompt: str
    choices: list[str] = []
    answer: str
    topic: str
    explanation: str


class QuizResponse(BaseModel):
    id: str
    source_label: SourceLabel
    questions: list[QuizQuestion]
    metadata: dict = {}
    created_at: str | None = None


class QuizAnswer(BaseModel):
    question_id: str
    topic: str
    correct: bool
    selected_answer: str | None = None
    correct_answer: str | None = None


class QuizAttemptIn(BaseModel):
    quiz_id: str
    answers: list[QuizAnswer]


class WeakTopic(BaseModel):
    topic: str
    misses: int
    attempts: int
    accuracy: float
    recommendation: str


class WeakTopicResponse(BaseModel):
    topics: list[WeakTopic]


class StudyPlanResponse(BaseModel):
    id: str | None = None
    plan: list[str]
    focus_topics: list[str]
    metadata: dict = {}
    created_at: str | None = None
