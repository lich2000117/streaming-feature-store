FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY feast/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY feast/ .

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import feast; print('Feast ready')"

# Default to feast serve
CMD ["feast", "serve", "--host", "0.0.0.0", "--port", "6566"]
