from __future__ import annotations

import json
import random
import uuid

from app.schemas import Flashcard, FlashcardResponse, QuizQuestion, QuizResponse, StudyPlanResponse, WeakTopic
from app.services.llm import OpenAILearningClient


class StudyService:
    def __init__(self, repo, llm: OpenAILearningClient):
        self.repo = repo
        self.llm = llm

    def flashcards(self, topic: str | None, count: int, context: str | None = None) -> FlashcardResponse:
        prompt = (
            "Create durable study flashcards as JSON with a cards array. "
            "Each card needs question, answer, and topic. Put a term, concept, definition prompt, "
            "or application question on the front. Put a concise but useful answer on the back. "
            "Avoid trivia-only cards; focus on recall, distinctions, mechanisms, and exam-ready explanations. "
            f"Count: {count}. Topic: {topic or 'uploaded material'}.\n"
            f"Context: {context or 'Use general knowledge.'}"
        )
        content, metadata = self.llm.chat(
            [
                {"role": "system", "content": "You create high-yield study flashcards."},
                {"role": "user", "content": prompt},
            ],
            json_mode=True,
        )
        cards = _safe_json(content).get("cards", [])
        return FlashcardResponse(
            cards=[
                Flashcard(
                    question=str(card.get("question", "What should I remember?")),
                    answer=str(card.get("answer", "Review the main idea and an example.")),
                    topic=str(card.get("topic", topic or "general")),
                    source_label="uploaded_materials" if context else "general_openai",
                )
                for card in cards[:count]
            ],
            metadata=metadata,
        )

    def quiz(self, topic: str | None, count: int, context: str | None = None) -> QuizResponse:
        quiz_id = str(uuid.uuid4())
        prompt = (
            "Create a challenging multiple-choice quiz as JSON with a questions array. "
            "Each question needs type='multiple_choice', prompt, choices, answer, topic, and explanation. "
            "Each question must have exactly 4 choices, and answer must exactly match one choice. "
            "Write college-level questions that test mechanisms, distinctions, transfer, and common misconceptions. "
            "Distractors must be plausible, similar in length and specificity, and based on realistic misunderstandings. "
            "Do not use joke answers, obviously unrelated choices, 'all of the above', or 'none of the above'. "
            f"Count: {count}. Topic: {topic or 'uploaded material'}.\n"
            f"Context: {context or 'Use general knowledge.'}"
        )
        content, metadata = self.llm.chat(
            [
                {"role": "system", "content": "You write fair quizzes that reveal weak areas."},
                {"role": "user", "content": prompt},
            ],
            json_mode=True,
        )
        data = _safe_json(content).get("questions", [])
        questions = [_multiple_choice_question(item, topic or "general") for item in data[:count]]
        return QuizResponse(
            id=quiz_id,
            source_label="uploaded_materials" if context else "general_openai",
            questions=questions,
            metadata=metadata,
        )

    def weak_topics(self, user_id: str) -> list[WeakTopic]:
        topics = []
        for row in self.repo.weak_topics(user_id):
            topic = row["topic"]
            topics.append(
                WeakTopic(
                    topic=topic,
                    misses=row["misses"],
                    attempts=row["attempts"],
                    accuracy=row["accuracy"],
                    recommendation=f"Review {topic}, then answer 3 retrieval questions without looking at notes.",
                )
            )
        return topics

    def study_plan(self, user_id: str) -> StudyPlanResponse:
        weak = self.weak_topics(user_id)
        focus = [topic.topic for topic in weak[:3]]
        if not focus:
            focus = ["upload materials", "ask a question", "take a quiz"]
        return StudyPlanResponse(
            focus_topics=focus,
            plan=[
                "Upload your first set of notes, slides, or transcript.",
                "Ask Cramly a question that should be answered from your material.",
                "Generate a short quiz and mark anything you miss.",
                "Review weak topics before creating your next study plan.",
            ],
            metadata={"source": "weak_topics" if weak else "empty_state"},
        )


def _safe_json(content: str) -> dict:
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return {"cards": [], "questions": []}


def _multiple_choice_question(item: dict, fallback_topic: str) -> QuizQuestion:
    topic = str(item.get("topic", fallback_topic) or fallback_topic)
    answer = str(item.get("answer", "The best answer identifies the mechanism and why it matters.")).strip()
    prompt = str(item.get("prompt", f"Which option best explains {topic}?")).strip()
    explanation = str(item.get("explanation", "Review why the correct choice fits better than the distractors.")).strip()

    choices: list[str] = []
    for choice in item.get("choices", []):
        value = str(choice).strip()
        if value and value.lower() not in {existing.lower() for existing in choices}:
            choices.append(value)

    choices = [choice for choice in choices if choice.lower() != answer.lower()]
    distractor_seeds = [
        f"It correctly names {topic}, but reverses the cause-and-effect relationship.",
        f"It describes a related idea, but leaves out the key mechanism that makes {topic} work.",
        f"It applies only in a narrow case and would not explain the broader pattern.",
        f"It sounds similar, but confuses the evidence for {topic} with the result of {topic}.",
    ]
    for seed in distractor_seeds:
        if len(choices) >= 3:
            break
        if seed.lower() not in {existing.lower() for existing in choices}:
            choices.append(seed)

    choices = choices[:3] + [answer]
    random.shuffle(choices)
    return QuizQuestion(
        id=str(uuid.uuid4()),
        type="multiple_choice",
        prompt=prompt,
        choices=choices,
        answer=answer,
        topic=topic,
        explanation=explanation,
    )
