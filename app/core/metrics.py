from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

# NOTE: Prometheus client registers metrics in the default CollectorRegistry.
# Define each metric exactly once per process to avoid:
# `ValueError: Duplicated timeseries in CollectorRegistry`.

traffic_api_requests_total = Counter(
    "traffic_api_requests_total",
    "traffic endpoint requests",
    labelnames=("cache_hit", "congestion_level"),
)

traffic_api_latency_seconds = Histogram(
    "traffic_api_latency_seconds", "end-to-end query latency seconds"
)

google_routes_api_calls_total = Counter(
    "google_routes_api_calls_total", "actual upstream calls made"
)

quota_usage_ratio = Gauge(
    "quota_usage_ratio", "used/cap ratio (0..1) updated on each call"
)

