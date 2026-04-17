"""
Paper2Signal — FastAPI Application
All endpoints for frontend consumption.

Endpoints:
  GET  /health
  GET  /papers
  GET  /papers/{id}
  GET  /papers/{id}/brief
  GET  /papers/{id}/session
  POST /papers/{id}/analyze
  POST /papers/{id}/analyze/stream  (SSE)
  POST /papers/{id}/index           (PageIndex build)
  POST /papers/{id}/chat            (abstract level)
  POST /papers/{id}/chat/deep       (PageIndex full PDF)
  POST /chat                        (global RAG)
  GET  /hidden-gems
  GET  /themes
  GET  /search
  GET  /analyzed
  GET  /sessions
  GET  /sessions/{id}
  POST /pipeline/run
"""
'''
import uuid
import json
import logging
import asyncio
from datetime import datetime
from typing import Optional, List, AsyncGenerator

from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select, and_

from config.settings import settings
from ingestion.models import Paper, ChatSession, init_db, get_db
from agents.pipeline import analyze_paper, get_pipeline
from agents.rag import global_chat, paper_chat, deep_paper_chat
from agents.llm_router import sentinel_state, ping_sentinel
from ml.embeddings import update_paper_metadata

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Paper2Signal API",
    description="AI Research Intelligence Platform",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Startup ───────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    logger.info("[Paper2Signal] Starting up...")
    await init_db()
    logger.info("[DB] Tables ready")
    get_pipeline()
    logger.info("[Pipeline] Ready")
    # Start Sentinel keep-alive — pings every 20min to prevent cold starts
    asyncio.create_task(_sentinel_keepalive())
    logger.info("[Sentinel] Keep-alive task started (20min interval)")


# ── Request/Response Models ───────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    history: Optional[List[dict]] = []
    paper_id: Optional[str] = None
    session_id: Optional[str] = None
    user_stack: Optional[List[str]] = []


class DeepChatRequest(BaseModel):
    message: str
    history: Optional[List[dict]] = []
    session_id: Optional[str] = None


class AnalyzeUrlRequest(BaseModel):
    arxiv_url: str


# ── Health ────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    async with get_db() as db:
        total = (await db.execute(select(Paper))).scalars().all()
        analyzed = [p for p in total if p.is_analyzed]
        indexed = [p for p in total if p.page_index_built]
    return {
        "status": "ok",
        "papers_count": len(total),
        "analyzed_count": len(analyzed),
        "deep_indexed_count": len(indexed),
        "pipeline": "ready",
        "sentinel": sentinel_state.to_dict(),
    }


@app.get("/sentinel/status")
async def sentinel_status():
    """Detailed Sentinel Space status — latency, warmth, call history."""
    stats = sentinel_state.to_dict()
    stats["space_url"] = "https://shau1905-papersignal-sentinal.hf.space"
    stats["model"] = "shau1905/papersignal-hype-detector"
    stats["note"] = (
        "Cold start ~60-90s. Warm calls ~15-25s. "
        "Keep-alive ping runs every 20min to prevent cold starts."
    )
    return stats


@app.post("/sentinel/ping")
async def sentinel_ping():
    """Manually trigger a keep-alive ping to warm up The Sentinel."""
    import time
    t = time.time()
    ok = await ping_sentinel()
    return {
        "success": ok,
        "latency_s": round(time.time() - t, 1),
        "sentinel": sentinel_state.to_dict(),
    }


# ── Papers ────────────────────────────────────────────────────────────────

@app.get("/papers")
async def list_papers(
    limit: int = 20,
    offset: int = 0,
    action: Optional[str] = None,
    domain: Optional[str] = None,
    has_github: Optional[bool] = None,
    analyzed_only: bool = False,
):
    async with get_db() as db:
        q = select(Paper).order_by(Paper.ingested_at.desc())
        if action:
            q = q.where(Paper.action == action)
        if domain:
            q = q.where(Paper.domain == domain)
        if has_github:
            q = q.where(Paper.github_url.isnot(None))
        if analyzed_only:
            q = q.where(Paper.is_analyzed == True)
        q = q.offset(offset).limit(limit)
        papers = (await db.execute(q)).scalars().all()

    return [_paper_to_dict(p) for p in papers]


@app.get("/papers/{paper_id}")
async def get_paper(paper_id: str):
    async with get_db() as db:
        paper = await db.get(Paper, paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    return _paper_to_dict(paper, full=True)


@app.get("/papers/{paper_id}/brief")
async def get_brief(paper_id: str):
    async with get_db() as db:
        paper = await db.get(Paper, paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    return {
        "paper_id":       paper.id,
        "title":          paper.title,
        "summary":        paper.summary,
        "stack_fit":      paper.stack_fit,
        "action":         paper.action,
        "action_reason":  paper.action_reason,
        "overall_score":  paper.overall_score,
        "score_reasoning": paper.score_reasoning,
        "hype_score":     paper.hype_score,
        "hype_reason":    paper.hype_reason,
        "contributions":  paper.contributions,
        "domain":         paper.domain,
        "novelty":        paper.novelty,
        "arxiv_url":      paper.arxiv_url,
        "github_url":     paper.github_url,
        "page_index_built": paper.page_index_built,
        "page_index_sections": paper.page_index_sections,
        "page_index_pages": paper.page_index_pages,
    }


@app.get("/papers/{paper_id}/session")
async def get_paper_session(paper_id: str):
    """
    Check if paper has PageIndex session built.
    Returns index status + existing chat sessions for this paper.
    """
    async with get_db() as db:
        paper = await db.get(Paper, paper_id)
        if not paper:
            raise HTTPException(status_code=404, detail="Paper not found")

        sessions_q = select(ChatSession).where(
            ChatSession.paper_id == paper_id
        ).order_by(ChatSession.last_used.desc())
        sessions = (await db.execute(sessions_q)).scalars().all()

    return {
        "paper_id":     paper_id,
        "indexed":      paper.page_index_built,
        "doc_id":       paper.page_index_doc_id,
        "sections":     paper.page_index_sections,
        "pages":        paper.page_index_pages,
        "sessions":     [_session_to_dict(s) for s in sessions],
    }


# ── Analyze ───────────────────────────────────────────────────────────────

@app.post("/papers/{paper_id}/analyze")
async def analyze_single_paper(paper_id: str):
    async with get_db() as db:
        paper = await db.get(Paper, paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    result = await analyze_paper(paper)

    async with get_db() as db:
        p = await db.get(Paper, paper_id)
        if p:
            p.domain         = result.get("domain")
            p.novelty        = result.get("novelty")
            p.contributions  = result.get("contributions")
            p.has_code       = result.get("has_code")
            p.overall_score  = result.get("overall_score")
            p.reproducibility = result.get("reproducibility")
            p.compute_cost   = result.get("compute_cost")
            p.latency_score  = result.get("latency")
            p.adoption       = result.get("adoption")
            p.score_reasoning = result.get("score_reasoning")
            p.summary        = result.get("summary")
            p.stack_fit      = result.get("stack_fit")
            p.action         = result.get("action")
            p.action_reason  = result.get("action_reason")
            p.hype_score     = result.get("hype_score")
            p.hype_reason    = result.get("hype_reason")
            p.is_analyzed    = True
            # Update ChromaDB metadata so RAG context includes analysis results
            await update_paper_metadata(p)

    return result


@app.post("/papers/{paper_id}/analyze/stream")
async def analyze_stream(paper_id: str):
    """
    SSE endpoint — streams agent progress events to frontend.
    Frontend receives step-by-step updates as agents run.
    """
    async with get_db() as db:
        paper = await db.get(Paper, paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    async def event_generator() -> AsyncGenerator[str, None]:
        agents = [
            ("classifier", "The Reasoner", "Classifying domain and novelty..."),
            ("scorer",     "The Thinker",  "Scoring production readiness..."),
            ("brief",      "The Scribe",   "Writing intelligence brief..."),
            ("hype",       "The Sentinel", "Predicting community hype..."),
        ]

        # Send start event
        yield f"data: {json.dumps({'type': 'start', 'paper_id': paper_id})}\n\n"
        await asyncio.sleep(0.1)

        # Run actual analysis
        result_container = {}

        async def run_analysis():
            result_container["result"] = await analyze_paper(paper)

        task = asyncio.create_task(run_analysis())

        # Stream fake progress while waiting
        for i, (agent_id, agent_name, description) in enumerate(agents):
            yield f"data: {json.dumps({'type': 'agent_start', 'agent': agent_id, 'name': agent_name, 'description': description, 'step': i+1, 'total': 4})}\n\n"
            await asyncio.sleep(2.5)
            yield f"data: {json.dumps({'type': 'agent_done', 'agent': agent_id, 'name': agent_name, 'step': i+1})}\n\n"
            await asyncio.sleep(0.3)

        # Wait for real result
        await task
        result = result_container.get("result", {})

        # Save to DB
        async with get_db() as db:
            p = await db.get(Paper, paper_id)
            if p:
                p.domain          = result.get("domain")
                p.novelty         = result.get("novelty")
                p.contributions   = result.get("contributions")
                p.has_code        = result.get("has_code")
                p.overall_score   = result.get("overall_score")
                p.reproducibility = result.get("reproducibility")
                p.compute_cost    = result.get("compute_cost")
                p.latency_score   = result.get("latency")
                p.adoption        = result.get("adoption")
                p.score_reasoning = result.get("score_reasoning")
                p.summary         = result.get("summary")
                p.stack_fit       = result.get("stack_fit")
                p.action          = result.get("action")
                p.action_reason   = result.get("action_reason")
                p.hype_score      = result.get("hype_score")
                p.hype_reason     = result.get("hype_reason")
                p.is_analyzed     = True
                await update_paper_metadata(p)

        yield f"data: {json.dumps({'type': 'complete', 'result': result})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
    )


# ── PageIndex — Deep Chat ─────────────────────────────────────────────────

@app.post("/papers/{paper_id}/index")
async def build_index(paper_id: str, background_tasks: BackgroundTasks):
    """
    Trigger PageIndex build for a paper.
    Returns immediately — build happens in background.
    Frontend polls /papers/{id}/session to check status.
    """
    async with get_db() as db:
        paper = await db.get(Paper, paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    if paper.page_index_built:
        return {
            "status":   "already_built",
            "doc_id":   paper.page_index_doc_id,
            "sections": paper.page_index_sections,
            "pages":    paper.page_index_pages,
        }

    if not settings.PAGEINDEX_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="PageIndex API key not configured"
        )

    background_tasks.add_task(_build_index_task, paper_id)

    return {
        "status":   "building",
        "paper_id": paper_id,
        "message":  "Index building started. Poll /papers/{id}/session to check status.",
    }


async def _build_index_task(paper_id: str):
    """Background task: fetch PDF → build PageIndex → save to DB."""
    from ml.page_indexer import build_paper_index

    logger.info(f"[PageIndex] Building index for {paper_id}...")

    try:
        index_data = await build_paper_index(paper_id)

        async with get_db() as db:
            paper = await db.get(Paper, paper_id)
            if paper:
                paper.page_index_doc_id   = index_data["doc_id"]
                paper.page_index_tree     = index_data["tree"]
                paper.page_index_built    = True
                paper.page_index_sections = index_data["sections"]
                paper.page_index_pages    = index_data["pages"]

        logger.info(
            f"[PageIndex] Index built for {paper_id}: "
            f"{index_data['sections']} sections, {index_data['pages']} pages"
        )

    except Exception as e:
        logger.error(f"[PageIndex] Build failed for {paper_id}: {e}")


@app.post("/papers/{paper_id}/chat/deep")
async def deep_chat(paper_id: str, req: DeepChatRequest):
    """
    Deep chat using PageIndex — full PDF, section-aware, code generation.
    Requires paper to be indexed first via POST /papers/{id}/index.
    Saves session to DB automatically.
    """
    async with get_db() as db:
        paper = await db.get(Paper, paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    if not paper.page_index_built or not paper.page_index_doc_id:
        raise HTTPException(
            status_code=400,
            detail="Paper not indexed yet. Call POST /papers/{id}/index first."
        )

    paper_context = {
        "title":          paper.title,
        "overall_score":  paper.overall_score or 0,
        "action":         paper.action or "",
        "stack_fit":      paper.stack_fit or "",
        "score_reasoning": paper.score_reasoning or "",
    }

    result = await deep_paper_chat(
        query=req.message,
        paper_id=paper_id,
        doc_id=paper.page_index_doc_id,
        paper_context=paper_context,
        history=req.history,
    )

    # Save/update session
    session_id = await _save_session(
        session_id=req.session_id,
        session_type="deep",
        paper_id=paper_id,
        paper_title=paper.title,
        message=req.message,
        answer=result["answer"],
        history=req.history,
    )

    return {**result, "session_id": session_id}


# ── Chat ──────────────────────────────────────────────────────────────────

@app.post("/papers/{paper_id}/chat")
async def paper_level_chat(paper_id: str, req: ChatRequest):
    """Abstract-level paper chat via ChromaDB RAG."""
    async with get_db() as db:
        paper = await db.get(Paper, paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    result = await paper_chat(
        query=req.message,
        paper_id=paper_id,
        paper_title=paper.title,
        paper_abstract=paper.abstract,
        score_reasoning=paper.score_reasoning or "",
        stack_fit=paper.stack_fit or "",
        overall_score=paper.overall_score or 0.0,
        action=paper.action or "",
        user_stack=req.user_stack or [],
        history=req.history,
    )

    session_id = await _save_session(
        session_id=req.session_id,
        session_type="paper",
        paper_id=paper_id,
        paper_title=paper.title,
        message=req.message,
        answer=result["answer"],
        history=req.history,
    )

    return {**result, "session_id": session_id}


@app.post("/chat")
async def global_rag_chat(req: ChatRequest):
    """Global RAG chat across all papers."""
    result = await global_chat(
        query=req.message,
        history=req.history,
        n_papers=settings.RAG_TOP_K,
    )

    session_id = await _save_session(
        session_id=req.session_id,
        session_type="global",
        paper_id=None,
        paper_title=None,
        message=req.message,
        answer=result["answer"],
        history=req.history,
    )

    return {**result, "session_id": session_id}


# ── Sessions ──────────────────────────────────────────────────────────────

@app.get("/sessions")
async def list_sessions(
    session_type: Optional[str] = None,
    paper_id: Optional[str] = None,
    limit: int = 50,
):
    """Return all saved chat sessions for profile page."""
    async with get_db() as db:
        q = select(ChatSession).order_by(ChatSession.last_used.desc())
        if session_type:
            q = q.where(ChatSession.session_type == session_type)
        if paper_id:
            q = q.where(ChatSession.paper_id == paper_id)
        q = q.limit(limit)
        sessions = (await db.execute(q)).scalars().all()

    return [_session_to_dict(s) for s in sessions]


@app.get("/sessions/{session_id}")
async def get_session(session_id: str):
    """Get full session with all messages — for restoring chat."""
    async with get_db() as db:
        session = await db.get(ChatSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return _session_to_dict(session, full=True)


# ── Discovery ─────────────────────────────────────────────────────────────

@app.get("/hidden-gems")
async def hidden_gems(limit: int = 10):
    """
    Papers with high production score but low hype.
    These are what the community is sleeping on.
    """
    async with get_db() as db:
        q = (
            select(Paper)
            .where(
                and_(
                    Paper.is_analyzed == True,
                    Paper.overall_score >= 7.0,
                    Paper.hype_score <= 4.0,
                )
            )
            .order_by(Paper.overall_score.desc())
            .limit(limit)
        )
        papers = (await db.execute(q)).scalars().all()

    return [_paper_to_dict(p) for p in papers]


@app.get("/analyzed")
async def analyzed_papers(
    action: Optional[str] = None,
    limit: int = 50,
):
    async with get_db() as db:
        q = (
            select(Paper)
            .where(Paper.is_analyzed == True)
            .order_by(Paper.overall_score.desc())
        )
        if action:
            q = q.where(Paper.action == action)
        q = q.limit(limit)
        papers = (await db.execute(q)).scalars().all()

    return [_paper_to_dict(p) for p in papers]


@app.get("/themes")
async def get_themes():
    async with get_db() as db:
        q = select(Paper).where(Paper.cluster_theme.isnot(None))
        papers = (await db.execute(q)).scalars().all()

    themes: dict = {}
    for p in papers:
        theme = p.cluster_theme
        if theme and theme != "Unclustered":
            if theme not in themes:
                themes[theme] = {"theme": theme, "count": 0, "papers": []}
            themes[theme]["count"] += 1
            if len(themes[theme]["papers"]) < 3:
                themes[theme]["papers"].append({"id": p.id, "title": p.title})

    return sorted(themes.values(), key=lambda x: x["count"], reverse=True)


@app.get("/search")
async def search_papers(q: str, limit: int = 10):
    from ml.embeddings import search_similar
    results = await search_similar(q, n_results=limit)
    return results


# ── Sentinel Keep-alive ──────────────────────────────────────────────────────

async def _sentinel_keepalive():
    """
    Runs forever in background. Pings Sentinel every 20 minutes.
    Prevents HF Space cold starts — keeps analyze fast.
    20min < 30min HF Space sleep threshold.
    """
    while True:
        await asyncio.sleep(1200)   # 20 minutes
        try:
            await ping_sentinel()
        except Exception as e:
            logger.warning(f"[Sentinel] Keep-alive error: {e}")


# ── Pipeline ──────────────────────────────────────────────────────────────

@app.post("/pipeline/run")
async def run_pipeline(background_tasks: BackgroundTasks):
    background_tasks.add_task(_run_full_pipeline)
    return {
        "message": "Pipeline triggered. Running in background.",
        "stages": ["scrape", "embed", "cluster", "velocity"],
    }


async def _run_full_pipeline():
    from ingestion.scraper import run_scrape
    from ml.embeddings import embed_pending_papers
    from ml.clustering import run_clustering
    from ml.velocity import score_papers

    logger.info("[Pipeline] Starting...")
    try:
        run = await run_scrape()
        logger.info(f"[Pipeline] Scrape: {run.papers_new} new")
        embedded = await embed_pending_papers()
        logger.info(f"[Pipeline] Embedded: {embedded}")
        await run_clustering()
        logger.info("[Pipeline] Clustering done")
        scored = await score_papers()
        logger.info(f"[Pipeline] Velocity: {scored}")
    except Exception as e:
        logger.error(f"[Pipeline] Failed: {e}", exc_info=True)


# ── Helpers ───────────────────────────────────────────────────────────────

def _paper_to_dict(paper: Paper, full: bool = False) -> dict:
    d = {
        "id":              paper.id,
        "title":           paper.title,
        "authors":         paper.authors or [],
        "categories":      paper.categories or [],
        "published_at":    paper.published_at.isoformat() if paper.published_at else None,
        "arxiv_url":       paper.arxiv_url,
        "github_url":      paper.github_url,
        "velocity_score":  paper.velocity_score,
        "github_stars":    paper.github_stars,
        "cluster_theme":   paper.cluster_theme,
        "domain":          paper.domain,
        "novelty":         paper.novelty,
        "overall_score":   paper.overall_score,
        "reproducibility": paper.reproducibility,
        "compute_cost":    paper.compute_cost,
        "latency_score":   paper.latency_score,
        "adoption":        paper.adoption,
        "action":          paper.action,
        "action_reason":   paper.action_reason,
        "hype_score":      paper.hype_score,
        "hype_reason":     paper.hype_reason,
        "is_analyzed":     paper.is_analyzed,
        "page_index_built": paper.page_index_built,
        "page_index_sections": paper.page_index_sections,
        "page_index_pages": paper.page_index_pages,
    }
    if full:
        d.update({
            "abstract":        paper.abstract,
            "summary":         paper.summary,
            "stack_fit":       paper.stack_fit,
            "score_reasoning": paper.score_reasoning,
            "contributions":   paper.contributions,
            "has_code":        paper.has_code,
            "pdf_url":         paper.pdf_url,
            "page_index_doc_id": paper.page_index_doc_id,
        })
    return d


def _session_to_dict(session: ChatSession, full: bool = False) -> dict:
    d = {
        "id":            session.id,
        "session_type":  session.session_type,
        "paper_id":      session.paper_id,
        "paper_title":   session.paper_title,
        "title":         session.title,
        "message_count": session.message_count,
        "created_at":    session.created_at.isoformat(),
        "last_used":     session.last_used.isoformat(),
    }
    if full:
        d["messages"] = session.messages
    return d


async def _save_session(
    session_id: Optional[str],
    session_type: str,
    paper_id: Optional[str],
    paper_title: Optional[str],
    message: str,
    answer: str,
    history: list,
) -> str:
    """Create or update a chat session."""
    async with get_db() as db:
        if session_id:
            session = await db.get(ChatSession, session_id)
        else:
            session = None

        new_messages = history + [
            {"role": "user",      "content": message},
            {"role": "assistant", "content": answer},
        ]

        if session:
            session.messages      = new_messages
            session.message_count = len(new_messages) // 2
            session.last_used     = datetime.utcnow()
        else:
            sid = str(uuid.uuid4())
            # Title = first user message truncated
            title = message[:80] + ("..." if len(message) > 80 else "")
            session = ChatSession(
                id=sid,
                session_type=session_type,
                paper_id=paper_id,
                paper_title=paper_title,
                title=title,
                messages=new_messages,
                message_count=1,
            )
            db.add(session)

    return session.id


# ── Static files — must be LAST ───────────────────────────────────────────
# Uncomment after building React frontend:
# app.mount("/", StaticFiles(directory="static", html=True), name="static")'''




"""
Paper2Signal — FastAPI Application

Endpoints:
  GET  /health
  GET  /sentinel/status
  POST /sentinel/ping
  GET  /papers
  GET  /papers/{id}
  GET  /papers/{id}/brief
  GET  /papers/{id}/session
  POST /papers/{id}/analyze
  POST /papers/{id}/analyze/stream  (SSE)
  POST /papers/{id}/index           (local PDF index — free, no API cost)
  POST /papers/{id}/chat/deep       (unified paper agent)
  POST /chat                        (global RAG)
  GET  /hidden-gems
  GET  /themes
  GET  /search
  GET  /analyzed
  GET  /sessions
  GET  /sessions/{id}
  POST /pipeline/run
"""

import uuid
import json
import logging
import asyncio
from datetime import datetime
from typing import Optional, List, AsyncGenerator

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select, and_

from config.settings import settings
from ingestion.models import Paper, ChatSession, init_db, get_db
from agents.pipeline import analyze_paper, get_pipeline
from agents.rag import global_chat, deep_paper_chat
from agents.llm_router import sentinel_state, ping_sentinel
from ml.embeddings import update_paper_metadata

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Paper2Signal API",
    description="AI Research Intelligence Platform",
    version="3.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Startup ───────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    logger.info("[Paper2Signal] Starting up...")
    await init_db()
    logger.info("[DB] Tables ready")
    get_pipeline()
    logger.info("[Pipeline] Ready")
    asyncio.create_task(_sentinel_keepalive())
    logger.info("[Sentinel] Keep-alive task started")


# ── Request Models ────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    model_config = {"protected_namespaces": ()}
    message:    str
    history:    Optional[List[dict]] = []
    session_id: Optional[str]        = None
    model_pref: str                  = "auto"   # "auto" | "groq" | "openai"


class DeepChatRequest(BaseModel):
    model_config = {"protected_namespaces": ()}
    message:    str
    history:    Optional[List[dict]] = []
    session_id: Optional[str]        = None
    model_pref: str                  = "auto"   # "auto" | "groq" | "openai"
 
from datetime import datetime as _dt
 
class SeedPaperRequest(BaseModel):
    model_config = {"protected_namespaces": ()}
    id:           str
    title:        str
    abstract:     str
    authors:      Optional[List]  = []
    categories:   Optional[List]  = []
    arxiv_url:    Optional[str]   = None
    pdf_url:      Optional[str]   = None
    github_url:   Optional[str]   = None
    published_at: Optional[str]   = None
    updated_at:   Optional[str]   = None
 
 
@app.post("/seed/paper")
async def seed_paper(req: SeedPaperRequest):
    """
    Direct paper insert for seeding landmark papers.
    Returns 'exists' if already in DB, 'added' if new.
    Used by seed_db.py — not called by the frontend.
    """
    async with get_db() as db:
        existing = await db.get(Paper, req.id)
        if existing:
            return {"status": "exists", "id": req.id}
 
        now = _dt.utcnow()
        paper = Paper(
            id           = req.id,
            title        = req.title,
            abstract     = req.abstract,
            authors      = req.authors or [],
            categories   = req.categories or [],
            published_at = _dt.fromisoformat(req.published_at) if req.published_at else now,
            updated_at   = _dt.fromisoformat(req.updated_at)   if req.updated_at   else now,
            arxiv_url    = req.arxiv_url or f"https://arxiv.org/abs/{req.id}",
            pdf_url      = req.pdf_url,
            github_url   = req.github_url,
        )
        db.add(paper)
 
    logger.info(f"[Seed] Added: {req.id} — {req.title[:60]}")
    return {"status": "added", "id": req.id, "title": req.title}
 
# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    async with get_db() as db:
        total    = (await db.execute(select(Paper))).scalars().all()
        analyzed = [p for p in total if p.is_analyzed]
        indexed  = [p for p in total if p.page_index_built]
    return {
        "status":             "ok",
        "papers_count":       len(total),
        "analyzed_count":     len(analyzed),
        "deep_indexed_count": len(indexed),
        "pipeline":           "ready",
        "sentinel":           sentinel_state.to_dict(),
    }


@app.get("/sentinel/status")
async def sentinel_status():
    stats = sentinel_state.to_dict()
    stats["model"] = "shau1905/papersignal-hype-detector"
    stats["note"]  = "Cold start ~60-90s. Keep-alive runs every 20min."
    return stats


@app.post("/sentinel/ping")
async def sentinel_ping():
    import time
    t  = time.time()
    ok = await ping_sentinel()
    return {
        "success":   ok,
        "latency_s": round(time.time() - t, 1),
        "sentinel":  sentinel_state.to_dict(),
    }


# ── Papers ────────────────────────────────────────────────────────────────────

@app.get("/papers")
async def list_papers(
    limit:         int            = 20,
    offset:        int            = 0,
    action:        Optional[str]  = None,
    domain:        Optional[str]  = None,
    has_github:    Optional[bool] = None,
    analyzed_only: bool           = False,
):
    async with get_db() as db:
        q = select(Paper).order_by(Paper.ingested_at.desc())
        if action:        q = q.where(Paper.action == action)
        if domain:        q = q.where(Paper.domain == domain)
        if has_github:    q = q.where(Paper.github_url.isnot(None))
        if analyzed_only: q = q.where(Paper.is_analyzed == True)
        q = q.offset(offset).limit(limit)
        papers = (await db.execute(q)).scalars().all()
    return [_paper_to_dict(p) for p in papers]


@app.get("/papers/{paper_id}")
async def get_paper(paper_id: str):
    async with get_db() as db:
        paper = await db.get(Paper, paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    return _paper_to_dict(paper, full=True)


@app.get("/papers/{paper_id}/brief")
async def get_brief(paper_id: str):
    async with get_db() as db:
        paper = await db.get(Paper, paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    return {
        "paper_id":            paper.id,
        "title":               paper.title,
        "summary":             paper.summary,
        "stack_fit":           paper.stack_fit,
        "action":              paper.action,
        "action_reason":       paper.action_reason,
        "overall_score":       paper.overall_score,
        "score_reasoning":     paper.score_reasoning,
        "hype_score":          paper.hype_score,
        "hype_reason":         paper.hype_reason,
        "contributions":       paper.contributions,
        "domain":              paper.domain,
        "novelty":             paper.novelty,
        "arxiv_url":           paper.arxiv_url,
        "github_url":          paper.github_url,
        "page_index_built":    paper.page_index_built,
        "page_index_sections": paper.page_index_sections,
        "page_index_pages":    paper.page_index_pages,
    }


@app.get("/papers/{paper_id}/session")
async def get_paper_session(paper_id: str):
    """Index status + most recent chat messages."""
    async with get_db() as db:
        paper = await db.get(Paper, paper_id)
        if not paper:
            raise HTTPException(status_code=404, detail="Paper not found")
        sessions_q = (
            select(ChatSession)
            .where(ChatSession.paper_id == paper_id)
            .order_by(ChatSession.last_used.desc())
        )
        sessions = (await db.execute(sessions_q)).scalars().all()

    latest_messages = sessions[0].messages or [] if sessions else []
    return {
        "paper_id": paper_id,
        "indexed":  paper.page_index_built,
        "doc_id":   paper.page_index_doc_id,
        "sections": paper.page_index_sections,
        "pages":    paper.page_index_pages,
        "messages": latest_messages,
        "sessions": [_session_to_dict(s) for s in sessions],
    }


# ── Analyze ───────────────────────────────────────────────────────────────────

@app.post("/papers/{paper_id}/analyze")
async def analyze_single_paper(paper_id: str):
    async with get_db() as db:
        paper = await db.get(Paper, paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    result = await analyze_paper(paper)
    await _save_analysis(paper_id, result)
    return result


@app.post("/papers/{paper_id}/analyze/stream")
async def analyze_stream(paper_id: str):
    """SSE — streams agent progress while analysis runs in background."""
    async with get_db() as db:
        paper = await db.get(Paper, paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    async def event_generator() -> AsyncGenerator[str, None]:
        agents = [
            ("classifier", "The Reasoner", "Classifying domain and novelty..."),
            ("scorer",     "The Thinker",  "Scoring production readiness..."),
            ("brief",      "The Scribe",   "Writing intelligence brief..."),
            ("hype",       "The Sentinel", "Predicting community hype..."),
        ]
        yield f"data: {json.dumps({'type':'start','paper_id':paper_id})}\n\n"
        await asyncio.sleep(0.1)

        result_container = {}

        async def run_analysis():
            result_container["result"] = await analyze_paper(paper)

        task = asyncio.create_task(run_analysis())

        for i, (agent_id, agent_name, desc) in enumerate(agents):
            yield f"data: {json.dumps({'type':'agent_start','agent':agent_id,'name':agent_name,'description':desc,'step':i+1,'total':4})}\n\n"
            await asyncio.sleep(2.5)
            yield f"data: {json.dumps({'type':'agent_done','agent':agent_id,'name':agent_name,'step':i+1})}\n\n"
            await asyncio.sleep(0.3)

        await task
        result = result_container.get("result", {})
        await _save_analysis(paper_id, result)
        yield f"data: {json.dumps({'type':'complete','result':result})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no"},
    )


async def _save_analysis(paper_id: str, result: dict):
    """Write analysis result to DB + update ChromaDB metadata."""
    async with get_db() as db:
        p = await db.get(Paper, paper_id)
        if p:
            p.domain          = result.get("domain")
            p.novelty         = result.get("novelty")
            p.contributions   = result.get("contributions")
            p.has_code        = result.get("has_code")
            p.overall_score   = result.get("overall_score")
            p.reproducibility = result.get("reproducibility")
            p.compute_cost    = result.get("compute_cost")
            p.latency_score   = result.get("latency")
            p.adoption        = result.get("adoption")
            p.score_reasoning = result.get("score_reasoning")
            p.summary         = result.get("summary")
            p.stack_fit       = result.get("stack_fit")
            p.action          = result.get("action")
            p.action_reason   = result.get("action_reason")
            p.hype_score      = result.get("hype_score")
            p.hype_reason     = result.get("hype_reason")
            p.is_analyzed     = True
            await update_paper_metadata(p)


# ── PDF Index ─────────────────────────────────────────────────────────────────

@app.post("/papers/{paper_id}/index")
async def build_index(paper_id: str):
    """
    Download PDF → paragraph extraction → BM25+semantic index → local ChromaDB.
    Free, no external API. ~20-60s per paper.
    """
    async with get_db() as db:
        paper = await db.get(Paper, paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    if paper.page_index_built and paper.page_index_doc_id:
        return {
            "status":   "already_built",
            "doc_id":   paper.page_index_doc_id,
            "sections": paper.page_index_sections,
            "pages":    paper.page_index_pages,
        }

    from ml.pdf_indexer import build_paper_index
    try:
        index_data = await build_paper_index(paper_id)
    except Exception as e:
        logger.error(f"[PDFIndex] Build failed for {paper_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    async with get_db() as db:
        p = await db.get(Paper, paper_id)
        if p:
            p.page_index_doc_id   = index_data["doc_id"]
            p.page_index_tree     = index_data.get("tree", [])
            p.page_index_built    = True
            p.page_index_sections = index_data["sections"]
            p.page_index_pages    = index_data["pages"]

    logger.info(
        f"[PDFIndex] {paper_id}: {index_data['sections']} sections, "
        f"{index_data['pages']} pages, {index_data.get('chunks','?')} chunks"
    )
    return {
        "status":   "built",
        "doc_id":   index_data["doc_id"],
        "sections": index_data["sections"],
        "pages":    index_data["pages"],
        "chunks":   index_data.get("chunks", 0),
        "math":     index_data.get("math", 0),
        "tables":   index_data.get("tables", 0),
    }


# ── Paper Chat (unified agent) ────────────────────────────────────────────────

@app.post("/papers/{paper_id}/chat/deep")
async def deep_chat(paper_id: str, req: DeepChatRequest):
    """
    Paper-specific agent.
    Uses PDF chunks if indexed (hybrid BM25+semantic retrieval),
    falls back to abstract automatically if not.
    Intent layer (explain/math/implement/compare/results) shapes response.
    model_pref: "auto" | "groq" | "openai"
    """
    async with get_db() as db:
        paper = await db.get(Paper, paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    paper_context = {
        "title":           paper.title,
        "abstract":        paper.abstract or "",
        "overall_score":   paper.overall_score or 0,
        "action":          paper.action or "",
        "stack_fit":       paper.stack_fit or "",
        "score_reasoning": paper.score_reasoning or "",
    }

    clean_history = [
        m for m in (req.history or [])
        if m.get("role") in ("user", "assistant")
    ]

    result = await deep_paper_chat(
        query         = req.message,
        paper_id      = paper_id,
        paper_context = paper_context,
        history       = clean_history,
        model_pref    = req.model_pref,
    )

    session_id = await _save_session(
        session_id   = req.session_id,
        session_type = "deep",
        paper_id     = paper_id,
        paper_title  = paper.title,
        message      = req.message,
        answer       = result["answer"],
        history      = clean_history,
    )

    return {**result, "session_id": session_id}


# ── Global Chat ───────────────────────────────────────────────────────────────

@app.post("/chat")
async def global_rag_chat(req: ChatRequest):
    """Global RAG chat across all papers. model_pref controls LLM selection."""
    result = await global_chat(
        query      = req.message,
        history    = req.history,
        n_papers   = settings.RAG_TOP_K,
        model_pref = req.model_pref,
    )

    session_id = await _save_session(
        session_id   = req.session_id,
        session_type = "global",
        paper_id     = None,
        paper_title  = None,
        message      = req.message,
        answer       = result["answer"],
        history      = req.history or [],
    )

    return {**result, "session_id": session_id}


# ── Sessions ──────────────────────────────────────────────────────────────────

@app.get("/sessions")
async def list_sessions(
    session_type: Optional[str] = None,
    paper_id:     Optional[str] = None,
    limit:        int           = 50,
):
    async with get_db() as db:
        q = select(ChatSession).order_by(ChatSession.last_used.desc())
        if session_type: q = q.where(ChatSession.session_type == session_type)
        if paper_id:     q = q.where(ChatSession.paper_id == paper_id)
        q = q.limit(limit)
        sessions = (await db.execute(q)).scalars().all()
    return [_session_to_dict(s) for s in sessions]


@app.get("/sessions/{session_id}")
async def get_session(session_id: str):
    async with get_db() as db:
        session = await db.get(ChatSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return _session_to_dict(session, full=True)


# ── Discovery ─────────────────────────────────────────────────────────────────

@app.get("/hidden-gems")
async def hidden_gems(limit: int = 10):
    """Papers with high production score but low community hype."""
    async with get_db() as db:
        q = (
            select(Paper)
            .where(and_(
                Paper.is_analyzed    == True,
                Paper.overall_score  >= 7.0,
                Paper.hype_score     <= 4.0,
            ))
            .order_by(Paper.overall_score.desc())
            .limit(limit)
        )
        papers = (await db.execute(q)).scalars().all()
    return [_paper_to_dict(p) for p in papers]


@app.get("/analyzed")
async def analyzed_papers(action: Optional[str] = None, limit: int = 50):
    async with get_db() as db:
        q = (
            select(Paper)
            .where(Paper.is_analyzed == True)
            .order_by(Paper.overall_score.desc())
        )
        if action: q = q.where(Paper.action == action)
        q = q.limit(limit)
        papers = (await db.execute(q)).scalars().all()
    return [_paper_to_dict(p) for p in papers]


@app.get("/themes")
async def get_themes():
    async with get_db() as db:
        papers = (await db.execute(select(Paper).where(Paper.cluster_theme.isnot(None)))).scalars().all()
    themes: dict = {}
    for p in papers:
        t = p.cluster_theme
        if t and t != "Unclustered":
            if t not in themes:
                themes[t] = {"theme": t, "count": 0, "papers": []}
            themes[t]["count"] += 1
            if len(themes[t]["papers"]) < 3:
                themes[t]["papers"].append({"id": p.id, "title": p.title})
    return sorted(themes.values(), key=lambda x: x["count"], reverse=True)


@app.get("/search")
async def search_papers(q: str, limit: int = 10):
    from ml.embeddings import search_similar
    return await search_similar(q, n_results=limit)


# ── Sentinel Keep-alive ───────────────────────────────────────────────────────

async def _sentinel_keepalive():
    while True:
        await asyncio.sleep(1200)
        try:
            await ping_sentinel()
        except Exception as e:
            logger.warning(f"[Sentinel] Keep-alive error: {e}")


# ── Pipeline ──────────────────────────────────────────────────────────────────

@app.post("/pipeline/run")
async def run_pipeline(background_tasks: BackgroundTasks):
    background_tasks.add_task(_run_full_pipeline)
    return {"message": "Pipeline triggered.", "stages": ["scrape","embed","cluster","velocity"]}


async def _run_full_pipeline():
    from ingestion.scraper import run_scrape
    from ml.embeddings import embed_pending_papers
    from ml.clustering import run_clustering
    from ml.velocity import score_papers
    logger.info("[Pipeline] Starting...")
    try:
        run      = await run_scrape();           logger.info(f"[Pipeline] Scrape: {run.papers_new} new")
        embedded = await embed_pending_papers(); logger.info(f"[Pipeline] Embedded: {embedded}")
        await run_clustering();                  logger.info("[Pipeline] Clustering done")
        scored   = await score_papers();         logger.info(f"[Pipeline] Velocity: {scored}")
    except Exception as e:
        logger.error(f"[Pipeline] Failed: {e}", exc_info=True)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _paper_to_dict(paper: Paper, full: bool = False) -> dict:
    d = {
        "id":                  paper.id,
        "title":               paper.title,
        "authors":             paper.authors or [],
        "categories":          paper.categories or [],
        "published_at":        paper.published_at.isoformat() if paper.published_at else None,
        "arxiv_url":           paper.arxiv_url,
        "github_url":          paper.github_url,
        "velocity_score":      paper.velocity_score,
        "github_stars":        paper.github_stars,
        "cluster_theme":       paper.cluster_theme,
        "domain":              paper.domain,
        "novelty":             paper.novelty,
        "overall_score":       paper.overall_score,
        "reproducibility":     paper.reproducibility,
        "compute_cost":        paper.compute_cost,
        "latency_score":       paper.latency_score,
        "adoption":            paper.adoption,
        "action":              paper.action,
        "action_reason":       paper.action_reason,
        "hype_score":          paper.hype_score,
        "hype_reason":         paper.hype_reason,
        "is_analyzed":         paper.is_analyzed,
        "page_index_built":    paper.page_index_built,
        "page_index_sections": paper.page_index_sections,
        "page_index_pages":    paper.page_index_pages,
    }
    if full:
        d.update({
            "abstract":          paper.abstract,
            "summary":           paper.summary,
            "stack_fit":         paper.stack_fit,
            "score_reasoning":   paper.score_reasoning,
            "contributions":     paper.contributions,
            "has_code":          paper.has_code,
            "pdf_url":           paper.pdf_url,
            "page_index_doc_id": paper.page_index_doc_id,
        })
    return d


def _session_to_dict(session: ChatSession, full: bool = False) -> dict:
    d = {
        "id":            session.id,
        "session_type":  session.session_type,
        "paper_id":      session.paper_id,
        "paper_title":   session.paper_title,
        "title":         session.title,
        "message_count": session.message_count,
        "created_at":    session.created_at.isoformat(),
        "last_used":     session.last_used.isoformat(),
    }
    if full:
        d["messages"] = session.messages
    return d


async def _save_session(
    session_id:   Optional[str],
    session_type: str,
    paper_id:     Optional[str],
    paper_title:  Optional[str],
    message:      str,
    answer:       str,
    history:      list,
) -> str:
    async with get_db() as db:
        session = await db.get(ChatSession, session_id) if session_id else None
        new_messages = history + [
            {"role": "user",      "content": message},
            {"role": "assistant", "content": answer},
        ]
        if session:
            session.messages      = new_messages
            session.message_count = len(new_messages) // 2
            session.last_used     = datetime.utcnow()
        else:
            sid     = str(uuid.uuid4())
            title   = message[:80] + ("..." if len(message) > 80 else "")
            session = ChatSession(
                id=sid, session_type=session_type,
                paper_id=paper_id, paper_title=paper_title,
                title=title, messages=new_messages, message_count=1,
            )
            db.add(session)
    return session.id