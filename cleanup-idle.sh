#!/bin/bash
# Manual cleanup script - shows and optionally kills all idle processes

echo "========================================="
echo "  IDLE PROCESS CLEANUP TOOL"
echo "========================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

IDLE_TIMEOUT=3600  # 1 hour

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

# Function to check for active connections
has_active_connections() {
    local pid=$1
    local connections=$(ss -tnp 2>/dev/null | grep "pid=$pid," | grep ESTAB | wc -l)
    [ "$connections" -gt 0 ]
}

# Function to format idle time
format_idle() {
    local seconds=$1
    if [ $seconds -ge 3600 ]; then
        printf "%dh %dm" $((seconds / 3600)) $(((seconds % 3600) / 60))
    elif [ $seconds -ge 60 ]; then
        printf "%dm" $((seconds / 60))
    else
        printf "%ds" $seconds
    fi
}

# Track processes to potentially kill
declare -a PIDS_TO_KILL=()
declare -a PID_LABELS=()

# ========== CHROME/PUPPETEER ==========
echo -e "${BLUE}[1] Checking Chrome/Puppeteer processes...${NC}"
chrome_procs=$(pgrep -f "puppeteer_dev_chrome_profile" 2>/dev/null)
if [ -n "$chrome_procs" ]; then
    echo "Found Chrome/Puppeteer processes:"
    for pid in $chrome_procs; do
        idle=$(get_idle_time $pid)
        idle_str=$(format_idle $idle)
        cmd=$(ps -p $pid -o cmd= 2>/dev/null | cut -c1-70)
        if [ $idle -gt $IDLE_TIMEOUT ]; then
            echo -e "  ${RED}●${NC} PID $pid - Idle: ${idle_str} - $cmd"
            PIDS_TO_KILL+=($pid)
            PID_LABELS+=("Chrome (idle $idle_str)")
        else
            echo -e "  ${GREEN}○${NC} PID $pid - Idle: ${idle_str} - $cmd"
        fi
    done
else
    echo "  No Chrome/Puppeteer processes found"
fi
echo ""

# ========== CLAUDE SESSIONS ==========
echo -e "${BLUE}[2] Checking Claude Code sessions...${NC}"
claude_procs=$(pgrep -x "claude" 2>/dev/null)
if [ -n "$claude_procs" ]; then
    echo "Found Claude Code sessions:"
    for pid in $claude_procs; do
        idle=$(get_idle_time $pid)
        idle_str=$(format_idle $idle)
        tty=$(ps -p $pid -o tty= 2>/dev/null | tr -d ' ')
        cmd=$(ps -p $pid -o cmd= 2>/dev/null | cut -c1-70)
        if [ $idle -gt $IDLE_TIMEOUT ]; then
            echo -e "  ${RED}●${NC} PID $pid - Idle: ${idle_str} - TTY: $tty"
            PIDS_TO_KILL+=($pid)
            PID_LABELS+=("Claude session on $tty (idle $idle_str)")
        else
            echo -e "  ${GREEN}○${NC} PID $pid - Idle: ${idle_str} - TTY: $tty"
        fi
    done
else
    echo "  No Claude Code sessions found"
fi
echo ""

# ========== NODE.JS SERVERS ==========
echo -e "${BLUE}[3] Checking Node.js servers...${NC}"
node_patterns="node.*next-dev|node.*vite|node.*webpack|node.*serve|node.*start|node.*dev"
node_patterns="$node_patterns|npm.*dev|npm.*start|npm.*run"
node_procs=$(pgrep -f "$node_patterns" 2>/dev/null)
if [ -n "$node_procs" ]; then
    echo "Found Node.js servers:"
    for pid in $node_procs; do
        idle=$(get_idle_time $pid)
        idle_str=$(format_idle $idle)
        cmd=$(ps -p $pid -o cmd= 2>/dev/null | cut -c1-70)
        if has_active_connections $pid; then
            echo -e "  ${GREEN}○${NC} PID $pid - Active connections - $cmd"
        elif [ $idle -gt $IDLE_TIMEOUT ]; then
            echo -e "  ${RED}●${NC} PID $pid - Idle: ${idle_str} - No connections"
            PIDS_TO_KILL+=($pid)
            PID_LABELS+=("Node.js server (idle $idle_str, no connections)")
        else
            echo -e "  ${YELLOW}○${NC} PID $pid - Idle: ${idle_str} - $cmd"
        fi
    done
else
    echo "  No Node.js servers found"
fi
echo ""

# ========== PYTHON SERVERS ==========
echo -e "${BLUE}[4] Checking Python servers...${NC}"
python_patterns="python.*manage.py|python.*app.py|python.*main.py|python.*server.py|uvicorn|gunicorn"
python_patterns="$python_patterns|daphne|hypercorn|streamlit|gradio|jupyter"
python_procs=$(pgrep -f "$python_patterns" 2>/dev/null)
if [ -n "$python_procs" ]; then
    echo "Found Python servers:"
    for pid in $python_procs; do
        idle=$(get_idle_time $pid)
        idle_str=$(format_idle $idle)
        cmd=$(ps -p $pid -o cmd= 2>/dev/null | cut -c1-70)
        if has_active_connections $pid; then
            echo -e "  ${GREEN}○${NC} PID $pid - Active connections - $cmd"
        elif [ $idle -gt $IDLE_TIMEOUT ]; then
            echo -e "  ${RED}●${NC} PID $pid - Idle: ${idle_str} - No connections"
            PIDS_TO_KILL+=($pid)
            PID_LABELS+=("Python server (idle $idle_str, no connections)")
        else
            echo -e "  ${YELLOW}○${NC} PID $pid - Idle: ${idle_str} - $cmd"
        fi
    done
else
    echo "  No Python servers found"
fi
echo ""

# ========== PRESERVED PROCESSES ==========
echo -e "${BLUE}[5] Protected (will NOT be killed):${NC}"
preserved=$(pgrep -f "continuous-scraper.js|redis-server" 2>/dev/null)
if [ -n "$preserved" ]; then
    for pid in $preserved; do
        cmd=$(ps -p $pid -o cmd= 2>/dev/null | cut -c1-70)
        echo -e "  ${GREEN}✓${NC} PID $pid - $cmd"
    done
else
    echo "  No protected processes found"
fi
echo ""

# ========== SUMMARY ==========
if [ ${#PIDS_TO_KILL[@]} -eq 0 ]; then
    echo -e "${GREEN}✓ No idle processes to clean!${NC}"
else
    echo -e "${YELLOW}=========================================${NC}"
    echo -e "${RED}Found ${#PIDS_TO_KILL[@]} idle process(es):${NC}"
    echo ""
    for i in "${!PIDS_TO_KILL[@]}"; do
        echo "  [$((i+1))] PID ${PIDS_TO_KILL[$i]} - ${PID_LABELS[$i]}"
    done
    echo ""
    read -p "Kill these processes? (y/N) " -n 1 -r
    echo
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        for pid in "${PIDS_TO_KILL[@]}"; do
            kill $pid 2>/dev/null
            if [ $? -eq 0 ]; then
                echo -e "${GREEN}✓${NC} Killed PID $pid"
            else
                echo -e "${RED}✗${NC} Failed to kill PID $pid"
            fi
        done
        echo ""
        echo -e "${GREEN}Cleanup completed!${NC}"
    else
        echo -e "${YELLOW}Cancelled.${NC}"
    fi
fi
