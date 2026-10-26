FROM python:3.12.13-slim
WORKDIR /app
COPY 28/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY 28/provider_route.py /app/service.py
RUN useradd --create-home --uid 10001 app
USER app
EXPOSE 8000
CMD ["uvicorn", "service:app", "--host", "0.0.0.0", "--port", "8000"]
