#!/bin/bash
# 编译菜单栏 App。只需要 Xcode 命令行工具（swiftc），不用装完整的 Xcode。
#
#   ./build.sh          编译并打包成 WorkTime.app
#   ./build.sh --run    编译完顺便启动
#
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DIR="$(cd "$HERE/.." && pwd)"                 # worktime/
APP="$HERE/WorkTime.app"
BUILD="$HERE/.build"                          # sed 替换后的源码，编译完就是垃圾

PYTHON="$(command -v python3 || true)"
if [ -z "$PYTHON" ]; then
  echo "找不到 python3，先装上再来。" >&2
  exit 1
fi

if ! command -v swiftc >/dev/null 2>&1; then
  echo "找不到 swiftc。装一下命令行工具：xcode-select --install" >&2
  exit 1
fi

echo "python3 : $PYTHON"
echo "工时目录 : $DIR"
echo "输出     : $APP"

# 把真实路径写进源码，替换占位符。三个 .swift 都过一遍——
# main.swift(入口) / WorkTime.swift(菜单栏界面) / Nudge.swift(解锁提醒)。
rm -rf "$APP" "$BUILD"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources" "$BUILD"
for f in "$HERE"/*.swift; do
  sed -e "s|__PYTHON__|$PYTHON|g" -e "s|__WORKTIME_DIR__|$DIR|g" "$f" > "$BUILD/$(basename "$f")"
done

echo "编译中…"
# 多文件编译时顶层可执行代码必须在 main.swift 里，所以入口单独一个文件
swiftc -O -o "$APP/Contents/MacOS/WorkTime" "$BUILD"/*.swift -framework Cocoa
cp "$HERE/Info.plist" "$APP/Contents/Info.plist"

# ad-hoc 签名。没有苹果开发者证书，只能用这个，首次打开需要手动放行一次。
codesign --force --sign - "$APP" >/dev/null 2>&1 || echo "（签名跳过，通常也能跑）"

# 让系统重新认识这个 App
/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister \
  -f "$APP" >/dev/null 2>&1 || true

echo "✓ 编译完成：$APP"

if [ "${1:-}" = "--run" ]; then
  echo "启动…"
  open "$APP"
fi
