# Cramly Project Context

Last updated: 2026-06-10

This file is a handoff summary for continuing work on Cramly from a new account/session. It intentionally does not include secrets such as `OPENAI_API_KEY`, JWT secrets, or local account passwords.

## Product Summary

Cramly is a full-stack AI learning companion for students. Students can upload class materials, ask questions, generate explanations, create flashcards and quizzes, and track weak areas over time.

The app is meant to feel like a polished student study product, not a backend dashboard. The frontend theme is dark gray/black with blue accents, using the Cramly logo at `frontend/public/cramly-logo.png`.

## Current Stack

- Frontend: Next.js 16, React 19, TypeScript, Tailwind CSS, lucide-react
- Backend: Python FastAPI
- Database: PostgreSQL with pgvector
- Object storage: MinIO in Docker, S3-compatible shape
- AI: OpenAI chat model and OpenAI embeddings
- RAG: custom retrieval service using OpenAI embeddings, pgvector, query rewriting, reranking, and source labeling
- OCR/text extraction: pypdf, python-docx, python-pptx, PyMuPDF for scanned PDF rendering, OpenAI vision-capable model for images/OCR
- DevOps: Docker Compose and GitHub Actions CI

## Main Local URLs

- Frontend: `http://localhost:3000`
- Backend API: `http://localhost:8000`
- API docs: `http://localhost:8000/docs`
- MinIO console: `http://localhost:9001`

## Important Environment Variables

Use `.env.example` as the template. The real `.env` exists locally but should not be copied into this file or committed.

Required for official app behavior:

```bash
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-4.1-mini
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
CRAMLY_ALLOW_DEMO_MODE=false
JWT_SECRET=replace-with-a-long-random-secret
ACCESS_TOKEN_MINUTES=10080
```

Docker Compose overrides storage/database values for local containers:

```bash
DATABASE_URL=postgresql://cramly:cramly@cramly-postgres:5432/cramly
S3_ENDPOINT_URL=http://cramly-minio:9000
S3_BUCKET=cramly-uploads
NEXT_PUBLIC_API_URL=http://localhost:8000
```

CORS was fixed for local browser variants with:

```bash
CORS_ORIGINS=http://localhost:3000
CORS_ORIGIN_REGEX=https?://(localhost|127\.0\.0\.1|0\.0\.0\.0|\[::1\])(:\d+)?
```

Do not expose or paste the real OpenAI key in chat output or docs.

## How To Run

From repo root:

```bash
docker compose up -d --build
```

Useful checks:

```bash
docker compose ps
curl -sS http://localhost:8000/api/health
curl -I -sS http://localhost:3000
```

Backend tests:

```bash
./.venv/bin/python -m pytest backend
```

Frontend checks:

```bash
cd frontend
npm run lint
npm run build
```

Note: `npm run build` may need to run outside restrictive sandboxing because Turbopack can spawn a worker/bind a local IPC port.

## Current Verification State

Most recent verified state:

- Backend tests: `13 passed`
- Frontend lint: passed
- Frontend production build: passed
- Docker backend/frontend rebuilt and restarted
- Backend health returned `demo_mode: false`, `openai_configured: true`, and `database: PostgresRepository`
- CORS preflights returned `200 OK` for:
  - `http://localhost:3000`
  - `http://127.0.0.1:3000`
  - `http://0.0.0.0:3000`

## Local Account Notes

Existing local user account in Postgres:

```text
libraajayk@gmail.com
```

The password was reset during troubleshooting, but the actual password is not stored in this context file. If login fails in the normal browser but works in private browsing, clear stale browser session state:

```js
localStorage.removeItem("cramly_token");
location.href = "http://localhost:3000";
```

If password recovery is needed again, reset the password hash in Postgres using `backend/app/services/auth.py::hash_password`. Be careful to escape `$` characters when writing a PBKDF2 hash through a shell command, or use a Python DB update to avoid shell interpolation.

## Important Recent Fixes

### Auth And CORS

- Login issue was not actually the password after reset; browser console showed CORS preflight failures.
- Backend CORS now accepts common localhost origins using `allow_origin_regex`.
- Relevant files:
  - `backend/app/config.py`
  - `backend/app/main.py`
  - `.env.example`
  - `docker-compose.yml`

### Practice Area UI

The Practice panel was redesigned because showing flashcards and quiz questions at the same time was confusing.

Current behavior:

- The user chooses either `Flashcards` or `Quiz`.
- Flashcards mode shows:
  - `New flashcards`
  - `Due today`
  - `Past flashcards`
  - Flippable cards with `again`, `hard`, `good`, `easy` review buttons
- Quiz mode shows:
  - `New quiz`
  - `Past questions`
  - Saved quiz selector
  - Multiple-choice questions where the answer is hidden until the user picks an option

Relevant file:

```text
frontend/app/page.tsx
```

### Persisted Study Items

Generated study items are now stored in Postgres and exposed through API routes.

Persisted entities:

- Flashcards
- Quizzes
- Quiz attempts
- Weak topics
- Study plans

Relevant files:

```text
backend/migrations/001_init.sql
backend/app/repository.py
backend/app/main.py
backend/app/schemas.py
frontend/app/page.tsx
backend/tests/test_study_persistence.py
```

### Quiz Behavior

Quizzes are now multiple-choice only. Answers are not revealed until an option is selected. Quiz generation prompts ask for harder, plausible distractors instead of obvious wrong answers.

Relevant file:

```text
backend/app/services/study.py
```

### Document Ingestion

Supported uploads:

- `.txt`
- `.md`
- `.markdown`
- `.csv`
- `.pdf`
- `.docx`
- `.pptx`
- `.png`
- `.jpg`
- `.jpeg`
- `.webp`
- `.tif`
- `.tiff`

Behavior:

- PDFs preserve page labels.
- PPTX files preserve slide labels.
- Images and scanned PDF pages can use OpenAI OCR when the configured model supports vision.
- Text is chunked by page/slide/image/document section.
- OpenAI embeddings are stored in pgvector.

Relevant file:

```text
backend/app/services/documents.py
```

## Backend Architecture

FastAPI entrypoint:

```text
backend/app/main.py
```

Core services:

- `backend/app/services/auth.py`: password hashing, JWT-like session tokens, email normalization
- `backend/app/services/documents.py`: extraction, OCR hooks, chunking, keyword extraction
- `backend/app/services/llm.py`: OpenAI chat, embeddings, OCR calls, demo fallback
- `backend/app/services/rag.py`: ingest, retrieve, query rewriting, reranking, source labeling, general/materials/hybrid answers
- `backend/app/services/storage.py`: S3/MinIO/local storage save logic
- `backend/app/services/study.py`: flashcard generation, quiz generation, weak topics, study plan
- `backend/app/repository.py`: in-memory and Postgres repository implementations
- `backend/app/schemas.py`: Pydantic API models

Primary API routes:

```text
GET  /api/health
POST /api/auth/register
POST /api/auth/login
GET  /api/auth/me
GET  /api/documents
POST /api/uploads
POST /api/chat
POST /api/flashcards
GET  /api/flashcards
GET  /api/flashcards/due
POST /api/flashcards/{flashcard_id}/review
POST /api/quizzes
GET  /api/quizzes
POST /api/quiz-attempts
GET  /api/weak-topics
GET  /api/study-plan
GET  /api/study-plans
GET  /api/dev/rag
```

## RAG Behavior

Source modes:

- `general`: answer from OpenAI general model knowledge only
- `materials`: answer from uploaded materials if chunks are retrieved, otherwise fall back to general
- `hybrid`: combine uploaded-material answer with OpenAI general explanation
- `auto`: classify based on question wording and retrieval score

Important source-labeling rule:

- Never pretend general OpenAI knowledge came from uploaded files.
- Uploaded-document answers include citations.
- Hybrid answers separate `From your materials` and `OpenAI general knowledge`.

Retrieval quality features:

- Query rewriting with OpenAI JSON mode
- Multiple embedding searches per rewritten query
- Candidate deduping
- Heuristic reranking by semantic score, term overlap, and page/slide section bonus
- Relevance thresholds for uploaded/materials/hybrid classification
- Dev RAG panel displays retrieved chunks and scores

Relevant file:

```text
backend/app/services/rag.py
```

## Frontend Architecture

The app is currently mostly a single-page client component:

```text
frontend/app/page.tsx
```

Supporting files:

- `frontend/app/layout.tsx`: metadata and app shell
- `frontend/app/globals.css`: global theme utilities and Tailwind layers
- `frontend/lib/api.ts`: API helpers for GET/POST/upload with bearer token support
- `frontend/public/cramly-logo.png`: logo

Major UI surfaces:

- First-screen branded homepage with Cramly logo and center dashboard button
- Auth screen with login/register
- Main dashboard with:
  - Ask Cramly chat
  - answer source/depth controls
  - markdown-ish answer rendering
  - loading bar while asking
  - source citations
  - Today's focus/study plan
  - Materials upload with progress steps
  - Practice panel
  - Weak areas
  - Dev RAG inspector

## Database Schema Highlights

Migration file:

```text
backend/migrations/001_init.sql
```

Tables:

- `users`
- `documents`
- `document_chunks`
- `quiz_attempts`
- `flashcards`
- `quizzes`
- `study_plans`

Important indexes:

- `document_chunks_embedding_idx` using pgvector ivfflat cosine ops
- `documents_user_id_idx`
- `quiz_attempts_user_id_idx`
- `flashcards_user_due_idx`
- `quizzes_user_created_idx`
- `study_plans_user_created_idx`

## Known Gotchas

### Do Not Commit Secrets

The `.env` file has real local secrets and is not included in this handoff. Never paste or commit the real OpenAI key.

### Browser Cache / Local Storage

If the normal browser fails but private browsing works:

```js
localStorage.removeItem("cramly_token");
location.href = "http://localhost:3000";
```

Also use a fresh tab at `http://localhost:3000`.

### Password Reset Hashes

Password hashes contain `$`. If updating through a shell command, escape each `$` or use Python to update the database. An earlier reset attempt failed because shell expansion stripped parts of the hash.

### Docker Compose Output Race

Immediately running `docker compose ps` in parallel with `docker compose up -d` can show stale container age/image for a moment. Re-run `docker compose ps` after the recreate settles.

### Codex In-App Browser

During prior work, the Codex in-app browser surface sometimes returned an empty browser list. When that happens, verify locally with `curl`, tests, and Docker status instead.

## Suggested Next Product Work

Good next steps:

- Add a proper account settings page with change password.
- Add a real password reset flow.
- Add user-facing quiz history with scores/attempt summaries, not only saved questions.
- Add flashcard spaced-repetition analytics and due counts in the dashboard.
- Add delete/rename actions for documents, flashcards, and quizzes.
- Add streaming responses for chat.
- Add better upload/indexing status from backend jobs instead of simulated frontend progress.
- Add production auth provider or email verification before deploying publicly.
- Add hosted S3 configuration and production Postgres migrations.
- Add screenshot assets to README.

## Quick Resume Summary

Cramly is a full-stack AI study app built with Next.js, FastAPI, PostgreSQL/pgvector, MinIO, Docker, and OpenAI. It supports private user accounts, document upload and extraction, OpenAI embeddings, RAG with source citations, general and hybrid AI explanations, flashcards, harder multiple-choice quizzes, persisted study history, weak-topic tracking, and a dev RAG inspector.

