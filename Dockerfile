FROM python:3.11-slim

WORKDIR /app

# libpq needed at runtime for psycopg; gcc only to build it, then dropped.
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .

COPY alembic.ini ./
COPY migrations ./migrations

EXPOSE 8000

# `pip install .` above already installs docqa into site-packages, so no
# --app-dir/PYTHONPATH is needed here the way local dev needs it against a
# non-installed checkout. Overridden by docker-compose.yml's `command:` for
# the worker service — this default is the API.
CMD ["uvicorn", "docqa.main:app", "--host", "0.0.0.0", "--port", "8000"]
