# ============================================================
# Stage 1: builder — устанавливаем зависимости через Poetry
# ============================================================
FROM python:3.11-slim AS builder

# Системные зависимости для сборки
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем Poetry
ENV POETRY_VERSION=1.8.3 \
    POETRY_HOME=/opt/poetry \
    POETRY_VENV=/opt/poetry-venv \
    POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=1 \
    POETRY_VIRTUALENVS_CREATE=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN python -m venv $POETRY_VENV \
    && $POETRY_VENV/bin/pip install --upgrade pip \
    && $POETRY_VENV/bin/pip install poetry==$POETRY_VERSION

ENV PATH="$POETRY_VENV/bin:$PATH"

WORKDIR /app

# Копируем только файлы зависимостей для кэширования слоёв
COPY pyproject.toml poetry.lock ./

# Устанавливаем только production-зависимости (без dev)
RUN poetry install --only=main --no-root --no-ansi

# Копируем исходный код и устанавливаем пакет
COPY src/ ./src/
RUN poetry install --only=main --no-ansi

# ============================================================
# Stage 2: runtime — минимальный образ для запуска
# ============================================================
FROM python:3.11-slim AS runtime

# Метаданные образа
LABEL maintainer="orchestra" \
      description="Agent Orchestra — multi-agent orchestration system" \
      version="0.1.0"

# Системные зависимости runtime (минимально)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 1001 orchestra \
    && useradd --uid 1001 --gid orchestra --shell /bin/bash --create-home orchestra

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    VIRTUAL_ENV="/app/.venv"

WORKDIR /app

# Копируем виртуальное окружение из builder
COPY --from=builder /app/.venv /app/.venv

# Копируем исходный код
COPY --from=builder /app/src ./src
COPY --from=builder /app/pyproject.toml ./pyproject.toml

# Копируем конфигурацию и статику
COPY config/ ./config/
COPY public/ ./public/
COPY landing/ ./landing/

# Директория для данных (jobs, runs, sessions)
RUN mkdir -p /app/_orchestra/jobs /app/_orchestra/runs /app/_orchestra/supervised \
    && chown -R orchestra:orchestra /app

# Переключаемся на непривилегированного пользователя
USER orchestra

# Порт веб-сервера (из src/cli/app.py: default=3015)
EXPOSE 3015

# Healthcheck: проверяем что сервер отвечает
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:3015/ || exit 1

# Точка входа: скрипт orchestra устанавливается Poetry в /app/.venv/bin/
ENTRYPOINT ["orchestra"]
CMD ["serve", "--host", "0.0.0.0", "--port", "3015"]
