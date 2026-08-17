# Architecture

## Solution Overview

The solution consists of independent Python modules orchestrated by a Jenkins pipeline.

```text
             Jenkins
                 │
                 │
      ┌──────────┴──────────┐
      │                     │
 Cleanup Automation   Metrics Automation
      │                     │
      │             Artifactory Sync
      └──────────┬──────────┘
                 │
         Dashboard Generator
                 │
      reports/html/dashboard.html
                 │
      Email + Jenkins Artifacts
```

---

# Components

## config.py

Central configuration using Python constants.

Contains:

* Retention policy
* Retry configuration
* SSL configuration
* Report locations
* Dashboard configuration
* Protected index patterns

---

## creds.py

Stores:

* OpenSearch credentials
* Artifactory credentials
* Cluster inventory

Business logic should never hardcode credentials.

---

## opensearch_client.py

Responsible for:

* Creating a reusable requests.Session()
* Retry strategy
* SSL configuration
* Wrapper methods for OpenSearch APIs

Retry configuration:

* 3 retries
* Exponential backoff
* Retry on connection/read/status failures

---

## artifactory_client.py

Wrapper around:

* HEAD
* GET
* PUT

Used exclusively for rolling metrics CSV management.

---

## cleanup.py

Responsibilities:

* Retrieve indices
* Filter protected indices
* Apply retention policy
* Calculate Top-N largest indices
* Generate cleanup CSV
* Delete indices when requested

Modes:

* REPORT
* DELETE
* DRY RUN

---

## metrics.py

Responsibilities:

Collect:

* Cluster health
* Node statistics
* Index statistics
* Shard statistics

Maintain rolling 30-day CSV history.

---

## dashboard.py

Reads generated CSV files from previous stages and invokes the HTML renderer.

This keeps Cleanup and Metrics independent.

---

## html_report.py

Generates a single executive dashboard using Chart.js.

Dashboard sections:

Charts:

* Storage by Cluster
* Heap %
* Disk %
* Largest Indices

Tables:

* Cleanup Candidates
* Cluster Metrics

---

# Execution Flow

```text
Cleanup
    │
    ├── cleanup_report.csv
    │
Metrics
    │
    ├── master_c1.csv
    ├── master_c2.csv
    └── ...
    │
Dashboard
    │
    └── dashboard.html
    │
Jenkins
    │
    ├── Archive CSV
    ├── Archive HTML
    └── Email Dashboard
```

---

# OpenSearch APIs

The framework uses REST APIs including:

* GET /_cluster/health
* GET /_nodes/stats
* GET /_cat/indices?format=json&bytes=mb
* GET /_cat/shards?format=json

---

# Parallel Processing

Cleanup and Metrics support concurrent execution across multiple clusters using configurable worker threads.

Default worker count is defined in `config.py`.

---

# Reporting

CSV Reports:

* Cleanup candidates
* Rolling metrics history

HTML Report:

* Executive dashboard
* Interactive Chart.js charts
* Operational summary tables

---

# Design Principles

* Modular components with clear responsibilities.
* Shared REST clients reused across automations.
* Configuration separated from credentials.
* Safety-first deletion workflow with DRY RUN support.
* Reports generated independently of business logic.
* Jenkins acts only as the orchestration layer while Python implements all automation logic.
