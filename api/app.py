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
  POST /papers/{id}/ingest
  POST /papers/{id}/analyze
  POST /papers/{id}/analyze/async
  POST /papers/{id}/analyze/stream  (SSE)
  POST /papers/{id}/index
  POST /papers/{id}/chat/deep
  POST /chat
  GET  /jobs
  GET  /jobs/{job_id}
  DELETE /jobs/{job_id}
  GET  /hidden-gems
  GET  /themes
  GET  /search
  GET  /analyzed
  GET  /sessions
  GET  /sessions/{id}
  POST /pipeline/run
  GET  /agents/metrics
  POST /agents/metrics/reset
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
# from ingestion.models import Paper, ChatSession, init_db, get_db
from ingestion.models import Paper, ChatSession, User, UserActivity, init_db, get_db
from agents.pipeline import analyze_paper, get_pipeline
from agents.rag import global_chat, deep_paper_chat
from agents.llm_router import sentinel_state, ping_sentinel
from agents.eval import get_metrics, reset_metrics
from ml.embeddings import update_paper_metadata

logger = logging.getLogger(__name__)

# ── In-memory job store ───────────────────────────────────────────────────────
jobs: dict = {}  # job_id → {status, paper_id, title, result, error, created_at}

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
    global jobs
    jobs.clear()  # Reset jobs to empty on each server start (session-based memory)
    logger.info("[Jobs] Cleared (session-based memory)")
    await init_db()
    logger.info("[DB] Tables ready")
    
    # Clear session-based memory: chat sessions and PDF embeddings
    # async with get_db() as db:
    #     # Delete all chat sessions
    #     from sqlalchemy import delete
    #     await db.execute(delete(ChatSession))
    #     logger.info("[Sessions] Cleared all chat sessions (session-based memory)")
    #     
    #     # Clear PDF embeddings from all papers
    #     papers = (await db.execute(select(Paper))).scalars().all()
    #     for paper in papers:
    #         paper.page_index_doc_id = None
    #         paper.page_index_tree = None
    #         paper.page_index_built = False
    #         paper.page_index_sections = None
    #         paper.page_index_pages = None
    #     logger.info(f"[PDFIndex] Cleared embeddings from {len(papers)} papers (session-based memory)")
    
    # Seed default user if not exists
    async with get_db() as db:
        existing_user = await db.get(User, "default_user")
        if not existing_user:
            user = User(
                id="default_user",
                name="Shaurya",
                email="shaurya@papersignal.ai",
                role="Lead ML Engineer",
                preferences={"theme": "dark", "model_pref": "auto", "alert_threshold": 7.5}
            )
            db.add(user)
            logger.info("[User] Seeded default user Shaurya")

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
    model_pref: str                  = "auto"


class DeepChatRequest(BaseModel):
    model_config = {"protected_namespaces": ()}
    message:    str
    history:    Optional[List[dict]] = []
    session_id: Optional[str]        = None
    model_pref: str                  = "auto"

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


# ── Agent Metrics ─────────────────────────────────────────────────────────────

@app.get("/agents/metrics")
async def agent_metrics():
    return get_metrics()


@app.post("/agents/metrics/reset")
async def reset_agent_metrics():
    reset_metrics()
    return {"status": "reset"}


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


# ── Ingest ────────────────────────────────────────────────────────────────────

@app.post("/papers/{arxiv_id}/ingest")
async def ingest_paper(arxiv_id: str):
    """
    Fetch a paper from ArXiv by ID → save to DB → embed.
    Auto-called by Analyze overlay when paper not in DB.
    """
    import arxiv as arxiv_lib
    from ingestion.scraper import _build_arxiv_client, _result_to_paper
    from ml.embeddings import embed_pending_papers

    async with get_db() as db:
        existing = await db.get(Paper, arxiv_id)
        if existing:
            return {"status": "already_exists", "paper_id": arxiv_id, "title": existing.title}

    try:
        client = _build_arxiv_client()
        search = arxiv_lib.Search(id_list=[arxiv_id])
        result = next(client.results(search))
    except StopIteration:
        raise HTTPException(status_code=404, detail=f"Paper {arxiv_id} not found on ArXiv")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    paper = _result_to_paper(result)

    async with get_db() as db:
        db.add(paper)
        await log_activity(db, "ingest", f"Ingested paper: {paper.title[:60]}...")

    await embed_pending_papers()

    logger.info(f"[Ingest] {arxiv_id} — {paper.title[:60]}")
    return {
        "status":   "ingested",
        "paper_id": paper.id,
        "title":    paper.title,
        "pdf_url":  paper.pdf_url,
    }


# ── Analyze (sync) ────────────────────────────────────────────────────────────

@app.post("/papers/{paper_id}/analyze")
async def analyze_single_paper(paper_id: str):
    async with get_db() as db:
        paper = await db.get(Paper, paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    result = await analyze_paper(paper)
    await _save_analysis(paper_id, result)
    return result


# ── Analyze (async job) ───────────────────────────────────────────────────────

@app.post("/papers/{paper_id}/analyze/async")
async def analyze_single_paper_async(paper_id: str, background_tasks: BackgroundTasks):
    """Submit analysis as background job. Returns job_id immediately."""
    async with get_db() as db:
        paper = await db.get(Paper, paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    job_id = str(uuid.uuid4())
    jobs[job_id] = {
        "job_id":     job_id,
        "status":     "pending",
        "paper_id":   paper_id,
        "title":      paper.title,
        "result":     None,
        "error":      None,
        "created_at": datetime.utcnow().isoformat(),
    }
    background_tasks.add_task(_run_analysis_job, job_id, paper)
    logger.info(f"[Job] Queued {job_id} for {paper_id}")
    return {"job_id": job_id, "status": "pending", "paper_id": paper_id, "title": paper.title}


async def _run_analysis_job(job_id: str, paper):
    """Background task — runs 4-agent pipeline, updates job store."""
    jobs[job_id]["status"] = "running"
    try:
        result = await analyze_paper(paper)
        await _save_analysis(paper.id, result)
        jobs[job_id]["status"] = "done"
        jobs[job_id]["result"] = result
        logger.info(f"[Job] {job_id} done — {paper.id}")
    except Exception as e:
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["error"]  = str(e)
        logger.error(f"[Job] {job_id} failed: {e}", exc_info=True)


# ── Job endpoints ─────────────────────────────────────────────────────────────

@app.get("/jobs")
async def list_all_jobs():
    return list(jobs.values())


@app.get("/jobs/{job_id}")
async def get_job_status(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.delete("/jobs/{job_id}")
async def delete_job(job_id: str):
    if job_id in jobs:
        del jobs[job_id]
    return {"status": "deleted"}


# ── Analyze (SSE stream) ──────────────────────────────────────────────────────

@app.post("/papers/{paper_id}/analyze/stream")
async def analyze_stream(paper_id: str):
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
            await log_activity(db, "analyze", f"Analyzed paper: {p.title[:60]}...")


# ── PDF Index ─────────────────────────────────────────────────────────────────

@app.post("/papers/{paper_id}/index")
async def build_index(paper_id: str):
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
            await log_activity(db, "index", f"Indexed PDF for paper: {p.title[:60]}...")

    logger.info(f"[PDFIndex] {paper_id}: {index_data['sections']} sections, {index_data['pages']} pages")
    return {
        "status":   "built",
        "doc_id":   index_data["doc_id"],
        "sections": index_data["sections"],
        "pages":    index_data["pages"],
        "chunks":   index_data.get("chunks", 0),
        "math":     index_data.get("math", 0),
        "tables":   index_data.get("tables", 0),
    }


# ── Paper Chat ────────────────────────────────────────────────────────────────

@app.post("/papers/{paper_id}/chat/deep")
async def deep_chat(paper_id: str, req: DeepChatRequest):
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


# @app.get("/analyzed")
# async def analyzed_papers(action: Optional[str] = None, limit: int = 50):
#     async with get_db() as db:
#         q = (
#             select(Paper)
#             .where(Paper.is_analyzed == True)
#             .order_by(Paper.overall_score.desc())
#         )
#         if action: q = q.where(Paper.action == action)
#         q = q.limit(limit)
#         papers = (await db.execute(q)).scalars().all()
#     return [_paper_to_dict(p) for p in papers]

@app.get("/analyzed")
async def analyzed_papers(action: Optional[str] = None, recent: bool = False, limit: int = 50):
    async with get_db() as db:
        q = (
            select(Paper)
            .where(Paper.is_analyzed == True)
            .order_by(Paper.overall_score.desc())
        )
        if action: 
            q = q.where(Paper.action == action)
            
        if recent:
            # Get latest ingested_at timestamp
            max_ingest_q = select(Paper.ingested_at).order_by(Paper.ingested_at.desc()).limit(1)
            latest_ingest_time = (await db.execute(max_ingest_q)).scalar_one_or_none()
            if latest_ingest_time:
                # Group papers ingested in the last 2 hours of the latest ingestion
                from datetime import timedelta
                start_window = latest_ingest_time - timedelta(hours=2)
                q = q.where(Paper.ingested_at >= start_window)

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
            # Use message for logging details instead of parsing s.title
            detail_msg = message[:50] + ("..." if len(message) > 50 else "")
            await log_activity(db, "chat", f"Chat: {detail_msg}")
        else:
            sid     = str(uuid.uuid4())
            title   = message[:80] + ("..." if len(message) > 80 else "")
            session = ChatSession(
                id=sid, session_type=session_type,
                paper_id=paper_id, paper_title=paper_title,
                title=title, messages=new_messages, message_count=1,
            )
            db.add(session)
            detail_msg = message[:50] + ("..." if len(message) > 50 else "")
            await log_activity(db, "chat", f"Chat: {detail_msg}")
    return session.id


# ── User Profile & Action Logging System ──────────────────────────────────────

async def log_activity(db, action_type: str, details: str, user_id: str = "default_user"):
    act = UserActivity(user_id=user_id, action_type=action_type, details=details)
    db.add(act)

class ProfileUpdateRequest(BaseModel):
    model_config = {"protected_namespaces": ()}
    name:        Optional[str]  = None
    email:       Optional[str]  = None
    role:        Optional[str]  = None
    preferences: Optional[dict] = None

@app.get("/user/profile")
async def get_user_profile(user_id: str = "default_user"):
    async with get_db() as db:
        user = await db.get(User, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "role": user.role,
            "preferences": user.preferences,
            "created_at": user.created_at.isoformat()
        }

@app.post("/user/profile")
async def update_user_profile(req: ProfileUpdateRequest, user_id: str = "default_user"):
    async with get_db() as db:
        user = await db.get(User, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        if req.name is not None:        user.name = req.name
        if req.email is not None:       user.email = req.email
        if req.role is not None:        user.role = req.role
        if req.preferences is not None: user.preferences = {**user.preferences, **req.preferences}
        
        # Log profile update action
        await log_activity(db, "profile", "Updated user profile settings")
        return {
            "status": "success",
            "name": user.name,
            "email": user.email,
            "role": user.role,
            "preferences": user.preferences
        }

@app.get("/user/activity")
async def get_user_activity(limit: int = 20, user_id: str = "default_user"):
    async with get_db() as db:
        q = (
            select(UserActivity)
            .where(UserActivity.user_id == user_id)
            .order_by(UserActivity.timestamp.desc())
            .limit(limit)
        )
        activities = (await db.execute(q)).scalars().all()
    return [
        {
            "id": a.id,
            "action_type": a.action_type,
            "details": a.details,
            "timestamp": a.timestamp.isoformat()
        }
        for a in activities
    ]