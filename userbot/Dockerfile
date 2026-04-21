FROM python:3.11-slim

WORKDIR /app

RUN adduser --disabled-password --gecos "" appuser && \
    mkdir -p /data/pdfs && \
    chown -R appuser:appuser /data

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

USER appuser

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

CMD ["python", "-m", "src.main"]
