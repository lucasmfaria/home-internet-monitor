FROM python:3.12-slim

LABEL maintainer="home-internet-monitor"
LABEL description="Ping monitor for continuous internet connectivity checking"

# Install system ping utility
RUN apt-get update && \
    apt-get install -y --no-install-recommends iputils-ping && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY config.py monitor.py ./

CMD ["python", "-u", "monitor.py"]
