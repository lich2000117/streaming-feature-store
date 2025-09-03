FROM python:3.11-slim as base

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY inference/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy inference service code
COPY inference/ .

# Create directories for models and outputs
RUN mkdir -p training/outputs models logs

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash app \
    && chown -R app:app /app

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

USER app

# Environment variables
ENV PYTHONPATH=/app
ENV MODEL_PATH=training/outputs/model.pkl
ENV FEATURE_NAMES_PATH=training/outputs/feature_names.json
ENV REDIS_HOST=redis
ENV LOG_LEVEL=DEBUG

EXPOSE 8080

# Use exec form for proper signal handling
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
