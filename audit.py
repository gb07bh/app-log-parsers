#!/usr/bin/env python3
"""
Read-only JFrog Artifactory service-account Delete-permission audit.
Designed for Artifactory 7.143.x using the legacy per-user permission endpoint.

Install:
    python -m pip install requests pandas openpyxl

Environment:
    JFROG_URL=https://jfrog.example.com
    JFROG_AUTH_MODE=bearer            # bearer or x-jfrog-api
    JFROG_TOKEN=<access-token-or-api-key>
    # TLS verification is disabled in this script (verify=False), per configuration.
    JFROG_TIMEOUT=30                  # optional
    JFROG_OUTPUT=service_account_delete_audit.xlsx  # optional

Run:
    python jfrog_permission_audit.py

This script makes GET requests only. Review the workbook's Audit Summary and
API Errors sheets before relying on the results. Validate at least one direct
grant and one group-derived grant in your own JFrog instance.
"""
from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlparse
from typing import Any

import pandas as pd
import requests
import urllib3
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# User-requested: suppress warnings caused by verify=False.
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

USER_LIST_PATH = "/access/api/v2/users"
USER_DETAILS_PATH = "/access/api/v2/users/{username}"
REPOSITORIES_PATH = "/artifactory/api/repositories"
# Available on older Artifactory versions; returns permission targets relevant to a user.
USER_PERMISSIONS_PATH = "/artifactory/api/v2/security/permissions/users/{username}"

OUTPUT_COLUMNS = [
    "UserName", "User Email", "Permission Name", "Repository Name",
    "Read", "Write", "Delete", "Annotate",
]
LOGGER = logging.getLogger("jfrog_audit")


class AuditError(RuntimeError):
    pass


def env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    return default if raw is None else raw.strip().lower() in {"1", "true", "yes", "on"}


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("jfrog_permission_audit.log", encoding="utf-8"),
        ],
    )


def normalize_base_url(raw: str) -> str:
    url = raw.strip().rstrip("/")
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise AuditError("JFROG_URL must be a full URL, e.g. https://jfrog.example.com")
    if parsed.username or parsed.password:
        raise AuditError("Do not put credentials in JFROG_URL.")
    return url


def make_session(credential: str, auth_mode: str, verify_tls: bool, timeout: int) -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "Accept": "application/json",
        "User-Agent": "jfrog-readonly-permission-audit/1.2",
    })
    if auth_mode == "bearer":
        session.headers["Authorization"] = f"Bearer {credential}"
    elif auth_mode == "x-jfrog-api":
        session.headers["X-JFrog-Art-Api"] = credential
    else:
        raise AuditError("JFROG_AUTH_MODE must be 'bearer' or 'x-jfrog-api'.")
    # User-requested: disable TLS certificate verification for every request.
    session.verify = False
    session.request_timeout = timeout  # type: ignore[attr-defined]
    retry = Retry(
        total=4, connect=4, read=3, backoff_factor=0.7,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def get_json(session: requests.Session, url: str, params: dict[str, Any] | None = None) -> Any:
    try:
        response = session.get(
            url, params=params, timeout=getattr(session, "request_timeout", 30)
        )
    except requests.RequestException as exc:
        raise AuditError(f"GET failed for {url}: {exc}") from exc
    if not response.ok:
        body = response.text[:1000].replace("\n", " ")
        raise AuditError(f"GET {response.url} returned HTTP {response.status_code}: {body}")
    try:
        return response.json()
    except ValueError as exc:
        raise AuditError(f"Expected JSON from {response.url}") from exc


def list_users(session: requests.Session, base_url: str, page_size: int = 500) -> tuple[int, list[dict[str, Any]]]:
    """Cursor-paginate users and select case-insensitive usernames starting with svc."""
    all_users: list[dict[str, Any]] = []
    cursor: str | None = None
    seen: set[str] = set()

    while True:
        params: dict[str, Any] = {"limit": page_size}
        if cursor:
            params["cursor"] = cursor
        payload = get_json(session, base_url + USER_LIST_PATH, params)
        if isinstance(payload, list):
            batch, next_cursor = payload, None
        elif isinstance(payload, dict):
            batch = payload.get("users", [])
            next_cursor = payload.get("cursor")
        else:
            raise AuditError(f"Unexpected users response type: {type(payload).__name__}")
        if not isinstance(batch, list):
            raise AuditError("Users response did not contain a users array.")
        all_users.extend(u for u in batch if isinstance(u, dict))
        if not next_cursor or not batch:
            break
        cursor = str(next_cursor)
        if cursor in seen:
            raise AuditError("User pagination returned a repeated cursor; stopping to avoid a loop.")
        seen.add(cursor)

    matches = []
    for user in all_users:
        username = user.get("username") or user.get("name")
        if isinstance(username, str) and username.casefold().startswith("svc"):
            matches.append({**user, "username": username})
    LOGGER.info("User list returned %d users; %d start with 'svc'.", len(all_users), len(matches))
    return len(all_users), matches


def get_user_email(session: requests.Session, base_url: str, username: str) -> str:
    url = base_url + USER_DETAILS_PATH.format(username=quote(username, safe=""))
    try:
        payload = get_json(session, url)
    except AuditError as exc:
        LOGGER.warning("Email lookup failed for %s: %s", username, exc)
        return ""
    if isinstance(payload, dict) and payload.get("email"):
        return str(payload["email"]).strip()
    return ""


def list_local_release_repositories(session: requests.Session, base_url: str) -> tuple[int, set[str]]:
    payload = get_json(session, base_url + REPOSITORIES_PATH, {"type": "local"})
    if not isinstance(payload, list):
        raise AuditError("Repository API did not return a JSON array.")
    all_local = set()
    matching = set()
    for item in payload:
        if not isinstance(item, dict):
            continue
        key = item.get("key") or item.get("repoKey") or item.get("name")
        typ = str(item.get("type", "local")).lower()
        if isinstance(key, str) and typ == "local":
            all_local.add(key)
            if "local-release" in key.casefold():
                matching.add(key)
    LOGGER.info("Found %d local repositories; %d contain 'local-release'.", len(all_local), len(matching))
    return len(all_local), matching


def get_user_permissions(session: requests.Session, base_url: str, username: str) -> list[dict[str, Any]]:
    url = base_url + USER_PERMISSIONS_PATH.format(username=quote(username, safe=""))
    payload = get_json(session, url)
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    # Some API gateways wrap arrays in an object.
    if isinstance(payload, dict):
        for key in ("permissions", "permissionTargets", "items"):
            if isinstance(payload.get(key), list):
                return [x for x in payload[key] if isinstance(x, dict)]
    raise AuditError(f"Unexpected permission response shape for user {username!r}.")


def normalize_actions(raw: Any) -> set[str]:
    if not isinstance(raw, list):
        return set()
    return {str(action).strip().casefold().replace("_", "").replace("-", "") for action in raw}


def repo_names_from_target(repo_section: dict[str, Any], all_local: set[str]) -> set[str]:
    raw = repo_section.get("repositories", [])
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        raw = []

    names: set[str] = set()
    for item in raw:
        if not isinstance(item, str):
            continue
        normalized = item.strip()
        if normalized in all_local:
            names.add(normalized)
        elif normalized.casefold() in {"any local", "any-local", "anylocal"}:
            names.update(all_local)
        # Do not expand arbitrary wildcard patterns silently. They are logged below.
        elif "*" in normalized or "?" in normalized:
            LOGGER.warning("Repository wildcard %r not expanded; review manually.", normalized)
    return names


def build_rows(
    username: str,
    email: str,
    permission_targets: list[dict[str, Any]],
    all_local: set[str],
    matching_repos: set[str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for target in permission_targets:
        permission_name = target.get("name") or target.get("permissionName") or ""
        repo = target.get("repo")
        # Legacy endpoint response uses repo.actions and repo.repositories.
        # Be conservative: don't infer repository actions from build permissions.
        if not isinstance(repo, dict):
            continue
        actions = normalize_actions(repo.get("actions", []))
        repos = repo_names_from_target(repo, all_local) & matching_repos

        delete = bool(actions & {"delete", "deleteoverwrite", "deleteartifact"})
        if not delete:
            continue
        read = bool(actions & {"read", "readartifact"})
        write = bool(actions & {"write", "deploy", "writeartifact"})
        annotate = bool(actions & {"annotate", "annotateartifact"})

        for repo_name in sorted(repos):
            rows.append({
                "UserName": username,
                "User Email": email,
                "Permission Name": str(permission_name),
                "Repository Name": repo_name,
                "Read": read,
                "Write": write,
                "Delete": delete,
                "Annotate": annotate,
            })
    return rows


def main() -> int:
    configure_logging()
    raw_url = os.getenv("JFROG_URL", "")
    credential = os.getenv("JFROG_TOKEN", "")
    auth_mode = os.getenv("JFROG_AUTH_MODE", "bearer").strip().lower()
    verify_tls = False  # Deliberately fixed per request: all HTTP calls use verify=False.
    try:
        timeout = int(os.getenv("JFROG_TIMEOUT", "30"))
    except ValueError:
        LOGGER.error("JFROG_TIMEOUT must be an integer.")
        return 2
    output = Path(os.getenv("JFROG_OUTPUT", "service_account_delete_audit.xlsx"))

    if not raw_url or not credential:
        LOGGER.error("Set JFROG_URL and JFROG_TOKEN environment variables.")
        return 2
    if auth_mode not in {"bearer", "x-jfrog-api"}:
        LOGGER.error("JFROG_AUTH_MODE must be 'bearer' or 'x-jfrog-api'.")
        return 2
    if timeout <= 0:
        LOGGER.error("JFROG_TIMEOUT must be positive.")
        return 2
    LOGGER.warning("TLS certificate verification is disabled (verify=False), as configured.")

    try:
        base_url = normalize_base_url(raw_url)
        session = make_session(credential, auth_mode, verify_tls, timeout)

        total_users, users = list_users(session, base_url)
        total_local_repos, matching_repos = list_local_release_repositories(session, base_url)
        # Retrieve the full local repository set for expanding the explicit 'ANY LOCAL' target.
        repo_payload = get_json(session, base_url + REPOSITORIES_PATH, {"type": "local"})
        all_local_repos = {str(x.get('key') or x.get('repoKey') or x.get('name')) for x in repo_payload if isinstance(x, dict) and (x.get('key') or x.get('repoKey') or x.get('name')) and str(x.get('type', 'local')).lower() == 'local'}
        emails: dict[str, str] = {}
        rows: list[dict[str, Any]] = []
        errors: list[dict[str, str]] = []
        permission_successes = 0
        users_with_delete = set()

        for idx, user in enumerate(users, start=1):
            username = user["username"]
            if username not in emails:
                emails[username] = get_user_email(session, base_url, username)
            try:
                targets = get_user_permissions(session, base_url, username)
                permission_successes += 1
                user_rows = build_rows(username, emails[username], targets, all_local_repos, matching_repos)
                if user_rows:
                    users_with_delete.add(username)
                    rows.extend(user_rows)
            except AuditError as exc:
                LOGGER.error("Permission lookup failed for %s: %s", username, exc)
                errors.append({"UserName": username, "Error": str(exc)})
            if idx % 50 == 0:
                LOGGER.info("Processed %d/%d matching users.", idx, len(users))

        results = pd.DataFrame(rows, columns=OUTPUT_COLUMNS)
        if not results.empty:
            results = results.drop_duplicates()
            for col in ("Read", "Write", "Delete", "Annotate"):
                results[col] = results[col].astype(bool)
            results = results.sort_values(
                ["UserName", "Repository Name", "Permission Name"], kind="stable"
            )

        summary = [
            ("Audit timestamp UTC", datetime.now(timezone.utc).isoformat()),
            ("JFrog base URL", base_url),
            ("Authentication mode", auth_mode),
            ("Artifactory version supplied", "7.143.x"),
            ("Username filter", "case-insensitive startswith 'svc' (includes svc_arti)"),
            ("Repository filter", "repository type LOCAL; key contains local-release (case-insensitive)"),
            ("Permission source", "GET /artifactory/api/v2/security/permissions/users/{username}"),
            ("Group permission handling", "Uses per-user permission endpoint; validate group-derived grants in this instance"),
            ("Total users returned by API", total_users),
            ("Matching service accounts", len(users)),
            ("Total local repositories", total_local_repos),
            ("Matching local-release repositories", len(matching_repos)),
            ("Users with successful permission lookup", permission_successes),
            ("Users with permission lookup failures", len(errors)),
            ("Users with matching Delete access", len(users_with_delete)),
            ("Rows exported (Delete=true)", len(results)),
            ("Matching users with missing email", sum(not emails.get(u["username"], "") for u in users)),
            ("TLS verification enabled", False),
            ("InsecureRequestWarning suppressed", True),
            ("Completeness", "INCOMPLETE - see API Errors" if errors else "Review group-grant validation before sign-off"),
        ]
        summary_df = pd.DataFrame(summary, columns=["Metric", "Value"])
        errors_df = pd.DataFrame(errors, columns=["UserName", "Error"])

        output.parent.mkdir(parents=True, exist_ok=True)
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            results.to_excel(writer, index=False, sheet_name="Audit Results")
            summary_df.to_excel(writer, index=False, sheet_name="Audit Summary")
            errors_df.to_excel(writer, index=False, sheet_name="API Errors")
            for sheet_name in ("Audit Results", "Audit Summary", "API Errors"):
                ws = writer.sheets[sheet_name]
                ws.freeze_panes = "A2"
                ws.auto_filter.ref = ws.dimensions
                for cells in ws.columns:
                    width = max((len(str(c.value)) if c.value is not None else 0) for c in cells)
                    ws.column_dimensions[cells[0].column_letter].width = min(max(width + 2, 12), 60)

        LOGGER.info("Excel report saved to %s", output.resolve())
        LOGGER.info("Exported %d rows with Delete=true.", len(results))
        if errors:
            LOGGER.error("Audit incomplete: %d user permission lookups failed.", len(errors))
            return 1
        LOGGER.warning("Before sign-off, validate at least one group-derived Delete grant against the JFrog UI.")
        return 0

    except (AuditError, requests.RequestException, OSError, ValueError) as exc:
        LOGGER.exception("Audit failed: %s", exc)
        return 2


if __name__ == "__main__":
    # Fix variable typo guard is intentionally kept simple below in patched version.
    raise SystemExit(main())
