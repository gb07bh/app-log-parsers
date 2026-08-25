
local function empty_to_nil(value)
    if value == nil then return nil end
    value = tostring(value)
    if value == "" or value == "-" then return nil end
    return value
end

local function to_number(value)
    value = empty_to_nil(value)
    if value == nil then return nil end
    return tonumber(value)
end

local function normalize_timestamp(value)
    if value == nil then return nil end
    value = tostring(value)

    if value:match("^%d+$") then
        local epoch_ms = tonumber(value)
        if epoch_ms == nil then return nil end
        local seconds = math.floor(epoch_ms / 1000)
        local milliseconds = epoch_ms % 1000
        local t = os.date("!*t", seconds)
        if t == nil then return nil end
        return string.format("%04d-%02d-%02dT%02d:%02d:%02d.%03dZ", t.year, t.month, t.day, t.hour, t.min, t.sec, milliseconds)
    end

    local year, month, day, hour, minute, second, milliseconds = value:match("^(%d%d%d%d)%-(%d%d)%-(%d%d) (%d%d):(%d%d):(%d%d),(%d%d%d)$")
    if year == nil then return nil end

    local epoch = os.time({
        year = tonumber(year),
        month = tonumber(month),
        day = tonumber(day),
        hour = tonumber(hour),
        min = tonumber(minute),
        sec = tonumber(second)
    })

    if epoch == nil then return nil end

    local t = os.date("!*t", epoch)
    if t == nil then return nil end

    return string.format("%04d-%02d-%02dT%02d:%02d:%02d.%03dZ", t.year, t.month, t.day, t.hour, t.min, t.sec, tonumber(milliseconds))
end

local function parse_request_id(record, field_name, prefix)
    local value = record[field_name]
    if value == nil then return end

    value = tostring(value)
    if value == "" or value == "-" then return end

    record[prefix .. "_original"] = value

    local direction, cluster_marker, node_id, minute_of_day, request_number, concurrent = value:match("^([io])([*@])([^x]+)x(%d+)x(%d+)x(%d+)$")

    if node_id == nil then
        cluster_marker, node_id, minute_of_day, request_number, concurrent = value:match("^([*@])([^x]+)x(%d+)x(%d+)x(%d+)$")
    end

    if node_id == nil then return end

    if direction == "i" then
        record[prefix .. "_direction"] = "input"
    elseif direction == "o" then
        record[prefix .. "_direction"] = "output"
    end

    record[prefix .. "_cluster_marker"] = cluster_marker
    record[prefix .. "_clustered"] = cluster_marker == "*"
    record[prefix .. "_node_id"] = node_id

    local minute_value = tonumber(minute_of_day)

    if minute_value ~= nil then
        record[prefix .. "_minute_of_day"] = minute_value
        record[prefix .. "_hour"] = math.floor(minute_value / 60)
        record[prefix .. "_minute"] = minute_value % 60
    end

    record[prefix .. "_request_number"] = tonumber(request_number)
    record[prefix .. "_concurrent"] = tonumber(concurrent)

    if direction ~= nil then
        record[prefix .. "_correlation_id"] = string.sub(value, 3)
    else
        record[prefix .. "_correlation_id"] = string.sub(value, 2)
    end
end

local function parse_client_ip(record)
    local value = record["client_ip"]
    if value == nil then return end

    value = tostring(value)
    record["client_ip_original"] = value

    if value:find(",", 1, true) then
        local first, remainder = value:match("^%s*([^,]+)%s*,%s*(.*)$")

        if first ~= nil then
            record["client_ip_forwarded"] = first
            record["client_ip_remote"] = remainder
        end
    else
        record["client_ip_remote"] = value
    end
end

local function normalize_access_fields(record)
    local value

    if record["status"] ~= nil then
        value = to_number(record["status"])
        if value ~= nil then record["status"] = value end
    end

    if record["bytes_read"] ~= nil then
        value = to_number(record["bytes_read"])
        if value ~= nil then record["bytes_read"] = value end
    end

    if record["bytes_written"] ~= nil then
        value = to_number(record["bytes_written"])
        if value ~= nil then record["bytes_written"] = value end
    end

    if record["duration_ms"] ~= nil then
        value = to_number(record["duration_ms"])
        if value ~= nil then record["duration_ms"] = value end
    end
end

local function parse_application_log(record)
    local raw = record["log"]

    if raw == nil then
        raw = record["message"]
    end

    if raw == nil then
        record["application_parse_error"] = true
        return
    end

    raw = tostring(raw)

    local app_timestamp, level, thread, remainder = raw:match("^(%d%d%d%d%-%d%d%-%d%d %d%d:%d%d:%d%d,%d%d%d) ([A-Z]+) %[([^%]]*)%] (.*)$")

    if app_timestamp == nil then
        record["application_parse_error"] = true
        record["application_raw"] = raw
        return
    end

    record["timestamp"] = app_timestamp
    record["level"] = level
    record["thread"] = thread

    local request_id, after_request = remainder:match("^([io][*@][A-Za-z0-9]+x%d+x%d+x%d+)%s+(.*)$")

    if request_id ~= nil then
        record["request_id"] = request_id
        parse_request_id(record, "request_id", "request_id")
        remainder = after_request
    end

    local logger, message = remainder:match("^(%S+)%s+(.*)$")

    if logger == nil then
        record["logger"] = remainder
        record["message"] = ""
    else
        record["logger"] = logger
        record["message"] = message
    end

    if record["request_id"] == nil then
        local message_request_id = tostring(record["message"]):match("[io][*@][A-Za-z0-9]+x%d+x%d+x%d+")

        if message_request_id ~= nil then
            record["request_id"] = message_request_id
            parse_request_id(record, "request_id", "request_id")
        end
    end

    record["log"] = nil
end

function normalize(tag, timestamp, record)
    local is_access = tag == "bitbucket.access"
    local is_application = tag == "bitbucket.application"
    local is_audit = tag == "bitbucket.audit"

    record["log_source"] = "bitbucket-data-center"

    if is_access then
        parse_client_ip(record)
        parse_request_id(record, "request_id", "request_id")
        normalize_access_fields(record)
    end

    if is_application then
        parse_application_log(record)
    end

    if is_audit then
        parse_client_ip(record)
        parse_request_id(record, "request_id", "request_id")

        if record["timestamp_ms"] ~= nil then
            record["timestamp_ms"] = tonumber(record["timestamp_ms"])
        end
    end

    if record["timestamp"] ~= nil then
        local normalized = normalize_timestamp(record["timestamp"])
        if normalized ~= nil then record["@timestamp"] = normalized end
    elseif record["timestamp_ms"] ~= nil then
        local normalized = normalize_timestamp(record["timestamp_ms"])
        if normalized ~= nil then record["@timestamp"] = normalized end
    end

    if not is_audit then
        record["timestamp"] = nil
    end

    return 1, timestamp, record
end