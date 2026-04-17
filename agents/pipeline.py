

"""
PaperSignal — LangGraph Agent Pipeline
4 agents connected via LangGraph StateGraph:

  Agent 1 (Classifier)  → domain tags, novelty flag, key contributions
  Agent 2 (Scorer)      → production readiness score via DeepSeek-R1
  Agent 3 (Brief)       → final intelligence brief, guardrails validated
  Agent 4 (Hype)        → community traction prediction via GRPO model

Fixes applied:
  - Domain sanity cap: non-ML papers capped at 6.0 / Experiment
  - SCORER_SYSTEM: grounded reasoning — must reference abstract content
  - HYPE_SYSTEM: must cite specific concepts from abstract, not generic tags
  - agent_hype: if Sentinel is down, leaves hype_score=None (no fake fallback)
"""
'''
import json
import logging
import re
from typing import TypedDict, Optional
from langgraph.graph import StateGraph, END

from agents.llm_router import llm_call, ModelType
from agents.guardrails import run_guardrails
from ingestion.models import Paper

logger = logging.getLogger(__name__)

# ── Known ML domains — papers outside this get score capped ──────────────────
ML_DOMAINS = {
    "RAG", "Fine-tuning", "Reasoning", "Vision", "Multimodal",
    "LLM", "Diffusion", "NLP", "RL", "Agents", "Robotics",
    "Optimization", "Efficiency", "Training", "Alignment",
}

# ── Prompts ───────────────────────────────────────────────────────────────────

CLASSIFIER_SYSTEM = """You are an AI research classifier.
Analyze the paper and return ONLY valid JSON with these exact keys:
- domain: string — pick the MOST specific from this list:
  "RAG" | "Fine-tuning" | "Reasoning" | "Vision" | "Multimodal" |
  "LLM" | "Diffusion" | "NLP" | "RL" | "Agents" | "Robotics" |
  "Optimization" | "Efficiency" | "Training" | "Alignment" |
  "Other" (use Other ONLY for non-ML papers like sports, biology, etc.)
- novelty: string ("incremental" | "moderate" | "significant" | "breakthrough")
- contributions: list of 3 short strings, each max 10 words
- has_code: boolean (true if abstract mentions code/github/implementation)
Return ONLY JSON. No explanation. No markdown fences."""


SCORER_SYSTEM = """You are a brutally honest senior ML engineer deciding if a paper is usable in production TODAY.

IMPORTANT:
- Score based ONLY on what the abstract actually says
- Reference specific claims from the paper in your reasoning
- DO NOT give average scores — use the full 0–10 range
- Be decisive

SCORING GUIDE:
0–3 → useless, skip
4–5 → weak, theoretical, not practical
6–7 → promising, needs work, experiment
8–10 → strong, ship it, adopt

HARD RULES:
- No code mentioned → overall_score ≤ 6
- Pure theory, no experiments → overall_score ≤ 5
- Hard to reproduce → penalize
- Code + benchmarks + easy integration → boost
- Non-ML domain (sports, biology, etc.) → overall_score ≤ 5

Your reasoning MUST mention at least one specific method, result, or claim from the abstract.
Do NOT write generic sentences like "this paper shows promising results".

Return ONLY valid JSON:
{
  "overall_score": float,
  "reproducibility": float,
  "compute_cost": float,
  "latency": float,
  "adoption": float,
  "reasoning": "2 sentences referencing specific paper content"
}"""


BRIEF_SYSTEM = """You are a technical writer for senior AI engineers.
Write a concise intelligence brief. Return ONLY valid JSON:
- summary: string (2-3 sentences — what this paper does and why it matters for production)
- stack_fit: string (1 sentence — what existing stack this works with: PyTorch/HF/vLLM/etc)
- action: string ("Watch" | "Experiment" | "Adopt")
- action_reason: string (1 sentence why)
Return ONLY JSON. No markdown fences."""


HYPE_SYSTEM = """You are an AI research hype detector.

Predict how much buzz this paper will generate in the ML community.

STRICT SCORING RULES (VERY IMPORTANT):

8–10 → HIGH:
- clear real-world use (infra, efficiency, systems)
- code or easy implementation
- reduces cost / latency / memory significantly
- plug-and-play for existing stacks
- widely applicable (not niche)

6–7 → MED-HIGH:
- useful idea but limited scope OR no code

4–5 → MED:
- incremental improvement
- moderate usefulness
- unclear adoption

1–3 → LOW:
- theory only
- niche domain
- no experiments or implementation

CRITICAL:
- DO NOT default to 4–5
- If strong practical impact → MUST be 7+
- If theory/niche → MUST be ≤3
- If no experiments AND no code → score MUST be ≤3

GROUNDING RULE:
- Use specific phrases from abstract
- Avoid generic statements like "novel approach"

Respond ONLY in JSON:
{"hype_score": <float 1-10>, "reason": "<specific reason>"}"""


# ── State Definition ──────────────────────────────────────────────────────────

class PaperState(TypedDict):
    paper_id: str
    title: str
    abstract: str
    github_url: str
    velocity_score: float
    domain: Optional[str]
    novelty: Optional[str]
    contributions: Optional[list]
    has_code: Optional[bool]
    overall_score: Optional[float]
    reproducibility: Optional[float]
    compute_cost: Optional[float]
    latency: Optional[float]
    adoption: Optional[float]
    score_reasoning: Optional[str]
    summary: Optional[str]
    stack_fit: Optional[str]
    action: Optional[str]
    action_reason: Optional[str]
    hype_score: Optional[float]
    hype_reason: Optional[str]
    errors: list


# ── Agent 1: Classifier ───────────────────────────────────────────────────────

async def agent_classifier(state: PaperState) -> PaperState:
    logger.info(f"[Agent1/Classifier] {state['paper_id']}")
    user_prompt = f"Title: {state['title']}\n\nAbstract: {state['abstract']}"

    for attempt in range(2):
        raw = await llm_call(system=CLASSIFIER_SYSTEM, user=user_prompt, model_type=ModelType.FAST)
        result = run_guardrails(raw_output=raw, required_keys=["domain", "novelty", "contributions", "has_code"])
        if result.passed:
            state.update({
                "domain":        result.output.get("domain", "Other"),
                "novelty":       result.output.get("novelty", "incremental"),
                "contributions": result.output.get("contributions", []),
                "has_code":      bool(result.output.get("has_code", False)),
            })
            logger.info(f"[Agent1] domain={state['domain']} novelty={state['novelty']}")
            return state
        logger.warning(f"[Agent1] Attempt {attempt+1} failed: {result.errors}")

    state.update({"domain": "Other", "novelty": "incremental", "contributions": [], "has_code": False})
    state["errors"].append("classifier_failed")
    return state


# ── Agent 2: Scorer ───────────────────────────────────────────────────────────

async def agent_scorer(state: PaperState) -> PaperState:
    logger.info(f"[Agent2/Scorer] {state['paper_id']}")

    user_prompt = (
        f"Title: {state['title']}\n"
        f"Domain: {state['domain']}\n"
        f"Novelty: {state['novelty']}\n"
        f"Has code: {state['has_code']}\n"
        f"GitHub URL: {state['github_url'] or 'None'}\n"
        f"Velocity score: {state['velocity_score']}\n\n"
        f"Abstract: {state['abstract']}"
    )

    for attempt in range(2):
        raw = await llm_call(system=SCORER_SYSTEM, user=user_prompt, model_type=ModelType.REASONING)
        result = run_guardrails(
            raw_output=raw,
            required_keys=["overall_score", "reproducibility", "compute_cost", "latency", "adoption", "reasoning"],
            score_fields={
                "overall_score":  (0, 10),
                "reproducibility":(0, 10),
                "compute_cost":   (0, 10),
                "latency":        (0, 10),
                "adoption":       (0, 10),
            },
        )
        if result.passed:
            overall = float(result.output["overall_score"])
            logger.info(f"[Agent2] RAW score from DeepSeek: {overall}") 
            if overall < 1.0:
                overall *= 10
            logger.info(f"[Agent2] SCALED score: {overall}")  # Scale up low scores to use full range

            # ── Domain sanity cap ─────────────────────────────────────────────
            # Non-ML papers (sports, biology, etc.) should never score above 6
            if state.get("domain") not in ML_DOMAINS:
                if overall > 6.0:
                    logger.warning(
                        f"[Agent2] Domain '{state['domain']}' not in ML_DOMAINS — "
                        f"capping score {overall} → 6.0"
                    )
                    overall = 6.0

            state.update({
                "overall_score":   overall,
                "reproducibility": float(result.output["reproducibility"]),
                "compute_cost":    float(result.output["compute_cost"]),
                "latency":         float(result.output["latency"]),
                "adoption":        float(result.output["adoption"]),
                "score_reasoning": result.output.get("reasoning", ""),
            })
            logger.info(f"[Agent2] overall_score={state['overall_score']}")
            return state
        logger.warning(f"[Agent2] Attempt {attempt+1} failed: {result.errors}")

    state.update({"overall_score": 0.0, "score_reasoning": "scoring_failed"})
    state["errors"].append("scorer_failed")
    return state


# ── Agent 3: Brief ────────────────────────────────────────────────────────────

async def agent_brief(state: PaperState) -> PaperState:
    logger.info(f"[Agent3/Brief] {state['paper_id']}")

    user_prompt = (
        f"Title: {state['title']}\n"
        f"Domain: {state['domain']} | Novelty: {state['novelty']}\n"
        f"Production score: {state['overall_score']}/10\n"
        f"Reasoning: {state['score_reasoning']}\n"
        f"Key contributions: {json.dumps(state['contributions'])}\n\n"
        f"Abstract: {state['abstract']}"
    )

    for attempt in range(2):
        raw = await llm_call(system=BRIEF_SYSTEM, user=user_prompt, model_type=ModelType.FAST)
        result = run_guardrails(
            raw_output=raw,
            required_keys=["summary", "stack_fit", "action", "action_reason"],
            source_text=state["abstract"],
            claim_field="summary",
        )
        if result.passed:
            state.update({
                "summary":       result.output.get("summary", ""),
                "stack_fit":     result.output.get("stack_fit", ""),
                "action":        result.output.get("action", "Watch"),
                "action_reason": result.output.get("action_reason", ""),
            })

            # Action is always determined by score — LLM suggestion ignored
            score = state.get("overall_score", 0)
            if score < 4:
                state["action"] = "Skip"
            elif score < 6:
                state["action"] = "Experiment"
            elif score < 8:
                state["action"] = "Strong Experiment"
            else:
                state["action"] = "Adopt"

            logger.info(f"[Agent3] action={state['action']}")
            return state
        logger.warning(f"[Agent3] Attempt {attempt+1} failed: {result.errors}")

    state["errors"].append("brief_failed")
    return state


# ── Hype parser ───────────────────────────────────────────────────────────────

def _parse_hype_response(raw: str) -> tuple[float, str]:
    if not raw:
        return -1, ""

    cleaned = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
    cleaned = re.sub(r"```(?:json)?\s*|\s*```", "", cleaned).strip()

    try:
        parsed = json.loads(cleaned)
        score = float(parsed.get("hype_score", -1))
        if 1.0 <= score <= 10.0:
            return score, str(parsed.get("reason", ""))
    except Exception:
        pass

    m = re.search(r'"hype_score"\s*:\s*([0-9]+(?:\.[0-9]+)?)', raw)
    if m:
        score = float(m.group(1))
        if 1.0 <= score <= 10.0:
            r = re.search(r'"reason"\s*:\s*"([^"]{0,200})', raw)
            return score, r.group(1) if r else "parsed via fallback"

    return -1, ""


# ── Agent 4: Hype ─────────────────────────────────────────────────────────────

async def agent_hype(state: PaperState) -> PaperState:
    """
    Calls local Sentinel GRPO model.
    If Sentinel is down → hype_score stays None.
    We do NOT fall back to Groq for hype — generic Groq hype is worse than None.
    """
    logger.info(f"[Agent4/Hype] {state['paper_id']}")

    try:
        raw = await llm_call(
            system=HYPE_SYSTEM,
            user=f"Abstract:\n{state['abstract'][:800]}",
            model_type=ModelType.HYPE,
        )

        if not raw:
            raise ValueError("Empty response from hype model — Sentinel may be offline")

        score, reason = _parse_hype_response(raw)

        if score > 0:
            state.update({"hype_score": round(score, 1), "hype_reason": reason})
            logger.info(f"[Agent4] hype_score={state['hype_score']} | {reason[:60]}")
        else:
            raise ValueError(f"Parse failed: {raw[:80]}")

    except Exception as e:
        logger.warning(f"[Agent4/Hype] Failed: {e} — hype_score=None")
        state.update({"hype_score": None, "hype_reason": None})
        state["errors"].append("hype_failed")

    return state


# ── Graph ─────────────────────────────────────────────────────────────────────

def build_pipeline():
    graph = StateGraph(PaperState)
    graph.add_node("classifier", agent_classifier)
    graph.add_node("scorer",     agent_scorer)
    graph.add_node("brief",      agent_brief)
    graph.add_node("hype",       agent_hype)
    graph.set_entry_point("classifier")
    graph.add_edge("classifier", "scorer")
    graph.add_edge("scorer",     "brief")
    graph.add_edge("brief",      "hype")
    graph.add_edge("hype",       END)
    return graph.compile()


_pipeline = None

def get_pipeline():
    global _pipeline
    if _pipeline is None:
        _pipeline = build_pipeline()
    return _pipeline


async def analyze_paper(paper: Paper) -> dict:
    initial_state = PaperState(
        paper_id=paper.id, title=paper.title, abstract=paper.abstract,
        github_url=paper.github_url or "", velocity_score=paper.velocity_score or 0.0,
        domain=None, novelty=None, contributions=None, has_code=None,
        overall_score=None, reproducibility=None, compute_cost=None,
        latency=None, adoption=None, score_reasoning=None,
        summary=None, stack_fit=None, action=None, action_reason=None,
        hype_score=None, hype_reason=None, errors=[],
    )
    pipeline = get_pipeline()
    final_state = await pipeline.ainvoke(initial_state)

    score = final_state.get("overall_score")
    hype  = final_state.get("hype_score")
    final_state["is_hidden_gem"] = bool(
        score is not None and hype is not None and score >= 7 and hype <= 4
    )
    return dict(final_state)'''



"""
PaperSignal — LangGraph Agent Pipeline
4 agents connected via LangGraph StateGraph:

  Agent 1 (Classifier)  → domain tags, novelty flag, key contributions
  Agent 2 (Scorer)      → production readiness score via DeepSeek-R1
  Agent 3 (Brief)       → final intelligence brief, guardrails validated
  Agent 4 (Hype)        → community traction prediction via GRPO model

Fixes applied:
  - Domain sanity cap: non-ML papers capped at 6.0
  - Infra+code floor: papers with efficiency signals + code floored at 7.0
  - SCORER_SYSTEM: grounded reasoning — must reference abstract content
  - HYPE_SYSTEM: updated strict scoring rules matching Sentinel training
  - agent_hype: signal-based correction after GRPO output
  - agent_hype: if Sentinel is down, leaves hype_score=None (no fake fallback)
"""

import json
import logging
import re
from typing import TypedDict, Optional
from langgraph.graph import StateGraph, END

from agents.llm_router import llm_call, ModelType
from agents.guardrails import run_guardrails
from ingestion.models import Paper

logger = logging.getLogger(__name__)

# ── Known ML domains — papers outside this get score capped ──────────────────
ML_DOMAINS = {
    "RAG", "Fine-tuning", "Reasoning", "Vision", "Multimodal",
    "LLM", "Diffusion", "NLP", "RL", "Agents", "Robotics",
    "Optimization", "Efficiency", "Training", "Alignment",
}

# ── Signal keywords ───────────────────────────────────────────────────────────
THEORY_SIGNALS = [
    "bound", "bounds", "convergence", "proof", "theorem",
    "regularity", "theoretical", "asymptotic", "lemma",
]
PRACTICAL_SIGNALS = [
    "github", "code", "implementation", "released",
    "experiment", "benchmark", "dataset",
]
INFRA_SIGNALS = [
    "latency", "memory", "throughput", "faster", "speed",
    "flops", "utilization", "efficient", "compress", "quantiz",
]


# ── Prompts ───────────────────────────────────────────────────────────────────

CLASSIFIER_SYSTEM = """You are an AI research classifier.
Analyze the paper and return ONLY valid JSON with these exact keys:
- domain: string — pick the MOST specific from this list:
  "RAG" | "Fine-tuning" | "Reasoning" | "Vision" | "Multimodal" |
  "LLM" | "Diffusion" | "NLP" | "RL" | "Agents" | "Robotics" |
  "Optimization" | "Efficiency" | "Training" | "Alignment" |
  "Other" (use Other ONLY for non-ML papers like sports, biology, etc.)
- novelty: string ("incremental" | "moderate" | "significant" | "breakthrough")
- contributions: list of 3 short strings, each max 10 words
- has_code: boolean (true if abstract mentions code/github/implementation)
Return ONLY JSON. No explanation. No markdown fences."""


SCORER_SYSTEM = """You are a brutally honest senior ML engineer deciding if a paper is usable in production TODAY.

IMPORTANT:
- Score based ONLY on what the abstract actually says
- Reference specific claims from the paper in your reasoning
- DO NOT give average scores — use the full 0–10 range
- Be decisive

SCORING GUIDE:
0–3 → useless, skip
4–5 → weak, theoretical, not practical
6–7 → promising, needs work, experiment
8–10 → strong, ship it, adopt

HARD RULES:
- No code mentioned → overall_score ≤ 6
- Pure theory, no experiments → overall_score ≤ 5
- Hard to reproduce → penalize
- Code + benchmarks + easy integration → boost
- Non-ML domain (sports, biology, etc.) → overall_score ≤ 5

Your reasoning MUST mention at least one specific method, result, or claim from the abstract.
Do NOT write generic sentences like "this paper shows promising results".

Return ONLY valid JSON:
{
  "overall_score": float,
  "reproducibility": float,
  "compute_cost": float,
  "latency": float,
  "adoption": float,
  "reasoning": "2 sentences referencing specific paper content"
}"""


BRIEF_SYSTEM = """You are a technical writer for senior AI engineers.
Write a concise intelligence brief. Return ONLY valid JSON:
- summary: string (2-3 sentences — what this paper does and why it matters for production)
- stack_fit: string (1 sentence — what existing stack this works with: PyTorch/HF/vLLM/etc)
- action: string ("Watch" | "Experiment" | "Adopt")
- action_reason: string (1 sentence why)
Return ONLY JSON. No markdown fences."""


HYPE_SYSTEM = """You are an AI research hype detector.

Predict how much buzz this paper will generate in the ML community.

STRICT SCORING RULES (VERY IMPORTANT):

8–10 → HIGH:
- clear real-world use (infra, efficiency, systems)
- code or easy implementation
- reduces cost / latency / memory significantly
- plug-and-play for existing stacks
- widely applicable (not niche)

6–7 → MED-HIGH:
- useful idea but limited scope OR no code

4–5 → MED:
- incremental improvement
- moderate usefulness
- unclear adoption

1–3 → LOW:
- theory only
- niche domain
- no experiments or implementation

CRITICAL:
- DO NOT default to 4–5
- If strong practical impact → MUST be 7+
- If theory/niche → MUST be ≤3
- If no experiments AND no code → score MUST be ≤3

GROUNDING RULE:
- Use specific phrases from abstract
- Avoid generic statements like "novel approach"

Respond ONLY in JSON:
{"hype_score": <float 1-10>, "reason": "<specific reason>"}"""


# ── State Definition ──────────────────────────────────────────────────────────

class PaperState(TypedDict):
    paper_id: str
    title: str
    abstract: str
    github_url: str
    velocity_score: float
    domain: Optional[str]
    novelty: Optional[str]
    contributions: Optional[list]
    has_code: Optional[bool]
    overall_score: Optional[float]
    reproducibility: Optional[float]
    compute_cost: Optional[float]
    latency: Optional[float]
    adoption: Optional[float]
    score_reasoning: Optional[str]
    summary: Optional[str]
    stack_fit: Optional[str]
    action: Optional[str]
    action_reason: Optional[str]
    hype_score: Optional[float]
    hype_reason: Optional[str]
    errors: list


# ── Signal helpers ────────────────────────────────────────────────────────────

def _extract_signals(abstract: str, has_code_flag: bool = False) -> dict:
    """Extract binary signals from abstract text."""
    a = abstract.lower()
    has_practical = has_code_flag or any(x in a for x in PRACTICAL_SIGNALS)
    has_infra     = any(x in a for x in INFRA_SIGNALS)
    is_theory     = any(x in a for x in THEORY_SIGNALS)
    return {
        "has_practical": has_practical,
        "has_infra":     has_infra,
        "is_theory":     is_theory,
    }


# ── Agent 1: Classifier ───────────────────────────────────────────────────────

async def agent_classifier(state: PaperState) -> PaperState:
    logger.info(f"[Agent1/Classifier] {state['paper_id']}")
    user_prompt = f"Title: {state['title']}\n\nAbstract: {state['abstract']}"

    for attempt in range(2):
        raw = await llm_call(system=CLASSIFIER_SYSTEM, user=user_prompt, model_type=ModelType.FAST)
        result = run_guardrails(raw_output=raw, required_keys=["domain", "novelty", "contributions", "has_code"])
        if result.passed:
            state.update({
                "domain":        result.output.get("domain", "Other"),
                "novelty":       result.output.get("novelty", "incremental"),
                "contributions": result.output.get("contributions", []),
                "has_code":      bool(result.output.get("has_code", False)),
            })
            logger.info(f"[Agent1] domain={state['domain']} novelty={state['novelty']}")
            return state
        logger.warning(f"[Agent1] Attempt {attempt+1} failed: {result.errors}")

    state.update({"domain": "Other", "novelty": "incremental", "contributions": [], "has_code": False})
    state["errors"].append("classifier_failed")
    return state


# ── Agent 2: Scorer ───────────────────────────────────────────────────────────

async def agent_scorer(state: PaperState) -> PaperState:
    logger.info(f"[Agent2/Scorer] {state['paper_id']}")

    user_prompt = (
        f"Title: {state['title']}\n"
        f"Domain: {state['domain']}\n"
        f"Novelty: {state['novelty']}\n"
        f"Has code: {state['has_code']}\n"
        f"GitHub URL: {state['github_url'] or 'None'}\n"
        f"Velocity score: {state['velocity_score']}\n\n"
        f"Abstract: {state['abstract']}"
    )

    for attempt in range(2):
        raw = await llm_call(system=SCORER_SYSTEM, user=user_prompt, model_type=ModelType.REASONING)
        result = run_guardrails(
            raw_output=raw,
            required_keys=["overall_score", "reproducibility", "compute_cost", "latency", "adoption", "reasoning"],
            score_fields={
                "overall_score":  (0, 10),
                "reproducibility":(0, 10),
                "compute_cost":   (0, 10),
                "latency":        (0, 10),
                "adoption":       (0, 10),
            },
        )
        if result.passed:
            overall = float(result.output["overall_score"])

            # Scale normalized scores (DeepSeek sometimes outputs 0–1 range)
            if overall < 1.0:
                overall *= 10
            logger.info(f"[Agent2] score={overall}")

            # ── Domain sanity cap ─────────────────────────────────────────────
            if state.get("domain") not in ML_DOMAINS and overall > 6.0:
                logger.warning(f"[Agent2] Domain cap: {overall} → 6.0")
                overall = 6.0

            # ── Infra + code floor ────────────────────────────────────────────
            # Papers with clear efficiency gains + code should never score < 7
            sig = _extract_signals(state["abstract"], state.get("has_code", False))
            if sig["has_infra"] and sig["has_practical"] and overall < 7.0:
                logger.info(f"[Agent2] Infra+code floor: {overall} → 7.0")
                overall = 7.0

            state.update({
                "overall_score":   round(overall, 1),
                "reproducibility": float(result.output["reproducibility"]),
                "compute_cost":    float(result.output["compute_cost"]),
                "latency":         float(result.output["latency"]),
                "adoption":        float(result.output["adoption"]),
                "score_reasoning": result.output.get("reasoning", ""),
            })
            logger.info(f"[Agent2] overall_score={state['overall_score']}")
            return state
        logger.warning(f"[Agent2] Attempt {attempt+1} failed: {result.errors}")

    state.update({"overall_score": 0.0, "score_reasoning": "scoring_failed"})
    state["errors"].append("scorer_failed")
    return state


# ── Agent 3: Brief ────────────────────────────────────────────────────────────

async def agent_brief(state: PaperState) -> PaperState:
    logger.info(f"[Agent3/Brief] {state['paper_id']}")

    user_prompt = (
        f"Title: {state['title']}\n"
        f"Domain: {state['domain']} | Novelty: {state['novelty']}\n"
        f"Production score: {state['overall_score']}/10\n"
        f"Reasoning: {state['score_reasoning']}\n"
        f"Key contributions: {json.dumps(state['contributions'])}\n\n"
        f"Abstract: {state['abstract']}"
    )

    for attempt in range(2):
        raw = await llm_call(system=BRIEF_SYSTEM, user=user_prompt, model_type=ModelType.FAST)
        result = run_guardrails(
            raw_output=raw,
            required_keys=["summary", "stack_fit", "action", "action_reason"],
            source_text=state["abstract"],
            claim_field="summary",
        )
        if result.passed:
            state.update({
                "summary":       result.output.get("summary", ""),
                "stack_fit":     result.output.get("stack_fit", ""),
                "action":        result.output.get("action", "Watch"),
                "action_reason": result.output.get("action_reason", ""),
            })

            # Action always derived from score — never trust LLM on this
            score = state.get("overall_score", 0)
            if score < 4:
                state["action"] = "Skip"
            elif score < 6:
                state["action"] = "Experiment"
            elif score < 8:
                state["action"] = "Strong Experiment"
            else:
                state["action"] = "Adopt"

            logger.info(f"[Agent3] action={state['action']}")
            return state
        logger.warning(f"[Agent3] Attempt {attempt+1} failed: {result.errors}")

    state["errors"].append("brief_failed")
    return state


# ── Hype parser ───────────────────────────────────────────────────────────────

def _parse_hype_response(raw: str) -> tuple[float, str]:
    if not raw:
        return -1, ""

    cleaned = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
    cleaned = re.sub(r"```(?:json)?\s*|\s*```", "", cleaned).strip()

    try:
        parsed = json.loads(cleaned)
        score = float(parsed.get("hype_score", -1))
        if 1.0 <= score <= 10.0:
            return score, str(parsed.get("reason", ""))
    except Exception:
        pass

    m = re.search(r'"hype_score"\s*:\s*([0-9]+(?:\.[0-9]+)?)', raw)
    if m:
        score = float(m.group(1))
        if 1.0 <= score <= 10.0:
            r = re.search(r'"reason"\s*:\s*"([^"]{0,200})', raw)
            return score, r.group(1) if r else "parsed via fallback"

    return -1, ""


def _correct_hype_score(score: float, abstract: str) -> float:
    """
    Apply signal-based correction to GRPO output.
    Same rules as hype_model.py — must stay in sync.
    """
    sig = _extract_signals(abstract)

    # Pure theory, no practical signals → cap at 3
    if sig["is_theory"] and not sig["has_practical"]:
        score = min(score, 3.0)

    # No code/experiments at all → cap at 5
    if not sig["has_practical"]:
        score = min(score, 5.0)

    # Has code but no infra gains → cap at 6
    if sig["has_practical"] and not sig["has_infra"]:
        score = min(score, 6.0)

    # Infra + code → floor at 7
    if sig["has_infra"] and sig["has_practical"]:
        score = max(score, 7.0)

    return round(score, 1)


# ── Agent 4: Hype ─────────────────────────────────────────────────────────────

async def agent_hype(state: PaperState) -> PaperState:
    """
    Calls local Sentinel GRPO model then applies signal correction.
    If Sentinel is down → hype_score stays None.
    Never falls back to Groq — generic Groq hype is worse than None.
    """
    logger.info(f"[Agent4/Hype] {state['paper_id']}")

    try:
        raw = await llm_call(
            system=HYPE_SYSTEM,
            user=f"Abstract:\n{state['abstract'][:800]}",
            model_type=ModelType.HYPE,
        )

        if not raw:
            raise ValueError("Empty response — Sentinel may be offline")

        score, reason = _parse_hype_response(raw)

        if score < 0:
            raise ValueError(f"Parse failed: {raw[:80]}")

        # Apply same correction layer as hype_model.py
        corrected = _correct_hype_score(score, state["abstract"])
        if corrected != score:
            logger.info(f"[Agent4] Hype corrected: {score} → {corrected}")

        state.update({"hype_score": corrected, "hype_reason": reason})
        logger.info(f"[Agent4] hype_score={corrected} | {reason[:60]}")

    except Exception as e:
        logger.warning(f"[Agent4/Hype] Failed: {e} — hype_score=None")
        state.update({"hype_score": None, "hype_reason": None})
        state["errors"].append("hype_failed")

    return state


# ── Graph ─────────────────────────────────────────────────────────────────────

def build_pipeline():
    graph = StateGraph(PaperState)
    graph.add_node("classifier", agent_classifier)
    graph.add_node("scorer",     agent_scorer)
    graph.add_node("brief",      agent_brief)
    graph.add_node("hype",       agent_hype)
    graph.set_entry_point("classifier")
    graph.add_edge("classifier", "scorer")
    graph.add_edge("scorer",     "brief")
    graph.add_edge("brief",      "hype")
    graph.add_edge("hype",       END)
    return graph.compile()


_pipeline = None

def get_pipeline():
    global _pipeline
    if _pipeline is None:
        _pipeline = build_pipeline()
    return _pipeline


async def analyze_paper(paper: Paper) -> dict:
    initial_state = PaperState(
        paper_id=paper.id, title=paper.title, abstract=paper.abstract,
        github_url=paper.github_url or "", velocity_score=paper.velocity_score or 0.0,
        domain=None, novelty=None, contributions=None, has_code=None,
        overall_score=None, reproducibility=None, compute_cost=None,
        latency=None, adoption=None, score_reasoning=None,
        summary=None, stack_fit=None, action=None, action_reason=None,
        hype_score=None, hype_reason=None, errors=[],
    )
    pipeline = get_pipeline()
    final_state = await pipeline.ainvoke(initial_state)

    score = final_state.get("overall_score")
    hype  = final_state.get("hype_score")
    final_state["is_hidden_gem"] = bool(
        score is not None and hype is not None and score >= 7 and hype <= 4
    )
    return dict(final_state)