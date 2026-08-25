-- ============================================================
-- Bitbucket Data Center Fluent Bit normalization
-- ============================================================

local function normalize_timestamp(value)
    if value == nil then
        return nil
    end

    value = tostring(value)

    -- Bitbucket application/access/Mesh/search logs:
    -- 2022-04-12 07:00:50,059
    local year, month, day, hour, minute, second, millis =
        value:match("^(%d%d%d%d)%-(%d%d)%-(%d%d) (%d%d):(%d%d):(%d%d),(%d%d%d)$")

    if year then
        local epoch = os.time({
            year  = tonumber(year),
            month = tonumber(month),
            day   = tonumber(day),
            hour  = tonumber(hour),
            min   = tonumber(minute),
            sec   = tonumber(second)
        })

        if epoch then
            return string.format(
                "%04d-%02d-%02dT%02d:%02d:%02d.%03dZ",
                os.date("!*t", epoch).year,
                os.date("!*t", epoch).month,
                os.date("!*t", epoch).day,
                os.date("!*t", epoch).hour,
                os.date("!*t", epoch).min,
                os.date("!*t", epoch).sec,
                tonumber(millis)
            )
        end
    end

    -- Audit log:
    -- epoch milliseconds since 1970-01-01
    local epoch_ms = tonumber(value)

    if epoch_ms then
        local seconds = math.floor(epoch_ms / 1000)
        local millis = epoch_ms % 1000
        local t = os.date("!*t", seconds)

        return string.format(
            "%04d-%02d-%02dT%02d:%02d:%02d.%03dZ",
            t.year,
            t.month,
            t.day,
            t.hour,
            t.min,
            t.sec,
            millis
        )
    end

    return nil
end


local function normalize_dash_number(value)
    if value == nil or value == "" or value == "-" then
        return nil
    end

    return tonumber(value)
end


local function set_direction(record, id_field, direction_field)
    local id = record[id_field]

    if id == nil then
        return
    end

    id = tostring(id)

    local first = id:sub(1, 1)

    if first == "i" then
        record[direction_field] = "input"
    elseif first == "o" then
        record[direction_field] = "output"
    end
end


function normalize(tag, timestamp, record)

    -- --------------------------------------------------------
    -- Common request ID normalization
    -- --------------------------------------------------------

    -- Standard Bitbucket access log
    if record["request_id"] ~= nil then

        -- Preserve the original ID explicitly.
        record["request_id_original"] = record["request_id"]

        set_direction(
            record,
            "request_id",
            "request_direction"
        )
    end


    -- --------------------------------------------------------
    -- Mesh access
    --
    -- Mesh execution ID has the i/o prefix.
    -- Bitbucket request ID is a separate correlation ID.
    -- --------------------------------------------------------

    if record["mesh_execution_id"] ~= nil then

        record["mesh_execution_id_original"] =
            record["mesh_execution_id"]

        set_direction(
            record,
            "mesh_execution_id",
            "mesh_request_direction"
        )
    end


    -- --------------------------------------------------------
    -- Normalize timestamps
    -- --------------------------------------------------------

    if record["timestamp"] ~= nil then

        local normalized =
            normalize_timestamp(record["timestamp"])

        if normalized ~= nil then
            record["@timestamp"] = normalized
        end

    elseif record["timestamp_ms"] ~= nil then

        local normalized =
            normalize_timestamp(record["timestamp_ms"])

        if normalized ~= nil then
            record["@timestamp"] = normalized
        end
    end


    -- --------------------------------------------------------
    -- Access log numeric fields
    -- --------------------------------------------------------

    if record["status"] ~= nil then
        record["status"] =
            normalize_dash_number(record["status"])
    end

    if record["bytes_read"] ~= nil then
        record["bytes_read"] =
            normalize_dash_number(record["bytes_read"])
    end

    if record["bytes_written"] ~= nil then
        record["bytes_written"] =
            normalize_dash_number(record["bytes_written"])
    end

    if record["duration_ms"] ~= nil then
        record["duration_ms"] =
            normalize_dash_number(record["duration_ms"])
    end


    -- --------------------------------------------------------
    -- Mesh access numeric fields
    -- --------------------------------------------------------

    if record["rpc_status"] ~= nil then
        record["rpc_status"] =
            normalize_dash_number(record["rpc_status"])
    end

    if record["incoming_messages"] ~= nil then
        record["incoming_messages"] =
            normalize_dash_number(record["incoming_messages"])
    end

    if record["outgoing_messages"] ~= nil then
        record["outgoing_messages"] =
            normalize_dash_number(record["outgoing_messages"])
    end


    -- --------------------------------------------------------
    -- Audit timestamp
    -- Keep the original timestamp_ms for traceability.
    -- --------------------------------------------------------

    if record["timestamp_ms"] ~= nil then
        record["timestamp_ms"] =
            tonumber(record["timestamp_ms"])
    end


    -- --------------------------------------------------------
    -- Remove parser-specific timestamp fields only after the
    -- normalized @timestamp has been created.
    -- --------------------------------------------------------

    record["timestamp"] = nil


    return 1, timestamp, record
end