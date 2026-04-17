# Paper2Signal

**Production readiness radar for AI research papers.**  
A multi-agent system that ingests ArXiv papers, scores them for engineering utility, predicts community hype using a GRPO fine-tuned model, and surfaces hidden gems — papers worth building with that nobody is talking about yet.

<img src="frontend/src/assets/demo.gif" width="800"/>

---

## What It Does

Most AI researchers consume papers passively. Engineers need to know: *can I ship this?* Paper2Signal answers that question automatically for every new ArXiv paper in your domain.

Given any ArXiv abstract, the system outputs:

| Signal | What it means |
|--------|--------------|
| **Production Score** (0–10) | How usable is this paper's method in an engineering stack today |
| **Action** | Skip / Experiment / Strong Experiment / Adopt |
| **Hype Score** (0–10) | Predicted community buzz — Twitter, GitHub, HuggingFace |
| **Hidden Gem** flag | High production score, low hype → worth implementing before the crowd |
| **Intelligence Brief** | 2-sentence summary + stack fit + reasoning |

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Paper2Signal                                 │
│                                                                       │
│  ┌──────────┐   ┌──────────────────────────────────────────────┐    │
│  │  ArXiv   │──▶│              Ingestion Layer                  │    │
│  │  Scraper │   │  Scraper → Embeddings → ChromaDB → Velocity  │    │
│  └──────────┘   └──────────────────────┬───────────────────────┘    │
│                                         │                             │
│                                         ▼                             │
│                         ┌──────────────────────────┐                 │
│                         │    4-Agent LangGraph      │                 │
│                         │        Pipeline           │                 │
│                         └──────────────────────────┘                 │
│                                         │                             │
│          ┌──────────────────────────────┼───────────────────┐        │
│          │                              │                   │         │
│          ▼                              ▼                   ▼         │
│  ┌──────────────┐             ┌──────────────┐   ┌──────────────┐   │
│  │   FastAPI    │             │  Hype Model  │   │  PDF Indexer │   │
│  │   REST API   │             │  (port 8001) │   │  + RAG Chat  │   │
│  └──────────────┘             └──────────────┘   └──────────────┘   │
│          │                                                             │
│          ▼                                                             │
│  ┌──────────────┐                                                     │
│  │  React SPA   │                                                     │
│  │  (Vite)      │                                                     │
│  └──────────────┘                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## The 4-Agent Pipeline

Every paper passes through a LangGraph `StateGraph` with four sequential agents. Each agent has a dedicated LLM, a specific role, and guardrails on its output.

```
Abstract Input
      │
      ▼
┌─────────────────────────────────────────────────────────────────┐
│  Agent 1 — The Classifier                                        │
│  Model: Groq Llama-3.3-70b (fast, free tier)                    │
│  Output: domain, novelty, contributions[], has_code             │
│  Guard: schema validation, retry ×2                             │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│  Agent 2 — The Scorer (DeepSeek-R1)                             │
│  Model: DeepSeek-R1-Distill-Llama-8B via HF Router              │
│  Output: overall_score, reproducibility, compute_cost,          │
│          latency, adoption, reasoning                            │
│  Corrections applied:                                           │
│    • Scale normalized scores (< 1.0 → ×10)                     │
│    • Domain cap: non-ML papers → ≤ 6.0                          │
│    • Infra+code floor: efficiency papers with code → ≥ 7.0      │
│  Fallback: Groq if DeepSeek unavailable                         │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│  Agent 3 — The Scribe                                           │
│  Model: Groq Llama-3.3-70b                                      │
│  Output: summary, stack_fit, action, action_reason              │
│  Note: action is ALWAYS overridden by score rule:               │
│    score < 4 → Skip | < 6 → Experiment |                        │
│    < 8 → Strong Experiment | ≥ 8 → Adopt                        │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│  Agent 4 — The Sentinel (GRPO Fine-tuned)                       │
│  Model: Qwen2.5-1.5B-Instruct + LoRA (shau1905/papersignal-     │
│         hype-detector), served locally on port 8001             │
│  Output: hype_score (1–10), hype_reason                         │
│  Signal correction layer:                                        │
│    • theory + no code → cap ≤ 3                                  │
│    • no practical signals → cap ≤ 5                              │
│    • code + no infra → cap ≤ 6                                   │
│    • infra + code → floor ≥ 7                                    │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                               ▼
              is_hidden_gem = score ≥ 7 AND hype ≤ 4
```

---

## The Sentinel — GRPO Fine-tuned Hype Detector

The hype model is the most technically novel component of the system. Standard LLMs cannot reliably score community hype because they default to mid-range outputs (5–6) for everything. We solve this with **Group Relative Policy Optimization (GRPO)** fine-tuning.

### Training Setup

| Component | Detail |
|-----------|--------|
| Base model | `Qwen2.5-1.5B-Instruct` (Unsloth 4-bit) |
| Fine-tuning method | GRPO via TRL |
| LoRA rank | r=16, α=32 |
| Dataset | 303 papers (87 HIGH / 103 MED / 113 LOW) |
| Training steps | 230 (stopped at KL divergence peak) |
| Hosted | `shau1905/papersignal-hype-detector` |

### Reward Design

Two reward functions trained simultaneously:

```
Reward 1 — Score Accuracy (confidence-weighted)
  • Gaussian decay from ground truth score
  • Landmark papers (FlashAttention, LoRA, Transformers): full penalty ×2
  • GPT-labeled papers: softened ×0.7 (noisy labels)
  • Missed HIGH by landmark: ×2.0 penalty
  • Missed HIGH by GPT paper: ×1.5 penalty

Reward 2 — Grounding Check
  • Keyword overlap between reason and abstract
  • < 10% overlap → -1.0 (generic boilerplate)
  • > 40% overlap → +1.0 (grounded in paper)
  • Blocks: "LLMs, agents, multimodal, diffusion" patterns → -1.0
```

### Training Dynamics

```
Steps 0–100:    Learning phase     (reward: -0.3 → +0.5)
Steps 100–150:  Improving          (reward: +0.5 → +0.8)
Steps 150–200:  Peak zone ★        (reward: 0.8–1.0, grounding: ~1.0)
Steps 200+:     Post-peak drift    (KL diverging, reward unstable)
                → Stopped at step 230
```

### Test Results (13/16 correct, 7/8 new-paper patterns)

| Paper Type | Expected | Got | Result |
|-----------|----------|-----|--------|
| LoRA (landmark) | 7–9 | 8.0 | ✅ |
| FlashAttention (infra) | 7–9 | 9.0 | ✅ |
| New paper, simple+useful | 7–9 | 8.0 | ✅ |
| Theory, no code | 1–3 | 3.0 | ✅ |
| Over-hyped, no implementation | 2–5 | 2.0 | ✅ |
| DeepSeek-R1 style | 8–10 | 8.0 | ✅ |
| Mamba SSM | 7–9 | 9.0 | ✅ |
| Safety paper with code | 5–7 | 8.0 | ❌ |

---

## Ingestion & ML Pipeline

```
ArXiv API (6-hour poll)
        │
        ▼
   Scraper.py
   ┌───────────────────────────────────────┐
   │ • Fetch by category: cs.LG, cs.AI,   │
   │   cs.CL, cs.CV, stat.ML              │
   │ • Deduplicate by arxiv_id             │
   │ • Extract GitHub URLs via regex       │
   │ • Store to SQLite via SQLAlchemy      │
   └──────────────────┬────────────────────┘
                      │
                      ▼
            Embeddings.py
   ┌───────────────────────────────────────┐
   │ Model: all-MiniLM-L6-v2              │
   │ Input: title (×2) + abstract         │
   │ Batch: 32 papers                     │
   │ Store: ChromaDB (cosine space)        │
   │ Metadata: score, action, summary     │
   └──────────────────┬────────────────────┘
                      │
                      ▼
            Clustering.py
   ┌───────────────────────────────────────┐
   │ UMAP: 384-dim → 5-dim (cosine)       │
   │ HDBSCAN: min_cluster=3, eom method   │
   │ Theme labels: TF-IDF on titles       │
   │ Output: cluster_id, cluster_theme    │
   └──────────────────┬────────────────────┘
                      │
                      ▼
            Velocity.py
   ┌───────────────────────────────────────┐
   │ GitHub API: star count               │
   │ Semantic Scholar: citation count     │
   │ velocity = 0.6×star_rate             │
   │           + 0.4×citation_rate        │
   └───────────────────────────────────────┘
```

---

## PDF Indexer & RAG System

When a user clicks "Index PDF", the system builds a local knowledge base for that paper. All retrieval is local — zero API cost per query.

### Index Build Pipeline

```
ArXiv PDF
    │
    ▼
PyMuPDF extraction
    ├── Text blocks (paragraph-aware, PyMuPDF native boundaries)
    │       • Noise filter: page numbers, artifacts, short stubs
    │       • Section header detection via regex
    │       • 50-word overlap between adjacent chunks (continuity)
    │       • Figure caption tagging (Fig. N, Table N)
    │       • Math detection ($, \frac, ∑, →)
    └── Table extraction (structured rows)
    
    ▼
Two storage layers per section
    ├── Paragraph chunks  → exact retrieval (specific facts)
    └── Section summaries → reasoning layer (overview questions)
    
    ▼
ChromaDB (separate collection: p2s_pdf_v3)
    • Embedding text: labeled  [Section | Page N | MATH]
    • LLM context text: clean  (no label artifacts)
    • Overlap context: raw_text_ctx  (50-word prefix)
```

### Retrieval Pipeline (per query)

```
User Query
    │
    ▼
Query Expansion
    • "problem" → + "limitation challenge drawback weakness"
    • "method"  → + "approach algorithm technique"
    • Named entity detection (CamelCase, ACRONYM)
    
    ▼
Semantic Search (ChromaDB bi-encoder)
    • Fetch 3× candidates (n_results = n × 3)
    
    ▼
BM25 Keyword Search (in-memory, no external dep)
    • Same candidate pool
    • Critical for exact term matching: model names, equations
    
    ▼
Reciprocal Rank Fusion (RRF, k=60)
    + Boosts:
      • Named entity boost: +0.4× BM25 weight for CamelCase/ACRONYM queries
      • Numbered list boost: ×1.5 for chunks with 1) 2) 3) patterns
        when query asks about problems/contributions/limitations
      • Figure caption boost: ×1.6 when query mentions figure/diagram/table
    
    ▼
Cross-encoder Reranking
    • Model: cross-encoder/ms-marco-MiniLM-L-6-v2 (~85MB, CPU)
    • Input: 2n candidates → jointly scores (query, chunk) pairs
    • Output: top n chunks re-ordered by relevance
    • Why: bi-encoder embeds query/chunk independently;
           cross-encoder reads both together → much higher precision
    
    ▼
Sort by section order → context reads like the paper
    
    ▼
LLM Generation (intent-routed)
    • formula/math/implement → OpenAI GPT-4o-mini (precision)
    • explain/results/compare → Groq Llama-3.3-70b (speed)
    • Response length calibrated per intent:
        formula   → formula first, 2-3 sentences
        results   → exact numbers, bullet points
        implement → complete runnable code
        explain   → thorough with paper's framing
        short     → 1-2 sentences only
```

### Retrieval Quality

| Metric | Value |
|--------|-------|
| Mean Precision@5 (global) | **0.64** |
| Formula accuracy (manual) | verified correct |
| Context leakage | eliminated (clean/labeled text split) |
| Chunk overlap | 50-word sliding window |
| Figure context | caption extraction without vision API |

---

## LLM-as-Judge

Optional retrieval quality scoring using Groq. Runs on `explain` and `discuss` intents only (to save API calls). Logs retrievals scoring below 3/5 as warnings — surfacing cases where the indexed content doesn't match the query well.

```
Score 5 → context directly contains the answer with specific details
Score 4 → answer can be clearly inferred
Score 3 → partial match, some relevant content  (adequate)
Score 2 → tangentially related                  (flagged)
Score 1 → not relevant                          (flagged)
```

---

## System Metrics

These are measured on the live system with 254 ingested papers, 60 analyzed:

| Metric | Value |
|--------|-------|
| Hype model accuracy (10-paper test set) | **100%** |
| Hype score std deviation | **2.79** (high discrimination) |
| Hype score range | 1.0 – 9.0 |
| RAG Precision@5 | **0.64** |
| Scoring consistency (2-run delta) | **±0.5** |
| Score range (live DB) | 2.5 – 9.0 |
| Unique score values | 12 |
| Global chat latency | ~2100ms |
| Semantic search latency | ~300ms |
| PDF index build time | ~20–60s |
| Sentinel inference (CPU) | ~20s |

---

## Guardrails

Every LLM output passes through a validation layer before reaching the user or being stored.

```
SchemaValidator    → required JSON keys present, valid structure
ScoreValidator     → numeric fields in range, auto-clamp violations
GroundingValidator → 10% keyword overlap minimum between summary and abstract
Off-topic Guard    → regex blocks: jailbreak, prompt injection, 
                     irrelevant domains (crypto, weather, etc.)
Hallucination Guard → keyword overlap check between answer and context;
                      < 15% → appends confidence note
```

---

## Data Flow: Full End-to-End

```
   New ArXiv Paper Published
            │
            ▼
   Scheduler (APScheduler, every 6h)
            │
            ├──▶ run_scrape()
            │        └── fetch categories → dedupe → store SQLite
            │
            ├──▶ embed_pending_papers()
            │        └── encode title+abstract → ChromaDB upsert
            │
            ├──▶ run_clustering()
            │        └── UMAP → HDBSCAN → TF-IDF theme labels
            │
            └──▶ score_papers()
                     └── GitHub stars + Semantic Scholar citations
                              → velocity score

   User Requests Analysis
            │
            ▼
   POST /papers/{id}/analyze
            │
            ▼
   LangGraph Pipeline (4 agents, sequential)
            │
            ├──▶ Agent 1: Classify → domain, novelty, has_code
            ├──▶ Agent 2: Score → production readiness 0–10
            ├──▶ Agent 3: Brief → summary, stack_fit, action
            └──▶ Agent 4: Hype → community buzz 1–10
                     └── POST http://localhost:8001/predict
                              └── Sentinel GRPO model

   User Opens Paper for Chat
            │
            ├──▶ [first time] POST /papers/{id}/index
            │        └── fetch PDF → extract → embed → ChromaDB
            │
            └──▶ POST /papers/{id}/chat/deep
                     └── retrieve_context() (hybrid BM25 + semantic + rerank)
                              └── Groq / OpenAI generates grounded answer
```

---

## Tech Stack

### Backend
| Component | Technology |
|-----------|-----------|
| API framework | FastAPI + Uvicorn |
| Agent orchestration | LangGraph (StateGraph) |
| Database | SQLite + SQLAlchemy async |
| Vector store | ChromaDB (persistent) |
| Embeddings | sentence-transformers/all-MiniLM-L6-v2 |
| Reranker | cross-encoder/ms-marco-MiniLM-L-6-v2 |
| Clustering | UMAP + HDBSCAN + scikit-learn TF-IDF |
| PDF extraction | PyMuPDF (fitz) |

### LLMs
| Agent | Model | Provider |
|-------|-------|----------|
| Classifier (Agent 1) | Llama-3.3-70b-versatile | Groq |
| Scorer (Agent 2) | DeepSeek-R1-Distill-Llama-8B | HF Router |
| Scribe (Agent 3) | Llama-3.3-70b-versatile | Groq |
| Hype/Sentinel (Agent 4) | Qwen2.5-1.5B + LoRA (GRPO) | Local (port 8001) |
| Deep chat (default) | Llama-3.3-70b-versatile | Groq |
| Deep chat (math/code) | GPT-4o-mini | OpenAI |
| Scorer fallback | Llama-3.3-70b-versatile | Groq |

### Frontend
| Component | Technology |
|-----------|-----------|
| Framework | React + Vite |
| State | Zustand |
| Routing | React Router |
| PDF viewer | Custom (iframe + navigation) |
| Chat | SSE streaming |

### Training
| Component | Technology |
|-----------|-----------|
| Fine-tuning method | GRPO (TRL) |
| Base model | Qwen2.5-1.5B-Instruct (Unsloth 4-bit) |
| Platform | Google Colab T4 |
| Hosting | HuggingFace Hub |

---

## Project Structure

```
Paper2Signal/
├── api/
│   └── app.py               # FastAPI routes (20+ endpoints)
├── agents/
│   ├── pipeline.py          # LangGraph 4-agent pipeline
│   ├── llm_router.py        # LLM routing (Groq / DeepSeek / Sentinel)
│   ├── rag.py               # RAG engine (global + deep chat)
│   └── guardrails.py        # Schema, score, grounding validators
├── ml/
│   ├── pdf_indexer.py       # PDF extraction + hybrid retrieval
│   ├── embeddings.py        # ChromaDB embedding pipeline
│   ├── clustering.py        # UMAP + HDBSCAN
│   └── velocity.py          # GitHub + citation velocity
├── ingestion/
│   ├── scraper.py           # ArXiv scraper
│   └── models.py            # SQLAlchemy models
├── config/
│   └── settings.py          # Pydantic settings (all tunables)
├── hype_model.py            # Sentinel FastAPI server (port 8001)
├── main.py                  # Uvicorn entrypoint (port 8000)
├── scheduler.py             # APScheduler background pipeline
├── bulk.py                  # Parallel batch analyzer
├── seed_db.py               # Landmark paper seeder (50 papers)
├── test_models.py           # Model test suite (4/4 agents)
└── frontend/
    └── src/
        ├── App.jsx
        ├── Today.jsx        # Main feed
        ├── Explore.jsx      # Paper browser
        ├── ReadChat.jsx     # PDF viewer + deep chat
        ├── Analyze.jsx      # Analysis streaming
        └── Chat.jsx         # Global RAG chat
```

---

## Key Design Decisions

**Why GRPO instead of SFT for the hype model?**  
Supervised fine-tuning on hype scores produces mid-range collapse (everything scores 5–6) because the model learns to minimize MSE loss by hedging. GRPO uses relative reward signals between candidate outputs, forcing the model to discriminate between HIGH and LOW. The grounding reward prevents the model from ignoring the abstract entirely and outputting template phrases.

**Why a signal correction layer on top of GRPO output?**  
The model learned strong pattern recognition but imperfect calibration. Theory papers with no experiments still occasionally scored 4 instead of ≤3. The correction layer (4 deterministic rules based on abstract signals) fixes systematic calibration errors without retraining. This is identical to how production ranking systems work — learned model + calibration layer.

**Why separate clean/labeled text in ChromaDB?**  
Storing `[Section | Page 5 | MATH]` prefix in the same field used for LLM generation causes context leakage — the model sees and repeats these artifacts in answers. We store labeled text for embedding (retrieval benefits from structural signals) and clean text for generation (no artifacts). The embedding space benefits from labels; the LLM context does not.

**Why BM25 + semantic instead of semantic alone?**  
Semantic search fails on exact named entity queries. Asking "what problems does laDeCo face" returns a section summary (high semantic similarity) instead of the numbered problem paragraph (low embedding similarity, high BM25 score because "laDeCo" is an exact term match). RRF merges both signals. Cross-encoder then reranks the merged pool with joint query-document understanding.

**Why stop training at step 230?**  
KL divergence reached 0.35+ and grounding reward saturated at 1.0. Both are strong indicators of reward exploitation beginning. The model at step 200 had ≥90% of its peak performance. Continuing would have caused reward hacking (keyword stuffing) without meaningful score accuracy improvement.

---

## Running Locally

```bash
# 1. Backend
pip install -r requirements.txt
python main.py                          # port 8000

# 2. Sentinel (separate terminal)
python hype_model.py                    # port 8001

# 3. Seed landmark papers
python seed_db.py

# 4. Analyze papers
python bulk.py --limit 50 --concurrency 3

# 5. Frontend
cd frontend && npm install && npm run dev   # port 5173

# 6. Verify everything works
python test_models.py                   # should show 4/4 PASS
```

Required `.env`:
```
GROQ_API_KEY=...
HF_API_KEY=...
OPENAI_API_KEY=...   # optional, used for math/implement queries
GITHUB_TOKEN=...     # optional, for velocity scoring
```

---

## Evaluation

Run the full metrics suite:
```bash
python metrics.py
```

Tests: Sentinel accuracy, RAG Precision@5, scoring consistency (2-run delta), score distribution, end-to-end latency.
