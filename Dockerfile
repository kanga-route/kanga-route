# Lightweight Python base image for containerized engine appliance
FROM python:3.9-slim

# Prevent Python from writing .pyc files and buffer outputs
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/src

WORKDIR /app

# Install system dependencies (including ca-certificates and bind9-host for DNS)
RUN apt-get update && apt-get install -y --no-install-recommends \
    bind9-host \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt pyproject.toml /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code and test suite
COPY src/ /app/src/
COPY tests/ /app/tests/

# Set default command to execute main runner
CMD ["python", "-m", "kanga_route.main"]
