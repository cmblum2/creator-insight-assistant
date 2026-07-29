FROM python:3.12-slim
WORKDIR /app
# COPY and RUN are separate instructions. Copy requirements first so the pip layer caches.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# bake synthetic data + vector index + the holdout ledger and drift baseline so the demo is fully
# populated on first load (economics/holdout/drift all have data)
RUN python scripts/gen_data.py && python -m app.ingest && \
    python -c "from app.holdout import init_forward_ledger; init_forward_ledger()" && \
    python -c "from app.drift import drift_report; drift_report()"
EXPOSE 8000
HEALTHCHECK CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1
# ANTHROPIC_API_KEY is passed at RUNTIME (docker run -e ...), never baked into the image.
CMD ["uvicorn", "app.server:api", "--host", "0.0.0.0", "--port", "8000"]
