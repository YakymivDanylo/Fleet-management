FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --upgrade pip setuptools

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY pyproject.toml .
COPY src ./src
RUN pip install --no-deps .

COPY alembic.ini .
COPY alembic ./alembic

RUN useradd --create-home appuser
USER appuser


EXPOSE 8000

CMD ["sh", "-c", "alembic upgrade head && exec uvicorn fleet_management.main:app --host 0.0.0.0 --port 8000"]