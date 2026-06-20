# Riskified performance-review prototype.
# One image runs the whole pipeline: ingestion, deck generation, the Streamlit agent, and tests
# (each docker-compose service overrides the command).
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
# Branding: assets/riskified_logo.png is the single logo — embedded in the PPTX decks and shown
# in the Streamlit UI. .streamlit holds the brand theme.
COPY assets/ ./assets/
COPY .streamlit/ ./.streamlit/

# Default: run the ingestion pipeline. Override per docker-compose service.
CMD ["python", "scripts/ingest.py"]
