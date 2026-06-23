# Cramly

Cramly is a consumer-friendly AI learning companion for students. It turns notes, PDFs, transcripts, textbook chapters, and study guides into explainers, flashcards, quizzes, source-cited RAG answers, and weak-topic study plans.

## What It Does

- Upload `.txt`, `.md`, `.csv`, `.pdf`, `.docx`, `.pptx`, `.png`, `.jpg`, `.webp`, and `.tiff` study materials.
- Store original files in S3-compatible storage, with MinIO in Docker and local disk fallback.
- Extract text, preserve PDF page/slide/image OCR sections, chunk documents, embed chunks with the OpenAI API, and store vectors in PostgreSQL with pgvector.
- OCR image uploads and scanned PDF pages with the configured OpenAI model when selectable text is not available.
- Ask materials-based questions with citations to document name, section/page, chunk id, and similarity score.
- Ask general study questions using clearly labeled OpenAI general model knowledge.
- Use hybrid mode to separate `From your materials` from `OpenAI general knowledge`.
- Choose answer depth: standard college-level breakdowns or advanced PhD-level breakdowns.
- General OpenAI answers use structured study prompts with definitions, mechanisms, examples, common mistakes, self-checks, and expert-level limitations when requested.
- Improve RAG quality with query rewriting, candidate reranking, stricter relevance thresholds, and sample course-note evaluation tests.
- Generate flashcards and quizzes from uploaded materials or a general topic.
- Save generated flashcards, quizzes, quiz attempts, and study plans to the user account.
- Review flashcards as real flip cards with due-today scheduling and simple spaced repetition.
- Take harder multiple-choice quizzes that reveal the answer only after a student chooses an option.
- Track missed quiz topics and recommend focused review.
- Create real student accounts so documents, study history, quiz misses, and RAG results are private per user.
- Inspect retrieved chunks, scores, embedding status, and model metadata on the development-only Dev RAG panel.

## Architecture

```text
frontend/ Next.js + TypeScript + Tailwind
backend/  FastAPI service with bearer-token auth
postgres  PostgreSQL + pgvector for users, document chunks, and quiz attempts
minio     S3-compatible local object storage
openai    Chat model for tutoring/generation and embedding model for RAG
```

Backend flow:

```text
upload -> S3/MinIO/local storage -> text extraction/OCR -> page-aware chunking
       -> OpenAI embeddings -> pgvector -> query rewriting -> reranking
       -> relevance thresholds -> source-labeled answer
```

## Environment

Copy `.env.example` to `.env` and set:

```bash
OPENAI_API_KEY=your_key
OPENAI_MODEL=gpt-4.1-mini
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
CRAMLY_ALLOW_DEMO_MODE=false
CRAMLY_ENV=development
JWT_SECRET=replace-with-a-long-random-secret
ACCESS_TOKEN_MINUTES=10080
# Optional beta signup gate:
# CRAMLY_INVITE_CODE=your-beta-code
# NEXT_PUBLIC_REQUIRE_INVITE_CODE=true
```

No API keys are hardcoded. `OPENAI_API_KEY` is required for normal app startup. The backend uses OpenAI for both chat responses and embeddings.
`JWT_SECRET` signs local account sessions; set it to a long random value before treating the app as official.
Image uploads and scanned PDF pages use `OPENAI_MODEL` for OCR, so choose a vision-capable OpenAI model.

Only tests and throwaway local development should use:

```bash
CRAMLY_ALLOW_DEMO_MODE=true
```

Leave it `false` for any official run.
Use `CRAMLY_ENV=beta` or `CRAMLY_ENV=production` only with explicit `JWT_SECRET`, `DATABASE_URL`, S3 settings, and CORS origins configured.

Only local development should enable the Dev RAG inspector, because it exposes retrieved chunks, scores, and model metadata:

```bash
CRAMLY_ENABLE_DEV_RAG=true
NEXT_PUBLIC_ENABLE_DEV_RAG=true
```

Leave both flags unset or `false` for beta and production.

## Docker Setup

The project includes a complete Compose setup:

```bash
cp .env.example .env
# Edit .env and set OPENAI_API_KEY.
docker compose up --build
```

Local URLs:

- Frontend: `http://localhost:3000`
- Backend API: `http://localhost:8000`
- API docs: `http://localhost:8000/docs`
- MinIO console: `http://localhost:9001`

## Local Backend

For a lightweight local backend run without Docker:

```bash
cp .env.example .env
# Edit .env and set OPENAI_API_KEY.
cd backend
python3 -m uvicorn app.main:app --reload --port 8000
```

For an official local run, use Docker Compose so PostgreSQL with pgvector and MinIO are available. Without `DATABASE_URL`, the backend falls back to in-memory storage, which is useful for quick development but not persistence.

## Local Frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`.

## Deployment

Production-style hosting is configured for Vercel plus Render:

- Vercel serves the Next.js app from `frontend/`.
- Render serves the FastAPI backend from `backend/` and creates Postgres from `render.yaml`.
- Uploads should use Cloudflare R2, AWS S3, or another S3-compatible bucket.

See [DEPLOYMENT.md](DEPLOYMENT.md) and `.env.production.example` for the exact setup.

## Tests

```bash
cd backend
python3 -m pytest
```

The tests cover auth/password tokens, user data isolation, document ingestion/chunking, retrieval, RAG quality evaluation against sample course notes, chat source labeling, citations, quiz generation, saved study items, flashcard scheduling, and weak-topic tracking.

## API Routes

- `GET /api/health`
- `POST /api/auth/register`
- `POST /api/auth/login`
- `GET /api/auth/me`
- `POST /api/auth/change-password`
- `DELETE /api/auth/account`
- `GET /api/documents`
- `DELETE /api/documents/{document_id}`
- `POST /api/uploads`
- `POST /api/chat`
- `POST /api/flashcards`
- `GET /api/flashcards`
- `GET /api/flashcards/due`
- `POST /api/flashcards/{flashcard_id}/review`
- `POST /api/quizzes`
- `GET /api/quizzes`
- `POST /api/quiz-attempts`
- `GET /api/weak-topics`
- `GET /api/study-plan`
- `GET /api/study-plans`
- `GET /api/dev/rag` (development-only; gated by `CRAMLY_ENABLE_DEV_RAG`)

## Screenshots

Add screenshots here after running the app:

- Dashboard and onboarding
- Materials upload
- Source-cited RAG answer
- Flashcards and quiz
- Weak-topic tracker
- Dev RAG inspector, only when development flags are enabled

## Resume Bullets

- Built a full-stack AI study app with Next.js, FastAPI, PostgreSQL, pgvector, MinIO, and OpenAI.
- Added real account sessions with per-user document ownership, private quiz history, and user-scoped RAG retrieval.
- Implemented RAG over uploaded course materials with OpenAI embeddings, page/slide-aware chunking, source citations, and explicit source labeling.
- Hardened RAG quality with query rewriting, heuristic reranking, relevance thresholds, and sample-note evaluation tests.
- Designed hybrid answer behavior that separates uploaded-material evidence from general model knowledge.
- Added persisted AI flashcards, harder multiple-choice quizzes, spaced review scheduling, and weak-topic tracking for adaptive study recommendations.
- Added Docker Compose and GitHub Actions CI for reproducible local development and automated checks.
