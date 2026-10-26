# One recipe for both lab services. APP_FILE picks the code that goes into the image.
FROM python:3.12.13-slim
WORKDIR /app
COPY 14/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
ARG APP_FILE
COPY ${APP_FILE} /app/service.py
RUN useradd --create-home --uid 10001 app
USER app
EXPOSE 8000
CMD ["uvicorn", "service:app", "--host", "0.0.0.0", "--port", "8000"]
