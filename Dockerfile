FROM python:3.10-slim

# Install curl, unzip, and Node.js
RUN apt-get update && apt-get install -y \
    curl \
    unzip \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

# Install latest Node.js
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs

# Install bun
RUN curl -fsSL https://bun.sh/install | bash

# Add bun to PATH
ENV PATH="/root/.bun/bin:${PATH}"

# Set the working directory in the container
WORKDIR /app

# Copy the entire repository into the container
COPY . /app

# Install Python dependencies
RUN pip install -r requirements.txt

# Verify installations
RUN node --version && npm --version && bun --version

# Expose port 8000 and 5173 (Vite dev server)
EXPOSE 8000 5173

# Default command (overridden by docker-compose)
CMD ["python", "server.py"]