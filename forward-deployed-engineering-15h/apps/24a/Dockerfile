# One image for the customer API mock and the two batch workers (lab, invented data). Versions pinned.
FROM python:3.12.13-slim
WORKDIR /app
RUN pip install --no-cache-dir "fastapi==0.162.0" "uvicorn==0.54.0" "httpx==0.28.1" "tenacity==9.1.4"
COPY erp_mock.py batch_worker.py /app/
RUN useradd --create-home --uid 10001 app
USER app
