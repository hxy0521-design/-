#!/bin/bash
# 把工时摆件装到 Übersicht。
#
#   ./install.sh        装（或覆盖更新）
#   ./install.sh -f     干净重装（先删掉再装）
#   ./install.sh -u     卸载
#
# 前提：Übersicht 已装到 /Applications。装完在 Übersicht 菜单里点
# 「Edit Widgets」可以把摆件拖到想要的位置。
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DIR="$(cd "$HERE/.." && pwd)"          # worktime/
WIDGETS="$HOME/Library/Application Support/Übersicht/widgets"
DEST="$WIDGETS/worktime.widget"

if [ "${1:-}" = "-u" ] || [ "${1:-}" = "--uninstall" ]; then
    rm -rf "$DEST" && echo "已移除 $DEST"
    echo "（Übersicht 里过一两秒就消失了）"
    exit 0
fi

# 更新时**不要**先删掉再建。删了再建，Übersicht 看到的是「摆件没了 → 又来了」，
# 会走销毁 + 新建实例这条路，有几率卡在不干净的状态里——表现就是摆件每秒闪一下。
# 原地覆盖只是改文件，Übersicht 走 api.update()，干净得多。
FORCE=0
if [ "${1:-}" = "-f" ] || [ "${1:-}" = "--force" ]; then FORCE=1; fi

if [ ! -d "/Applications/Übersicht.app" ] && [ ! -d "/Applications/Uebersicht.app" ]; then
    echo "没找到 Übersicht。先把它拖进 /Applications 再来。" >&2
    exit 1
fi

PYTHON="$(command -v python3 || true)"
if [ -z "$PYTHON" ]; then
    echo "找不到 python3。" >&2
    exit 1
fi

mkdir -p "$WIDGETS"
if [ -d "$DEST" ] && [ "$FORCE" -eq 0 ]; then
    echo "· 摆件已存在，原地更新（不销毁重建实例）"
else
    rm -rf "$DEST"
    mkdir -p "$DEST"
fi

sed -e "s|__PYTHON__|$PYTHON|g" \
    -e "s|__WORKTIME_DIR__|$DIR|g" \
    "$HERE/worktime.widget/index.jsx" > "$DEST/index.jsx"

echo "✓ 摆件已装到 $DEST"
echo "  python3  : $PYTHON"
echo "  工时目录  : $DIR"
echo
echo "位置：装上后按住卡片直接拖，松手自动记住。"
echo "     （初始位置默认右上角，写在 index.jsx 的 className 里）"
echo
echo "⚠️  记得打开 Übersicht 的「Enable interaction」——"
echo "    菜单栏 Übersicht 图标 → Preferences… → Enable interaction"
echo "    不开的话桌面层点击穿透，按钮和拖动都点不到。"
