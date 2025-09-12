FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Jupyter and nbconvert
RUN pip install --no-cache-dir jupyter jupyterlab nbconvert tqdm mysql-connector-python clickhouse-connect clickhouse-driver openpyxl prophet

# Copy application code
COPY . .

# Create directories for notebooks and outputs
RUN mkdir -p /app/data/notebooks /app/data/outputs

# Expose port
EXPOSE 8000

# Run the application
CMD ["python", "-m", "app.main"]
