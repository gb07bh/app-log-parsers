function parse_repo(tag, timestamp, record)

    --
    -- URL required
    --
    local url = record["url"]

    if url == nil then
        return 1, timestamp, record
    end

    url = string.lower(url)

    --
    -- localhost detection
    --
    local remote_address = record["remote_address"]

    if remote_address ~= nil then

        if remote_address == "127.0.0.1" or
           remote_address == "localhost" then

            record["client_type"] = "localhost"
        end
    end

    --
    -- extract repository
    --
    -- supports:
    --
    -- /artifactory/repo-name/path
    -- /repo-name/path
    --

    local repo =
        string.match(url, "^/artifactory/([^/]+)")

    if repo == nil then

        repo =
            string.match(url, "^/([^/]+)")
    end

    if repo == nil then
        return 1, timestamp, record
    end

    --
    -- ignore internal API/system endpoints
    --
    if repo == "api" or
       repo == "ui" or
       repo == "router" or
       repo == "access" then

        return 1, timestamp, record
    end

    record["repo"] = repo

    --
    -- local repository
    -- pattern:
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
    -- remote repository
    -- patterns:
    -- docker-remote
    -- nuget-remote-cache
    -- maven-remote-cache
    --
    local remote_tech =
        string.match(repo,
            "^([^-]+)-remote.*$")

    if remote_tech ~= nil then

        record["techtype"] = remote_tech
        record["repo_type"] = "remote"

        return 1, timestamp, record
    end

    --
    -- virtual repository
    -- pattern:
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