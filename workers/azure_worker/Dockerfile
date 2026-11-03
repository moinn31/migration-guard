FROM python:3.11-slim

# Install git and essential tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -g 10001 appuser && \
    useradd -u 10001 -g appuser -m -d /home/appuser -s /bin/bash appuser

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy worker application
COPY worker.py .
RUN chown -R appuser:appuser /app

USER appuser

ENV PYTHONUNBUFFERED=1

CMD ["python", "worker.py"]
