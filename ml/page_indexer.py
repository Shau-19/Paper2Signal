"""
Paper2Signal — PageIndex Integration
Fetches ArXiv PDFs, indexes via PageIndex Cloud API,
stores doc_id + tree in DB for session-based deep chat.

Flow:
  1. Fetch PDF bytes from arxiv.org/pdf/{id}
  2. Upload to PageIndex POST /doc/ (multipart)
  3. Poll GET /doc/{doc_id}/?type=tree until completed
  4. Store doc_id + tree JSON in Paper row
  5. Chat via POST /chat/completions with doc_id

Auth: header "api_key": YOUR_KEY  (NOT Authorization: Bearer)
"""
'''
import json
import time
import logging
import urllib.request
import urllib.error
from typing import Optional

from config.settings import settings

logger = logging.getLogger(__name__)

PAGEINDEX_BASE = "https://api.pageindex.ai"


# ── Auth + HTTP helpers ───────────────────────────────────────────────────

def _headers(api_key: str) -> dict:
    """PageIndex uses 'api_key' header, not Bearer token."""
    return {"api_key": api_key}


def _get(api_key: str, path: str) -> dict:
    req = urllib.request.Request(
        f"{PAGEINDEX_BASE}{path}",
        headers=_headers(api_key),
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise ValueError(f"PageIndex GET error {e.code}: {body}")


def _multipart_post(api_key: str, path: str,
                    filename: str, content: bytes,
                    content_type: str = "application/pdf") -> dict:
    """POST multipart/form-data — no external deps."""
    boundary = "----PaperSignalBoundary7f3a9b2c"

    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: {content_type}\r\n\r\n"
    ).encode("utf-8") + content + f"\r\n--{boundary}--\r\n".encode("utf-8")

    req = urllib.request.Request(
        f"{PAGEINDEX_BASE}{path}",
        data=body,
        method="POST",
        headers={
            **_headers(api_key),
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Content-Length": str(len(body)),
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body_err = e.read().decode("utf-8", errors="replace")
        raise ValueError(f"PageIndex POST error {e.code}: {body_err}")


# ── PDF fetching ──────────────────────────────────────────────────────────

def fetch_arxiv_pdf(arxiv_id: str) -> bytes:
    """
    Download PDF from arxiv.org.
    arxiv_id examples: "2401.12345" or "2401.12345v1"
    """
    # Strip version suffix for clean ID
    base_id = arxiv_id.split("v")[0]
    url = f"https://arxiv.org/pdf/{base_id}"

    logger.info(f"[PageIndex] Fetching PDF: {url}")

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Paper2Signal/1.0 (research tool)",
            "Accept": "application/pdf",
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            pdf_bytes = r.read()
            logger.info(f"[PageIndex] PDF fetched: {len(pdf_bytes)/1024:.0f} KB")
            return pdf_bytes
    except urllib.error.HTTPError as e:
        raise ValueError(f"Could not fetch ArXiv PDF {arxiv_id}: {e.code}")
    except Exception as e:
        raise ValueError(f"PDF fetch failed: {e}")


# ── Polling ───────────────────────────────────────────────────────────────

def poll_until_ready(api_key: str, doc_id: str,
                     max_wait: int = 180) -> list:
    """
    Poll GET /doc/{doc_id}/?type=tree until status == completed.
    Returns tree nodes list.
    max_wait: seconds before timeout (default 3 min)
    """
    deadline = time.time() + max_wait
    attempts = 0

    while time.time() < deadline:
        attempts += 1
        try:
            data = _get(api_key, f"/doc/{doc_id}/?type=tree")
            status = data.get("status", "")

            logger.info(f"[PageIndex] Poll {attempts}: {status}")

            if status == "completed":
                tree = data.get("result", [])
                logger.info(f"[PageIndex] Tree ready: {_count_nodes(tree)} nodes")
                return tree

            if status in ("failed", "error"):
                raise ValueError(
                    f"PageIndex processing failed for {doc_id}: {data}"
                )

        except ValueError:
            raise
        except Exception as e:
            logger.warning(f"[PageIndex] Poll error: {e}")

        time.sleep(4)

    raise TimeoutError(
        f"PageIndex timed out after {max_wait}s for doc_id={doc_id}"
    )


# ── Tree utilities ────────────────────────────────────────────────────────

def _count_nodes(nodes) -> int:
    if not nodes:
        return 0
    if not isinstance(nodes, list):
        nodes = [nodes]
    return sum(1 + _count_nodes(n.get("nodes", [])) for n in nodes)


def _count_pages(nodes) -> int:
    """Estimate page count from end_index of deepest nodes."""
    if not nodes:
        return 0
    max_page = 0
    stack = nodes if isinstance(nodes, list) else [nodes]
    while stack:
        node = stack.pop()
        end = node.get("end_index", 0)
        if end > max_page:
            max_page = end
        stack.extend(node.get("nodes", []))
    return max_page


def render_tree_text(nodes, depth: int = 0, max_depth: int = 4) -> str:
    """Render tree as readable text for debugging/display."""
    if depth > max_depth or not nodes:
        return ""
    lines = []
    if not isinstance(nodes, list):
        nodes = [nodes]
    for node in nodes:
        indent = "  " * depth
        node_id = node.get("node_id", "?")
        title = node.get("title", "")
        summary = (node.get("summary", "") or "")[:100]
        line = f"{indent}[{node_id}] {title}"
        if summary:
            line += f"\n{indent}    {summary}{'…' if len(summary) == 100 else ''}"
        lines.append(line)
        children = node.get("nodes", [])
        if children:
            child_text = render_tree_text(children, depth + 1, max_depth)
            if child_text:
                lines.append(child_text)
    return "\n".join(filter(None, lines))


# ── PageIndex Chat API ────────────────────────────────────────────────────

def pageindex_chat(api_key: str, doc_id: str,
                   messages: list) -> str:
    """
    POST /chat/completions scoped to a specific document.
    messages: list of {role, content} dicts
    Returns answer string.
    """
    payload = json.dumps({
        "doc_id": doc_id,
        "messages": messages,
        "stream": False,
    }).encode()

    req = urllib.request.Request(
        f"{PAGEINDEX_BASE}/chat/completions",
        data=payload,
        method="POST",
        headers={
            **_headers(api_key),
            "Content-Type": "application/json",
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.loads(r.read())
        return data["choices"][0]["message"]["content"]
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise ValueError(f"PageIndex Chat error {e.code}: {body}")


# ── Main public interface ─────────────────────────────────────────────────

async def build_paper_index(arxiv_id: str) -> dict:
    """
    Full pipeline: fetch PDF → upload → poll → return index info.

    Returns:
        {
            doc_id: str,
            tree: list,
            sections: int,
            pages: int,
            tree_text: str,
        }

    Raises ValueError if API key missing or any step fails.
    """
    api_key = settings.PAGEINDEX_API_KEY
    if not api_key:
        raise ValueError(
            "PAGEINDEX_API_KEY not set — add it to .env to use deep chat"
        )

    # Step 1: Fetch PDF
    pdf_bytes = fetch_arxiv_pdf(arxiv_id)

    # Step 2: Upload to PageIndex
    logger.info(f"[PageIndex] Uploading PDF for {arxiv_id}...")
    result = _multipart_post(
        api_key,
        "/doc/",
        filename=f"{arxiv_id}.pdf",
        content=pdf_bytes,
        content_type="application/pdf",
    )

    doc_id = result.get("doc_id")
    if not doc_id:
        raise ValueError(f"PageIndex did not return doc_id: {result}")
    logger.info(f"[PageIndex] doc_id={doc_id}, polling for tree...")

    # Step 3: Poll until ready
    tree = poll_until_ready(api_key, doc_id)

    sections = _count_nodes(tree)
    pages = _count_pages(tree)
    tree_text = render_tree_text(tree)

    logger.info(
        f"[PageIndex] Index ready: {sections} sections, ~{pages} pages"
    )

    return {
        "doc_id": doc_id,
        "tree": tree,
        "sections": sections,
        "pages": pages,
        "tree_text": tree_text,
    }


async def chat_with_paper(doc_id: str, messages: list,
                          paper_context: dict = None) -> str:
    """
    Chat with an indexed paper via PageIndex Chat API.

    doc_id: from build_paper_index()
    messages: full conversation history [{role, content}]
    paper_context: optional dict with title, score, action etc
                   for system prompt enrichment

    Returns answer string.
    """
    api_key = settings.PAGEINDEX_API_KEY
    if not api_key:
        raise ValueError("PAGEINDEX_API_KEY not set")

    # Inject system message with Paper2Signal context
    system_content = """You are The Scribe — Paper2Signal's senior ML engineer 
who has read this paper in full via PageIndex reasoning-based retrieval.

When answering:
- Be specific and cite section titles or page numbers when possible
- For code questions:
  * If the paper contains actual code/pseudocode: extract it directly 
    and say "From the paper (Section X, page Y):"
  * If the paper describes methodology without code: implement it 
    yourself and say "Based on Section X's methodology:"
- Format code with proper language tags (```python, ```bash etc)
- Format math as LaTeX ($inline$ or $$block$$)
- Always specify which case you're in for code
- If asked about integration (HuggingFace, PyTorch, vLLM etc): 
  give concrete implementation advice based on the paper's approach
- Be direct — engineers need actionable answers, not summaries
"""

    # Add paper metadata to system if available
    if paper_context:
        system_content += f"""
Paper context:
- Title: {paper_context.get('title', 'Unknown')}
- Production score: {paper_context.get('overall_score', 'N/A')}/10
- Action: {paper_context.get('action', 'N/A')}
- Stack fit: {paper_context.get('stack_fit', 'N/A')}
"""

    # Prepend system message
    full_messages = [
        {"role": "system", "content": system_content}
    ] + messages[-10:]  # last 10 turns to stay within context

    return await _async_pageindex_chat(api_key, doc_id, full_messages)


async def _async_pageindex_chat(api_key: str, doc_id: str,
                                 messages: list) -> str:
    """Async wrapper around sync pageindex_chat."""
    import asyncio
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, pageindex_chat, api_key, doc_id, messages
    )'''

"""
Paper2Signal — PageIndex Integration
Proper SDK-based flow (not /chat/completions black box).

Build flow:
  1. Download PDF from ArXiv
  2. Submit to PageIndex via SDK → get doc_id
  3. Poll until retrieval_ready
  4. Fetch tree with node_summary=True → store in DB

Deep chat flow (per query):
  1. Load tree from DB (no re-fetch)
  2. Submit query to PageIndex retrieval API → get retrieval_id
  3. Poll retrieval until done → get relevant node texts
  4. Pass node texts as context to YOUR LLM (Groq) → generate answer
  5. Extract page/section citations from node metadata

This is the correct PageIndex flow — grounded retrieval, your LLM answers.
"""

import json
import time
import asyncio
import logging
import tempfile
import os
import urllib.request
import urllib.error
from typing import Optional

from pageindex import PageIndexClient

from config.settings import settings
from agents.llm_router import llm_call, ModelType

logger = logging.getLogger(__name__)


# ── Client singleton ──────────────────────────────────────────────────────

_pi_client: Optional[PageIndexClient] = None

def get_client() -> PageIndexClient:
    global _pi_client
    if _pi_client is None:
        if not settings.PAGEINDEX_API_KEY:
            raise ValueError("PAGEINDEX_API_KEY not set — add it to .env")
        _pi_client = PageIndexClient(api_key=settings.PAGEINDEX_API_KEY)
    return _pi_client


# ── PDF fetching ──────────────────────────────────────────────────────────

def _fetch_pdf_to_temp(arxiv_id: str) -> str:
    """
    Download ArXiv PDF to a temp file. Returns temp file path.
    Caller must delete the file after use.
    """
    base_id = arxiv_id.split("v")[0]
    url = f"https://arxiv.org/pdf/{base_id}"
    logger.info(f"[PageIndex] Fetching PDF: {url}")

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Paper2Signal/1.0 (research tool)",
            "Accept": "application/pdf",
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            pdf_bytes = r.read()
    except urllib.error.HTTPError as e:
        raise ValueError(f"Could not fetch ArXiv PDF {arxiv_id}: HTTP {e.code}")
    except Exception as e:
        raise ValueError(f"PDF fetch failed: {e}")

    # Write to temp file (SDK needs a file path)
    tmp = tempfile.NamedTemporaryFile(
        delete=False, suffix=".pdf", prefix=f"paper_{base_id}_"
    )
    tmp.write(pdf_bytes)
    tmp.close()
    logger.info(f"[PageIndex] PDF saved to {tmp.name} ({len(pdf_bytes)//1024} KB)")
    return tmp.name


# ── Polling helpers ───────────────────────────────────────────────────────

def _poll_tree_ready(client: PageIndexClient, doc_id: str, max_wait: int = 240) -> list:
    """
    Poll until tree is ready. Returns tree with summaries.
    Runs synchronously — call via run_in_executor.
    """
    deadline = time.time() + max_wait
    attempt = 0

    while time.time() < deadline:
        attempt += 1
        try:
            if client.is_retrieval_ready(doc_id):
                result = client.get_tree(doc_id, node_summary=True)
                tree = result.get("result", [])
                logger.info(f"[PageIndex] Tree ready after {attempt} polls — {_count_nodes(tree)} nodes")
                return tree
            else:
                status = client.get_tree(doc_id).get("status", "unknown")
                logger.info(f"[PageIndex] Poll {attempt}: {status}")
        except Exception as e:
            logger.warning(f"[PageIndex] Poll error: {e}")

        time.sleep(5)

    raise TimeoutError(f"PageIndex timed out after {max_wait}s for doc_id={doc_id}")


def _poll_retrieval(client: PageIndexClient, retrieval_id: str, max_wait: int = 60) -> dict:
    """
    Poll retrieval until done. Returns retrieval result dict.
    Runs synchronously — call via run_in_executor.
    """
    deadline = time.time() + max_wait
    attempt = 0

    while time.time() < deadline:
        attempt += 1
        try:
            result = client.get_retrieval(retrieval_id)
            status = result.get("status", "")
            logger.info(f"[PageIndex Retrieval] Poll {attempt}: {status}")

            if status == "completed":
                return result
            if status in ("failed", "error"):
                raise ValueError(f"PageIndex retrieval failed: {result}")

        except ValueError:
            raise
        except Exception as e:
            logger.warning(f"[PageIndex Retrieval] Poll error: {e}")

        time.sleep(2)

    raise TimeoutError(f"PageIndex retrieval timed out after {max_wait}s")


# ── Tree utilities ────────────────────────────────────────────────────────

def _count_nodes(nodes) -> int:
    if not nodes:
        return 0
    if not isinstance(nodes, list):
        nodes = [nodes]
    return sum(1 + _count_nodes(n.get("nodes", [])) for n in nodes)


def _count_pages(nodes) -> int:
    if not nodes:
        return 0
    max_page = 0
    stack = list(nodes) if isinstance(nodes, list) else [nodes]
    while stack:
        node = stack.pop()
        end = node.get("end_index", node.get("page_index", 0)) or 0
        if end > max_page:
            max_page = end
        stack.extend(node.get("nodes", []))
    return max_page


def _extract_node_context(retrieval_result: dict) -> tuple[str, list[dict]]:
    """
    Extract text and citation metadata from retrieval result.
    Returns (context_text, citations_list).
    """
    nodes = retrieval_result.get("result", [])
    if not nodes:
        return "", []

    context_parts = []
    citations = []

    for node in nodes:
        title   = node.get("title", "")
        text    = node.get("text", "")
        page    = node.get("page_index")
        node_id = node.get("node_id", "")

        if text:
            header = f"[Section: {title}"
            if page:
                header += f" | Page {page}"
            header += "]"
            context_parts.append(f"{header}\n{text}")

            if page:
                citations.append({"type": "page",    "value": int(page)})
            if title:
                citations.append({"type": "section", "value": title})

    # Deduplicate citations
    seen = set()
    unique_citations = []
    for c in citations:
        key = (c["type"], str(c["value"]))
        if key not in seen:
            seen.add(key)
            unique_citations.append(c)

    return "\n\n---\n\n".join(context_parts), unique_citations


# ── Sync build pipeline ───────────────────────────────────────────────────

def _sync_build_pipeline(arxiv_id: str) -> dict:
    """
    Full sync pipeline: fetch PDF → submit → poll → return tree data.
    Runs inside run_in_executor.
    """
    client = get_client()
    tmp_path = None

    try:
        # 1. Download PDF
        tmp_path = _fetch_pdf_to_temp(arxiv_id)

        # 2. Submit to PageIndex
        logger.info(f"[PageIndex] Submitting PDF for {arxiv_id}...")
        result = client.submit_document(tmp_path)
        doc_id = result.get("doc_id")
        if not doc_id:
            raise ValueError(f"PageIndex did not return doc_id: {result}")
        logger.info(f"[PageIndex] doc_id={doc_id}, waiting for tree...")

        # 3. Poll until tree ready (with node summaries for tree search)
        tree = _poll_tree_ready(client, doc_id)

        sections = _count_nodes(tree)
        pages    = _count_pages(tree)

        logger.info(f"[PageIndex] Ready: {sections} sections, ~{pages} pages")
        return {
            "doc_id":   doc_id,
            "tree":     tree,
            "sections": sections,
            "pages":    pages,
        }

    finally:
        # Always clean up temp file
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


def _sync_retrieve(doc_id: str, query: str) -> dict:
    """
    Submit retrieval query and poll for result.
    Returns raw retrieval result dict.
    Runs inside run_in_executor.
    """
    client = get_client()

    logger.info(f"[PageIndex] Submitting retrieval query: {query[:60]}...")
    submit_result = client.submit_query(doc_id=doc_id, query=query)
    retrieval_id  = submit_result.get("retrieval_id")

    if not retrieval_id:
        raise ValueError(f"PageIndex did not return retrieval_id: {submit_result}")

    logger.info(f"[PageIndex] retrieval_id={retrieval_id}, polling...")
    return _poll_retrieval(client, retrieval_id)


# ── Public async interface ────────────────────────────────────────────────

async def build_paper_index(arxiv_id: str) -> dict:
    """
    Full async pipeline: download PDF → submit → poll → return index data.
    Blocking I/O runs in thread executor.
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _sync_build_pipeline, arxiv_id)


async def retrieve_context(doc_id: str, query: str) -> tuple[str, list[dict]]:
    """
    Retrieve relevant context from indexed paper for a query.
    Returns (context_text, citations).
    This is the core PageIndex value — tree-search-based grounded retrieval.
    """
    loop = asyncio.get_event_loop()
    retrieval_result = await loop.run_in_executor(
        None, _sync_retrieve, doc_id, query
    )
    return _extract_node_context(retrieval_result)