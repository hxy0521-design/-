// 工时记录 · 菜单栏常驻 · 入口
//
// swiftc 一次编译多个文件时，顶层可执行代码只允许出现在名为 main.swift 的
// 文件里，所以那四行单独放这儿。界面在 WorkTime.swift，提醒在 Nudge.swift。

import Cocoa

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.run()
