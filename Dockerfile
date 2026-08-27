FROM python:3.12-slim

# Prevent Python from writing .pyc files and buffer stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8585

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Create a non-root user and group
RUN groupadd -g 10001 appuser && \
    useradd -u 10001 -g appuser -s /bin/sh -M -d /app appuser

# Copy application code
COPY . .

# Set proper ownership for the app directory
RUN chown -R appuser:appuser /app

USER appuser

EXPOSE 8585

HEALTHCHECK --interval=60s --timeout=5s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request, os; urllib.request.urlopen('http://127.0.0.1:' + str(os.environ.get('PORT', 8585)) + '/health')" || exit 1

CMD ["python", "main.py"]
