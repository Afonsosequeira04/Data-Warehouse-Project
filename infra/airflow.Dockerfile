# Airflow image with dbt and postgresql-client
# Uses a stable recent 2.x version of Apache Airflow
ARG AIRFLOW_VERSION=2.9.3
ARG PYTHON_VERSION=3.11
FROM apache/airflow:${AIRFLOW_VERSION}-python${PYTHON_VERSION}

# Install system dependencies
USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Create writable directories for dbt target and logs with correct ownership
RUN mkdir -p /opt/airflow/dbt_project/target /tmp/dbt_logs && chown -R airflow:root /opt/airflow/dbt_project/target /tmp/dbt_logs

# Switch back to airflow user
USER airflow

# Install Python dependencies (dbt from the project's requirements.txt)
# Copy requirements first for better layer caching
COPY --chown=airflow:root dbt_project/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Set working directory
WORKDIR /opt/airflow