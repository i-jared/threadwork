FROM python:3.10-slim

# Set the working directory in the container.
WORKDIR /app

# Copy the entire repository into the container.
COPY . /app

# Install dependencies. Assumes requirements.txt is at the root.
RUN pip install -r requirements.txt

# Expose port 8000 so that the server can be accessed externally.
EXPOSE 8000

# Default command (overridden by docker-compose).
CMD ["python", "main.py"]