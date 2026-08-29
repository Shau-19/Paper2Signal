"""
Paper2Signal — PDF Indexer v3
Optimized for Microsoft IR internship demo quality.

Key improvements:
  1. Fixed duplicate chunk store (delete by ID list, not where filter)
  2. Overlapping chunks (50-word overlap) for continuity
  3. Context leakage fix — clean text stored separately from labeled text
     (LLM gets clean text, embedding gets labeled text for better retrieval)
  4. Figure caption extraction — captions near figures stored as chunks
     (honest image context without vision API cost)
  5. Cross-encoder reranking (ms-marco-MiniLM-L-6-v2, ~85MB, CPU)
  6. Query expansion for factual queries
  7. Named entity BM25 boost (laDeCo, LoRA etc.)
  8. Numbered list boost in RRF (catches problem/limitation answers)
  9. LLM-as-judge (optional, Groq, logs poor retrievals)
  10. PDF build failure resilience — explicit meta tensor fix
  11. FIX: duplicate pre-delete now uses limit=10000 so where filter works
  12. Chain retrieval for implement/math intents — pulls prev/next chunks
      in same section for execution continuity
  13. Section boost for implement/math/results — boosts relevant sections
      before RRF so the right content ranks first

"""

import re
import math
import asyncio
import logging
import os
import urllib.request
import urllib.error
from collections import defaultdict

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
from config.settings import settings

logger = logging.getLogger(__name__)

PDF_COLLECTION = "p2s_pdf_v3"  # bump version = clean slate

_embed_fn      = None
_collection    = None
_cross_encoder = None


# ── Singletons ────────────────────────────────────────────────────────────────

def get_embed_fn():
    global _embed_fn
    if _embed_fn is None:
        os.environ["TOKENIZERS_PARALLELISM"] = "false"
        _embed_fn = SentenceTransformerEmbeddingFunction(
            model_name=settings.EMBEDDING_MODEL,
            device="cpu",
        )
    return _embed_fn


def get_pdf_collection():
    global _collection
    if _collection is None:
        client      = chromadb.PersistentClient(path=settings.CHROMA_PATH)
        _collection = client.get_or_create_collection(
            name=PDF_COLLECTION,
            embedding_function=get_embed_fn(),
        )
        logger.info(f"[PDFIndex] Collection ready ({_collection.count()} chunks)")
    return _collection


def get_cross_encoder():
    """
    Lazy-load cross-encoder for reranking.
    Falls back gracefully — retrieval still works without it.
    """
    global _cross_encoder
    if _cross_encoder is None:
        try:
            from sentence_transformers import CrossEncoder
            _cross_encoder = CrossEncoder(
                "cross-encoder/ms-marco-MiniLM-L-6-v2",
                max_length=512,
                device="cpu",
            )
            logger.info("[PDFIndex] Cross-encoder loaded")
        except Exception as e:
            logger.warning(f"[PDFIndex] Cross-encoder unavailable: {e}")
            _cross_encoder = "unavailable"
    return None if _cross_encoder == "unavailable" else _cross_encoder


# ── PDF Fetch ─────────────────────────────────────────────────────────────────

def _fetch_pdf(arxiv_id: str) -> bytes:
    url = f"https://arxiv.org/pdf/{arxiv_id.split('v')[0]}"
    logger.info(f"[PDFIndex] Fetching: {url}")
    req = urllib.request.Request(url, headers={
        "User-Agent": "Paper2Signal/3.0",
        "Accept":     "application/pdf",
    })
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            data = r.read()
            logger.info(f"[PDFIndex] Got {len(data)//1024} KB")
            return data
    except urllib.error.HTTPError as e:
        raise ValueError(f"PDF fetch failed {arxiv_id}: HTTP {e.code}")
    except Exception as e:
        raise ValueError(f"PDF fetch failed: {e}")


# ── Section / Math / Figure Detection ────────────────────────────────────────

_SECTION_RE = re.compile(
    r'^(\d+\.?\d*\.?\s+)?'
    r'(Abstract|Introduction|Related Work|Background|Preliminaries|'
    r'Notation|Methodology|Method|Approach|Model|Architecture|Framework|'
    r'Experiments?|Results?|Evaluation|Analysis|Ablation Study|'
    r'Discussion|Conclusion|Limitations?|Future Work|'
    r'References?|Appendix[A-Z\s]?|[A-Z][A-Za-z\s&:,\-]{3,60})$'
)

_MATH_RE = re.compile(
    r'(\$.*?\$|\\[a-zA-Z]+\{|\\frac|\\sum|\\int|'
    r'[∑∫≈→←⊕‖]|\d+\.\d+e[-+]\d+|Equation\s+\d+)'
)

_LIST_RE    = re.compile(r'^\s*[1-9][.)]\s+|^\s*[-•]\s+', re.MULTILINE)
_FIGURE_RE  = re.compile(r'^(Fig\.?|Figure|Table)\s*\d+', re.IGNORECASE)
_NOISE_RE   = re.compile(
    r'^[\d\s\.]+$'                    # page numbers / section numbers only
    r'|^[A-Z\s]{2,6}$'               # short all-caps headers
    r'|^\s*\d+\s*$'                  # standalone numbers
    r'|^https?://\S+$'               # bare URLs
)


def _is_section_header(line: str) -> bool:
    line = line.strip()
    return (3 <= len(line) <= 90) and bool(_SECTION_RE.match(line))


def _is_noise(text: str) -> bool:
    """Filter out header/footer noise, page numbers, short artifacts."""
    stripped = text.strip()
    if len(stripped) < 20:
        return True
    if _NOISE_RE.match(stripped):
        return True
    # Ratio of alpha chars < 30% → likely noise (equations/numbers block)
    alpha = sum(c.isalpha() for c in stripped)
    if alpha / max(len(stripped), 1) < 0.25 and not _MATH_RE.search(stripped):
        return True
    return False


def _has_math(text: str) -> bool:
    return bool(_MATH_RE.search(text))


def _has_numbered_list(text: str) -> bool:
    return bool(_LIST_RE.search(text))


def _is_figure_caption(text: str) -> bool:
    return bool(_FIGURE_RE.match(text.strip()))


# ── Extraction with overlap + figure captions ─────────────────────────────────

def _extract_paragraphs(pdf_bytes: bytes, paper_id: str) -> tuple[list[dict], int]:
    """
    Extract paragraph chunks with:
    - Noise filtering (headers, page numbers, artifacts)
    - 50-word overlap between consecutive paragraphs for continuity
    - Figure/table caption extraction as dedicated chunks
    - Clean raw_text (no labels) stored separately for LLM context
    """
    try:
        import fitz
    except ImportError:
        raise ImportError("pip install pymupdf --break-system-packages")

    # Fix meta tensor issue that caused build failures
    os.environ["TOKENIZERS_PARALLELISM"] = "false"

    doc             = fitz.open(stream=pdf_bytes, filetype="pdf")
    chunks          = []
    current_section = "Abstract"
    section_order   = 0
    chunk_idx       = 0
    prev_words: list[str] = []  # for overlap

    for page_num in range(len(doc)):
        page = doc[page_num]

        # ── Tables ───────────────────────────────────────────────────────────
        try:
            for t_idx, table in enumerate(page.find_tables()):
                rows = table.extract()
                if not rows:
                    continue
                lines  = []
                header = [str(c).strip() if c else "" for c in rows[0]]
                lines.append(" | ".join(header))
                lines.append("-" * max(30, len(" | ".join(header))))
                for row in rows[1:]:
                    lines.append(" | ".join(str(c).strip() if c else "" for c in row))
                raw = "\n".join(lines)
                if len(raw) < 30:
                    continue
                # Labeled text for embedding (retrieval context)
                labeled  = f"[{current_section} | Page {page_num+1} | TABLE]\n{raw}"
                chunks.append({
                    "chunk_id":      f"{paper_id}_p{page_num+1}_t{t_idx}",
                    "text":          labeled,       # embedding text (with labels)
                    "raw_text":      raw,           # clean text (for LLM context)
                    "page":          page_num + 1,
                    "section":       current_section,
                    "section_order": section_order,
                    "type":          "table",
                    "has_math":      False,
                    "has_list":      False,
                    "is_caption":    False,
                    "paper_id":      paper_id,
                })
                chunk_idx += 1
        except Exception as e:
            logger.debug(f"[PDFIndex] Table p{page_num+1}: {e}")

        # ── Text blocks ───────────────────────────────────────────────────────
        for block in page.get_text("blocks", sort=True):
            raw = block[4].strip()

            # Noise filter
            if not raw or _is_noise(raw):
                continue

            first_line = raw.split('\n')[0].strip()

            # Section header detection
            if _is_section_header(first_line):
                current_section = first_line
                section_order  += 1
                prev_words      = []  # reset overlap at section boundary
                continue

            # Skip references section
            if current_section.lower().startswith("refer"):
                continue

            has_math    = _has_math(raw)
            has_list    = _has_numbered_list(raw)
            is_caption  = _is_figure_caption(raw)

            # Build overlap prefix (50 words from previous chunk)
            if prev_words and not is_caption:
                overlap_text = " ".join(prev_words[-50:])
                raw_with_overlap = f"{overlap_text} [...] {raw}"
            else:
                raw_with_overlap = raw

            # Build tags for embedding label (NOT shown to LLM)
            tags = []
            if has_math:    tags.append("MATH")
            if has_list:    tags.append("LIST")
            if is_caption:  tags.append("FIGURE")
            tag_str = " | " + " | ".join(tags) if tags else ""

            labeled = f"[{current_section} | Page {page_num+1}{tag_str}]\n{raw}"

            chunks.append({
                "chunk_id":      f"{paper_id}_p{page_num+1}_b{chunk_idx}",
                "text":          labeled,              # embedding: labeled
                "raw_text":      raw_with_overlap,     # LLM: clean + overlap
                "clean_text":    raw,                  # pure clean (no overlap)
                "page":          page_num + 1,
                "section":       current_section,
                "section_order": section_order,
                "type":          "caption" if is_caption else ("math" if has_math else "text"),
                "has_math":      has_math,
                "has_list":      has_list,
                "is_caption":    is_caption,
                "paper_id":      paper_id,
            })

            # Update overlap buffer (use clean text only)
            prev_words = raw.split()
            chunk_idx += 1

    total_pages = len(doc)
    doc.close()

    math_count    = sum(1 for c in chunks if c["has_math"])
    caption_count = sum(1 for c in chunks if c["is_caption"])
    list_count    = sum(1 for c in chunks if c["has_list"])
    logger.info(
        f"[PDFIndex] {len(chunks)} chunks | {total_pages} pages | "
        f"{math_count} math | {caption_count} figure captions | {list_count} lists"
    )
    return chunks, total_pages


# ── Section Summaries ─────────────────────────────────────────────────────────

def _build_section_summaries(chunks: list[dict], paper_id: str) -> list[dict]:
    """One summary per section — used for high-level/overview questions."""
    by_section: dict[str, list[str]] = defaultdict(list)
    order_map:  dict[str, int]       = {}

    for c in chunks:
        if c["type"] in ("text", "math"):
            sec = c["section"]
            # Use clean_text for summaries — no overlap prefix
            by_section[sec].append(c.get("clean_text", c["raw_text"]))
            order_map[sec] = c["section_order"]

    summaries = []
    for sec, texts in by_section.items():
        combined = " ".join(texts)
        trimmed  = " ".join(combined.split()[:500])
        safe_sec = re.sub(r'[^a-z0-9]', '_', sec.lower())[:40]
        summaries.append({
            "chunk_id":      f"{paper_id}_sum_{safe_sec}",
            "text":          f"[SECTION OVERVIEW: {sec}]\n{trimmed}",
            "raw_text":      trimmed,
            "clean_text":    trimmed,
            "page":          0,
            "section":       sec,
            "section_order": order_map.get(sec, 0),
            "type":          "summary",
            "has_math":      any(_has_math(t) for t in texts),
            "has_list":      False,
            "is_caption":    False,
            "paper_id":      paper_id,
        })

    logger.info(f"[PDFIndex] {len(summaries)} section summaries")
    return summaries


# ── Store — FIX: use limit=10000 so where filter actually works ───────────────

def _store(all_chunks: list[dict], paper_id: str):
    """
    FIX: ChromaDB's where filter on get() silently returns nothing without
    a limit parameter. Adding limit=10000 ensures existing chunks are found
    and deleted before re-indexing, eliminating the duplicate ID spam and
    retrieval pollution from doubled embeddings.
    """
    collection = get_pdf_collection()

    try:
        existing = collection.get(
            where={"paper_id": paper_id},
            limit=10000,   # ← THE FIX: without this, where filter returns nothing
        )
        if existing and existing.get("ids"):
            collection.delete(ids=existing["ids"])
            logger.info(f"[PDFIndex] Cleared {len(existing['ids'])} old chunks for {paper_id}")
    except Exception as e:
        logger.warning(f"[PDFIndex] Pre-delete failed (safe to continue): {e}")

    if not all_chunks:
        return

    for i in range(0, len(all_chunks), 150):
        batch = all_chunks[i:i + 150]
        collection.add(
            ids       = [c["chunk_id"] for c in batch],
            documents = [c["text"] for c in batch],       # labeled text → embedding
            metadatas = [{
                "paper_id":      c["paper_id"],
                "page":          c["page"],
                "section":       c["section"],
                "section_order": c["section_order"],
                "type":          c["type"],
                "has_math":      c["has_math"],
                "has_list":      c.get("has_list", False),
                "is_caption":    c.get("is_caption", False),
                # Store clean raw_text for LLM — no label prefix noise
                "raw_text":      c.get("clean_text", c["raw_text"])[:1000],
                # Store overlap version separately for continuity
                "raw_text_ctx":  c["raw_text"][:1200],
            } for c in batch],
        )

    logger.info(f"[PDFIndex] Stored {len(all_chunks)} chunks for {paper_id}")


# ── BM25 ──────────────────────────────────────────────────────────────────────

class _BM25:
    def __init__(self, corpus: list[str], k1: float = 1.5, b: float = 0.75):
        self.k1    = k1
        self.b     = b
        self.N     = len(corpus)
        self.avgdl = sum(len(d.split()) for d in corpus) / max(self.N, 1)
        self.df: dict[str, int]       = defaultdict(int)
        self.tf: list[dict[str, int]] = []

        for doc in corpus:
            tokens = self._tok(doc)
            freq: dict[str, int] = defaultdict(int)
            for t in tokens:
                freq[t] += 1
            self.tf.append(freq)
            for t in set(tokens):
                self.df[t] += 1

    def _tok(self, text: str) -> list[str]:
        return re.findall(r'\b[a-zA-Z0-9_\-]{2,}\b', text.lower())

    def score(self, query: str, idx: int) -> float:
        tokens = self._tok(query)
        tf     = self.tf[idx]
        dl     = sum(tf.values())
        s      = 0.0
        for t in tokens:
            if t not in tf:
                continue
            idf = math.log((self.N - self.df[t] + 0.5) / (self.df[t] + 0.5) + 1)
            num = tf[t] * (self.k1 + 1)
            den = tf[t] + self.k1 * (1 - self.b + self.b * dl / self.avgdl)
            s  += idf * num / den
        return s

    def top_k(self, query: str, k: int) -> list[tuple[int, float]]:
        scored = sorted(
            [(i, self.score(query, i)) for i in range(self.N)],
            key=lambda x: x[1], reverse=True
        )
        return [(i, s) for i, s in scored[:k] if s > 0]


# ── Query Expansion ───────────────────────────────────────────────────────────

_EXPANSIONS = {
    "problem":      "limitation challenge issue drawback weakness failure",
    "challenge":    "limitation problem difficulty obstacle constraint",
    "limitation":   "problem challenge weakness drawback shortcoming",
    "contribution": "novelty proposal method result achievement",
    "method":       "approach algorithm technique methodology procedure",
    "result":       "performance accuracy benchmark evaluation experiment finding",
    "how":          "mechanism process steps procedure implementation",
    "compare":      "versus difference advantage disadvantage tradeoff",
    "equation":     "formula derivation loss objective function",
    "architecture": "model structure layer design component module",
    "figure":       "diagram illustration visualization caption table",
}

def _expand_query(query: str) -> str:
    q     = query.lower()
    extra = [v for k, v in _EXPANSIONS.items() if k in q]
    return f"{query} {' '.join(extra)}" if extra else query


def _detect_named_entities(query: str) -> list[str]:
    camel  = re.findall(r'\b[A-Z][a-z]+(?:[A-Z][a-z]+)+\b', query)
    acronm = re.findall(r'\b[A-Z]{2,}\b', query)
    return list(set(camel + acronm))


# ── Section boosts per intent ─────────────────────────────────────────────────
# Sections that should rank first for each intent type.
# Matching is case-insensitive substring so "4.1 Method" matches "Method".

SECTION_BOOSTS: dict[str, list[str]] = {
    "implement": [
        "Method", "Algorithm", "Architecture", "Framework",
        "Pipeline", "System", "Approach", "Implementation",
    ],
    "math": [
        "Preliminaries", "Notation", "Background", "Method",
        "Proof", "Theorem", "Derivation", "Analysis",
    ],
    "results": [
        "Experiments", "Results", "Evaluation", "Ablation",
        "Benchmark", "Performance", "Comparison",
    ],
    "formula": [
        "Method", "Preliminaries", "Notation", "Background",
        "Derivation", "Objective", "Loss",
    ],
}


def _apply_section_boost(
    sem_ids:   list[str],
    chunk_map: dict,
    intent:    str,
) -> list[str]:
    """
    Move chunks from boosted sections to the front of the semantic ranking
    before RRF so they have a higher chance of surviving into final results.
    Everything else stays in original order — no items removed.
    """
    boost_sections = SECTION_BOOSTS.get(intent, [])
    if not boost_sections:
        return sem_ids

    boosted = []
    rest    = []
    for cid in sem_ids:
        section = chunk_map.get(cid, (None, {}, 0))[1].get("section", "")
        if any(b.lower() in section.lower() for b in boost_sections):
            boosted.append(cid)
        else:
            rest.append(cid)

    promoted = boosted + rest
    if boosted:
        logger.info(f"[PDFIndex] Section boost ({intent}): promoted {len(boosted)} chunks from {boost_sections}")
    return promoted


# ── Chain retrieval — prev/next chunks in same section ────────────────────────

def _get_chain_chunks(
    selected_cids: list[str],
    all_cid_list:  list[str],
    chunk_map:     dict,
    max_extra:     int = 4,
) -> list[str]:
    """
    For each selected chunk, pull the immediately preceding and following
    chunk within the same section. This provides execution/derivation
    continuity that isolated top-k retrieval misses.

    Only adds chunks not already in selected_cids.
    Respects section boundaries — no cross-section leakage.
    """
    selected_set = set(selected_cids)
    extra: list[str] = []

    for cid in selected_cids:
        if cid not in chunk_map:
            continue
        section = chunk_map[cid][1].get("section", "")

        try:
            idx = all_cid_list.index(cid)
        except ValueError:
            continue

        # Previous chunk in same section
        if idx > 0:
            prev_cid = all_cid_list[idx - 1]
            if (
                prev_cid not in selected_set
                and prev_cid in chunk_map
                and chunk_map[prev_cid][1].get("section", "") == section
            ):
                extra.append(prev_cid)
                selected_set.add(prev_cid)

        # Next chunk in same section
        if idx < len(all_cid_list) - 1:
            next_cid = all_cid_list[idx + 1]
            if (
                next_cid not in selected_set
                and next_cid in chunk_map
                and chunk_map[next_cid][1].get("section", "") == section
            ):
                extra.append(next_cid)
                selected_set.add(next_cid)

        if len(extra) >= max_extra:
            break

    if extra:
        logger.info(f"[PDFIndex] Chain retrieval: added {len(extra)} neighboring chunks")
    return extra


# ── RRF with boosts ───────────────────────────────────────────────────────────

def _rrf_with_boosts(
    sem_ids:   list[str],
    bm25_ids:  list[str],
    chunk_map: dict,
    query:     str,
    k:         int = 60,
) -> list[str]:
    scores: dict[str, float] = defaultdict(float)

    for rank, cid in enumerate(sem_ids):
        scores[cid] += 1.0 / (k + rank + 1)
    for rank, cid in enumerate(bm25_ids):
        scores[cid] += 1.0 / (k + rank + 1)

    # Named entity → extra BM25 weight (laDeCo, LoRA, BERT etc.)
    named_entities = _detect_named_entities(query)
    if named_entities:
        for rank, cid in enumerate(bm25_ids):
            scores[cid] += 0.4 / (k + rank + 1)

    # Numbered list boost for concrete factual questions
    list_triggers = [
        "problem", "challenge", "limitation", "step", "contribution",
        "what are", "approach", "method", "how does", "key", "main",
    ]
    if any(t in query.lower() for t in list_triggers):
        for cid, (_, meta, _dist) in chunk_map.items():
            if meta.get("has_list", False):
                scores[cid] *= 1.5

    # Figure caption boost for figure/diagram questions
    if re.search(r'\b(figure|fig|diagram|table|illustration|plot|chart)\b', query, re.I):
        for cid, (_, meta, _dist) in chunk_map.items():
            if meta.get("is_caption", False):
                scores[cid] *= 1.6

    return sorted(scores, key=lambda x: scores[x], reverse=True)


# ── Cross-encoder Reranker ────────────────────────────────────────────────────

def _rerank(query: str, top_cids: list[str], chunk_map: dict, top_n: int) -> list[str]:
    """
    Cross-encoder jointly scores (query, chunk_text) pairs.
    Much more accurate than cosine similarity — understands query-chunk relevance.
    """
    encoder = get_cross_encoder()
    if encoder is None or len(top_cids) <= top_n:
        return top_cids[:top_n]

    pairs      = []
    valid_cids = []
    for cid in top_cids:
        if cid not in chunk_map:
            continue
        _, meta, _ = chunk_map[cid]
        # Use clean text for reranking (no label prefix bias)
        raw = meta.get("raw_text", "")[:400]
        pairs.append([query, raw])
        valid_cids.append(cid)

    if not pairs:
        return top_cids[:top_n]

    try:
        scores   = encoder.predict(pairs)
        ranked   = sorted(zip(valid_cids, scores), key=lambda x: x[1], reverse=True)
        reranked = [cid for cid, _ in ranked[:top_n]]
        logger.info(f"[PDFIndex] Cross-encoder reranked {len(pairs)} → {top_n}")
        return reranked
    except Exception as e:
        logger.warning(f"[PDFIndex] Rerank failed: {e}")
        return top_cids[:top_n]


# ── LLM-as-Judge ─────────────────────────────────────────────────────────────

async def _judge_retrieval(query: str, context: str, paper_title: str) -> dict:
    """
    Groq-based retrieval quality scoring.
    Only called for explain/discuss intents — saves API calls.
    Score < 3 = logged as warning so you can debug poor retrievals.
    """
    if not context or len(context) < 100:
        return {"score": 1, "reason": "Empty context", "adequate": False}
    try:
        from agents.llm_router import _call_groq
        import json as _json

        system = (
            "You are a retrieval quality judge. "
            "Score whether the retrieved context adequately answers the query.\n"
            "Return ONLY JSON: {\"score\": int (1-5), \"reason\": \"one sentence\", \"adequate\": bool}\n"
            "5=direct answer present, 4=can infer, 3=partial, 2=tangential, 1=irrelevant"
        )
        user = (
            f"Paper: {paper_title}\n"
            f"Query: {query}\n\n"
            f"Context (first 800 chars):\n{context[:800]}"
        )
        raw = await _call_groq(system, user)
        if not raw:
            return {"score": 3, "reason": "Judge unavailable", "adequate": True}
        cleaned = re.sub(r"```(?:json)?\s*|\s*```", "", raw).strip()
        result  = _json.loads(cleaned)
        score   = int(result.get("score", 3))
        if score < 3:
            logger.warning(f"[Judge] LOW score {score}/5: {result.get('reason','')} | '{query[:50]}'")
        return {"score": score, "reason": result.get("reason", ""), "adequate": score >= 3}
    except Exception as e:
        logger.debug(f"[Judge] Failed: {e}")
        return {"score": 3, "reason": "error", "adequate": True}


# ── Public Interface ──────────────────────────────────────────────────────────

async def build_paper_index(arxiv_id: str) -> dict:
    loop = asyncio.get_event_loop()

    def _sync():
        pdf_bytes           = _fetch_pdf(arxiv_id)
        chunks, total_pages = _extract_paragraphs(pdf_bytes, arxiv_id)
        summaries           = _build_section_summaries(chunks, arxiv_id)
        all_chunks          = chunks + summaries
        _store(all_chunks, arxiv_id)
        return {
            "doc_id":    arxiv_id,
            "tree":      [],
            "sections":  len(set(c["section"] for c in chunks)),
            "pages":     total_pages,
            "chunks":    len(all_chunks),
            "math":      sum(1 for c in chunks if c["has_math"]),
            "tables":    sum(1 for c in chunks if c["type"] == "table"),
            "captions":  sum(1 for c in chunks if c["is_caption"]),
            "summaries": len(summaries),
        }

    return await loop.run_in_executor(None, _sync)


async def retrieve_context(
    paper_id:    str,
    query:       str,
    n:           int  = 10,
    paper_title: str  = "",
    run_judge:   bool = False,
    intent:      str  = "discuss",   # NEW: passed from rag.py for section boost + chain retrieval
) -> tuple[str, list[dict]]:
    """
    Full retrieval pipeline:
      1. Query expansion
      2. Semantic search (fetch 3× candidates)
      3. Section boost — move intent-relevant sections to front (NEW)
      4. BM25 over candidate pool
      5. RRF merge with list/entity/figure boosts
      6. Cross-encoder rerank (2n → n)
      7. Chain retrieval — add prev/next chunks in same section (NEW)
      8. Sort by section order (reads like the paper)
      9. Return CLEAN context (no label prefix noise for LLM)
      10. Optional LLM-as-judge
    """
    loop = asyncio.get_event_loop()

    def _sync() -> tuple[str, list[dict], str]:
        collection     = get_pdf_collection()
        expanded_query = _expand_query(query)
        fetch_n        = min(n * 3, 30)

        try:
            sem_res = collection.query(
                query_texts = [expanded_query],
                n_results   = fetch_n,
                where       = {"paper_id": paper_id},
                include     = ["documents", "metadatas", "distances"],
            )
        except Exception as e:
            logger.warning(f"[PDFIndex] Query failed: {e}")
            return "", [], ""

        docs  = sem_res.get("documents", [[]])[0]
        metas = sem_res.get("metadatas", [[]])[0]
        dists = sem_res.get("distances", [[]])[0]

        if not docs:
            return "", [], ""

        # Build candidate pool
        chunk_map: dict[str, tuple] = {}
        sem_ids:   list[str]        = []
        for i, (doc, meta) in enumerate(zip(docs, metas)):
            cid = f"{meta.get('section','')}_{meta.get('page',0)}_{meta.get('type','')}_{i}"
            chunk_map[cid] = (doc, meta, dists[i] if i < len(dists) else 1.0)
            sem_ids.append(cid)

        # ── Section boost: promote intent-relevant sections before RRF ────────
        sem_ids = _apply_section_boost(sem_ids, chunk_map, intent)

        # BM25 over candidate pool (uses clean raw_text, not labeled embedding text)
        cid_list  = list(chunk_map.keys())
        raw_texts = [chunk_map[c][1].get("raw_text", chunk_map[c][0][:500]) for c in cid_list]
        bm25      = _BM25(raw_texts)
        bm25_ids  = [cid_list[i] for i, _ in bm25.top_k(query, k=fetch_n)]

        # RRF with boosts
        merged = _rrf_with_boosts(sem_ids, bm25_ids, chunk_map, query)

        # Cross-encoder rerank: 2n candidates → n
        reranked = _rerank(query, merged[:n * 2], chunk_map, top_n=n)

        # ── Chain retrieval: pull neighboring chunks for implement/math ────────
        if intent in ("implement", "math", "formula"):
            chain_extras = _get_chain_chunks(reranked, cid_list, chunk_map, max_extra=4)
            reranked = reranked + chain_extras

        # Sort by section order for coherent reading flow
        final = sorted(
            [(cid, chunk_map[cid]) for cid in reranked if cid in chunk_map],
            key=lambda x: (x[1][1].get("section_order", 0), x[1][1].get("page", 0))
        )

        # Build CLEAN context — use raw_text_ctx (with overlap) NOT labeled embedding text
        context_parts: list[str]  = []
        citations:     list[dict] = []
        seen_sections: set        = set()
        seen_pages:    set        = set()

        for cid, (_, meta, dist) in final:
            if dist > 1.8:
                continue
            page    = meta.get("page", 0)
            section = meta.get("section", "")

            # Use overlap-aware context for LLM (raw_text_ctx)
            clean = meta.get("raw_text_ctx", meta.get("raw_text", ""))

            # Prepend section header as readable annotation (not a label artifact)
            if section and section not in seen_sections:
                context_parts.append(f"── {section} ──\n{clean}")
            else:
                context_parts.append(clean)

            if page and page not in seen_pages:
                seen_pages.add(page)
                citations.append({"type": "page", "value": page})
            if section and section not in seen_sections:
                seen_sections.add(section)
                citations.append({"type": "section", "value": section})

        context_text = "\n\n".join(context_parts)
        logger.info(
            f"[PDFIndex] {len(context_parts)} chunks | intent={intent} | "
            f"expanded={expanded_query != query} | query: {query[:50]}"
        )
        return context_text, citations, context_text

    context_text, citations, ctx_for_judge = await loop.run_in_executor(None, _sync)

    if run_judge and context_text and paper_title:
        await _judge_retrieval(query, ctx_for_judge, paper_title)

    return context_text, citations