FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates && rm -rf /var/lib/apt/lists/*
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY core ./core
COPY schemas ./schemas
COPY services ./services
COPY prompts ./prompts
COPY demo ./demo
COPY tests ./tests
COPY pytest.ini ./
ENV PYTHONPATH=/app
CMD ["python", "-m", "services.orchestrator.main"]
