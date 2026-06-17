# AI Code Review Tool — Build Specification

## Project Overview

Build a full-stack web application called **CodeReview AI** that analyzes source code submitted by a user and returns structured feedback combining two layers of analysis: a custom-built static analysis engine (rule-based, no external API) and an LLM-based semantic analysis layer (via free-tier Gemini/Groq APIs — see Tech Stack section for why). The tool should feel like a lightweight version of tools like CodeRabbit or SonarQube, built from scratch.

This is a portfolio project for a final-year CS student targeting software engineering roles at top tech companies. Code quality, architectural clarity, and explainability matter more than feature count. Prioritize a working, well-documented system over a feature-bloated one.

---

## Tech Stack (do not substitute without asking)

- **Frontend:** React (Vite), Monaco Editor for the code input component
- **Backend:** Python, Flask (REST API)
- **Database:** PostgreSQL (use a free-tier hosted instance — see deployment section)
- **LLM:** Google Gemini API (`gemini-2.5-flash` via Google AI Studio) as the primary provider — it has a generous no-credit-card free tier with a large daily request quota. Use Groq (`llama-3.3-70b-versatile` or similar) as a fallback/secondary provider if Gemini's rate limit is hit. Abstract both behind a single `LLMProvider` interface so providers can be swapped without touching calling code.
- **Auth:** GitHub OAuth2 + JWT for session tokens
- **Deployment target:** 100% free-tier hosting only — see "Free deployment plan" section below
- **Containerization:** Docker + docker-compose for local dev (Flask + Postgres)

### Why Gemini instead of Claude/OpenAI for this project
Claude and OpenAI APIs are pay-as-you-go with no meaningful ongoing free tier (Claude gives a small one-time credit grant only), which means every demo, every test, and every recruiter who tries the live link would cost real money. Gemini 2.5 Flash's free tier has no expiry and needs no credit card, which makes it sustainable for a project that needs to stay live and demoable indefinitely on a student budget. This is also a legitimate, honest design decision to mention in interviews: "I chose Gemini Flash specifically so the project could run sustainably on a $0 budget without rate-limit-driven outages during demos."

---

## Build phases (build and verify in this order — do not skip ahead)

### Phase 1 — Static analysis engine (no external APIs)

Build a standalone Python module `static_analyzer/` that takes a code string and a language identifier and returns a list of `Issue` objects. Implement these rules from scratch (use Python's `ast` module for Python; regex-based pattern matching is acceptable for other languages):

1. Hardcoded secrets/credentials (API keys, passwords in plain strings)
2. SQL injection risk (string concatenation/formatting inside query execution calls)
3. Unused variables (Python: via AST; flag declared-but-never-referenced names)
4. Bare/broad exception handling (`except:` with no type, or catching `Exception` and silently passing)
5. Missing null/None checks before attribute access where a prior assignment could be None
6. Potential infinite loops (`while True` with no visible break statement in scope)
7. Mutable default arguments (Python-specific: `def f(x=[])`)
8. Inconsistent naming convention (e.g., mixing snake_case and camelCase in the same file)

Each rule must return: `line_number`, `severity` (`critical` | `warning` | `info`), `category` (`bug` | `security` | `style` | `performance`), `message`, `suggestion`.

Write unit tests for every rule (pytest) using small code snippets that should and should not trigger each rule. This static engine must run in under 50ms for a 200-line file with zero network calls.

**Deliverable for this phase:** a CLI script `analyze.py file.py` that prints all issues found, plus a passing pytest suite.

---

### Phase 2 — LLM semantic analysis layer

Build `llm_reviewer/` module that:

- Accepts the code, language, and the list of issues already found by the static analyzer
- Constructs a prompt instructing the LLM to find issues NOT already caught by static analysis (explicitly pass the static findings into the prompt so the LLM avoids duplicating them)
- Requests a strict JSON response matching the same `Issue` schema as Phase 1
- Parses and validates the JSON response (handle malformed JSON gracefully — retry once, then fail gracefully with a clear error rather than crashing)
- Has a configurable timeout (8 seconds) and falls back to static-only results if the LLM call fails or times out
- If the primary provider (Gemini) returns a rate-limit error (HTTP 429), automatically retry the same request against the fallback provider (Groq) before giving up — this fallback chain is itself a good interview talking point about building resilient systems on free infrastructure

Abstract the LLM provider behind a simple interface (`LLMProvider` base class) with `GeminiProvider` and `GroqProvider` implementations, so providers can be swapped or chained without touching calling code. Both providers' API keys come from free, no-credit-card-required signups (Google AI Studio and Groq Console respectively) — document this clearly in the README so the project never requires anyone to enter billing details to run it.

**Deliverable for this phase:** the CLI script now also calls the LLM layer and merges/deduplicates results with the static findings, printing a combined report.

---

### Phase 3 — Flask REST API

Build the API with these endpoints:

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/auth/github/callback` | Exchange GitHub OAuth code for a JWT |
| POST | `/api/review` | Submit code (or a GitHub file URL) for review; returns a `review_id` immediately, processes async |
| GET | `/api/review/<review_id>` | Poll for review status/results |
| GET | `/api/history` | List past reviews for the authenticated user, paginated |
| GET | `/api/stats` | Aggregate stats: most common issue categories, total reviews run, average issues per review |

Requirements:
- JWT-based auth middleware protecting all endpoints except the OAuth callback
- Rate limiting: 10 reviews per hour per authenticated user (Flask-Limiter). This also protects the free LLM tier's daily quota from being exhausted by one user — mention in the README that the limit exists both for fair usage AND to keep the project running at zero cost
- Async processing for `/api/review` — use a simple background thread or task queue (Celery is optional/stretch goal; a simple `ThreadPoolExecutor` is acceptable for v1) so the API responds immediately rather than blocking on the LLM call
- Input validation: reject code submissions over 5,000 lines or 500KB with a clear 400 error
- All review results persisted to PostgreSQL (see schema below)
- CORS configured correctly for the React frontend origin only
- Structured error responses (consistent JSON error shape across all endpoints)
- Environment variables for all secrets (`.env` file, never hardcoded) — provide a `.env.example`

**Database schema (PostgreSQL):**

```sql
CREATE TABLE users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  github_id VARCHAR(64) UNIQUE NOT NULL,
  username VARCHAR(128) NOT NULL,
  avatar_url TEXT,
  created_at TIMESTAMP DEFAULT now()
);

CREATE TABLE reviews (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES users(id),
  language VARCHAR(32) NOT NULL,
  code_snippet TEXT NOT NULL,
  status VARCHAR(16) NOT NULL DEFAULT 'pending', -- pending | processing | complete | failed
  created_at TIMESTAMP DEFAULT now(),
  completed_at TIMESTAMP
);

CREATE TABLE issues (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  review_id UUID REFERENCES reviews(id) ON DELETE CASCADE,
  source VARCHAR(16) NOT NULL, -- 'static' | 'llm'
  line_number INTEGER,
  severity VARCHAR(16) NOT NULL,
  category VARCHAR(16) NOT NULL,
  message TEXT NOT NULL,
  suggestion TEXT
);

CREATE INDEX idx_reviews_user_id ON reviews(user_id);
CREATE INDEX idx_issues_review_id ON issues(review_id);
```

**Deliverable for this phase:** a running Flask app (`docker-compose up` brings up Flask + Postgres), all endpoints testable via Postman/curl, with a Postman collection or `requests.http` file included.

---

### Phase 4 — React frontend

Pages/components needed:

1. **Login page** — "Sign in with GitHub" button, redirects through OAuth flow
2. **Review page** (main page) — Monaco Editor for code input, language dropdown, "Review code" button, results panel showing issues grouped by severity with inline code highlighting at the relevant line, each issue showing category badge, message, and suggestion
3. **History page** — table/list of past reviews with date, language, issue count, status; clicking one opens the full result
4. **Dashboard/stats page** — simple charts (use Chart.js or Recharts) showing issue category breakdown and trends over time

Requirements:
- Clean, professional UI — no default unstyled HTML. Use a simple, consistent design system (Tailwind CSS is fine)
- Loading states while a review is processing (poll `/api/review/<id>` every 2 seconds until status is `complete`)
- Error states clearly shown to the user (rate limit hit, invalid code, server error)
- Responsive enough to look good on a laptop screen (mobile support is not required)
- README includes screenshots of each page

**Deliverable for this phase:** a working frontend that talks to the Flask API end to end, from login through to viewing a completed review.

---

### Phase 5 — Deployment, docs, and polish

**Free deployment plan (verified options, no credit card required, as of mid-2026):**

| Component | Platform | Notes |
|---|---|---|
| Backend (Flask) | Render free web service | 750 free hours/month, no card needed. App sleeps after inactivity and wakes on next request (mention this honestly in the README as a known limitation, not a flaw to hide) |
| Database (PostgreSQL) | Supabase free tier | Render's free Postgres expires after 30 days, so use Supabase instead — it provides a permanent free Postgres instance (500MB) with no card required and no expiry |
| Frontend (React) | Vercel free tier | Generous permanent free tier for static/frontend hosting, no card required |
| LLM | Gemini (primary) + Groq (fallback) | Both have permanent no-card free tiers, as established above |

Steps:
1. Deploy Flask backend to Render as a free web service, connected to GitHub for auto-deploy on push
2. Create a free Supabase project, get the PostgreSQL connection string, set it as an environment variable on Render
3. Deploy React frontend to Vercel, connected to the same GitHub repo
4. Set all API keys (Gemini, Groq, GitHub OAuth, JWT secret) as environment variables on Render — never commit them
5. Document the Render free-tier cold-start behavior in the README (first request after inactivity can take 30-50 seconds) so it doesn't look like a bug during a live demo — frame it honestly: "Note: the backend is hosted on a free tier and may take up to a minute to wake up if it hasn't been used recently."

6. Write a comprehensive `README.md` containing:
   - One-paragraph project summary
   - Architecture diagram (can be a simple ASCII or Mermaid diagram)
   - Setup instructions (local dev with docker-compose)
   - API documentation (endpoints, request/response examples)
   - A "Design decisions" section explaining: why Flask over Django, why PostgreSQL over MongoDB, why Gemini/Groq over paid LLM APIs (sustainability and zero ongoing cost), why a two-layer (static + LLM) approach instead of LLM-only, how rate limiting works, how the system would scale to more users
   - Screenshots
   - Live demo link, with the cold-start note above
7. Get at least 15–20 people (classmates, friends) to actually use it and submit real code, to be able to honestly say "used by X real users" on the resume
8. Write a short design doc (1 page) as a separate file: what tradeoffs were made and why, what would be done differently at scale (e.g., move async processing to Celery + Redis, add caching for repeated submissions, upgrade off free tiers, shard the database by user, add a proper job queue)

---

## What NOT to build (explicitly out of scope for v1)

- No multi-file/whole-repo analysis in v1 — single file or pasted snippet only (mention "whole-repo analysis" as a documented future improvement)
- No support for more than 4 languages initially (Python, JavaScript, Java, C++)
- No payment/billing system
- No team/organization accounts — individual users only
- No real-time collaborative review (that's a different project)

---

## Critical instruction for the coding agent

Build this in the phase order listed above. After completing each phase, pause and produce a brief summary of what was built and why specific implementation choices were made (e.g., "used ThreadPoolExecutor instead of Celery because..."). Do not skip ahead to later phases before earlier phases are verified working. Prioritize code that is readable and well-commented over clever/compressed code, since this project will be explained line-by-line in technical interviews. Every non-trivial design decision should be accompanied by a one-sentence comment explaining the reasoning, not just what the code does.
