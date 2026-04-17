"""
PaperSignal — Embedding Pipeline
Loads un-embedded papers from DB, encodes title+abstract,
upserts into ChromaDB. Batch size and model from settings.
"""

import logging
from typing import List

import chromadb
from sentence_transformers import SentenceTransformer
from sqlalchemy import select

from ingestion.models import Paper, get_db
from config.settings import settings

logger = logging.getLogger(__name__)

# ── Singletons (lazy-loaded) ──────────────────────────────────────────────────

_encoder: SentenceTransformer | None = None
_chroma_collection = None


def get_encoder() -> SentenceTransformer:
    global _encoder
    if _encoder is None:
        logger.info(f"[Embeddings] Loading model: {settings.EMBEDDING_MODEL}")
        _encoder = SentenceTransformer(settings.EMBEDDING_MODEL)
    return _encoder


def get_chroma_collection():
    global _chroma_collection
    if _chroma_collection is None:
        client = chromadb.PersistentClient(path=settings.CHROMA_PATH)
        _chroma_collection = client.get_or_create_collection(
            name=settings.CHROMA_COLLECTION,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(f"[Embeddings] ChromaDB collection '{settings.CHROMA_COLLECTION}' ready")
    return _chroma_collection


def _make_document(paper: Paper) -> str:
    """Text fed to encoder — title gets extra weight by prepending twice."""
    return f"{paper.title}. {paper.title}. {paper.abstract}"


# ── Main pipeline ─────────────────────────────────────────────────────────────

async def embed_pending_papers() -> int:
    """
    Fetch all papers where is_embedded=False, encode them,
    upsert to ChromaDB, mark as embedded in DB.
    Returns count of newly embedded papers.
    """
    async with get_db() as db:
        result = await db.execute(
            select(Paper).where(Paper.is_embedded == False)  # noqa: E712
        )
        papers: List[Paper] = result.scalars().all()

    if not papers:
        logger.info("[Embeddings] No pending papers to embed")
        return 0

    logger.info(f"[Embeddings] Embedding {len(papers)} papers in batches of {settings.EMBEDDING_BATCH_SIZE}")

    encoder = get_encoder()
    collection = get_chroma_collection()

    # Process in configurable batches
    total = 0
    for i in range(0, len(papers), settings.EMBEDDING_BATCH_SIZE):
        batch = papers[i : i + settings.EMBEDDING_BATCH_SIZE]

        documents = [_make_document(p) for p in batch]
        embeddings = encoder.encode(documents, show_progress_bar=False).tolist()

        # Metadata stored alongside vectors for filtering
        metadatas = [
            {
                "paper_id": p.id,                           # ← needed for paper-specific RAG
                "title": p.title[:500],
                "authors": ", ".join(p.authors[:5]),
                "categories": ", ".join(p.categories),
                "published_at": p.published_at.isoformat(),
                "arxiv_url": p.arxiv_url,
                "github_url": p.github_url or "",
                "velocity_score": p.velocity_score or 0.0,
                "summary": "",                              # filled after analysis
                "stack_fit": "",
                "score_reasoning": "",
                "overall_score": p.overall_score or 0.0,
                "action": p.action or "",
            }
            for p in batch
        ]

        collection.upsert(
            ids=[p.id for p in batch],
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )

        # Mark as embedded in DB
        async with get_db() as db:
            for p in batch:
                p_db = await db.get(Paper, p.id)
                if p_db:
                    p_db.is_embedded = True

        total += len(batch)
        logger.info(f"[Embeddings] Batch {i//settings.EMBEDDING_BATCH_SIZE + 1} done ({total}/{len(papers)})")

    return total


async def search_similar(query: str, n_results: int = 10) -> List[dict]:
    """
    Semantic search over paper embeddings.
    Returns list of {id, title, score, metadata} dicts.
    """
    encoder = get_encoder()
    collection = get_chroma_collection()

    query_embedding = encoder.encode([query]).tolist()
    results = collection.query(
        query_embeddings=query_embedding,
        n_results=n_results,
        include=["metadatas", "distances", "documents"],
    )

    output = []
    for idx, doc_id in enumerate(results["ids"][0]):
        output.append({
            "id": doc_id,
            "score": round(1 - results["distances"][0][idx], 4),  # cosine → similarity
            "metadata": results["metadatas"][0][idx],
        })
    return output

async def update_paper_metadata(paper) -> None:
    """
    Called after analysis — updates ChromaDB metadata with agent outputs
    so RAG context includes summary, score, action, stack_fit.
    Only updates metadata — does NOT re-embed.
    """
    collection = get_chroma_collection()
    try:
        collection.update(
            ids=[paper.id],
            metadatas=[{
                "paper_id": paper.id,
                "title": paper.title[:500],
                "authors": ", ".join(paper.authors[:5]) if paper.authors else "",
                "categories": ", ".join(paper.categories) if paper.categories else "",
                "published_at": paper.published_at.isoformat() if paper.published_at else "",
                "arxiv_url": paper.arxiv_url or "",
                "github_url": paper.github_url or "",
                "velocity_score": paper.velocity_score or 0.0,
                "summary": (paper.summary or "")[:500],
                "stack_fit": paper.stack_fit or "",
                "score_reasoning": (paper.score_reasoning or "")[:300],
                "overall_score": paper.overall_score or 0.0,
                "action": paper.action or "",
            }]
        )
        logger.info(f"[Embeddings] Metadata updated for {paper.id}")
    except Exception as e:
        logger.warning(f"[Embeddings] Metadata update failed for {paper.id}: {e}")