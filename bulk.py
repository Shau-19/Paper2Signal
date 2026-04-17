import asyncio
import httpx
import argparse
import time

BASE = "http://localhost:8000"


# ── Fetch papers ─────────────────────────────────────────────

async def get_unanalyzed_papers(client, limit=20, github_only=False):
    url = f"{BASE}/papers?limit=100&analyzed_only=false"
    r = await client.get(url, timeout=30.0)
    papers = r.json()

    unanalyzed = [p for p in papers if not p.get("is_analyzed")]

    if github_only:
        unanalyzed = [p for p in unanalyzed if p.get("github_url")]
        print(f"Filtered to {len(unanalyzed)} GitHub papers")

    return unanalyzed[:limit]


# ── Analyze one paper ───────────────────────────────────────

async def analyze_paper(client, paper, idx, total):
    title = paper.get("title", "")
    paper_id = paper.get("id")

    print(f"\n[{idx}/{total}] {title[:60]}...")
    print(f"         ID: {paper_id}")

    start = time.time()

    try:
        r = await client.post(
            f"{BASE}/papers/{paper_id}/analyze",
            timeout=150.0
        )

        elapsed = time.time() - start

        if r.status_code != 200:
            print(f"  ❌ HTTP {r.status_code}")
            return None

        data = r.json()

        score = data.get("overall_score", 0)
        hype = data.get("hype_score")
        action = data.get("action", "?")

        hype_str = f"{hype}/10" if hype is not None else "N/A"

        print(f"  ✅ Score: {score}/10 | Hype: {hype_str} | Action: {action} | {elapsed:.1f}s")

        return data

    except Exception as e:
        print(f"  ❌ Error: {e}")
        return None


# ── Parallel runner ─────────────────────────────────────────

async def run_parallel(papers, concurrency=3):
    async with httpx.AsyncClient(timeout=150.0) as client:
        sem = asyncio.Semaphore(concurrency)

        async def limited_task(paper, idx):
            async with sem:
                return await analyze_paper(client, paper, idx, len(papers))

        tasks = [
            limited_task(paper, i + 1)
            for i, paper in enumerate(papers)
        ]

        results = await asyncio.gather(*tasks)
        return [r for r in results if r is not None]


# ── Gems checker ────────────────────────────────────────────

async def get_hidden_gems(client):
    r = await client.get(f"{BASE}/hidden-gems", timeout=30.0)
    return r.json()


# ── Main ───────────────────────────────────────────────────

async def main(limit, github_only, concurrency):
    print("\n🚀 Paper2Signal — Parallel Analyzer")
    print("=" * 55)
    print(f"Target: {limit} papers | Concurrency: {concurrency}")
    print("=" * 55)

    async with httpx.AsyncClient(timeout=30.0) as client:

        # Health
        health = (await client.get(f"{BASE}/health")).json()
        print(f"\nCurrent: {health['papers_count']} papers | {health['analyzed_count']} analyzed")

        gems_before = await get_hidden_gems(client)
        print(f"Hidden gems before: {len(gems_before)}")

        # Fetch papers
        papers = await get_unanalyzed_papers(client, limit, github_only)

        if not papers:
            print("\nℹ️ All papers already analyzed!")
            return

        print(f"\nAnalyzing {len(papers)} papers in parallel...\n")

        start_time = time.time()

        results = await run_parallel(papers, concurrency)

        total_time = time.time() - start_time

        # ── Summary ──
        print("\n" + "=" * 55)
        print(f"✅ Completed: {len(results)}/{len(papers)} papers")
        print(f"⏱️ Total time: {total_time:.1f}s")
        print(f"⚡ Avg per paper: {total_time / len(results):.1f}s")

        # Gems
        gems = [
            r for r in results
            if r.get("overall_score", 0) >= 7.0 and
               r.get("hype_score") is not None and
               r.get("hype_score") <= 4.0
        ]

        print(f"\n💎 Gems found: {len(gems)}")

        for g in gems:
            print(f"  • {g['title'][:60]}")
            print(f"    Score: {g['overall_score']} | Hype: {g['hype_score']}")

        print("=" * 55)


# ── CLI ────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--github-only", action="store_true")
    parser.add_argument("--concurrency", type=int, default=3)

    args = parser.parse_args()

    asyncio.run(main(args.limit, args.github_only, args.concurrency))