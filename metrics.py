"""
Paper2Signal — Model Metrics Evaluation Suite
Tests: Hype Model Accuracy, RAG Retrieval Quality, Pipeline Consistency, Scoring Distribution

Run: python eval_metrics.py
Server must be on localhost:8000, Sentinel on localhost:8001
"""

import asyncio
import httpx
import json
import time
import sys
import re
import numpy as np
from collections import Counter

sys.path.insert(0, ".")

BASE      = "http://localhost:8000"
SENTINEL  = "http://localhost:8001"

# ──────────────────────────────────────────────────────────────
# GROUND TRUTH — manually labeled test set
# These are papers with known expected outcomes
# ──────────────────────────────────────────────────────────────

HYPE_GROUND_TRUTH = [
    # (abstract, expected_hype_range, label)
    (
        "FlashAttention-2 achieves 2x speedup over FlashAttention with 73% GPU FLOPS utilization. "
        "Code released at github.com/Dao-AILab/flash-attention. Drop-in replacement for standard attention.",
        (7, 10), "HIGH - infra+code"
    ),
    (
        "LoRA reduces trainable parameters by 10000x and GPU memory by 3x with no inference latency. "
        "Matches GPT-3 fine-tuning quality. Code at github.com/microsoft/LoRA.",
        (7, 10), "HIGH - efficiency+code"
    ),
    (
        "We prove convergence bounds for SGD under non-convex losses, improving prior bounds by "
        "a logarithmic factor under standard assumptions. No code released.",
        (1, 4), "LOW - theory only"
    ),
    (
        "Theoretical analysis of neural tangent kernel in infinite-width networks. "
        "We derive closed-form expressions for gradient flow dynamics. No experiments.",
        (1, 3), "LOW - pure theory"
    ),
    (
        "We introduce a new regularization technique reducing overfitting by 3% on ImageNet. "
        "Code available at github.com/example/reg. Plug-and-play with existing pipelines.",
        (5, 7), "MED - marginal improvement"
    ),
    (
        "New benchmark dataset for table question answering with 50k examples. "
        "Evaluation suite released. Moderate improvements over baselines.",
        (4, 7), "MED - benchmark"
    ),
    (
        "Quantized LLM inference reduces memory by 4x and increases throughput 3x on consumer GPUs. "
        "Library released at github.com/example/quant. Works with Llama, Mistral, Qwen.",
        (8, 10), "HIGH - systems+code"
    ),
    (
        "Survey of transformer architectures in NLP. We review 200 papers and categorize approaches. "
        "No novel contribution. No code.",
        (1, 4), "LOW - survey"
    ),
    (
        "We propose a novel attention variant with theoretical improvements. "
        "Experiments on 3 tasks show marginal gains. No code released.",
        (3, 6), "MED - no code"
    ),
    (
        "Speculative decoding achieves 3x inference speedup with no quality degradation. "
        "Code released. Works with any autoregressive model. Deployed at scale.",
        (7, 10), "HIGH - deployed+code"
    ),
]

RAG_TEST_QUERIES = [
    # (query, expected_topic_keywords)
    ("How to reduce LLM inference memory?",     ["memory", "quantiz", "efficient", "compress", "attention"]),
    ("Autonomous driving perception methods",    ["driving", "perception", "detection", "sensor", "vehicle"]),
    ("Knowledge distillation techniques",        ["distill", "student", "teacher", "compress", "knowledge"]),
    ("Diffusion model image generation",         ["diffusion", "image", "generation", "noise", "denois"]),
    ("Reinforcement learning from human feedback", ["rlhf", "reward", "human", "feedback", "alignment", "preference"]),
]

SCORING_CONSISTENCY_PAIRS = [
    # Same paper scored twice — scores should be within 1.0 of each other
    {
        "id":    "test_consist_1",
        "title": "LoRA: Low-Rank Adaptation of Large Language Models",
        "abstract": (
            "We propose LoRA which freezes pretrained weights and injects trainable rank "
            "decomposition matrices. Reduces trainable parameters by 10000x. Code at github.com/microsoft/LoRA."
        ),
        "github_url": "https://github.com/microsoft/LoRA",
    },
    {
        "id":    "test_consist_2",
        "title": "Attention Is All You Need",
        "abstract": (
            "We propose the Transformer, based solely on attention mechanisms. "
            "Achieves 28.4 BLEU on WMT translation. Code available. "
            "Widely adopted in production NLP systems."
        ),
        "github_url": "https://github.com/tensorflow/tensor2tensor",
    },
]


# ── Helpers ───────────────────────────────────────────────────

def section(title):
    print(f"\n{'═'*60}")
    print(f"  {title}")
    print(f"{'═'*60}")

def ok(msg):   print(f"  ✅ {msg}")
def fail(msg): print(f"  ❌ {msg}")
def warn(msg): print(f"  ⚠️  {msg}")
def info(msg): print(f"  ℹ️  {msg}")


# ──────────────────────────────────────────────────────────────
# METRIC 1: Hype Model Accuracy
# ──────────────────────────────────────────────────────────────

async def eval_hype_model():
    section("METRIC 1: Hype Model Accuracy (Sentinel)")
    print("  Testing against manually labeled ground truth...\n")

    correct   = 0
    total     = len(HYPE_GROUND_TRUTH)
    scores    = []
    errors    = []

    async with httpx.AsyncClient(timeout=60.0) as client:
        # Check Sentinel is alive
        try:
            h = await client.get(f"{SENTINEL}/health")
            info(f"Sentinel health: {h.json()}")
        except Exception:
            fail("Sentinel not running on port 8001 — run: python hype_model.py")
            return None

        for abstract, (lo, hi), label in HYPE_GROUND_TRUTH:
            try:
                r = await client.post(f"{SENTINEL}/predict", json={"abstract": abstract})
                data = r.json()
                score  = float(data.get("hype_score", -1))
                reason = data.get("reason", "")
                scores.append(score)

                in_range = lo <= score <= hi
                if in_range:
                    correct += 1
                    ok(f"{label}: {score}/10 ✅ (expected {lo}–{hi})")
                else:
                    fail(f"{label}: {score}/10 ❌ (expected {lo}–{hi})")
                    errors.append((label, score, lo, hi))

                # Check reason is grounded not generic
                generic_patterns = ["llms, agents, multimodal, diffusion", "large language model"]
                is_generic = any(p in reason.lower() for p in generic_patterns)
                if is_generic:
                    warn(f"  Reason is generic: '{reason[:60]}'")

            except Exception as e:
                fail(f"{label}: Error — {e}")

    accuracy = correct / total * 100
    avg_score = np.mean(scores) if scores else 0
    std_score = np.std(scores) if scores else 0

    print(f"\n  {'─'*40}")
    print(f"  Accuracy:     {accuracy:.0f}% ({correct}/{total} correct)")
    print(f"  Avg score:    {avg_score:.2f}/10")
    print(f"  Score StdDev: {std_score:.2f} (higher = better discrimination)")
    print(f"  Score range:  {min(scores):.1f}–{max(scores):.1f}")

    # Distribution check
    low_count  = sum(1 for s in scores if s <= 4)
    med_count  = sum(1 for s in scores if 4 < s <= 7)
    high_count = sum(1 for s in scores if s > 7)
    print(f"  Distribution: LOW={low_count} MED={med_count} HIGH={high_count}")

    if accuracy >= 70:
        ok(f"Hype model accuracy: {accuracy:.0f}% — acceptable for portfolio")
    else:
        warn(f"Hype model accuracy: {accuracy:.0f}% — below threshold, model needs retraining")

    return {
        "accuracy":    accuracy,
        "avg_score":   avg_score,
        "std_score":   std_score,
        "score_range": (min(scores), max(scores)),
        "distribution": {"low": low_count, "med": med_count, "high": high_count},
        "errors":      errors,
    }


# ──────────────────────────────────────────────────────────────
# METRIC 2: RAG Retrieval Quality (Precision@K)
# ──────────────────────────────────────────────────────────────

async def eval_rag_quality():
    section("METRIC 2: RAG Retrieval Quality (Precision@K)")
    print("  Testing semantic search relevance against keyword overlap...\n")

    precisions = []

    async with httpx.AsyncClient(timeout=30.0) as client:
        for query, keywords in RAG_TEST_QUERIES:
            try:
                r = await client.get(f"{BASE}/search", params={"q": query, "limit": 5})
                results = r.json()

                if not results:
                    warn(f"No results for: '{query}'")
                    continue

                # Check how many top-5 results have keyword overlap
                relevant = 0
                for res in results[:5]:
                    title    = res["metadata"].get("title", "").lower()
                    abstract = res["metadata"].get("summary", "").lower()
                    text     = title + " " + abstract

                    if any(k in text for k in keywords):
                        relevant += 1

                precision = relevant / min(5, len(results))
                precisions.append(precision)

                status = "✅" if precision >= 0.4 else "⚠️ "
                print(f"  {status} P@5={precision:.2f} | '{query[:45]}'")
                print(f"      Top result: {results[0]['metadata']['title'][:55]}")

            except Exception as e:
                fail(f"Query failed: '{query}' — {e}")

    mean_precision = np.mean(precisions) if precisions else 0

    print(f"\n  {'─'*40}")
    print(f"  Mean Precision@5: {mean_precision:.2f}")
    print(f"  Queries tested:   {len(precisions)}")

    if mean_precision >= 0.5:
        ok(f"RAG precision: {mean_precision:.2f} — good retrieval quality")
    elif mean_precision >= 0.3:
        warn(f"RAG precision: {mean_precision:.2f} — acceptable but low paper count hurts recall")
    else:
        fail(f"RAG precision: {mean_precision:.2f} — embeddings may be misconfigured")

    # Also test global chat grounding
    print("\n  Testing global chat answer grounding...")
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(f"{BASE}/chat", json={
            "message": "What papers reduce transformer memory usage?"
        })
        data = r.json()
        answer     = data.get("answer", "")
        citations  = data.get("citations", [])
        n_sources  = data.get("n_sources", 0)

        ok(f"Answer length: {len(answer)} chars")
        ok(f"Citations returned: {len(citations)} sources")

        # Check if answer references actual paper titles
        if citations:
            first_title = citations[0].get("title", "").lower()[:30]
            if first_title and first_title in answer.lower():
                ok("Answer references cited papers — grounded ✅")
            else:
                warn("Answer may not reference cited papers directly")

    return {
        "mean_precision_at_5": mean_precision,
        "queries_tested":      len(precisions),
        "all_precisions":      precisions,
    }


# ──────────────────────────────────────────────────────────────
# METRIC 3: Scoring Consistency (Idempotency)
# ──────────────────────────────────────────────────────────────

async def eval_scoring_consistency():
    section("METRIC 3: Scoring Consistency (Same Paper × 2 Runs)")
    print("  Scoring same papers twice — delta should be < 1.0...\n")

    from agents.pipeline import analyze_paper
    from ingestion.models import Paper
    from datetime import datetime

    results = []

    for paper_data in SCORING_CONSISTENCY_PAIRS:
        paper = Paper(
            id=paper_data["id"],
            title=paper_data["title"],
            abstract=paper_data["abstract"],
            github_url=paper_data.get("github_url"),
            velocity_score=0.5,
            arxiv_url=f"https://arxiv.org/abs/{paper_data['id']}",
            authors=[],
            categories=[],
            published_at=datetime.utcnow(),
        )

        print(f"  Paper: {paper_data['title'][:55]}...")

        scores_runs = []
        for run in range(2):
            try:
                t = time.time()
                result = await analyze_paper(paper)
                elapsed = time.time() - t
                score = result.get("overall_score")
                action = result.get("action")
                scores_runs.append(score)
                info(f"  Run {run+1}: score={score} action={action} ({elapsed:.1f}s)")
            except Exception as e:
                fail(f"  Run {run+1} failed: {e}")
                scores_runs.append(None)

            await asyncio.sleep(2)  # small delay between runs

        if len(scores_runs) == 2 and all(s is not None for s in scores_runs):
            delta = abs(scores_runs[0] - scores_runs[1])
            results.append(delta)
            if delta <= 1.0:
                ok(f"Delta: {delta:.1f} ≤ 1.0 — consistent ✅")
            elif delta <= 2.0:
                warn(f"Delta: {delta:.1f} — moderate variance (LLM temperature)")
            else:
                fail(f"Delta: {delta:.1f} — high variance, scoring unreliable")
        print()

    avg_delta = np.mean(results) if results else 0
    print(f"  {'─'*40}")
    print(f"  Avg score delta across runs: {avg_delta:.2f}")
    if avg_delta <= 1.0:
        ok(f"Scoring is consistent (avg delta={avg_delta:.2f})")
    else:
        warn(f"Scoring has variance (avg delta={avg_delta:.2f}) — expected with LLM temperature")

    return {"avg_delta": avg_delta, "all_deltas": results}


# ──────────────────────────────────────────────────────────────
# METRIC 4: Score Distribution Analysis
# ──────────────────────────────────────────────────────────────

async def eval_score_distribution():
    section("METRIC 4: Score Distribution (Live DB)")
    print("  Analyzing score distribution across analyzed papers...\n")

    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(f"{BASE}/analyzed?limit=200")
        papers = r.json()

    if not papers:
        fail("No analyzed papers — run bulk.py first")
        return None

    scores    = [p["overall_score"] for p in papers if p.get("overall_score")]
    hypes     = [p["hype_score"]    for p in papers if p.get("hype_score")]
    actions   = Counter(p["action"] for p in papers if p.get("action"))
    domains   = Counter(p["domain"] for p in papers if p.get("domain"))
    with_code = sum(1 for p in papers if p.get("has_code"))

    print(f"  Papers analyzed:  {len(papers)}")
    print(f"  With code:        {with_code} ({with_code/len(papers)*100:.0f}%)")
    print()

    # Score stats
    print(f"  Overall Score Stats:")
    print(f"    Mean:   {np.mean(scores):.2f}/10")
    print(f"    Median: {np.median(scores):.2f}/10")
    print(f"    StdDev: {np.std(scores):.2f}")
    print(f"    Range:  {min(scores):.1f}–{max(scores):.1f}")

    # Check for score clustering (bad sign if everything is 5.0)
    unique_scores = len(set(round(s, 1) for s in scores))
    print(f"    Unique score values: {unique_scores} (higher = better discrimination)")
    if unique_scores < 5:
        warn("Scores clustered — model may not be discriminating well")
    else:
        ok(f"Good score diversity ({unique_scores} unique values)")

    # Hype stats
    if hypes:
        print(f"\n  Hype Score Stats:")
        print(f"    Mean:   {np.mean(hypes):.2f}/10")
        print(f"    StdDev: {np.std(hypes):.2f}")
        generic_hypes = sum(1 for p in papers if p.get("hype_reason") and
                           "llms, agents, multimodal, diffusion" in (p.get("hype_reason") or "").lower())
        print(f"    Generic reasons: {generic_hypes}/{len(hypes)} ({generic_hypes/len(hypes)*100:.0f}%)")
        if generic_hypes / len(hypes) > 0.5:
            warn("Sentinel is producing generic reasons >50% — needs retraining")
        else:
            ok(f"Sentinel grounding: {100 - generic_hypes/len(hypes)*100:.0f}% specific reasons")

    # Action distribution
    print(f"\n  Action Distribution:")
    for action, count in sorted(actions.items(), key=lambda x: -x[1]):
        bar = "█" * int(count / len(papers) * 30)
        print(f"    {action:15s} {count:3d} ({count/len(papers)*100:.0f}%) {bar}")

    # Domain distribution
    print(f"\n  Domain Distribution:")
    for domain, count in sorted(domains.items(), key=lambda x: -x[1])[:7]:
        print(f"    {domain:20s} {count:3d}")

    # Hidden gems
    async with httpx.AsyncClient(timeout=30.0) as client:
        gems = (await client.get(f"{BASE}/hidden-gems?limit=20")).json()
    print(f"\n  Hidden Gems (score≥7, hype≤4): {len(gems)}")
    for g in gems[:3]:
        print(f"    • {g['title'][:55]} | score={g['overall_score']} hype={g['hype_score']}")

    return {
        "total_papers":    len(papers),
        "score_mean":      np.mean(scores),
        "score_std":       np.std(scores),
        "score_range":     (min(scores), max(scores)),
        "action_dist":     dict(actions),
        "hidden_gems":     len(gems),
        "with_code_pct":   with_code / len(papers) * 100,
    }


# ──────────────────────────────────────────────────────────────
# METRIC 5: End-to-End Latency
# ──────────────────────────────────────────────────────────────

async def eval_latency():
    section("METRIC 5: End-to-End Latency Benchmarks")

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Get a paper that's already analyzed
        papers = (await client.get(f"{BASE}/papers?analyzed_only=true&limit=1")).json()
        if not papers:
            warn("No analyzed papers for latency test")
            return None
        paper_id = papers[0]["id"]

    latencies = {}

    async with httpx.AsyncClient(timeout=120.0) as client:

        # 1. Semantic search
        t = time.time()
        await client.get(f"{BASE}/search?q=attention+mechanism")
        latencies["semantic_search_ms"] = round((time.time() - t) * 1000)

        # 2. Paper brief
        t = time.time()
        await client.get(f"{BASE}/papers/{paper_id}/brief")
        latencies["paper_brief_ms"] = round((time.time() - t) * 1000)

        # 3. Global RAG chat
        t = time.time()
        await client.post(f"{BASE}/chat", json={"message": "What is knowledge distillation?"})
        latencies["global_chat_ms"] = round((time.time() - t) * 1000)

        # 4. Paper chat
        t = time.time()
        await client.post(f"{BASE}/papers/{paper_id}/chat", json={
            "message": "Summarize the key contributions"
        })
        latencies["paper_chat_ms"] = round((time.time() - t) * 1000)

    print(f"\n  Endpoint latencies:")
    for endpoint, ms in latencies.items():
        label = endpoint.replace("_ms", "").replace("_", " ").title()
        bar = "█" * min(int(ms / 200), 20)
        status = "✅" if ms < 3000 else "⚠️ "
        print(f"  {status} {label:25s} {ms:5d}ms  {bar}")

    print(f"\n  Total chat latency: {latencies.get('global_chat_ms', 0)}ms")
    if latencies.get("global_chat_ms", 0) < 5000:
        ok("Chat latency under 5s — acceptable for demo")
    else:
        warn("Chat latency over 5s — consider caching or faster model")

    return latencies


# ──────────────────────────────────────────────────────────────
# SUMMARY REPORT
# ──────────────────────────────────────────────────────────────

def print_summary(hype_metrics, rag_metrics, consistency_metrics, dist_metrics, latency_metrics):
    section("📊 FINAL METRICS REPORT — Paper2Signal")

    print("""
  ┌─────────────────────────────────────────────────────┐
  │  METRIC                        VALUE     STATUS      │
  ├─────────────────────────────────────────────────────┤""")

    rows = []

    if hype_metrics:
        rows.append((
            "Hype Model Accuracy",
            f"{hype_metrics['accuracy']:.0f}%",
            "✅" if hype_metrics['accuracy'] >= 70 else "⚠️ "
        ))
        rows.append((
            "Hype Score Discrimination",
            f"StdDev={hype_metrics['std_score']:.2f}",
            "✅" if hype_metrics['std_score'] >= 1.5 else "⚠️ "
        ))

    if rag_metrics:
        rows.append((
            "RAG Precision@5",
            f"{rag_metrics['mean_precision_at_5']:.2f}",
            "✅" if rag_metrics['mean_precision_at_5'] >= 0.5 else "⚠️ "
        ))

    if consistency_metrics:
        rows.append((
            "Scoring Consistency (delta)",
            f"±{consistency_metrics['avg_delta']:.1f}",
            "✅" if consistency_metrics['avg_delta'] <= 1.0 else "⚠️ "
        ))

    if dist_metrics:
        rows.append(("Papers Analyzed",       str(dist_metrics['total_papers']), "ℹ️ "))
        rows.append(("Score Range",           f"{dist_metrics['score_range'][0]:.1f}–{dist_metrics['score_range'][1]:.1f}", "ℹ️ "))
        rows.append(("Score Mean",            f"{dist_metrics['score_mean']:.2f}/10", "ℹ️ "))
        rows.append(("Hidden Gems Found",     str(dist_metrics['hidden_gems']), "ℹ️ "))
        rows.append(("Papers With Code %",    f"{dist_metrics['with_code_pct']:.0f}%", "ℹ️ "))

    if latency_metrics:
        rows.append(("Global Chat Latency",   f"{latency_metrics.get('global_chat_ms', 0)}ms", "ℹ️ "))
        rows.append(("Semantic Search",       f"{latency_metrics.get('semantic_search_ms', 0)}ms", "ℹ️ "))

    for label, value, status in rows:
        print(f"  │  {status} {label:30s}  {value:10s}          │")

    print("  └─────────────────────────────────────────────────────┘")

    print("""
  Copy these for your resume/README:
  ──────────────────────────────────""")

    if hype_metrics and dist_metrics and rag_metrics:
        print(f"""
  • Hype model accuracy: {hype_metrics['accuracy']:.0f}% on labeled test set (10 papers)
  • RAG Precision@5: {rag_metrics['mean_precision_at_5']:.2f} across {rag_metrics['queries_tested']} semantic queries  
  • Scored {dist_metrics['total_papers']} papers, score range {dist_metrics['score_range'][0]:.1f}–{dist_metrics['score_range'][1]:.1f}/10
  • {dist_metrics['hidden_gems']} hidden gems detected (score≥7, hype≤4)
  • End-to-end chat latency: {latency_metrics.get('global_chat_ms', 'N/A')}ms
  • Scoring consistency: ±{consistency_metrics['avg_delta']:.1f} delta across repeated runs
""")


# ──────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────

async def main():
    print("\n" + "="*60)
    print("  Paper2Signal — Evaluation Metrics Suite")
    print("="*60)
    print("  Running all evaluations. This takes ~3-5 minutes.\n")

    # Check server is up
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            h = (await client.get(f"{BASE}/health")).json()
            info(f"Backend: {h['papers_count']} papers, {h['analyzed_count']} analyzed")
    except Exception:
        print("\n❌ Backend not running. Start with: python main.py")
        sys.exit(1)

    hype_m        = await eval_hype_model()
    rag_m         = await eval_rag_quality()
    consistency_m = await eval_scoring_consistency()
    dist_m        = await eval_score_distribution()
    latency_m     = await eval_latency()

    print_summary(hype_m, rag_m, consistency_m, dist_m, latency_m)


if __name__ == "__main__":
    asyncio.run(main())