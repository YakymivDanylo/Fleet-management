#!/bin/sh
# Lab 8: screenshot of the Grafana dashboard with headless Chrome.
#   monitoring/screenshot.sh <out.png> <from> <to> [run]   (from/to: epoch ms or now-1h / now)
CHROME="${CHROME:-/c/Program Files/Google/Chrome/Application/chrome.exe}"
"$CHROME" --headless=new --disable-gpu --hide-scrollbars --window-size=1700,2650 \
  --virtual-time-budget=20000 --screenshot="$(cygpath -aw "$1")" \
  "http://localhost:3000/d/lab8-soak/lab-8-soak-test?kiosk&from=$2&to=$3&var-run=${4:-soak}" 2>/dev/null
