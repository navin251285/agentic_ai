# One recipe for both lab services. APP_FILE picks the code that runs as service:app.
FROM python:3.12.13-slim
WORKDIR /app
COPY 16/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY 13/customer_api.py /app/customer_api.py
ARG APP_FILE
COPY ${APP_FILE} /app/service.py
RUN useradd --create-home --uid 10001 app
USER app
EXPOSE 8000
CMD ["uvicorn", "service:app", "--host", "0.0.0.0", "--port", "8000"]
