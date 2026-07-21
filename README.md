# CodeLens AI

[![Tests](https://github.com/Mayank1x/CodeLens/actions/workflows/test.yml/badge.svg)](https://github.com/Mayank1x/CodeLens/actions/workflows/test.yml)

🔗 **Live Demo: [Add your deployed URL here]** — click "Try as Guest", no login needed  
*(The backend is hosted on Render free tier and may take up to a minute to wake up if it hasn't been used recently.)*

---

CodeLens AI is a full-stack code review tool that combines a **custom-built static analysis engine** (8 AST/regex rules, <50ms, zero network calls) with an **LLM-based semantic analysis layer** (Gemini + Groq fallback). It supports single-file snippets, `.zip` batch uploads, and full recursive GitHub repository scanning for Python, JavaScript, Java, and C++.

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│               React Frontend (Vite + Monaco Editor)           │
│   Login │ Review (Paste/ZIP/GitHub) │ History │ Dashboard     │
└───────────────────────────┬──────────────────────────────────┘
                            │  REST API + JWT Auth
┌───────────────────────────▼──────────────────────────────────┐
│                    Flask Backend (Python)                      │
│                                                               │
│  ┌─────────────────┐     ┌──────────────────────┐            │
│  │ Static Analyzer  │────▶│    LLM Reviewer       │           │
│  │ 8 rules, <50ms  │     │ Gemini → Groq → fail  │           │
│  │ (AST + regex)    │     │ gracefully             │           │
│  └─────────────────┘     └──────────────────────┘            │
│                                                               │
│  ThreadPoolExecutor │ Flask-Limiter │ JWT Middleware          │
└───────────────────────────┬──────────────────────────────────┘
                            │
┌───────────────────────────▼──────────────────────────────────┐
│              PostgreSQL (users, reviews, issues, batches)      │
└──────────────────────────────────────────────────────────────┘
```

## Features

- **Two-layer analysis** — Static rules catch deterministic patterns; LLM catches semantic bugs, race conditions, resource leaks. Static findings are passed to the LLM to avoid duplicate noise.
- **8 static analysis rules** — Hardcoded secrets, SQL injection, unused variables, bare exceptions, null checks, infinite loops, mutable defaults, naming conventions.
- **Multi-language** — Python (AST-based), JavaScript, Java, C++ (regex-based).
- **GitHub repo scanning** — Browse your repositories, pick files, scan up to 30 files per batch. Uses the Trees API for efficient single-call repo traversal.
- **ZIP batch upload** — Upload a project archive; files are filtered, extracted securely (zip-slip prevention), and analyzed individually.
- **Health score** — 0–100 weighted heuristic (critical: -15, warning: -5, info: -1). Displayed as a custom SVG ring indicator.
- **Diff-aware re-review** — Re-submit edited code to see "X issues resolved, Y new, Z unchanged" instead of a full fresh report.
- **Guest mode** — Recruiters and visitors can try the tool instantly with a pre-loaded buggy code sample. No login, no signup.
- **Admin dashboard** — System-wide stats, LLM provider health monitoring, guest vs. authenticated usage split, daily review trends.
- **Rate limiting** — 10 reviews/hour for authenticated users, 3 per session for guests. Protects both fair usage and free LLM tier quotas.

## Tech Stack

| Layer | Technology | Why |
|---|---|---|
| Frontend | React (Vite), Monaco Editor, Recharts | Monaco gives VS Code-quality editing; Recharts for dashboard charts |
| Backend | Python, Flask | Explicit, lightweight, easy to explain line-by-line in interviews |
| Database | PostgreSQL | Relational data (users→reviews→issues), aggregates, free Supabase hosting |
| Primary LLM | Google Gemini 2.5 Flash | Generous free tier, no credit card, no expiry |
| Fallback LLM | Groq (llama-3.3-70b) | Free tier fallback when Gemini hits rate limits |
| Auth | GitHub OAuth2 + JWT | Session tokens with 24h expiry; guest tokens for anonymous access |
| Deployment | Render + Supabase + Vercel | 100% free tier, no credit card required |

## Setup (Local Development)

### Prerequisites
- Docker & Docker Compose
- Node.js 18+
- A GitHub OAuth App ([create one here](https://github.com/settings/developers))
- A Gemini API key ([get one here](https://aistudio.google.com/apikey)) — free, no credit card

### 1. Clone and configure

```bash
git clone https://github.com/Mayank1x/CodeLens.git
cd CodeLens

# Copy and fill in the environment files
cp .env.example .env       # Edit with your API keys
cp frontend/.env.example frontend/.env  # Edit with your GitHub Client ID
```

### 2. Start the backend (Flask + PostgreSQL)

```bash
docker-compose up
# Flask will be at http://localhost:5000
# PostgreSQL at localhost:5432
```

### 3. Start the frontend

```bash
cd frontend
npm install
npm run dev
# React app at http://localhost:5173
```

### 4. (Optional) Run tests

```bash
cd backend
pip install -r requirements.txt
pytest tests/ -v
```

## API Documentation

| Method | Endpoint | Auth | Purpose |
|---|---|---|---|
| `POST` | `/api/auth/github/callback` | No | Exchange GitHub OAuth code for JWT |
| `POST` | `/api/auth/github/upgrade` | Yes | Upgrade OAuth scope to `repo` |
| `POST` | `/api/auth/guest` | No | Issue a temporary guest JWT |
| `POST` | `/api/review` | Yes | Submit code for async review |
| `GET` | `/api/review/<id>` | Yes | Poll for review status/results |
| `POST` | `/api/review/batch` | Yes | Upload ZIP for batch review |
| `POST` | `/api/review/github` | Yes | Scan a GitHub repository |
| `GET` | `/api/batch/<id>` | Yes | Get batch status and per-file results |
| `GET` | `/api/github/repos` | Yes | List user's GitHub repositories |
| `GET` | `/api/github/repos/<owner>/<repo>/tree` | Yes | Get filtered file tree |
| `GET` | `/api/history` | Yes | Past reviews (paginated) |
| `GET` | `/api/stats` | Yes | User's aggregate statistics |
| `GET` | `/api/admin/stats` | Admin | System-wide statistics |
| `GET` | `/health` | No | Health check |

### Example: Submit a review

```bash
curl -X POST http://localhost:5000/api/review \
  -H "Authorization: Bearer <your-jwt>" \
  -H "Content-Type: application/json" \
  -d '{
    "code": "password = \"secret123\"\nquery = \"SELECT * FROM users WHERE id = \" + user_id",
    "language": "python"
  }'
```

Response (202 Accepted):
```json
{
  "review_id": "a1b2c3d4-...",
  "status": "pending"
}
```

Poll `GET /api/review/a1b2c3d4-...` every 2s until `status` is `"complete"`.

## Design Decisions

See [DESIGN.md](DESIGN.md) for the full design document, including:

- Why Flask over Django
- Why PostgreSQL over MongoDB
- Why Gemini/Groq over paid LLM APIs (sustainability at $0/month)
- Why a two-layer (static + LLM) approach instead of LLM-only
- Why ThreadPoolExecutor over Celery
- Why GitHub Contents API instead of full repo cloning
- Why the health score is a simple weighted heuristic
- Security considerations (token encryption, zip-slip prevention, rate limiting)
- What would change at production scale

## Health Score Formula

Each review starts at **100** and deducts points per issue:

| Severity | Deduction |
|---|---|
| Critical | -15 |
| Warning | -5 |
| Info | -1 |

Score is floored at 0. This is a deliberately simple, explainable heuristic — not a machine-learned model — and the simplicity is a feature, not a limitation. The exact formula is documented here so users know precisely how their score is computed.

## Free Deployment Plan

| Component | Platform | Notes |
|---|---|---|
| Backend | [Render](https://render.com) free web service | 750 hrs/month, auto-deploy from GitHub. Sleeps after inactivity (30-50s cold start). |
| Database | [Supabase](https://supabase.com) free tier | 500MB Postgres, no expiry, no card |
| Frontend | [Vercel](https://vercel.com) free tier | Unlimited static hosting, auto-deploy |
| LLM | Gemini (primary) + Groq (fallback) | Both permanent free tiers, no card |

## Project Structure

```
CodeLens/
├── backend/
│   ├── static_analyzer/     # Phase 1: 8 rule modules + analyzer orchestrator
│   │   ├── rules/           # Individual rule implementations
│   │   ├── analyzer.py      # Runs all rules, deduplicates, sorts
│   │   └── models.py        # Issue dataclass (shared schema)
│   ├── llm_reviewer/        # Phase 2: LLM orchestration
│   │   ├── provider.py      # LLMProvider ABC + Gemini/Groq implementations
│   │   ├── reviewer.py      # Fallback chain, parsing, deduplication
│   │   └── prompt.py        # Prompt construction (isolated for iteration)
│   ├── api/                 # Phase 3: REST endpoints
│   │   ├── routes.py        # All API endpoints
│   │   ├── review_worker.py # Background processing (ThreadPoolExecutor)
│   │   ├── zip_utils.py     # Secure ZIP extraction
│   │   └── github_utils.py  # GitHub Trees/Blobs API integration
│   ├── auth/                # Authentication layer
│   │   ├── middleware.py     # @require_auth decorator
│   │   ├── jwt_utils.py     # JWT create/decode
│   │   ├── github_oauth.py  # OAuth2 code exchange
│   │   └── encryption.py    # Fernet encryption for stored tokens
│   ├── models/              # SQLAlchemy models
│   ├── tests/               # pytest suites (unit + integration)
│   ├── app.py               # Application factory
│   ├── database.py          # SQLAlchemy init
│   └── Dockerfile           # Multi-stage production build
├── frontend/
│   ├── src/
│   │   ├── pages/           # LoginPage, ReviewPage, HistoryPage, DashboardPage, AdminPage
│   │   ├── components/      # Navbar, ProtectedRoute, RepoSelector, FileTreeSelector
│   │   ├── api/client.js    # Centralized fetch wrapper with JWT handling
│   │   ├── context/         # AuthContext (React Context for session state)
│   │   └── utils/           # Constants, severity/category mappings
│   └── index.html
├── docker-compose.yml       # Local dev: Flask + PostgreSQL
├── DESIGN.md                # Architecture and tradeoff decisions
└── .github/workflows/       # CI: pytest on every push
```

## Future Improvements

- **Database migrations** — Replace `db.create_all()` with Flask-Migrate (Alembic) for versioned schema evolution
- **Caching** — Redis cache for repeated submissions (hash the code, return cached results)
- **Celery + Redis** — Replace ThreadPoolExecutor for durable job queue with retries, priority queues, dead letter queues
- **Webhook-based reviews** — Trigger analysis on GitHub push/PR events instead of manual submission
- **AI-generated fix suggestions** — Show concrete code diffs (not just text suggestions) — with user confirmation before applying
- **Test coverage reporting** — Add `pytest-cov` to CI and display coverage badge

## License

MIT
