"""
OpenSearch Automation V2 - Logging Configuration

Configures standard logging output to stdout (for Jenkins console)
and file handler pointing to logs/automation.log.
"""

import sys
import logging
from pathlib import Path
import config


def setup_logging(verbose: bool = False, log_filename: str = "automation.log") -> logging.Logger:
    """
    Sets up application logging across stream (stdout) and file handlers.
    """
    log_level = logging.DEBUG if verbose else logging.INFO
    log_format = "%(asctime)s [%(levelname)s] [%(name)s] %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    formatter = logging.Formatter(log_format, datefmt=date_format)

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Clear existing handlers to avoid duplicate logs when imported multiple times
    if root_logger.hasHandlers():
        root_logger.handlers.clear()

    # Stream Handler (Stdout for Jenkins Console)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # File Handler
    log_file_path = Path(config.LOG_DIR) / log_filename
    file_handler = logging.FileHandler(log_file_path, encoding="utf-8")
    file_handler.setLevel(log_level)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    return root_logger
