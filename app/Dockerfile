# Use a specific Python version for reproducibility.
FROM python:3.12-slim

# Set environment variables to prevent writing .pyc files and to run in unbuffered mode
# ENV PYTHONDONTWRITEBYTECODE 1
# ENV PYTHONUNBUFFERED 1
ENV DOMAIN_NAME="hyacos.top" 

# Set the working directory in the container
WORKDIR /app

# Install uv, the package manager
RUN pip install uv

# Install curl for health checks
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# Copy dependency definition files from the main server directory
COPY requirements.txt ./

# Install dependencies using uv
RUN uv pip install --system --no-cache -r requirements.txt

# Copy the application source code for the 'app' service
# COPY . .

# Expose the port the app runs on
EXPOSE 8001

# Command to run the application
CMD ["sh", "/app/start.sh"]
