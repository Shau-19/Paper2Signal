"""
PaperSignal — LLM Router
Priority chain:
  Agent 1 & 3  → Groq Llama-3.3-70b           (fast, free)
  Agent 2      → DeepSeek-R1 via HF router     (reasoning)
  Agent 4      → The Sentinel via HF Space     (GRPO hype detection)
  Fallback     → OpenAI GPT-4o-mini            (when all else fails)
"""
'''
import json
import logging
import re
import time
from enum import Enum
from typing import Optional

import httpx
from config.settings import settings

logger = logging.getLogger(__name__)

# ── URLs ──────────────────────────────────────────────────────────────────────

GROQ_URL      = "https://api.groq.com/openai/v1/chat/completions"
OPENAI_URL    = "https://api.openai.com/v1/chat/completions"
HF_ROUTER_URL = "https://router.huggingface.co/v1/chat/completions"
SENTINEL_URL  = "https://shau1905-papersignal-sentinal.hf.space/run/predict"


class ModelType(str, Enum):
    REASONING = "reasoning"
    FAST      = "fast"
    HYPE      = "hype"


# ── Sentinel state tracker ────────────────────────────────────────────────────

class SentinelState:
    """Tracks Sentinel Space warmth and latency history."""
    last_call_time: float = 0.0       # epoch of last successful call
    last_latency_s: float = 0.0       # seconds taken by last call
    avg_latency_s: float  = 0.0       # rolling average
    call_count: int       = 0         # total calls
    fail_count: int       = 0         # total failures
    is_warm: bool         = False     # True if called within last 25 min
    last_error: str       = ""        # last error message

    def record_success(self, latency: float):
        self.last_call_time = time.time()
        self.last_latency_s = round(latency, 1)
        self.call_count += 1
        # Rolling average (simple EMA with α=0.3)
        if self.avg_latency_s == 0:
            self.avg_latency_s = latency
        else:
            self.avg_latency_s = round(0.3 * latency + 0.7 * self.avg_latency_s, 1)
        self.is_warm = True
        self.last_error = ""

    def record_failure(self, error: str):
        self.fail_count += 1
        self.last_error = error

    def check_warmth(self):
        """Mark as cold if not called in 25 minutes."""
        if self.last_call_time and (time.time() - self.last_call_time) > 1500:
            self.is_warm = False

    def to_dict(self) -> dict:
        self.check_warmth()
        return {
            "is_warm":        self.is_warm,
            "last_latency_s": self.last_latency_s,
            "avg_latency_s":  self.avg_latency_s,
            "call_count":     self.call_count,
            "fail_count":     self.fail_count,
            "last_error":     self.last_error,
            "last_call_ago_s": round(time.time() - self.last_call_time, 0) if self.last_call_time else None,
        }


sentinel_state = SentinelState()


# ── Agent 1 & 3: Groq Llama-3.3-70b (fast) ───────────────────────────────────

async def _call_groq(system: str, user: str) -> Optional[str]:
    if not settings.GROQ_API_KEY:
        return None
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                GROQ_URL,
                headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}"},
                json={
                    "model": settings.GROQ_FAST_MODEL,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user",   "content": user},
                    ],
                    "max_tokens": settings.LLM_MAX_TOKENS,
                    "temperature": 0.3,
                },
            )
            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]["content"].strip()
            logger.warning(f"[Groq] {resp.status_code}: {resp.text[:150]}")
    except Exception as e:
        logger.warning(f"[Groq] Failed: {e}")
    return None


# ── Agent 2: DeepSeek-R1-Distill-Llama-8B via HF Router (reasoning) ──────────

async def _call_deepseek(system: str, user: str) -> Optional[str]:
    if not settings.HF_API_KEY:
        return None
    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            resp = await client.post(
                HF_ROUTER_URL,
                headers={"Authorization": f"Bearer {settings.HF_API_KEY}"},
                json={
                    "model": settings.HF_REASONING_MODEL,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user",   "content": user},
                    ],
                    "max_tokens": settings.LLM_MAX_TOKENS,
                    "temperature": 0.3,
                },
            )
            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]["content"].strip()
            logger.warning(f"[DeepSeek] {resp.status_code}: {resp.text[:150]}")
    except Exception as e:
        logger.warning(f"[DeepSeek] Failed: {e}")
    return None


# ── Agent 4: The Sentinel — GRPO fine-tuned via HF Space ─────────────────────


async def _call_sentinel(abstract: str) -> Optional[str]:
    """
    Call local GRPO hype model instead of HF Space.
    Keeps SentinelState tracking intact.
    """
    t_start = time.time()
    warm_hint = "warm" if sentinel_state.is_warm else "cold-start"
    logger.info(f"[Sentinel-Local] Calling ({warm_hint}) ...")

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                "http://localhost:8001/predict",
                json={"abstract": abstract[:800]},
                timeout=120.0,
            )

            if resp.status_code != 200:
                err = f"HTTP {resp.status_code}"
                sentinel_state.record_failure(err)
                logger.warning(f"[Sentinel-Local] {err}")
                return None

            data = resp.json()

            # Track success
            latency = time.time() - t_start
            sentinel_state.record_success(latency)

            logger.info(
                f"[Sentinel-Local] Done in {latency:.1f}s "
                f"(avg {sentinel_state.avg_latency_s:.1f}s, "
                f"calls={sentinel_state.call_count})"
            )

            # IMPORTANT: return string for compatibility with parser
            return json.dumps({
                "hype_score": data.get("hype_score"),
                "reason": data.get("reason", "")
            })

    except Exception as e:
        err = str(e)[:100]
        sentinel_state.record_failure(err)
        logger.warning(f"[Sentinel-Local] Failed after {time.time()-t_start:.1f}s: {err}")

    return None


async def ping_sentinel() -> bool:
    """
    Lightweight keep-alive ping to The Sentinel Space.
    Sends a minimal abstract so the Space stays warm.
    Call this every 20 minutes via background task.
    """
    test_abstract = "A new method for efficient deep learning inference."
    logger.info("[Sentinel] Sending keep-alive ping...")
    result = await _call_sentinel(test_abstract)
    if result:
        logger.info(f"[Sentinel] Keep-alive OK — Space is warm")
        return True
    logger.warning("[Sentinel] Keep-alive failed — Space may be cold")
    return False


# ── Fallback: OpenAI GPT-4o-mini ─────────────────────────────────────────────

async def _call_openai(system: str, user: str) -> Optional[str]:
    if not settings.OPENAI_API_KEY:
        return None
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                OPENAI_URL,
                headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
                json={
                    "model": settings.OPENAI_FALLBACK_MODEL,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user",   "content": user},
                    ],
                    "max_tokens": settings.LLM_MAX_TOKENS,
                    "temperature": 0.3,
                },
            )
            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]["content"].strip()
            logger.warning(f"[OpenAI] {resp.status_code}")
    except Exception as e:
        logger.warning(f"[OpenAI] Failed: {e}")
    return None


# ── Main entrypoint ───────────────────────────────────────────────────────────

async def llm_call(
    system: str,
    user: str,
    model_type: ModelType = ModelType.FAST,
) -> str:
    """
    Route LLM calls by model type. Never raises — always returns string.

    FAST      → Groq Llama-3.3-70b          (Agent 1, Agent 3, RAG chat)
    REASONING → DeepSeek-R1 via HF router   (Agent 2 production scoring)
    HYPE      → The Sentinel via HF Space   (Agent 4 hype detection)
    Fallback  → OpenAI GPT-4o-mini
    """
    result = None

    # Agent 2: DeepSeek-R1 reasoning
    if model_type == ModelType.REASONING:
        logger.info("[Router] Agent 2 → DeepSeek-R1 (HF)")
        result = await _call_deepseek(system, user)

    # Agent 4: The Sentinel — GRPO hype model via HF Space
    elif model_type == ModelType.HYPE:
        logger.info("[Router] Agent 4 → Local GRPO Sentinel")

        try:
            # 🔥 Extract ONLY abstract from prompt
            if "Abstract:" in user:
                abstract = user.split("Abstract:")[-1].strip()
            else:
                abstract = user  # fallback (just in case)

            raw = await _call_sentinel(abstract)
            return raw or ""

        except Exception as e:
            logger.warning(f"[Sentinel-Local] Failed: {e}")
            return ""

    # Agent 1, 3, RAG: Groq fast
    if result is None:
        logger.info("[Router] Fast → Groq Llama-3.3-70b")
        result = await _call_groq(system, user)

    # Final fallback: OpenAI
    if result is None:
        logger.info("[Router] Fallback → OpenAI GPT-4o-mini")
        result = await _call_openai(system, user)

    if result is None:
        logger.error("[Router] All models failed")
        return ""

    return result'''



"""
PaperSignal — LLM Router

Priority chain:
  Agent 1 & 3  → Groq Llama-3.3-70b           (fast, free, with retry)
  Agent 2      → DeepSeek-R1 via HF router     (reasoning)
  Agent 4      → Sentinel local port 8001       (GRPO hype detection)
  Direct       → OpenAI GPT-4o-mini            (when model_pref="openai")
  Fallback     → OpenAI GPT-4o-mini            (when all else fails)

Changes vs previous:
  - ModelType.OPENAI added for direct model selection
  - Groq: exponential backoff retry on 429 (rate limit)
  - Groq: 3 attempts max before falling back to OpenAI
"""

import asyncio
import json
import logging
import re
import time
from enum import Enum
from typing import Optional

import httpx
from config.settings import settings

logger = logging.getLogger(__name__)

GROQ_URL      = "https://api.groq.com/openai/v1/chat/completions"
OPENAI_URL    = "https://api.openai.com/v1/chat/completions"
HF_ROUTER_URL = "https://router.huggingface.co/v1/chat/completions"


class ModelType(str, Enum):
    REASONING = "reasoning"
    FAST      = "fast"
    HYPE      = "hype"
    OPENAI    = "openai"    # direct OpenAI, no fallback chain


# ── Sentinel state tracker ────────────────────────────────────────────────────

class SentinelState:
    last_call_time: float = 0.0
    last_latency_s: float = 0.0
    avg_latency_s:  float = 0.0
    call_count:     int   = 0
    fail_count:     int   = 0
    is_warm:        bool  = False
    last_error:     str   = ""

    def record_success(self, latency: float):
        self.last_call_time = time.time()
        self.last_latency_s = round(latency, 1)
        self.call_count    += 1
        self.avg_latency_s  = round(
            0.3 * latency + 0.7 * self.avg_latency_s if self.avg_latency_s else latency, 1
        )
        self.is_warm   = True
        self.last_error = ""

    def record_failure(self, error: str):
        self.fail_count += 1
        self.last_error  = error

    def check_warmth(self):
        if self.last_call_time and (time.time() - self.last_call_time) > 1500:
            self.is_warm = False

    def to_dict(self) -> dict:
        self.check_warmth()
        return {
            "is_warm":         self.is_warm,
            "last_latency_s":  self.last_latency_s,
            "avg_latency_s":   self.avg_latency_s,
            "call_count":      self.call_count,
            "fail_count":      self.fail_count,
            "last_error":      self.last_error,
            "last_call_ago_s": round(time.time() - self.last_call_time, 0) if self.last_call_time else None,
        }


sentinel_state = SentinelState()


# ── Agent 1 & 3: Groq Llama-3.3-70b ─────────────────────────────────────────
# Exponential backoff on 429 — handles rate limits gracefully
# without failing the entire request chain.

async def _call_groq(system: str, user: str, max_retries: int = 3) -> Optional[str]:
    if not settings.GROQ_API_KEY:
        return None

    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    GROQ_URL,
                    headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}"},
                    json={
                        "model":       settings.GROQ_FAST_MODEL,
                        "messages":    [
                            {"role": "system", "content": system},
                            {"role": "user",   "content": user},
                        ],
                        "max_tokens":  settings.LLM_MAX_TOKENS,
                        "temperature": 0.3,
                    },
                )

                if resp.status_code == 200:
                    content = resp.json()["choices"][0]["message"]["content"]
                    if content is None:
                        logger.warning("[Groq] Response content is None")
                        return None
                    return content.strip()

                if resp.status_code == 429:
                    wait = 2 ** attempt   # 1s → 2s → 4s
                    logger.warning(f"[Groq] Rate limited (attempt {attempt+1}/{max_retries}) — retrying in {wait}s")
                    await asyncio.sleep(wait)
                    continue

                logger.warning(f"[Groq] {resp.status_code}: {resp.text[:150]}")
                return None

        except Exception as e:
            logger.warning(f"[Groq] Attempt {attempt+1} failed: {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(1)

    logger.warning("[Groq] All retries exhausted")
    return None


# ── Agent 2: DeepSeek-R1 via HF Router ───────────────────────────────────────

async def _call_deepseek(system: str, user: str) -> Optional[str]:
    if not settings.HF_API_KEY:
        return None
    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            resp = await client.post(
                HF_ROUTER_URL,
                headers={"Authorization": f"Bearer {settings.HF_API_KEY}"},
                json={
                    "model":       settings.HF_REASONING_MODEL,
                    "messages":    [
                        {"role": "system", "content": system},
                        {"role": "user",   "content": user},
                    ],
                    "max_tokens":  settings.LLM_MAX_TOKENS,
                    "temperature": 0.3,
                },
            )
            if resp.status_code == 200:
                content = resp.json()["choices"][0]["message"]["content"]
                if content is None:
                    logger.warning("[DeepSeek] Response content is None")
                    return None
                return content.strip()
            logger.warning(f"[DeepSeek] {resp.status_code}: {resp.text[:150]}")
    except Exception as e:
        logger.warning(f"[DeepSeek] Failed: {e}")
    return None


# ── Agent 4: Sentinel — local GRPO model on port 8001 ────────────────────────

async def _call_sentinel(abstract: str) -> Optional[str]:
    """
    Call local GRPO hype model on port 8001.
    Returns JSON string {"hype_score": float, "reason": str} or None.
    """
    t_start = time.time()
    logger.info(f"[Sentinel] Calling ({'warm' if sentinel_state.is_warm else 'cold'})...")

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                "http://localhost:8001/predict",
                json={"abstract": abstract[:800]},
            )
            if resp.status_code != 200:
                err = f"HTTP {resp.status_code}"
                sentinel_state.record_failure(err)
                logger.warning(f"[Sentinel] {err}")
                return None

            data    = resp.json()
            latency = time.time() - t_start
            sentinel_state.record_success(latency)
            logger.info(f"[Sentinel] Done in {latency:.1f}s (calls={sentinel_state.call_count})")

            return json.dumps({
                "hype_score": data.get("hype_score"),
                "reason":     data.get("reason", ""),
            })

    except Exception as e:
        err = str(e)[:100]
        sentinel_state.record_failure(err)
        logger.warning(f"[Sentinel] Failed after {time.time()-t_start:.1f}s: {err}")
    return None


async def ping_sentinel() -> bool:
    result = await _call_sentinel("A new method for efficient deep learning inference.")
    if result:
        logger.info("[Sentinel] Keep-alive OK")
        return True
    logger.warning("[Sentinel] Keep-alive failed")
    return False


# ── OpenAI GPT-4o-mini ────────────────────────────────────────────────────────

async def _call_openai(system: str, user: str) -> Optional[str]:
    if not settings.OPENAI_API_KEY:
        return None
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                OPENAI_URL,
                headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
                json={
                    "model":       settings.OPENAI_FALLBACK_MODEL,
                    "messages":    [
                        {"role": "system", "content": system},
                        {"role": "user",   "content": user},
                    ],
                    "max_tokens":  settings.LLM_MAX_TOKENS,
                    "temperature": 0.3,
                },
            )
            if resp.status_code == 200:
                content = resp.json()["choices"][0]["message"]["content"]
                if content is None:
                    return None
                return content.strip()
            logger.warning(f"[OpenAI] {resp.status_code}: {resp.text[:100]}")
    except Exception as e:
        logger.warning(f"[OpenAI] Failed: {e}")
    return None


# ── Main router ───────────────────────────────────────────────────────────────

async def llm_call(
    system:     str,
    user:       str,
    model_type: ModelType = ModelType.FAST,
) -> str:
    """
    Route LLM calls by model type. Never raises — always returns string.

    OPENAI    → OpenAI direct, falls back to Groq if fails
    FAST      → Groq with retry, falls back to OpenAI
    REASONING → DeepSeek-R1 via HF router, falls back to Groq
    HYPE      → Sentinel ONLY — never falls back (generic = useless)
    """

    # ── OPENAI: direct, Groq fallback ────────────────────────────────────────
    if model_type == ModelType.OPENAI:
        logger.info("[Router] Direct → OpenAI GPT-4o-mini")
        result = await _call_openai(system, user)
        if result:
            return result
        logger.warning("[Router] OpenAI failed → Groq fallback")
        result = await _call_groq(system, user)
        return result or ""

    # ── HYPE: Sentinel only ───────────────────────────────────────────────────
    if model_type == ModelType.HYPE:
        abstract = user.split("Abstract:")[-1].strip() if "Abstract:" in user else user
        try:
            raw = await _call_sentinel(abstract)
            return raw or ""
        except Exception as e:
            logger.warning(f"[Sentinel] Failed: {e}")
            return ""

    # ── REASONING: DeepSeek → Groq fallback ──────────────────────────────────
    if model_type == ModelType.REASONING:
        logger.info("[Router] Agent 2 → DeepSeek-R1 (HF)")
        result = await _call_deepseek(system, user)
        if result:
            return result
        logger.warning("[Router] DeepSeek failed → Groq fallback")

    # ── FAST + reasoning fallback: Groq (with retry) ─────────────────────────
    result = await _call_groq(system, user)
    if result:
        return result

    # ── Final fallback: OpenAI ────────────────────────────────────────────────
    logger.info("[Router] Groq failed → OpenAI fallback")
    result = await _call_openai(system, user)
    if result:
        return result

    logger.error("[Router] All models failed")
    return ""