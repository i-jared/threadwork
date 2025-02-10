FROM python:3.10-slim

# Set the working directory in the container.
WORKDIR /app

# Copy the requirements file and install dependencies
COPY requirements.txt /app
RUN pip install -r requirements.txt

# Copy the rest of the current directory into the container.
COPY . /app

# Expose port 8000 so that the server can be accessed externally.
EXPOSE 8000

# Run main.py when the container launches.
CMD ["python", "main.py"] 