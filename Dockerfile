FROM python:3.9-slim

# Install Firefox (ESR), plus wget, etc.
RUN apt-get update && apt-get install -y \
    firefox-esr \
    gnupg \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Install geckodriver 0.35.0 (compatible with Firefox 128.*)
# Check https://github.com/mozilla/geckodriver/releases for the latest version.
RUN wget https://github.com/mozilla/geckodriver/releases/download/v0.35.0/geckodriver-v0.35.0-linux64.tar.gz \
    && tar -xzf geckodriver-v0.35.0-linux64.tar.gz -C /usr/local/bin \
    && rm geckodriver-v0.35.0-linux64.tar.gz

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Disable buffering
ENV PYTHONUNBUFFERED=1

CMD ["python", "main.py"]
