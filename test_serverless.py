import sys
import os
import time
import httpx
from dotenv import load_dotenv

# Force stdout encoding to utf-8 if possible (helps Windows PowerShell/CMD render text)
try:
    sys.stdout.reconfigure(encoding='utf-8')
except AttributeError:
    pass

# Load env variables from local .env file
load_dotenv()

HF_API_KEY = os.getenv("HF_API_KEY")
HF_HYPE_MODEL = os.getenv("HF_HYPE_MODEL", "shau1905/papersignal-hype-detector")

if not HF_API_KEY:
    print("[ERROR] HF_API_KEY not found in your .env file!")
    print("Please make sure you have HF_API_KEY=hf_... in e:\\Paper2Signal\\.env")
    sys.exit(1)

print("-------------------------------------------------------")
print(f"HF_API_KEY Loaded: {HF_API_KEY[:12]}...")
print(f"Target HF Model:  {HF_HYPE_MODEL}")
print("-------------------------------------------------------")

# Qwen2.5 ChatML Prompt Template
SYSTEM_PROMPT = """You are an AI research hype detector.

Predict how much buzz this paper will generate in the ML community.

STRICT SCORING RULES (VERY IMPORTANT):

8-10 -> HIGH:
- clear real-world use (infra, efficiency, systems)
- code or easy implementation
- reduces cost / latency / memory significantly
- plug-and-play for existing stacks
- widely applicable (not niche)

6-7 -> MED-HIGH:
- useful idea but limited scope OR no code

4-5 -> MED:
- incremental improvement
- moderate usefulness
- unclear adoption

1-3 -> LOW:
- theory only
- niche domain
- no experiments or implementation

CRITICAL:
- DO NOT default to 4-5
- If strong practical impact -> MUST be 7+
- If theory/niche -> MUST be <=3
- If no experiments AND no code -> score MUST be <=3

GROUNDING RULE:
- Use specific phrases from abstract
- Avoid generic statements like "novel approach"

Respond ONLY in JSON:
{"hype_score": <float 1-10>, "reason": "<specific reason>"}"""

TEST_ABSTRACT = (
    "FlashAttention-2 achieves 2x speedup over FlashAttention with 73% GPU FLOPS utilization. "
    "Code released at github.com/Dao-AILab/flash-attention. Drop-in replacement for standard attention."
)

chatml_prompt = (
    f"<|im_start|>system\n{SYSTEM_PROMPT}\n<|im_end|>\n"
    f"<|im_start|>user\nAbstract:\n{TEST_ABSTRACT}\n<|im_end|>\n"
    f"<|im_start|>assistant\n"
)

# NEW HUGGING FACE ROUTER ENDPOINT (api-inference.huggingface.co was decommissioned)
API_URL = f"https://router.huggingface.co/hf-inference/models/{HF_HYPE_MODEL}"

print("\nRunning test on the NEW Hugging Face Serverless Inference API...")
print(f"API Endpoint: {API_URL}")
print("Sending test request (might take 20s if the model is currently cold/loading)...")

t_start = time.time()

try:
    with httpx.Client(timeout=60.0) as client:
        resp = client.post(
            API_URL,
            headers={"Authorization": f"Bearer {HF_API_KEY}"},
            json={
                "inputs": chatml_prompt,
                "parameters": {"max_new_tokens": 100, "temperature": 0.2}
            }
        )
        
        # Check if the model is loading (503)
        if resp.status_code == 503:
            print("[INFO] Hugging Face returned 503 (Model is currently loading). Waiting 10 seconds to retry...")
            time.sleep(10)
            t_retry = time.time()
            resp = client.post(
                API_URL,
                headers={"Authorization": f"Bearer {HF_API_KEY}"},
                json={
                    "inputs": chatml_prompt,
                    "parameters": {"max_new_tokens": 100, "temperature": 0.2}
                }
            )
            print(f"Retry request completed in {time.time() - t_retry:.2f}s")
            
        print(f"Status Code: {resp.status_code}")
        print(f"Total Request time: {time.time() - t_start:.2f}s")
        
        if resp.status_code == 200:
            result = resp.json()
            print("\n[SUCCESS] API Response:")
            
            # Extract generated assistant text
            text = result[0].get("generated_text", "") if isinstance(result, list) else result.get("generated_text", "")
            if "<|im_start|>assistant\n" in text:
                parsed_output = text.split("<|im_start|>assistant\n")[-1].strip()
                print("\nExtracted Assistant JSON Response:")
                print(parsed_output)
            else:
                print("\nAssistant tag not found. Full text response:")
                print(text)
        else:
            print(f"[ERROR] API Call failed: {resp.text}")
            
except Exception as e:
    print(f"[EXCEPTION] Occurred: {e}")
