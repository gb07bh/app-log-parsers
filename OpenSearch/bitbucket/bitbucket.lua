```lua
-- ============================================================
-- Bitbucket Data Center
-- Fluent Bit Lua normalization
--
-- Currently handles ONLY:
--
--   1. bitbucket.access
--   2. bitbucket.application
--   3. bitbucket.audit
--
-- NOT currently handled:
--
--   - Mesh access
--   - Mesh application
--   - Bitbucket Search
--
-- Responsibilities:
--
--   1. Timestamp normalization
--   2. Request ID decomposition
--   3. Input/output detection
--   4. Request correlation ID
--   5. Client IP decomposition
--   6. Access-log numeric field conversion
--   7. Extract request IDs appearing inside application logs
--
-- Original request IDs are NEVER overwritten.
-- ============================================================


-- ============================================================
-- Utility: empty / "-" -> nil
-- ============================================================

local function empty_to_nil(value)

    if value == nil then
        return nil
    end

    value = tostring(value)

    if value == "" or value == "-" then
        return nil
    end

    return value
end


-- ============================================================
-- Utility: convert numeric value
-- ============================================================

local function to_number(value)

    value = empty_to_nil(value)

    if value == nil then
        return nil
    end

    return tonumber(value)

end


-- ============================================================
-- Timestamp normalization
--
-- Bitbucket:
--
--   2026-08-25 16:27:08,904
--
-- Audit:
--
--   epoch milliseconds
--
-- Output:
--
--   @timestamp
--
--   2026-08-25T16:27:08.904Z
--
-- NOTE:
-- The Bitbucket text timestamp has no timezone.
-- os.time() uses the timezone configured for Fluent Bit.
--
-- If Bitbucket is writing local time, Fluent Bit should use
-- the same TZ as the Bitbucket node.
-- ============================================================

local function normalize_timestamp(value)

    if value == nil then
        return nil
    end

    value = tostring(value)


    -- --------------------------------------------------------
    -- Audit timestamp:
    -- epoch milliseconds
    -- --------------------------------------------------------

    if value:match("^%d%d%d%d%d%d%d%d%d%d%d%d%d$") then

        local epoch_ms = tonumber(value)

        if epoch_ms == nil then
            return nil
        end

        local seconds =
            math.floor(epoch_ms / 1000)

        local milliseconds =
            epoch_ms % 1000

        local t =
            os.date("!*t", seconds)

        if t == nil then
            return nil
        end

        return string.format(
            "%04d-%02d-%02dT%02d:%02d:%02d.%03dZ",
            t.year,
            t.month,
            t.day,
            t.hour,
            t.min,
            t.sec,
            milliseconds
        )

    end


    -- --------------------------------------------------------
    -- Bitbucket timestamp:
    --
    -- YYYY-MM-DD HH:mm:ss,SSS
    -- --------------------------------------------------------

    local year,
          month,
          day,
          hour,
          minute,
          second,
          milliseconds =
        value:match(
            "^(%d%d%d%d)%-(%d%d)%-(%d%d) (%d%d):(%d%d):(%d%d),(%d%d%d)$"
        )


    if year == nil then
        return nil
    end


    local epoch =
        os.time({
            year  = tonumber(year),
            month = tonumber(month),
            day   = tonumber(day),
            hour  = tonumber(hour),
            min   = tonumber(minute),
            sec   = tonumber(second)
        })


    if epoch == nil then
        return nil
    end


    local t =
        os.date("!*t", epoch)


    if t == nil then
        return nil
    end


    return string.format(
        "%04d-%02d-%02dT%02d:%02d:%02d.%03dZ",
        t.year,
        t.month,
        t.day,
        t.hour,
        t.min,
        t.sec,
        tonumber(milliseconds)
    )

end


-- ============================================================
-- Request ID decomposition
--
-- Bitbucket access:
--
--   i@NODExMINUTExREQUESTxCONCURRENT
--   o@NODExMINUTExREQUESTxCONCURRENT
--
--   i*NODExMINUTExREQUESTxCONCURRENT
--   o*NODExMINUTExREQUESTxCONCURRENT
--
-- Audit:
--
--   @NODExMINUTExREQUESTxCONCURRENT
--   *NODExMINUTExREQUESTxCONCURRENT
--
--
-- Example:
--
--   o*8I1NZx987x78511x0
--
-- Generates:
--
--   request_id_original
--   request_id_direction
--   request_id_cluster_marker
--   request_id_clustered
--   request_id_node_id
--   request_id_minute_of_day
--   request_id_hour
--   request_id_minute
--   request_id_request_number
--   request_id_concurrent
--   request_id_correlation_id
--
-- The original request_id is NOT changed.
-- ============================================================

local function parse_request_id(
    record,
    field_name,
    prefix
)

    local value =
        record[field_name]


    if value == nil then
        return
    end


    value =
        tostring(value)


    if value == "" or value == "-" then
        return
    end


    -- --------------------------------------------------------
    -- Preserve original ID
    -- --------------------------------------------------------

    record[prefix .. "_original"] =
        value


    -- --------------------------------------------------------
    -- Access-log format
    --
    -- i@...
    -- o@...
    -- i*...
    -- o*...
    -- --------------------------------------------------------

    local direction,
          cluster_marker,
          node_id,
          minute_of_day,
          request_number,
          concurrent =
        value:match(
            "^([io])([*@])([^x]+)x(%d+)x(%d+)x(%d+)$"
        )


    -- --------------------------------------------------------
    -- Audit format
    --
    -- @...
    -- *...
    -- --------------------------------------------------------

    if node_id == nil then

        cluster_marker,
        node_id,
        minute_of_day,
        request_number,
        concurrent =
            value:match(
                "^([*@])([^x]+)x(%d+)x(%d+)x(%d+)$"
            )

    end


    -- --------------------------------------------------------
    -- Invalid / unexpected request ID.
    -- Keep original but don't create partial fields.
    -- --------------------------------------------------------

    if node_id == nil then
        return
    end


    -- --------------------------------------------------------
    -- Direction
    -- --------------------------------------------------------

    if direction == "i" then

        record[prefix .. "_direction"] =
            "input"

    elseif direction == "o" then

        record[prefix .. "_direction"] =
            "output"

    end


    -- --------------------------------------------------------
    -- @ or *
    -- --------------------------------------------------------

    record[prefix .. "_cluster_marker"] =
        cluster_marker


    record[prefix .. "_clustered"] =
        cluster_marker == "*"


    -- --------------------------------------------------------
    -- Node
    -- --------------------------------------------------------

    record[prefix .. "_node_id"] =
        node_id


    -- --------------------------------------------------------
    -- Minute of day
    -- --------------------------------------------------------

    local minute_value =
        tonumber(minute_of_day)


    if minute_value ~= nil then

        record[prefix .. "_minute_of_day"] =
            minute_value


        record[prefix .. "_hour"] =
            math.floor(minute_value / 60)


        record[prefix .. "_minute"] =
            minute_value % 60

    end


    -- --------------------------------------------------------
    -- Request number
    -- --------------------------------------------------------

    record[prefix .. "_request_number"] =
        tonumber(request_number)


    -- --------------------------------------------------------
    -- Concurrent request count
    -- --------------------------------------------------------

    record[prefix .. "_concurrent"] =
        tonumber(concurrent)


    -- --------------------------------------------------------
    -- Correlation ID
    --
    -- Removes:
    --
    --   i@
    --   o@
    --   i*
    --   o*
    --
    -- OR for audit:
    --
    --   @
    --   *
    --
    -- The original ID remains untouched.
    -- --------------------------------------------------------

    if direction ~= nil then

        record[prefix .. "_correlation_id"] =
            string.sub(value, 3)

    else

        record[prefix .. "_correlation_id"] =
            string.sub(value, 2)

    end

end


-- ============================================================
-- Client IP normalization
--
-- Example:
--
--   10.156.89.176,10.118.127.220
--
-- Generates:
--
--   client_ip_original
--   client_ip_forwarded
--   client_ip_remote
--
-- The original client_ip is preserved.
-- ============================================================

local function parse_client_ip(record)

    local value =
        record["client_ip"]


    if value == nil then
        return
    end


    value =
        tostring(value)


    record["client_ip_original"] =
        value


    -- --------------------------------------------------------
    -- Multiple IPs
    -- --------------------------------------------------------

    if value:find(",", 1, true) then

        local first,
              remainder =
            value:match(
                "^%s*([^,]+)%s*,%s*(.*)$"
            )


        if first ~= nil then

            record["client_ip_forwarded"] =
                first

            record["client_ip_remote"] =
                remainder

        end

    else

        record["client_ip_remote"] =
            value

    end

end


-- ============================================================
-- Normalize Bitbucket access-log numeric fields
-- ============================================================

local function normalize_access_fields(record)

    local value


    -- --------------------------------------------------------
    -- HTTP status / SSH exit code
    -- --------------------------------------------------------

    if record["status"] ~= nil then

        value =
            to_number(record["status"])

        if value ~= nil then
            record["status"] = value
        end

    end


    -- --------------------------------------------------------
    -- Bytes read
    -- --------------------------------------------------------

    if record["bytes_read"] ~= nil then

        value =
            to_number(record["bytes_read"])

        if value ~= nil then
            record["bytes_read"] = value
        end

    end


    -- --------------------------------------------------------
    -- Bytes written
    -- --------------------------------------------------------

    if record["bytes_written"] ~= nil then

        value =
            to_number(record["bytes_written"])

        if value ~= nil then
            record["bytes_written"] = value
        end

    end


    -- --------------------------------------------------------
    -- Duration
    -- --------------------------------------------------------

    if record["duration_ms"] ~= nil then

        value =
            to_number(record["duration_ms"])

        if value ~= nil then
            record["duration_ms"] = value
        end

    end

end


-- ============================================================
-- Extract request ID from Bitbucket application-log message
--
-- Some application-log messages can contain a request ID.
--
-- Example:
--
--   ... request i@8I1NZx987x78511x0 ...
--
-- If found, we create:
--
--   request_id
--   request_id_original
--   request_id_direction
--   ...
--
-- ============================================================

local function extract_application_request_id(record)

    local message =
        record["message"]


    if message == nil then
        return
    end


    message =
        tostring(message)


    local request_id =
        message:match(
            "[io][*@][A-Za-z0-9]+x%d+x%d+x%d+"
        )


    if request_id == nil then
        return
    end


    record["request_id"] =
        request_id


    parse_request_id(
        record,
        "request_id",
        "request_id"
    )

end


-- ============================================================
-- MAIN FLUENT BIT CALLBACK
-- ============================================================

function normalize(
    tag,
    timestamp,
    record
)

    -- ========================================================
    -- Determine log type
    -- ========================================================

    local is_access =
        tag == "bitbucket.access"


    local is_application =
        tag == "bitbucket.application"


    local is_audit =
        tag == "bitbucket.audit"


    -- ========================================================
    -- Source marker
    -- ========================================================

    record["log_source"] =
        "bitbucket-data-center"


    -- ========================================================
    -- Timestamp
    --
    -- Access/application:
    --
    --   timestamp
    --
    -- Audit:
    --
    --   timestamp_ms
    -- ========================================================

    if record["timestamp"] ~= nil then

        local normalized =
            normalize_timestamp(
                record["timestamp"]
            )


        if normalized ~= nil then

            record["@timestamp"] =
                normalized

        end

    elseif record["timestamp_ms"] ~= nil then

        local normalized =
            normalize_timestamp(
                record["timestamp_ms"]
            )


        if normalized ~= nil then

            record["@timestamp"] =
                normalized

        end

    end


    -- ========================================================
    -- BITBUCKET ACCESS
    -- ========================================================

    if is_access then

        -- ----------------------------------------------------
        -- Client IP
        -- ----------------------------------------------------

        parse_client_ip(
            record
        )


        -- ----------------------------------------------------
        -- Request ID
        --
        -- This handles:
        --
        --   i@...
        --   o@...
        --   i*...
        --   o*...
        -- ----------------------------------------------------

        parse_request_id(
            record,
            "request_id",
            "request_id"
        )


        -- ----------------------------------------------------
        -- Numeric fields
        --
        -- Works for both HTTP and SSH.
        -- ----------------------------------------------------

        normalize_access_fields(
            record
        )

    end


    -- ========================================================
    -- BITBUCKET APPLICATION
    -- ========================================================

    if is_application then

        -- ----------------------------------------------------
        -- Multiline processing has already happened before
        -- this Lua filter.
        --
        -- The complete Java stack trace is therefore inside
        -- record["message"].
        -- ----------------------------------------------------

        extract_application_request_id(
            record
        )

    end


    -- ========================================================
    -- BITBUCKET AUDIT
    -- ========================================================

    if is_audit then

        -- ----------------------------------------------------
        -- Client IP
        -- ----------------------------------------------------

        parse_client_ip(
            record
        )


        -- ----------------------------------------------------
        -- Audit request ID:
        --
        -- @...
        -- *...
        -- ----------------------------------------------------

        parse_request_id(
            record,
            "request_id",
            "request_id"
        )


        -- ----------------------------------------------------
        -- Keep original epoch milliseconds as numeric value.
        -- ----------------------------------------------------

        if record["timestamp_ms"] ~= nil then

            record["timestamp_ms"] =
                tonumber(
                    record["timestamp_ms"]
                )

        end

    end


    -- ========================================================
    -- Remove parser timestamp after @timestamp is created.
    --
    -- Audit timestamp_ms is deliberately retained.
    -- ========================================================

    if not is_audit then

        record["timestamp"] =
            nil

    end


    -- ========================================================
    -- Return
    -- ========================================================

    return 1, timestamp, record

end
