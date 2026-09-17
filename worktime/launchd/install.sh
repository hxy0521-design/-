#!/bin/bash
# 装开机自启（或卸载）。
#
#   ./install.sh     装上并立刻启动，之后每次登录自动跑
#   ./install.sh -u  卸载，并停掉正在跑的进程
#
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="$HOME/Library/LaunchAgents"
U="$(id -u)"
LABELS=("com.zhuguangpi.worktime" "com.zhuguangpi.worktime.menubar")

if [ "${1:-}" = "-u" ] || [ "${1:-}" = "--uninstall" ]; then
    for L in "${LABELS[@]}"; do
        launchctl bootout "gui/$U/$L" 2>/dev/null && echo "已停止 $L" || true
        rm -f "$DEST/$L.plist" && echo "已移除 $DEST/$L.plist"
    done
    echo "✓ 卸载完成（数据库和代码都还在，没删）"
    exit 0
fi

mkdir -p "$DEST"
for L in "${LABELS[@]}"; do
    cp "$HERE/$L.plist" "$DEST/$L.plist"
    # 先停掉旧的，再装新的，避免出现两个实例
    launchctl bootout "gui/$U/$L" 2>/dev/null || true
    launchctl bootstrap "gui/$U" "$DEST/$L.plist"
    echo "✓ 已装载 $L"
done

echo
echo "服务     : http://127.0.0.1:5899"
echo "日志     : /tmp/worktime-server.log  /tmp/worktime-server.err"
echo "菜单栏日志 : /tmp/worktime-menubar.log"
echo
echo "卸载：$0 -u"
