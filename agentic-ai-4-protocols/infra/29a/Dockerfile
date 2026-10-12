# Sandbox image for lesson 29a: a pinned Python base and the mcp version the lesson was tested with.
FROM python:3.12-slim-bookworm
RUN pip install --no-cache-dir mcp==2.3.0 \
 && useradd --uid 10001 --create-home --home-dir /home/app app
USER 10001
WORKDIR /app
