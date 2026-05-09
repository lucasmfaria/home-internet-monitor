FROM python:3.12-slim

LABEL maintainer="home-internet-monitor"
LABEL description="Automated speed tester using the official Ookla Speedtest CLI"

# Install dependencies and the official Ookla Speedtest CLI
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl \
        gnupg \
        lsb-release \
        ca-certificates && \
    # Add Ookla's official GPG key and repository
    curl -fsSL https://packagecloud.io/ookla/speedtest-cli/gpgkey | gpg --dearmor -o /usr/share/keyrings/ookla-archive-keyring.gpg && \
    echo "deb [signed-by=/usr/share/keyrings/ookla-archive-keyring.gpg] https://packagecloud.io/ookla/speedtest-cli/debian/ $(lsb_release -cs) main" \
        > /etc/apt/sources.list.d/ookla-speedtest.list && \
    apt-get update && \
    apt-get install -y --no-install-recommends speedtest && \
    # Cleanup
    apt-get purge -y curl gnupg lsb-release && \
    apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY config.py tester.py ./

CMD ["python", "-u", "tester.py"]
