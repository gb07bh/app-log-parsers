"""
OpenSearch Automation V2 - Dashboard Orchestrator Script

Consolidates cleanup and metrics CSV reports and triggers the HTML dashboard generator.
Outputs reports/html/dashboard.html.
"""

import sys
import argparse
import logging
from datetime import datetime, timezone
from pathlib import Path

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from scripts.logging_config import setup_logging
from scripts import reporting
from scripts import html_report

logger = logging.getLogger("dashboard")


def generate_dashboard() -> Path:
    """
    Consolidates CSV report files and outputs final executive HTML dashboard.
    """
    logger.info("Reading and consolidating CSV reports...")
    cleanup_df = reporting.consolidate_cleanup_reports(config.CSV_REPORT_DIR)
    metrics_df = reporting.consolidate_metrics_reports(config.CSV_REPORT_DIR)

    output_path = config.HTML_REPORT_DIR / "dashboard.html"
    generated_at_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    logger.info(f"Generating HTML dashboard with {len(cleanup_df)} cleanup rows and {len(metrics_df)} metrics rows...")
    final_path = html_report.render_dashboard(
        cleanup_df=cleanup_df,
        metrics_df=metrics_df,
        output_html_path=output_path,
        generated_at=generated_at_str,
    )

    logger.info(f"Dashboard generation successful: {final_path}")
    return final_path


def main():
    parser = argparse.ArgumentParser(description="OpenSearch Automation V2 - Executive Dashboard Generator")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose debug logging")

    args = parser.parse_args()
    setup_logging(verbose=args.verbose, log_filename="dashboard.log")

    generate_dashboard()


if __name__ == "__main__":
    main()
