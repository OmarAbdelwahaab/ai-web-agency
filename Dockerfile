# syntax=docker/dockerfile:1
FROM python:3.12-slim

# Install system dependencies & Node.js 22 LTS for wrangler/impeccable QA
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    git \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# Create non-root application user
RUN useradd -m -u 1000 -s /bin/bash agency

WORKDIR /app

# Copy dependency specifications first for layer caching
COPY pyproject.toml README.md ./
COPY pricing.yaml ./
COPY src/ ./src/

# Install agency package with voice dependencies
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir ".[voice]"

# Prepare data and output directories with proper permissions
RUN mkdir -p /app/data /app/output && chown -R agency:agency /app

USER agency

ENV PYTHONUNBUFFERED=1
ENV DB_PATH=/app/data/agency.db

# Default to agency CLI help
CMD ["agency", "--help"]
