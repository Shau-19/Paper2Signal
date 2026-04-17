"""
PaperSignal — Velocity Scorer
Enriches papers that have GitHub links with real star counts.
Computes a composite velocity score from star velocity + citation proxy.
All weights from settings.
"""

import logging
import httpx
from datetime import datetime, timedelta
from typing import Optional, List

import asyncio


from sqlalchemy import select, and_

from ingestion.models import Paper, get_db
from config.settings import settings

logger = logging.getLogger(__name__)

SEMANTIC_SCHOLAR_URL = "https://api.semanticscholar.org/graph/v1/paper/arXiv:{arxiv_id}"
GITHUB_API_URL = "https://api.github.com/repos/{owner}/{repo}"


def _parse_github_repo(url: str) -> Optional[tuple[str, str]]:
    """Extract (owner, repo) from a GitHub URL."""
    try:
        parts = url.rstrip("/").split("github.com/")[-1].split("/")
        if len(parts) >= 2:
            return parts[0], parts[1]
    except Exception:
        pass
    return None


async def _fetch_github_stars(owner: str, repo: str, client: httpx.AsyncClient) -> Optional[int]:
    """Fetch current star count for a GitHub repo."""
    headers = {"Accept": "application/vnd.github+json"}
    if settings.GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {settings.GITHUB_TOKEN}"

    try:
        resp = await client.get(
            GITHUB_API_URL.format(owner=owner, repo=repo),
            headers=headers,
            timeout=10.0,
        )
        if resp.status_code == 200:
            return resp.json().get("stargazers_count", 0)
        logger.debug(f"[Velocity] GitHub {owner}/{repo} returned {resp.status_code}")
    except Exception as e:
        logger.debug(f"[Velocity] GitHub fetch failed for {owner}/{repo}: {e}")
    return None


async def _fetch_citation_count(arxiv_id: str, client: httpx.AsyncClient) -> Optional[int]:
    """Fetch citation count from Semantic Scholar (free, no key needed)."""
    try:
        resp = await client.get(
            SEMANTIC_SCHOLAR_URL.format(arxiv_id=arxiv_id),
            params={"fields": "citationCount"},
            timeout=10.0,
        )
        if resp.status_code == 200:
            return resp.json().get("citationCount", 0)
    except Exception as e:
        logger.debug(f"[Velocity] SemanticScholar fetch failed for {arxiv_id}: {e}")
    return None


def _compute_velocity(
    stars: Optional[int],
    prev_stars: Optional[int],
    citations: Optional[int],
    prev_citations: Optional[int],
    days_old: float,
) -> float:
    """
    Composite velocity score 0–100.
    Weighted sum of normalised star growth + citation growth.
    """
    if days_old <= 0:
        days_old = 1

    star_velocity = 0.0
    if stars is not None:
        delta = stars - (prev_stars or 0)
        # Normalise: 100 stars/day = score 1.0
        star_velocity = min(delta / max(days_old, 1) / 100, 1.0)

    citation_velocity = 0.0
    if citations is not None:
        delta = citations - (prev_citations or 0)
        # Normalise: 10 citations/day = score 1.0
        citation_velocity = min(delta / max(days_old, 1) / 10, 1.0)

    score = (
        settings.VELOCITY_STAR_WEIGHT * star_velocity
        + settings.VELOCITY_CITATION_WEIGHT * citation_velocity
    ) * 100

    return round(min(score, 100.0), 2)


async def score_papers() -> int:
    """
    Fetch velocity signals for all papers with GitHub links.
    Falls back to citation-only for papers without GitHub.
    Returns number of papers scored.
    """
    async with get_db() as db:
        result = await db.execute(select(Paper))
        papers: List[Paper] = result.scalars().all()

    if not papers:
        logger.info("[Velocity] No papers to score")
        return 0

    now = datetime.utcnow()
    scored = 0

    async with httpx.AsyncClient() as client:
        for paper in papers:
            days_old = max((now - paper.published_at.replace(tzinfo=None)).days, 1)

            stars = None
            if paper.github_url:
                parsed = _parse_github_repo(paper.github_url)
                if parsed:
                    owner, repo = parsed
                    stars = await _fetch_github_stars(owner, repo, client)

            citations = await _fetch_citation_count(paper.id, client)
            await asyncio.sleep(1.5) 

            velocity = _compute_velocity(
                stars=stars,
                prev_stars=paper.github_stars,
                citations=citations,
                prev_citations=paper.citation_count,
                days_old=settings.VELOCITY_WINDOW_DAYS,
            )

            async with get_db() as db:
                p = await db.get(Paper, paper.id)
                if p:
                    p.github_stars_delta = (stars or 0) - (p.github_stars or 0) if stars else None
                    p.citation_delta = (citations or 0) - (p.citation_count or 0) if citations else None
                    p.github_stars = stars if stars is not None else p.github_stars
                    p.citation_count = citations if citations is not None else p.citation_count
                    p.velocity_score = velocity
                    scored += 1

    logger.info(f"[Velocity] Scored {scored}/{len(papers)} papers")
    return scored