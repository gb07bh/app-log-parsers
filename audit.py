
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
