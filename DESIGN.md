# CodeLens AI — Design Document

## Architecture Overview

CodeLens uses a **two-layer analysis architecture** that combines deterministic static analysis with probabilistic LLM-based semantic analysis. This is the project's core technical insight: neither layer alone provides complete coverage, but together they catch significantly more issues than either would individually.

```
┌─────────────────────────────────────────────────────────────────┐
│                     React Frontend (Vite)                       │
│  Monaco Editor │ Recharts │ React Router │ GitHub OAuth Flow    │
└────────────────────────────┬────────────────────────────────────┘
                             │ REST API (JWT Auth)
┌────────────────────────────▼────────────────────────────────────┐
│                     Flask Backend (Python)                       │
│                                                                  │
│  ┌──────────────────┐    ┌──────────────────┐                   │
│  │  Static Analyzer  │    │   LLM Reviewer    │                  │
│  │  (8 AST/regex     │───▶│  (Gemini primary   │                 │
│  │   rules, <50ms)   │    │   Groq fallback)   │                 │
│  └──────────────────┘    └──────────────────┘                   │
│                                                                  │
│  ThreadPoolExecutor  │  Rate Limiter  │  JWT Auth Middleware     │
└────────────────────────────┬────────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────────┐
│                   PostgreSQL (Supabase)                          │
│  users │ reviews │ issues │ batches                              │
└─────────────────────────────────────────────────────────────────┘
```

## Key Design Decisions

### Why Flask over Django?

Django's batteries-included approach (ORM, admin panel, template engine, form handling) adds significant complexity for a REST-only API backend. Flask gives us explicit control over every layer — the request lifecycle, middleware, error handling — which makes the code easier to explain in interviews and easier to understand when reading. For a project with 5 REST endpoints and no server-rendered HTML, Django's features would be unused overhead.

### Why PostgreSQL over MongoDB?

The data model is inherently relational: users have many reviews, reviews have many issues, batches group reviews. Foreign keys, cascading deletes, and aggregate queries (`GROUP BY`, `COUNT`, `AVG`) are used throughout the stats and admin endpoints. MongoDB would require manual denormalization and lacks transactional guarantees across collections. PostgreSQL also has excellent free-tier hosting (Supabase).

### Why Gemini + Groq over Paid LLM APIs?

Claude and OpenAI APIs are pay-as-you-go with no meaningful free tier. Every demo, test, and recruiter visit would cost real money. Gemini 2.5 Flash has a generous free tier with no credit card requirement and no expiry, making it sustainable for a project that needs to stay demoable indefinitely. Groq serves as a fallback when Gemini's rate limit is hit — this fallback chain itself is a talking point about building resilient systems on free infrastructure.

### Why Two Layers (Static + LLM) Instead of LLM-Only?

1. **Reliability**: Static analysis runs in <50ms with zero network calls. If the LLM is down, rate-limited, or slow, users still get immediate, deterministic results.
2. **Deduplication**: We pass static findings into the LLM prompt so it focuses on semantic issues the static engine can't catch (race conditions, architectural flaws, resource leaks).
3. **Cost**: Each LLM call costs rate-limit budget. Running 8 deterministic rules locally first means the LLM does less redundant work.

### Why ThreadPoolExecutor over Celery?

Celery requires a message broker (Redis or RabbitMQ) — that's an additional service to deploy, configure, and monitor. For the expected load of a portfolio project (single-digit concurrent users), a `ThreadPoolExecutor` with `max_workers=4` is perfectly adequate and keeps the deployment to two services (Flask + Postgres). The executor is used only for the review processing pipeline, which is the single async operation in the system.

**At scale, this would change:** Celery + Redis would provide proper job queue semantics — persistent job storage, automatic retries with exponential backoff, priority queues, dead letter queues for failed jobs, and horizontal scaling across multiple worker processes.

### Why GitHub Contents API (Trees + Blobs) Instead of git clone?

Full `git clone` downloads the entire repository history, which is wasteful when we only need the current version of source files. The Trees API fetches the complete repo structure in a single API call, then we selectively download individual files via the Blobs API. This is lighter weight, uses fewer rate-limit credits, and avoids the need for git as a system dependency in the container.

### Why a Simple Weighted Health Score?

The health score (start at 100, subtract 15/critical, 5/warning, 1/info, floor at 0) is deliberately a simple, explainable heuristic. It's not a machine-learned score — and that's an intentional choice. A learned model would require training data we don't have, would be a black box difficult to explain to users, and would add complexity that isn't justified for v1. The formula is documented in the README so users know exactly how it's computed.

## Security Considerations

| Concern | Mitigation |
|---|---|
| GitHub OAuth tokens | Encrypted with Fernet (AES-128-CBC) before database storage |
| JWT secrets | Loaded from environment variables, never hardcoded |
| Zip-Slip vulnerability | Every extracted path is validated against the target directory |
| SQL injection | SQLAlchemy ORM parameterizes all queries |
| Rate limiting | 10 reviews/hour for auth users, 3 for guests — protects both fair usage and LLM quota |
| CORS | Restricted to the configured frontend origin |
| Input validation | Code submissions rejected if >500KB or >5000 lines |

## What Would Change at Scale

| Current (Portfolio) | Production Scale |
|---|---|
| ThreadPoolExecutor (4 workers) | Celery + Redis with configurable worker pools |
| In-memory rate limiting | Redis-backed rate limiting (distributed) |
| `db.create_all()` | Flask-Migrate (Alembic) for versioned schema migrations |
| Single Flask process (gunicorn 2 workers) | Auto-scaling container instances behind a load balancer |
| Free-tier Postgres (Supabase 500MB) | Managed PostgreSQL with connection pooling (PgBouncer) |
| In-memory LLM health counters | Prometheus/Grafana metrics pipeline |
| Monolith architecture | Separate API gateway, analysis workers, and result storage |
| No caching | Redis cache for repeated submissions (same code hash) |

## Cost Analysis

This project runs at **$0/month** with no credit card required:

| Component | Provider | Free Tier |
|---|---|---|
| Backend | Render | 750 hrs/month (sleeps after inactivity) |
| Database | Supabase | 500MB Postgres, no expiry |
| Frontend | Vercel | Unlimited static hosting |
| Primary LLM | Google Gemini | Generous daily quota, no card |
| Fallback LLM | Groq | Free tier, no card |
