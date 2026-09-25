# Airflow image with dbt and postgresql-client
ARG AIRFLOW_VERSION=2.9.3
ARG PYTHON_VERSION=3.11
FROM apache/airflow:${AIRFLOW_VERSION}-python${PYTHON_VERSION}

# Install system dependencies
USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Create writable directory for dbt project (target, dbt_packages, etc.) and logs
RUN mkdir -p /opt/airflow/dbt_project/target /tmp/dbt_logs && \
    chown -R airflow:root /opt/airflow/dbt_project /tmp/dbt_logs

# Everything from here runs as the airflow user
USER airflow

# Install Python dependencies (dbt from the project's requirements.txt)
COPY --chown=airflow:root dbt_project/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Copy dbt project into the image (dbt_packages/target/logs excluded via .dockerignore,
# so packages are always installed fresh below, never a possibly-locked host copy)
COPY --chown=airflow:root dbt_project/ /opt/airflow/dbt_project/

# Install dbt packages from packages.yml
RUN dbt deps --project-dir /opt/airflow/dbt_project --profiles-dir /opt/airflow/dbt_project
RUN test -d /opt/airflow/dbt_project/dbt_packages/dbt_utils \
    || (echo "dbt_utils não foi instalado" && exit 1)

WORKDIR /opt/airflow