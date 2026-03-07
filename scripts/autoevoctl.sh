#!/bin/bash
# RoleMesh Infinite Auto-Evolution Control
# usage: rolemesh_autoevoctl.sh on|off|status|restart

set -e
PID_FILE="/tmp/rolemesh-autoevo-worker.pid"
LOG_FILE="/tmp/rolemesh-autoevo.log"
CMD="python3 /Users/rocky/ai-comms/rolemesh_autoevo_worker.py --daemon"

is_running() {
  [[ -f "$PID_FILE" ]] && ps -p "$(cat "$PID_FILE")" >/dev/null 2>&1
}

case "${1:-status}" in
  on|start)
    if is_running; then
      echo "already-on pid=$(cat "$PID_FILE")"
      exit 0
    fi
    nohup $CMD >> "$LOG_FILE" 2>&1 &
    sleep 1
    if is_running; then
      echo "on pid=$(cat "$PID_FILE")"
    else
      echo "failed-to-start"
      exit 1
    fi
    ;;

  off|stop)
    if is_running; then
      kill "$(cat "$PID_FILE")" || true
      sleep 1
      rm -f "$PID_FILE"
      echo "off"
    else
      rm -f "$PID_FILE"
      echo "already-off"
    fi
    ;;

  restart)
    "$0" off
    "$0" on
    ;;

  status)
    if is_running; then
      echo "on pid=$(cat "$PID_FILE")"
    else
      echo "off"
    fi
    echo "log=$LOG_FILE"
    ;;

  *)
    echo "usage: $0 on|off|status|restart"
    exit 2
    ;;
esac
