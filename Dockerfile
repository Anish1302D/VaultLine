FROM python:3.11-slim

# Set environment variables:
# - PYTHONUNBUFFERED: Ensure logs stream immediately
# - PYTHONDONTWRITEBYTECODE: Avoid writing .pyc files
# - VAULTLINE_NO_LLM=1: Default to deterministic, sub-50ms offline mode
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    VAULTLINE_NO_LLM=1 \
    PYTHONPATH=/app

WORKDIR /app

# Install curl/utilities if needed
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code and data
COPY data/ data/
COPY seller/ seller/
COPY buyers/ buyers/
COPY experiments/ experiments/
COPY tests/ tests/
COPY outputs/ outputs/
COPY harness.py .
COPY evaluate.py .
COPY AGENT_CARD.json .
COPY README.md .
COPY Makefile .

# Expose Streamlit port if running interactive demo
EXPOSE 8501

# Default command: run full test suite with 0 violations verification
CMD ["pytest", "-v", "tests/"]
