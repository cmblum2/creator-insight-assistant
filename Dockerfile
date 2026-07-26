FROM python:3.12-slim
WORKDIR /app
# COPY and RUN are separate instructions. Copy requirements first so the pip layer caches.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN python scripts/gen_data.py && python -m app.ingest   # bake synthetic data + index
EXPOSE 8000
HEALTHCHECK CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1
# ANTHROPIC_API_KEY is passed at RUNTIME (docker run -e ...), never baked into the image.
CMD ["uvicorn", "app.server:api", "--host", "0.0.0.0", "--port", "8000"]
