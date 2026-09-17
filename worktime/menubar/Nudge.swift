// 工时记录 · 解锁提醒
//
// 这个工具的根本弱点是「你得记得去点」。最容易漏的是两个时刻：
//
//   1. 锁屏回来。去吃饭、接孩子、睡一觉，回来早想不起自己几点切过类别，
//      甚至忘了锁屏前根本没暂停。
//   2. 一口气干了两三个小时。中间从备课变成运营了，计时器还停在原来那格。
//
// 所以这里做三件事：解锁弹窗问一句、每小时飘一条带按钮的横幅、以及
// **不想被打扰的时候一律不出声**（全屏 / 名单里的 App）。
//
// 挂在菜单栏 App 的进程里，不新起常驻进程——它本来就在跑，已经有调 CLI 的
// 通路，也已经有每秒一次的 tick，复用现成的就行。
//
// ── 为什么每小时提醒是自画的横幅，不是系统通知 ──────────────────
//
// 一开始用的是 UNUserNotificationCenter，实测在这台机器上被系统直接拒了：
//
//     通知授权请求 → 拒绝  错误：Notifications are not allowed for this application
//
// 不是用户点了「不允许」——是**压根没弹授权框**，系统看到这个 App 就拒。
// 换成 `open WorkTime.app` 正经走一遍 LaunchServices 注册，结果一模一样，
// 所以跟「launchd 直接拉内层二进制」无关。真正的原因是它只有 ad-hoc 签名、
// 没有 Team ID，macOS 26 不给这种 App 发通知。
//
// （顺带一提，NSUserNotification 这条老路也没了——macOS 26 的 Foundation 里
//   那个符号已经被删干净，nm 出来是 0 个。）
//
// 所以横幅自己画。反正「系统通知」只是实现手段，要的是「不打断你、点一下
// 就能切类别」——非模态面板一样能做到，还不用求系统给权限，顺便能跟桌面摆件
// 长得像一点。

import Cocoa
import CoreGraphics

// ---------------------------------------------------------------- 参数
//
// 这几个数都是拍脑袋定的，觉得不对劲直接改。

/// 免打扰名单。纯文本，一行一个 App 名，# 开头是注释。
let kNudgeBlocklistPath = kWorktimeDir + "/nudge_blocklist.txt"

/// 提醒自己的流水账。
///
/// 这个功能的本职就是「打扰你」，所以**它没出声的时候你得能查出为什么**——
/// 是没解锁？是锁得太短？是全屏静默了？还是手动静默忘了关？
/// 没有这份日志，这些全都只能靠猜。出问题先看这里。
let kNudgeLogPath = "/tmp/worktime-nudge.log"

/// 锁屏短于这个时长就不问了——快捷键误触、屏保闪一下，都不是「离开过」
let kMinLockSeconds: TimeInterval = 60

/// 两次弹窗的最短间隔。深睡唤醒的兜底路径和正常的解锁通知可能对同一次
/// 解锁各触发一回，靠这个压掉重复。
let kDedupeSeconds: TimeInterval = 90

/// 解锁弹窗没人理就自己关掉，别一直杵在那儿
let kAlertTimeoutSeconds: TimeInterval = 60

/// 每小时提醒的间隔
let kHourlyInterval: TimeInterval = 3600

/// 迟到超过这么久就不补发了。睡一觉醒来时「到点」早就过去几小时了，
/// 补发只会连着弹一堆没意义的提醒。
let kHourlyLateGrace: TimeInterval = 600

/// 横幅自己消失前待多久
let kBannerTimeoutSeconds: TimeInterval = 45

/// 窗口边缘离屏幕边缘允许差几个像素，就算「铺满了整块屏」。
///
/// 这里**不能**用「覆盖率 ≥95%」那种松判据：这台机器菜单栏占 25px，
/// 一个只是点了最大化的窗口高度是 1415，覆盖率 98%，会被误判成全屏——
/// 明明还看得见菜单栏，却当成全屏静默了。全屏窗口（原生全屏、无边框全屏）
/// 都是严丝合缝盖满整块屏的，所以要求四条边都贴齐，留 2px 防亚像素误差。
let kFullscreenSlack: CGFloat = 2

// ---------------------------------------------------------------- 小工具

func nudgeLog(_ msg: String) {
    let f = DateFormatter()
    f.dateFormat = "MM-dd HH:mm:ss"
    guard let data = ("\(f.string(from: Date()))  \(msg)\n").data(using: .utf8) else { return }
    if let fh = FileHandle(forWritingAtPath: kNudgeLogPath) {
        fh.seekToEndOfFile()
        fh.write(data)
        try? fh.close()
    } else {
        try? data.write(to: URL(fileURLWithPath: kNudgeLogPath))
    }
}

/// 这个窗口是不是严丝合缝盖满了整块屏幕。
///
/// 两个 rect 必须都是 Quartz 坐标（左上角为原点），调用方负责保证。
/// 拆成独立函数是为了能把「最大化窗口不算全屏」这件事单独测一遍。
func coversWholeDisplay(_ r: CGRect, _ screen: CGRect) -> Bool {
    r.minX <= screen.minX + kFullscreenSlack &&
    r.minY <= screen.minY + kFullscreenSlack &&
    r.maxX >= screen.maxX - kFullscreenSlack &&
    r.maxY >= screen.maxY - kFullscreenSlack
}

extension NSColor {
    /// 从 "#38bdf8" 这种写法的十六进制取色，跟网页和摆件用的是同一套色号
    convenience init(hex: String) {
        var s = hex.trimmingCharacters(in: .whitespaces)
        if s.hasPrefix("#") { s.removeFirst() }
        var v: UInt64 = 0
        Scanner(string: s).scanHexInt64(&v)
        self.init(srgbRed: CGFloat((v >> 16) & 0xFF) / 255,
                  green: CGFloat((v >> 8) & 0xFF) / 255,
                  blue: CGFloat(v & 0xFF) / 255,
                  alpha: 1)
    }
}

// ---------------------------------------------------------------- 横幅
//
// 自己画的一条小横幅，贴在屏幕右上角菜单栏底下。
//
// 关键是**非模态、不抢焦点**：用 .nonactivatingPanel + orderFrontRegardless()，
// 它飘出来的时候你正在打字的那个窗口还是活的，接着打就行，不理它过一会儿自己走。
//
// 用 NSPanel 而不是 NSWindow，是因为只有 panel 能在 App 不是前台的时候正常显示
// 并接收点击——菜单栏 App 是 .accessory，永远不是「前台 App」。

final class NudgeBanner: NSObject {

    var onPick: ((String) -> Void)?

    private var panel: NSPanel?
    private var dismissTimer: Timer?

    private let width: CGFloat = 340
    private let height: CGFloat = 106

    func show(title: String, runningKey: String?) {
        dismiss()   // 已经有一条就换掉，不叠着

        guard let screen = NSScreen.main else { return }
        let vis = screen.visibleFrame

        let p = NSPanel(contentRect: NSRect(x: 0, y: 0, width: width, height: height),
                        styleMask: [.borderless, .nonactivatingPanel],
                        backing: .buffered, defer: false)
        p.isOpaque = false
        p.backgroundColor = .clear
        p.hasShadow = true
        p.level = .floating
        // 所有桌面空间都显示；但**不含** .fullScreenAuxiliary，
        // 所以不会盖到全屏应用上去（那边本来也静默了）
        p.collectionBehavior = [.canJoinAllSpaces, .stationary, .ignoresCycle]
        p.hidesOnDeactivate = false
        p.becomesKeyOnlyIfNeeded = true

        let blur = NSVisualEffectView(frame: NSRect(x: 0, y: 0, width: width, height: height))
        blur.material = .hudWindow
        blur.blendingMode = .behindWindow
        blur.state = .active
        blur.wantsLayer = true
        blur.layer?.cornerRadius = 14
        blur.layer?.masksToBounds = true
        blur.layer?.borderWidth = 1
        blur.layer?.borderColor = NSColor.white.withAlphaComponent(0.13).cgColor

        // 标题
        let label = NSTextField(labelWithString: title)
        label.font = .systemFont(ofSize: 13, weight: .semibold)
        label.textColor = .labelColor
        label.frame = NSRect(x: 16, y: height - 36, width: width - 130, height: 18)
        blur.addSubview(label)

        // 右边那行小字：现在正在记什么
        let now = runningKey.flatMap { k in kCategories.first { $0.key == k }?.label }
        let hint = NSTextField(labelWithString: now.map { "● \($0)" } ?? "没在计时")
        hint.font = .systemFont(ofSize: 11)
        hint.textColor = now == nil ? .tertiaryLabelColor : .secondaryLabelColor
        hint.alignment = .right
        hint.frame = NSRect(x: width - 130, y: height - 35, width: 114, height: 16)
        blur.addSubview(hint)

        // 三个按钮
        //
        // 不用系统那种圆角按钮：contentTintColor 只染「内容」不染底，
        // 试过是一排灰的，跟网页和摆件那套色号对不上。所以自己铺底色。
        let pad: CGFloat = 16, gap: CGFloat = 8
        let btnW = (width - pad * 2 - gap * 2) / 3
        for (i, cat) in kCategories.enumerated() {
            let b = NSButton(frame: NSRect(x: pad + CGFloat(i) * (btnW + gap),
                                           y: 16, width: btnW, height: 32))
            b.isBordered = false
            b.wantsLayer = true
            b.layer?.backgroundColor = NSColor(hex: cat.color).cgColor
            b.layer?.cornerRadius = 9
            b.attributedTitle = NSAttributedString(
                string: runningKey == cat.key ? "继续\(cat.label)" : cat.label,
                attributes: [
                    .foregroundColor: NSColor.white,
                    .font: NSFont.systemFont(ofSize: 12.5, weight: .semibold),
                ])
            b.target = self
            b.action = #selector(pick(_:))
            b.identifier = NSUserInterfaceItemIdentifier(cat.key)
            blur.addSubview(b)
        }

        p.contentView = blur
        p.setFrameOrigin(NSPoint(x: vis.maxX - width - 16, y: vis.maxY - height - 12))
        p.orderFrontRegardless()     // 显示但不激活，别抢你的焦点
        panel = p

        let t = Timer.scheduledTimer(withTimeInterval: kBannerTimeoutSeconds, repeats: false) { [weak self] _ in
            self?.dismiss()
        }
        RunLoop.main.add(t, forMode: .common)
        dismissTimer = t
    }

    func dismiss() {
        dismissTimer?.invalidate()
        dismissTimer = nil
        panel?.orderOut(nil)
        panel = nil
    }

    @objc private func pick(_ sender: NSButton) {
        let key = sender.identifier?.rawValue ?? ""
        dismiss()
        onPick?(key)
    }
}

// ---------------------------------------------------------------- 引擎

final class NudgeEngine {

    /// 用户在弹窗/横幅里选了某个类别 → 回调出去（由 AppDelegate 去调 CLI）
    var onStartCategory: ((String) -> Void)?

    /// 当前正在计时的类别 key，用来在按钮上加个 ● 标记
    var runningKey: String?

    private let banner = NudgeBanner()

    // 解锁状态机
    private var wasLocked = false
    private var lockedAt: Date?

    private var lastPromptAt: Date?
    private var nextHourlyDue: Date?
    private var mutedUntil: Date?
    private var observers: [NSObjectProtocol] = []

    // ---- 生命周期

    /// 由 AppDelegate 在启动时调一次
    func start() {
        nudgeLog("—— 启动 · 名单 \(kNudgeBlocklistPath)")
        banner.onPick = { [weak self] key in
            self?.onStartCategory?(key)
        }
        // 开机也起算一次。只在解锁时起算的话，「早上开机、一整天没锁过屏」
        // 就一条提醒都收不到——而那恰恰是最容易忘记切类别的一天。
        nextHourlyDue = Date().addingTimeInterval(kHourlyInterval)
        setupObservers()
    }

    // ---- 解锁监听

    private func setupObservers() {
        // 注意是 DistributedNotificationCenter，不是 NSWorkspace 的那个。
        // 这俩搞混了观察者永远不会触发，是这块最常见的坑。
        let dnc = DistributedNotificationCenter.default()

        observers.append(dnc.addObserver(
            forName: NSNotification.Name("com.apple.screenIsLocked"),
            object: nil, queue: .main
        ) { [weak self] _ in
            self?.wasLocked = true
            self?.lockedAt = Date()
            nudgeLog("锁屏")
        })

        observers.append(dnc.addObserver(
            forName: NSNotification.Name("com.apple.screenIsUnlocked"),
            object: nil, queue: .main
        ) { [weak self] _ in
            self?.handleUnlock()
        })

        // 兜底：解锁通知在深睡唤醒后不一定发得出来（Sonoma 之后一直有这毛病）。
        // 所以再听一个唤醒，醒来后等几秒看看到底还锁不锁着——不锁了就当解锁处理。
        observers.append(NSWorkspace.shared.notificationCenter.addObserver(
            forName: NSWorkspace.didWakeNotification,
            object: nil, queue: .main
        ) { [weak self] _ in
            DispatchQueue.main.asyncAfter(deadline: .now() + 3) {
                guard let self, self.wasLocked else { return }
                if self.isSessionLocked() { return }   // 还锁着，等真正的解锁通知
                nudgeLog("唤醒后补触发解锁")
                self.handleUnlock()
            }
        })
    }

    private func isSessionLocked() -> Bool {
        guard let d = CGSessionCopyCurrentDictionary() as? [String: Any] else { return false }
        return (d["CGSSessionScreenIsLocked"] as? Bool) ?? false
    }

    private func handleUnlock() {
        guard wasLocked else { return }
        wasLocked = false

        // 离开得太短，当没这回事
        if let t = lockedAt, Date().timeIntervalSince(t) < kMinLockSeconds {
            nudgeLog("解锁 · 只离开了 \(Int(Date().timeIntervalSince(t)))s（门槛 \(Int(kMinLockSeconds))s），不问")
            return
        }

        // 每小时提醒的钟，每次真解锁都重新起算
        nextHourlyDue = Date().addingTimeInterval(kHourlyInterval)

        // 兜底路径和正常路径可能都走到这儿，去重
        if let t = lastPromptAt, Date().timeIntervalSince(t) < kDedupeSeconds {
            nudgeLog("解锁 · 刚问过 \(Int(Date().timeIntervalSince(t)))s 前，去重跳过")
            return
        }

        if let why = quietReason() {
            nudgeLog("解锁 · 静默不弹（\(why)）")
            return
        }

        lastPromptAt = Date()
        nudgeLog("解锁 · 弹窗")
        presentPicker(title: "刚回来，现在做什么？",
                      subtitle: "点一个开始计时，或在玩就关掉")
    }

    // ---- 免打扰

    /// 全屏、名单里的 App、或者手动安静期，任一成立就闭嘴。
    /// 返回原因（没静默就是 nil）——日志里要写清楚是被谁挡下来的。
    func quietReason() -> String? {
        if let until = mutedUntil, Date() < until {
            return "手动静默中，还有 \(Int(until.timeIntervalSince(Date()) / 60)) 分钟"
        }
        if frontAppIsBlocked() {
            return "前台 App 在免打扰名单里"
        }
        if frontWindowIsFullscreen() {
            return "前台窗口铺满了整块屏"
        }
        return nil
    }

    private func frontAppIsBlocked() -> Bool {
        guard let app = NSWorkspace.shared.frontmostApplication else { return false }
        let candidates = [app.localizedName, app.bundleIdentifier]
            .compactMap { $0?.lowercased() }
        guard !candidates.isEmpty else { return false }

        // 每次现读，改完名单立刻生效，不用重启 App
        guard let text = try? String(contentsOfFile: kNudgeBlocklistPath, encoding: .utf8) else {
            return false
        }
        for raw in text.split(separator: "\n") {
            let line = raw.trimmingCharacters(in: .whitespaces)
            if line.isEmpty || line.hasPrefix("#") { continue }
            if candidates.contains(line.lowercased()) { return true }
        }
        return false
    }

    private func frontWindowIsFullscreen() -> Bool {
        guard let pid = NSWorkspace.shared.frontmostApplication?.processIdentifier else {
            return false
        }

        // 基准必须用 CGDisplayBounds——它和 CGWindowBounds 同属「左上角为原点」
        // 的 Quartz 坐标。用 NSScreen.frame 会错，那是左下角为原点的 Cocoa 坐标。
        let screen = CGDisplayBounds(CGMainDisplayID())
        guard screen.width > 0, screen.height > 0 else { return false }

        // 不需要屏幕录制权限——被权限挡住的是 kCGWindowName（窗口标题），
        // bounds / layer / pid 照给。
        guard let list = CGWindowListCopyWindowInfo(
            [.optionOnScreenOnly, .excludeDesktopElements], kCGNullWindowID
        ) as? [[String: Any]] else { return false }

        for w in list {
            guard let owner = w[kCGWindowOwnerPID as String] as? pid_t, owner == pid else { continue }
            guard let layer = w[kCGWindowLayer as String] as? Int, layer == 0 else { continue }
            guard let dict = w[kCGWindowBounds as String] as? [String: Any],
                  let r = CGRect(dictionaryRepresentation: dict as CFDictionary)
            else { continue }

            if coversWholeDisplay(r, screen) { return true }
        }
        return false
    }

    // ---- 手动静默

    func muteFor(_ seconds: TimeInterval) {
        mutedUntil = Date().addingTimeInterval(seconds)
        nudgeLog("手动静默 \(Int(seconds / 60)) 分钟")
    }

    func unmute() {
        mutedUntil = nil
        nudgeLog("解除手动静默")
    }

    var isMuted: Bool {
        guard let until = mutedUntil else { return false }
        return Date() < until
    }

    // ---- 解锁弹窗

    private func presentPicker(title: String, subtitle: String?) {
        let alert = NSAlert()
        alert.messageText = title
        if let s = subtitle { alert.informativeText = s }
        alert.alertStyle = .informational

        // 按钮顺序必须跟 kCategories 一致，后面靠 first/second/third 认。
        // 正在跑的那一类写成「继续X」——点它什么都不做（core.start 会挡住，
        // 不会把记录劈成两条），只是给你一个「维持现状」的出口。
        for cat in kCategories {
            alert.addButton(withTitle: runningKey == cat.key ? "继续\(cat.label)" : cat.label)
        }
        // 「在玩」只在解锁弹窗里给。这条问的是「你刚才在干嘛」，那是个需要
        // 交代的问题；每小时横幅没这个语境，所以它只有三个类别按钮。
        alert.addButton(withTitle: "在玩")

        NSApp.activate(ignoringOtherApps: true)

        // 没人理就自己关。这个 timer 加在 .common 模式上，所以弹窗期间
        // 菜单栏的标题照样在跳秒（原来那两个 timer 也是这么加的）。
        //
        // 不用额外加「是否已关闭」的标志位：runModal 和 invalidate 都在主线程
        // 上顺序执行，中间不可能插进来一次 timer 回调。
        let timeout = Timer.scheduledTimer(withTimeInterval: kAlertTimeoutSeconds, repeats: false) { _ in
            NSApp.abortModal()
        }
        RunLoop.main.add(timeout, forMode: .common)

        let resp = alert.runModal()
        timeout.invalidate()

        // 「在玩」和超时都落到 default —— 按需求，什么都不做，计时照跑
        switch resp {
        case .alertFirstButtonReturn:
            nudgeLog("弹窗 → 选「\(kCategories[0].label)」")
            onStartCategory?(kCategories[0].key)
        case .alertSecondButtonReturn:
            nudgeLog("弹窗 → 选「\(kCategories[1].label)」")
            onStartCategory?(kCategories[1].key)
        case .alertThirdButtonReturn:
            nudgeLog("弹窗 → 选「\(kCategories[2].label)」")
            onStartCategory?(kCategories[2].key)
        default:
            nudgeLog("弹窗 → 在玩 / 超时未答，什么都不做")
        }
    }

    // ---- 每小时提醒

    /// 由 AppDelegate 的每秒 tick 调进来
    func tick() {
        guard let due = nextHourlyDue else { return }
        let now = Date()
        guard now >= due else { return }

        // 无论发不发，先把下一次排上，避免同一秒里反复触发
        nextHourlyDue = now.addingTimeInterval(kHourlyInterval)

        // 睡过去了，这一轮就算了
        if now.timeIntervalSince(due) > kHourlyLateGrace {
            nudgeLog("每小时 · 迟到 \(Int(now.timeIntervalSince(due) / 60)) 分钟，不补发")
            return
        }
        if let why = quietReason() {
            nudgeLog("每小时 · 静默不提醒（\(why)）")
            return
        }

        nudgeLog("每小时 · 飘横幅")
        banner.show(title: "现在在做什么？", runningKey: runningKey)
    }
}
