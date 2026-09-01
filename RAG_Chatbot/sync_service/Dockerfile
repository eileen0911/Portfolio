FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY sync_service/ ./sync_service/
CMD ["python", "-m", "sync_service.scheduler"]
