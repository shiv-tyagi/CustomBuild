FROM python:3.10.16-slim-bookworm

# Install system dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends git gosu \
    && rm -rf /var/lib/apt/lists/*

# Create ardupilot user and group
RUN groupadd -g 999 ardupilot && \
    useradd -u 999 -g 999 -m ardupilot --shell /bin/bash && \
    mkdir -p /app && \
    chown -R ardupilot:ardupilot /app

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY --chown=ardupilot:ardupilot web_new/requirements.txt /app/web_new/

# Install Python dependencies
RUN pip install --no-cache-dir -r /app/web_new/requirements.txt

# Copy application files
COPY --chown=ardupilot:ardupilot . /app

# Expose port 8000
EXPOSE 8000

# Switch to non-root user
USER ardupilot

# Set Python path to include parent modules and web_new directory
ENV PYTHONPATH=/app:/app/web_new

# Change working directory to web_new
WORKDIR /app/web_new

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# Run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
