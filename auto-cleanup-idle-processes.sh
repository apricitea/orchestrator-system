#!/bin/bash
# Auto-cleanup script for idle processes
# Kills Chrome/Puppeteer and backend/frontend servers after > 1 hour idle
# Does NOT kill Claude sessions (too unreliable to detect active usage)
# Preserves: continuous-scraper.js, redis-server, monitor itself

IDLE_TIMEOUT=3600  # 1 hour in seconds
LOG_FILE="/home/ubuntu/cleanup-monitor.log"

# Function to log messages
log() {
    echo "$1" | tee -a "$LOG_FILE"
}

# Function to get process idle time in seconds
get_idle_time() {
    local pid=$1
    local stat_data=$(cat /proc/$pid/stat 2>/dev/null)
    if [ -z "$stat_data" ]; then
        echo 999999999
        return
    fi

    local current_jiffies=$(awk '{print $1}' /proc/uptime)
    current_jiffies=$(echo "$current_jiffies * 100" | bc | cut -d. -f1)

    local last_scheduled=$(echo $stat_data | awk '{print $14}')
    local idle_jiffies=$((current_jiffies - last_scheduled))
    local idle_seconds=$((idle_jiffies / 100))

    echo $idle_seconds
}

# Function to check if process should be preserved (never kill)
should_preserve() {
    local cmd=$1
    if echo "$cmd" | grep -q "continuous-scraper.js"; then
        return 0  # True, preserve
    fi
    if echo "$cmd" | grep -q "redis-server"; then
        return 0  # True, preserve
    fi
    if echo "$cmd" | grep -q "auto-cleanup-idle-processes"; then
        return 0  # True, preserve (don't kill self)
    fi
    if echo "$cmd" | grep -q "cleanup-monitor"; then
        return 0  # True, preserve
    fi
    return 1  # False, don't preserve
}

# Function to check if process has active network connections
has_active_connections() {
    local pid=$1

    # Check for established TCP connections
    local connections=$(ss -tnp | grep "pid=$pid," | grep ESTAB | wc -l)

    if [ "$connections" -gt 0 ]; then
        return 0  # Has active connections
    fi

    return 1  # No active connections
}

# Main cleanup loop
log "Starting auto-cleanup monitor - checking for idle processes every 10 minutes..."
log "Chrome/servers killed after $(($IDLE_TIMEOUT / 60))min idle. Claude sessions NOT monitored."
log "Preserved processes: continuous-scraper.js, redis-server, monitor itself"

while true; do
    timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    killed_count=0

    # ========== CHROME/PUPPETEER PROCESSES ==========
    for pid in $(pgrep -f "puppeteer_dev_chrome_profile" 2>/dev/null); do
        if [ -f "/proc/$pid/stat" ]; then
            cmd=$(cat /proc/$pid/cmdline 2>/dev/null | tr '\0' ' ')

            if should_preserve "$cmd"; then
                continue
            fi

            idle_time=$(get_idle_time $pid)

            if [ "$idle_time" -gt "$IDLE_TIMEOUT" ]; then
                log "[$timestamp] [CHROME] Killing PID $pid (idle ${idle_time}s): $(echo "$cmd" | cut -c1-80)..."
                kill $pid 2>/dev/null
                if [ $? -eq 0 ]; then
                    ((killed_count++))
                fi
            fi
        fi
    done

    # ========== CLAUDE CODE SESSIONS ==========
    # REMOVED: Too difficult to reliably detect active vs inactive Claude sessions
    # Users should manage Claude sessions manually
    # Only killing abandoned Chrome processes and idle backend servers

    # ========== NODE.JS BACKEND/FRONTEND SERVERS ==========
    # Look for common dev servers and backends
    server_patterns="node.*next-dev|node.*vite|node.*webpack|node.*serve|node.*start|node.*dev"
    server_patterns="$server_patterns|npm.*dev|npm.*start|npm.*run"
    server_patterns="$server_patterns|npx.*next|npx.*vite|npx.*create-"

    for pid in $(pgrep -f "$server_patterns" 2>/dev/null); do
        if [ -f "/proc/$pid/stat" ]; then
            cmd=$(cat /proc/$pid/cmdline 2>/dev/null | tr '\0' ' ')

            if should_preserve "$cmd"; then
                continue
            fi

            # Skip if has active network connections
            if has_active_connections $pid; then
                continue
            fi

            idle_time=$(get_idle_time $pid)

            if [ "$idle_time" -gt "$IDLE_TIMEOUT" ]; then
                log "[$timestamp] [NODE-SERVER] Killing idle server PID $pid (idle ${idle_time}s, no active connections): $(echo "$cmd" | cut -c1-80)..."
                kill $pid 2>/dev/null
                if [ $? -eq 0 ]; then
                    ((killed_count++))
                fi
            fi
        fi
    done

    # ========== PYTHON BACKEND/FRONTEND SERVERS ==========
    # Look for common Python servers
    python_patterns="python.*manage.py|python.*app.py|python.*main.py|python.*server.py"
    python_patterns="$python_patterns|uvicorn|gunicorn|daphne|hypercorn"
    python_patterns="$python_patterns|python.*flask|python.*django|python.*fastapi"
    python_patterns="$python_patterns|streamlit|gradio|jupyter"

    for pid in $(pgrep -f "$python_patterns" 2>/dev/null); do
        if [ -f "/proc/$pid/stat" ]; then
            cmd=$(cat /proc/$pid/cmdline 2>/dev/null | tr '\0' ' ')

            if should_preserve "$cmd"; then
                continue
            fi

            # Skip if has active network connections
            if has_active_connections $pid; then
                continue
            fi

            idle_time=$(get_idle_time $pid)

            if [ "$idle_time" -gt "$IDLE_TIMEOUT" ]; then
                log "[$timestamp] [PYTHON-SERVER] Killing idle server PID $pid (idle ${idle_time}s, no active connections): $(echo "$cmd" | cut -c1-80)..."
                kill $pid 2>/dev/null
                if [ $? -eq 0 ]; then
                    ((killed_count++))
                fi
            fi
        fi
    done

    # ========== NPM/ZAI-MCP-SERVER (already checking above, but add explicit) ==========
    for pid in $(pgrep -f "npm exec.*zai-mcp-server" 2>/dev/null); do
        if [ -f "/proc/$pid/stat" ]; then
            idle_time=$(get_idle_time $pid)

            if [ "$idle_time" -gt "$IDLE_TIMEOUT" ]; then
                cmd=$(cat /proc/$pid/cmdline 2>/dev/null | tr '\0' ' ')
                log "[$timestamp] [NPM] Killing idle npm exec PID $pid (idle ${idle_time}s): $(echo "$cmd" | cut -c1-80)..."
                kill $pid 2>/dev/null
                if [ $? -eq 0 ]; then
                    ((killed_count++))
                fi
            fi
        fi
    done

    if [ $killed_count -gt 0 ]; then
        log "[$timestamp] Cleanup completed: $killed_count idle process(es) killed."
    fi

    # Sleep for 10 minutes before next check
    sleep 600
done
