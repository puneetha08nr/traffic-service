# MG Road Traffic Analysis — Traffic Service Experiment

## 1. What Data Is Fetched

The service calls the **Google Routes API** (`TRAFFIC_AWARE_OPTIMAL` mode) and requests these fields:

| Field Mask | What It Returns |
|---|---|
| `routes.duration` | Actual travel time accounting for current traffic |
| `routes.staticDuration` | Free-flow baseline (zero-traffic travel time) |
| `routes.travelAdvisory` | Route-level traffic advisory from Google |
| `routes.legs.travelAdvisory` | Per-leg traffic advisory |
| `routes.legs.steps.localizedValues` | Step-level human-readable values |

### Derived Fields (computed locally)

| Field | Computation |
|---|---|
| `delay_seconds` | `max(0, duration - static_duration)` |
| `congestion_level` | `< 60s → NORMAL`, `≤ 300s → SLOW`, `> 300s → TRAFFIC_JAM` |
| `overall_condition` | Directly from `travelAdvisory.trafficOnRoute` |

---

## 2. Route — MG Road, Bangalore (~0.85 km segment)

| Point | Location | Coordinates |
|---|---|---|
| **Origin** | MG Road Metro Station end | `12.9752, 77.6094` |
| **Destination** | Trinity Circle end | `12.9719, 77.6176` |

Same road, directional segment, under 1 km.

### Query

```bash
curl -X POST "http://localhost:8000/api/v1/traffic/query" \
  -H "Content-Type: application/json" \
  -d '{
    "origin":      { "latitude": 12.9752, "longitude": 77.6094 },
    "destination": { "latitude": 12.9719, "longitude": 77.6176 },
    "label": "mg_road_metro_to_trinity"
  }'
```

### Response Shape

```json
{
  "origin":                   { "latitude": 12.9752, "longitude": 77.6094 },
  "destination":              { "latitude": 12.9719, "longitude": 77.6176 },
  "duration_seconds":         347,
  "static_duration_seconds":  412,
  "delay_seconds":            0,
  "congestion_level":         "NORMAL",
  "overall_condition":        null,
  "cache_hit":                false,
  "queried_at":               "2026-03-30T08:29:12.053864Z",
  "label":                    "mg_road_metro_to_trinity"
}
```

---

## 3. Time-of-Day Sampling Plan

Run the same query at these intervals to capture Bangalore's traffic patterns:

| Time (IST) | Expected Pattern | Key Signal |
|---|---|---|
| `06:00` | Near free-flow | `delay_seconds` ≈ 0, `congestion_level = NORMAL` |
| `08:30–10:00` | Morning peak | Expect `SLOW` or `TRAFFIC_JAM` |
| `12:00–13:00` | Lunch lull | Moderate, likely `NORMAL`–`SLOW` |
| `17:30–19:30` | Evening peak — worst of the day | Highest `delay_seconds` expected |
| `21:00` | Night wind-down | Returning toward `NORMAL` |
| `00:00` | Late night baseline | `delay_seconds` ≈ 0, free-flow |

### Historical Query (after collecting data)

```bash
curl "http://localhost:8000/api/v1/traffic/history?\
origin_lat=12.9752&origin_lng=77.6094\
&dest_lat=12.9719&dest_lng=77.6176\
&from_dt=2026-03-30T00:00:00Z\
&to_dt=2026-03-30T23:59:59Z\
&limit=50"
```

---

## 4. Observations So Far

| Time (IST) | duration_seconds | static_duration_seconds | delay_seconds | congestion_level | Note |
|---|---|---|---|---|---|
| 08:29 | 347 | 412 | 0 | NORMAL | `TRAFFIC_AWARE_OPTIMAL` found a faster path than baseline |

### Anomaly Note — 08:29 Reading

`duration_seconds (347) < static_duration_seconds (412)` — traffic-aware route was **faster** than the free-flow baseline. This is expected behavior:

- `TRAFFIC_AWARE_OPTIMAL` may choose a **different path** than the geometric default used for static duration.
- `delay_seconds` is clamped at `0` — it does not go negative.
- `overall_condition: null` means Google did not flag notable congestion on this segment.

---

## 5. Monitoring — Prometheus + Grafana

### Prometheus

Scrapes `http://app:8000/metrics` every **15 seconds**. Collects 4 custom metrics:

| Metric | Type | Tracks |
|---|---|---|
| `traffic_api_requests_total` | Counter | Every `/query` call, labeled by `cache_hit` + `congestion_level` |
| `traffic_api_latency_seconds` | Histogram | End-to-end query time |
| `google_routes_api_calls_total` | Counter | Billable Google API calls made |
| `quota_usage_ratio` | Gauge | `used / cap` ratio (0.0 → 1.0) |

Access: `http://localhost:9090`

### Grafana Dashboard (`Traffic Service Dashboard`)

Auto-refreshes every 10 seconds. Shows last 1 hour by default.

```
┌──────────────────────────────────┬──────────────────────────────────┐
│  API Requests (cache hit/miss)   │  Google Upstream Calls           │
│  rate(traffic_api_requests[5m])  │  rate(google_routes_calls[5m])   │
├──────────────────────────────────┼──────────────────────────────────┤
│  API Latency p50 / p95           │  Quota Usage Gauge               │
│  histogram_quantile(0.5 / 0.95)  │  green < 80% / orange / red 95%  │
└──────────────────────────────────┴──────────────────────────────────┘
```

Access: `http://localhost:3000`

### Quota Guard

- Monthly cap controlled by `GOOGLE_ROUTES_MONTHLY_QUOTA_CAP` (default: 4500 calls).
- Tracked in Redis under key `traffic:api_calls:{YYYY-MM}`.
- Returns HTTP `429` once cap is reached.
- Check current usage: `curl http://localhost:8000/api/v1/traffic/quota`

---

## 6. Service Architecture (Quick Reference)

```
Client
  │  POST /api/v1/traffic/query
  ▼
FastAPI
  ├── Redis cache hit? → return cached response
  ├── Quota check (Redis counter) → 429 if exceeded
  ├── Call Google Routes API (httpx async, 3 retries)
  ├── Persist to TimescaleDB (traffic_records hypertable)
  └── Write to Redis cache (TTL-based)

Prometheus scrapes /metrics every 15s → Grafana visualizes
```

---

## 7. Scheduler — Automated MG Road Polling

The scheduler (`app/scheduler.py`) uses **APScheduler AsyncIOScheduler** to poll MG Road automatically at a configured interval. No manual curl needed after startup.

### How It Works

```
FastAPI startup
  └── start_scheduler(app, interval_minutes)
        └── registers poll_mg_road() as an interval job
              └── every N minutes:
                    _do_poll(app)
                      ├── opens DB session from app.state.db_sessionmaker
                      ├── builds TrafficService with app.state.redis / httpx
                      ├── calls svc.query(MG_ROAD_REQUEST)
                      └── result auto-persisted to TimescaleDB
```

### Configuration (`.env.docker` or `.env`)

```
SCHEDULER_ENABLED=true          # set to false to disable (e.g. in tests)
SCHEDULER_INTERVAL_MINUTES=15   # how often to poll; set to 1 for fast testing
```

### Scheduler Control Endpoints

| Method | Endpoint | What it does |
|---|---|---|
| `GET` | `/api/v1/scheduler/status` | Returns `enabled`, `running`, `interval_minutes`, `next_run_time`, `job_id` |
| `POST` | `/api/v1/scheduler/trigger` | Runs one poll immediately, returns `TrafficResponse` |
| `POST` | `/api/v1/scheduler/pause` | Pauses the scheduled job |
| `POST` | `/api/v1/scheduler/resume` | Resumes a paused job |

```bash
# Check status
curl http://localhost:8000/api/v1/scheduler/status

# Trigger one poll immediately
curl -X POST http://localhost:8000/api/v1/scheduler/trigger

# Pause automatic polling
curl -X POST http://localhost:8000/api/v1/scheduler/pause

# Resume automatic polling
curl -X POST http://localhost:8000/api/v1/scheduler/resume
```

---

## 8. Running the Stack

### Prerequisites

- Docker and Docker Compose installed
- `GOOGLE_ROUTES_API_KEY` set in `.env.docker`

### Start

```bash
cd ~/Documents/IterativeResearch/RoutesAPI/traffic-service
docker compose -f infra/docker-compose.yml up --build
```

### Services

| Service | URL |
|---|---|
| FastAPI app | `http://localhost:8000` |
| API docs | `http://localhost:8000/docs` |
| Prometheus | `http://localhost:9090` |
| Grafana | `http://localhost:3000` |

### What happens after startup

1. All containers come up (app, redis, db, prometheus, grafana).
2. TimescaleDB is initialised with `migrations/001_init.sql`.
3. Scheduler starts and fires the **first MG Road poll within 15 minutes** (or immediately via `/trigger`).
4. Each poll logs `scheduler_poll_complete` with `congestion_level` and `delay_seconds`.
5. Results accumulate in TimescaleDB — query them via `/api/v1/traffic/history`.

### Tips

- To poll every minute while testing: set `SCHEDULER_INTERVAL_MINUTES=1` in `.env.docker` and rebuild.
- To disable the scheduler entirely (e.g. during unit test runs): set `SCHEDULER_ENABLED=false`.
- Watch live logs: `docker compose -f infra/docker-compose.yml logs -f app`
