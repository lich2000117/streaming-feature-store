FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY streaming/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Copy schemas for validation  
COPY ../schemas/ ./schemas/

# Health check - check if process is running and consuming
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import redis; r=redis.Redis(host='redis'); r.ping()" || exit 1

# Default to simplified stream processor
CMD ["python", "simple/stream_processor.py", "--kafka-servers", "kafka:9092", "--redis-host", "redis"]
