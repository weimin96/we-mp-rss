# Source-only candidate: no rachelos/* prebuilt base image.
# Review/pin upstream base image digest and dependencies before production use.
FROM python:3.13-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PLANT_PATH=/app/env \
    PLAYWRIGHT_BROWSERS_PATH=/opt/playwright-browsers \
    HEADLESS=true \
    ENABLE_XVFB=false \
    BROWSER_TYPE=webkit \
    HOME=/home/wrss

WORKDIR /app

RUN sed -i 's|http://deb.debian.org|https://mirrors.aliyun.com|g' /etc/apt/sources.list.d/debian.sources \
    && apt-get update && apt-get install -y --no-install-recommends \
      bash ca-certificates libffi-dev libssl-dev build-essential \
      zlib1g-dev libsqlite3-dev libgdbm-dev libreadline-dev \
      procps curl \
    && rm -rf /var/lib/apt/lists/*

ENV PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/

COPY requirements.txt ./
RUN python -m venv "/app/env_$(uname -m)" \
    && "/app/env_$(uname -m)/bin/python" -m pip install -r requirements.txt \
    && "/app/env_$(uname -m)/bin/python" -m playwright install --with-deps webkit chromium

COPY . .
COPY config.example.yaml /app/config.yaml
RUN printf '%s\n' \
      'export PLAYWRIGHT_BROWSERS_PATH=/opt/playwright-browsers' \
      'export TZ=Asia/Shanghai' \
      'export BROWSER_TYPE=webkit' > /app/environment.sh \
    && useradd --system --create-home --uid 10001 wrss \
    && mkdir -p /app/data \
    && chown -R wrss:wrss /app /opt/playwright-browsers \
    && chmod +x /app/start.sh

USER 10001:10001
EXPOSE 8001
CMD ["/bin/bash", "/app/start.sh"]
