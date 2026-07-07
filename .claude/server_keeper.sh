#!/bin/bash
# 课后素材平台守护进程：每10秒检查，挂了自动重启
PORT=5888
DIR="/Users/meowmeow/Claude code-课后素材"
LOG="/tmp/server_keeper.log"

while true; do
  if ! lsof -i :$PORT -sTCP:LISTEN > /dev/null 2>&1; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') Server down, restarting..." >> "$LOG"
    cd "$DIR" && python3 server.py >> /tmp/server.log 2>&1 &
    sleep 4
  fi
  sleep 10
done
