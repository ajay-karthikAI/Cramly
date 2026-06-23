from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import math
import time
import uuid

from app.config import Settings


class MemoryRepository:
    def __init__(self):
        self.users: dict[str, dict] = {}
        self.documents: dict[str, dict] = {}
        self.chunks: dict[str, dict] = {}
        self.attempts: list[dict] = []
        self.flashcards: dict[str, dict] = {}
        self.quizzes: dict[str, dict] = {}
        self.study_plans: dict[str, dict] = {}
        self.daily_usage: dict[tuple[str, str, str], int] = {}

    def migrate(self) -> None:
        return None

    def create_user(self, email: str, password_hash: str) -> dict:
        user_id = str(uuid.uuid4())
        user = {
            "id": user_id,
            "email": email,
            "password_hash": password_hash,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self.users[user_id] = user
        return user

    def get_user_by_email(self, email: str) -> dict | None:
        return next((user for user in self.users.values() if user["email"] == email), None)

    def get_user_by_id(self, user_id: str) -> dict | None:
        return self.users.get(user_id)

    def update_user_password(self, user_id: str, password_hash: str) -> dict | None:
        user = self.users.get(user_id)
        if not user:
            return None
        user["password_hash"] = password_hash
        return user

    def delete_user(self, user_id: str) -> bool:
        if user_id not in self.users:
            return False
        document_ids = {document_id for document_id, document in self.documents.items() if document["user_id"] == user_id}

        del self.users[user_id]
        self.documents = {
            document_id: document
            for document_id, document in self.documents.items()
            if document["user_id"] != user_id
        }
        self.chunks = {
            chunk_id: chunk
            for chunk_id, chunk in self.chunks.items()
            if chunk.get("user_id") != user_id and chunk.get("document_id") not in document_ids
        }
        self.attempts = [attempt for attempt in self.attempts if attempt["user_id"] != user_id]
        self.flashcards = {
            card_id: card
            for card_id, card in self.flashcards.items()
            if card["user_id"] != user_id
        }
        self.quizzes = {
            quiz_id: quiz
            for quiz_id, quiz in self.quizzes.items()
            if quiz["user_id"] != user_id
        }
        self.study_plans = {
            plan_id: plan
            for plan_id, plan in self.study_plans.items()
            if plan["user_id"] != user_id
        }
        self.daily_usage = {
            key: count
            for key, count in self.daily_usage.items()
            if key[0] != user_id
        }
        return True

    def create_document(self, user_id: str, name: str, storage_key: str, text: str, keywords: list[str]) -> dict:
        doc_id = str(uuid.uuid4())
        document = {
            "id": doc_id,
            "user_id": user_id,
            "name": name,
            "status": "processing",
            "chunks": 0,
            "keywords": keywords,
            "storage_key": storage_key,
            "raw_text": text,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self.documents[doc_id] = document
        return document

    def update_document_status(self, document_id: str, status: str, chunks: int = 0) -> dict:
        document = self.documents[document_id]
        document["status"] = status
        document["chunks"] = chunks
        return document

    def list_documents(self, user_id: str) -> list[dict]:
        documents = [document for document in self.documents.values() if document["user_id"] == user_id]
        return sorted(documents, key=lambda doc: doc["created_at"], reverse=True)

    def get_document(self, user_id: str, document_id: str) -> dict | None:
        document = self.documents.get(document_id)
        if not document or document["user_id"] != user_id:
            return None
        return document

    def delete_document(self, user_id: str, document_id: str) -> bool:
        document = self.get_document(user_id, document_id)
        if not document:
            return False
        del self.documents[document_id]
        self.chunks = {
            chunk_id: chunk
            for chunk_id, chunk in self.chunks.items()
            if chunk["document_id"] != document_id
        }
        return True

    def insert_chunks(self, document_id: str, chunks: list[dict], embeddings: list[list[float]]) -> None:
        document = self.documents[document_id]
        for index, (chunk, embedding) in enumerate(zip(chunks, embeddings), start=1):
            chunk_id = str(uuid.uuid4())
            self.chunks[chunk_id] = {
                "id": chunk_id,
                "user_id": document["user_id"],
                "document_id": document_id,
                "document_name": document["name"],
                "section": chunk["section"],
                "text": chunk["text"],
                "embedding": embedding,
                "chunk_index": index,
            }

    def search_chunks(
        self,
        user_id: str,
        embedding: list[float],
        limit: int = 5,
        document_id: str | None = None,
    ) -> list[dict]:
        rows = []
        for chunk in self.chunks.values():
            if chunk["user_id"] != user_id:
                continue
            if document_id and chunk["document_id"] != document_id:
                continue
            score = cosine_similarity(embedding, chunk["embedding"])
            rows.append({**chunk, "score": score})
        return sorted(rows, key=lambda row: row["score"], reverse=True)[:limit]

    def save_flashcards(self, user_id: str, cards: list[dict]) -> list[dict]:
        saved = []
        for card in cards:
            card_id = str(uuid.uuid4())
            row = {
                "id": card_id,
                "user_id": user_id,
                "question": card["question"],
                "answer": card["answer"],
                "topic": card["topic"],
                "source_label": card["source_label"],
                "interval_days": 0,
                "ease": 2.5,
                "due_at": datetime.now(timezone.utc).isoformat(),
                "last_reviewed_at": None,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            self.flashcards[card_id] = row
            saved.append(row)
        return saved

    def list_flashcards(self, user_id: str, limit: int = 50) -> list[dict]:
        cards = [card for card in self.flashcards.values() if card["user_id"] == user_id]
        return sorted(cards, key=lambda card: card["created_at"], reverse=True)[:limit]

    def due_flashcards(self, user_id: str, limit: int = 20) -> list[dict]:
        today = datetime.now(timezone.utc).date()
        cards = [
            card
            for card in self.flashcards.values()
            if card["user_id"] == user_id and _parse_datetime(card["due_at"]).date() <= today
        ]
        return sorted(cards, key=lambda card: card["due_at"])[:limit]

    def review_flashcard(self, user_id: str, flashcard_id: str, rating: str) -> dict | None:
        card = self.flashcards.get(flashcard_id)
        if not card or card["user_id"] != user_id:
            return None
        updated = _schedule_flashcard(card, rating)
        self.flashcards[flashcard_id] = updated
        return updated

    def save_quiz(self, user_id: str, quiz_id: str, source_label: str, questions: list[dict], metadata: dict) -> dict:
        quiz = {
            "id": quiz_id,
            "user_id": user_id,
            "source_label": source_label,
            "questions": questions,
            "metadata": metadata,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self.quizzes[quiz_id] = quiz
        return quiz

    def list_quizzes(self, user_id: str, limit: int = 20) -> list[dict]:
        quizzes = [quiz for quiz in self.quizzes.values() if quiz["user_id"] == user_id]
        return sorted(quizzes, key=lambda quiz: quiz["created_at"], reverse=True)[:limit]

    def save_study_plan(self, user_id: str, plan: list[str], focus_topics: list[str], metadata: dict) -> dict:
        plan_id = str(uuid.uuid4())
        row = {
            "id": plan_id,
            "user_id": user_id,
            "plan": plan,
            "focus_topics": focus_topics,
            "metadata": metadata,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self.study_plans[plan_id] = row
        return row

    def list_study_plans(self, user_id: str, limit: int = 10) -> list[dict]:
        plans = [plan for plan in self.study_plans.values() if plan["user_id"] == user_id]
        return sorted(plans, key=lambda plan: plan["created_at"], reverse=True)[:limit]

    def record_quiz_attempt(self, user_id: str, quiz_id: str, answers: list[dict]) -> None:
        for answer in answers:
            self.attempts.append(
                {
                    "user_id": user_id,
                    "quiz_id": quiz_id,
                    "question_id": answer["question_id"],
                    "topic": answer["topic"].lower(),
                    "selected_answer": answer.get("selected_answer"),
                    "correct_answer": answer.get("correct_answer"),
                    "correct": answer["correct"],
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
            )

    def weak_topics(self, user_id: str) -> list[dict]:
        totals: dict[str, dict[str, int]] = {}
        for attempt in self.attempts:
            if attempt["user_id"] != user_id:
                continue
            topic = attempt["topic"]
            totals.setdefault(topic, {"attempts": 0, "misses": 0})
            totals[topic]["attempts"] += 1
            if not attempt["correct"]:
                totals[topic]["misses"] += 1

        rows = []
        for topic, counts in totals.items():
            attempts = counts["attempts"]
            misses = counts["misses"]
            accuracy = (attempts - misses) / attempts if attempts else 1
            if misses:
                rows.append(
                    {
                        "topic": topic,
                        "misses": misses,
                        "attempts": attempts,
                        "accuracy": round(accuracy, 2),
                    }
                )
        return sorted(rows, key=lambda row: (-row["misses"], row["accuracy"], row["topic"]))

    def get_daily_usage(self, user_id: str, category: str, usage_date: str) -> int:
        return self.daily_usage.get((user_id, usage_date, category), 0)

    def increment_daily_usage(self, user_id: str, category: str, usage_date: str, amount: int = 1) -> int:
        key = (user_id, usage_date, category)
        self.daily_usage[key] = self.daily_usage.get(key, 0) + amount
        return self.daily_usage[key]


class PostgresRepository:
    def __init__(self, database_url: str):
        self.database_url = database_url
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ModuleNotFoundError as exc:
            raise RuntimeError("psycopg is required for PostgreSQL mode.") from exc

        self.psycopg = psycopg
        self.dict_row = dict_row

    def _connect(self):
        return self.psycopg.connect(self.database_url, row_factory=self.dict_row)

    def _connect_with_retry(self, attempts: int = 20, delay: float = 1.0):
        last_error = None
        for _ in range(attempts):
            try:
                return self._connect()
            except self.psycopg.OperationalError as exc:
                last_error = exc
                time.sleep(delay)
        raise last_error

    def migrate(self) -> None:
        with open("migrations/001_init.sql", encoding="utf-8") as handle:
            sql = handle.read()
        with self._connect_with_retry() as conn:
            conn.execute(sql)
            conn.commit()

    def create_user(self, email: str, password_hash: str) -> dict:
        with self._connect() as conn:
            row = conn.execute(
                """
                insert into users (email, password_hash)
                values (%s, %s)
                returning id::text, email, password_hash, created_at::text
                """,
                (email, password_hash),
            ).fetchone()
            conn.commit()
            return row

    def get_user_by_email(self, email: str) -> dict | None:
        with self._connect() as conn:
            return conn.execute(
                """
                select id::text, email, password_hash, created_at::text
                from users where email = %s
                """,
                (email,),
            ).fetchone()

    def get_user_by_id(self, user_id: str) -> dict | None:
        with self._connect() as conn:
            return conn.execute(
                """
                select id::text, email, password_hash, created_at::text
                from users where id = %s
                """,
                (user_id,),
            ).fetchone()

    def update_user_password(self, user_id: str, password_hash: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                update users
                set password_hash = %s
                where id = %s
                returning id::text, email, password_hash, created_at::text
                """,
                (password_hash, user_id),
            ).fetchone()
            conn.commit()
            return row

    def delete_user(self, user_id: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                """
                delete from users
                where id = %s
                returning id::text
                """,
                (user_id,),
            ).fetchone()
            conn.commit()
            return row is not None

    def create_document(self, user_id: str, name: str, storage_key: str, text: str, keywords: list[str]) -> dict:
        with self._connect() as conn:
            row = conn.execute(
                """
                insert into documents (user_id, name, storage_key, raw_text, keywords, status)
                values (%s, %s, %s, %s, %s::jsonb, 'processing')
                returning id::text, user_id::text, name, status, chunks, keywords, storage_key, raw_text, created_at::text
                """,
                (user_id, name, storage_key, text, json.dumps(keywords)),
            ).fetchone()
            conn.commit()
            return row

    def update_document_status(self, document_id: str, status: str, chunks: int = 0) -> dict:
        with self._connect() as conn:
            row = conn.execute(
                """
                update documents set status = %s, chunks = %s
                where id = %s
                returning id::text, user_id::text, name, status, chunks, keywords, storage_key, raw_text, created_at::text
                """,
                (status, chunks, document_id),
            ).fetchone()
            conn.commit()
            return row

    def list_documents(self, user_id: str) -> list[dict]:
        with self._connect() as conn:
            return conn.execute(
                """
                select id::text, user_id::text, name, status, chunks, keywords, storage_key, created_at::text
                from documents
                where user_id = %s
                order by created_at desc
                """,
                (user_id,),
            ).fetchall()

    def get_document(self, user_id: str, document_id: str) -> dict | None:
        with self._connect() as conn:
            return conn.execute(
                """
                select id::text, user_id::text, name, status, chunks, keywords, storage_key, raw_text, created_at::text
                from documents where id = %s and user_id = %s
                """,
                (document_id, user_id),
            ).fetchone()

    def delete_document(self, user_id: str, document_id: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                """
                delete from documents
                where id = %s and user_id = %s
                returning id::text
                """,
                (document_id, user_id),
            ).fetchone()
            conn.commit()
            return row is not None

    def insert_chunks(self, document_id: str, chunks: list[dict], embeddings: list[list[float]]) -> None:
        with self._connect() as conn:
            for index, (chunk, embedding) in enumerate(zip(chunks, embeddings), start=1):
                conn.execute(
                    """
                    insert into document_chunks (document_id, chunk_index, section, content, embedding)
                    values (%s, %s, %s, %s, %s::vector)
                    """,
                    (document_id, index, chunk["section"], chunk["text"], _vector_literal(embedding)),
                )
            conn.commit()

    def save_flashcards(self, user_id: str, cards: list[dict]) -> list[dict]:
        with self._connect() as conn:
            rows = []
            for card in cards:
                row = conn.execute(
                    """
                    insert into flashcards (user_id, question, answer, topic, source_label)
                    values (%s, %s, %s, %s, %s)
                    returning id::text, question, answer, topic, source_label, interval_days,
                              due_at::text, last_reviewed_at::text, created_at::text
                    """,
                    (user_id, card["question"], card["answer"], card["topic"], card["source_label"]),
                ).fetchone()
                rows.append(row)
            conn.commit()
            return rows

    def list_flashcards(self, user_id: str, limit: int = 50) -> list[dict]:
        with self._connect() as conn:
            return conn.execute(
                """
                select id::text, question, answer, topic, source_label, interval_days,
                       due_at::text, last_reviewed_at::text, created_at::text
                from flashcards
                where user_id = %s
                order by created_at desc
                limit %s
                """,
                (user_id, limit),
            ).fetchall()

    def due_flashcards(self, user_id: str, limit: int = 20) -> list[dict]:
        with self._connect() as conn:
            return conn.execute(
                """
                select id::text, question, answer, topic, source_label, interval_days,
                       due_at::text, last_reviewed_at::text, created_at::text
                from flashcards
                where user_id = %s and due_at::date <= current_date
                order by due_at asc
                limit %s
                """,
                (user_id, limit),
            ).fetchall()

    def review_flashcard(self, user_id: str, flashcard_id: str, rating: str) -> dict | None:
        with self._connect() as conn:
            card = conn.execute(
                """
                select id::text, question, answer, topic, source_label, interval_days, ease::float as ease,
                       due_at::text, last_reviewed_at::text, created_at::text
                from flashcards
                where id = %s and user_id = %s
                """,
                (flashcard_id, user_id),
            ).fetchone()
            if not card:
                return None
            scheduled = _schedule_flashcard(card, rating)
            row = conn.execute(
                """
                update flashcards
                set interval_days = %s, ease = %s, due_at = %s, last_reviewed_at = %s
                where id = %s and user_id = %s
                returning id::text, question, answer, topic, source_label, interval_days,
                          due_at::text, last_reviewed_at::text, created_at::text
                """,
                (
                    scheduled["interval_days"],
                    scheduled["ease"],
                    scheduled["due_at"],
                    scheduled["last_reviewed_at"],
                    flashcard_id,
                    user_id,
                ),
            ).fetchone()
            conn.commit()
            return row

    def save_quiz(self, user_id: str, quiz_id: str, source_label: str, questions: list[dict], metadata: dict) -> dict:
        with self._connect() as conn:
            row = conn.execute(
                """
                insert into quizzes (id, user_id, source_label, questions, metadata)
                values (%s, %s, %s, %s::jsonb, %s::jsonb)
                returning id::text, source_label, questions, metadata, created_at::text
                """,
                (quiz_id, user_id, source_label, json.dumps(questions), json.dumps(metadata)),
            ).fetchone()
            conn.commit()
            return row

    def list_quizzes(self, user_id: str, limit: int = 20) -> list[dict]:
        with self._connect() as conn:
            return conn.execute(
                """
                select id::text, source_label, questions, metadata, created_at::text
                from quizzes
                where user_id = %s
                order by created_at desc
                limit %s
                """,
                (user_id, limit),
            ).fetchall()

    def save_study_plan(self, user_id: str, plan: list[str], focus_topics: list[str], metadata: dict) -> dict:
        with self._connect() as conn:
            row = conn.execute(
                """
                insert into study_plans (user_id, focus_topics, plan, metadata)
                values (%s, %s::jsonb, %s::jsonb, %s::jsonb)
                returning id::text, focus_topics, plan, metadata, created_at::text
                """,
                (user_id, json.dumps(focus_topics), json.dumps(plan), json.dumps(metadata)),
            ).fetchone()
            conn.commit()
            return row

    def list_study_plans(self, user_id: str, limit: int = 10) -> list[dict]:
        with self._connect() as conn:
            return conn.execute(
                """
                select id::text, focus_topics, plan, metadata, created_at::text
                from study_plans
                where user_id = %s
                order by created_at desc
                limit %s
                """,
                (user_id, limit),
            ).fetchall()

    def search_chunks(
        self,
        user_id: str,
        embedding: list[float],
        limit: int = 5,
        document_id: str | None = None,
    ) -> list[dict]:
        vector = _vector_literal(embedding)
        params: list = [vector, user_id]
        where = "where d.user_id = %s"
        if document_id:
            where += " and c.document_id = %s"
            params.append(document_id)
        params.append(vector)
        params.append(limit)
        with self._connect() as conn:
            return conn.execute(
                f"""
                select c.id::text, c.document_id::text, d.name as document_name, c.section,
                       c.content as text, 1 - (c.embedding <=> %s::vector) as score
                from document_chunks c
                join documents d on d.id = c.document_id
                {where}
                order by c.embedding <=> %s::vector
                limit %s
                """,
                params,
            ).fetchall()

    def record_quiz_attempt(self, user_id: str, quiz_id: str, answers: list[dict]) -> None:
        with self._connect() as conn:
            for answer in answers:
                conn.execute(
                    """
                    insert into quiz_attempts (
                        user_id, quiz_id, question_id, topic, selected_answer, correct_answer, correct
                    )
                    values (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        user_id,
                        quiz_id,
                        answer["question_id"],
                        answer["topic"].lower(),
                        answer.get("selected_answer"),
                        answer.get("correct_answer"),
                        answer["correct"],
                    ),
                )
            conn.commit()

    def weak_topics(self, user_id: str) -> list[dict]:
        with self._connect() as conn:
            return conn.execute(
                """
                select topic,
                       count(*) filter (where not correct)::int as misses,
                       count(*)::int as attempts,
                       round((count(*) filter (where correct)::numeric / count(*)), 2)::float as accuracy
                from quiz_attempts
                where user_id = %s
                group by topic
                having count(*) filter (where not correct) > 0
                order by misses desc, accuracy asc, topic asc
                """,
                (user_id,),
            ).fetchall()

    def get_daily_usage(self, user_id: str, category: str, usage_date: str) -> int:
        with self._connect() as conn:
            row = conn.execute(
                """
                select usage_count
                from daily_usage
                where user_id = %s and usage_date = %s::date and category = %s
                """,
                (user_id, usage_date, category),
            ).fetchone()
            return int(row["usage_count"]) if row else 0

    def increment_daily_usage(self, user_id: str, category: str, usage_date: str, amount: int = 1) -> int:
        with self._connect() as conn:
            row = conn.execute(
                """
                insert into daily_usage (user_id, usage_date, category, usage_count)
                values (%s, %s::date, %s, %s)
                on conflict (user_id, usage_date, category)
                do update set
                    usage_count = daily_usage.usage_count + excluded.usage_count,
                    updated_at = now()
                returning usage_count
                """,
                (user_id, usage_date, category, amount),
            ).fetchone()
            conn.commit()
            return int(row["usage_count"])


def create_repository(settings: Settings):
    if not settings.database_url:
        if settings.is_strict_env:
            raise RuntimeError(f"DATABASE_URL is required when CRAMLY_ENV={settings.env}.")
        return MemoryRepository()

    try:
        return PostgresRepository(settings.database_url)
    except RuntimeError as exc:
        if settings.is_strict_env:
            raise RuntimeError(
                f"PostgreSQL repository initialization failed when CRAMLY_ENV={settings.env}; "
                "refusing to fall back to MemoryRepository."
            ) from exc
    return MemoryRepository()


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right:
        return 0.0
    total = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left)) or 1.0
    right_norm = math.sqrt(sum(b * b for b in right)) or 1.0
    return total / (left_norm * right_norm)


def _vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(f"{value:.8f}" for value in vector) + "]"


def _parse_datetime(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _schedule_flashcard(card: dict, rating: str) -> dict:
    now = datetime.now(timezone.utc)
    interval = int(card.get("interval_days") or 0)
    ease = float(card.get("ease") or 2.5)

    if rating == "again":
        interval = 0
        ease = max(1.3, ease - 0.2)
        due_at = now + timedelta(minutes=10)
    elif rating == "hard":
        interval = max(1, interval)
        ease = max(1.3, ease - 0.1)
        due_at = now + timedelta(days=interval)
    elif rating == "easy":
        interval = 3 if interval == 0 else max(interval + 1, math.ceil(interval * (ease + 0.3)))
        ease = min(3.2, ease + 0.15)
        due_at = now + timedelta(days=interval)
    else:
        interval = 1 if interval == 0 else max(interval + 1, math.ceil(interval * ease))
        due_at = now + timedelta(days=interval)

    return {
        **card,
        "interval_days": interval,
        "ease": round(ease, 2),
        "due_at": due_at.isoformat(),
        "last_reviewed_at": now.isoformat(),
    }
