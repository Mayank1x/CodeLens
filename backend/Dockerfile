# Multi-stage build for smaller final image
# Stage 1: Install dependencies
FROM python:3.12-slim AS builder

WORKDIR /app

# Install system dependencies for psycopg2 (PostgreSQL adapter)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Stage 2: Runtime image
FROM python:3.12-slim

WORKDIR /app

# Only install the runtime PostgreSQL library (not the build tools)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from builder stage
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

# Copy application code
COPY . .

EXPOSE 5000

# Use gunicorn in production for proper multi-worker serving.
# In development, docker-compose overrides this with `flask run`.
# --timeout 120 because LLM calls can take up to 8 seconds, and we
# want headroom for slow Gemini responses during free-tier cold starts.
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "120", "app:create_app()"]
