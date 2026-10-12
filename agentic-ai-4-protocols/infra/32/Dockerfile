# Trackr replica image for lesson 32: a pinned Python base and the versions the lesson was tested with.
# The build context is the flat folder the notebook prepares (data/32/build): the apps/32 files,
# tut_env.py and the issues file as issues.json. No keys and no model code go into the image.
# Lab only: the container runs as root so it can write the bind-mounted SQLite file in data/32.
# Production: a volume owned by a non-root user, and the image's USER set to that user.
FROM python:3.12-slim-bookworm
RUN pip install --no-cache-dir "mcp==2.3.0" "a2a-sdk[http-server,sqlite]==1.2.2" "fastapi==0.143.0" "uvicorn==0.54.0"
COPY . /app
WORKDIR /app
ENV PYTHONPATH=/app PYTHONUNBUFFERED=1
