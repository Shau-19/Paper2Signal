"""
PaperSignal — ArXiv Scraper
Fetches papers from configured categories, deduplicates by arxiv ID,
extracts GitHub links from abstracts/comments.
All tunables come from settings.
"""

import re
import logging
import arxiv
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy import select
from ingestion.models import Paper, ScrapeRun, get_db
from config.settings import settings

logger = logging.getLogger(__name__)

# Regex to find GitHub URLs in text
GITHUB_RE = re.compile(r'https?://github\.com/[A-Za-z0-9_.\-]+/[A-Za-z0-9_.\-]+', re.IGNORECASE)


def _extract_github(text: str) -> Optional[str]:
    """Return first GitHub repo URL found in text, else None."""
    match = GITHUB_RE.search(text or "")
    return match.group(0).rstrip('.,)') if match else None


def _build_arxiv_client() -> arxiv.Client:
    return arxiv.Client(
        page_size=min(settings.ARXIV_MAX_RESULTS, 100),
        delay_seconds=5.0,
        num_retries=3,
    )


def _build_search(categories: List[str], days_back: int) -> arxiv.Search:
    """Build arxiv Search object for given categories and time window."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)
    # arxiv query: combine categories with OR
    query = " OR ".join(f"cat:{c}" for c in categories)
    return arxiv.Search(
        query=query,
        max_results=settings.ARXIV_MAX_RESULTS,
        sort_by=arxiv.SortCriterion.SubmittedDate,
        sort_order=arxiv.SortOrder.Descending,
    )


def _result_to_paper(result: arxiv.Result) -> Paper:
    """Convert an arxiv Result into a Paper ORM object."""
    arxiv_id = result.entry_id.split("/")[-1]   # e.g. "2401.12345v1"
    base_id = arxiv_id.split("v")[0]            # strip version → "2401.12345"

    # Try to find GitHub link in abstract or comment
    github = (
        _extract_github(result.summary)
        or _extract_github(getattr(result, "comment", None) or "")
    )

    return Paper(
        id=base_id,
        title=result.title.strip().replace("\n", " "),
        abstract=result.summary.strip().replace("\n", " "),
        authors=[a.name for a in result.authors],
        categories=[str(c) for c in result.categories],
        published_at=result.published,
        updated_at=result.updated,
        arxiv_url=result.entry_id,
        pdf_url=result.pdf_url,
        github_url=github,
    )


async def run_scrape(days_back: Optional[int] = None) -> ScrapeRun:
    """
    Main scrape entrypoint. Fetches papers, deduplicates, persists new ones.
    Returns the completed ScrapeRun audit record.
    """
    days = days_back or settings.ARXIV_DAYS_BACK
    categories = settings.ARXIV_CATEGORIES

    async with get_db() as db:
        # Create audit record
        run = ScrapeRun(categories=categories, status="running")
        db.add(run)
        await db.flush()   # get run.id

        try:
            client = _build_arxiv_client()
            search = _build_search(categories, days)

            results = list(client.results(search))
            run.papers_found = len(results)
            logger.info(f"[Scraper] Fetched {len(results)} results from arxiv")

            # Fetch existing IDs to skip dupes — single query
            all_ids = [r.entry_id.split("/")[-1].split("v")[0] for r in results]
            existing = set(
                row[0] for row in
                (await db.execute(select(Paper.id).where(Paper.id.in_(all_ids)))).all()
            )

            new_papers = []
            for result in results:
                paper = _result_to_paper(result)
                if paper.id not in existing:
                    new_papers.append(paper)

            if new_papers:
                db.add_all(new_papers)

            run.papers_new = len(new_papers)
            run.finished_at = datetime.utcnow()
            run.status = "done"

            logger.info(
                f"[Scraper] Done — {run.papers_found} fetched, "
                f"{run.papers_new} new, {len(existing)} already known"
            )

        except Exception as e:
            run.status = "failed"
            run.error = str(e)
            run.finished_at = datetime.utcnow()
            logger.error(f"[Scraper] Failed: {e}", exc_info=True)
            raise

        return run