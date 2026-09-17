// 工时记录 · 菜单栏常驻
//
// 直接调 worktime.py 命令行，不依赖 5899 那个网页服务——
// 这样即使服务挂了，随手开始/暂停照样能用。
//
// 每 5 秒拉一次真实数据，中间在本地按秒累加，显示跳分钟不卡顿。
// 编译见同目录 build.sh（只需要 swiftc，不用装 Xcode）。

import Cocoa

// build.sh 编译时会把这两个占位符替换成真实路径
let kPythonPath = "__PYTHON__"
let kWorktimeDir = "__WORKTIME_DIR__"
let kScriptPath = kWorktimeDir + "/worktime.py"
let kServerURL = URL(string: "http://127.0.0.1:5899")!

// 色号跟 worktime_core.py 的 CATEGORIES 保持一致，网页/摆件/横幅三处一个色
let kCategories: [(key: String, label: String, color: String)] = [
    ("prep", "备课", "#38bdf8"),
    ("ops",  "运营", "#fb923c"),
    ("cls",  "上课", "#7c6ff7"),
]

let kPollSeconds: TimeInterval = 5

// ---------------------------------------------------------------- 数据

struct Snapshot {
    var ok = false
    var errorText: String?
    var weekHM = "0:00"
    var todayHM = "0:00"
    var weekLabel = ""
    var runningKey: String?
    var runningLabel: String?
    var runningNote: String?
    var runningStart: Date?

    var isRunning: Bool { runningStart != nil }

    /// 当前这段已记录的时长（本地累加，不依赖轮询）
    func runningElapsed() -> TimeInterval {
        guard let s = runningStart else { return 0 }
        return max(0, Date().timeIntervalSince(s))
    }
}

func fmtHM(_ seconds: Double) -> String {
    let total = max(0, Int(seconds))
    return "\(total / 3600):" + String(format: "%02d", (total / 60) % 60)
}

let tsParser: DateFormatter = {
    let f = DateFormatter()
    f.dateFormat = "yyyy-MM-dd HH:mm:ss"
    f.locale = Locale(identifier: "en_US_POSIX")
    f.timeZone = TimeZone.current
    return f
}()

// ---------------------------------------------------------------- 主程序

final class AppDelegate: NSObject, NSApplicationDelegate, NSMenuDelegate {

    var statusItem: NSStatusItem!
    let menu = NSMenu()
    var snap = Snapshot()
    var pollTimer: Timer?
    var tickTimer: Timer?

    /// 解锁提醒。解锁弹窗、每小时横幅、全屏/名单免打扰都在它里面，见 Nudge.swift
    let nudge = NudgeEngine()

    // ---- 生命周期

    func applicationDidFinishLaunching(_ note: Notification) {
        NSApp.setActivationPolicy(.accessory)   // 不出现在 Dock 和 Cmd+Tab
        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        menu.delegate = self
        statusItem.menu = menu

        updateTitle()
        refresh()

        pollTimer = Timer.scheduledTimer(withTimeInterval: kPollSeconds, repeats: true) { [weak self] _ in
            self?.refresh()
        }
        tickTimer = Timer.scheduledTimer(withTimeInterval: 1, repeats: true) { [weak self] _ in
            self?.updateTitle()
            self?.nudge.tick()          // 每小时提醒的到点判定，复用这个秒表
        }
        // .common 模式：菜单展开时定时器也照跑
        RunLoop.main.add(pollTimer!, forMode: .common)
        RunLoop.main.add(tickTimer!, forMode: .common)

        // 解锁提醒。点了弹窗/横幅里的类别按钮，走的就是菜单里那几个动作。
        nudge.onStartCategory = { [weak self] key in
            self?.runCLI(["start", key])
        }
        nudge.start()
    }

    // ---- 调 CLI

    func runCLI(_ args: [String], done: (() -> Void)? = nil) {
        DispatchQueue.global(qos: .utility).async {
            let p = Process()
            p.executableURL = URL(fileURLWithPath: kPythonPath)
            p.arguments = [kScriptPath] + args
            p.currentDirectoryURL = URL(fileURLWithPath: kWorktimeDir)
            var env = ProcessInfo.processInfo.environment
            env["PATH"] = "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
            p.environment = env

            let out = Pipe()
            p.standardOutput = out
            p.standardError = Pipe()   // 吞掉报错噪音，失败时靠退出码判断

            var data = Data()
            var code: Int32 = -1
            do {
                try p.run()
                // 先读完再等退出，避免管道写满导致死锁
                data = out.fileHandleForReading.readDataToEndOfFile()
                p.waitUntilExit()
                code = p.terminationStatus
            } catch {
                DispatchQueue.main.async { done?() }
                return
            }

            DispatchQueue.main.async {
                if code == 0 { self.apply(data) }
                else { self.markFailed("命令执行失败（退出码 \(code)）") }
                done?()
            }
        }
    }

    // ---- 刷新

    func refresh() {
        runCLI(["status", "--json"]) {
            // 动作执行完顺手刷新，这里不用再做别的
        }
    }

    func apply(_ data: Data) {
        guard let any = try? JSONSerialization.jsonObject(with: data),
              let obj = any as? [String: Any] else {
            markFailed("返回数据看不懂")
            return
        }
        var s = Snapshot()
        s.ok = true

        if let w = obj["week_totals_hm"] as? [String: Any],
           let t = w["total"] as? String { s.weekHM = t }
        if let t = obj["today_totals_hm"] as? [String: Any],
           let v = t["total"] as? String { s.todayHM = v }
        if let week = obj["week"] as? [String: Any],
           let lbl = week["label"] as? String { s.weekLabel = lbl }

        // running 为 null 时这句自然不成立
        if let run = obj["running"] as? [String: Any] {
            s.runningKey = run["category"] as? String
            s.runningLabel = run["label"] as? String
            let note = run["note"] as? String
            s.runningNote = (note?.isEmpty ?? true) ? nil : note
            if let ts = run["start_ts"] as? String { s.runningStart = tsParser.date(from: ts) }
        }

        snap = s
        nudge.runningKey = s.runningKey     // 弹窗按钮上那个 ● 标记要用
        updateTitle()
        rebuildMenu()
    }

    func markFailed(_ why: String) {
        snap.ok = false
        snap.errorText = why
        updateTitle()
        rebuildMenu()
    }

    // ---- 标题

    func updateTitle() {
        guard let button = statusItem.button else { return }
        if !snap.ok {
            button.attributedTitle = NSAttributedString(
                string: "⚠️ 工时",
                attributes: [.font: NSFont.systemFont(ofSize: 12, weight: .medium)])
            button.toolTip = "工时记录：连不上数据（\(snap.errorText ?? "未知原因")）"
            return
        }

        let text: String
        if snap.isRunning {
            text = "● \(fmtHM(snap.runningElapsed())) · 本周 \(snap.weekHM)"
        } else {
            text = "⏱ 本周 \(snap.weekHM)"
        }
        // 等宽数字，秒数跳动时标题宽度不抖
        button.attributedTitle = NSAttributedString(string: text, attributes: [
            .font: NSFont.monospacedDigitSystemFont(ofSize: 12, weight: .regular)
        ])
        var tip = "本周 \(snap.weekHM)（\(snap.weekLabel)）\n今日 \(snap.todayHM)"
        if let l = snap.runningLabel {
            tip = "正在记录：\(l)" + (snap.runningNote.map { "（\($0)）" } ?? "") + "\n" + tip
        }
        button.toolTip = tip
    }

    // ---- 菜单

    func rebuildMenu() {
        menu.removeAllItems()

        guard snap.ok else {
            menu.addItem(disabled("⚠️ 读取失败"))
            menu.addItem(disabled(snap.errorText ?? "未知原因"))
            menu.addItem(.separator())
            menu.addItem(item("重试", #selector(doRefresh)))
            menu.addItem(.separator())
            menu.addItem(item("退出", #selector(doQuit)))
            return
        }

        // 状态区
        if snap.isRunning {
            let head = disabled("● \(snap.runningLabel ?? "")　\(fmtHM(snap.runningElapsed()))")
            head.attributedTitle = NSAttributedString(
                string: "● \(snap.runningLabel ?? "")　\(fmtHM(snap.runningElapsed()))",
                attributes: [.font: NSFont.monospacedDigitSystemFont(ofSize: 13, weight: .semibold)])
            menu.addItem(head)
            if let n = snap.runningNote {
                menu.addItem(disabled("　\(n)"))
            }
        } else {
            menu.addItem(disabled("当前没有在计时"))
        }
        menu.addItem(.separator())

        // 三个开始按钮
        for cat in kCategories {
            // 正在跑的那一类写成「继续X」：点它不会重开（core.start 会挡住），
            // 只是跟解锁弹窗的措辞保持一致
            let running = snap.runningKey == cat.key
            let mi = item(running ? "● 继续\(cat.label)" : "▶ 开始\(cat.label)",
                          #selector(doStart(_:)))
            mi.representedObject = cat.key
            menu.addItem(mi)
        }
        let pause = item("⏸ 暂停记录", #selector(doPause))
        pause.isEnabled = snap.isRunning
        menu.addItem(pause)
        menu.addItem(.separator())

        // 汇总
        menu.addItem(disabled("今日　\(snap.todayHM)"))
        menu.addItem(disabled("本周　\(snap.weekHM)　\(snap.weekLabel)"))
        menu.addItem(.separator())

        menu.addItem(item("查看历史…", #selector(doOpenPage)))
        menu.addItem(item("设置一周起点…", #selector(doOpenPage)))
        menu.addItem(item("打开数据文件夹", #selector(doOpenDataDir)))
        menu.addItem(.separator())

        // 提醒（解锁弹窗 / 每小时横幅）
        let mute = item(nudge.isMuted ? "🔕 提醒已安静" : "🔕 安静 1 小时",
                        #selector(doToggleMute))
        mute.state = nudge.isMuted ? .on : .off
        menu.addItem(mute)
        menu.addItem(item("编辑免打扰名单…", #selector(doOpenBlocklist)))
        menu.addItem(.separator())

        menu.addItem(item("立即刷新", #selector(doRefresh)))
        menu.addItem(item("退出", #selector(doQuit)))
    }

    func item(_ title: String, _ action: Selector) -> NSMenuItem {
        let mi = NSMenuItem(title: title, action: action, keyEquivalent: "")
        mi.target = self
        return mi
    }

    func disabled(_ title: String) -> NSMenuItem {
        let mi = NSMenuItem(title: title, action: nil, keyEquivalent: "")
        mi.isEnabled = false
        return mi
    }

    func menuWillOpen(_ menu: NSMenu) {
        refresh()   // 每次展开都拿最新数据
    }

    // ---- 动作

    @objc func doStart(_ sender: NSMenuItem) {
        guard let key = sender.representedObject as? String else { return }
        runCLI(["start", key])
    }

    @objc func doPause() {
        runCLI(["pause"])
    }

    @objc func doRefresh() {
        refresh()
    }

    @objc func doOpenPage() {
        NSWorkspace.shared.open(kServerURL)
    }

    @objc func doOpenDataDir() {
        NSWorkspace.shared.open(URL(fileURLWithPath: kWorktimeDir + "/data"))
    }

    @objc func doToggleMute() {
        if nudge.isMuted { nudge.unmute() } else { nudge.muteFor(3600) }
        rebuildMenu()
    }

    @objc func doOpenBlocklist() {
        let path = kNudgeBlocklistPath
        // 文件被删了就用一份带说明的模板补上，别让「打开」变成什么都没发生
        if !FileManager.default.fileExists(atPath: path) {
            let tpl = """
            # 免打扰名单
            #
            # 前台是这个 App 的时候，解锁弹窗和每小时提醒都不出声。
            # 一行一个，写 App 名字或者 bundle id，大小写随便，# 开头是注释。
            #
            # 只看 bundle id：
            #   osascript -e 'id of app "Steam"'

            """
            try? tpl.write(toFile: path, atomically: true, encoding: .utf8)
        }
        NSWorkspace.shared.open(URL(fileURLWithPath: path))
    }

    @objc func doQuit() {
        NSApp.terminate(nil)
    }
}

// 入口在 main.swift —— swiftc 编译多个文件时，顶层可执行代码只允许写在
// 名为 main.swift 的那个文件里。
