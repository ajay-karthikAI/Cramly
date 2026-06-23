from __future__ import annotations

import json

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import get_settings
from app.repository import create_repository
from app.schemas import (
    AuthResponse,
    ChatRequest,
    ChatResponse,
    ChangePasswordRequest,
    DocumentOut,
    Flashcard,
    FlashcardRequest,
    FlashcardResponse,
    FlashcardReviewIn,
    QuizAttemptIn,
    QuizQuestion,
    QuizRequest,
    QuizResponse,
    StudyPlanResponse,
    SuccessResponse,
    UserCreate,
    UserLogin,
    UserOut,
    WeakTopicResponse,
)
from app.services.auth import (
    AuthError,
    create_access_token,
    hash_password,
    normalize_email,
    verify_access_token,
    verify_password,
)
from app.services.documents import (
    UNSUPPORTED_FILE_TYPE_MESSAGE,
    chunk_text,
    extract_keywords,
    extract_text,
    is_supported_filename,
)
from app.services.limits import (
    DailyQuota,
    FixedWindowRateLimiter,
    LimitViolation,
    ensure_max_bytes,
    ensure_max_chars,
    ensure_max_count,
)
from app.services.llm import OpenAILearningClient
from app.services.rag import RagService
from app.services.storage import StorageService
from app.services.study import StudyService


settings = get_settings()
repo = create_repository(settings)
llm = OpenAILearningClient(settings)
rag = RagService(repo, llm)
study = StudyService(repo, llm)
storage = StorageService(settings)
security = HTTPBearer(auto_error=False)
rate_limiter = FixedWindowRateLimiter()
daily_quota = DailyQuota()

app = FastAPI(title="Cramly API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=settings.cors_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    try:
        repo.migrate()
    except Exception as exc:
        if settings.is_strict_env:
            raise RuntimeError(
                f"Database startup failed when CRAMLY_ENV={settings.env}; "
                "verify DATABASE_URL and database availability."
            ) from exc
        raise


@app.get("/api/health")
def health() -> dict:
    return {
        "ok": True,
        "demo_mode": settings.demo_mode,
        "openai_configured": bool(settings.openai_api_key),
        "database": repo.__class__.__name__,
        "openai_model": settings.openai_model,
        "embedding_model": settings.openai_embedding_model,
    }


def current_user(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict:
    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sign in to use Cramly.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        user_id = verify_access_token(credentials.credentials, settings.jwt_secret)
    except AuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    user = repo.get_user_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session user no longer exists.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def _enforce_rate_limit(scope: str, request: Request, user: dict | None = None) -> None:
    limit = settings.auth_rate_limit_per_minute if scope == "auth" else settings.ai_rate_limit_per_minute
    actor = f"user:{user['id']}" if user else f"ip:{_client_host(request)}"
    try:
        rate_limiter.check(
            f"{scope}:{actor}",
            limit,
            settings.rate_limit_window_seconds,
            "Too many requests. Please wait briefly and try again.",
        )
    except LimitViolation as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


def _enforce_daily_quota(user_id: str, category: str) -> None:
    limits = {
        "chat": settings.daily_chat_limit,
        "upload": settings.daily_upload_limit,
        "generation": settings.daily_generation_limit,
    }
    messages = {
        "chat": "Daily chat limit reached. Try again tomorrow.",
        "upload": "Daily upload limit reached. Try again tomorrow.",
        "generation": "Daily AI generation limit reached. Try again tomorrow.",
    }
    try:
        daily_quota.consume(repo, user_id, category, limits[category], messages[category])
    except LimitViolation as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


async def _read_upload_content(file: UploadFile) -> bytes:
    existing_size = getattr(file, "size", None)
    if isinstance(existing_size, int):
        try:
            ensure_max_bytes(
                existing_size,
                settings.max_upload_bytes,
                f"Upload exceeds the {settings.max_upload_bytes} byte beta limit.",
            )
        except LimitViolation as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        try:
            ensure_max_bytes(
                total,
                settings.max_upload_bytes,
                f"Upload exceeds the {settings.max_upload_bytes} byte beta limit.",
            )
        except LimitViolation as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
        chunks.append(chunk)
    return b"".join(chunks)


def _client_host(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _user_out(user: dict) -> UserOut:
    return UserOut(id=user["id"], email=user["email"], created_at=user.get("created_at"))


@app.post("/api/auth/register", response_model=AuthResponse)
def register(payload: UserCreate, request: Request) -> AuthResponse:
    _enforce_rate_limit("auth", request)
    try:
        email = normalize_email(payload.email)
    except AuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if settings.invite_code and payload.invite_code != settings.invite_code:
        raise HTTPException(status_code=403, detail="A valid invite code is required.")
    if repo.get_user_by_email(email):
        raise HTTPException(status_code=409, detail="An account already exists for that email.")

    user = repo.create_user(email, hash_password(payload.password))
    token = create_access_token(user["id"], settings.jwt_secret, settings.access_token_minutes)
    return AuthResponse(access_token=token, user=_user_out(user))


@app.post("/api/auth/login", response_model=AuthResponse)
def login(payload: UserLogin, request: Request) -> AuthResponse:
    _enforce_rate_limit("auth", request)
    try:
        email = normalize_email(payload.email)
    except AuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    user = repo.get_user_by_email(email)
    if not user or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    token = create_access_token(user["id"], settings.jwt_secret, settings.access_token_minutes)
    return AuthResponse(access_token=token, user=_user_out(user))


@app.get("/api/auth/me", response_model=UserOut)
def me(user: dict = Depends(current_user)) -> UserOut:
    return _user_out(user)


@app.post("/api/auth/change-password", response_model=SuccessResponse)
def change_password(payload: ChangePasswordRequest, user: dict = Depends(current_user)) -> SuccessResponse:
    if not verify_password(payload.current_password, user["password_hash"]):
        raise HTTPException(status_code=400, detail="Current password is incorrect.")
    updated = repo.update_user_password(user["id"], hash_password(payload.new_password))
    if not updated:
        raise HTTPException(status_code=401, detail="Session user no longer exists.")
    return SuccessResponse()


@app.delete("/api/auth/account", response_model=SuccessResponse)
def delete_account(user: dict = Depends(current_user)) -> SuccessResponse:
    repo.delete_user(user["id"])
    return SuccessResponse()


@app.get("/api/documents", response_model=list[DocumentOut])
def documents(user: dict = Depends(current_user)) -> list[dict]:
    return repo.list_documents(user["id"])


@app.delete("/api/documents/{document_id}", response_model=SuccessResponse)
def delete_document(document_id: str, user: dict = Depends(current_user)) -> SuccessResponse:
    if not repo.delete_document(user["id"], document_id):
        raise HTTPException(status_code=404, detail="Document not found.")
    return SuccessResponse()


@app.post("/api/uploads", response_model=DocumentOut)
async def upload(request: Request, file: UploadFile = File(...), user: dict = Depends(current_user)) -> dict:
    _enforce_rate_limit("ai", request, user)

    filename = file.filename or "notes.txt"
    if not is_supported_filename(filename):
        raise HTTPException(status_code=422, detail=UNSUPPORTED_FILE_TYPE_MESSAGE)

    content = await _read_upload_content(file)
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    _enforce_daily_quota(user["id"], "upload")

    try:
        text = extract_text(
            filename,
            content,
            llm,
            max_pdf_pages=settings.max_pdf_pages,
            max_ocr_pages=settings.max_ocr_pages,
        )
        ensure_max_chars(
            text,
            settings.max_extracted_text_chars,
            f"Extracted text exceeds the {settings.max_extracted_text_chars} character beta limit.",
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except LimitViolation as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    if not text:
        raise HTTPException(status_code=422, detail="No readable text found in this file.")

    chunks = chunk_text(text)
    try:
        ensure_max_count(
            len(chunks),
            settings.max_document_chunks,
            f"Document would create more than {settings.max_document_chunks} chunks. Try a smaller file.",
        )
    except LimitViolation as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    storage_key = storage.save(filename, content)
    document = repo.create_document(
        user_id=user["id"],
        name=filename,
        storage_key=storage_key,
        text=text,
        keywords=extract_keywords(text),
    )
    try:
        rag.ingest_document(document["id"], text, chunks=chunks)
    except RuntimeError as exc:
        repo.update_document_status(document["id"], "failed", 0)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        repo.update_document_status(document["id"], "failed", 0)
        raise HTTPException(status_code=502, detail="Indexing failed. Check OpenAI embeddings and database settings.") from exc
    return repo.get_document(user["id"], document["id"]) or document


@app.post("/api/chat", response_model=ChatResponse)
def chat(payload: ChatRequest, request: Request, user: dict = Depends(current_user)) -> ChatResponse:
    _enforce_rate_limit("ai", request, user)
    _enforce_daily_quota(user["id"], "chat")
    return rag.answer(payload.question, user["id"], payload.mode, payload.depth)


@app.post("/api/flashcards", response_model=FlashcardResponse)
def flashcards(payload: FlashcardRequest, request: Request, user: dict = Depends(current_user)) -> FlashcardResponse:
    _enforce_rate_limit("ai", request, user)
    _enforce_daily_quota(user["id"], "generation")
    context = _document_context(user["id"], payload.document_id) if payload.source != "general" else None
    response = study.flashcards(payload.topic, payload.count, context)
    saved = repo.save_flashcards(user["id"], [card.model_dump() for card in response.cards])
    return FlashcardResponse(cards=[Flashcard(**card) for card in saved], metadata=response.metadata)


@app.get("/api/flashcards", response_model=FlashcardResponse)
def saved_flashcards(user: dict = Depends(current_user)) -> FlashcardResponse:
    cards = repo.list_flashcards(user["id"])
    return FlashcardResponse(cards=[Flashcard(**card) for card in cards], metadata={"source": "saved"})


@app.get("/api/flashcards/due", response_model=FlashcardResponse)
def due_flashcards(user: dict = Depends(current_user)) -> FlashcardResponse:
    cards = repo.due_flashcards(user["id"])
    return FlashcardResponse(cards=[Flashcard(**card) for card in cards], metadata={"source": "due_today"})


@app.post("/api/flashcards/{flashcard_id}/review", response_model=Flashcard)
def review_flashcard(
    flashcard_id: str,
    payload: FlashcardReviewIn,
    user: dict = Depends(current_user),
) -> Flashcard:
    card = repo.review_flashcard(user["id"], flashcard_id, payload.rating)
    if not card:
        raise HTTPException(status_code=404, detail="Flashcard not found.")
    return Flashcard(**card)


@app.post("/api/quizzes", response_model=QuizResponse)
def quizzes(payload: QuizRequest, request: Request, user: dict = Depends(current_user)) -> QuizResponse:
    _enforce_rate_limit("ai", request, user)
    _enforce_daily_quota(user["id"], "generation")
    context = _document_context(user["id"], payload.document_id) if payload.source != "general" else None
    response = study.quiz(payload.topic, payload.count, context)
    saved = repo.save_quiz(
        user["id"],
        response.id,
        response.source_label,
        [question.model_dump() for question in response.questions],
        response.metadata,
    )
    return _quiz_response(saved)


@app.get("/api/quizzes", response_model=list[QuizResponse])
def saved_quizzes(user: dict = Depends(current_user)) -> list[QuizResponse]:
    return [_quiz_response(row) for row in repo.list_quizzes(user["id"])]


@app.post("/api/quiz-attempts", response_model=WeakTopicResponse)
def quiz_attempts(attempt: QuizAttemptIn, user: dict = Depends(current_user)) -> WeakTopicResponse:
    repo.record_quiz_attempt(user["id"], attempt.quiz_id, [answer.model_dump() for answer in attempt.answers])
    return WeakTopicResponse(topics=study.weak_topics(user["id"]))


@app.get("/api/weak-topics", response_model=WeakTopicResponse)
def weak_topics(user: dict = Depends(current_user)) -> WeakTopicResponse:
    return WeakTopicResponse(topics=study.weak_topics(user["id"]))


@app.get("/api/study-plan", response_model=StudyPlanResponse)
def study_plan(user: dict = Depends(current_user)) -> StudyPlanResponse:
    saved_plans = repo.list_study_plans(user["id"], limit=1)
    if saved_plans:
        return _study_plan_response(saved_plans[0])
    return study.study_plan(user["id"])


@app.post("/api/study-plan", response_model=StudyPlanResponse)
def create_study_plan(request: Request, user: dict = Depends(current_user)) -> StudyPlanResponse:
    _enforce_rate_limit("ai", request, user)
    _enforce_daily_quota(user["id"], "generation")
    response = study.study_plan(user["id"])
    saved = repo.save_study_plan(user["id"], response.plan, response.focus_topics, response.metadata)
    return _study_plan_response(saved)


@app.get("/api/study-plans", response_model=list[StudyPlanResponse])
def saved_study_plans(user: dict = Depends(current_user)) -> list[StudyPlanResponse]:
    return [_study_plan_response(row) for row in repo.list_study_plans(user["id"])]


def require_dev_rag_enabled() -> None:
    if not settings.enable_dev_rag:
        raise HTTPException(status_code=404, detail="Dev RAG inspector is disabled.")


@app.get("/api/dev/rag")
def dev_rag(
    question: str = "What should I review?",
    _: None = Depends(require_dev_rag_enabled),
    user: dict = Depends(current_user),
) -> dict:
    chunks, metadata = rag.retrieve(question, user["id"])
    return {
        "question": question,
        "embedding": metadata,
        "pipeline": [
            "extract text",
            "chunk with LangChain splitter or fallback",
            "embed with OpenAI embeddings",
            "store/search pgvector",
            "answer with source label",
        ],
        "retrieved_chunks": [chunk.model_dump() for chunk in chunks],
        "openai": {
            "chat_model": settings.openai_model,
            "embedding_model": settings.openai_embedding_model,
            "demo_mode": settings.demo_mode,
        },
    }


def _document_context(user_id: str, document_id: str | None) -> str | None:
    documents = [repo.get_document(user_id, document_id)] if document_id else repo.list_documents(user_id)[:3]
    texts = [document.get("raw_text", "") for document in documents if document]
    combined = "\n\n".join(texts).strip()
    return combined[:6000] if combined else None


def _quiz_response(row: dict) -> QuizResponse:
    questions = _json_value(row.get("questions"), [])
    return QuizResponse(
        id=row["id"],
        source_label=row["source_label"],
        questions=[QuizQuestion(**question) for question in questions],
        metadata=_json_value(row.get("metadata"), {}),
        created_at=row.get("created_at"),
    )


def _study_plan_response(row: dict) -> StudyPlanResponse:
    return StudyPlanResponse(
        id=row.get("id"),
        focus_topics=_json_value(row.get("focus_topics"), []),
        plan=_json_value(row.get("plan"), []),
        metadata=_json_value(row.get("metadata"), {}),
        created_at=row.get("created_at"),
    )


def _json_value(value, fallback):
    if value is None:
        return fallback
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return fallback
    return value
