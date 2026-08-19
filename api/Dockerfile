# Python 3.12 deliberately: ADK and the GCP client libraries are tested against
# it, and the host machine running 3.14 does not change what ships.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# One image, three entrypoints. The command is overridden per Cloud Run service
# and for the Job; this default serves the API.
ENV PORT=8080
CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT}
