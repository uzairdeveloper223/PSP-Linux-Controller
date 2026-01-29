#!/bin/bash
# PSP Controller Server Startup Script

set -e

echo "PSP Linux Controller Server"
echo "==========================="

# Check for xdotool
if ! command -v xdotool &> /dev/null; then
    echo ""
    echo "ERROR: xdotool is not installed!"
    echo "Install it with: sudo apt install xdotool"
    echo ""
    exit 1
fi

# Check for Python 3
if ! command -v python3 &> /dev/null; then
    echo ""
    echo "ERROR: Python 3 is not installed!"
    echo "Install it with: sudo apt install python3"
    echo ""
    exit 1
fi

# Get the directory of this script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Run the server
cd "$SCRIPT_DIR"
python3 psp_controller_server.py "$@"
