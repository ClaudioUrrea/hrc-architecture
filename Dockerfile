FROM python:3.11-slim@sha256:2f1d0b0f1e0d1b4a8e6b8b5f0b7f5f8b4a3c2d1e0f9a8b7c6d5e4f3a2b1c0d9e

LABEL org.opencontainers.image.title="hrc-architecture reproducibility image"
LABEL org.opencontainers.image.source="https://github.com/ClaudioUrrea/hrc-architecture"
LABEL org.opencontainers.image.licenses="MIT"

WORKDIR /work
RUN apt-get update && apt-get install -y --no-install-recommends make ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["make", "all"]
