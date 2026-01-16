FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY . /app
ENV PYTHONPATH=/app
EXPOSE 3000
CMD ["uvicorn", "services.web_gateway.app:app", "--host", "0.0.0.0", "--port", "3000"]
