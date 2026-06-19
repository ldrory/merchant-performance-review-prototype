# Riskified performance-review prototype.
# Installs the full project dependencies so the image is ready for all phases
# (Phase 1 ingestion now; Phase 2 decks / Phase 3 Streamlit agent later).
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

WORKDIR /app

# Dependencies first for better layer caching.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code + raw inputs.
COPY src/ ./src/
COPY scripts/ ./scripts/
COPY tests/ ./tests/
COPY data/raw/ ./data/raw/
# Branding: PNG logo embedded in decks + assets/streamlit logo for the agent UI.
COPY assets/ ./assets/
COPY .streamlit/ ./.streamlit/
COPY ["Riskified Logo.webp", "./"]

# Default: run the ingestion pipeline. Override per docker-compose service.
CMD ["python", "scripts/ingest.py"]
