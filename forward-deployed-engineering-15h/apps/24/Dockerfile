# One recipe for both versions. APP_FILE picks the code that goes into the image.
FROM python:3.12.13-slim
WORKDIR /app
RUN pip install --no-cache-dir "fastapi==0.162.0" "uvicorn==0.54.0"
ARG APP_FILE
COPY ${APP_FILE} /app/service.py
RUN useradd --create-home --uid 10001 app
USER app
EXPOSE 8000
CMD ["uvicorn", "service:app", "--host", "0.0.0.0", "--port", "8000"]
