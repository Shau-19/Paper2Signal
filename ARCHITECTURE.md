# Paper2Signal — Architecture Diagrams

Source diagrams for Paper2Signal, in Mermaid. GitHub renders Mermaid natively in `.md` files — view this file directly on GitHub for rendered diagrams, or paste any block into [mermaid.live](https://mermaid.live) to export as PNG/SVG for a polished version.

---

## 1. System Overview

```mermaid
flowchart TB
    ARXIV[ArXiv API] -->|poll every 6h<br/>APScheduler| SCRAPER[Scraper]
    SCRAPER --> EMBED[Embeddings<br/>MiniLM-L6-v2]
    EMBED --> CHROMA[(ChromaDB<br/>paper embeddings)]
    EMBED --> CLUSTER[Clustering<br/>UMAP + HDBSCAN]
    CLUSTER --> VELOCITY[Velocity Score<br/>GitHub stars + citations]

    VELOCITY -->|"POST /papers/{id}/analyze"| PIPELINE

    subgraph PIPELINE["4-Agent LangGraph Pipeline (each agent guardrail-validated inline, retry x2 on failure)"]
        direction LR
        A1[Classifier] --> A2[Scorer] --> A3[Brief] --> A4[Hype / Sentinel]
    end

    PIPELINE --> ROUTER[LLM Router<br/>Groq / OpenAI / DeepSeek-R1<br/>per-agent fallback chains]
    PIPELINE --> SENTINEL[Sentinel GRPO Model<br/>local :8001 or HF Space fallback]

    PIPELINE --> DB[(SQLite<br/>papers, sessions, activity)]
    DB --> API[FastAPI REST<br/>20+ endpoints, SSE streaming]

    subgraph ONDEMAND["On-demand, per-paper (user clicks 'Index PDF')"]
        direction TB
        PDF[ArXiv PDF] --> INDEXER[PDF Indexer<br/>PyMuPDF extraction + chunking]
        INDEXER --> CHROMA2[(ChromaDB<br/>per-paper chunk index)]
        CHROMA2 --> RAG[Hybrid RAG<br/>BM25 + dense + cross-encoder rerank]
    end

    RAG -->|"POST /papers/{id}/chat/deep"| API
    CHROMA -->|"POST /chat (global RAG)"| API

    API --> SPA["React SPA — Today / Explore /<br/>Read & Chat / Jobs / Profile"]

    style PIPELINE fill:#1a1a2e,stroke:#e94560,color:#fff
    style ONDEMAND fill:#2a2a1a,stroke:#e9c046,color:#fff
    style RAG fill:#16213e,stroke:#0f3460,color:#fff
```

**Note on guardrails:** validation (schema / score-range / grounding checks) happens *inside* each pipeline agent, immediately after that agent's LLM call — not as one shared gate after all four agents finish. See §5 for the per-agent guardrail flow.

**Note on the PDF/RAG branch:** unlike the ingestion pipeline (which runs automatically on a 6h schedule for every new paper), PDF indexing and hybrid RAG only run when a user explicitly opens a paper in Read & Chat and clicks "Index PDF" — it is not part of the automatic scrape → score flow.

---

## 2. The 4-Agent Pipeline (LangGraph StateGraph)

```mermaid
flowchart TD
    START([Input: title, abstract,<br/>github_url, velocity_score]) --> C[Agent 1: Classifier<br/>Groq gpt-oss-120b]
    C -->|"domain, novelty,<br/>contributions[], has_code"| S[Agent 2: Scorer<br/>DeepSeek-R1]
    S -->|"overall_score, reproducibility,<br/>compute_cost, latency,<br/>adoption, score_reasoning"| B[Agent 3: Brief<br/>Groq gpt-oss-120b]
    B -->|"summary, stack_fit,<br/>action, action_reason"| H[Agent 4: Hype / Sentinel<br/>Qwen2.5-1.5B GRPO LoRA]
    H -->|"hype_score, hype_reason"| END([is_hidden_gem =<br/>overall_score≥7 AND hype_score≤4])

    C -.retry ×2 on<br/>guardrail fail.-> C
    S -.domain cap ≤6,<br/>infra+code floor ≥7.-> S
    B -.action always<br/>score-derived, not LLM's.-> B
    H -.signal correction<br/>layer (cap/floor rules).-> H

    classDef agent fill:#0f3460,stroke:#e94560,color:#fff
    class C,S,B,H agent
```

**Exact `PaperState` fields (TypedDict, `agents/pipeline.py`)** — every agent reads what it needs and writes only its own keys into this one shared object:

```python
class PaperState(TypedDict):
    # Input (set before the graph runs)
    paper_id: str
    title: str
    abstract: str
    github_url: str
    velocity_score: float

    # Agent 1 — Classifier
    domain: Optional[str]            # RAG | Fine-tuning | Reasoning | Vision | ... | Other
    novelty: Optional[str]           # incremental | moderate | significant | breakthrough
    contributions: Optional[list]    # 3 short strings
    has_code: Optional[bool]

    # Agent 2 — Scorer
    overall_score: Optional[float]       # 0-10, domain-capped / infra-floored
    reproducibility: Optional[float]     # 0-10
    compute_cost: Optional[float]        # 0-10
    latency: Optional[float]             # 0-10
    adoption: Optional[float]            # 0-10
    score_reasoning: Optional[str]

    # Agent 3 — Brief
    summary: Optional[str]
    stack_fit: Optional[str]         # free text, e.g. "PyTorch/HF/vLLM"
    action: Optional[str]            # Skip | Experiment | Strong Experiment | Adopt
    action_reason: Optional[str]     # always derived from overall_score, never from the LLM directly

    # Agent 4 — Hype / Sentinel
    hype_score: Optional[float]      # 1-10, or None if Sentinel unreachable — never guessed
    hype_reason: Optional[str]

    # Accumulated across all agents
    errors: list                     # e.g. "classifier_failed", "hype_failed"
```

**Key property:** each agent writes only its own fields to this shared typed state. A failure in one agent does not corrupt the others' output — guardrail failures are caught, retried twice, and degrade gracefully (e.g. the hype agent leaves `hype_score = None` rather than guessing, and appends to `errors` rather than raising).

---

## 3. Hybrid RAG Retrieval Pipeline

```mermaid
flowchart TD
    Q[User Query] --> INTENT[Intent Classification<br/>weighted scoring]
    INTENT --> DECOMP[Query Decomposition<br/>intent-aware sub-queries]

    DECOMP --> DENSE[Dense Retrieval<br/>ChromaDB bi-encoder]
    DECOMP --> BM25[BM25 Keyword Search<br/>in-memory]

    DENSE --> RRF[Reciprocal Rank Fusion<br/>k=60 + entity/list/figure boosts]
    BM25 --> RRF

    RRF --> CROSS[Cross-encoder Rerank<br/>ms-marco-MiniLM-L-6-v2]
    CROSS --> SORT[Sort by section order]
    SORT --> GEN[LLM Generation<br/>intent-routed model + length]
    GEN --> CONF[Confidence Check<br/>answer/context overlap]
    CONF --> ANSWER[Grounded Answer<br/>+ citations]

    classDef stage fill:#16213e,stroke:#0f3460,color:#fff
    class DENSE,BM25,RRF,CROSS stage
```

---

## 4. Guardrails Flow

```mermaid
flowchart LR
    RAW[Raw LLM Output] --> SCHEMA{Schema<br/>Valid?}
    SCHEMA -->|no| RETRY[Retry ×2]
    RETRY --> SCHEMA
    SCHEMA -->|yes| SCORE[Score Range Check<br/>clamp violations]
    SCORE --> GROUND{Grounding<br/>≥10% overlap?}
    GROUND -->|no| RETRY
    GROUND -->|yes| STORE[(Store / Return)]

    style GROUND fill:#e94560,stroke:#e94560,color:#fff
```

---

## 5. Data Flow — End to End

```mermaid
sequenceDiagram
    participant Sched as Scheduler (6h)
    participant Scraper as ArXiv Scraper
    participant DB as SQLite
    participant Chroma as ChromaDB
    participant Pipeline as LangGraph Pipeline
    participant Sentinel
    participant User

    Sched->>Scraper: run_scrape()
    Scraper->>DB: dedupe + store new papers<br/>(ArXiv only — no other paper source)
    Scraper->>Chroma: embed title+abstract

    User->>Pipeline: POST /papers/{id}/analyze
    Pipeline->>Pipeline: Classifier → Scorer → Brief
    Pipeline->>Sentinel: POST /predict (abstract)
    Sentinel-->>Pipeline: hype_score, reason
    Pipeline->>DB: save analysis

    User->>Pipeline: POST /papers/{id}/index
    Pipeline->>Chroma: extract PDF, chunk, embed

    User->>Pipeline: POST /papers/{id}/chat/deep
    Pipeline->>Chroma: hybrid retrieve (BM25+dense+rerank)
    Pipeline-->>User: grounded answer + citations
```

**Source-of-truth correction:** papers are ingested from **ArXiv only** (`ingestion/scraper.py`). GitHub is used later, separately, only to fetch star counts for velocity scoring (`ml/velocity.py`) — it is not a paper source. HuggingFace is used as an LLM/model provider (DeepSeek-R1 routing, Sentinel hosting) — it is also not a paper source. A diagram that lists "arXiv / HF / GitHub" as parallel ingestion sources overstates the system; there is exactly one ingestion source.

---

## Notes for redrawing

- Color scheme used above: dark navy (`#0f3460`, `#16213e`) for infra/pipeline stages, red-pink (`#e94560`) for guardrail/decision points, white text throughout.
- The 4-agent pipeline (§2) is the diagram most worth polishing first — it maps directly to "LangGraph / LangChain, agents and tool-use" in a job description.
- The hybrid RAG diagram (§3) maps directly to "vector DBs, RAG pipelines."
- §5 (this one) overlaps substantially with §1's automatic-vs-on-demand story — consider whether it earns its own page or whether §1 already covers it well enough. If keeping it, avoid restating the same fact (e.g. "runs every 6h") in more than one place in the same image — swimlane diagrams get noisy fast, so redundant labels cost more here than in a simple flowchart.
