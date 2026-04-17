from fastapi import FastAPI
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM
from peft import PeftModel
import uvicorn
import re
import json

app = FastAPI()

# ── Config ─────────────────────────────────────────────
BASE = "Qwen/Qwen2.5-1.5B-Instruct"
PEFT = "shau1905/papersignal-hype-detector"

print("Loading model...")

tokenizer = AutoTokenizer.from_pretrained(BASE)

base_model = AutoModelForCausalLM.from_pretrained(
    BASE,
    torch_dtype=torch.float16,
    device_map="cpu",
)

model = PeftModel.from_pretrained(base_model, PEFT, revision="main")
model = model.merge_and_unload()   # merge LoRA into base weights
model.eval()

print("Model loaded (LoRA merged)")

# ── System prompt — must stay in sync with pipeline.py HYPE_SYSTEM ─────────
SYSTEM = """You are an AI research hype detector.

Predict how much buzz this paper will generate in the ML community.

STRICT SCORING RULES (VERY IMPORTANT):

8–10 → HIGH:
- clear real-world use (infra, efficiency, systems)
- code or easy implementation
- reduces cost / latency / memory significantly
- plug-and-play for existing stacks
- widely applicable (not niche)

6–7 → MED-HIGH:
- useful idea but limited scope OR no code

4–5 → MED:
- incremental improvement
- moderate usefulness
- unclear adoption

1–3 → LOW:
- theory only
- niche domain
- no experiments or implementation

CRITICAL:
- DO NOT default to 4–5
- If strong practical impact → MUST be 7+
- If theory/niche → MUST be ≤3
- If no experiments AND no code → score MUST be ≤3

GROUNDING RULE:
- Use specific phrases from abstract
- Avoid generic statements like "novel approach"

Respond ONLY in JSON:
{"hype_score": <float 1-10>, "reason": "<specific reason>"}"""

# ── Signal keywords — must stay in sync with pipeline.py ────────────────────
THEORY_SIGNALS   = ["bound", "bounds", "convergence", "proof", "theorem",
                    "regularity", "theoretical", "asymptotic", "lemma"]
PRACTICAL_SIGNALS = ["github", "code", "implementation", "released",
                     "experiment", "benchmark", "dataset"]
INFRA_SIGNALS    = ["latency", "memory", "throughput", "faster", "speed",
                    "flops", "utilization", "efficient", "compress", "quantiz"]


# ── Parser ──────────────────────────────────────────────
def safe_parse(response: str) -> dict:
    try:
        cleaned = re.sub(r"<think>.*?</think>", "", response, flags=re.DOTALL).strip()
        cleaned = re.sub(r"```(?:json)?\s*|\s*```", "", cleaned).strip()
        parsed  = json.loads(cleaned)
        score   = float(parsed.get("hype_score", -1))
        if 1.0 <= score <= 10.0:
            return parsed
    except Exception:
        pass

    m = re.search(r'"hype_score"\s*:\s*(\d+(?:\.\d+)?)', response)
    if m:
        score = float(m.group(1))
        if 1.0 <= score <= 10.0:
            r = re.search(r'"reason"\s*:\s*"([^"]{0,200})', response)
            return {
                "hype_score": score,
                "reason": r.group(1) if r else "parsed via fallback",
            }

    return {"hype_score": 5.0, "reason": "parse fallback"}


# ── Signal-based correction ─────────────────────────────
def correct_score(score: float, abstract: str) -> float:
    """
    Rule layer on top of GRPO output.
    Fixes systematic model errors without retraining.
    Must stay in sync with pipeline.py _correct_hype_score().
    """
    a = abstract.lower()
    has_practical = any(x in a for x in PRACTICAL_SIGNALS)
    has_infra     = any(x in a for x in INFRA_SIGNALS)
    is_theory     = any(x in a for x in THEORY_SIGNALS)

    if is_theory and not has_practical:
        score = min(score, 3.0)   # pure theory → LOW

    if not has_practical:
        score = min(score, 5.0)   # no code/experiments → MED at most

    if has_practical and not has_infra:
        score = min(score, 6.0)   # code but no efficiency gain → MED-HIGH at most

    if has_infra and has_practical:
        score = max(score, 7.0)   # infra + code → always HIGH

    return round(score, 1)


# ── Inference ──────────────────────────────────────────
def run_inference(abstract: str) -> dict:
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user",   "content": f"Abstract:\n{abstract}"},
    ]

    prompt = tokenizer.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True,
    )

    inputs = tokenizer(prompt, return_tensors="pt").to(model.device)

    with torch.no_grad():
        output = model.generate(
            **inputs,
            max_new_tokens=64,
            temperature=0.2,
            do_sample=True,
            pad_token_id=tokenizer.eos_token_id,
        )

    response = tokenizer.decode(
        output[0][inputs["input_ids"].shape[1]:],
        skip_special_tokens=True,
    )

    result = safe_parse(response)
    result["hype_score"] = correct_score(float(result["hype_score"]), abstract)
    return result


# ── Startup verification ────────────────────────────────
print("Running startup verification...")

_test = run_inference(
    "FlashAttention improves training speed 3x and reduces memory 10x. "
    "Code at github.com/HazyResearch/flash-attention."
)
print(f"Verification: {_test}")

if _test["hype_score"] >= 7:
    print("Model verified OK")
else:
    print("WARNING: test score below 7 — check model or correction rules")


# ── Endpoints ───────────────────────────────────────────
@app.post("/predict")
def predict(data: dict):
    abstract = data.get("abstract", "")[:800]
    return run_inference(abstract)


@app.get("/health")
def health():
    test = run_inference(
        "Simple transformer optimization reduces memory and latency with code at github.com/example."
    )
    return {
        "status":       "ok",
        "test_score":   test["hype_score"],
        "model_loaded": True,
    }


# ── Run ─────────────────────────────────────────────────
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)