FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml poetry.lock ./
COPY maildrain/ ./maildrain/

RUN pip install --no-cache-dir . \
 && useradd --no-create-home --shell /bin/false maildrain

USER maildrain

CMD ["maildrain"]
