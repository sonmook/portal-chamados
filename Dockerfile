# syntax=docker/dockerfile:1
FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt ./
RUN --mount=type=secret,id=proxy_ca \
    if [ -s /run/secrets/proxy_ca ]; then export PIP_CERT=/run/secrets/proxy_ca; fi; \
    python -m pip install --no-cache-dir --require-hashes -r requirements.txt
COPY . ./
RUN groupadd --gid 10001 portal && useradd --uid 10001 --gid portal --no-create-home portal \
    && mkdir -p /data/private /static && chown -R portal:portal /app /data /static
USER portal
EXPOSE 8000
CMD ["sh", "deploy/start.sh"]
