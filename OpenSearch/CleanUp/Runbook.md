# OpenSearch Automation V2 - Operational Runbook

## Overview

OpenSearch Automation V2 is a Python-based framework designed to manage multi-cluster OpenSearch operations (supporting clusters `c1` through `c6`). It provides two core automations:

1. **Cleanup Automation (`scripts/cleanup.py`)**: Identifies candidate indices exceeding retention thresholds (`RETENTION_DAYS`), ignores protected patterns (`PROTECTED_INDICES`), excludes indices younger than minimum delete age (`MINIMUM_DELETE_AGE_DAYS`), ranks candidates by size (Top-N), generates CSV reports, and deletes indices when executed in `DELETE` mode.
2. **Metrics Automation (`scripts/metrics.py`)**: Queries OpenSearch REST APIs (`/_cluster/health`, `/_nodes/stats`, `/_cat/indices`, `/_cat/shards`) to capture health status, shard counts, heap %, CPU %, disk %, and storage metrics. Maintains a rolling 30-day CSV history per cluster synced with Artifactory.
3. **Executive Dashboard Generator (`scripts/dashboard.py`)**: Consolidates CSV reports and renders an executive HTML dashboard (`reports/html/dashboard.html`) using Chart.js.
 
---

## Configuration & Credentials Setup

Credentials and endpoints are defined in `creds.py` and loaded from environment variables (defaulting to `"UNDEFINED"`).

> [!WARNING]
> If any required credential or URL is `"UNDEFINED"`, `creds.validate_creds()` raises an explicit error and halts execution.

### Environment Variable Reference

| Variable Name | Description | Default |
| :--- | :--- | :--- |
| `OPENSEARCH_C1_URL` .. `C6_URL` | Base REST endpoint for clusters `c1` to `c6` | `UNDEFINED` |
| `OPENSEARCH_C1_USER` .. `C6_USER` | HTTP Basic Auth Username | `UNDEFINED` |
| `OPENSEARCH_C1_PASSWORD` .. `C6_PASSWORD` | HTTP Basic Auth Password | `UNDEFINED` |
| `ARTIFACTORY_URL` | Base URL for Artifactory server | `UNDEFINED` |
| `ARTIFACTORY_REPO` | Target Artifactory repository name | `opensearch-metrics` |
| `ARTIFACTORY_UPLOAD_PATH` | Subfolder path in repository | `rolling-history` |
| `ARTIFACTORY_USER` / `ARTIFACTORY_TOKEN` | Auth credentials for Artifactory | `UNDEFINED` |
| `VERIFY_SSL` | SSL Certificate Verification | `False` (Off by default) |

### Artifactory Path Concatenation
The `ArtifactoryClient` constructs full artifact REST URLs using:
$$\text{Target URL} = \text{arti\_url} + \text{"/artifactory/"} + \text{repo\_name} + \text{"/"} + \text{upload\_path} + \text{"/"} + \text{filename}$$

---

## CLI Parameters Reference

### 1. `scripts/cleanup.py`

```bash
python scripts/cleanup.py --cluster c1 --mode REPORT --top-n 10 --workers 4 --dry-run --verbose
```

| CLI Option | Type | Required | Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `--cluster` | String | **Yes** | N/A | Target cluster key (`c1`, `c2`, ..., `c6`, or `ALL`). |
| `--mode` | Choice | No | `REPORT` | `REPORT` (generates CSV without deleting) or `DELETE` (deletes indices). |
| `--top-n` | Integer | No | `10` | Number of top largest candidate indices to evaluate per cluster. |
| `--workers` | Integer | No | `4` | Number of parallel worker threads when `--cluster ALL` is specified. |
| `--dry-run` | Flag | No | `False` | Simulates deletion operations without executing REST `DELETE` calls. |
| `--verbose` | Flag | No | `False` | Enables detailed debug logging output to stdout and log files. |

### 2. `scripts/metrics.py`

```bash
python scripts/metrics.py --cluster ALL --workers 4 --verbose
```

| CLI Option | Type | Required | Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `--cluster` | String | **Yes** | N/A | Target cluster key (`c1`..`c6` or `ALL`). |
| `--workers` | Integer | No | `4` | Parallel threads for cluster metrics collection. |
| `--verbose` | Flag | No | `False` | Enables debug logging output. |

### 3. `scripts/dashboard.py`

```bash
python scripts/dashboard.py --verbose
```

Consolidates all CSV reports inside `reports/csv/` and generates `reports/html/dashboard.html`.

---

## Jenkins Parameter Mapping

All CLI options map directly to parametrized inputs in the [Jenkinsfile](file:///d:/BNP_Code/OpenSearch/CleanUp/Jenkinsfile):

```groovy
parameters {
    choice(name: 'MODE', choices: ['REPORT', 'DELETE'])
    choice(name: 'TARGET_CLUSTER', choices: ['ALL', 'c1', 'c2', 'c3', 'c4', 'c5', 'c6'])
    string(name: 'TOP_N', defaultValue: '10')
    string(name: 'WORKERS', defaultValue: '4')
    booleanParam(name: 'DRY_RUN', defaultValue: true)
    string(name: 'EMAIL_RECIPIENTS', defaultValue: 'opensearch-admin@company.com')
}
```

### Mapping Matrix

| Jenkins Parameter | CLI Equivalent | Stage Applied |
| :--- | :--- | :--- |
| `TARGET_CLUSTER` | `--cluster ${TARGET_CLUSTER}` | Cleanup & Metrics |
| `MODE` | `--mode ${MODE}` | Cleanup |
| `TOP_N` | `--top-n ${TOP_N}` | Cleanup |
| `WORKERS` | `--workers ${WORKERS}` | Cleanup & Metrics |
| `DRY_RUN` | `--dry-run` (if checked) | Cleanup |
| `EMAIL_RECIPIENTS` | `emailext to: "${EMAIL_RECIPIENTS}"` | Post (Success & Failure) |

---

## Jenkins Pipeline Features

1. **Top Header & Wiki Link**:
   Contains documentation header at top referencing Wiki URL: `https://wiki.company.com/display/OPENSEARCH/OpenSearch+Automation+V2`.
2. **Concurrent Build Prevention**:
   Configured with `options { disableConcurrentBuilds() }` to guarantee thread safety across clusters.
3. **Email Notifications (`email-ext`)**:
   - Triggers automatically on **both SUCCESS and FAILURE** builds.
   - Embeds the generated HTML dashboard in the email body.
   - Attaches CSV reports (`reports/csv/*.csv`) and execution logs (`logs/*.log`).

---

## Verification & Manual Testing

To run manual dry-run verification locally:

```bash
# 1. Test Cleanup in Dry-Run mode
python scripts/cleanup.py --cluster ALL --mode REPORT --dry-run --verbose

# 2. Test Metrics Collection
python scripts/metrics.py --cluster ALL --verbose

# 3. Render HTML Dashboard
python scripts/dashboard.py --verbose
```
