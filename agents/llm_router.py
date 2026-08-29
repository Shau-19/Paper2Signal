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


# # ── Agent 4: Sentinel — local GRPO model on port 8001 ────────────────────────
# 
# async def _call_sentinel(abstract: str) -> Optional[str]:
#     """
#     Call local GRPO hype model on port 8001.
#     Returns JSON string {"hype_score": float, "reason": str} or None.
#     """
#     t_start = time.time()
#     logger.info(f"[Sentinel] Calling ({'warm' if sentinel_state.is_warm else 'cold'})...")
# 
#     try:
#         async with httpx.AsyncClient(timeout=120.0) as client:
#             resp = await client.post(
#                 "http://localhost:8001/predict",
#                 json={"abstract": abstract[:800]},
#             )
#             if resp.status_code != 200:
#                 err = f"HTTP {resp.status_code}"
#                 sentinel_state.record_failure(err)
#                 logger.warning(f"[Sentinel] {err}")
#                 return None
# 
#             data    = resp.json()
#             latency = time.time() - t_start
#             sentinel_state.record_success(latency)
#             logger.info(f"[Sentinel] Done in {latency:.1f}s (calls={sentinel_state.call_count})")
# 
#             return json.dumps({
#                 "hype_score": data.get("hype_score"),
#                 "reason":     data.get("reason", ""),
#             })
# 
#     except Exception as e:
#         err = str(e)[:100]
#         sentinel_state.record_failure(err)
#         logger.warning(f"[Sentinel] Failed after {time.time()-t_start:.1f}s: {err}")
#     return None
# 
# 
# async def ping_sentinel() -> bool:
#     result = await _call_sentinel("A new method for efficient deep learning inference.")
#     if result:
#         logger.info("[Sentinel] Keep-alive OK")
#         return True
#     logger.warning("[Sentinel] Keep-alive failed")
#     return False

# ── Agent 4: Sentinel — local model + HF Serverless Fallback ──────────────────

SYSTEM_HYPE_PROMPT = """You are an AI research hype detector.

Predict how much buzz this paper will generate in the ML community.

STRICT SCORING RULES (VERY IMPORTANT):

8-10 -> HIGH:
- clear real-world use (infra, efficiency, systems)
- code or easy implementation
- reduces cost / latency / memory significantly
- plug-and-play for existing stacks
- widely applicable (not niche)

6-7 -> MED-HIGH:
- useful idea but limited scope OR no code

4-5 -> MED:
- incremental improvement
- moderate usefulness
- unclear adoption

1-3 -> LOW:
- theory only
- niche domain
- no experiments or implementation

CRITICAL:
- DO NOT default to 4-5
- If strong practical impact -> MUST be 7+
- If theory/niche -> MUST be <=3
- If no experiments AND no code -> score MUST be <=3

GROUNDING RULE:
- Use specific phrases from abstract
- Avoid generic statements like "novel approach"

Respond ONLY in JSON:
{"hype_score": <float 1-10>, "reason": "<specific reason>"}"""

async def _call_sentinel(abstract: str) -> Optional[str]:
    """
    Call local GRPO hype model on port 8001.
    If offline or connection fails, falls back automatically to
    Hugging Face Serverless Inference API using settings.HF_API_KEY.
    """
    t_start = time.time()
    logger.info(f"[Sentinel] Calling ({'warm' if sentinel_state.is_warm else 'cold'})...")

    # Try local port first with a fast timeout (5 seconds for ping, 60 seconds query)
    local_online = False
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            h_resp = await client.get("http://localhost:8001/health")
            if h_resp.status_code == 200:
                local_online = True
    except Exception:
        pass

    if local_online:
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    "http://localhost:8001/predict",
                    json={"abstract": abstract[:800]},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    latency = time.time() - t_start
                    sentinel_state.record_success(latency)
                    logger.info(f"[Sentinel] Local Query: Done in {latency:.1f}s (calls={sentinel_state.call_count})")
                    return json.dumps({
                        "hype_score": data.get("hype_score"),
                        "reason":     data.get("reason", ""),
                    })
                else:
                    logger.warning(f"[Sentinel] Local query returned HTTP {resp.status_code}")
        except Exception as e:
            logger.warning(f"[Sentinel] Local query exception: {e}")

    # Fallback to Hugging Face Serverless API
    logger.info("[Sentinel] Local model server is offline. Falling back to Hugging Face Serverless API...")
    if not settings.HF_API_KEY:
        logger.warning("[Sentinel] HF_API_KEY not configured. Cannot perform serverless fallback.")
        sentinel_state.record_failure("missing_hf_api_key")
        return None

    try:
        # Prompt formatted in ChatML style
        prompt = (
            f"<|im_start|>system\n{SYSTEM_HYPE_PROMPT}\n<|im_end|>\n"
            f"<|im_start|>user\nAbstract:\n{abstract[:800]}\n<|im_end|>\n"
            f"<|im_start|>assistant\n"
        )
        api_url = f"https://router.huggingface.co/hf-inference/models/{settings.HF_HYPE_MODEL}"

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                api_url,
                headers={"Authorization": f"Bearer {settings.HF_API_KEY}"},
                json={
                    "inputs": prompt,
                    "parameters": {"max_new_tokens": 100, "temperature": 0.2}
                }
            )

            if resp.status_code == 503:
                logger.warning("[Sentinel] HF model serverless API is loading (503). Retrying in 10s...")
                await asyncio.sleep(10)
                resp = await client.post(
                    api_url,
                    headers={"Authorization": f"Bearer {settings.HF_API_KEY}"},
                    json={
                        "inputs": prompt,
                        "parameters": {"max_new_tokens": 100, "temperature": 0.2}
                    }
                )

            if resp.status_code == 200:
                result = resp.json()
                text = result[0].get("generated_text", "") if isinstance(result, list) else result.get("generated_text", "")
                if "<|im_start|>assistant\n" in text:
                    text = text.split("<|im_start|>assistant\n")[-1].strip()
                
                # Check for basic Qwen ChatML end tokens
                text = text.replace("<|im_end|>", "").strip()

                # Verify parse sanity
                from agents.pipeline import _parse_hype_response
                score, reason = _parse_hype_response(text)
                if score > 0:
                    latency = time.time() - t_start
                    sentinel_state.record_success(latency)
                    logger.info(f"[Sentinel] HF API: Done in {latency:.1f}s")
                    return json.dumps({"hype_score": score, "reason": reason})

            logger.warning(f"[Sentinel] HF API Request failed with status {resp.status_code}: {resp.text[:150]}")
            sentinel_state.record_failure(f"hf_api_http_{resp.status_code}")

    except Exception as e:
        logger.warning(f"[Sentinel] HF API Exception occurred: {e}")
        sentinel_state.record_failure(f"hf_exception_{type(e).__name__}")

    return None


async def ping_sentinel() -> bool:
    # Try calling with a dummy query to ping
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
        # DeepSeek failed — record fallback before switching to Groq
        from agents.eval import record_fallback
        record_fallback("scorer")
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