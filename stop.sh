#!/bin/bash
# Stop the Haven Builders ERP server
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

if [ -f .server.pid ]; then
    PID=$(cat .server.pid)
    if kill $PID 2>/dev/null; then
        echo "✅ Server stopped (PID $PID)"
    else
        echo "Server was not running."
    fi
    rm -f .server.pid
else
    echo "No running server found. Trying to kill by port..."
    PID=$(lsof -ti:5050 2>/dev/null)
    if [ -n "$PID" ]; then
        kill $PID
        echo "✅ Server stopped (PID $PID)"
    else
        echo "No process found on port 5050."
    fi
fi
