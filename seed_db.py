"""
Paper2Signal — Database Seeder
Fetches landmark ML papers from ArXiv and seeds them into the DB.

Usage:
  python seed_db.py                         # seed landmarks + embed
  python seed_db.py --landmarks-only        # just insert, no embed
  python seed_db.py --analyze               # also run 4-agent analysis
  python seed_db.py --analyze --limit 20    # analyze first 20 unanalyzed
  python seed_db.py --check                 # just show DB status

Requirements:
  - Backend running on localhost:8000
  - /seed/paper endpoint in app.py (see seed_endpoint.py)
  - pip install arxiv httpx
"""

import asyncio
import argparse
import re
import sys
import time
from typing import Optional
import httpx

BASE = "http://localhost:8000"

# ── 50 Landmark Papers ────────────────────────────────────────────────────────

LANDMARK_PAPERS = [
    # Fine-tuning
    "2106.09685",   # LoRA
    "2305.11206",   # QLoRA
    "2101.00190",   # Prefix-Tuning
    "2104.08691",   # Prompt Tuning (T5 scale)
    "2110.07602",   # Compacter

    # Attention & Efficiency
    "2205.14135",   # FlashAttention
    "2307.08691",   # FlashAttention-2
    "2306.00978",   # GQA
    "2312.00752",   # Mamba
    "2112.05682",   # S4 (structured SSMs)

    # Foundation Models
    "2302.13971",   # LLaMA 1
    "2307.09288",   # Llama 2
    "2310.06825",   # Mistral 7B
    "2401.04088",   # Mixtral
    "2204.05149",   # PaLM
    "2309.10305",   # Phi-1.5
    "2305.10403",   # LIMA

    # Reasoning & Alignment
    "2203.02155",   # InstructGPT / RLHF
    "2212.08073",   # Constitutional AI
    "2305.20050",   # DPO
    "2401.10020",   # SPIN
    "2402.01306",   # ORPO

    # RAG & Retrieval
    "2005.11401",   # RAG
    "2212.10560",   # Self-RAG
    "2310.11511",   # Lost in the Middle
    "2401.15884",   # RAPTOR
    "2312.10997",   # Self-Refine

    # Quantization
    "2208.07339",   # LLM.int8
    "2210.17323",   # GPTQ
    "2305.14314",   # SqueezeLLM
    "2401.14112",   # AQLM

    # Agents
    "2303.11366",   # ReAct
    "2308.00352",   # MetaGPT
    "2309.07864",   # AutoGen

    # Multimodal
    "2304.08485",   # LLaVA
    "2310.03744",   # LLaVA-1.5
    "2305.13048",   # InstructBLIP

    # Diffusion & Generation
    "2112.10752",   # Latent Diffusion / Stable Diffusion
    "2207.12598",   # DALL-E 2

    # Scaling
    "2001.08361",   # Scaling Laws
    "2203.15556",   # Chinchilla
    "2305.13301",   # Sophia optimizer

    # Inference Optimization
    "2211.17192",   # Speculative Decoding
    "2305.05920",   # Medusa
    "2308.04898",   # vLLM / PagedAttention

    # Embeddings
    "2212.03533",   # E5 embeddings
    "2401.00368",   # BGE-M3

    # Evaluation
    "2306.04757",   # LMSYS Chatbot Arena
    "2307.13702",   # LLM-as-Judge

    "1706.03762"
]


def ok(msg):    print(f"  \u2705 {msg}")
def fail(msg):  print(f"  \u274c {msg}")
def warn(msg):  print(f"  \u26a0\ufe0f  {msg}")
def info(msg):  print(f"  \u2139\ufe0f  {msg}")
def section(t): print(f"\n{'─'*60}\n  {t}\n{'─'*60}")
def header(t):  print(f"\n{'='*60}\n  {t}\n{'='*60}")


# ── Fetch paper from ArXiv ────────────────────────────────────────────────────

async def fetch_arxiv_paper(arxiv_id: str, client: httpx.AsyncClient) -> Optional[dict]:
    """Fetch paper metadata from ArXiv. Try library first, fallback to API."""
    clean_id = arxiv_id.split("v")[0]

    try:
        import arxiv as arxiv_lib
        results = list(arxiv_lib.Client().results(
            arxiv_lib.Search(id_list=[clean_id], max_results=1)
        ))
        if results:
            res = results[0]
            gh = re.search(
                r'https?://github\.com/[A-Za-z0-9_.\-]+/[A-Za-z0-9_.\-]+',
                res.summary + (getattr(res, "comment", "") or "")
            )
            return {
                "id":           clean_id,
                "title":        res.title.strip().replace("\n", " "),
                "abstract":     res.summary.strip().replace("\n", " "),
                "authors":      [a.name for a in res.authors[:10]],
                "categories":   [str(c) for c in res.categories],
                "arxiv_url":    res.entry_id,
                "pdf_url":      res.pdf_url,
                "github_url":   gh.group(0).rstrip(".,)") if gh else None,
                "published_at": res.published.isoformat() if res.published else None,
                "updated_at":   res.updated.isoformat() if res.updated else None,
            }
    except ImportError:
        pass
    except Exception:
        pass

    # ArXiv API fallback
    try:
        url  = f"http://export.arxiv.org/api/query?id_list={clean_id}&max_results=1"
        resp = await client.get(url, timeout=30.0)
        text = resp.text
        title_m = re.search(r'<entry>.*?<title>(.*?)</title>', text, re.DOTALL)
        abs_m   = re.search(r'<summary>(.*?)</summary>', text, re.DOTALL)
        if title_m and abs_m:
            title    = title_m.group(1).strip().replace('\n', ' ')
            abstract = abs_m.group(1).strip().replace('\n', ' ')
            if len(title) > 5 and "ArXiv" not in title:
                return {
                    "id":        clean_id,
                    "title":     title,
                    "abstract":  abstract,
                    "arxiv_url": f"https://arxiv.org/abs/{clean_id}",
                }
    except Exception:
        pass

    return None


# ── Check endpoint availability ───────────────────────────────────────────────

async def check_seed_endpoint(client: httpx.AsyncClient) -> bool:
    """Returns True if /seed/paper is available."""
    try:
        # 422 = endpoint exists but bad input
        # 404 = endpoint doesn't exist
        # 200 = worked (shouldn't happen with empty body)
        r = await client.post(f"{BASE}/seed/paper", json={}, timeout=5.0)
        if r.status_code in (200, 409, 422):
            return True
        if r.status_code == 404:
            return False
        return True   # any other status = endpoint exists
    except Exception:
        return False


# ── Seed landmarks ────────────────────────────────────────────────────────────

async def seed_landmarks(client: httpx.AsyncClient):
    section(f"Seeding {len(LANDMARK_PAPERS)} Landmark Papers")

    try:
        import arxiv  # noqa: F401
        print("  Using arxiv library \u2713")
    except ImportError:
        warn("arxiv not installed — using API fallback (slower)")
        print("  Run: pip install arxiv")

    added   = 0
    skipped = 0
    failed  = 0

    for i, arxiv_id in enumerate(LANDMARK_PAPERS, 1):
        print(f"\n  [{i:02d}/{len(LANDMARK_PAPERS)}] {arxiv_id}", end="", flush=True)

        # Already in DB?
        try:
            r = await client.get(f"{BASE}/papers/{arxiv_id}", timeout=5.0)
            if r.status_code == 200:
                print(" — already in DB")
                skipped += 1
                continue
        except Exception:
            pass

        # Fetch from ArXiv
        paper_data = await fetch_arxiv_paper(arxiv_id, client)
        if not paper_data:
            print(" — ArXiv fetch failed")
            failed += 1
            await asyncio.sleep(1.0)
            continue

        # Insert via seed endpoint
        try:
            r = await client.post(f"{BASE}/seed/paper", json=paper_data, timeout=15.0)
            if r.status_code == 200:
                status = r.json().get("status", "?")
                if status == "exists":
                    print(" — already exists")
                    skipped += 1
                else:
                    print(f" — \u2705 {paper_data['title'][:50]}")
                    added += 1
            else:
                print(f" — HTTP {r.status_code}: {r.text[:60]}")
                failed += 1
        except Exception as e:
            print(f" — error: {e}")
            failed += 1

        await asyncio.sleep(1.0)   # be nice to ArXiv

    print(f"\n  Done: {added} added, {skipped} skipped, {failed} failed")
    return added, skipped, failed


# ── Embed new papers ──────────────────────────────────────────────────────────

async def embed_papers(client: httpx.AsyncClient):
    """
    Trigger embedding for new papers only.
    Unlike /pipeline/run (which scrapes + embeds + clusters + velocity),
    this just does embedding — we wait for it to complete by polling.
    """
    section("Embedding New Papers into ChromaDB")

    r      = await client.get(f"{BASE}/health", timeout=5.0)
    before = r.json()["analyzed_count"]  # noqa: F841 — kept for intent clarity

    r = await client.post(f"{BASE}/pipeline/run", timeout=10.0)
    if r.status_code != 200:
        fail(f"Pipeline trigger failed: {r.status_code}")
        return

    ok("Embed pipeline triggered on server (scrape \u2192 embed \u2192 cluster)")
    print("  Waiting for embedding to complete...")

    prev_count    = -1
    stable_rounds = 0
    for _ in range(30):
        await asyncio.sleep(3)
        try:
            r       = await client.get(f"{BASE}/health", timeout=5.0)
            data    = r.json()
            current = data["papers_count"]
            print(f"  ... {current} papers embedded", end="\r")
            if current == prev_count:
                stable_rounds += 1
                if stable_rounds >= 3:
                    break
            else:
                stable_rounds = 0
            prev_count = current
        except Exception:
            pass

    r    = await client.get(f"{BASE}/health", timeout=5.0)
    data = r.json()
    print(f"\n  Papers in DB:       {data['papers_count']}")
    print(f"  Papers analyzed:    {data['analyzed_count']}")


# ── Analyze papers ────────────────────────────────────────────────────────────

async def analyze_papers(client: httpx.AsyncClient, limit: int, concurrency: int = 2):
    section(f"Running 4-Agent Analysis (limit={limit}, concurrency={concurrency})")

    r            = await client.get(f"{BASE}/papers?limit=300&analyzed_only=false", timeout=15.0)
    all_papers   = r.json()
    r2           = await client.get(f"{BASE}/analyzed?limit=300", timeout=15.0)
    analyzed_ids = {p["id"] for p in r2.json()}
    unanalyzed   = [p for p in all_papers if p["id"] not in analyzed_ids][:limit]

    if not unanalyzed:
        ok("All papers already analyzed!")
        return

    print(f"  {len(unanalyzed)} papers to analyze...")

    sem     = asyncio.Semaphore(concurrency)
    results = {"ok": 0, "fail": 0}

    async def analyze_one(paper, idx):
        async with sem:
            pid   = paper["id"]
            title = paper.get("title", "?")[:50]
            print(f"\n  [{idx}/{len(unanalyzed)}] {title}...")
            t = time.time()
            try:
                resp    = await client.post(f"{BASE}/papers/{pid}/analyze", timeout=150.0)
                elapsed = time.time() - t
                if resp.status_code == 200:
                    d = resp.json()
                    ok(
                        f"{elapsed:.0f}s | Score: {d.get('overall_score', '?')} "
                        f"| Action: {d.get('action', '?')} "
                        f"| Hype: {d.get('hype_score', '?')}"
                    )
                    results["ok"] += 1
                else:
                    fail(f"HTTP {resp.status_code}: {resp.text[:60]}")
                    results["fail"] += 1
            except Exception as e:
                fail(f"Error: {e}")
                results["fail"] += 1

    tasks = [analyze_one(p, i + 1) for i, p in enumerate(unanalyzed)]
    await asyncio.gather(*tasks)

    print(f"\n  Analysis: {results['ok']} ok, {results['fail']} failed")


# ── Main ──────────────────────────────────────────────────────────────────────

async def main():
    global BASE  # must be first — before any reference to BASE

    parser = argparse.ArgumentParser(description="Paper2Signal DB Seeder")
    parser.add_argument("--landmarks-only", action="store_true", help="Seed only, skip embed pipeline")
    parser.add_argument("--check",          action="store_true", help="Just print DB status")
    parser.add_argument("--analyze",        action="store_true", help="Run analysis after seeding")
    parser.add_argument("--limit",          type=int, default=30, help="Max papers to analyze")
    parser.add_argument("--concurrency",    type=int, default=2,  help="Analysis concurrency")
    parser.add_argument("--base",           default=BASE,         help="Backend base URL")
    args = parser.parse_args()

    BASE = args.base

    header("Paper2Signal — Database Seeder")

    async with httpx.AsyncClient(timeout=30.0) as client:

        # Health check
        try:
            r = await client.get(f"{BASE}/health", timeout=5.0)
            r.raise_for_status()
            data = r.json()
            ok(
                f"Backend up | Papers: {data['papers_count']} "
                f"| Analyzed: {data['analyzed_count']} "
                f"| Indexed: {data['deep_indexed_count']}"
            )
        except Exception as e:
            fail(f"Backend not reachable at {BASE}: {e}")
            print("\n  Start your backend first: python main.py")
            sys.exit(1)

        if args.check:
            return

        # Check /seed/paper endpoint
        endpoint_ok = await check_seed_endpoint(client)
        if not endpoint_ok:
            print("\n" + "=" * 60)
            fail("/seed/paper endpoint missing from app.py")
            print("\n  Add the contents of seed_endpoint.py to app.py")
            print("  (paste after the DeepChatRequest model)")
            print("  Then restart the backend and rerun this script.")
            print("=" * 60)
            sys.exit(1)
        else:
            ok("/seed/paper endpoint found")

        # Seed
        added, skipped, failed_count = await seed_landmarks(client)

        if added == 0 and skipped == len(LANDMARK_PAPERS):
            ok("All landmark papers already in DB — nothing to do")
        elif failed_count > 0:
            warn(f"{failed_count} papers failed to fetch. Re-run to retry.")

        # Embed
        if not args.landmarks_only and added > 0:
            await embed_papers(client)
        elif args.landmarks_only:
            info("Skipping embed (--landmarks-only). Run without flag to embed.")

        # Analyze
        if args.analyze:
            await analyze_papers(client, args.limit, args.concurrency)
        elif added > 0:
            r    = await client.get(f"{BASE}/health", timeout=5.0)
            data = r.json()
            unanalyzed = data["papers_count"] - data["analyzed_count"]
            if unanalyzed > 0:
                info(f"{unanalyzed} papers need analysis. Run with --analyze to process them.")
                print(f"  python seed_db.py --analyze --limit {min(unanalyzed, 50)}")

        # Final summary
        r    = await client.get(f"{BASE}/health", timeout=5.0)
        data = r.json()
        header("Final Status")
        ok(f"Papers in DB:    {data['papers_count']}")
        ok(f"Analyzed:        {data['analyzed_count']}")
        ok(f"PDF Indexed:     {data['deep_indexed_count']}")

        if data["analyzed_count"] == 0:
            print("\n  Next step: analyze papers")
            print("  python seed_db.py --analyze --limit 30 --concurrency 2")


if __name__ == "__main__":
    asyncio.run(main())