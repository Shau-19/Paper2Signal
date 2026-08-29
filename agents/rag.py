"""
Paper2Signal — RAG Engine v4

Two modes:
  1. global_chat()      — Hybrid research navigator
  2. deep_paper_chat()  — Paper-specific agent with PDF retrieval

Changes in this version:
  - detect_intent(): weighted scoring replaces first-match-wins regex
    (fixes "implement a retrieval-memory module" routing to discuss)
  - Intent logging added for debugging routing decisions
  - _decompose_query(): stronger implement decomposition
    (appendix, pseudocode, training details, architecture)
  - PAPER_AGENT_SYSTEM: faithful architecture prompt for implement intent
  - _LENGTH_GUIDE: tight per-intent caps
  - _confidence_check: threshold raised to 0.20
  - retrieve_context receives intent= for section boost + chain retrieval
"""

import logging
import re
import asyncio
from typing import Optional
from collections import defaultdict

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

from config.settings import settings
from agents.llm_router import llm_call, ModelType

logger = logging.getLogger(__name__)


# ── ChromaDB singleton ────────────────────────────────────────────────────────

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


# ── Global intent detection ───────────────────────────────────────────────────

_LATEST_PATTERNS = [
    r"\b(latest|recent|new|newest|this week|today|2024|2025|2026)\b",
    r"\bwhat('s| is) new\b",
    r"\bjust (released|published|came out)\b",
    r"\bcutting.?edge\b",
    r"\bstate.?of.?the.?art\b",
]
_LEARNING_PATTERNS = [
    r"\b(learn|understand|study|intro|introduction|beginner|start|get started)\b",
    r"\bhow (do i|to) (learn|understand|get started)\b",
    r"\bbest papers (to|for) (learn|understand|read)\b",
    r"\bprimer\b", r"\btutorial\b", r"\bfoundation\b",
]
_PRACTICAL_PATTERNS = [
    r"\b(production|deploy|implement|integrate|use in|build|ship)\b",
    r"\b(practical|real.?world|industry|applied)\b",
    r"\bstack (fit|compatible|works with)\b",
    r"\b(pytorch|huggingface|fastapi|triton|vllm)\b",
]
_COMPARE_PATTERNS = [
    r"\bvs\.?\b", r"\bversus\b", r"\bdifference between\b",
    r"\bcompare\b", r"\bbetter than\b", r"\btradeoff\b",
    r"\badvantage|disadvantage\b",
]
_RECOMMEND_PATTERNS = [
    r"\b(recommend|suggest|best|top|should i read|worth reading)\b",
    r"\bwhat (papers?|are) (good|best|worth)\b",
    r"\bgive me (papers?|recommendations?)\b",
]


def detect_global_intent(query: str) -> str:
    q = query.lower()
    for p in _LATEST_PATTERNS:
        if re.search(p, q, re.IGNORECASE): return "latest"
    for p in _LEARNING_PATTERNS:
        if re.search(p, q, re.IGNORECASE): return "learning"
    for p in _PRACTICAL_PATTERNS:
        if re.search(p, q, re.IGNORECASE): return "practical"
    for p in _COMPARE_PATTERNS:
        if re.search(p, q, re.IGNORECASE): return "compare"
    for p in _RECOMMEND_PATTERNS:
        if re.search(p, q, re.IGNORECASE): return "recommend"
    return "factual"


# ── Dense retrieval ───────────────────────────────────────────────────────────

def _dense_retrieve(query: str, n: int = 8, paper_id: Optional[str] = None) -> list[dict]:
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
        logger.warning(f"[RAG] Dense query failed: {e}")
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
            "overall_score":   float(meta.get("overall_score") or 0),
            "action":          meta.get("action", ""),
            "arxiv_url":       meta.get("arxiv_url", "") or f"https://arxiv.org/abs/{pid}",
            "velocity_score":  float(meta.get("velocity_score") or 0),
            "distance":        dist,
            "source":          "dense",
        })
    return papers


# ── BM25 retrieval ────────────────────────────────────────────────────────────

def _bm25_retrieve(query: str, n: int = 8) -> list[dict]:
    try:
        collection = get_collection()
        total      = collection.count()
        if total == 0:
            return []

        fetch_n = min(total, 500)
        result  = collection.get(include=["metadatas", "documents"], limit=fetch_n)

        ids    = result.get("ids", [])
        metas  = result.get("metadatas", [])
        docs   = result.get("documents", [])

        query_terms = set(re.findall(r'\b\w{3,}\b', query.lower()))
        stopwords   = {"the","a","an","and","or","but","in","on","at","to","for","of","with","by","from","is","are","was"}
        query_terms -= stopwords

        if not query_terms:
            return []

        scored = []
        for i, pid in enumerate(ids):
            doc  = (docs[i] if i < len(docs) else "").lower()
            meta = metas[i] if i < len(metas) else {}

            title       = meta.get("title", "").lower()
            title_terms = set(re.findall(r'\b\w{3,}\b', title)) - stopwords
            doc_terms   = set(re.findall(r'\b\w{3,}\b', doc))   - stopwords

            title_overlap = len(query_terms & title_terms)
            doc_overlap   = len(query_terms & doc_terms)
            bm25_score    = (title_overlap * 3 + doc_overlap) / max(len(query_terms), 1)

            if bm25_score > 0:
                scored.append({
                    "id":             pid,
                    "title":          meta.get("title", "Unknown"),
                    "abstract":       docs[i] if i < len(docs) else "",
                    "summary":        meta.get("summary", ""),
                    "stack_fit":      meta.get("stack_fit", ""),
                    "score_reasoning":meta.get("score_reasoning", ""),
                    "overall_score":  float(meta.get("overall_score") or 0),
                    "action":         meta.get("action", ""),
                    "arxiv_url":      meta.get("arxiv_url", "") or f"https://arxiv.org/abs/{pid}",
                    "velocity_score": float(meta.get("velocity_score") or 0),
                    "bm25_score":     bm25_score,
                    "distance":       1.0 - min(bm25_score / 5.0, 1.0),
                    "source":         "bm25",
                })

        scored.sort(key=lambda x: x["bm25_score"], reverse=True)
        return scored[:n]

    except Exception as e:
        logger.warning(f"[RAG] BM25 failed: {e}")
        return []


# ── Live ArXiv retrieval ──────────────────────────────────────────────────────

async def _arxiv_live_retrieve(query: str, n: int = 5) -> list[dict]:
    try:
        import arxiv as arxiv_lib

        def _sync_search():
            client = arxiv_lib.Client(page_size=n, delay_seconds=3.0, num_retries=2)
            search = arxiv_lib.Search(
                query=query, max_results=n,
                sort_by=arxiv_lib.SortCriterion.SubmittedDate,
                sort_order=arxiv_lib.SortOrder.Descending,
            )
            return list(client.results(search))

        results = await asyncio.to_thread(_sync_search)
        papers  = []
        for r in results:
            arxiv_id = r.entry_id.split("/")[-1].split("v")[0]
            papers.append({
                "id": arxiv_id, "title": r.title.strip().replace("\n", " "),
                "abstract": r.summary.strip().replace("\n", " ")[:500],
                "summary": "", "stack_fit": "", "score_reasoning": "",
                "overall_score": None, "action": "unanalyzed",
                "arxiv_url": r.entry_id or f"https://arxiv.org/abs/{arxiv_id}",
                "velocity_score": 0.0, "distance": 0.5, "source": "arxiv_live",
                "published_at": r.published.isoformat() if r.published else "",
            })
        logger.info(f"[RAG] ArXiv live: {len(papers)} results for '{query[:40]}'")
        return papers
    except Exception as e:
        logger.warning(f"[RAG] ArXiv live search failed: {e}")
        return []


# ── Multi-source aggregation ──────────────────────────────────────────────────

def _aggregate_and_dedup(dense, bm25, arxiv) -> list[dict]:
    seen: dict[str, dict] = {}

    def _add(papers, weight):
        for p in papers:
            pid = p["id"]
            if pid not in seen:
                seen[pid] = {**p, "_sources": [p["source"]], "_raw_distance": p["distance"]}
            else:
                seen[pid]["_raw_distance"] = min(seen[pid]["_raw_distance"], p["distance"])
                if p["source"] not in seen[pid]["_sources"]:
                    seen[pid]["_sources"].append(p["source"])
                if p.get("summary") and not seen[pid].get("summary"):
                    seen[pid].update({"summary": p["summary"], "stack_fit": p.get("stack_fit",""), "action": p.get("action",""), "overall_score": p.get("overall_score")})

    _add(dense, 1.0); _add(bm25, 0.8); _add(arxiv, 0.6)
    return list(seen.values())


# ── Paper-level reranker ──────────────────────────────────────────────────────

def _rerank_papers(papers: list[dict], intent: str, n: int = 6) -> list[dict]:
    def _score(p):
        sim  = 1.0 - p.get("_raw_distance", 0.5)
        prod = (p.get("overall_score") or 0) / 10.0
        vel  = min((p.get("velocity_score") or 0) / 100.0, 1.0)
        ms   = 0.2 if len(p.get("_sources", [])) > 1 else 0.0
        has_sum = 0.1 if p.get("summary") else 0.0
        adopt   = 0.15 if "adopt" in (p.get("action") or "").lower() else 0.0
        unana   = -0.1 if p.get("action") == "unanalyzed" else 0.0
        if intent == "practical":  return sim*0.3 + prod*0.4 + adopt*0.2 + ms*0.1
        if intent == "latest":     return sim*0.4 + (0.3 if p.get("source")=="arxiv_live" else 0) + ms*0.1 + vel*0.2
        if intent == "learning":   return sim*0.4 + prod*0.25 + has_sum*0.2 + adopt*0.15
        if intent == "compare":    return sim*0.5 + prod*0.2 + ms*0.2 + vel*0.1
        if intent == "recommend":  return sim*0.35 + prod*0.3 + vel*0.15 + ms*0.2
        return sim*0.5 + prod*0.3 + ms*0.2 + unana

    for p in papers:
        p["_rerank_score"] = _score(p)
    papers.sort(key=lambda x: x["_rerank_score"], reverse=True)
    return papers[:n]


# ── Context builders ──────────────────────────────────────────────────────────

def _build_global_context(papers: list[dict], intent: str) -> str:
    if not papers:
        return "No relevant papers found in the database or ArXiv."
    parts = []
    for i, p in enumerate(papers, 1):
        score  = f"{p['overall_score']:.1f}/10" if p.get("overall_score") else "not yet analyzed"
        url    = p.get("arxiv_url") or f"https://arxiv.org/abs/{p['id']}"
        source = ", ".join(p.get("_sources", ["unknown"]))
        part   = (f"[Paper {i}] {p['title']}\nArXiv: {url}\nScore: {score} | Action: {p.get('action','')} | Source: {source}\nAbstract: {p['abstract'][:300]}\n")
        if p.get("summary"):               part += f"Summary: {p['summary'][:200]}\n"
        if p.get("stack_fit") and intent == "practical": part += f"Stack Fit: {p['stack_fit']}\n"
        if p.get("score_reasoning") and intent in ("recommend","practical"): part += f"Reasoning: {p['score_reasoning'][:150]}\n"
        parts.append(part)
    has_live = any(p.get("source") == "arxiv_live" for p in papers)
    header   = f"[Retrieved {len(papers)} papers | Intent: {intent.upper()}{' | Includes live ArXiv results' if has_live else ''}]\n\n"
    return header + "\n---\n".join(parts)


def _build_citations(papers: list[dict]) -> list[dict]:
    return [{"id": p["id"], "title": p["title"], "score": p.get("overall_score"), "action": p.get("action"), "url": p.get("arxiv_url") or f"https://arxiv.org/abs/{p['id']}", "source": p.get("source","local"), "distance": round(p.get("_raw_distance",1.0),3)} for p in papers]


# ── Deep chat intent detection — WEIGHTED SCORING ─────────────────────────────
# Each pattern contributes a score. Highest score wins.
# Weights:  3 = strong unambiguous signal
#           2 = moderate signal
#           1 = weak signal (avoid for explain — it fires on almost anything)
# This replaces the previous first-match-wins approach which caused
# "implement a retrieval-memory module" to route to "discuss".

_FORMULA_P   = [r"\b(formula|equation|notation|loss function|objective)\b", r"\bwhat('s| is) the (formula|equation|math|loss)\b"]
_MATH_P      = [r"\b(proof|derivation|theorem|lemma|derive)\b", r"\bmath(ematical)?\b"]
_IMPLEMENT_P = [r"\b(implement|code|build|write|create|reproduce|script)\b", r"\bhow (do i|to|can i) (use|integrate|run|apply|set up)\b", r"\bshow.{0,20}(code|implementation)\b"]
_RESULTS_P   = [r"\b(results?|findings?|performance|benchmark|accuracy|evaluation|scores?)\b"]
_COMPARE_P   = [r"\bvs\.?\b", r"\bversus\b", r"\bdifference between\b", r"\bcompare\b"]
_EXPLAIN_P   = [r"\bwhat is\b", r"\bhow does\b", r"\bexplain\b", r"\bwhy does\b", r"\bintuition\b", r"\bsummar(ize|y)\b"]
_SHORT_P     = [r"\bwho (wrote|authored|created)\b", r"\bwhen was\b", r"\bhow many\b"]


def detect_intent(query: str) -> str:
    """
    Weighted scoring across all intent categories.
    Every matching pattern adds to that intent's score.
    The intent with the highest total score wins.
    Falls back to 'discuss' if no patterns match.
    """
    q = query.lower()

    scores = {
        "formula":   0,
        "math":      0,
        "implement": 0,
        "results":   0,
        "compare":   0,
        "explain":   0,
        "short":     0,
        "discuss":   0,
    }

    for p in _FORMULA_P:
        if re.search(p, q, re.IGNORECASE): scores["formula"]   += 3
    for p in _MATH_P:
        if re.search(p, q, re.IGNORECASE): scores["math"]      += 3
    for p in _IMPLEMENT_P:
        if re.search(p, q, re.IGNORECASE): scores["implement"] += 3
    for p in _RESULTS_P:
        if re.search(p, q, re.IGNORECASE): scores["results"]   += 2
    for p in _COMPARE_P:
        if re.search(p, q, re.IGNORECASE): scores["compare"]   += 2
    for p in _EXPLAIN_P:
        if re.search(p, q, re.IGNORECASE): scores["explain"]   += 1  # weak — fires on almost any query
    for p in _SHORT_P:
        if re.search(p, q, re.IGNORECASE): scores["short"]     += 3

    best   = max(scores, key=lambda k: scores[k])
    intent = best if scores[best] > 0 else "discuss"

    logger.info(f"[Intent] '{q[:70]}' → {intent} | scores={scores}")
    return intent


# ── Length guides ─────────────────────────────────────────────────────────────

_LENGTH_GUIDE = {
    "formula":   "Lead with the LaTeX formula in a math block. Explain each variable in 1 sentence. No preamble. Total: formula + max 5 variable explanations.",
    "math":      "Show derivation step by step with paper notation. Be precise. Do not add general background unless asked. Max 400 words.",
    "implement": "Write complete, runnable code with imports and inline comments. Prose explanation under 100 words. Prefer code over prose.",
    "results":   "Report exact numbers and metrics from the paper. Bullet list. No background. Max 150 words.",
    "compare":   "Side-by-side comparison, one paragraph per dimension. One-sentence verdict at the end. Max 250 words.",
    "explain":   "Thorough explanation using the paper's own framing and terminology. Max 300 words. Do not pad with general background.",
    "short":     "Answer in 1–2 sentences only. No preamble. No elaboration unless asked.",
    "discuss":   "Conversational but focused. 2–3 paragraphs max. Stay grounded in what the paper says.",
}


# ── Query decomposition ───────────────────────────────────────────────────────

def _decompose_query(query: str, intent: str) -> list[str]:
    """
    Break complex queries into sub-queries for multi-pass retrieval.
    Implement intent gets the most aggressive decomposition because
    implementation details are scattered across Methods, Appendix, and
    training sections — a single query rarely surfaces all of them.
    """
    queries = [query]

    if intent == "implement":
        q_lower = query.lower()
        # Core architecture components — always add for implement
        queries.append(query + " architecture components layers modules")
        queries.append(query + " forward pass training objective loss function")
        queries.append(query + " implementation details pseudocode algorithm steps")
        queries.append(query + " appendix hyperparameters configuration training")

        # Domain-specific expansions
        if any(w in q_lower for w in ["diffusion", "unet", "denoising", "score"]):
            queries.append(query + " noise schedule time embedding sinusoidal")
        if any(w in q_lower for w in ["attention", "transformer", "cross-attention"]):
            queries.append(query + " attention mechanism query key value projection")
        if any(w in q_lower for w in ["encode", "decode", "latent", "vae", "variational"]):
            queries.append(query + " encoder decoder latent space reparameterization")
        if any(w in q_lower for w in ["retriev", "rag", "index", "embed"]):
            queries.append(query + " retrieval index embedding similarity search")
        if any(w in q_lower for w in ["graph", "node", "edge", "gnn"]):
            queries.append(query + " graph construction node features adjacency")
        if any(w in q_lower for w in ["train", "fine-tun", "lora", "finetun"]):
            queries.append(query + " training loop optimizer learning rate schedule")

    elif intent in ("explain", "discuss") and any(
        w in query.lower() for w in ["architecture", "framework", "system", "pipeline", "design"]
    ):
        queries.append(query + " workflow components execution flow")
        queries.append(query + " system design overview")

    elif intent == "math":
        queries.append(query + " derivation proof notation formulation")
        queries.append(query + " objective function loss optimization")

    elif intent == "formula":
        queries.append(query + " equation definition notation variables")

    # Deduplicate while preserving order
    seen, deduped = set(), []
    for q in queries:
        if q not in seen:
            seen.add(q)
            deduped.append(q)

    logger.info(f"[Decompose] intent={intent} → {len(deduped)} sub-queries")
    return deduped


# ── Generate ──────────────────────────────────────────────────────────────────

async def _generate(
    query:      str,
    context:    str,
    system:     str,
    history:    list[dict],
    model_pref: str = "auto",
    intent:     str = "discuss",
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

    # auto: OpenAI for math/implement/formula (better code + LaTeX), Groq for rest
    if intent in ("math", "implement", "formula"):
        return await llm_call(system=system, user=user_prompt, model_type=ModelType.OPENAI)
    return await llm_call(system=system, user=user_prompt, model_type=ModelType.FAST)


# ── Confidence check ──────────────────────────────────────────────────────────

def _confidence_check(answer: str, context: str) -> str:
    if not context:
        return answer
    STOPWORDS = {"the","a","an","and","or","but","in","on","at","to","for","of","with","by","from","is","are","was","were","this","that","we","our","it","its","be","as","if","so","do","not","have","has","can","will"}
    def _kw(text):
        return {w.lower() for w in re.findall(r'\b[a-zA-Z]{5,}\b', text) if w.lower() not in STOPWORDS}
    answer_kw  = _kw(answer)
    context_kw = _kw(context)
    if not answer_kw:
        return answer
    overlap = len(answer_kw & context_kw) / len(answer_kw)
    if overlap < 0.20:
        return answer + "\n\n*Note: parts of this answer extend beyond the retrieved sections — verify against the paper.*"
    return answer


# ── System Prompts ────────────────────────────────────────────────────────────

GLOBAL_SYSTEM = """You are Paper2Signal — an AI research navigator for ML engineers.

Your role: CURATE, SYNTHESIZE, GUIDE — not just retrieve chunks.

Query intent: {intent}

LEARNING  → Curated reading roadmap. Explain WHY each paper matters and in what order.
PRACTICAL → High-scored, adopt-ready papers. Mention stack fit and implementation details.
COMPARE   → Side-by-side synthesis. State tradeoffs clearly. Give a final recommendation.
LATEST    → Summarize what's new. Note papers not yet analyzed.
RECOMMEND → Curated shortlist with clear reasoning. Score and action label for each.
FACTUAL   → Direct answer with paper citations. Be concise.

Rules:
- Always include ArXiv URL for every paper mentioned
- Always state production score and action label when available
- For unanalyzed papers, note they haven't been scored — suggest using Analyze
- Do NOT just list papers — synthesize, compare, give your verdict
- Keep response focused: 3–6 papers max"""


PAPER_AGENT_SYSTEM = """You are a world-class ML researcher and engineer who has read this paper in full.

Paper: {title}
Production Score: {score}/10 | Action: {action}

The context below contains exact text extracted from the paper.
Answer as an expert who knows this work inside and out.

Query intent: {intent}
Response length guidance: {length_guide}

IMPLEMENT intent — CRITICAL rules (apply ONLY when intent is IMPLEMENT):
- Reconstruct the FULL architecture described in the paper — not a toy demo, not a minimal example
- If the paper uses Conv2d, attention layers, skip connections — implement those exactly
- If the paper describes a noise schedule, time embeddings, or cross-attention conditioning — implement them
- Do NOT substitute nn.Linear for convolutions when the paper uses spatial operations
- Do NOT omit core components (encoder, decoder, backbone, conditioning mechanism, loss)
- Before writing code, list the components you found in the context, then implement each as a separate class
- Use the paper's own variable names and mathematical notation in comments
- Write the loss/objective formula in a comment above its implementation
- Default target: faithful architecture prototype
  → More than a toy example
  → Less than full production code
  → Every paper-described component present and connected
- Structure: one class per paper component, then a top-level model class connecting them
- If the paper's appendix or implementation details describe hyperparameters, include them as defaults

MATH/FORMULA intent — rules:
- Lead with the exact formula in LaTeX ($$...$$)
- Use the paper's own variable names
- Explain each variable in one sentence
- Show derivation steps if asked, using paper notation

ALL intents — rules:
- Never say "based on chunks" or "retrieved text shows" — say "the paper" or "Section X"
- Citation format: [[page:N]] or [[section:Name]]
- If something is genuinely not in the retrieved context, say so once briefly
- Match response length strictly to the length guidance — do not pad
- No hallucination: stay within what the context supports"""


# ── Public Interface ──────────────────────────────────────────────────────────

async def global_chat(
    query:      str,
    history:    Optional[list[dict]] = None,
    n_papers:   int = 5,
    model_pref: str = "auto",
) -> dict:
    if is_off_topic(query):
        return {"answer": "I can only answer questions about AI research papers.", "citations": [], "n_sources": 0, "mode": "blocked"}

    intent = detect_global_intent(query)
    logger.info(f"[GlobalChat] intent={intent} query='{query[:50]}'")

    dense_results = _dense_retrieve(query, n=n_papers + 3)
    bm25_results  = _bm25_retrieve(query, n=n_papers)

    arxiv_results = []
    local_confidence = len([p for p in dense_results if p.get("distance", 1.0) < 0.5])
    if intent == "latest" or local_confidence < 2:
        arxiv_results = await _arxiv_live_retrieve(query, n=5)

    all_papers = _aggregate_and_dedup(dense_results, bm25_results, arxiv_results)
    reranked   = _rerank_papers(all_papers, intent=intent, n=n_papers + 1)
    context    = _build_global_context(reranked, intent)
    system     = GLOBAL_SYSTEM.format(intent=intent.upper())
    answer     = await _generate(query, context, system, history or [], model_pref, intent)

    mode = "hybrid"
    if arxiv_results and not dense_results: mode = "arxiv_live"
    elif not arxiv_results:                 mode = "local_db"

    return {
        "answer": answer, "citations": _build_citations(reranked),
        "n_sources": len(reranked), "mode": mode, "intent": intent, "model": model_pref,
        "sources": {"dense": len(dense_results), "bm25": len(bm25_results), "arxiv": len(arxiv_results)},
    }


async def deep_paper_chat(
    query:         str,
    paper_id:      str,
    paper_context: dict,
    history:       Optional[list[dict]] = None,
    model_pref:    str = "auto",
    doc_id:        Optional[str] = None,
) -> dict:
    history = history or []

    if is_off_topic(query):
        return {"answer": "I can only answer questions about this paper.", "citations": [], "paper_id": paper_id, "n_sources": 0, "mode": "blocked"}

    intent   = detect_intent(query)
    n_chunks = {
        "formula":   6,
        "short":     5,
        "results":   10,
        "compare":   12,
        "explain":   12,
        "discuss":   10,
        "math":      15,
        "implement": 20,   # largest window — implementation details are scattered
    }.get(intent, 10)

    logger.info(f"[PaperAgent] intent={intent} model={model_pref} paper={paper_id} chunks={n_chunks}")

    # ── Multi-query retrieval ─────────────────────────────────────────────────
    subqueries   = _decompose_query(query, intent)
    context_text = ""
    citations    = []
    mode         = "abstract"

    try:
        from ml.pdf_indexer import retrieve_context

        if len(subqueries) == 1:
            context_text, citations = await retrieve_context(
                paper_id=paper_id, query=query, n=n_chunks,
                paper_title=paper_context.get("title", ""),
                run_judge=intent in ("explain", "discuss"),
                intent=intent,
            )
        else:
            # Multi-query — merge unique contexts from all sub-queries
            chunks_per_query = max(n_chunks // len(subqueries) + 2, 5)
            seen_ctx, merged_parts, merged_cits = set(), [], []

            for sq in subqueries:
                ctx, cits = await retrieve_context(
                    paper_id=paper_id, query=sq, n=chunks_per_query,
                    paper_title=paper_context.get("title", ""),
                    run_judge=False,
                    intent=intent,
                )
                if ctx and ctx not in seen_ctx:
                    seen_ctx.add(ctx)
                    merged_parts.append(ctx)
                for c in cits:
                    if c not in merged_cits:
                        merged_cits.append(c)

            context_text = "\n\n".join(merged_parts)
            citations    = merged_cits
            logger.info(f"[PaperAgent] Multi-query: {len(subqueries)} queries merged into {len(merged_parts)} unique contexts")

        if context_text:
            mode = "deep"

    except Exception as e:
        logger.warning(f"[PaperAgent] PDF retrieval failed: {e}")

    # ── Abstract fallback ─────────────────────────────────────────────────────
    if not context_text:
        mode = "abstract"
        context_text = (
            f"[Paper Abstract]\n{paper_context.get('abstract', '')[:1000]}\n\n"
            f"[Analysis]\nScore Reasoning: {paper_context.get('score_reasoning', '')}\n"
            f"Stack Fit: {paper_context.get('stack_fit', '')}\n\n"
            f"Note: Full PDF not indexed. Click 'Index PDF' for section-level precision."
        )

    # ── Generate ──────────────────────────────────────────────────────────────
    system = PAPER_AGENT_SYSTEM.format(
        title        = paper_context.get("title", "Unknown"),
        score        = paper_context.get("overall_score", "N/A"),
        action       = paper_context.get("action", "N/A"),
        intent       = intent.upper(),
        length_guide = _LENGTH_GUIDE.get(intent, ""),
    )

    answer        = await _generate(query, context_text, system, history, model_pref, intent)
    answer        = _confidence_check(answer, context_text)
    inline        = _extract_inline_citations(answer)
    all_citations = citations + [c for c in inline if c not in citations]

    return {
        "answer": answer, "citations": all_citations, "paper_id": paper_id,
        "n_sources": len(all_citations), "mode": mode, "intent": intent, "model": model_pref,
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_inline_citations(text: str) -> list[dict]:
    citations = []
    for page in re.findall(r'\[\[page:(\d+)\]\]', text):
        citations.append({"type": "page", "value": int(page)})
    for section in re.findall(r'\[\[section:([^\]]+)\]\]', text):
        citations.append({"type": "section", "value": section})
    return citations


# ── Legacy compatibility ──────────────────────────────────────────────────────

def retrieve(query: str, n: int = 5, paper_id: Optional[str] = None) -> list[dict]:
    return _dense_retrieve(query, n=n, paper_id=paper_id)

def build_context(papers: list[dict]) -> str:
    return _build_global_context(papers, intent="factual")

def build_citations(papers: list[dict]) -> list[dict]:
    return _build_citations(papers)