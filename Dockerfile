FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bind9-host \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && addgroup --system kanga-route \
    && adduser \
        --system \
        --ingroup kanga-route \
        --home /home/kanga-route \
        kanga-route

COPY requirements.txt pyproject.toml README.md /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ /app/src/
RUN pip install --no-cache-dir --no-deps . \
    && chown -R kanga-route:kanga-route /app /home/kanga-route

USER kanga-route

EXPOSE 8080 10040

CMD ["kanga-route-engine"]
