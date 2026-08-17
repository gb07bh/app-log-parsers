# OpenSearch Automation V2

## Overview

OpenSearch Automation V2 is a Python-based automation framework that runs from Jenkins. It provides two primary automations:

1. **Cleanup Automation** – Identifies and optionally deletes old OpenSearch indices.
2. **Metrics Automation** – Collects cluster metrics, maintains a rolling 30-day history in Artifactory, and generates an executive HTML dashboard.

The solution is designed for multiple OpenSearch clusters (currently six clusters) and emphasizes safety, reporting, parallel execution, and Jenkins integration.

---

# Repository Structure

```text
opensearch-automation-v2/

config.py
creds.py
requirements.txt
Jenkinsfile
README.md
architecture.md

scripts/
    cleanup.py
    metrics.py
    dashboard.py
    html_report.py
    reporting.py
    logging_config.py
    opensearch_client.py
    artifactory_client.py
    utils.py

reports/
    csv/
    html/

logs/
```

---

# Configuration

## config.py

Contains Python constants only (no YAML).

Key configuration includes:

* RETENTION_DAYS
* MINIMUM_DELETE_AGE_DAYS
* DEFAULT_TOP_N
* DEFAULT_WORKERS
* REQUEST_TIMEOUT
* VERIFY_SSL=False
* REST_RETRIES=3
* REST_BACKOFF_SECONDS=2
* CHARTJS_CDN
* REPORT_DIR
* CSV_REPORT_DIR
* HTML_REPORT_DIR
* LOG_DIR
* MAX_LARGEST_INDICES
* PROTECTED_INDICES

## creds.py

Contains:

* OpenSearch credentials
* Artifactory credentials
* Cluster definitions

Example:

```python
CLUSTERS = {
    "c1": {...},
    "c2": {...},
    ...
    "c6": {...}
}
```

---

# Cleanup Automation

Supports:

* REPORT mode
* DELETE mode
* DRY RUN

Options:

* --cluster c1
* --cluster ALL
* --top-n
* --workers
* --dry-run
* --verbose

Workflow:

1. Retrieve indices.
2. Ignore protected indices.
3. Ignore indices younger than minimum delete age.
4. Apply retention policy.
5. Identify Top-N largest deletion candidates.
6. Generate CSV report.
7. Delete indices only in DELETE mode (or simulate in DRY RUN).

Cleanup report columns:

* Cluster
* Index
* Size (MB)
* Documents
* Age (Days)
* Reason
* Action

---

# Metrics Automation

Collects:

Cluster:

* Status
* Active shards
* Relocating shards
* Initializing shards
* Unassigned shards

Node:

* Heap %
* Heap bytes
* CPU %
* Disk %

Index:

* Total indices
* Total storage
* Largest index
* Largest index size

Shard:

* Total shards

Each execution updates a rolling 30-day CSV stored in Artifactory.

---

# Artifactory Integration

For each cluster:

1. Download master CSV.
2. Append latest metrics.
3. Keep only the latest 30 rows.
4. Upload updated CSV.

Uses REST APIs:

* HEAD
* GET
* PUT

---

# Dashboard

A single Chart.js dashboard is generated after Cleanup and Metrics complete.

Visualizations:

* Storage by Cluster
* Heap Utilization
* Disk Utilization
* Top Largest Indices

Tables:

* Cleanup Candidates
* Cluster Metrics

Output:

```
reports/html/dashboard.html
```

---

# Jenkins Pipeline

Pipeline stages:

1. Cleanup
2. Metrics
3. Dashboard
4. Archive Reports
5. Email Notification

Parameters:

* MODE
* TARGET_CLUSTER
* TOP_N
* DRY_RUN
* EMAIL_RECIPIENTS

Dashboard HTML is used as the EmailExt email body.

---

# Logging

Primary:

* Jenkins console (stdout)

Secondary:

```
logs/automation.log
```

---

# Technologies

* Python 3.10+
* requests
* pandas
* urllib3
* Jinja2
* Jenkins
* OpenSearch REST APIs
* Artifactory REST APIs
* Chart.js

---

# Design Goals

* Safe deletion process
* Parallel execution
* Minimal configuration
* Clear reporting
* Jenkins-friendly logging
* Easily extensible for future automations
