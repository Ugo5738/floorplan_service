# Pull the base image
FROM python:3.9

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# Install necessary system dependencies
RUN apt-get update -y && \
    apt-get install -y \
    openjdk-17-jdk \
    netcat-openbsd \
    wget \
    gnupg \
    curl \
    chromium \
    chromium-driver

# Install Node.js for Playwright
RUN curl -fsSL https://deb.nodesource.com/setup_21.x | bash - && \
    apt-get install -y nodejs

# Clean up APT when done
RUN apt-get clean && rm -rf /var/lib/apt/lists/*

# Set work directory
WORKDIR /code

# Copy project
COPY . /code/

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Set execute permission for entrypoint.sh
RUN chmod +x /code/entrypoint.sh

# ENTRYPOINT ["/code/entrypoint.sh"]

# Run the application
CMD ["daphne", "floorplan_service.asgi:application", "--port", "$PORT", "--bind", "0.0.0.0"]
