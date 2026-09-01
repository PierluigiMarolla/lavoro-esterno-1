FROM python:3.13-slim

# Dipendenze di sistema minime richieste da psycopg2 (build) e Pillow/lxml (parsing/immagini).
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    libjpeg62-turbo-dev \
    zlib1g-dev \
    libxml2-dev \
    libxslt1-dev \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml ./
# Copiamo il codice prima dell'installazione editable perché il progetto usa
# `packages = ["app"]` in hatchling: senza la cartella app/ presente, `pip install -e .`
# fallirebbe nel risolvere il pacchetto.
COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./alembic.ini

RUN pip install --no-cache-dir -e .

# Chromium headless per Scrapling DynamicFetcher/StealthyFetcher.
# DynamicFetcher usa Playwright; StealthyFetcher usa Patchright.
RUN playwright install --with-deps chromium \
    && patchright install chromium

EXPOSE 8000

# I worker Celery (scraping/media/ai) e Celery Beat riusano questa stessa immagine
# con comando diverso, definito nel docker-compose a livello di repo (non gestito qui).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
