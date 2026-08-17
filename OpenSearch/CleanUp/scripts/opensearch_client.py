"""
OpenSearch Automation V2 - OpenSearch Client Wrapper

Handles HTTP REST communications with OpenSearch REST APIs including:
- /_cluster/health
- /_nodes/stats
- /_cat/indices?format=json&bytes=mb
- /_cat/shards?format=json
- DELETE /{index}
"""

import logging
from typing import Dict, List, Any, Optional
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import urllib3

import config

logger = logging.getLogger(__name__)

# Suppress insecure HTTPS warnings when VERIFY_SSL is False
if not config.VERIFY_SSL:
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class OpenSearchClient:
    """
    REST Client for OpenSearch clusters with session reuse, retries, and error handling.
    """

    def __init__(
        self,
        base_url: str,
        auth: Optional[tuple] = None,
        verify_ssl: bool = config.VERIFY_SSL,
        timeout: int = config.REQUEST_TIMEOUT,
        retries: int = config.REST_RETRIES,
        backoff_factor: float = config.REST_BACKOFF_SECONDS,
    ):
        self.base_url = base_url.rstrip("/")
        self.verify_ssl = verify_ssl
        self.timeout = timeout

        self.session = requests.Session()
        if auth and auth[0] != "UNDEFINED" and auth[1] != "UNDEFINED":
            self.session.auth = auth

        self.session.verify = self.verify_ssl

        # Configure Retry logic
        retry_strategy = Retry(
            total=retries,
            backoff_factor=backoff_factor,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "HEAD", "PUT", "DELETE"],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    def _request(self, method: str, endpoint: str, params: Optional[Dict] = None, json_data: Optional[Dict] = None) -> Any:
        """Helper to send HTTP request and return JSON response."""
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        try:
            response = self.session.request(
                method=method,
                url=url,
                params=params,
                json=json_data,
                timeout=self.timeout,
            )
            response.raise_for_status()
            if response.status_code == 204:
                return {}
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"HTTP {method} request to {url} failed: {e}")
            raise

    def get_cluster_health(self) -> Dict[str, Any]:
        """GET /_cluster/health"""
        return self._request("GET", "/_cluster/health")

    def get_node_stats(self) -> Dict[str, Any]:
        """GET /_nodes/stats"""
        return self._request("GET", "/_nodes/stats")

    def get_cat_indices(self) -> List[Dict[str, Any]]:
        """GET /_cat/indices?format=json&bytes=mb"""
        params = {"format": "json", "bytes": "mb"}
        return self._request("GET", "/_cat/indices", params=params)

    def get_cat_shards(self) -> List[Dict[str, Any]]:
        """GET /_cat/shards?format=json"""
        params = {"format": "json"}
        return self._request("GET", "/_cat/shards", params=params)

    def get_index_settings(self, index_name: str) -> Dict[str, Any]:
        """GET /{index_name}"""
        return self._request("GET", f"/{index_name}")

    def delete_index(self, index_name: str) -> Dict[str, Any]:
        """DELETE /{index_name}"""
        logger.info(f"Issuing REST DELETE command for index: {index_name}")
        return self._request("DELETE", f"/{index_name}")
