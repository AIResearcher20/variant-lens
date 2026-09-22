FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src/ ./src/

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -e .

RUN useradd --create-home --shell /bin/bash appuser
USER appuser

ENTRYPOINT ["variant-lens"]
CMD ["--help"]
