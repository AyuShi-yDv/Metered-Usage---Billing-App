FROM python:3.11.10-slim
RUN useradd --create-home --uid 10001 app
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
USER app
# One worker keeps the in-memory per-account rate limit exact; raise WEB_CONCURRENCY for throughput
# (the outbox publisher is safe with many workers thanks to FOR UPDATE SKIP LOCKED).
ENV WEB_CONCURRENCY=1
CMD ["sh", "-c", "alembic upgrade head && (uvicorn app.admin:app --host 0.0.0.0 --port 8002 &) && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers ${WEB_CONCURRENCY}"]
