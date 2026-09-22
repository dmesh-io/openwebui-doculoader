FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY main.py .

# Create temp work directory
RUN mkdir -p /tmp/doculoader

# Environment variables (defaults, override with docker run -e)
ENV AZURE_CONTENT_UNDERSTANDING_ENDPOINT=""
ENV AZURE_CONTENT_UNDERSTANDING_KEY=""
ENV AZURE_CONTENT_UNDERSTANDING_ANALYZER_ID="prebuilt-documentSearch"
ENV TEMP_WORK_DIR="/tmp/doculoader"

# Expose port
EXPOSE 8000

# Run the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
