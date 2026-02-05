# Python runtime base image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose port (gunicorn will run on this)
EXPOSE 5000

# Default command
CMD ["gunicorn", "--preload", "main:app", "--timeout", "120", "--bind", "0.0.0.0:5000"]
