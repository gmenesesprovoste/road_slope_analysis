FROM python:3.8-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    postgresql-client \
    postgis \
    gdal-bin \
    libgdal-dev \
    libpq-dev \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Set GDAL environment variables
ENV CPLUS_INCLUDE_PATH=/usr/include/gdal
ENV C_INCLUDE_PATH=/usr/include/gdal

# Get GDAL version and set it as an environment variable
RUN gdal-config --version > /tmp/gdal_version.txt && \
    export GDAL_VERSION=$(cat /tmp/gdal_version.txt) && \
    echo "GDAL_VERSION=${GDAL_VERSION}" >> /etc/environment

# Create and set working directory
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN export GDAL_VERSION=$(gdal-config --version) && \
    pip install --no-cache-dir GDAL==${GDAL_VERSION} && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Make scripts executable
RUN chmod +x *.sh

# Set environment variables
ENV PYTHONPATH=/app

# Expose Streamlit port
EXPOSE 8501

# Remove the bash entrypoint and use CMD instead
CMD ["streamlit", "run", "web-app/streamlit_app.py", "--server.address", "0.0.0.0"] 