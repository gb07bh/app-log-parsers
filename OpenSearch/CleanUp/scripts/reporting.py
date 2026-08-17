"""
OpenSearch Automation V2 - Reporting Helper Module

Handles CSV report generation for index cleanup candidates and
maintains rolling 30-day metric history CSV files using pandas.
"""

import logging
from pathlib import Path
from typing import List, Dict, Any
import pandas as pd

import config

logger = logging.getLogger(__name__)

# Required CSV Columns for Cleanup Reports
CLEANUP_CSV_COLUMNS = [
    "Cluster",
    "Index",
    "Size (MB)",
    "Documents",
    "Age (Days)",
    "Reason",
    "Action",
]

# Required CSV Columns for Rolling Metrics Reports
METRICS_CSV_COLUMNS = [
    "Timestamp",
    "Cluster",
    "Status",
    "Active Shards",
    "Relocating Shards",
    "Initializing Shards",
    "Unassigned Shards",
    "Total Shards",
    "Heap Percent (%)",
    "Heap Used (Bytes)",
    "CPU Percent (%)",
    "Disk Percent (%)",
    "Total Indices",
    "Total Storage (MB)",
    "Largest Index Name",
    "Largest Index Size (MB)",
]


def write_cleanup_report(candidates: List[Dict[str, Any]], output_path: Path) -> Path:
    """
    Writes cleanup candidates list to CSV file.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not candidates:
        df = pd.DataFrame(columns=CLEANUP_CSV_COLUMNS)
    else:
        df = pd.DataFrame(candidates)
        # Ensure exact column order
        for col in CLEANUP_CSV_COLUMNS:
            if col not in df.columns:
                df[col] = ""
        df = df[CLEANUP_CSV_COLUMNS]

    df.to_csv(output_path, index=False)
    logger.info(f"Wrote cleanup CSV report with {len(df)} records to {output_path}")
    return output_path


def update_rolling_metrics_csv(existing_csv_path: Path, new_metrics: Dict[str, Any], max_rows: int = 30) -> Path:
    """
    Appends new metric record to existing CSV (or creates new one) and retains only the latest max_rows (30).
    """
    existing_csv_path.parent.mkdir(parents=True, exist_ok=True)

    if existing_csv_path.exists() and existing_csv_path.stat().st_size > 0:
        try:
            df = pd.read_csv(existing_csv_path)
        except Exception as exc:
            logger.warning(f"Could not read existing CSV {existing_csv_path}: {exc}. Starting fresh.")
            df = pd.DataFrame(columns=METRICS_CSV_COLUMNS)
    else:
        df = pd.DataFrame(columns=METRICS_CSV_COLUMNS)

    # Convert new single metric dict to dataframe
    new_df = pd.DataFrame([new_metrics])
    for col in METRICS_CSV_COLUMNS:
        if col not in new_df.columns:
            new_df[col] = ""
    new_df = new_df[METRICS_CSV_COLUMNS]

    # Append new row
    combined_df = pd.concat([df, new_df], ignore_index=True)

    # Retain latest max_rows (rolling 30-day window)
    if len(combined_df) > max_rows:
        combined_df = combined_df.tail(max_rows).reset_index(drop=True)

    combined_df.to_csv(existing_csv_path, index=False)
    logger.info(f"Updated rolling metrics CSV {existing_csv_path} (Total rows: {len(combined_df)})")
    return existing_csv_path


def consolidate_cleanup_reports(input_directory: Path = config.CSV_REPORT_DIR) -> pd.DataFrame:
    """
    Reads and concatenates all cleanup_*.csv files into a single dataframe.
    """
    cleanup_files = list(input_directory.glob("cleanup_*.csv"))
    dfs = []
    for f in cleanup_files:
        try:
            temp_df = pd.read_csv(f)
            dfs.append(temp_df)
        except Exception as exc:
            logger.warning(f"Failed to read cleanup CSV {f}: {exc}")

    if dfs:
        return pd.concat(dfs, ignore_index=True)
    return pd.DataFrame(columns=CLEANUP_CSV_COLUMNS)


def consolidate_metrics_reports(input_directory: Path = config.CSV_REPORT_DIR) -> pd.DataFrame:
    """
    Reads and concatenates all metrics_*.csv files into a single dataframe.
    """
    metrics_files = list(input_directory.glob("metrics_*.csv"))
    dfs = []
    for f in metrics_files:
        try:
            temp_df = pd.read_csv(f)
            # Pick latest row for each cluster metrics summary
            if not temp_df.empty:
                dfs.append(temp_df.tail(1))
        except Exception as exc:
            logger.warning(f"Failed to read metrics CSV {f}: {exc}")

    if dfs:
        return pd.concat(dfs, ignore_index=True)
    return pd.DataFrame(columns=METRICS_CSV_COLUMNS)
