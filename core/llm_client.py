"""
core/llm_client.py

Two LLM backends:
  llm         — GeminiClient   (planning / synthesis / critique / extraction)
  groq_client — GroqClient     (unused fallback)
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import threading
import time
from typing import Any, List, Optional, Type, TypeVar

from google import genai
from groq import AsyncGroq, Groq
from loguru import logger
from pydantic import BaseModel, Field
from tenacity import retry, stop_after_attempt, wait_exponential

from config import settings

T = TypeVar("T", bound=BaseModel)


# ─────────────────────────────────────────────────────────────────────────────
# Extraction Pydantic Schemas
# ─────────────────────────────────────────────────────────────────────────────

class ExtractedClaim(BaseModel):
    claim: str = Field(description="The factual statement extracted, max 180 characters. Objective and specific.")
    category: str = Field(description="One of: result, method, metric, limitation, comparison, trend, definition, conclusion, algorithm, dataset")
    confidence: float = Field(description="Confidence score between 0.0 and 1.0. High (>= 0.7) for specific claims with numbers, study citations, or named methods.")
    para: int = Field(description="The 1-based index of the paragraph the claim came from.")

class ExtractedClaimsList(BaseModel):
    items: List[ExtractedClaim]


# ─────────────────────────────────────────────────────────────────────────────
# Gemini Client  (planning / synthesis / critique / extraction)
# ─────────────────────────────────────────────────────────────────────────────

class GeminiClient:
    def __init__(self):
        self.high_reasoning_model = settings.GEMINI_HIGH_REASONING_MODEL
        self.volume_model = settings.GEMINI_VOLUME_MODEL
        self.model = settings.GEMINI_HIGH_REASONING_MODEL  # for compatibility
        self.high_reasoning_fallback_active = False

        # Combine singular key and plural keys list, preserving uniqueness
        self.api_keys = []
        if settings.GEMINI_API_KEY:
            self.api_keys.append(settings.GEMINI_API_KEY.strip())
        if settings.GEMINI_API_KEYS:
            for k in settings.GEMINI_API_KEYS.split(","):
                k_stripped = k.strip()
                if k_stripped and k_stripped not in self.api_keys:
                    self.api_keys.append(k_stripped)
        
        self.current_key_idx = 0
        self.exhausted_keys = set()
        self._lock = threading.Lock()
        self._init_client()

    def _init_client(self):
        if not self.api_keys:
            logger.error("[Gemini] No API keys configured in settings.GEMINI_API_KEY or GEMINI_API_KEYS.")
            self.client = None
            return
        current_key = self.api_keys[self.current_key_idx]
        masked_key = current_key[:6] + "..." + current_key[-4:] if len(current_key) > 10 else "..."
        logger.info(f"[Gemini] Initialized client with key index {self.current_key_idx} ({masked_key})")
        self.client = genai.Client(api_key=current_key)

    def rotate_key(self, failed_key_idx: int, e: Exception):
        with self._lock:
            # If it's a daily limit error, mark this key index as permanently exhausted
            err_str = str(e)
            if "GenerateRequestsPerDay" in err_str or "PerDay" in err_str:
                if failed_key_idx not in self.exhausted_keys:
                    self.exhausted_keys.add(failed_key_idx)
                    logger.warning(f"[Gemini] Key index {failed_key_idx} marked as daily/permanently exhausted.")

            # Only rotate if the key that failed is still the active key
            if self.current_key_idx == failed_key_idx:
                rotated = False
                for step in range(1, len(self.api_keys)):
                    candidate_idx = (failed_key_idx + step) % len(self.api_keys)
                    if candidate_idx not in self.exhausted_keys:
                        old_idx = self.current_key_idx
                        self.current_key_idx = candidate_idx
                        self._init_client()
                        logger.info(f"[Gemini] Rotated key from index {old_idx} to {self.current_key_idx} due to failure.")
                        rotated = True
                        break
                
                # If all keys are marked exhausted, fallback to resetting and rotating sequentially
                if not rotated and len(self.api_keys) > 1:
                    self.exhausted_keys.clear()
                    old_idx = self.current_key_idx
                    self.current_key_idx = (self.current_key_idx + 1) % len(self.api_keys)
                    self._init_client()
                    logger.info(f"[Gemini] All keys marked exhausted. Resetting and rotating to index {self.current_key_idx}.")

    def _get_retry_delay(self, e: Exception) -> float:
        err_str = str(e)
        match = re.search(r"['\"]retryDelay['\"]\s*:\s*['\"](\d+(?:\.\d+)?)s?['\"]", err_str)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                pass
        if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
            return 30.0
        return 0.0

    @retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=2, min=4, max=45))
    async def generate_text_async(self, prompt: str, high_reasoning: bool = True) -> str:
        model_used = self.volume_model if (not high_reasoning or self.high_reasoning_fallback_active) else self.high_reasoning_model
        attempt_key_idx = self.current_key_idx
        client = self.client
        if not client:
            raise ValueError("[Gemini] API Client not initialized. Please verify your GEMINI_API_KEY environment variable.")
        try:
            response = await client.aio.models.generate_content(
                model=model_used,
                contents=prompt,
                config={"temperature": settings.GEMINI_TEMPERATURE},
            )
            return response.text
        except Exception as e:
            logger.error(f"[Gemini] generate_text failed (key index {attempt_key_idx}, model {model_used}): {e}")
            err_str = str(e)
            is_quota_error = "GenerateRequestsPerDay" in err_str or "PerDay" in err_str or "quota" in err_str.lower() or "RESOURCE_EXHAUSTED" in err_str
            
            if is_quota_error and model_used == self.high_reasoning_model:
                with self._lock:
                    if attempt_key_idx not in self.exhausted_keys:
                        self.exhausted_keys.add(attempt_key_idx)
                        logger.warning(f"[Gemini] Key index {attempt_key_idx} marked as exhausted for high-reasoning model due to daily limit.")
                    
                    if len(self.exhausted_keys) >= len(self.api_keys):
                        logger.warning("[Gemini] All keys exhausted for high-reasoning model. Activating fallback to volume model.")
                        self.high_reasoning_fallback_active = True
            
            delay = self._get_retry_delay(e)
            if delay > 0:
                logger.warning(f"[Gemini] Rate limited. Sleeping for {delay + 1:.2f}s before retry...")
                await asyncio.sleep(delay + 1.0)
            self.rotate_key(attempt_key_idx, e)
            raise

    @retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=2, min=4, max=45))
    async def generate_structured_async(self, prompt: str, schema: Type[T], high_reasoning: bool = True) -> T:
        model_used = self.volume_model if (not high_reasoning or self.high_reasoning_fallback_active) else self.high_reasoning_model
        attempt_key_idx = self.current_key_idx
        client = self.client
        if not client:
            raise ValueError("[Gemini] API Client not initialized. Please verify your GEMINI_API_KEY environment variable.")
        try:
            response = await client.aio.models.generate_content(
                model=model_used,
                contents=prompt,
                config={
                    "temperature": settings.GEMINI_TEMPERATURE,
                    "response_mime_type": "application/json",
                    "response_json_schema": schema.model_json_schema(),
                },
            )
            return schema.model_validate_json(response.text)
        except Exception as e:
            logger.error(f"[Gemini] generate_structured failed (key index {attempt_key_idx}, model {model_used}): {e}")
            err_str = str(e)
            is_quota_error = "GenerateRequestsPerDay" in err_str or "PerDay" in err_str or "quota" in err_str.lower() or "RESOURCE_EXHAUSTED" in err_str
            
            if is_quota_error and model_used == self.high_reasoning_model:
                with self._lock:
                    if attempt_key_idx not in self.exhausted_keys:
                        self.exhausted_keys.add(attempt_key_idx)
                        logger.warning(f"[Gemini] Key index {attempt_key_idx} marked as exhausted for high-reasoning model due to daily limit.")
                    
                    if len(self.exhausted_keys) >= len(self.api_keys):
                        logger.warning("[Gemini] All keys exhausted for high-reasoning model. Activating fallback to volume model.")
                        self.high_reasoning_fallback_active = True
            
            delay = self._get_retry_delay(e)
            if delay > 0:
                logger.warning(f"[Gemini] Rate limited. Sleeping for {delay + 1:.2f}s before retry...")
                await asyncio.sleep(delay + 1.0)
            self.rotate_key(attempt_key_idx, e)
            raise

    async def extract_evidence_async(self, paragraphs: List[str], topic: str, source_title: str) -> List[dict]:
        """
        Extract factual claims from a batch of paragraphs using the volume model (gemini-3.1-flash-lite).
        Returns a list of dictionaries with claim, category, confidence, and para number.
        """
        numbered = "\n\n".join(f"[P{i+1}] {p}" for i, p in enumerate(paragraphs))

        prompt = f"""You are a scientific evidence extractor.

Topic: {topic}
Source: {source_title[:100]}

Extract ALL factual claims from the numbered paragraphs below.

Rules:
- Only objective factual statements — no opinions, marketing, navigation text
- Skip boilerplate (cookie notices, sign up prompts, etc.)
- Set confidence >= 0.7 for claims with specific numbers, study citations, or named methods
- Return an empty list if no factual claims found

Paragraphs:
{numbered[:3000]}"""

        try:
            result = await self.generate_structured_async(prompt, ExtractedClaimsList, high_reasoning=False)
            return [item.model_dump() for item in result.items]
        except Exception as e:
            logger.error(f"[Gemini] Structured extraction failed: {e}")
            return []


# ─────────────────────────────────────────────────────────────────────────────
# Groq Client  (unused fallback)
# ─────────────────────────────────────────────────────────────────────────────

class GroqClient:
    """
    Groq API client using the official `groq` Python SDK.
    Used for high-throughput extraction tasks (Llama 3.3 70B runs at ~300 tok/s on Groq hardware).
    """

    def __init__(self):
        self.model = settings.GROQ_MODEL
        api_key = settings.GROQ_API_KEY or os.environ.get("GROQ_API_KEY")
        if api_key:
            try:
                self._async_client = AsyncGroq(api_key=api_key)
                self._sync_client = Groq(api_key=api_key)
            except Exception as e:
                logger.warning(f"[Groq] Initialization failed: {e}")
                self._async_client = None
                self._sync_client = None
        else:
            self._async_client = None
            self._sync_client = None

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
    async def generate_json_async(self, prompt: str) -> Any:
        """
        Generate a JSON response from Groq. Returns parsed Python object.
        Uses Groq's JSON mode for reliable JSON output.
        """
        if not self._async_client:
            logger.warning("[Groq] generate_json_async called but Groq API key is missing.")
            return []

        response = await self._async_client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.05,
            max_tokens=4096,
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content or ""
        # Strip any accidental markdown fences
        raw = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.IGNORECASE)
        raw = re.sub(r"\s*```$", "", raw)
        try:
            return json.loads(raw.strip())
        except json.JSONDecodeError as e:
            logger.debug(f"[Groq] JSON parse failed: {e} | raw={raw[:200]}")
            return []

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
    async def generate_text_async(self, prompt: str) -> str:
        """Generate plain text response from Groq."""
        if not self._async_client:
            logger.warning("[Groq] generate_text_async called but Groq API key is missing.")
            return ""

        response = await self._async_client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=2048,
        )
        return response.choices[0].message.content or ""

    async def extract_evidence(self, paragraphs: List[str], topic: str, source_title: str) -> List[dict]:
        """
        Extract factual claims from a batch of numbered paragraphs.
        Returns list of {claim, category, confidence, para} dicts.
        """
        if not self._async_client:
            logger.warning("[Groq] extract_evidence called but Groq API key is missing.")
            return []

        numbered = "\n\n".join(f"[P{i+1}] {p}" for i, p in enumerate(paragraphs))

        prompt = f"""You are a scientific evidence extractor.

Topic: {topic}
Source: {source_title[:100]}

Extract ALL factual claims from the numbered paragraphs below.

Return a JSON object with key "items" containing an array. Each item must have:
- "claim": the factual statement (max 180 chars, keep original wording)
- "category": one of result|method|metric|limitation|comparison|trend|definition|conclusion
- "confidence": float 0.0-1.0 (high for specific claims with numbers/named methods)
- "para": which paragraph number the claim came from (1, 2, 3...)

Rules:
- Only objective factual statements — no opinions, marketing, navigation text
- Skip boilerplate (cookie notices, sign up prompts, etc.)
- Set confidence >= 0.7 for claims with specific numbers, study citations, or named methods
- Return {{"items": []}} if no factual claims found

Paragraphs:
{numbered[:3000]}"""

        result = await self.generate_json_async(prompt)

        # Normalise: handle both array and object with "items" key
        if isinstance(result, list):
            items = result
        elif isinstance(result, dict):
            items = result.get("items") or result.get("claims") or result.get("evidence") or []
        else:
            items = []

        valid_cats = {
            "result", "method", "metric", "limitation", "comparison",
            "trend", "definition", "conclusion", "algorithm", "dataset",
        }
        cleaned = []
        for item in items:
            if not isinstance(item, dict):
                continue
            claim = str(item.get("claim", "")).strip()
            if len(claim) < 20:
                continue
            cat = str(item.get("category", "unknown")).lower().strip()
            conf = float(item.get("confidence", 0.5))
            para = int(item.get("para", 1))
            cleaned.append({
                "claim": claim[:200],
                "category": cat if cat in valid_cats else "unknown",
                "confidence": max(0.0, min(1.0, conf)),
                "para": para,
            })
        return cleaned


# ─────────────────────────────────────────────────────────────────────────────
# Module-level singletons
# ─────────────────────────────────────────────────────────────────────────────

llm = GeminiClient()
groq_client = GroqClient()
