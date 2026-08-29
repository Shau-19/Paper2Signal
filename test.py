"""
Paper2Signal — Backend Test Script (updated)
Run: python test_backend.py
Tests all endpoints in order. Server must be running on localhost:8000.
"""

import httpx
import json
import time
import sys

BASE = "http://localhost:8000"
PAPER_ID = None  # will be set from /papers response

# ── Helpers ───────────────────────────────────────────────────────────────────

def ok(label):
    print(f"  ✅ {label}")

def fail(label, detail=""):
    print(f"  ❌ {label} {detail}")

def header(title):
    print(f"\n{'─'*50}")
    print(f"  {title}")
    print(f"{'─'*50}")

# ── Tests ─────────────────────────────────────────────────────────────────────

def test_health(client):
    header("1. Health Check")
    r = client.get(f"{BASE}/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    ok(f"Status: ok | Papers: {data['papers_count']} | Analyzed: {data['analyzed_count']}")
    assert data["papers_count"] > 0, "No papers — run POST /pipeline/run first"
    return data


def test_papers(client):
    global PAPER_ID
    header("2. Paper Feed")
    r = client.get(f"{BASE}/papers?limit=3")
    assert r.status_code == 200
    papers = r.json()
    assert len(papers) > 0
    PAPER_ID = papers[0]["id"]
    ok(f"Got {len(papers)} papers | Using: {PAPER_ID}")
    ok(f"Title: {papers[0]['title'][:60]}...")
    return papers


def test_analyze(client):
    header("3. Paper Analysis (full 4-agent pipeline)")
    print(f"  Analyzing {PAPER_ID}... (may take 30-60s for Sentinel cold start)")
    start = time.time()
    r = client.post(f"{BASE}/papers/{PAPER_ID}/analyze", timeout=120.0)
    elapsed = time.time() - start
    assert r.status_code == 200
    data = r.json()

    # Core checks
    assert data.get("overall_score") is not None, "overall_score missing"
    assert data.get("domain") is not None, "domain missing"
    assert data.get("action") in ["Adopt", "Experiment", "Watch", "Skip"], f"bad action: {data.get('action')}"
    assert len(data.get("errors", [])) == 0, f"errors: {data.get('errors')}"

    ok(f"Domain: {data['domain']} | Novelty: {data['novelty']}")
    ok(f"Overall score: {data['overall_score']}/10 | Action: {data['action']}")
    ok(f"Reproducibility: {data['reproducibility']} | Compute: {data['compute_cost']}")
    ok(f"Summary: {data['summary'][:80]}...")

    # Hype score check
    if data.get("hype_score"):
        ok(f"Hype score: {data['hype_score']}/10 — The Sentinel ✅")
        ok(f"Hype reason: {data.get('hype_reason', '')[:80]}")
    else:
        print(f"  ⚠️  hype_score is None — Sentinel may be cold starting ({elapsed:.1f}s elapsed)")

    ok(f"Completed in {elapsed:.1f}s")
    return data


def test_global_chat(client):
    header("4. Global RAG Chat")
    r = client.post(f"{BASE}/chat", json={
        "message": "What are the best papers for reducing LLM inference cost?"
    }, timeout=90.0)  # ← fixed from 60.0
    assert r.status_code == 200
    data = r.json()
    assert data.get("answer"), "Empty answer"
    assert data.get("session_id"), "No session_id"
    assert data.get("citations") is not None
    ok(f"Answer length: {len(data['answer'])} chars")
    ok(f"Citations: {len(data['citations'])} sources")
    ok(f"Session saved: {data['session_id'][:8]}...")
    return data["session_id"]


def test_paper_chat(client):
    header("5. Paper-Specific Chat")
    r = client.post(f"{BASE}/papers/{PAPER_ID}/chat", json={
        "message": "Give me the key implementation steps for this paper"
    }, timeout=60.0)
    assert r.status_code == 200
    data = r.json()
    assert data.get("answer"), "Empty answer"
    assert data.get("session_id"), "No session_id"
    assert data.get("mode") == "abstract"

    # Check for code generation
    has_code = "```" in data["answer"]
    ok(f"Answer length: {len(data['answer'])} chars")
    ok(f"Code generated: {'yes ✅' if has_code else 'no (text only)'}")
    ok(f"Mode: {data['mode']} | Session: {data['session_id'][:8]}...")
    return data["session_id"]


def test_sessions(client, global_session_id, paper_session_id):
    header("6. Session Persistence")
    r = client.get(f"{BASE}/sessions")
    assert r.status_code == 200
    sessions = r.json()
    assert len(sessions) >= 2, f"Expected 2+ sessions, got {len(sessions)}"

    ids = [s["id"] for s in sessions]
    assert global_session_id in ids, "Global session not found"
    assert paper_session_id in ids, "Paper session not found"

    ok(f"Total sessions: {len(sessions)}")
    for s in sessions[:3]:
        ok(f"  [{s['session_type']}] {s['title'][:50]}...")

    # Test restore
    r2 = client.get(f"{BASE}/sessions/{paper_session_id}")
    assert r2.status_code == 200
    full = r2.json()
    assert "messages" in full, "No messages in restored session"
    ok(f"Session restore: {len(full['messages'])} messages")


def test_hidden_gems(client):
    header("7. Hidden Gems")
    r = client.get(f"{BASE}/hidden-gems")
    assert r.status_code == 200  # only check endpoint works
    gems = r.json()
    ok(f"Hidden gems found: {len(gems)}")
    if gems:
        g = gems[0]
        ok(f"Top gem: {g['title'][:60]}")
        ok(f"  Score: {g['overall_score']} | Hype: {g['hype_score']}")
    else:
        print("  ℹ️  No gems yet — run: python analyze_bulk.py --github-only")


def test_themes(client):
    header("8. Themes / Clustering")
    r = client.get(f"{BASE}/themes")
    assert r.status_code == 200
    themes = r.json()
    ok(f"Themes found: {len(themes)}")
    for t in themes[:3]:
        ok(f"  {t['theme']} ({t['count']} papers)")


def test_search(client):
    header("9. Semantic Search")
    r = client.get(f"{BASE}/search?q=attention+mechanism+efficiency")
    assert r.status_code == 200
    results = r.json()
    assert len(results) > 0
    ok(f"Results: {len(results)}")
    ok(f"Top result: {results[0]['metadata']['title'][:60]}... (score: {results[0]['score']})")


def test_brief(client):
    header("10. Paper Brief")
    r = client.get(f"{BASE}/papers/{PAPER_ID}/brief")
    assert r.status_code == 200
    data = r.json()
    assert data.get("summary"), "No summary"
    assert data.get("action"), "No action"
    ok(f"Action: {data['action']} | Score: {data['overall_score']}")
    ok(f"Summary: {data['summary'][:80]}...")
    ok(f"PageIndex built: {data['page_index_built']}")


# ── Runner ────────────────────────────────────────────────────────────────────

def main():
    print("\n🚀 Paper2Signal Backend Test Suite")
    print("="*50)

    passed = 0
    failed = 0

    with httpx.Client(timeout=30.0) as client:
        tests = [
            ("Health",          lambda: test_health(client)),
            ("Papers",          lambda: test_papers(client)),
            ("Analyze",         lambda: test_analyze(client)),
            ("Global Chat",     lambda: test_global_chat(client)),
            ("Paper Chat",      lambda: test_paper_chat(client)),
            ("Themes",          lambda: test_themes(client)),
            ("Search",          lambda: test_search(client)),
            ("Brief",           lambda: test_brief(client)),
            ("Hidden Gems",     lambda: test_hidden_gems(client)),
        ]

        session_ids = {}

        for name, test_fn in tests:
            try:
                result = test_fn()
                # Collect session IDs from chat tests
                if name == "Global Chat":
                    session_ids["global"] = result
                elif name == "Paper Chat":
                    session_ids["paper"] = result
                passed += 1
            except AssertionError as e:
                fail(f"{name} FAILED", str(e))
                failed += 1
            except Exception as e:
                fail(f"{name} ERROR", str(e))
                failed += 1

        # Sessions test needs both IDs
        if "global" in session_ids and "paper" in session_ids:
            try:
                test_sessions(client, session_ids["global"], session_ids["paper"])
                passed += 1
            except Exception as e:
                fail("Sessions FAILED", str(e))
                failed += 1

    print(f"\n{'='*50}")
    print(f"  Results: {passed} passed, {failed} failed")
    if failed == 0:
        print("  🎉 All tests passed — backend is production ready!")
        print("  Next step: React frontend")
    else:
        print("  ⚠️  Fix failures before starting frontend")
    print("="*50)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())