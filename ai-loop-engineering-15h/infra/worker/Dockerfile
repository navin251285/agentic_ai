# Worker image for lesson 28b. Pinned base image and library versions (never latest).
FROM python:3.12.16-slim
RUN pip install --no-cache-dir "psycopg[binary]==3.3.6" "tenacity==9.1.4"
WORKDIR /app
COPY worker.py .
CMD ["python", "-u", "worker.py"]
