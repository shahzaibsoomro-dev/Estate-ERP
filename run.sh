#!/bin/bash
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

echo ""
echo "  Haven Builders ERP — Starting Server"
echo ""

PYCMD=""
if command -v python3 &>/dev/null; then PYCMD="python3"
elif command -v python &>/dev/null; then PYCMD="python"
else echo "ERROR: Python not installed."; exit 1; fi

echo "  Installing dependencies..."
$PYCMD -m pip install -r requirements.txt --quiet --break-system-packages 2>/dev/null \
  || $PYCMD -m pip install -r requirements.txt --quiet

echo "  Starting FastAPI on http://localhost:5050 ..."
$PYCMD -m uvicorn backend.main:app --host 0.0.0.0 --port 5050 > server.log 2>&1 &
echo $! > .server.pid
sleep 3

URL="http://localhost:5050"
if [[ "$OSTYPE" == "darwin"* ]]; then open "$URL"
else xdg-open "$URL" 2>/dev/null || sensible-browser "$URL" 2>/dev/null; fi

echo "  Running. Stop with: kill \$(cat .server.pid)"
