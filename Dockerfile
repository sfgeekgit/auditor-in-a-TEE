FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir fastapi uvicorn pydantic httpx cryptography

COPY webapp/ ./

EXPOSE 8080

CMD ["python", "api_server.py"]
