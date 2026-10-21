#!/usr/bin/env python3
"""
Read-only JFrog Artifactory service-account Delete-permission audit.
Designed for Artifactory 7.143.x using permission-target-centric retrieval.

Install:
    python -m pip install requests pandas openpyxl

Edit the global USER CONFIGURATION block, then run:
    python jfrog_permission_audit_globals.py

This script makes GET requests only. Review the workbook's Audit Summary and
API Errors sheets before relying on the results. Validate at least one direct
grant and one group-derived grant in your own JFrog instance.
"""
from __future__ import annotations

import logging
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlparse
from typing import Any

import pandas as pd
from tqdm import tqdm
import requests
import urllib3
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# User-requested: suppress warnings caused by verify=False.
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

USER_LIST_PATH = "/access/api/v2/users"
USER_DETAILS_PATH = "/access/api/v2/users/{username}"
REPOSITORIES_PATH = "/artifactory/api/repositories"

OUTPUT_COLUMNS = [
    "UserName", "User Email", "Permission Name", "Repository Name",
    "Read", "Write", "Delete", "Annotate",
]
LOGGER = logging.getLogger("jfrog_audit")

# ---------------------------------------------------------------------------
# USER CONFIGURATION — edit these values directly in this script.
# ---------------------------------------------------------------------------
JFROG_URL = "https://your-jfrog-host"
JFROG_AUTH_MODE = "bearer"  # "bearer" or "x-jfrog-api"
JFROG_TOKEN = "REPLACE_WITH_YOUR_TOKEN"
REQUEST_TIMEOUT = 30  # seconds
OUTPUT_FILE = "service_account_delete_audit.xlsx"
MAX_WORKERS = 4  # Hard cap requested; tune lower if the server rate-limits requests.
# ---------------------------------------------------------------------------



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



def list_permission_target_names(session: requests.Session, base_url: str) -> list[str]:
    """List repository permission targets once using the legacy API supported on 7.143.x."""
    payload = get_json(session, base_url + "/artifactory/api/v2/security/permissions")
    if not isinstance(payload, list):
        raise AuditError("Permission target list API did not return a JSON array.")
    return list(dict.fromkeys(
        item["name"] for item in payload
        if isinstance(item, dict) and isinstance(item.get("name"), str) and item["name"]
    ))


def get_permission_target_detail(
    session: requests.Session, base_url: str, permission_name: str
) -> dict[str, Any]:
    url = base_url + "/artifactory/api/v2/security/permissions/" + quote(permission_name, safe="")
    payload = get_json(session, url)
    if not isinstance(payload, dict):
        raise AuditError(f"Permission target {permission_name!r} returned non-object JSON.")
    return payload


def get_user_profile_and_groups(
    session: requests.Session, base_url: str, username: str
) -> tuple[str, set[str], bool]:
    """Fetch email and group membership in one legacy user-details request."""
    url = base_url + "/artifactory/api/security/users/" + quote(username, safe="")
    payload = get_json(session, url)
    if not isinstance(payload, dict):
        raise AuditError(f"User details for {username!r} returned non-object JSON.")
    email = str(payload.get("email") or "").strip()
    raw_groups = payload.get("groups", payload.get("groupNames", payload.get("user_groups")))
    if isinstance(raw_groups, list):
        return email, {str(g).casefold() for g in raw_groups if isinstance(g, str)}, True
    if isinstance(raw_groups, dict):
        return email, {str(g).casefold() for g in raw_groups.keys()}, True
    return email, set(), False


def parse_target_grants(target: dict[str, Any]) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    """Extract direct user and group action grants from a legacy permission target."""
    repo = target.get("repo")
    actions = repo.get("actions", {}) if isinstance(repo, dict) else {}
    users: dict[str, set[str]] = {}
    groups: dict[str, set[str]] = {}
    if not isinstance(actions, dict):
        return users, groups
    for key, destination in (("users", users), ("groups", groups)):
        grants = actions.get(key, {})
        if isinstance(grants, dict):
            for principal, raw_actions in grants.items():
                if isinstance(raw_actions, list):
                    destination[str(principal).casefold()] = {
                        str(a).strip().casefold().replace("_", "").replace("-", "")
                        for a in raw_actions
                    }
    return users, groups


def target_matching_repositories(
    target: dict[str, Any], all_local_repos: set[str], matching_repos: set[str]
) -> set[str]:
    repo = target.get("repo")
    raw = repo.get("repositories", []) if isinstance(repo, dict) else []
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        return set()
    found: set[str] = set()
    for item in raw:
        if not isinstance(item, str):
            continue
        name = item.strip()
        if name in all_local_repos:
            found.add(name)
        elif name.casefold() in {"any local", "any-local", "anylocal"}:
            found.update(all_local_repos)
        elif name.casefold() in {"any", "any repository", "any-repository"}:
            found.update(matching_repos)
        elif "*" in name or "?" in name:
            LOGGER.warning("Permission target %r has wildcard repository pattern %r; not expanded automatically.",
                           target.get("name", "<unnamed>"), name)
    return found & matching_repos


def action_flags(actions: set[str]) -> dict[str, bool]:
    normalized = {a.casefold().replace("_", "").replace("-", "") for a in actions}
    return {
        "Read": bool(normalized & {"read", "readartifact"}),
        "Write": bool(normalized & {"write", "deploy", "writeartifact"}),
        "Delete": bool(normalized & {"delete", "deleteoverwrite", "deleteartifact"}),
        "Annotate": bool(normalized & {"annotate", "annotateartifact"}),
    }


def map_permission_targets_to_users(
    users: list[dict[str, Any]],
    profiles: dict[str, tuple[str, set[str], bool]],
    targets: list[dict[str, Any]],
    all_local_repos: set[str],
    matching_repos: set[str],
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    rows: list[dict[str, Any]] = []
    group_gaps: list[dict[str, str]] = []
    for user in users:
        username = user["username"]
        email, memberships, has_group_data = profiles.get(username.casefold(), ("", set(), False))
        if not has_group_data:
            group_gaps.append({
                "UserName": username,
                "Error": "User details did not expose group memberships; group-derived grants may be omitted."
            })
        for target in targets:
            user_grants, group_grants = parse_target_grants(target)
            actions = set(user_grants.get(username.casefold(), set()))
            for group in memberships:
                actions.update(group_grants.get(group, set()))
            flags = action_flags(actions)
            if not flags["Delete"]:
                continue
            repos = target_matching_repositories(target, all_local_repos, matching_repos)
            for repo_name in sorted(repos):
                rows.append({
                    "UserName": username,
                    "User Email": email,
                    "Permission Name": str(target.get("name") or ""),
                    "Repository Name": repo_name,
                    **flags,
                })
    return rows, group_gaps

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
    raw_url = JFROG_URL
    credential = JFROG_TOKEN
    auth_mode = JFROG_AUTH_MODE.strip().lower()
    verify_tls = False  # All requests use verify=False as requested.
    timeout = REQUEST_TIMEOUT
    output = Path(OUTPUT_FILE)

    if not raw_url or not credential or credential == "REPLACE_WITH_YOUR_TOKEN":
        LOGGER.error("Set JFROG_URL and JFROG_TOKEN in the USER CONFIGURATION section.")
        return 2
    if auth_mode not in {"bearer", "x-jfrog-api"}:
        LOGGER.error("JFROG_AUTH_MODE must be 'bearer' or 'x-jfrog-api'.")
        return 2
    if not isinstance(timeout, int) or timeout <= 0:
        LOGGER.error("REQUEST_TIMEOUT must be a positive integer.")
        return 2
    LOGGER.warning("TLS certificate verification is disabled (verify=False), as configured.")

    try:
        base_url = normalize_base_url(raw_url)
        session = make_session(credential, auth_mode, verify_tls, timeout)

        total_users, users = list_users(session, base_url)
        total_local_repos, matching_repos = list_local_release_repositories(session, base_url)
        repo_payload = get_json(session, base_url + REPOSITORIES_PATH, {"type": "local"})
        all_local_repos = {
            str(item.get("key") or item.get("repoKey") or item.get("name"))
            for item in repo_payload
            if isinstance(item, dict)
            and (item.get("key") or item.get("repoKey") or item.get("name"))
            and str(item.get("type", "local")).lower() == "local"
        }

        if not isinstance(MAX_WORKERS, int) or not 1 <= MAX_WORKERS <= 4:
            raise AuditError("MAX_WORKERS must be an integer from 1 through 4.")

        profile_errors: list[dict[str, str]] = []
        permission_errors: list[dict[str, str]] = []
        profiles: dict[str, tuple[str, set[str], bool]] = {}

        def fetch_profile(username: str):
            worker_session = make_session(credential, auth_mode, verify_tls, timeout)
            try:
                return username, get_user_profile_and_groups(worker_session, base_url, username), None
            except AuditError as exc:
                return username, None, str(exc)
            finally:
                worker_session.close()

        # One profile request per service account; retrieves email and group memberships.
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = [executor.submit(fetch_profile, u["username"]) for u in users]
            for future in tqdm(as_completed(futures), total=len(futures),
                               desc="Fetching user profiles", unit="user"):
                try:
                    username, profile, error = future.result()
                except Exception as exc:
                    profile_errors.append({"UserName": "<unknown>", "Error": str(exc)})
                    continue
                if error or profile is None:
                    profile_errors.append({"UserName": username, "Error": error or "Unknown profile error"})
                else:
                    profiles[username.casefold()] = profile

        # Fetch each permission target once rather than once per user.
        permission_names = list_permission_target_names(session, base_url)
        permission_targets: list[dict[str, Any]] = []

        def fetch_target(name: str):
            worker_session = make_session(credential, auth_mode, verify_tls, timeout)
            try:
                return name, get_permission_target_detail(worker_session, base_url, name), None
            except AuditError as exc:
                return name, None, str(exc)
            finally:
                worker_session.close()

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = [executor.submit(fetch_target, name) for name in permission_names]
            for future in tqdm(as_completed(futures), total=len(futures),
                               desc="Fetching permission targets", unit="target"):
                try:
                    name, target, error = future.result()
                except Exception as exc:
                    permission_errors.append({"Permission Name": "<unknown>", "Error": str(exc)})
                    continue
                if error or target is None:
                    permission_errors.append({"Permission Name": name, "Error": error or "Unknown target error"})
                else:
                    permission_targets.append(target)

        rows, group_gaps = map_permission_targets_to_users(
            users, profiles, permission_targets, all_local_repos, matching_repos
        )
        errors = (
            [{"UserName": x["UserName"], "Error": x["Error"]} for x in profile_errors]
            + [{"UserName": "Permission target: " + x["Permission Name"], "Error": x["Error"]}
               for x in permission_errors]
            + group_gaps
        )
        emails = {u["username"]: profiles.get(u["username"].casefold(), ("", set(), False))[0] for u in users}
        permission_successes = len(permission_targets)
        users_with_delete = {r["UserName"] for r in rows}

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
            ("Parallel worker threads", MAX_WORKERS),
            ("Artifactory version supplied", "7.143.x"),
            ("Username filter", "case-insensitive startswith 'svc' (includes svc_arti)"),
            ("Repository filter", "repository type LOCAL; key contains local-release (case-insensitive)"),
            ("Permission source", "Permission-target-centric: list and fetch each target once"),
            ("Group permission handling", "Maps user memberships to group grants from permission targets; validate against UI"),
            ("Permission targets listed", len(permission_names)),
            ("Permission targets fetched successfully", len(permission_targets)),
            ("Permission target fetch failures", len(permission_errors)),
            ("User profile fetch failures", len(profile_errors)),
            ("Users missing group membership data", len(group_gaps)),
            ("Total users returned by API", total_users),
            ("Matching service accounts", len(users)),
            ("Total local repositories", total_local_repos),
            ("Matching local-release repositories", len(matching_repos)),
            ("Permission targets processed successfully", permission_successes),
            ("User/target/group data errors", len(errors)),
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
    raise SystemExit(main())
