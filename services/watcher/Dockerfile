FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir \
    chromadb \
    sentence-transformers \
    watchdog \
    pyyaml \
    python-dotenv

COPY . .

CMD ["python", "watcher.py"]