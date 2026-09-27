FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Don't run as root inside the container. The log directory is a shared volume read by OpsMind.
RUN useradd --create-home appuser \
    && mkdir -p /var/log/product-api && chown appuser /var/log/product-api
USER appuser

EXPOSE 8000

# --no-access-log: our own middleware writes structured JSON request logs instead.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
