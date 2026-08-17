"""
OpenSearch Automation V2 - Cleanup Script

Identifies old OpenSearch indices based on retention policy and minimum delete age,
ranks candidates by size (Top-N), generates CSV reports, and deletes indices when
executing in DELETE mode (or simulates deletion in DRY RUN mode).
"""

import sys
import argparse
import logging
from pathlib import Path
from typing import List, Dict, Any

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
import creds
from scripts.logging_config import setup_logging
from scripts.opensearch_client import OpenSearchClient
from scripts import utils
from scripts import reporting

logger = logging.getLogger("cleanup")


def process_cluster_cleanup(
    cluster_key: str,
    mode: str,
    top_n: int,
    dry_run: bool,
) -> List[Dict[str, Any]]:
    """
    Executes cleanup analysis and deletion workflow for a single cluster.
    """
    logger.info(f"=== Starting Cleanup Workflow for Cluster [{cluster_key}] (Mode: {mode}, DryRun: {dry_run}) ===")
    c_info = creds.CLUSTERS.get(cluster_key)
    if not c_info:
        logger.error(f"Cluster key '{cluster_key}' not found in configuration.")
        return []

    candidates: List[Dict[str, Any]] = []
    is_mock = False

    # Check if credentials are mock/undefined for testing
    if c_info["url"] == "UNDEFINED":
        logger.warning(f"URL for cluster [{cluster_key}] is UNDEFINED. Operating in Mock Data mode.")
        is_mock = True

    indices_raw: List[Dict[str, Any]] = []

    if not is_mock:
        try:
            auth = (c_info["user"], c_info["password"])
            client = OpenSearchClient(base_url=c_info["url"], auth=auth)
            indices_raw = client.get_cat_indices()
        except Exception as exc:
            logger.error(f"Failed to fetch indices from OpenSearch cluster [{cluster_key}]: {exc}")
            logger.warning(f"Falling back to dry-run mock indices for cluster [{cluster_key}].")
            is_mock = True

    if is_mock:
        # Generate mock indices for testing validation
        indices_raw = [
            {"index": ".kibana_1", "store.size": "15", "docs.count": "120", "creation.date": None},
            {"index": "security-auditlog-2026.01", "store.size": "450", "docs.count": "8900", "creation.date": None},
            {"index": "app-logs-2025.01.01", "store.size": "12500", "docs.count": "450000", "creation.date": None},
            {"index": "app-logs-2025.05.10", "store.size": "9800", "docs.count": "320000", "creation.date": None},
            {"index": "app-logs-2026.07.01", "store.size": "5400", "docs.count": "150000", "creation.date": None},
            {"index": f"metrics-{cluster_key}-2025-02-01", "store.size": "8900", "docs.count": "210000", "creation.date": None},
            {"index": f"metrics-{cluster_key}-2026-07-20", "store.size": "3400", "docs.count": "95000", "creation.date": None},
        ]

    # Evaluate indices against safety and retention policies
    evaluated_list = []
    for idx_info in indices_raw:
        index_name = idx_info.get("index", "")
        if not index_name:
            continue

        # Check protected indices
        if utils.is_protected_index(index_name, config.PROTECTED_INDICES):
            logger.debug(f"Skipping protected index: {index_name}")
            continue

        # Parse index size (MB)
        try:
            size_mb = float(idx_info.get("store.size", idx_info.get("pri.store.size", 0.0)))
        except (ValueError, TypeError):
            size_mb = 0.0

        # Parse index age in days
        creation_epoch = idx_info.get("creation.date")
        creation_epoch_ms = int(creation_epoch) if creation_epoch and str(creation_epoch).isdigit() else None
        age_days = utils.parse_index_age_days(index_name, creation_epoch_ms=creation_epoch_ms)

        docs_count = idx_info.get("docs.count", "0")

        # Policy checks
        if age_days < config.MINIMUM_DELETE_AGE_DAYS:
            logger.debug(f"Index {index_name} age ({age_days}d) < minimum delete age ({config.MINIMUM_DELETE_AGE_DAYS}d). Keeping.")
            continue

        if age_days >= config.RETENTION_DAYS:
            reason = f"Age ({age_days:.1f} days) exceeds retention threshold ({config.RETENTION_DAYS} days)"
            evaluated_list.append({
                "Cluster": cluster_key,
                "Index": index_name,
                "Size (MB)": size_mb,
                "Documents": docs_count,
                "Age (Days)": age_days,
                "Reason": reason,
                "Action": "PENDING"
            })

    # Sort evaluated candidates by Size (MB) descending and pick Top-N
    evaluated_list.sort(key=lambda x: x["Size (MB)"], reverse=True)
    top_candidates = evaluated_list[:top_n]

    # Perform action based on MODE & DRY_RUN
    final_candidates = []
    client = None
    if not is_mock:
        try:
            auth = (c_info["user"], c_info["password"])
            client = OpenSearchClient(base_url=c_info["url"], auth=auth)
        except Exception:
            client = None

    for item in top_candidates:
        index_name = item["Index"]

        if mode == "REPORT" or dry_run:
            item["Action"] = "REPORT_ONLY" if mode == "REPORT" else "DRY_RUN_DELETE"
            logger.info(f"[{cluster_key}] Candidate identified ({item['Action']}): {index_name} (Size: {item['Size (MB)']} MB, Age: {item['Age (Days)']} days)")
        elif mode == "DELETE":
            if is_mock or client is None:
                item["Action"] = "SIMULATED_DELETED"
                logger.info(f"[{cluster_key}] Simulated deletion of index: {index_name}")
            else:
                try:
                    client.delete_index(index_name)
                    item["Action"] = "DELETED"
                    logger.info(f"[{cluster_key}] DELETED index: {index_name}")
                except Exception as exc:
                    item["Action"] = f"FAILED: {exc}"
                    logger.error(f"[{cluster_key}] Failed to delete index {index_name}: {exc}")

        final_candidates.append(item)

    # Save cluster cleanup report CSV
    csv_file = config.CSV_REPORT_DIR / f"cleanup_{cluster_key}.csv"
    reporting.write_cleanup_report(final_candidates, csv_file)

    return final_candidates


def main():
    parser = argparse.ArgumentParser(description="OpenSearch Automation V2 - Index Cleanup Script")
    parser.add_argument("--cluster", required=True, help="Target cluster key (c1, c2, ..., c6, or ALL)")
    parser.add_argument("--mode", choices=["REPORT", "DELETE"], default="REPORT", help="Execution mode")
    parser.add_argument("--top-n", type=int, default=config.DEFAULT_TOP_N, help="Top N largest candidates to evaluate")
    parser.add_argument("--workers", type=int, default=config.DEFAULT_WORKERS, help="Parallel worker threads")
    parser.add_argument("--dry-run", action="store_true", help="Simulate actions without deleting indices")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose debug logging")

    args = parser.parse_args()
    setup_logging(verbose=args.verbose, log_filename="cleanup.log")

    logger.info(f"Starting Cleanup Script with CLI args: {vars(args)}")

    target_clusters = []
    if args.cluster.upper() == "ALL":
        target_clusters = list(creds.CLUSTERS.keys())
    else:
        target_clusters = [args.cluster.lower()]

    # Validate credentials
    creds.validate_creds(target_clusters=target_clusters, check_artifactory=False, strict=False)

    if len(target_clusters) == 1:
        process_cluster_cleanup(target_clusters[0], args.mode, args.top_n, args.dry_run)
    else:
        # Concurrent processing across multiple clusters
        def _worker(c_key: str):
            return process_cluster_cleanup(c_key, args.mode, args.top_n, args.dry_run)

        utils.run_concurrent_tasks(_worker, target_clusters, max_workers=args.workers)

    logger.info("Cleanup execution completed successfully.")


if __name__ == "__main__":
    main()
