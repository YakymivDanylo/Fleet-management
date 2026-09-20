FROM python:3.13-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN python -m venv --without-pip /opt/venv

WORKDIR /app

COPY requirements.txt .
RUN pip --python /opt/venv/bin/python install -r requirements.txt

COPY pyproject.toml .
COPY src ./src
RUN pip --python /opt/venv/bin/python install --no-deps .


FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv

COPY alembic.ini .
COPY alembic ./alembic

RUN /usr/local/bin/python -m pip uninstall -y pip setuptools wheel \
    && useradd --create-home appuser

USER appuser

EXPOSE 8000

CMD ["sh", "-c", "alembic upgrade head && exec uvicorn fleet_management.main:app --host 0.0.0.0 --port 8000"]