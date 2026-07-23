FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends libexpat1 ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md ./
RUN mkdir scale \
    && touch scale/__init__.py \
    && pip install . \
    && rm -rf scale
COPY scale ./scale

RUN useradd --create-home --uid 10001 scale \
    && mkdir -p /var/cache/scale \
    && chown -R scale:scale /var/cache/scale
USER scale

EXPOSE 8000
CMD ["uvicorn", "scale.api:app", "--host", "0.0.0.0", "--port", "8000"]
