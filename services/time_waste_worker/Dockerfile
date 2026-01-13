FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates && rm -rf /var/lib/apt/lists/*
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY core ./core
COPY schemas ./schemas
COPY services/time_waste_worker ./services/time_waste_worker
ENV PYTHONPATH=/app
CMD ["python", "-m", "services.time_waste_worker.main"]
