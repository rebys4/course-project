########################
# 1) Build stage
########################
FROM python:3.11-slim AS build

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Ставим системные зависимости только для сборки (если что-то нужно из C)
RUN apt-get update && \
    apt-get install -y --no-install-recommends build-essential && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-dev.txt ./

# Ставим зависимости в build-образ
RUN --mount=type=cache,target=/root/.cache \
    pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt -r requirements-dev.txt

# Копируем исходники и гоняем тесты
COPY . .
RUN pytest -q

########################
# 2) Runtime stage
########################
FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# создаём непривилегированного пользователя
RUN groupadd -r app && useradd -r -g app app

# ставим только runtime-зависимости
COPY requirements.txt ./
RUN --mount=type=cache,target=/root/.cache \
    pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt
# curl для healthcheck
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

COPY . .

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
