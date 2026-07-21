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
| POST | `/api/review` | Submit a single pasted code snippet for review; returns a `review_id` immediately, processes async |
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

### Phase 5 — Multi-file ingestion, GitHub repo scanning, and depth features

This phase extends the existing single-file pipeline (Phases 1–2) to handle multiple files at once, without modifying the analysis engine itself. Build sub-parts in this order:

**5a — Folder/zip upload**

- New endpoint: `POST /api/review/batch` — accepts a `.zip` file (`multipart/form-data`)
- Flask extracts the zip into a temp directory. **Security requirement: sanitize every extracted file path before writing to disk** to prevent zip-slip path traversal (reject or strip any path containing `../` or resolving outside the target temp directory)
- Walk the extracted directory tree; apply the same extension-to-language filter defined in 5b (Python, JavaScript, Java, C++ only — see table below). Skip `node_modules/`, `.git/`, `__pycache__/`, `venv/`, binary files, and files over 500KB. Files with unsupported extensions are skipped silently (not an error) and counted in the "X of Y files scanned" summary shown to the user, same as in 5b
- For each remaining file, run the existing Phase 1 + Phase 2 pipeline (no changes to that code — reuse it as-is)
- Hard cap: max 30 files per batch submission (protects the free LLM daily quota); return a clear error if exceeded, suggesting the user select a smaller subset

**5b — GitHub repo scanning (public and private)**

- New endpoint: `POST /api/review/github` — accepts a GitHub repo URL (public or private, owned by or accessible to the authenticated user)
- **OAuth scope change:** the GitHub OAuth flow from Phase 3 must request the `repo` scope (not just `read:user`) to allow reading private repository contents. This is a broader permission grant than basic login, so:
  - Make this scope request explicit and separate from the login flow if possible — e.g., a clear "Connect GitHub repos" action distinct from "Sign in," so the user understands exactly why the broader permission is being requested
  - Document in the README, visibly, what the `repo` scope grants (read access to the user's repositories, including private ones) and why it's needed
  - Never log, store, or transmit repo *contents* anywhere beyond what's needed for the immediate review — only the analysis results are persisted to the database, not full repo contents
- Use the GitHub Contents API (not a full `git clone`) to list and fetch files — lighter weight than cloning, and works well for a single-file-at-a-time pipeline. The same authenticated API call works for both public and private repos once the token has `repo` scope — GitHub's API handles the permission check transparently based on the token's access
- Use the authenticated user's GitHub OAuth token (already obtained in Phase 3, now with `repo` scope) for these API calls — authenticated requests get 5,000/hour vs. 60/hour unauthenticated
- **Handling mixed-language repos (important — real repos are never single-language):** apply this extension-to-language mapping when walking the repo tree:

  | Extension | Language | Analyzed? |
  |---|---|---|
  | `.py` | Python | Yes — full static + LLM pipeline |
  | `.js`, `.jsx` | JavaScript | Yes — full static + LLM pipeline |
  | `.java` | Java | Yes — full static + LLM pipeline |
  | `.cpp`, `.cc`, `.hpp`, `.h` | C++ | Yes — full static + LLM pipeline |
  | everything else (`.md`, `.json`, `.yml`, `.lock`, `.css`, `.html`, images, etc.) | — | No — skipped silently, not flagged as an error |

  A typical repo scan will therefore only review a subset of its files — this is expected and correct behavior, not a bug. The batch results UI must clearly communicate this: show a summary line like "Scanned 18 of 47 files (29 skipped: unsupported file type)" so the user understands why their `README.md` or `package.json` wasn't reviewed, rather than wondering if something failed
  - Apply the same file filter (ignore `node_modules/`, `.git/`, etc.) and 30-file cap as 5a, counted only against files that pass the language filter
- Reuse the same per-file pipeline and aggregation logic as 5a — the only difference between 5a and 5b is how files are *obtained*, not how they're analyzed

**A note on testing with real users:** since this feature can access a user's private repos, be thoughtful when asking friends to test it — make sure they understand exactly what access they're granting before connecting their GitHub account, and consider testing this specific feature primarily with your own account rather than asking many people to grant broad repo access to a student project.

**5c — Batch aggregation and schema update**

Add a `batches` table to track multi-file submissions:

```sql
CREATE TABLE batches (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES users(id),
  source VARCHAR(16) NOT NULL, -- 'zip' | 'github'
  source_url TEXT, -- repo URL if source = 'github', null otherwise
  status VARCHAR(16) NOT NULL DEFAULT 'pending',
  total_files INTEGER NOT NULL,
  created_at TIMESTAMP DEFAULT now(),
  completed_at TIMESTAMP
);
```

Add `batch_id UUID REFERENCES batches(id)` (nullable) to the existing `reviews` table, so a batch submission creates multiple `reviews` rows linked to one `batch`. New endpoint `GET /api/batch/<batch_id>` returns aggregated status and per-file results grouped together.

**5d — Code health score**

Add a simple computed score (0–100) per review and per batch: start at 100, subtract a weight per issue based on severity (e.g., critical: -15, warning: -5, info: -1), floor at 0. Display this prominently at the top of the results UI. Document the exact formula in the README — this is a deliberately simple, explainable heuristic, not a machine-learned score, and that's fine; be ready to say so directly if asked.

**5e — Diff-aware re-review (stretch goal within this phase)**

When a user re-submits code for a file they've already reviewed in the same session, compute a basic line-level diff against the previous submission (Python's built-in `difflib` is sufficient — no need for a new library). Only re-run the static analyzer and LLM call on changed line ranges (plus a few lines of surrounding context for accuracy). Show the new result as "X issues resolved, Y new issues, Z unchanged" rather than a full fresh report. This is the most novel feature in the project — most student tools are one-shot only, so this demonstrates thinking about realistic developer workflow rather than a single demo pass.

**Frontend additions for this phase:**
- A new "Upload folder" and "Scan GitHub repo" option alongside the existing paste-code flow on the Review page
- A batch results view: list of files with individual scores, expandable to see per-file issues (reuse the existing single-file results component)
- The health score displayed as a simple badge/number at the top of both single-file and batch results

**Deliverable for this phase:** a user can upload a zip or paste a GitHub repo URL, see a batch of files analyzed with an aggregated report, each file/batch shows a health score, and re-submitting edited code shows a diff-aware delta instead of a full re-review.

---

### Phase 6 — Guest access, admin dashboard, and design system

This phase addresses three practical gaps: recruiters viewing the deployed link without a GitHub account, an internal admin view, and avoiding a generic "AI-generated" visual look.

**7a — Guest/demo mode (build this first — solves the most urgent problem)**

The core issue: a recruiter clicking your deployed link will not create a GitHub account or grant OAuth permissions just to see your project. The login wall must not be the first thing they hit.

- Add a **"Try as Guest"** button on the login page, prominently placed, ideally more visually prominent than the GitHub login button itself
- Guest mode behavior: assigns a temporary, anonymous session (not tied to a real `users` row with a `github_id` — use a lightweight guest session, e.g. a signed cookie or short-lived JWT with a `guest: true` claim, no database user record needed)
- Guest users CAN submit real code through the paste-code flow (Phase 1-2 pipeline) and see real results — this is important, it should not be a screenshot or a fake demo, it should be the actual tool working
- Guest users CANNOT use GitHub repo scanning (5b) or folder upload requiring storage (5a can still work, since it doesn't need GitHub auth — only repo scanning specifically requires real OAuth)
- Guest mode should have a tighter rate limit than authenticated users (e.g., 3 reviews per session instead of 10/hour) to protect the free LLM quota from anonymous abuse
- Pre-load the Review page, when in guest mode, with one example "buggy" code snippet already in the editor (a small Python function with 2-3 obvious issues), so a recruiter can click "Review code" immediately without even typing anything — first impression in under 5 seconds
- Add a small persistent banner in guest mode: "You're viewing in guest mode — sign in with GitHub to save history and scan your own repos" — this signals the fuller feature set exists without forcing it

**7b — Admin dashboard (internal, your own view)**

A simple `/admin` route, protected separately from normal auth (e.g., a hardcoded check against your own `github_id` or a separate admin password env variable — does not need a full role-based permission system for v1). Purpose: a single page only you can see, showing:
- Total reviews run (guest + authenticated), broken down by day
- Most common issue categories found across all reviews (this is genuinely interesting data and could become a quotable resume stat: "analysis of N reviews showed X% of submissions had unhandled exception issues")
- Current LLM provider health (how often Gemini succeeded vs. fell back to Groq vs. failed entirely) — useful for you to monitor free-tier quota usage in real time
- Guest vs. authenticated usage split

This page is not meant to be polished or recruiter-facing — it's an operational tool, but having one at all is a good talking point: "I built a small internal dashboard to monitor real usage patterns and free-tier quota health post-launch."

**7c — Design system (avoid the generic AI-generated look)**

The default output of most AI page-builders tends toward a recognizable look: centered hero sections, purple-to-blue gradients, generic SaaS-template card grids, and rounded-everything with no real typographic hierarchy. Avoid this deliberately:

- Pick ONE accent color with intention (not a gradient) and use it sparingly — for a code tool, a desaturated, slightly technical palette works well (e.g., deep slate/graphite background with a single sharp accent like amber or a muted green, rather than purple-on-white)
- Use a monospace font for anything code-related (line numbers, issue messages referencing code, the score) and a distinct sans-serif for UI chrome — this single choice does a lot to make the tool feel "built for developers" rather than "generic AI dashboard"
- Avoid the default centered-hero-with-gradient-blob layout for the landing/login page; a left-aligned or asymmetric layout reads as more deliberate
- Keep border-radius consistent and modest (not the very rounded "bubbly" look common in AI-generated UIs) — sharper, more precise corners suit a developer tool
- Avoid stock icon sets used at default size/weight everywhere — pick one icon style (e.g., Lucide, which is already available in this stack) and use icons sparingly, not as decoration on every card
- The health score and severity badges are a good place to add a small custom visual touch (e.g., a simple radial/ring indicator for the score rather than a plain number) — this kind of small custom component is what makes a project feel designed rather than templated

**Deliverable for this phase:** a recruiter can open the deployed link, click "Try as Guest," immediately see a pre-loaded code example, click review, and see real results — all without creating an account. The UI reads as a considered developer tool rather than a generated template. A private `/admin` route exists for your own monitoring.

---

### Phase 6.5 — Tests and CI (last addition before deployment)

This is intentionally small in scope — the goal is confidence, not coverage percentage.

- Write integration tests (pytest + Flask's test client) covering the core happy paths: submit a single-file review and verify a result comes back with the expected shape, submit a batch zip and verify aggregation works, hit a protected endpoint without auth and verify a 401, exceed the rate limit and verify a 429
- Write at least one test that deliberately simulates an LLM failure (mock the Gemini call to raise an exception) and verifies the system falls back to Groq, then to static-only results, without crashing
- Set up a GitHub Actions workflow (`.github/workflows/test.yml`) that runs the full pytest suite (Phase 1 unit tests + these integration tests) on every push and pull request
- Add a passing/failing badge to the top of the README, linked to the Actions workflow — this is a small visual detail that signals engineering maturity at a glance

**This is the last phase that adds new scope.** No further features should be added after this phase — the next steps are the review pass and deployment, not more building.

---

### Phase 7 — Deployment, docs, and polish

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
6. Since Phase 5 extracts uploaded zips to a temp directory, ensure that directory is cleaned up after each batch review completes (or fails) — Render's free tier has ephemeral, limited disk, and leftover temp files across requests could fill it up over time

7. Write a comprehensive `README.md` containing:
   - One-paragraph project summary
   - Architecture diagram (can be a simple ASCII or Mermaid diagram)
   - Setup instructions (local dev with docker-compose)
   - API documentation (endpoints, request/response examples)
   - A "Design decisions" section explaining: why Flask over Django, why PostgreSQL over MongoDB, why Gemini/Groq over paid LLM APIs (sustainability and zero ongoing cost), why a two-layer (static + LLM) approach instead of LLM-only, how rate limiting works, why the GitHub Contents API was used instead of full repo cloning, why the health score is a simple weighted heuristic rather than a learned model, why guest mode exists (recruiter/reviewer accessibility without requiring OAuth), how the system would scale to more users
   - Screenshots
   - **Live demo link presented prominently at the very top of the README, explicitly labeled** e.g. "🔗 Live Demo (no login required — click 'Try as Guest')" — this is the single most important line in the README, since it's what determines whether a recruiter actually tries the tool, with the cold-start note immediately beside it
8. Get at least 15–20 people (classmates, friends) to actually use it and submit real code, to be able to honestly say "used by X real users" on the resume
9. Write a short design doc (1 page) as a separate file: what tradeoffs were made and why, what would be done differently at scale (e.g., move async processing to Celery + Redis for durable multi-file job queuing, add caching for repeated submissions, upgrade off free tiers, shard the database by user, support private GitHub repos)

---

## What NOT to build (explicitly out of scope, even with Phase 5 added)

- No support for more than 4 languages initially (Python, JavaScript, Java, C++)
- Private GitHub repos ARE supported in Phase 5b via the `repo` OAuth scope — but only for repos the authenticated user already has access to via their own GitHub account; no support for accessing arbitrary other users' private repos, org-wide bulk scanning, or repos requiring separate permission grants beyond the user's own token
- No payment/billing system
- No team/organization accounts — individual users only
- No real-time collaborative review (that's a different project)
- No AI-generated auto-fixes that directly modify code — the tool suggests, it does not auto-apply changes (this is both a scope decision and a safety one: auto-applying AI-suggested code changes without review is exactly the kind of thing that goes wrong in production)

---

## Critical instruction for the coding agent

Build this in the phase order listed above. After completing each phase, pause and produce a brief summary of what was built and why specific implementation choices were made (e.g., "used ThreadPoolExecutor instead of Celery because..."). Do not skip ahead to later phases before earlier phases are verified working. Prioritize code that is readable and well-commented over clever/compressed code, since this project will be explained line-by-line in technical interviews. Every non-trivial design decision should be accompanied by a one-sentence comment explaining the reasoning, not just what the code does.

**Scope is frozen at Phase 6.5.** If asked to add functionality beyond what is specified in Phases 1 through 6.5, push back and suggest it be noted in the README as a "future improvement" instead of being built — this project's scope was deliberately finalized, and Phase 7 (deployment) is meant to be the last phase, not a checkpoint to add more from.
