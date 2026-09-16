"""
PaperSignal — Guardrails
Validates every LLM output before it reaches the user.
Simple, explicit rules — no magic, no external guardrails library needed.

3 validators:
  1. SchemaValidator    — output has required fields
  2. ScoreValidator     — scores are numbers in valid range
  3. GroundingValidator — claims reference the source paper
"""

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    passed: bool
    output: Any          # cleaned/parsed output if passed
    errors: list[str]    # what failed
    retryable: bool      # should we retry with LLM?


# ── Validator 1: Schema ───────────────────────────────────────────────────────

def validate_schema(raw: str, required_keys: list[str]) -> ValidationResult:
    """
    Ensures LLM returned valid JSON with all required keys.
    Strips markdown code fences if present.
    """
    cleaned = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
    # Strip ```json ... ``` fences
    cleaned = re.sub(r"```(?:json)?\s*|\s*```", "", cleaned).strip()

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as e:
        return ValidationResult(
            passed=False,
            output=None,
            errors=[f"Invalid JSON: {e}"],
            retryable=True,
        )

    missing = [k for k in required_keys if k not in parsed]
    if missing:
        return ValidationResult(
            passed=False,
            output=parsed,
            errors=[f"Missing required keys: {missing}"],
            retryable=True,
        )

    return ValidationResult(passed=True, output=parsed, errors=[], retryable=False)


# ── Validator 2: Score Range ──────────────────────────────────────────────────

def validate_scores(parsed: dict, score_fields: dict[str, tuple[float, float]]) -> ValidationResult:
    """
    Checks that numeric score fields are within (min, max) range.
    score_fields = {"overall_score": (0, 10), "confidence": (0, 1)}
    """
    errors = []
    for field, (lo, hi) in score_fields.items():
        val = parsed.get(field)
        if val is None:
            errors.append(f"Missing score field: {field}")
            continue
        try:
            fval = float(val)
            if not (lo <= fval <= hi):
                errors.append(f"{field}={fval} out of range [{lo}, {hi}]")
                # Clamp instead of rejecting
                parsed[field] = max(lo, min(hi, fval))
        except (TypeError, ValueError):
            errors.append(f"{field} is not a number: {val}")

    # Clamping errors are warnings, not failures
    return ValidationResult(passed=True, output=parsed, errors=errors, retryable=False)


# ── Validator 3: Grounding ────────────────────────────────────────────────────

def validate_grounding(parsed: dict, source_text: str, claim_field: str = "summary") -> ValidationResult:
    """
    Lightweight grounding check: ensures the summary/brief isn't
    completely disconnected from the source paper text.
    Checks for keyword overlap — not perfect but catches hallucinations.
    """
    summary = parsed.get(claim_field, "")
    if not summary:
        return ValidationResult(passed=True, output=parsed, errors=[], retryable=False)

    # Extract meaningful words (>4 chars) from source
    source_words = set(w.lower() for w in re.findall(r'\b\w{5,}\b', source_text))
    summary_words = set(w.lower() for w in re.findall(r'\b\w{5,}\b', summary))

    if not source_words:
        return ValidationResult(passed=True, output=parsed, errors=[], retryable=False)

    overlap = len(source_words & summary_words) / max(len(summary_words), 1)

    if overlap < 0.1:   # less than 10% keyword overlap = likely hallucination
        return ValidationResult(
            passed=False,
            output=parsed,
            errors=[f"Low grounding score ({overlap:.2f}) — summary may be hallucinated"],
            retryable=True,
        )

    return ValidationResult(passed=True, output=parsed, errors=[], retryable=False)


# ── Combined Pipeline ─────────────────────────────────────────────────────────

def run_guardrails(
    raw_output: str,
    required_keys: list[str],
    score_fields: Optional[dict[str, tuple[float, float]]] = None,
    source_text: Optional[str] = None,
    claim_field: str = "summary",
) -> ValidationResult:
    """
    Runs all validators in sequence.
    Returns first hard failure (retryable=True) or final cleaned output.
    """
    # Step 1: Schema
    result = validate_schema(raw_output, required_keys)
    if not result.passed:
        logger.warning(f"[Guardrails] Schema failed: {result.errors}")
        return result

    # Step 2: Scores (if applicable)
    if score_fields:
        result = validate_scores(result.output, score_fields)
        if result.errors:
            logger.warning(f"[Guardrails] Score warnings (clamped): {result.errors}")

    # Step 3: Grounding (if source text provided)
    if source_text:
        result = validate_grounding(result.output, source_text, claim_field)
        if not result.passed:
            logger.warning(f"[Guardrails] Grounding failed: {result.errors}")
            return result

    return result