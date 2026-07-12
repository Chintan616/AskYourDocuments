FROM python:3.10-slim

WORKDIR /app

# Install system dependencies
# pdf2image requires poppler-utils
# opencv requires libgl1 and libglib2.0-0
# psycopg2 requires libpq-dev
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    libgl1 \
    libglib2.0-0 \
    poppler-utils \
    tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Expose the default port
EXPOSE 5001

# Command to run the application
# We use gunicorn with uvicorn workers for production performance
CMD ["gunicorn", "-k", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:5001", "--workers", "2", "--timeout", "120", "app.main:app"]
