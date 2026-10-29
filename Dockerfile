FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends nodejs npm && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml pricing.yaml ./
COPY src ./src
RUN pip install --no-cache-dir -e ".[voice]"
CMD ["python", "-m", "agency.voice.agent", "start"]
