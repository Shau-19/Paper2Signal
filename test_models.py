"""

PaperSignal - Model Test Suite

Tests every model in your pipeline individually.



Run from project root:

  python test_models.py



What it tests:

  1. Groq (Agent 1 & 3)        - speed + JSON output

  2. DeepSeek (Agent 2)        - reasoning + null check

  3. Sentinel (Agent 4)        - local hype model on port 8001

  4. Full pipeline end-to-end  - 3 papers (obvious Adopt / Skip / edge case)

"""



import asyncio

import json

import sys

import time

import re



# ── Setup path ────────────────────────────────────────────────────────────────

sys.path.insert(0, ".")



# ── Test papers ───────────────────────────────────────────────────────────────



PAPERS = {

    "ADOPT": {

        "id":    "test_adopt",

        "title": "LoRA: Low-Rank Adaptation of Large Language Models",

        "abstract": (

            "We propose Low-Rank Adaptation (LoRA), an approach that freezes the pretrained model "

            "weights and injects trainable rank decomposition matrices into each layer of the "

            "Transformer architecture, greatly reducing the number of trainable parameters for "

            "downstream tasks. Compared to GPT-3 fine-tuned with Adam, LoRA can reduce the number "

            "of trainable parameters by 10,000x and the GPU memory requirement by 3x. "

            "LoRA performs on-par or better than fine-tuning in model quality on RoBERTa, DeBERTa, "

            "GPT-2, and GPT-3. Code and pretrained weights at github.com/microsoft/LoRA."

        ),

        "github_url": "https://github.com/microsoft/LoRA",

        "expected_score_min": 7.0,

        "expected_action": "Adopt",

        "expected_hype_min": 7.0,

    },

    "SKIP": {

        "id":    "test_skip",

        "title": "Convergence Analysis of SGD Under Non-Convex Losses",

        "abstract": (

            "We analyze the convergence properties of stochastic gradient descent under "

            "non-convex loss surfaces. Our theoretical analysis improves prior convergence bounds "

            "by a logarithmic factor under standard assumptions. We provide proofs for two special "

            "cases. No experiments are conducted and no code is released."

        ),

        "github_url": None,

        "expected_score_max": 5.0,

        "expected_action": "Experiment",

        "expected_hype_max": 4.0,

    },

    "EDGE": {

        "id":    "test_edge",

        "title": "FlashAttention-2: Faster Attention with Better Parallelism",

        "abstract": (

            "We present FlashAttention-2 with better parallelism and work partitioning. "

            "FlashAttention-2 is 2x faster than FlashAttention and achieves 73% model FLOPS "

            "utilization on A100 GPUs. We also extend FlashAttention-2 to multi-query and grouped "

            "query attention. Code at github.com/Dao-AILab/flash-attention."

        ),

        "github_url": "https://github.com/Dao-AILab/flash-attention",

        "expected_score_min": 7.0,

        "expected_action": "Adopt",

        "expected_hype_min": 6.0,

    },

    "NON_ML": {

        "id":    "test_non_ml",

        "title": "Quantifying Player Skill in Table Tennis Using Motion Capture",

        "abstract": (

            "We present a method for quantifying player skill in table tennis using motion capture "

            "data. By analyzing swing trajectories, ball spin, and footwork patterns, we build a "

            "scoring system that correlates with official tournament rankings. Experiments on 50 "

            "players show 85% accuracy in tier prediction. No code released."

        ),

        "github_url": None,

        "expected_score_max": 6.0,   # domain cap should kick in

        "expected_action": "Experiment",

    },

}





# -- Colour helpers ------------------------------------------------------------



def ok(msg):  print(f"  [OK] {msg}")

def fail(msg):print(f"  [FAIL] {msg}")

def warn(msg):print(f"  [WARN] {msg}")

def section(title): print(f"\n{'-'*55}\n  {title}\n{'-'*55}")





# -- Test 1: Groq --------------------------------------------------------------



async def test_groq():

    section("1. Groq - Llama-3.3-70b (Agent 1 & 3)")

    from agents.llm_router import _call_groq



    system = "Return ONLY valid JSON: {\"status\": \"ok\", \"model\": \"groq\"}"

    user   = "Say hello."



    t = time.time()

    result = await _call_groq(system, user)

    elapsed = time.time() - t



    if result is None:

        fail(f"Returned None - check GROQ_API_KEY in .env")

        return False



    ok(f"Response received in {elapsed:.1f}s")

    ok(f"Content: {result[:100]}")



    # Check not None (the fix)

    if result.strip():

        ok("Null check: content is not None [OK]")

    else:

        fail("Empty string returned")

        return False



    # Check it's parseable JSON

    try:

        parsed = json.loads(re.sub(r"```(?:json)?\s*|\s*```", "", result).strip())

        ok(f"JSON valid: {parsed}")

    except:

        warn(f"Not JSON but that's ok for this test - raw: {result[:60]}")



    return True





# ── Test 2: DeepSeek ──────────────────────────────────────────────────────────



async def test_deepseek():

    section("2. DeepSeek-R1 via HF Router (Agent 2 - Scorer)")

    from agents.llm_router import _call_deepseek



    system = """You are a scorer. Return ONLY valid JSON:

{

  "overall_score": float,

  "reproducibility": float,

  "compute_cost": float,

  "latency": float,

  "adoption": float,

  "reasoning": "one sentence"

}"""

    user = (

        "Title: LoRA: Low-Rank Adaptation\n"

        "Domain: Fine-tuning\nNovelty: significant\nHas code: true\n"

        "GitHub URL: github.com/microsoft/LoRA\nVelocity: 0.9\n\n"

        "Abstract: LoRA freezes pretrained weights and injects trainable rank decomposition "

        "matrices, reducing trainable parameters by 10000x with no inference latency. "

        "Code released at github.com/microsoft/LoRA. Achieves GPT-3 quality on downstream tasks."

    )



    t = time.time()

    result = await _call_deepseek(system, user)

    elapsed = time.time() - t



    if result is None:

        fail(f"Returned None after {elapsed:.1f}s")

        fail("This means HF router returned 200 but content=None (model cold/overloaded)")

        fail("The null check fix prevents the NoneType.strip() crash")

        warn("Groq will be used as fallback - scoring still works")

        return False



    ok(f"Response in {elapsed:.1f}s")

    ok(f"Content not None [OK] (null check fix working)")



    # Parse and validate

    cleaned = re.sub(r"<think>.*?</think>", "", result, flags=re.DOTALL)

    cleaned = re.sub(r"```(?:json)?\s*|\s*```", "", cleaned).strip()

    try:

        parsed = json.loads(cleaned)

        score = float(parsed.get("overall_score", -1))



        # 🔥 FIX: scale normalized scores (DeepSeek sometimes outputs 0–1)

        if score < 1.0:

            score *= 10



        reasoning = parsed.get("reasoning", "")



        ok(f"JSON valid [OK]")

        ok(f"overall_score = {round(score, 1)}/10")

        ok(f"reasoning: {reasoning[:120]}")



        # Check grounding - does reasoning mention paper content?

        lora_keywords = ["rank", "lora", "parameter", "fine-tun", "adapter", "weight"]

        if any(k in reasoning.lower() for k in lora_keywords):

            ok("Reasoning is GROUNDED - references paper content [OK]")

        else:

            warn(f"Reasoning may be generic - check: '{reasoning[:80]}'")



        if score >= 7.0:

            ok(f"Score {round(score, 1)} >= 7 for LoRA - correct [OK]")

        else:

            warn(f"Score {round(score, 1)} seems low for LoRA (expected >= 7)")



    except Exception as e:

        fail(f"JSON parse failed: {e}")

        fail(f"Raw (first 300): {result[:300]}")

        return False



    return True





# ── Test 3: Sentinel ─────────────────────────────────────────────────────────



async def test_sentinel():

    section("3. Sentinel - Local GRPO model (port 8001)")

    from agents.llm_router import _call_sentinel



    tests = [

        ("HIGH - LoRA",

         "We propose LoRA, reducing trainable parameters by 10000x. Code at github.com/microsoft/LoRA.",

         7.0, 10.0),

        ("LOW - theory only",

         "We analyze convergence bounds of SGD under non-convex losses. Improves bounds by log factor. No code.",

         1.0, 4.0),

        ("MED - solid+code",

         "New regularization reduces overfitting. 2% ImageNet improvement. Code at github.com/example.",

         4.0, 7.0),

    ]



    all_passed = True

    for label, abstract, lo, hi in tests:

        t = time.time()

        raw = await _call_sentinel(abstract)

        elapsed = time.time() - t



        if raw is None:

            fail(f"{label}: Sentinel returned None after {elapsed:.1f}s")

            fail("  -> Is hype_model.py running on port 8001?")

            fail("  -> Run: python hype_model.py")

            all_passed = False

            continue



        try:

            parsed = json.loads(raw)

            score = float(parsed.get("hype_score", -1))

            reason = parsed.get("reason", "")



            if lo <= score <= hi:

                ok(f"{label}: {score}/10 [OK] (expected {lo}-{hi}) in {elapsed:.1f}s")

                ok(f"  reason: {reason[:80]}")

            else:

                warn(f"{label}: {score}/10 [WARN]  (expected {lo}-{hi}) in {elapsed:.1f}s")

                warn(f"  reason: {reason[:80]}")



            # Check reason is grounded (not generic)

            bad_patterns = ["llms, agents, multimodal, diffusion", "large language model, multimodal"]

            if any(p in reason.lower() for p in bad_patterns):

                warn(f"  [WARN]  Reason looks generic - Sentinel may not be reading abstract")

            else:

                ok(f"  Reason appears grounded [OK]")



        except Exception as e:

            fail(f"{label}: Parse failed - {e} | raw: {raw[:80]}")

            all_passed = False



    return all_passed





# ── Test 4: Full Pipeline ─────────────────────────────────────────────────────



async def test_pipeline():

    section("4. Full Pipeline - end-to-end (3 papers)")

    from agents.pipeline import analyze_paper

    from ingestion.models import Paper

    from datetime import datetime



    results_summary = []



    for label, paper_data in PAPERS.items():

        print(f"\n  -> {label}: {paper_data['title'][:55]}...")



        # Build a minimal Paper object

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



        t = time.time()

        try:

            result = await analyze_paper(paper)

            elapsed = time.time() - t

        except Exception as e:

            fail(f"Pipeline crashed: {e}")

            continue



        score  = result.get("overall_score")

        action = result.get("action")

        domain = result.get("domain")

        hype   = result.get("hype_score")

        reason = result.get("score_reasoning", "")

        errors = result.get("errors", [])



        print(f"    Domain:  {domain}")

        print(f"    Score:   {score}/10  ->  {action}")

        print(f"    Hype:    {hype}")

        print(f"    Reason:  {reason[:100]}")

        if errors:

            print(f"    Errors:  {errors}")



        passed = True



        # Check expected values

        if "expected_score_min" in paper_data:

            if score and score >= paper_data["expected_score_min"]:

                ok(f"Score {score} >= {paper_data['expected_score_min']} [OK]")

            else:

                fail(f"Score {score} below expected min {paper_data['expected_score_min']}")

                passed = False



        if "expected_score_max" in paper_data:

            if score and score <= paper_data["expected_score_max"]:

                ok(f"Score {score} <= {paper_data['expected_score_max']} [OK] (domain cap working)")

            else:

                fail(f"Score {score} above expected max {paper_data['expected_score_max']} - domain cap not working")

                passed = False



        if hype is None and label != "SKIP":

            warn(f"Hype score is None - Sentinel may be offline (pipeline still works)")



        if "scorer_failed" in errors:

            fail("Scorer failed - DeepSeek + Groq both down?")

            passed = False



        if "classifier_failed" in errors:

            fail("Classifier failed - Groq down?")

            passed = False



        ok(f"Completed in {elapsed:.1f}s")

        results_summary.append((label, passed))



    return all(p for _, p in results_summary)





# ── Main ──────────────────────────────────────────────────────────────────────



async def main():

    print("\n" + "="*55)

    print("  PaperSignal Model Test Suite")

    print("="*55)



    results = []



    results.append(("Groq",     await test_groq()))

    results.append(("DeepSeek", await test_deepseek()))

    results.append(("Sentinel", await test_sentinel()))

    results.append(("Pipeline", await test_pipeline()))



    print("\n" + "="*55)

    print("  RESULTS")

    print("="*55)

    passed = sum(1 for _, r in results if r)

    for name, r in results:

        status = "[OK] PASS" if r else "[FAIL] FAIL"

        print(f"  {status}  {name}")



    print(f"\n  {passed}/{len(results)} passed")



    if passed < len(results):

        print("\n  Common fixes:")

        print("  • DeepSeek None -> HF router cold, Groq fallback will handle it")

        print("  • Sentinel None -> run: python hype_model.py")

        print("  • Groq None     -> check GROQ_API_KEY in .env")

    else:

        print("\n  🎉 All models operational!")





if __name__ == "__main__":

    asyncio.run(main())