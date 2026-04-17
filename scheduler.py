"""
PaperSignal — Scheduler
Runs the full pipeline on a configurable interval.
Uses APScheduler with asyncio backend.
Poll interval comes from settings.ARXIV_POLL_HOURS.
"""

import asyncio
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from config.settings import settings
from ingestion.scraper import run_scrape
from ml.embeddings import embed_pending_papers
from ml.clustering import run_clustering
from ml.velocity import score_papers

logger = logging.getLogger(__name__)


async def pipeline_job():
    """Single scheduled job that runs all pipeline stages in sequence."""
    logger.info("[Scheduler] Pipeline job starting...")
    try:
        run = await run_scrape()
        logger.info(f"[Scheduler] Scrape: {run.papers_new} new papers")

        embedded = await embed_pending_papers()
        logger.info(f"[Scheduler] Embedded: {embedded} papers")

        await run_clustering()
        logger.info("[Scheduler] Clustering complete")

        scored = await score_papers()
        logger.info(f"[Scheduler] Velocity scored: {scored} papers")

    except Exception as e:
        logger.error(f"[Scheduler] Pipeline job failed: {e}", exc_info=True)


def create_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        pipeline_job,
        trigger=IntervalTrigger(hours=settings.ARXIV_POLL_HOURS),
        id="pipeline",
        name="Full PaperSignal pipeline",
        replace_existing=True,
        misfire_grace_time=600,   # 10 min grace if server was down
    )
    return scheduler


async def main():
    """Run scheduler as standalone process."""
    from ingestion.models import init_db
    await init_db()

    scheduler = create_scheduler()
    scheduler.start()
    logger.info(f"[Scheduler] Started. Pipeline runs every {settings.ARXIV_POLL_HOURS}h")

    # Run once immediately on startup
    await pipeline_job()

    try:
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
        logger.info("[Scheduler] Stopped.")


if __name__ == "__main__":
    logging.basicConfig(
        level=getattr(logging, settings.LOG_LEVEL),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )
    asyncio.run(main())