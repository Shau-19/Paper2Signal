"""
Paper2Signal — Agent Evaluation Layer

Tracks per-agent performance metrics across all pipeline runs.
Exposes via GET /agents/metrics for the frontend.

Metrics tracked per agent:
  - call_count, success_count, fail_count
  - avg_latency_s, p95_latency_s
  - fallback_count (e.g. DeepSeek → Groq)
  - guardrail_fail_count
  - score_distribution (Agent2 only)
  - last_error

Usage in pipeline.py:
  from agents.eval import agent_metrics, record_agent_call
"""

import time
import statistics
from collections import deque
from dataclasses import dataclass, field
from typing import Optional

# ── Agent names ───────────────────────────────────────────────────────────────

AGENTS = ["classifier", "scorer", "brief", "sentinel"]


@dataclass
class AgentStats:
    name:               str
    call_count:         int         = 0
    success_count:      int         = 0
    fail_count:         int         = 0
    guardrail_fails:    int         = 0
    fallback_count:     int         = 0   # e.g. DeepSeek → Groq
    latencies:          deque       = field(default_factory=lambda: deque(maxlen=100))
    last_error:         str         = ""
    last_model_used:    str         = ""
    scores:             deque       = field(default_factory=lambda: deque(maxlen=200))  # Agent2 only

    @property
    def success_rate(self) -> float:
        if self.call_count == 0:
            return 0.0
        return round(self.success_count / self.call_count * 100, 1)

    @property
    def avg_latency(self) -> float:
        if not self.latencies:
            return 0.0
        return round(statistics.mean(self.latencies), 1)

    @property
    def p95_latency(self) -> float:
        if not self.latencies:
            return 0.0
        sorted_l = sorted(self.latencies)
        idx = int(len(sorted_l) * 0.95)
        return round(sorted_l[min(idx, len(sorted_l) - 1)], 1)

    @property
    def score_stats(self) -> dict:
        """Score distribution for Agent2 (Scorer)."""
        if not self.scores:
            return {}
        s = list(self.scores)
        return {
            "mean":   round(statistics.mean(s), 2),
            "median": round(statistics.median(s), 2),
            "min":    round(min(s), 2),
            "max":    round(max(s), 2),
            "stdev":  round(statistics.stdev(s), 2) if len(s) > 1 else 0.0,
            "distribution": {
                "skip (0-4)":       len([x for x in s if x < 4]),
                "experiment (4-6)": len([x for x in s if 4 <= x < 6]),
                "strong_exp (6-8)": len([x for x in s if 6 <= x < 8]),
                "adopt (8-10)":     len([x for x in s if x >= 8]),
            }
        }

    def to_dict(self) -> dict:
        d = {
            "name":            self.name,
            "call_count":      self.call_count,
            "success_count":   self.success_count,
            "fail_count":      self.fail_count,
            "success_rate":    self.success_rate,
            "guardrail_fails": self.guardrail_fails,
            "fallback_count":  self.fallback_count,
            "avg_latency_s":   self.avg_latency,
            "p95_latency_s":   self.p95_latency,
            "last_error":      self.last_error,
            "last_model_used": self.last_model_used,
        }
        if self.scores:
            d["score_stats"] = self.score_stats
        return d


# ── Global metrics store ──────────────────────────────────────────────────────

_metrics: dict[str, AgentStats] = {
    name: AgentStats(name=name) for name in AGENTS
}

# Pipeline-level stats
_pipeline_stats = {
    "total_runs":        0,
    "successful_runs":   0,
    "failed_runs":       0,
    "avg_total_latency": deque(maxlen=100),
    "papers_analyzed":   0,
}


# ── Context manager for recording agent calls ─────────────────────────────────

class AgentCallContext:
    """
    Use as context manager in each agent:

    async with AgentCallContext("scorer") as ctx:
        result = await do_work()
        ctx.set_model("deepseek")
        ctx.record_score(7.5)
        ctx.mark_success()
    # On exception: automatically marks failure
    """

    def __init__(self, agent_name: str):
        self.agent_name  = agent_name
        self.stats       = _metrics.get(agent_name)
        self._start      = 0.0
        self._success    = False
        self._model      = ""
        self._score      = None
        self._fallback   = False
        self._guardrail  = False

    async def __aenter__(self):
        self._start = time.time()
        if self.stats:
            self.stats.call_count += 1
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if not self.stats:
            return False

        latency = time.time() - self._start
        self.stats.latencies.append(latency)

        if exc_type is not None:
            self.stats.fail_count  += 1
            self.stats.last_error   = str(exc_val)[:200]
        elif self._success:
            self.stats.success_count += 1
        else:
            self.stats.fail_count += 1

        if self._model:
            self.stats.last_model_used = self._model
        if self._fallback:
            self.stats.fallback_count += 1
        if self._guardrail:
            self.stats.guardrail_fails += 1
        if self._score is not None:
            self.stats.scores.append(self._score)

        return False  # don't suppress exceptions

    def mark_success(self):
        self._success = True

    def mark_guardrail_fail(self):
        self._guardrail = True

    def set_model(self, model: str):
        self._model = model

    def mark_fallback(self):
        self._fallback = True

    def record_score(self, score: float):
        self._score = score


# ── Simple function-style recording (for existing pipeline code) ──────────────

def record_agent_success(agent: str, latency: float, model: str = "", score: float = None):
    stats = _metrics.get(agent)
    if not stats:
        return
    stats.call_count    += 1
    stats.success_count += 1
    stats.latencies.append(latency)
    if model:
        stats.last_model_used = model
    if score is not None:
        stats.scores.append(score)


def record_agent_failure(agent: str, latency: float, error: str = "", guardrail: bool = False, fallback: bool = False):
    stats = _metrics.get(agent)
    if not stats:
        return
    stats.call_count  += 1
    stats.fail_count  += 1
    stats.latencies.append(latency)
    if error:
        stats.last_error = error[:200]
    if guardrail:
        stats.guardrail_fails += 1
    if fallback:
        stats.fallback_count  += 1


def record_fallback(agent: str):
    stats = _metrics.get(agent)
    if stats:
        stats.fallback_count += 1


def record_pipeline_run(success: bool, total_latency: float):
    _pipeline_stats["total_runs"] += 1
    if success:
        _pipeline_stats["successful_runs"] += 1
        _pipeline_stats["papers_analyzed"]  += 1
    else:
        _pipeline_stats["failed_runs"] += 1
    _pipeline_stats["avg_total_latency"].append(total_latency)


# ── Metrics output ────────────────────────────────────────────────────────────

def get_metrics() -> dict:
    """Return full metrics snapshot for /agents/metrics endpoint."""
    lat = list(_pipeline_stats["avg_total_latency"])
    return {
        "pipeline": {
            "total_runs":          _pipeline_stats["total_runs"],
            "successful_runs":     _pipeline_stats["successful_runs"],
            "failed_runs":         _pipeline_stats["failed_runs"],
            "papers_analyzed":     _pipeline_stats["papers_analyzed"],
            "avg_total_latency_s": round(statistics.mean(lat), 1) if lat else 0.0,
            "success_rate":        round(
                _pipeline_stats["successful_runs"] / max(_pipeline_stats["total_runs"], 1) * 100, 1
            ),
        },
        "agents": {name: stats.to_dict() for name, stats in _metrics.items()},
        "health": _compute_health(),
    }


def _compute_health() -> dict:
    """Simple health flags for dashboard display."""
    issues = []

    scorer = _metrics.get("scorer")
    if scorer and scorer.fallback_count > scorer.call_count * 0.3:
        issues.append(f"Scorer falling back to Groq {scorer.fallback_count}/{scorer.call_count} times — check HF_API_KEY")

    sentinel = _metrics.get("sentinel")
    if sentinel and sentinel.fail_count > sentinel.call_count * 0.5 and sentinel.call_count > 3:
        issues.append(f"Sentinel failing {sentinel.fail_count}/{sentinel.call_count} times — model may be offline")

    classifier = _metrics.get("classifier")
    if classifier and classifier.guardrail_fails > 5:
        issues.append(f"Classifier guardrail failing frequently ({classifier.guardrail_fails} times)")

    return {
        "healthy": len(issues) == 0,
        "issues":  issues,
    }


def reset_metrics():
    """Reset all metrics — useful for testing."""
    global _metrics, _pipeline_stats
    _metrics = {name: AgentStats(name=name) for name in AGENTS}
    _pipeline_stats = {
        "total_runs": 0, "successful_runs": 0,
        "failed_runs": 0, "avg_total_latency": deque(maxlen=100),
        "papers_analyzed": 0,
    }