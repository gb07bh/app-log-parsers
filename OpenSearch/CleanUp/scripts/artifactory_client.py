"""
OpenSearch Automation V2 - Artifactory Client Wrapper

Wrapper for REST interactions with Artifactory (HEAD, GET, PUT)
to manage rolling 30-day cluster metrics CSV storage.
"""

import os
import logging
from pathlib import Path
from typing import Optional
import requests

import config
import creds

logger = logging.getLogger(__name__)


class ArtifactoryClient:
    """
    REST Client for Artifactory artifact repository.
    Constructs target path as: {arti_url}/artifactory/{repo_name}/{upload_path}
    """

    def __init__(
        self,
        arti_url: Optional[str] = None,
        repo_name: Optional[str] = None,
        upload_path: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        token: Optional[str] = None,
    ):
        self.arti_url = (arti_url or creds.ARTIFACTORY_URL).rstrip("/")
        self.repo_name = repo_name or creds.ARTIFACTORY_REPO
        self.upload_path = (upload_path or creds.ARTIFACTORY_UPLOAD_PATH).strip("/")

        # Concatenated target base path as explicitly requested
        self.base_url = f"{self.arti_url}/artifactory/{self.repo_name}/{self.upload_path}"

        self.session = requests.Session()
        self.session.verify = config.VERIFY_SSL

        token_val = token if (token and token != "UNDEFINED") else creds.ARTIFACTORY_TOKEN
        user_val = username if (username and username != "UNDEFINED") else creds.ARTIFACTORY_USER
        pass_val = password if (password and password != "UNDEFINED") else creds.ARTIFACTORY_PASSWORD

        if token_val and token_val != "UNDEFINED":
            self.session.headers.update({"Authorization": f"Bearer {token_val}"})
        elif user_val and user_val != "UNDEFINED":
            self.session.auth = (user_val, pass_val)

    def file_exists(self, filename: str) -> bool:
        """Sends HTTP HEAD request to check if file exists in Artifactory."""
        url = f"{self.base_url}/{filename.lstrip('/')}"
        try:
            response = self.session.head(url, timeout=config.REQUEST_TIMEOUT)
            return response.status_code == 200
        except Exception as exc:
            logger.warning(f"Artifactory HEAD check for {url} failed: {exc}")
            return False

    def download_file(self, filename: str, destination_path: Path) -> bool:
        """Sends HTTP GET request to download file from Artifactory."""
        url = f"{self.base_url}/{filename.lstrip('/')}"
        try:
            response = self.session.get(url, timeout=config.REQUEST_TIMEOUT)
            if response.status_code == 200:
                destination_path.parent.mkdir(parents=True, exist_ok=True)
                destination_path.write_bytes(response.content)
                logger.info(f"Successfully downloaded {filename} from Artifactory")
                return True
            logger.warning(f"Download failed for {url} with status {response.status_code}")
            return False
        except Exception as exc:
            logger.error(f"Failed to download {filename} from Artifactory: {exc}")
            return False

    def upload_file(self, source_path: Path, filename: str) -> bool:
        """Sends HTTP PUT request to upload file to Artifactory."""
        url = f"{self.base_url}/{filename.lstrip('/')}"
        try:
            if not source_path.exists():
                logger.error(f"Local file {source_path} does not exist for upload.")
                return False
            with open(source_path, "rb") as f:
                response = self.session.put(url, data=f, timeout=config.REQUEST_TIMEOUT)
            if response.status_code in (200, 201):
                logger.info(f"Successfully uploaded {filename} to Artifactory ({url})")
                return True
            logger.error(f"Upload to {url} failed with status {response.status_code}: {response.text}")
            return False
        except Exception as exc:
            logger.error(f"Failed to upload {filename} to Artifactory: {exc}")
            return False
