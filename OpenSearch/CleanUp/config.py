"""
OpenSearch Automation V2 - Configuration Constants

Central configuration file using Python constants.
"""

import os
from pathlib import Path

# Base Directory of the Project
BASE_DIR = Path(__file__).resolve().parent

# Retention & Safety Configuration
RETENTION_DAYS = int(os.getenv("RETENTION_DAYS", "30"))
MINIMUM_DELETE_AGE_DAYS = int(os.getenv("MINIMUM_DELETE_AGE_DAYS", "7"))
PROTECTED_INDICES = [
    ".kibana*",
    ".opensearch*",
    "security-auditlog*",
    "system-*",
    ".plugins*",
    ".tasks*",
]

# Execution Defaults
DEFAULT_TOP_N = int(os.getenv("DEFAULT_TOP_N", "10"))
DEFAULT_WORKERS = int(os.getenv("DEFAULT_WORKERS", "4"))
MAX_LARGEST_INDICES = int(os.getenv("MAX_LARGEST_INDICES", "10"))

# REST / HTTP Client Configuration
# SSL Verification default is False ("off") as specified
VERIFY_SSL = os.getenv("VERIFY_SSL", "False").lower() in ("true", "1", "t", "yes")
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "30"))
REST_RETRIES = int(os.getenv("REST_RETRIES", "3"))
REST_BACKOFF_SECONDS = float(os.getenv("REST_BACKOFF_SECONDS", "2"))

# Directory Paths
REPORT_DIR = BASE_DIR / "reports"
CSV_REPORT_DIR = REPORT_DIR / "csv"
HTML_REPORT_DIR = REPORT_DIR / "html"
LOG_DIR = BASE_DIR / "logs"

# Ensure Output Directories Exist
CSV_REPORT_DIR.mkdir(parents=True, exist_ok=True)
HTML_REPORT_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

# Dashboard Visualization Settings
CHARTJS_CDN = os.getenv("CHARTJS_CDN", "https://cdn.jsdelivr.net/npm/chart.js")
