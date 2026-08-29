"""
Paper2Signal — Database Models & Session
"""

from datetime import datetime
from typing import Optional, List
from sqlalchemy import String, Float, Integer, DateTime, Text, Boolean, JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from contextlib import asynccontextmanager

from config.settings import settings


from sqlalchemy import event, text

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=(settings.ENV == "development"),
    future=True,
    connect_args={"timeout": 30, "check_same_thread": False},
)

# WAL mode via async — runs once at startup in init_db()
async def init_db():
    async with engine.begin() as conn:
        await conn.execute(text("PRAGMA journal_mode=WAL"))
        await conn.execute(text("PRAGMA synchronous=NORMAL"))
        await conn.execute(text("PRAGMA busy_timeout=10000"))
        await conn.run_sync(Base.metadata.create_all)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


@asynccontextmanager
async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


class Base(DeclarativeBase):
    pass


class Paper(Base):
    __tablename__ = "papers"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    abstract: Mapped[str] = mapped_column(Text, nullable=False)
    authors: Mapped[List] = mapped_column(JSON, default=list)
    categories: Mapped[List] = mapped_column(JSON, default=list)
    published_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    arxiv_url: Mapped[str] = mapped_column(String(200), nullable=False)
    pdf_url: Mapped[Optional[str]] = mapped_column(String(200))
    github_url: Mapped[Optional[str]] = mapped_column(String(200))

    # Phase 1 — ML scores
    velocity_score: Mapped[Optional[float]] = mapped_column(Float)
    github_stars: Mapped[Optional[int]] = mapped_column(Integer)
    github_stars_delta: Mapped[Optional[int]] = mapped_column(Integer)
    citation_count: Mapped[Optional[int]] = mapped_column(Integer)
    citation_delta: Mapped[Optional[int]] = mapped_column(Integer)
    cluster_id: Mapped[Optional[int]] = mapped_column(Integer)
    cluster_theme: Mapped[Optional[str]] = mapped_column(String(200))
    is_embedded: Mapped[bool] = mapped_column(Boolean, default=False)

    # Phase 2 — Agent outputs
    domain: Mapped[Optional[str]] = mapped_column(String(100))
    novelty: Mapped[Optional[str]] = mapped_column(String(50))
    contributions: Mapped[Optional[List]] = mapped_column(JSON)
    has_code: Mapped[Optional[bool]] = mapped_column(Boolean)
    overall_score: Mapped[Optional[float]] = mapped_column(Float)
    reproducibility: Mapped[Optional[float]] = mapped_column(Float)
    compute_cost: Mapped[Optional[float]] = mapped_column(Float)
    latency_score: Mapped[Optional[float]] = mapped_column(Float)
    adoption: Mapped[Optional[float]] = mapped_column(Float)
    score_reasoning: Mapped[Optional[str]] = mapped_column(Text)
    summary: Mapped[Optional[str]] = mapped_column(Text)
    stack_fit: Mapped[Optional[str]] = mapped_column(Text)
    action: Mapped[Optional[str]] = mapped_column(String(20))
    action_reason: Mapped[Optional[str]] = mapped_column(Text)
    is_analyzed: Mapped[bool] = mapped_column(Boolean, default=False)

    # Phase 3 — Hype model output
    hype_score: Mapped[Optional[float]] = mapped_column(Float)
    hype_reason: Mapped[Optional[str]] = mapped_column(Text)

    # Phase 4 — PageIndex deep chat
    page_index_doc_id: Mapped[Optional[str]] = mapped_column(String(200))
    page_index_tree: Mapped[Optional[dict]] = mapped_column(JSON)
    page_index_built: Mapped[bool] = mapped_column(Boolean, default=False)
    page_index_sections: Mapped[Optional[int]] = mapped_column(Integer)
    page_index_pages: Mapped[Optional[int]] = mapped_column(Integer)

    ingested_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ChatSession(Base):
    """
    Persists both paper-specific (deep) and global RAG chat sessions.
    session_type: "deep" | "global"
    Deep sessions use PageIndex, global sessions use ChromaDB RAG.
    """
    __tablename__ = "chat_sessions"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    session_type: Mapped[str] = mapped_column(String(20))       # "deep" | "global"
    paper_id: Mapped[Optional[str]] = mapped_column(String(50)) # None for global
    paper_title: Mapped[Optional[str]] = mapped_column(Text)    # cached for display
    title: Mapped[str] = mapped_column(Text)                    # first user message
    messages: Mapped[List] = mapped_column(JSON, default=list)  # [{role, content}]
    message_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_used: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ScrapeRun(Base):
    __tablename__ = "scrape_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    papers_found: Mapped[int] = mapped_column(Integer, default=0)
    papers_new: Mapped[int] = mapped_column(Integer, default=0)
    categories: Mapped[List] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), default="running")
    error: Mapped[Optional[str]] = mapped_column(Text)


class ClusterRun(Base):
    __tablename__ = "cluster_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ran_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    papers_clustered: Mapped[int] = mapped_column(Integer, default=0)
    clusters_found: Mapped[int] = mapped_column(Integer, default=0)
    noise_papers: Mapped[int] = mapped_column(Integer, default=0)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), default="ML Researcher")
    email: Mapped[str] = mapped_column(String(100), default="researcher@papersignal.com")
    role: Mapped[str] = mapped_column(String(100), default="Senior ML Engineer")
    preferences: Mapped[dict] = mapped_column(JSON, default=lambda: {
        "theme": "dark",
        "model_pref": "auto",
        "alert_threshold": 7.0
    })
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class UserActivity(Base):
    __tablename__ = "user_activities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(50), nullable=False)
    action_type: Mapped[str] = mapped_column(String(50), nullable=False)  # "ingest", "analyze", "chat", "index"
    details: Mapped[str] = mapped_column(Text, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


async def init_db():
    """Create all tables. Safe to call on every startup."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)