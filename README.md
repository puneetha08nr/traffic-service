## Traffic Service – Google Routes API Traffic Data

A production-grade backend service that queries real-time traffic data between geo-coordinates using the Google Routes API (TRAFFIC_AWARE_OPTIMAL), exposes it via a FastAPI REST API, and provides caching, persistence, monitoring, and cost guardrails.

### Architecture Overview

ASCII architecture diagram:

```text
         +------------------+         +---------------------+
         |  API Clients     |  HTTP   |  FastAPI (app/)     |
         |  (curl, FE, etc) +--------->  /api/v1/traffic    |
         +------------------+         |  /api/v1/health     |
                                      +----------+----------+
                                                 |
                               +-----------------+-------------------+
                               |                                 |   |
                        (1) Redis Cache                    (2) Cost |  (3) Google Routes
                               |                           Guard    |      API
                               v                                 |   v
                         +-----------+                  +----------------+
                         |  Redis    |                  |  httpx Async   |
                         |  cache.py |                  |  google_routes |
                         +-----------+                  +----------------+
                               |
                         (4) Persist to DB
                               v
                      +--------------------+
                      | TimescaleDB / PG   |
                      | db.models / repo   |
                      +--------------------+

Prometheus scrapes `/metrics` from the FastAPI app, Grafana visualizes dashboards.
```

Key components:

- **FastAPI app** (`app/main.py`): HTTP entrypoint, routing, metrics, logging, error handling.
- **Google Routes client** (`app/core/google_routes.py`): Async httpx client with retries, response parsing, and custom errors.
- **Cache layer** (`app/core/cache.py`): Redis-based response cache for route queries (TTL-based).
- **Cost guard** (`app/core/cost_guard.py`): Enforces monthly API call quota using Redis counters.
- **DB layer** (`app/db/*`): Async SQLAlchemy + TimescaleDB hypertable for historical traffic records.
- **Service orchestration** (`app/services/traffic_service.py`): End-to-end flow: validate → cache → quota → Google → DB → cache → response.
- **Monitoring**: `prometheus-fastapi-instrumentator` + custom metrics, Prometheus, Grafana dashboard.
- **Tests** (`tests/*`): Unit tests (mocks) and integration tests (test DB/Redis).

### Prerequisites

- Docker and Docker Compose
- Python 3.11+ (only needed if you want to run without Docker or run tests locally)
- A Google Cloud project with the Routes API enabled and a **GOOGLE_ROUTES_API_KEY**

### Configuration

Copy the example env file and fill in values:

```bash
cp .env.example .env
```

For Docker Compose runs, use `.env.docker` (container networking uses service names like `redis` and `db`).

Environment variables (see `.env.example` for defaults):

- **GOOGLE_ROUTES_API_KEY**: Google Routes API key (required).
- **GOOGLE_ROUTES_MONTHLY_QUOTA_CAP**: Monthly cap on real Google API calls (default 4500).
- **REDIS_URL**: Redis connection URL (e.g. `redis://redis:6379` in Docker).
- **DATABASE_URL**: Async SQLAlchemy URL (e.g. `postgresql+asyncpg://postgres:postgres@db:5432/traffic_db`).
- **CACHE_TTL_SECONDS**: Cache TTL for route responses.
- **LOG_LEVEL**: Logging level (`INFO`, `DEBUG`, etc.).
- **ENVIRONMENT**: `development`, `staging`, or `production`.

### Running with Docker Compose (Recommended)

From the `traffic-service/` directory:

```bash
docker compose -f infra/docker-compose.yml up --build
```

This will start:

- **app**: FastAPI service on `http://localhost:8000`
- **redis**: Redis cache on `localhost:6379`
- **db**: TimescaleDB/PostgreSQL on `localhost:5432`
- **prometheus**: on `http://localhost:9090`
- **grafana**: on `http://localhost:3000`

TimescaleDB is initialized with `migrations/001_init.sql` to create the `traffic_records` hypertable.

For a production-leaning configuration (separate compose file, different resource limits, etc.):

```bash
docker compose -f infra/docker-compose.prod.yml up --build -d
```

### Running Locally (Without Docker)

1. Ensure PostgreSQL + TimescaleDB and Redis are running and accessible.
2. Create the `traffic_db` database and apply `migrations/001_init.sql`.
3. Create and populate `.env` from `.env.example`.
4. Create a virtual environment and install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

5. Start the app with Uvicorn:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### API Usage Examples

Base URL (default): `http://localhost:8000`

- **POST `/api/v1/traffic/query`**

```bash
curl -X POST "http://localhost:8000/api/v1/traffic/query" \
  -H "Content-Type: application/json" \
  -d '{
    "origin":      { "latitude": 37.7749, "longitude": -122.4194 },
    "destination": { "latitude": 37.3382, "longitude": -121.8863 },
    "label": "sf_to_sanjose"
  }'
```

Response (shape):

```json
{
  "origin": { "latitude": 37.7749, "longitude": -122.4194 },
  "destination": { "latitude": 37.3382, "longitude": -121.8863 },
  "duration_seconds": 3600,
  "static_duration_seconds": 3000,
  "delay_seconds": 600,
  "congestion_level": "SLOW",
  "overall_condition": "HEAVY_TRAFFIC",
  "cache_hit": false,
  "queried_at": "2026-03-27T12:00:00Z",
  "label": "sf_to_sanjose"
}
```

- **GET `/api/v1/traffic/history`**

```bash
curl "http://localhost:8000/api/v1/traffic/history?origin_lat=37.7749&origin_lng=-122.4194&dest_lat=37.3382&dest_lng=-121.8863&from_dt=2026-03-01T00:00:00Z&to_dt=2026-03-31T23:59:59Z&limit=50"
```

- **GET `/api/v1/traffic/quota`**

```bash
curl "http://localhost:8000/api/v1/traffic/quota"
```

- **GET `/api/v1/health`**

```bash
curl "http://localhost:8000/api/v1/health"
```

### Metrics and Monitoring

- **Prometheus scrape endpoint**: `http://localhost:8000/metrics`
- **Default metrics** via `prometheus-fastapi-instrumentator` (request counts, latencies, etc.)
- **Custom metrics** (exposed in code):
  - `traffic_api_requests_total{cache_hit, congestion_level}`
  - `traffic_api_latency_seconds` (histogram)
  - `google_routes_api_calls_total`
  - `quota_usage_ratio`

Prometheus configuration is in `infra/prometheus.yml`, and Grafana dashboard JSON is under `infra/grafana/dashboard.json`.

### Running Tests

1. Create a `.env.test` from `.env.example` and point it at test Redis and a test DB.
2. Install dev dependencies:

```bash
pip install -r requirements.txt -r requirements-dev.txt
```

3. Run all tests:

```bash
pytest
```

You can also run subsets:

```bash
pytest tests/unit
pytest tests/integration
```

### Quota Management

The cost guard tracks monthly usage in Redis using keys of the form:

- `traffic:api_calls:{YYYY-MM}`

Behavior:

- Every real Google Routes API call (cache miss) increments the counter.
- Before calling Google, the current count is checked against `GOOGLE_ROUTES_MONTHLY_QUOTA_CAP`.
- If the cap is reached or exceeded, the service raises `QuotaExceededError` and returns HTTP `429` for further calls that month.
- The `/api/v1/traffic/quota` endpoint exposes `{ used, cap, remaining, reset_date }`.

To adjust your free-tier safety margin, change **GOOGLE_ROUTES_MONTHLY_QUOTA_CAP** in your env.

### Extending the Service

Ideas for extension:

- **New endpoints**:
  - Aggregated statistics for a route over time (average delay per hour, congestion distribution).
  - Multi-leg routes or batch queries.
- **More data sources**:
  - Add support for other mapping providers behind a common interface.
- **Advanced analytics**:
  - Use TimescaleDB continuous aggregates for reporting.
  - Add alerts via Prometheus (e.g. when quota usage ratio exceeds 80%).

When adding features:

- Reuse existing patterns in `app/services/traffic_service.py`.
- Ensure all new I/O is async.
- Add unit + integration tests alongside new features.

