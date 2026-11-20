# Base image with Python 3.11 slim
FROM python:3.11-slim

# Install system dependencies including Hebrew fonts for chart rendering
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    build-essential \
    fonts-dejavu-core \
    fonts-freefont-ttf \
    && rm -rf /var/lib/apt/lists/*

# Copy uv binary for fast package installation
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Set working directory
WORKDIR /app

# Copy dependency specifications first for layer caching
COPY requirements.txt ./
COPY telegram_bot/requirements.txt ./telegram_bot/

# Install dependencies
RUN uv pip install --system -r requirements.txt -r telegram_bot/requirements.txt

# Copy application code
COPY . .

# Set environment variables
ENV PYTHONPATH="/app:/app/telegram_bot" \
    PYTHONUNBUFFERED=1

# Run the Telegram bot
CMD ["python", "telegram_bot/telegram_bot.py"]
