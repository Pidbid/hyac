FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /server

RUN pip install uv

# # Copy dependency definition files
COPY requirements.txt .

# # Install dependencies using uv
RUN uv pip install --system --no-cache -r requirements.txt

# Copy the rest of the application source code
# COPY . .

# Copy and set permissions for the healthcheck script
COPY ./healthcheck.py /healthcheck.py
RUN chmod +x /healthcheck.py

# Expose the port the app runs on
EXPOSE 8000

CMD ["sh", "/server/start.sh"]
