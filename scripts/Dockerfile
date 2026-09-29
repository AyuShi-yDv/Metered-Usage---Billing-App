FROM python:3.11.10-slim
RUN useradd --create-home --uid 10001 app \
    && pip install --no-cache-dir asyncpg==0.30.0
WORKDIR /app
COPY --chown=app:app scripts/seed.py scripts/performance.py ./
USER app
ENTRYPOINT ["python"]
