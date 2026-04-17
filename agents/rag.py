

"""
Paper2Signal — RAG Engine v3

Two modes:
  1. global_chat()      — ChromaDB RAG across all papers
  2. deep_paper_chat()  — Paper-specific agent with PDF retrieval

Key improvements:
  - Response length calibrated to query type (formula → short, explain → long)
  - Model routing: math/implement → OpenAI, rest → Groq
  - Context leakage fix: LLM receives clean text, not label artifacts
  - retrieve_context passes paper_title + judge flag
  - Hallucination guard (keyword overlap check)
  - Off-topic guard
"""

import logging
import re
from typing import Optional

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

from config.settings import settings
from agents.llm_router import llm_call, ModelType

logger = logging.getLogger(__name__)


# ── ChromaDB (global paper collection) ───────────────────────────────────────

_embed_fn = None
_chroma   = None


def get_embed_fn():
    global _embed_fn
    if _embed_fn is None:
        _embed_fn = SentenceTransformerEmbeddingFunction(
            model_name=settings.EMBEDDING_MODEL
        )
    return _embed_fn


def get_collection():
    global _chroma
    if _chroma is None:
        client  = chromadb.PersistentClient(path=settings.CHROMA_PATH)
        _chroma = client.get_or_create_collection(
            name=settings.CHROMA_COLLECTION,
            embedding_function=get_embed_fn(),
        )
    return _chroma


# ── Global retrieval ──────────────────────────────────────────────────────────

def retrieve(query: str, n: int = 5, paper_id: Optional[str] = None) -> list[dict]:
    collection = get_collection()
    vector     = get_embed_fn()([query])[0]

    kwargs = {
        "query_embeddings": [vector],
        "n_results":        n,
        "include":          ["metadatas", "distances", "documents"],
    }
    if paper_id:
        kwargs["where"] = {"paper_id": paper_id}

    try:
        results = collection.query(**kwargs)
    except Exception as e:
        logger.warning(f"[RAG] ChromaDB query failed: {e}")
        return []

    papers = []
    ids    = results.get("ids",       [[]])[0]
    metas  = results.get("metadatas", [[]])[0]
    docs   = results.get("documents", [[]])[0]
    dists  = results.get("distances", [[]])[0]

    for i, pid in enumerate(ids):
        dist = dists[i] if i < len(dists) else 1.0
        if dist > 1.2:
            continue
        meta = metas[i] if i < len(metas) else {}
        papers.append({
            "id":              pid,
            "title":           meta.get("title", "Unknown"),
            "abstract":        docs[i] if i < len(docs) else "",
            "summary":         meta.get("summary", ""),
            "stack_fit":       meta.get("stack_fit", ""),
            "score_reasoning": meta.get("score_reasoning", ""),
            "overall_score":   meta.get("overall_score"),
            "action":          meta.get("action", ""),
            "arxiv_url":       meta.get("arxiv_url", ""),
            "distance":        dist,
        })
    return papers


def build_context(papers: list[dict]) -> str:
    if not papers:
        return "No relevant papers found."
    parts = []
    for i, p in enumerate(papers, 1):
        score = f"{p['overall_score']}/10" if p.get("overall_score") else "not scored"
        part  = (
            f"[Paper {i}] {p['title']}\n"
            f"Score: {score} | Action: {p.get('action','')}\n"
            f"Abstract: {p['abstract'][:350]}\n"
        )
        if p.get("summary"):   part += f"Summary: {p['summary']}\n"
        if p.get("stack_fit"): part += f"Stack Fit: {p['stack_fit']}\n"
        parts.append(part)
    return "\n---\n".join(parts)


def build_citations(papers: list[dict]) -> list[dict]:
    return [{
        "id":       p["id"],
        "title":    p["title"],
        "score":    p.get("overall_score"),
        "action":   p.get("action"),
        "url":      p.get("arxiv_url"),
        "distance": round(p.get("distance", 1.0), 3),
    } for p in papers]


# ── Off-topic guard ───────────────────────────────────────────────────────────

_BLOCK_PATTERNS = [
    r"\bwrite (me )?(a |an )?(poem|story|essay|song|joke|email|letter)\b",
    r"\bgenerate (a |an )?(image|picture|photo|video)\b",
    r"\bwhat('s| is) the weather\b",
    r"\b(bitcoin|crypto|stock price|exchange rate)\b",
    r"\bignore (all |previous |your )?(instructions|rules|system prompt)\b",
    r"\bforget (all |your )?(instructions|context)\b",
    r"\byou are now\b",
    r"\bjailbreak\b",
    r"\bbypass (your |all )?(filters|restrictions)\b",
    r"\breveal (your |the )?(api key|secret|password|token)\b",
]
_BLOCK_RE = [re.compile(p, re.IGNORECASE) for p in _BLOCK_PATTERNS]


def is_off_topic(query: str) -> bool:
    for pat in _BLOCK_RE:
        if pat.search(query):
            logger.warning(f"[Guard] Blocked: {query[:60]}")
            return True
    return False


# ── Intent detection ──────────────────────────────────────────────────────────

_FORMULA = [
    r"\b(formula|equation|notation|loss function|objective)\b",
    r"\bwhat('s| is) the (formula|equation|math|loss)\b",
    r"\bgive me the (formula|equation|expression)\b",
]
_MATH = [
    r"\b(proof|derivation|theorem|lemma|derive)\b",
    r"\bmath(ematical)?\b",
    r"\bshow (the |your )?(math|derivation|proof)\b",
]
_IMPLEMENT = [
    r"\b(implement|code|build|write|create|reproduce|script)\b",
    r"\bhow (do i|to|can i) (use|integrate|run|apply|set up)\b",
    r"\bgive me (the )?code\b",
    r"\bshow me (how|the code|an example)\b",
    r"\bhelp me (code|build|implement|use)\b",
]
_RESULTS = [
    r"\b(results?|findings?|performance|benchmark|accuracy|evaluation|scores?)\b",
    r"\bhow (well|good|much) does it\b",
    r"\bbeat|outperform|improve(ment)?\b",
]
_COMPARE = [
    r"\bvs\.?\b", r"\bversus\b", r"\bdifference between\b",
    r"\bcompare\b", r"\bbetter than\b",
    r"\badvantage|disadvantage|tradeoff\b",
]
_EXPLAIN = [
    r"\bwhat is\b", r"\bhow does\b", r"\bexplain\b",
    r"\bwhy does\b", r"\bintuition\b", r"\bbreak(down| it down)\b",
    r"\bsummar(ize|y)\b", r"\boverview\b",
]
_SHORT = [
    r"\bwho (wrote|authored|created)\b",
    r"\bwhen was\b",
    r"\bwhat year\b",
    r"\bhow many\b",
    r"\blist (the )?(authors?|papers?|methods?)\b",
]


def detect_intent(query: str) -> str:
    q = query.lower()
    for p in _FORMULA:
        if re.search(p, q, re.IGNORECASE): return "formula"
    for p in _MATH:
        if re.search(p, q, re.IGNORECASE): return "math"
    for p in _IMPLEMENT:
        if re.search(p, q, re.IGNORECASE): return "implement"
    for p in _RESULTS:
        if re.search(p, q, re.IGNORECASE): return "results"
    for p in _COMPARE:
        if re.search(p, q, re.IGNORECASE): return "compare"
    for p in _EXPLAIN:
        if re.search(p, q, re.IGNORECASE): return "explain"
    for p in _SHORT:
        if re.search(p, q, re.IGNORECASE): return "short"
    return "discuss"


# ── Response length guidance ──────────────────────────────────────────────────

_LENGTH_GUIDE = {
    "formula":   "Return the formula/equation directly. Use LaTeX. 2-3 sentences of explanation max.",
    "math":      "Show the full derivation step by step. Be precise with notation.",
    "implement": "Write complete, runnable code with comments. Include imports.",
    "results":   "Report exact numbers from the paper. Use bullet points for multiple metrics.",
    "compare":   "Side-by-side comparison. Be concise — one paragraph per dimension.",
    "explain":   "Thorough explanation with intuition. Use the paper's own framing.",
    "short":     "Answer in 1-2 sentences only. No preamble.",
    "discuss":   "Conversational but focused. 2-4 paragraphs max.",
}


# ── Model routing ─────────────────────────────────────────────────────────────

async def _generate(
    query:      str,
    context:    str,
    system:     str,
    history:    list[dict],
    model_pref: str = "auto",
) -> str:
    history_str = ""
    for turn in (history or [])[-4:]:
        role         = "User" if turn["role"] == "user" else "Assistant"
        history_str += f"{role}: {turn['content']}\n"

    user_prompt = f"{history_str}User: {query}\n\nContext:\n{context}"

    if model_pref == "openai":
        return await llm_call(system=system, user=user_prompt, model_type=ModelType.OPENAI)
    if model_pref == "groq":
        return await llm_call(system=system, user=user_prompt, model_type=ModelType.FAST)

    # auto: OpenAI for math/implement/formula (needs precision), Groq for rest
    intent = detect_intent(query)
    if intent in ("math", "implement", "formula"):
        return await llm_call(system=system, user=user_prompt, model_type=ModelType.OPENAI)
    return await llm_call(system=system, user=user_prompt, model_type=ModelType.FAST)


# ── Hallucination guard ───────────────────────────────────────────────────────

def _confidence_check(answer: str, context: str) -> str:
    if not context:
        return answer

    STOPWORDS = {
        "the","a","an","and","or","but","in","on","at","to","for","of",
        "with","by","from","is","are","was","were","this","that","we","our",
        "it","its","be","as","if","so","do","not","have","has","can","will",
    }

    def _kw(text: str) -> set:
        return {w.lower() for w in re.findall(r'\b[a-zA-Z]{5,}\b', text)
                if w.lower() not in STOPWORDS}

    answer_kw  = _kw(answer)
    context_kw = _kw(context)
    if not answer_kw:
        return answer

    overlap = len(answer_kw & context_kw) / len(answer_kw)
    if overlap < 0.15:
        return (
            answer +
            "\n\n*Note: Part of this answer draws on general knowledge beyond "
            "the retrieved sections. Verify against the original paper.*"
        )
    return answer


# ── System Prompts ────────────────────────────────────────────────────────────

GLOBAL_SYSTEM = """You are Paper2Signal — an AI research intelligence assistant for ML engineers.
You have access to a curated database of AI research papers scored for production readiness.

Answer based ONLY on the papers in the provided context. Be direct and actionable.
Always cite which paper you're referencing by name.
If no relevant paper exists in context, say so clearly.

When recommending papers, always mention:
- The paper's production score and action (Adopt / Experiment / Skip)
- Why it's relevant to the user's question
- The arxiv URL

Response style:
- Factual questions → concise prose
- Recommendation questions → clear verdict with reasoning and paper links
- Do NOT generate code unless explicitly asked"""


PAPER_AGENT_SYSTEM = """You are a world-class ML researcher and engineer who has read this paper in full.

Paper: {title}
Production Score: {score}/10 | Action: {action}

The context below contains exact text extracted from the paper.
Answer the user's question as an expert who knows this work inside and out.

Query intent: {intent}
Response length guidance: {length_guide}

Intent-specific instructions:
- FORMULA   → return the formula in LaTeX immediately, then explain variables briefly
- MATH      → show derivation step by step with notation from the paper
- IMPLEMENT → write complete code grounded in the paper's described method
- RESULTS   → report exact numbers/metrics from the paper's experiments
- COMPARE   → compare using what the paper itself says about related work
- EXPLAIN   → thorough explanation using the paper's own language and framing
- SHORT     → single sentence answer only
- DISCUSS   → conversational, 2-4 paragraphs

Citation format when drawing from specific parts:
- Page reference: [[page:N]]
- Section reference: [[section:Name]]

Critical rules:
1. Match response length to the query type — do NOT pad short-answer queries with explanations
2. Never say "based on chunks" or "retrieved text shows" — say "the paper shows", "in Section X"
3. If a formula is requested, lead with the formula in a code/math block, not prose
4. No hallucination: if genuinely not in this paper, say so once briefly then offer what IS known"""


# ── Public Interface ──────────────────────────────────────────────────────────

async def global_chat(
    query:      str,
    history:    Optional[list[dict]] = None,
    n_papers:   int = 5,
    model_pref: str = "auto",
) -> dict:
    if is_off_topic(query):
        return {
            "answer":    "I can only answer questions about AI research papers.",
            "citations": [],
            "n_sources": 0,
            "mode":      "blocked",
        }

    papers  = retrieve(query, n=n_papers)
    context = build_context(papers)
    answer  = await _generate(query, context, GLOBAL_SYSTEM, history or [], model_pref)

    return {
        "answer":    answer,
        "citations": build_citations(papers),
        "n_sources": len(papers),
        "mode":      "global",
        "model":     model_pref,
    }


async def deep_paper_chat(
    query:         str,
    paper_id:      str,
    paper_context: dict,
    history:       Optional[list[dict]] = None,
    model_pref:    str = "auto",
    doc_id:        Optional[str] = None,  # compatibility
) -> dict:
    """
    Paper-specific agent.
    Uses PDF chunks if indexed, abstract fallback if not.
    Response length calibrated to intent.
    Context leakage fixed — LLM receives clean text, not embedding labels.
    """
    history = history or []

    if is_off_topic(query):
        return {
            "answer":    "I can only answer questions about this paper.",
            "citations": [],
            "paper_id":  paper_id,
            "n_sources": 0,
            "mode":      "blocked",
        }

    intent = detect_intent(query)
    logger.info(f"[PaperAgent] intent={intent} model={model_pref} paper={paper_id}")

    # Intent → chunk count (formula/short queries need fewer, math/implement need more)
    n_chunks = {
        "formula":   6,
        "short":     6,
        "results":   10,
        "compare":   12,
        "explain":   12,
        "discuss":   10,
        "math":      15,
        "implement": 15,
    }.get(intent, 10)

    # ── Retrieve PDF chunks ───────────────────────────────────────────────────
    context_text = ""
    citations    = []
    mode         = "abstract"

    try:
        from ml.pdf_indexer import retrieve_context
        context_text, citations = await retrieve_context(
            paper_id    = paper_id,
            query       = query,
            n           = n_chunks,
            paper_title = paper_context.get("title", ""),
            run_judge   = intent in ("explain", "discuss"),
        )
        logger.info(
            f"[PaperAgent] retrieved {len(context_text)} chars, "
            f"{len(citations)} citations"
        )
        if context_text:
            mode = "deep"
    except Exception as e:
        logger.warning(f"[PaperAgent] PDF retrieval failed: {e}")

    # ── Abstract fallback ─────────────────────────────────────────────────────
    if not context_text:
        mode = "abstract"
        context_text = (
            f"[Paper Abstract]\n{paper_context.get('abstract', '')[:1000]}\n\n"
            f"[Analysis]\n"
            f"Score Reasoning: {paper_context.get('score_reasoning', '')}\n"
            f"Stack Fit: {paper_context.get('stack_fit', '')}\n\n"
            f"Note: Full PDF not indexed. Click 'Index PDF' for section-level precision."
        )

    # ── Build system prompt ───────────────────────────────────────────────────
    system = PAPER_AGENT_SYSTEM.format(
        title        = paper_context.get("title", "Unknown"),
        score        = paper_context.get("overall_score", "N/A"),
        action       = paper_context.get("action", "N/A"),
        intent       = intent.upper(),
        length_guide = _LENGTH_GUIDE.get(intent, ""),
    )

    answer = await _generate(query, context_text, system, history, model_pref)
    answer = _confidence_check(answer, context_text)

    inline        = _extract_inline_citations(answer)
    all_citations = citations + [c for c in inline if c not in citations]

    return {
        "answer":    answer,
        "citations": all_citations,
        "paper_id":  paper_id,
        "n_sources": len(all_citations),
        "mode":      mode,
        "intent":    intent,
        "model":     model_pref,
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_inline_citations(text: str) -> list[dict]:
    citations = []
    for page in re.findall(r'\[\[page:(\d+)\]\]', text):
        citations.append({"type": "page", "value": int(page)})
    for section in re.findall(r'\[\[section:([^\]]+)\]\]', text):
        citations.append({"type": "section", "value": section})
    return citations