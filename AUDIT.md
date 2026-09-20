# Security & Engineering Audit — legacy `student-engagement-api`

Audit of the pre-refactor codebase (Flask 3 + Flask-SQLAlchemy + SQLite; `app.py`,
`models.py`, `seed_data.py`, `static/js/dashboard.js`, `docs/openapi.yaml`).
Every finding below is a concrete defect observed in that source, with the file and
the remediation shipped in this refactor.

Severity key: **Critical** · **High** · **Medium** · **Low**

---

## A. Authentication & authorization

| # | Severity | Finding | Evidence | Remediation |
|:--|:---------|:--------|:---------|:------------|
| A1 | Critical | **Hard-coded fallback credential.** The API key defaults to the literal `'dev-api-key-2026'` when `API_KEY` is unset, so an unconfigured deployment ships a publicly known credential. | `app.py`: `app.config['API_KEY'] = os.environ.get('API_KEY', 'dev-api-key-2026')` | Secrets come only from the environment via `pydantic-settings`. `JWT_SECRET_KEY` has **no default** outside `DEMO_MODE`; startup fails fast if it is absent in production. `.env.example` carries placeholders only. |
| A2 | Critical | **Credential committed to the repo and served to every browser.** The same key is embedded in front-end JavaScript that is fetched by anyone who opens the dashboard. | `static/js/dashboard.js`: `const API_KEY = 'dev-api-key-2026';` | Dashboard now performs an OAuth2 password-grant login against `/api/v1/auth/token` with a documented, read-only demo account and holds a short-lived JWT in memory only (no `localStorage`, no source-embedded secret). |
| A3 | High | **Credential accepted in the query string.** `request.args.get('api_key')` means secrets land in access logs, proxy logs, browser history and `Referer` headers. | `app.py`, `require_api_key` | Query-string auth removed entirely. Credentials travel only in the `Authorization: Bearer` header. |
| A4 | High | **Non-constant-time credential comparison.** `api_key != app.config['API_KEY']` short-circuits on the first differing byte, a timing oracle. | `app.py`, `require_api_key` | Password verification uses bcrypt via `passlib`; JWT verification uses a MAC. No user-supplied string is compared with `==`. |
| A5 | High | **No authorization model at all.** A single shared key grants full read *and* write. Any holder of the dashboard's key can `POST /api/students`. | all `@require_api_key` routes | Role-based access control with three roles (`admin`, `analyst`, `viewer`) enforced by a FastAPI dependency (`require_roles`). Writes require `analyst` or `admin`; the demo account is `viewer` (read-only). |
| A6 | Medium | **No credential expiry or revocation.** A static key is valid forever; rotation means redeploying the dashboard. | `app.py` | JWTs are short-lived (`ACCESS_TOKEN_EXPIRE_MINUTES`, default 30) and carry `sub`, `role`, `iat`, `exp`, issuer and audience claims, all verified. |
| A7 | Medium | **No password storage at all** (there are no users), so there was no path to per-user accountability or audit. | — | User table with bcrypt hashes; every authenticated request logs `user` and `role` alongside the correlation id. |

## B. Input validation & data integrity

| # | Severity | Finding | Evidence | Remediation |
|:--|:---------|:--------|:---------|:------------|
| B1 | High | **Unvalidated JSON straight into the ORM.** `create_session` and `create_event` index `data['student_id']`, `data['course_id']`, `data['start_time']`, `data['session_id']`, `data['event_type']` with no presence check — a missing key raises `KeyError` → HTTP 500, and a wrong type is persisted verbatim. | `app.py`, `create_session`, `create_event` | Pydantic v2 request models with types, length bounds and value ranges. Violations produce a 422 problem+json body listing each offending field. |
| B2 | High | **`datetime.fromisoformat()` on attacker-controlled input without a guard.** A malformed `start_time`/`enrollment_date` raises `ValueError` → unhandled 500. | `app.py`, `create_student`, `create_session` | Datetime parsing is done by Pydantic; failures are validation errors, not crashes. |
| B3 | High | **No referential validation.** `session.student_id` and `event.session_id` are never checked to exist; SQLite does not enforce foreign keys unless `PRAGMA foreign_keys=ON` is issued, which the app never does. Orphan rows were silently creatable. | `models.py`, `app.py` | `PRAGMA foreign_keys=ON` is set on every SQLite connection, *and* the service layer verifies the parent row exists, returning 404 with a problem+json body. |
| B4 | Medium | **No value-range enforcement on `engagement_score`.** Any float — `-5`, `1e9`, `NaN` — is accepted and then averaged into the analytics, corrupting every aggregate. | `app.py`, `create_event`; `models.py` | Score constrained to `0.0 ≤ s ≤ 1.0` at the schema boundary and re-asserted by the scoring service. |
| B5 | Medium | **`duration_minutes` is caller-supplied and never reconciled with `start_time`/`end_time`.** A client can claim a 10-minute window lasted 500 minutes and skew `avg_session_duration`. | `app.py`, `create_session` | Duration is *derived* server-side from the timestamps when `end_time` is present; `end_time` must be after `start_time`. |
| B6 | Medium | **`event_data` is a free-form `Text` column fed unvalidated strings** (the seeder writes hand-built JSON by string interpolation). No schema, no size limit. | `models.py`, `seed_data.py` | Typed as an optional JSON object with a size bound, serialized by the adapter, never by string formatting. |
| B7 | Medium | **Unbounded pagination.** `per_page` is taken straight from the query string; `?per_page=1000000` materializes the whole table into memory and JSON. | `app.py`, all list endpoints | `page ≥ 1`, `1 ≤ page_size ≤ 100`, enforced by `Query(...)` constraints. |
| B8 | Low | **No uniqueness feedback.** Duplicate `student_id`/`email` raise an `IntegrityError` → 500 rather than a 409. | `app.py`, `create_student` | Duplicates return `409 Conflict` as problem+json. |

## C. Error handling & information disclosure

| # | Severity | Finding | Evidence | Remediation |
|:--|:---------|:--------|:---------|:------------|
| C1 | High | **`debug=True` in the entry point.** Werkzeug's debugger exposes an interactive Python console and a full stack trace to anyone who triggers an exception. If that line ever reaches a server, it is remote code execution. | `app.py`: `app.run(debug=True, port=5000)` | No debugger. The ASGI app is served by uvicorn/gunicorn; `DEBUG` is a settings flag that only affects log verbosity and is `false` by default. |
| C2 | Medium | **Inconsistent, non-standard error envelope.** Success paths return domain objects, failures return `{"error": "..."}`; handlers exist only for 404 and 500, so 400/401/405/422 leak Flask's HTML error pages. | `app.py`, `@app.errorhandler` | Every error path — including `RequestValidationError` and unhandled exceptions — is funneled through centralized handlers emitting **RFC 9457** `application/problem+json` with `type`, `title`, `status`, `detail`, `instance` and the `request_id`. |
| C3 | Medium | **Unhandled-exception detail leakage risk.** With `debug=True` the 500 handler never runs; tracebacks render to the client. | `app.py` | The catch-all handler logs the exception with traceback server-side and returns a generic 500 problem document containing only the correlation id. |
| C4 | Low | **No request correlation.** Nothing ties a client-visible failure to a server log line. | whole app | `X-Request-ID` middleware accepts or mints a UUIDv4, binds it to the structlog context, echoes it in the response header and includes it in every problem document. |

## D. Observability

| # | Severity | Finding | Evidence | Remediation |
|:--|:---------|:--------|:---------|:------------|
| D1 | Medium | **No application logging whatsoever** — only Werkzeug's default access line, plus `print()` statements in the seeder. Nothing is machine-parseable. | `app.py`, `seed_data.py` | `structlog` JSON logs to stdout with `request_id`, `method`, `path`, `status_code`, `duration_ms`, `user`, `role`. Console renderer only when `LOG_FORMAT=console`. |
| D2 | Low | **No health endpoint**, so no container, load balancer or orchestrator probe is possible. | — | `GET /health` (liveness) and `GET /health/ready` (readiness, issues `SELECT 1`), plus a Docker `HEALTHCHECK`. |

## E. Persistence, concurrency & performance

| # | Severity | Finding | Evidence | Remediation |
|:--|:---------|:--------|:---------|:------------|
| E1 | High | **N+1 query pattern baked into the model layer.** `lazy=True` relationships plus per-row `to_dict()` means serializing a page of students can fire one query per relationship access. | `models.py`: `db.relationship(..., lazy=True)` | Relationships are `lazy="raise"` by default so an accidental lazy load is a loud error, not a silent N+1; aggregates are computed in SQL. |
| E2 | High | **Synchronous, blocking I/O under a single-threaded dev server.** Every request holds a worker for the full DB round-trip. | whole app | Async stack end to end: FastAPI + SQLAlchemy async engine (`aiosqlite` / `asyncpg`), session-per-request via dependency injection. |
| E3 | High | **No database indexes beyond the implicit PK/unique ones.** `Session.student_id`, `Session.course_id`, `Session.start_time`, `EngagementEvent.session_id`, `EngagementEvent.event_type` and `EngagementEvent.timestamp` are all filtered, grouped or ordered on, and all require full scans. | `models.py` | Explicit indexes on every filter/sort/group column, plus composite indexes for the `(session_id, timestamp)` and `(student_id, start_time)` access paths. |
| E4 | Medium | **`func.date()` on `EngagementEvent.timestamp` in the trend query is non-portable and non-sargable** — SQLite-specific semantics, and it defeats the (missing) index. | `app.py`, `engagement_trend` | Date truncation is dialect-aware, and the trend query accepts a bounded date window rather than scanning all history. |
| E5 | Medium | **Naive `datetime.utcnow` defaults.** Timestamps are stored tz-naive, so any Postgres migration or cross-zone client silently misinterprets them. `datetime.utcnow` is also deprecated in Python 3.12. | `models.py` | All timestamps are timezone-aware UTC (`DateTime(timezone=True)`, `datetime.now(UTC)`). |
| E6 | Medium | **Hard-coded SQLite URI.** `'sqlite:///engagement.db'` cannot be pointed at Postgres without a code change. | `app.py` | `DATABASE_URL` setting; SQLite by default, Postgres-ready (`postgresql+asyncpg://…`) with no code change. |
| E7 | Medium | **Row-by-row inserts in the seeder with intermediate commits** and per-object `random` calls; ~3,000 objects inserted through the ORM identity map. | `seed_data.py` | Seeder uses bulk inserts inside a single transaction with a deterministic `random.Random(seed)` instance rather than mutating global RNG state. |
| E8 | Medium | **`seed_data.py` calls `db.drop_all()` unconditionally** — running it against a configured `DATABASE_URL` destroys production data with no confirmation. | `seed_data.py` | Seeding is explicit (`--reset` flag required to drop), refuses to run against a non-SQLite URL without `--force`, and `DEMO_MODE` seeds only when the database is empty. |
| E9 | Low | **`db.create_all()` as the migration strategy.** No schema versioning, no upgrade path. | `app.py` | Schema creation stays for the demo path, but models are structured for Alembic and the constraint set is explicit rather than implicit. |
| E10 | Low | **`top_students` groups by `Student.id` while selecting non-aggregated `first_name`, `last_name`, `major`.** SQLite tolerates this; Postgres rejects it outright. | `app.py`, `top_students` | All non-aggregated selected columns appear in `GROUP BY`. |

## F. Transport, headers & web security

| # | Severity | Finding | Evidence | Remediation |
|:--|:---------|:--------|:---------|:------------|
| F1 | High | **No CORS policy configured.** Flask-CORS is absent, so the browser default applies; any change (or a proxy adding `*`) would expose the API cross-origin with credentials. | whole app | CORS is explicit and closed by default: an allow-list of origins from settings, restricted methods and headers, `X-Request-ID` exposed. |
| F2 | High | **No rate limiting.** The login-less API can be scraped or brute-forced without cost. | whole app | `slowapi` global limits plus a tighter limit on the token endpoint; 429 responses are problem+json. |
| F3 | Medium | **No security response headers** — no HSTS, `X-Content-Type-Options`, `Referrer-Policy`, `X-Frame-Options` or CSP on the dashboard HTML. | `app.py`, `static/dashboard.html` | Security-header middleware on all responses; the dashboard and landing page ship a `Content-Security-Policy` meta tag allowing only self + `cdn.jsdelivr.net` + Google Fonts, with SRI on the CDN script. |
| F4 | Medium | **`/api/docs` serves the raw OpenAPI YAML off disk** via `send_from_directory` — hand-maintained and therefore already drifting from the implemented routes. | `app.py`, `docs/openapi.yaml` | OpenAPI is generated from the code. Scalar reference at `/docs`, ReDoc at `/redoc`, raw schema at `/openapi.json`. |
| F5 | Low | **XSS sink in the dashboard.** `tbody.innerHTML = data.map(...)` interpolates `s.name` and `s.major` — both user-controllable via `POST /api/students` — directly into markup. | `static/js/dashboard.js`, `loadTopStudents` | Rows are built with `createElement` / `textContent`; no `innerHTML` with interpolated data anywhere. |
| F6 | Low | **Unpinned CDN script with no SRI.** `chart.umd.min.js` is loaded with no `integrity` attribute. | `static/dashboard.html` | Pinned version plus `integrity` + `crossorigin`. |

## G. Testing, tooling & supply chain

| # | Severity | Finding | Evidence | Remediation |
|:--|:---------|:--------|:---------|:------------|
| G1 | High | **Zero tests.** No test directory, no fixtures, no CI — every change is unverified. | repo tree | `pytest` + `pytest-asyncio` + `httpx.AsyncClient` suite covering auth, RBAC denials, validation errors, analytics math, problem+json shape and request-id propagation, with `pytest-cov` gated in CI. |
| G2 | High | **No CI/CD.** Nothing runs lint, types, tests or a vulnerability scan on push. | repo tree | `deploy.yml` (ruff → mypy → pytest+coverage artifact → bandit → pip-audit → Docker build → Trivy → GHCR push on `main`) and `codeql.yml`, both with least-privilege `permissions:` blocks. |
| G3 | Medium | **Unpinned, two-line dependency file** with no dev/runtime split, no transitive pinning and no vulnerability scanning. | `requirements.txt` | Split `requirements.txt` / `requirements-dev.txt`, version-pinned, with `pip-audit` in CI. |
| G4 | Medium | **No static analysis.** No linter, no formatter, no type checker; the codebase is entirely untyped. | repo tree | `ruff` (lint + format) and `mypy --strict` configured in `pyproject.toml` and enforced in CI. |
| G5 | Medium | **No containerization.** No Dockerfile, no compose file — "works on my machine" is the only deployment story, and `app.run()` is a dev server. | repo tree | Multi-stage `Dockerfile` (`python:3.12-slim`, non-root `appuser`, `HEALTHCHECK`), `docker-compose.yml` with an optional `postgres` profile, `.dockerignore`, `Makefile`, `render.yaml`, `fly.toml`. |
| G6 | Low | **No `.gitignore`**, so `engagement.db`, `__pycache__/` and any future `.env` are candidates for accidental commit. | repo tree | `.gitignore` covering databases, virtualenvs, caches, coverage output and `.env`. |
| G7 | Low | **No license file** despite the README claiming MIT. | repo tree | `LICENSE` (MIT) added. |

## H. Architecture & maintainability

| # | Severity | Finding | Evidence | Remediation |
|:--|:---------|:--------|:---------|:------------|
| H1 | Medium | **No layering.** Routing, authentication, validation, business rules and SQL all live in one 299-line module; the ORM model is also the wire format (`to_dict`). Nothing can be unit-tested without a Flask app context. | `app.py`, `models.py` | Hexagonal layout: `domain` (entities + repository ports), `application` (use cases, scoring), `adapters` (SQLAlchemy repositories, API routers), `infrastructure` (settings, logging, security, db). Business rules are testable with no HTTP layer. |
| H2 | Medium | **Engagement scoring is not a domain concept.** The only scoring logic in the repo is a random-number generator inside the *seeder*; the API simply stores whatever score a client sends. | `seed_data.py`, `app.py` | Scoring is an explicit, tested application service: event-type weights, duration and recency factors, deterministic and inspectable, exposed via `/api/v1/analytics/students/{id}/score`. |
| H3 | Medium | **Module-level singletons.** `app` and `db` are import-time globals, so `seed_data.py` must import the web app to touch the database and tests cannot swap the engine. | `app.py`, `seed_data.py`, `models.py` | Application factory + DI container; the seeder depends on the database module, never on the web app. |
| H4 | Low | **Global RNG mutation.** `random.seed(42)` at import time of `seed_data` silently reseeds the process-wide RNG for anything else that imports it. | `seed_data.py` | A local `random.Random(seed)` instance is used. |
| H5 | Low | **Shadowed name `Session`.** The ORM class `Session` collides conceptually with SQLAlchemy's `Session`, an easy source of import bugs. | `models.py` | Renamed to `LearningSession` in the persistence layer; the JSON surface keeps the original field names. |
| H6 | Low | **`Student.query.get_or_404`** ties the persistence layer to Flask's HTTP abstractions. | `app.py` | Repositories return `None`; the application layer raises a domain error the API layer maps to 404. |

---

## Compatibility commitments carried through the refactor

* `GET /` still serves the dashboard experience (now a landing page offering **Open dashboard** and **Open API explorer**; the dashboard itself remains at `/dashboard`, and `/` renders without a redirect so no bookmark breaks).
* Every legacy `/api/*` path is preserved as a thin alias delegating to its `/api/v1/*` handler, with identical response bodies — including `/api/analytics/overview`, whose canonical name is now `/api/v1/analytics/summary`.
* `/api/docs` continues to resolve, now redirecting to the generated Scalar reference.
