FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates && rm -rf /var/lib/apt/lists/*
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY core ./core
COPY schemas ./schemas
COPY services/cost_worker ./services/cost_worker
ENV PYTHONPATH=/app
CMD ["python", "-m", "services.cost_worker.main"]
