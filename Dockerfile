# Use official Python runtime as base image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080

# Set work directory
WORKDIR /app

# Install system dependencies + Node.js for Tailwind CSS build
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    tesseract-ocr \
    libreoffice-core \
    libreoffice-writer \
    fonts-dejavu \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project
COPY . .

# Build Tailwind CSS
RUN npm ci --production=false && npm run build:css

# Collect static files (with dummy env vars for build)
RUN SECRET_KEY='build-secret-key-for-docker-image-must-be-at-least-fifty-characters-long-12345' \
    DEBUG='False' \
    ALLOWED_HOSTS='localhost' \
    DB_PASSWORD='build-dummy-password' \
    USE_CLOUD_SQL='False' \
    ZOHO_CLIENT_ID='build-dummy-id' \
    ZOHO_CLIENT_SECRET='build-dummy-secret' \
    python manage.py collectstatic --noinput

# Create a non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Expose port
EXPOSE 8080

# Run gunicorn
CMD exec gunicorn --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 0 minierp.wsgi:application
