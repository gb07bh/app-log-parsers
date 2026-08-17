"""
OpenSearch Automation V2 - Credentials & Cluster Inventory Configuration

Defines OpenSearch clusters and Artifactory settings.
Credentials default to "UNDEFINED" or environment variables.
"""

import os
import sys
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


def _get_env(var_name: str, default: str = "UNDEFINED") -> str:
    """Helper to read environment variable with default 'UNDEFINED'."""
    val = os.getenv(var_name)
    if val is None or val.strip() == "":
        return default
    return val.strip()


# Artifactory Credentials & URL configuration
ARTIFACTORY_URL = _get_env("ARTIFACTORY_URL", "UNDEFINED")
ARTIFACTORY_REPO = _get_env("ARTIFACTORY_REPO", "opensearch-metrics")
ARTIFACTORY_UPLOAD_PATH = _get_env("ARTIFACTORY_UPLOAD_PATH", "rolling-history")
ARTIFACTORY_USER = _get_env("ARTIFACTORY_USER", "UNDEFINED")
ARTIFACTORY_PASSWORD = _get_env("ARTIFACTORY_PASSWORD", "UNDEFINED")
ARTIFACTORY_TOKEN = _get_env("ARTIFACTORY_TOKEN", "UNDEFINED")


# OpenSearch Cluster Inventory (c1 through c6)
CLUSTERS: Dict[str, Dict[str, str]] = {
    "c1": {
        "name": "Cluster 1 (Prod Alpha)",
        "url": _get_env("OPENSEARCH_C1_URL", "UNDEFINED"),
        "user": _get_env("OPENSEARCH_C1_USER", "UNDEFINED"),
        "password": _get_env("OPENSEARCH_C1_PASSWORD", "UNDEFINED"),
    },
    "c2": {
        "name": "Cluster 2 (Prod Beta)",
        "url": _get_env("OPENSEARCH_C2_URL", "UNDEFINED"),
        "user": _get_env("OPENSEARCH_C2_USER", "UNDEFINED"),
        "password": _get_env("OPENSEARCH_C2_PASSWORD", "UNDEFINED"),
    },
    "c3": {
        "name": "Cluster 3 (Prod Gamma)",
        "url": _get_env("OPENSEARCH_C3_URL", "UNDEFINED"),
        "user": _get_env("OPENSEARCH_C3_USER", "UNDEFINED"),
        "password": _get_env("OPENSEARCH_C3_PASSWORD", "UNDEFINED"),
    },
    "c4": {
        "name": "Cluster 4 (Staging)",
        "url": _get_env("OPENSEARCH_C4_URL", "UNDEFINED"),
        "user": _get_env("OPENSEARCH_C4_USER", "UNDEFINED"),
        "password": _get_env("OPENSEARCH_C4_PASSWORD", "UNDEFINED"),
    },
    "c5": {
        "name": "Cluster 5 (Dev Main)",
        "url": _get_env("OPENSEARCH_C5_URL", "UNDEFINED"),
        "user": _get_env("OPENSEARCH_C5_USER", "UNDEFINED"),
        "password": _get_env("OPENSEARCH_C5_PASSWORD", "UNDEFINED"),
    },
    "c6": {
        "name": "Cluster 6 (Analytics)",
        "url": _get_env("OPENSEARCH_C6_URL", "UNDEFINED"),
        "user": _get_env("OPENSEARCH_C6_USER", "UNDEFINED"),
        "password": _get_env("OPENSEARCH_C6_PASSWORD", "UNDEFINED"),
    },
}


def validate_creds(target_clusters: Optional[List[str]] = None, check_artifactory: bool = False, strict: bool = True) -> List[str]:
    """
    Validates whether required environment variables are set or 'UNDEFINED'.
    If strict=True, prints an error and exits the program immediately if any required variable is UNDEFINED.
    """
    missing: List[str] = []

    # Validate Clusters
    if target_clusters:
        clusters_to_check = target_clusters
    else:
        clusters_to_check = list(CLUSTERS.keys())

    for c_key in clusters_to_check:
        if c_key not in CLUSTERS:
            missing.append(f"Unknown cluster identifier '{c_key}'")
            continue

        c_info = CLUSTERS[c_key]
        if c_info["url"] == "UNDEFINED":
            missing.append(f"OPENSEARCH_{c_key.upper()}_URL is UNDEFINED")
        if c_info["user"] == "UNDEFINED" and c_info["password"] == "UNDEFINED":
            # Check if at least user/pass is configured
            missing.append(f"OPENSEARCH_{c_key.upper()}_USER / OPENSEARCH_{c_key.upper()}_PASSWORD are UNDEFINED")

    # Validate Artifactory if required
    if check_artifactory:
        if ARTIFACTORY_URL == "UNDEFINED":
            missing.append("ARTIFACTORY_URL is UNDEFINED")
        if ARTIFACTORY_USER == "UNDEFINED" and ARTIFACTORY_TOKEN == "UNDEFINED":
            missing.append("ARTIFACTORY_USER / ARTIFACTORY_TOKEN are UNDEFINED")

    if missing:
        err_msg = "[CREDENTIAL ERROR] The following required configuration variables are not defined:\n" + "\n".join(f"  - {m}" for m in missing)
        logger.error(err_msg)
        if strict:
            print(err_msg, file=sys.stderr)
            sys.exit(1)

    return missing
