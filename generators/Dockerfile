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

# Install Python deps (keep python-snappy in requirements)
COPY generators/requirements.txt .
# (Optional) pin to a known-good: python-snappy==0.7.3
RUN pip install --no-cache-dir -r requirements.txt

# Copy app AFTER deps to leverage layer cache
COPY generators/ ./generators/

COPY ../schemas/ ./schemas/

# (Optional) quick import check while building
# RUN python -c "import snappy; print('snappy OK', snappy.__version__)"
ENTRYPOINT ["python"]
