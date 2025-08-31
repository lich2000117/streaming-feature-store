# Multi-stage Docker build for ML training
FROM python:3.11-slim as base

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY ml/requirements.txt ml/requirements.txt
RUN pip install --no-cache-dir -r ml/requirements.txt

# Copy source code
COPY . .

# Create directories for outputs
RUN mkdir -p ml/outputs ml/models

# Set environment variables
ENV PYTHONPATH=/app
ENV MLFLOW_TRACKING_URI=http://mlflow:5000

# Training stage
FROM base as training

# Set default command
CMD ["python", "ml/train.py"]

# Serving stage (for future use)
FROM base as serving

EXPOSE 8080
CMD ["python", "services/inference/app.py"]
