function parse_repo(tag, timestamp, record)

    local url = record["url"]

    if url == nil then
        return 1, timestamp, record
    end

    url = string.lower(url)

    --
    -- Extract repository from URL
    --
    -- Example:
    -- /artifactory/payments-maven-local-dev/com/test/app.jar
    --

    local repo =
        string.match(url, "^/artifactory/([^/]+)")

    if repo == nil then
        return 1, timestamp, record
    end

    record["repo"] = repo

    --
    -- team-techtype-local-env
    --
    local team, techtype, environment =
        string.match(repo,
            "^([^-]+)-([^-]+)-local%-([^-]+)$")

    if team ~= nil then

        record["team"] = team
        record["techtype"] = techtype
        record["environment"] = environment
        record["repo_type"] = "local"

        return 1, timestamp, record
    end

    --
    -- techtype-remote
    --
    local remote_tech =
        string.match(repo,
            "^([^-]+)-remote$")

    if remote_tech ~= nil then

        record["techtype"] = remote_tech
        record["repo_type"] = "remote"

        return 1, timestamp, record
    end

    --
    -- team-techtype
    --
    local virtual_team, virtual_tech =
        string.match(repo,
            "^([^-]+)-([^-]+)$")

    if virtual_team ~= nil then

        record["team"] = virtual_team
        record["techtype"] = virtual_tech
        record["repo_type"] = "virtual"

        return 1, timestamp, record
    end

    --
    -- fallback
    --
    record["repo_type"] = "unknown"

    return 1, timestamp, record
end