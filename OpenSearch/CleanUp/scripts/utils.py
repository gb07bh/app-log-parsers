"""
OpenSearch Automation V2 - Utility Helper Functions

Provides helper functions for:
- Protected index pattern matching (fnmatch)
- Index age calculations
- Unit conversions (MB, GB, Bytes)
- Thread pool executor concurrency
"""

import re
import fnmatch
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any, Callable, TypeVar, Optional

T = TypeVar("T")
R = TypeVar("R")


def is_protected_index(index_name: str, protected_patterns: List[str]) -> bool:
    """
    Checks if an index name matches any protected wildcard patterns (e.g., .kibana*).
    """
    if not index_name:
        return False
    for pattern in protected_patterns:
        if fnmatch.fnmatch(index_name, pattern):
            return True
    return False


def parse_index_age_days(index_name: str, creation_date_epoch_ms: Optional[int] = None) -> float:
    """
    Calculates index age in days.
    First uses explicit OpenSearch creation timestamp if available.
    Otherwise attempts to extract date pattern (YYYY.MM.DD or YYYY-MM-DD or YYYYMMDD) from index name.
    """
    now = datetime.now(timezone.utc)

    # Method 1: OpenSearch creation_date timestamp (in milliseconds epoch)
    if creation_date_epoch_ms and creation_date_epoch_ms > 0:
        creation_dt = datetime.fromtimestamp(creation_date_epoch_ms / 1000.0, tz=timezone.utc)
        age_seconds = (now - creation_dt).total_seconds()
        return max(0.0, round(age_seconds / 86400.0, 2))

    # Method 2: Extract date from index name pattern
    date_patterns = [
        (r"\b(\d{4})[\.\-_\/](\d{2})[\.\-_\/](\d{2})\b", "%Y-%m-%d"),  # YYYY-MM-DD or YYYY.MM.DD
        (r"\b(\d{4})(\d{2})(\d{2})\b", "%Y%m%d"),                     # YYYYMMDD
    ]

    for regex, fmt in date_patterns:
        match = re.search(regex, index_name)
        if match:
            try:
                if fmt == "%Y-%m-%d":
                    date_str = f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
                else:
                    date_str = match.group(0)
                creation_dt = datetime.strptime(date_str, fmt).replace(tzinfo=timezone.utc)
                age_seconds = (now - creation_dt).total_seconds()
                return max(0.0, round(age_seconds / 86400.0, 2))
            except ValueError:
                continue

    # Fallback default if age cannot be parsed
    return 0.0


def bytes_to_mb(bytes_val: Any) -> float:
    """Converts bytes to Megabytes (MB)."""
    try:
        val = float(bytes_val)
        return round(val / (1024 * 1024), 2)
    except (ValueError, TypeError):
        return 0.0


def mb_to_gb(mb_val: Any) -> float:
    """Converts Megabytes (MB) to Gigabytes (GB)."""
    try:
        val = float(mb_val)
        return round(val / 1024.0, 2)
    except (ValueError, TypeError):
        return 0.0


def run_concurrent_tasks(
    task_func: Callable[[T], R],
    items: List[T],
    max_workers: int = 4
) -> Dict[T, R]:
    """
    Executes task_func concurrently over a list of items using ThreadPoolExecutor.
    Returns a dict mapping item -> result.
    """
    results: Dict[T, R] = {}
    if not items:
        return results

    actual_workers = min(max_workers, len(items))
    with ThreadPoolExecutor(max_workers=actual_workers) as executor:
        future_to_item = {executor.submit(task_func, item): item for item in items}
        for future in as_completed(future_to_item):
            item = future_to_item[future]
            try:
                results[item] = future.result()
            except Exception as exc:
                results[item] = exc  # Store exception object for caller handling
    return results
