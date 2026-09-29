FROM python:3.11.10-slim
RUN useradd --create-home --uid 10001 app
WORKDIR /app
COPY services/ingest/requirements.txt /tmp/ingest-requirements.txt
COPY services/billing/requirements.txt /tmp/billing-requirements.txt
RUN pip install --no-cache-dir -r /tmp/ingest-requirements.txt -r /tmp/billing-requirements.txt
COPY --chown=app:app . .
USER app
