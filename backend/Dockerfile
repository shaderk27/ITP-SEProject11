FROM python:3.12-slim

WORKDIR /app

# System deps needed for psycopg2 and building some Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first (better layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the backend source code
# (this Dockerfile expects to be built with the repo root as build context,
# so the app/ folder ends up at /app/app)
COPY backend/ .

EXPOSE 8080

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
