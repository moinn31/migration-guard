FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends git nodejs npm ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /service
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY server.py .
RUN useradd -m -u 10001 workspace && mkdir /workspace && chown workspace:workspace /workspace
USER workspace
ENV PYTHONUNBUFFERED=1
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8080"]
