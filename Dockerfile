FROM python:3.9-slim

# Install Firefox, wget, and dependencies for geckodriver
RUN apt-get update && apt-get install -y \
    firefox-esr \
    gnupg \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Install geckodriver (adjust version as desired)
RUN wget https://github.com/mozilla/geckodriver/releases/download/v0.33.0/geckodriver-v0.33.0-linux64.tar.gz \
    && tar -xzf geckodriver-v0.33.0-linux64.tar.gz -C /usr/local/bin \
    && rm geckodriver-v0.33.0-linux64.tar.gz

# Set the working directory
WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of your source code
COPY . .

# By default, run the bot
CMD ["python", "main.py"]
