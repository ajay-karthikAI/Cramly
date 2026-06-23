from __future__ import annotations

import base64
import hashlib
import json
import math
import mimetypes
import re
from typing import Any

from app.config import Settings


class OpenAILearningClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._client = None
        if settings.openai_api_key and not _is_placeholder_key(settings.openai_api_key):
            try:
                from openai import OpenAI

                self._client = OpenAI(api_key=settings.openai_api_key)
            except Exception as exc:
                if not settings.allow_demo_mode:
                    raise RuntimeError("OpenAI SDK could not be initialized.") from exc
        elif not settings.allow_demo_mode:
            raise RuntimeError("OPENAI_API_KEY is required. Set it in your environment before starting Cramly.")

    @property
    def live(self) -> bool:
        return self._client is not None and bool(self.settings.openai_api_key)

    def chat(self, messages: list[dict[str, str]], temperature: float = 0.2, json_mode: bool = False) -> tuple[str, dict]:
        if self.live:
            kwargs: dict[str, Any] = {
                "model": self.settings.openai_model,
                "messages": messages,
                "temperature": temperature,
            }
            if json_mode:
                kwargs["response_format"] = {"type": "json_object"}
            response = self._client.chat.completions.create(**kwargs)
            content = response.choices[0].message.content or ""
            metadata = {
                "provider": "openai",
                "model": self.settings.openai_model,
                "usage": response.usage.model_dump() if response.usage else {},
            }
            return content, metadata

        if not self.settings.allow_demo_mode:
            raise RuntimeError("OpenAI chat is unavailable because OPENAI_API_KEY is not configured.")

        prompt = messages[-1]["content"] if messages else ""
        if json_mode:
            return json.dumps(_demo_json(prompt)), {"provider": "demo", "model": "demo-mode"}
        return _demo_text(prompt), {"provider": "demo", "model": "demo-mode"}

    def embed_texts(self, texts: list[str]) -> tuple[list[list[float]], dict]:
        if self.live:
            response = self._client.embeddings.create(
                model=self.settings.openai_embedding_model,
                input=texts,
            )
            return [item.embedding for item in response.data], {
                "provider": "openai",
                "model": self.settings.openai_embedding_model,
            }

        if not self.settings.allow_demo_mode:
            raise RuntimeError("OpenAI embeddings are unavailable because OPENAI_API_KEY is not configured.")

        return [_demo_embedding(text) for text in texts], {
            "provider": "demo",
            "model": "hash-bow-1536",
        }

    def ocr_image(self, filename: str, content: bytes) -> tuple[str, dict]:
        if self.live:
            mime_type = mimetypes.guess_type(filename)[0] or "image/png"
            data_url = f"data:{mime_type};base64,{base64.b64encode(content).decode('ascii')}"
            response = self._client.chat.completions.create(
                model=self.settings.openai_model,
                temperature=0,
                messages=[
                    {
                        "role": "system",
                        "content": "You extract study notes from images. Return only the readable text, preserving headings and lists.",
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "Extract all readable text from this image for a student study app. If nothing is readable, say nothing.",
                            },
                            {"type": "image_url", "image_url": {"url": data_url}},
                        ],
                    },
                ],
            )
            return response.choices[0].message.content or "", {
                "provider": "openai",
                "model": self.settings.openai_model,
                "usage": response.usage.model_dump() if response.usage else {},
            }

        if not self.settings.allow_demo_mode:
            raise RuntimeError("Image OCR needs OPENAI_API_KEY and a vision-capable OPENAI_MODEL.")

        return f"Demo OCR text extracted from {filename}.", {"provider": "demo", "model": "demo-mode"}


def _demo_embedding(text: str, dimensions: int = 1536) -> list[float]:
    vector = [0.0] * dimensions
    words = re.findall(r"[a-zA-Z][a-zA-Z\-]{2,}", text.lower())
    for word in words:
        digest = hashlib.sha256(word.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % dimensions
        vector[index] += 1.0
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / norm for value in vector]


def _is_placeholder_key(api_key: str) -> bool:
    return api_key.strip() in {"", "sk-your-openai-api-key", "your_key", "your-openai-api-key"}


def _demo_text(prompt: str) -> str:
    lowered = prompt.lower()
    if "uploaded-material excerpts" in lowered and "photosynthesis" in lowered:
        return (
            "Your lecture frames photosynthesis as an energy conversion process, not just "
            "\"plants eating sunlight.\" The notes say chlorophyll absorbs light, water is split, "
            "oxygen is released, and the Calvin cycle uses carbon dioxide with ATP and NADPH to "
            "build sugar. A good analogy from the notes is a solar-powered kitchen: light powers "
            "the work, carbon dioxide is an ingredient, and glucose is stored food."
        )
    if "photosynthesis" in lowered:
        return (
            "Photosynthesis is how plants turn light energy into stored chemical energy. "
            "Chlorophyll captures sunlight, water is split, carbon dioxide is rearranged, "
            "and glucose is made for the plant to use later. A simple analogy: the leaf is "
            "a tiny solar-powered kitchen."
        )
    if "study plan" in lowered:
        return "Review weak topics first, test yourself with short quizzes, then finish with flashcards due today."
    return (
        "Here is a concise study explanation with an example and a quick check-for-understanding question. "
        "Connect the concept to what you already know, then practice retrieving it without notes."
    )


def _demo_json(prompt: str) -> dict:
    lowered = prompt.lower()
    topic = "photosynthesis" if "photosynthesis" in lowered else "core concept"
    if "flashcard" in lowered:
        return {
            "cards": [
                {
                    "question": f"What is the big idea behind {topic}?",
                    "answer": f"{topic.title()} is best learned by naming the process, inputs, outputs, and why it matters.",
                    "topic": topic,
                },
                {
                    "question": f"What is one useful analogy for {topic}?",
                    "answer": "Treat the system like a small factory: inputs enter, steps transform them, and useful outputs leave.",
                    "topic": topic,
                },
            ]
        }
    return {
        "questions": [
            {
                "type": "multiple_choice",
                "prompt": f"Which option best explains how to study {topic} as a mechanism rather than as memorized facts?",
                "choices": [
                    "Identify the purpose, trace the ordered steps, and connect each input to an output.",
                    "Memorize isolated vocabulary terms before deciding how they relate to each other.",
                    "Start with an analogy and treat it as a replacement for the actual process.",
                    "Focus on the final result while skipping the conditions that make it possible.",
                ],
                "answer": "Identify the purpose, trace the ordered steps, and connect each input to an output.",
                "topic": topic,
                "explanation": "Harder exam questions usually test relationships between steps, not isolated labels.",
            },
            {
                "type": "multiple_choice",
                "prompt": f"A student understands the terms in {topic} but misses application questions. What is the most likely gap?",
                "choices": [
                    "They have not connected the terms to cause, sequence, evidence, and boundary conditions.",
                    "They need fewer examples so the definition stays simpler and easier to repeat.",
                    "They should ignore edge cases until they can recite every sentence from the notes.",
                    "They are overthinking because application questions only require recognizing keywords.",
                ],
                "answer": "They have not connected the terms to cause, sequence, evidence, and boundary conditions.",
                "topic": topic,
                "explanation": "Application questions expose whether a student can use the concept, not just recognize its wording.",
            },
        ]
    }
