FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates && rm -rf /var/lib/apt/lists/*
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY core ./core
COPY schemas ./schemas
COPY services/requirements_manager_worker ./services/requirements_manager_worker
ENV PYTHONPATH=/app
CMD ["python", "-m", "services.requirements_manager_worker.main"]
