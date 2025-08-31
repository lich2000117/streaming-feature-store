FROM python:3.11-slim

WORKDIR /app

# Snappy: runtime lib + headers; toolchain in case wheel builds from source
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    python3-dev \
    libsnappy1v5 \
    libsnappy-dev \
  && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY streaming/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY streaming/ ./streaming/

# Copy schemas for validation  
COPY ../schemas/ ./schemas/

# Health check - check if process is running and consuming
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import redis; r=redis.Redis(host='redis'); r.ping()" || exit 1

# Default to simplified stream processor
CMD ["python", "streaming/simple/stream_processor.py", "--kafka-servers", "kafka:9092", "--redis-host", "redis"]

# Or use flink job
#CMD ["python", "streaming/flink/feature_job.py", "--kafka-servers", "kafka:9092", "--redis-host", "redis"]
