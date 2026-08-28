"""
Metrics Service.

Provides in-memory metrics collection counters for requests, errors, latency, and business events.
"""

import asyncio
from typing import Any, Dict, List


class MetricsService:
    """
    In-memory, async-locked instrumentation metrics service.
    """

    def __init__(self) -> None:
        """
        Initialize counters and latency list.
        """
        self._lock = asyncio.Lock()
        self._counters: Dict[str, int] = {
            "requests_total": 0,
            "errors_total": 0,
            "posts_created_total": 0,
            "comments_created_total": 0,
            "likes_total": 0,
            "poll_votes_total": 0,
            "notifications_sent_total": 0
        }
        self._latencies: List[float] = []

    async def increment(self, metric_name: str, amount: int = 1) -> None:
        """
        Increment a specific named counter.
        """
        async with self._lock:
            if metric_name not in self._counters:
                self._counters[metric_name] = 0
            self._counters[metric_name] += amount

    async def record_latency(self, ms: float) -> None:
        """
        Record a request latency observation (in milliseconds).
        Keeps a sliding window of the last 1000 observations.
        """
        async with self._lock:
            self._latencies.append(ms)
            if len(self._latencies) > 1000:
                self._latencies.pop(0)

    async def get_metrics(self) -> Dict[str, Any]:
        """
        Compile and return all counters and calculated average latency.
        """
        async with self._lock:
            avg_latency = sum(self._latencies) / len(self._latencies) if self._latencies else 0.0
            metrics = dict(self._counters)
            metrics["avg_response_time_ms"] = round(avg_latency, 2)
            metrics["latency_observations_count"] = len(self._latencies)
            return metrics
