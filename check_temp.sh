#!/usr/bin/env bash
#
# check_temp.sh - Nagios check for the standby centre server room temperature.
#
# It reads the temperature logger file (one row per half hour, one column per
# server after the timestamp), works out the "room number" the way the original
# check does - drop the single hottest server reading, then average the rest -
# and decides OK / WARNING / CRITICAL. HDD means hard drive, the disk whose
# temperature each sensor reports; the hottest is dropped because one busy server
# can run hot on its own and would unfairly lift the average.
#
# Unlike the original, it does not judge on a single instant. It replays the last
# day of readings and applies two calming rules, so a room that merely wobbles
# around the limit does not raise a fresh alarm every time:
#   - hysteresis: warn above WARN_SET, but only clear once the number drops below
#     WARN_SET - CLEAR_GAP;
#   - persistence: require PERSIST_N readings in a row above a limit before it
#     alarms.
# Both settings were chosen from three years of data (see notebook.html).
#
# Usage:
#   ./check_temp.sh                 # download from DATA_URL, then check
#   ./check_temp.sh path/to/file.csv   # check a local file (no download); for tests
#
# Exit codes follow the Nagios convention: 0 OK, 1 WARNING, 2 CRITICAL, 3 UNKNOWN.

set -euo pipefail

# ===========================================================================
# Configuration - the only part meant to be edited
# ===========================================================================

# Where the data comes from. Set DATA_URL to the monitoring host's published
# logger file. For a manual test, pass a local CSV as the first argument instead.
DATA_URL="${DATA_URL:-}"                            # e.g. http://host/path/file.csv
DATA_FILE="${1:-/tmp/room_temperature_cache.csv}"   # local file to read (argument wins)

# Alarm limits, in degrees Celsius.
WARN_SET=26            # warn when the room number goes above this
CRIT_SET=28            # critical when the room number goes above this

# Calming settings (justified in the notebook).
CLEAR_GAP=1            # only clear once the number drops this far below the limit
PERSIST_N=2            # readings in a row above a limit before it alarms

# How the room number is formed, and how far back to replay.
DROP_HIGHEST=1         # how many of the hottest sensors to set aside before averaging
LOOKBACK=48            # rows to replay (48 half-hours = one day) for the calming rules

# Nagios exit codes (do not change).
readonly OK_CODE=0 WARNING_CODE=1 CRITICAL_CODE=2 UNKNOWN_CODE=3

# ===========================================================================
# Helpers
# ===========================================================================

# Print an UNKNOWN result and stop. Used whenever the data cannot be trusted, so a
# real problem is never silently reported as OK.
report_unknown() {
    echo "UNKNOWN - $1"
    exit "$UNKNOWN_CODE"
}

# Work out the room number for one CSV line: drop the timestamp, keep the numeric
# sensor readings, drop the single hottest, and average the rest. Prints the
# average to one decimal, or "NA" if the line has too few numeric readings.
room_number_for_line() {
    echo "$1" | awk -F',' -v drop="$DROP_HIGHEST" '
        {
            gsub(/\r/, "")                       # tolerate Windows line endings
            count = 0
            for (i = 2; i <= NF; i++) {
                if ($i ~ /^[ ]*-?[0-9]+(\.[0-9]+)?[ ]*$/) values[count++] = $i + 0
            }
            if (count - drop < 1) { print "NA"; exit }
            for (i = 1; i < count; i++) {         # simple ascending sort
                key = values[i]; j = i - 1
                while (j >= 0 && values[j] > key) { values[j + 1] = values[j]; j-- }
                values[j + 1] = key
            }
            kept = count - drop                   # everything except the hottest
            sum = 0
            for (i = 0; i < kept; i++) sum += values[i]
            printf "%.1f", sum / kept
        }'
}

# Read the timestamp (first field) from one CSV line.
timestamp_for_line() {
    echo "$1" | awk -F',' '{ gsub(/\r/, ""); print $1 }'
}

# Decimal-aware comparisons (awk handles the fractional room numbers, so there is
# no dependency on bc). Each returns success when the relation holds.
greater_than() { awk -v a="$1" -v b="$2" 'BEGIN { exit !(a > b) }'; }
less_than()    { awk -v a="$1" -v b="$2" 'BEGIN { exit !(a < b) }'; }

# ===========================================================================
# Get the data
# ===========================================================================

# Download only when no local file was passed and a URL is configured.
if [ -z "${1:-}" ] && [ -n "$DATA_URL" ]; then
    wget -q "$DATA_URL" -O "$DATA_FILE" || report_unknown "could not download the data file"
fi

if [ ! -s "$DATA_FILE" ]; then
    report_unknown "data file is missing or empty"
fi

# ===========================================================================
# Replay the recent readings and apply the calming rules
# ===========================================================================

# The clear lines sit one gap below each limit.
warn_clear=$(awk -v s="$WARN_SET" -v g="$CLEAR_GAP" 'BEGIN { printf "%.4f", s - g }')
crit_clear=$(awk -v s="$CRIT_SET" -v g="$CLEAR_GAP" 'BEGIN { printf "%.4f", s - g }')

warn_state=0; warn_run=0
crit_state=0; crit_run=0

# Replay the last LOOKBACK rows (tail keeps them in time order, oldest first).
while IFS= read -r line; do
    if [ -z "$line" ]; then continue; fi
    number=$(room_number_for_line "$line")
    if [ "$number" = "NA" ]; then continue; fi   # skip a row with too few readings

    # Warning level: count a streak above the limit, then latch on/off (hysteresis).
    if greater_than "$number" "$WARN_SET"; then warn_run=$((warn_run + 1)); else warn_run=0; fi
    if [ "$warn_state" -eq 0 ] && [ "$warn_run" -ge "$PERSIST_N" ]; then
        warn_state=1
    elif [ "$warn_state" -eq 1 ] && less_than "$number" "$warn_clear"; then
        warn_state=0
    fi

    # Critical level: exactly the same rules, one step up.
    if greater_than "$number" "$CRIT_SET"; then crit_run=$((crit_run + 1)); else crit_run=0; fi
    if [ "$crit_state" -eq 0 ] && [ "$crit_run" -ge "$PERSIST_N" ]; then
        crit_state=1
    elif [ "$crit_state" -eq 1 ] && less_than "$number" "$crit_clear"; then
        crit_state=0
    fi
done <<< "$(tail -n "$LOOKBACK" "$DATA_FILE")"

# The current reading is the latest non-empty row. If it cannot be read (too few
# sensors reporting), that is reported honestly as UNKNOWN, never as OK.
latest_line=$(awk 'NF { line = $0 } END { print line }' "$DATA_FILE")
newest_number=$(room_number_for_line "$latest_line")
newest_time=$(timestamp_for_line "$latest_line")
if [ "$newest_number" = "NA" ]; then
    report_unknown "no readable temperature in the latest data"
fi

# ===========================================================================
# Report the result
# ===========================================================================

if [ "$crit_state" -eq 1 ]; then
    echo "CRITICAL - $newest_time: room temperature too high (${newest_number} C)"
    exit "$CRITICAL_CODE"
elif [ "$warn_state" -eq 1 ]; then
    echo "WARNING - $newest_time: room temperature high (${newest_number} C)"
    exit "$WARNING_CODE"
else
    echo "OK - $newest_time: room temperature normal (${newest_number} C)"
    exit "$OK_CODE"
fi
