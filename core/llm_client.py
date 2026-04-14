"""
core/llm_client.py

Two LLM backends:
  llm    — GeminiClient  (planning / synthesis / critique)
  ollama — OllamaClient  (native ollama Python library, extraction)

GLM-5 setup guide
─────────────────
glm-5:cloud   → 744B cloud model via Ollama Cloud. Requires free account.
                1. ollama signin
                2. ollama pull glm-5:cloud
                3. .env:  OLLAMA_MODEL=glm-5:cloud

glm4          → Local 9B model (~5GB RAM).
                1. ollama pull glm4
                2. .env:  OLLAMA_MODEL=glm4

glm-4.7-flash → Best local option, 30B (~17GB).
                1. ollama pull glm-4.7-flash
                2. .env:  OLLAMA_MODEL=glm-4.7-flash
"""
from __future__ import annotations

import asyncio
import json
import re
from typing import Any, List, Optional, Type, TypeVar

from google import genai
from loguru import logger
from pydantic import BaseModel
from tenacity import retry, stop_after_attempt, wait_exponential

import ollama as ollama_lib
from ollama import AsyncClient as OllamaAsyncClient

from config import settings

T = TypeVar("T", bound=BaseModel)


# ─────────────────────────────────────────────────────────────────────────────
# Gemini Client
# ─────────────────────────────────────────────────────────────────────────────

class GeminiClient:
    def __init__(self):
        self.client = genai.Client(api_key=settings.GEMINI_API_KEY)
        self.model = settings.GEMINI_MODEL

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=2, max=12))
    def generate_text(self, prompt: str) -> str:
        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config={"temperature": settings.GEMINI_TEMPERATURE},
            )
            return response.text
        except Exception as e:
            logger.error(f"[Gemini] generate_text failed: {e}")
            raise

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=2, max=12))
    def generate_structured(self, prompt: str, schema: Type[T]) -> T:
        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config={
                    "temperature": settings.GEMINI_TEMPERATURE,
                    "response_mime_type": "application/json",
                    "response_json_schema": schema.model_json_schema(),
                },
            )
            return schema.model_validate_json(response.text)
        except Exception as e:
            logger.error(f"[Gemini] generate_structured failed: {e}")
            raise

    async def generate_text_async(self, prompt: str) -> str:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.generate_text, prompt)

    async def generate_structured_async(self, prompt: str, schema: Type[T]) -> T:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.generate_structured, prompt, schema)


# ─────────────────────────────────────────────────────────────────────────────
# Ollama Client  (uses official `ollama` Python library)
# ─────────────────────────────────────────────────────────────────────────────

class OllamaClient:
    """
    Official usage pattern (from ollama-python docs):

        # Sync
        from ollama import chat
        response = chat(model='glm-5:cloud', messages=[...])
        print(response.message.content)

        # Async
        from ollama import AsyncClient
        response = await AsyncClient().chat(model='glm-5:cloud', messages=[...])

        # Structured output (pass Pydantic schema)
        response = chat(
            model='glm4',
            messages=[...],
            format=MyModel.model_json_schema(),
            options={'temperature': 0}
        )
        result = MyModel.model_validate_json(response.message.content)
    """

    def __init__(self):
        self.model = settings.OLLAMA_MODEL
        self.host = settings.OLLAMA_BASE_URL
        self._available: Optional[bool] = None
        self._async_client = OllamaAsyncClient(host=self.host)

    # ── Availability check ────────────────────────────────────────────────────

    async def check_available(self) -> bool:
        """Return True if Ollama is running and the model is pulled."""
        if not settings.OLLAMA_ENABLED:
            return False
        try:
            tags = await self._async_client.list()
            model_names = [m.model for m in (tags.models or [])]
            model_base = self.model.split(":")[0].lower()
            found = any(model_base in name.lower() for name in model_names)
            if not found:
                logger.warning(
                    f"[Ollama] '{self.model}' not found. Available: {model_names}. "
                    f"Run:  ollama pull {self.model}"
                )
            self._available = found
            return found
        except Exception as e:
            logger.debug(f"[Ollama] Not reachable at {self.host}: {e}")
            self._available = False
            return False

    # ── Async generation ──────────────────────────────────────────────────────

    async def generate_text_async(self, prompt: str) -> str:
        """
        Async text generation.

        Equivalent to official docs:
            response = await AsyncClient().chat(model=..., messages=[...])
            return response.message.content
        """
        response = await self._async_client.chat(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0.1, "num_predict": 2048},
        )
        return response.message.content

    async def generate_json_async(self, prompt: str) -> Any:
        """
        Async JSON generation using ollama's built-in format='json'.

        Equivalent to:
            response = chat(model=..., messages=[...], format='json')
            return json.loads(response.message.content)
        """
        response = await self._async_client.chat(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            format="json",
            options={"temperature": 0.05, "num_predict": 4096},
        )
        raw = response.message.content
        # Strip accidental markdown code fences
        raw = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.IGNORECASE)
        raw = re.sub(r"\s*```$", "", raw)
        return json.loads(raw.strip())

    async def generate_structured_async(self, prompt: str, schema: Type[T]) -> T:
        """
        Full Pydantic schema enforcement via ollama format parameter.

        Equivalent to official structured output pattern:
            response = chat(
                model=model,
                messages=[...],
                format=MySchema.model_json_schema(),
                options={'temperature': 0}
            )
            return MySchema.model_validate_json(response.message.content)
        """
        response = await self._async_client.chat(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            format=schema.model_json_schema(),
            options={"temperature": 0, "num_predict": 4096},
        )
        return schema.model_validate_json(response.message.content)

    # ── Evidence extraction (primary use case in this project) ─────────────────

    async def extract_evidence(self, paragraph: str, topic: str) -> List[dict]:
        """
        Extract factual claims from a paragraph using GLM.

        Returns a list of:  [{claim: str, category: str, confidence: float}, ...]

        This replaces the 400-line heuristic keyword matcher in extraction_agent.py
        with an LLM that understands language context, negation, and semantics.
        """
        prompt = f"""You are a scientific evidence extractor.

Topic context: {topic}

Extract ALL factual claims from the paragraph below.

Return a JSON array. Each item must have exactly these keys:
- "claim": the factual statement (max 200 chars)
- "category": one of result|method|metric|limitation|comparison|trend|definition|conclusion
- "confidence": float 0.0-1.0

Rules:
- Extract objective factual statements only — not opinions, marketing, navigation text
- Set confidence >= 0.7 for claims with numbers, named methods, or specific data
- Return [] if no factual claims are found
- Return ONLY the JSON array, nothing else

Paragraph:
{paragraph[:2000]}"""

        try:
            result = await self.generate_json_async(prompt)

            # Normalise possible wrapper objects
            if not isinstance(result, list):
                for key in ("items", "claims", "evidence", "results", "data"):
                    if isinstance(result, dict) and isinstance(result.get(key), list):
                        result = result[key]
                        break
                else:
                    return []

            valid_cats = {
                "result", "method", "metric", "limitation", "comparison",
                "trend", "definition", "conclusion", "algorithm", "dataset",
            }
            cleaned = []
            for item in result:
                if not isinstance(item, dict):
                    continue
                claim = str(item.get("claim", "")).strip()
                if len(claim) < 20:
                    continue
                cat = str(item.get("category", "unknown")).lower().strip()
                conf = float(item.get("confidence", 0.5))
                cleaned.append({
                    "claim": claim[:200],
                    "category": cat if cat in valid_cats else "unknown",
                    "confidence": max(0.0, min(1.0, conf)),
                })
            return cleaned

        except json.JSONDecodeError:
            logger.debug("[Ollama] JSON decode failed in extract_evidence")
            return []
        except Exception as e:
            logger.warning(f"[Ollama] extract_evidence failed: {e}")
            return []

    # ── Sync wrappers (for non-async contexts like CLI main.py) ───────────────

    def generate_text(self, prompt: str) -> str:
        """
        Synchronous text generation using the official ollama library.

        Matches official usage:
            from ollama import chat
            response = chat(model='glm-5:cloud', messages=[{'role':'user','content':'...'}])
            print(response.message.content)
        """
        response = ollama_lib.chat(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0.1, "num_predict": 2048},
        )
        return response.message.content

    def generate_structured(self, prompt: str, schema: Type[T]) -> T:
        """Synchronous structured generation for CLI use."""
        response = ollama_lib.chat(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            format=schema.model_json_schema(),
            options={"temperature": 0, "num_predict": 4096},
        )
        return schema.model_validate_json(response.message.content)


llm = GeminiClient()
ollama = OllamaClient()
