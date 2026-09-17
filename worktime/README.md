# 工时记录

记备课、运营、上课三类工作的时长。菜单栏随时开关，网页翻历史。

- **时:分**，不显示秒
- 一周起点默认**周二**，随时可改，改完历史自动重算
- 开始新类别时**自动结束**上一个，同一时刻只算一件事，时长不会丢
- 忘点的时候可以**补记**，也能改、删已有记录
- 跨零点的记录按实际分钟数**拆到两天**

## 三个入口

| 入口 | 干什么 | 依赖 |
|---|---|---|
| **菜单栏**（右上角） | 随手开始/暂停，一眼看本周 | 无，直接调命令行 |
| **网页** http://127.0.0.1:5899 | 翻历史、补记、改周期、导出 | 本地服务 |
| **桌面摆件** | 贴桌面上看时钟和进度 | Übersicht |

菜单栏刻意**不走网页服务**——万一服务挂了，最常用的「随手记一笔」照样能用。

## 日常怎么用

点菜单栏右上角的 `⏱ 本周 12:30`：

```
● 上课　1:12              ← 正在记录
  探索4班
──────────────────
▶ 开始备课
▶ 开始运营
▶ 开始上课
⏸ 暂停记录                ← 没在计时时是灰的
──────────────────
今日　3:05
本周　12:30　9/8 周二 – 9/14 周一
──────────────────
查看历史…
设置一周起点…
打开数据文件夹
🔕 安静 1 小时
编辑免打扰名单…
──────────────────
立即刷新
退出
```

点「开始上课」时如果备课还在跑，备课会被自动结束并如实记下时长，不会丢。

## 解锁提醒

这套工具有个前提：**你得记得去点**。最容易漏的是两个时刻——锁屏回来（去吃饭、接孩子、睡一觉，回来早想不起几点起的），和一口气干了两三个小时（中间从备课变成运营了，计时器还停在原来那格）。

所以有两条提醒：

- **解锁弹窗**。离开超过 1 分钟再解锁，弹一句「刚回来，现在做什么？」，四个按钮 `继续备课 / 运营 / 上课 / 在玩`。点前三个直接切换，「在玩」就只关掉、计时照跑。60 秒没人理它自己消失，什么都不做。
- **每小时横幅**。屏幕右上角飘一条小横幅，三个按钮，点一下直接切类别。飘 45 秒自己走，**不抢焦点**——你正在打字接着打就行。开机和解锁各起算一次。

**正在跑的那一类，按钮上写的是「继续X」**，点它**什么都不做**——计时照走，起点不变。没在跑的时候就是普通的 `备课 / 运营 / 上课`。

「在玩」只在解锁弹窗里有，因为那条问的是「你刚才在干嘛」，是个需要交代的问题；每小时横幅没这个语境，所以它只有三个类别按钮。

这条规则在数据层（`worktime_core.py` 的 `start()`）挡着，所以菜单、网页、桌面摆件上的「继续X」也一样不会把记录劈开——同一类别点多少下都只算一条。

**不想被打扰的时候它不出声**，三种情况任一满足就静默：

1. 前台 App 在**免打扰名单**里（游戏、播放器这类）
2. 前台窗口**铺满了整块屏**（看电影、演示）
3. 菜单里点了「安静 1 小时」

免打扰名单就是 `nudge_blocklist.txt`，一行一个 App 名字（或者 bundle id），`#` 开头是注释。改完**立刻生效**，不用重启。菜单里有「编辑免打扰名单…」直接打开它。

名单主要用来兜**窗口化运行的游戏**——「有没有铺满屏幕」是自动判的，全屏的认得出，但窗口化跑的游戏跟普通窗口长得一样，只能靠名单。

**为什么每小时提醒是自己画的横幅，不是系统通知**：试过 `UNUserNotificationCenter`，macOS 直接拒了这个 App——`Notifications are not allowed for this application`，连授权框都不弹。换 `open` 启动也一样，所以跟启动方式无关，是**它只有 ad-hoc 签名、没有开发者 Team ID**。系统通知这条路走不通，就自己画了一条，效果更可控。

**出问题先看 `/tmp/worktime-nudge.log`**。这个功能的本职就是打扰你，所以它「没出声」的时候得能查出为什么——是没解锁、锁得太短、全屏静默了，还是手动静默忘了关，日志里都写了。

提醒只在菜单栏 App 活着的时候有效。菜单里点「退出」就没了（这是现有设计，`KeepAlive` 是关的）。

## 桌面摆件

贴在桌面上的一块小卡片，时钟（时:分，不显示秒）、本周总时长、三类分项，底下三个开始按钮和一个暂停按钮，都能直接点。

最下面那行「正在计时」是**时:分:秒**——只有它是带秒的，上面的时钟和所有统计都还是到分钟。摆件本来就每秒重绘一次（`refreshFrequency = 1000`），`elapsed` 每次现算，所以显示到秒**不增加任何轮询**，只是少截掉一段。

**尺寸和底色是照着 macOS 官方桌面小组件量的**（截图逐像素测的，不是估的），摆在一起看不出违和：

| | 官方小组件 | 本摆件 |
|---|---|---|
| 单格宽 / 整块宽 | 163 / 343（两格 + 18px 间隙） | 343 |
| 底色（同一张壁纸上渲染出的颜色） | RGB(84, 67, 61) | RGB(82, 69, 64) |
| 等效不透明度 | 0.62 | 0.62 |
| 圆角 | ~10px | ~10px |

所以卡片底色是 `rgba(29, 14, 10, 0.70)`——**暖调近黑、约七成不透明**，壁纸的色温能透上来。别改回那种又实又偏蓝的深灰，会跟旁边的官方组件明显不一样。

**⚠️ 别再给卡片加 `backdrop-filter`。** 试过 `WebkitBackdropFilter: blur(18px)`，加完摆件会**每秒闪一下**。原因：它把卡片提成一个独立的合成层，卡里内容一变（跳秒）就得重新解析 backdrop，于是整张卡 3800 多个像素被重画成略有差异的另一个样子，30 毫秒后再变回来。而且这个模糊本身是白做的——卡片背后是透明的网页背景不是壁纸，等于什么都没糊到。删掉之后视觉上完全一样，闪烁没了。上面那张配色表是**没有 backdrop-filter** 的状态下量的，所以删掉不会影响跟官方组件的对齐。

**摆位置**：**按住卡片直接拖**，松手自动记住，下次开机还在原地（坐标存在数据库的 `settings` 表里）。

Übersicht 本身不带拖动功能（摆件菜单里的「Edit...」是用编辑器打开源码，不是拖动模式），拖动是摆件自己实现的。

初始位置（还没拖过时）写在 `uebersicht/worktime.widget/index.jsx` 的 `className` 里，默认右上角。想改初始位置就改这两行，然后重跑 `uebersicht/install.sh`：

```js
export const className = `
  top: 44px;
  right: 24px;
`;
```

**⚠️ 必须先打开「Enable interaction」**：Übersicht 默认让桌面层**点击穿透**，这样一来摆件上的按钮和拖动全都点不到。打开方式：

> 菜单栏 Übersicht 图标 → **Preferences…** → 勾上 **Enable interaction**

（命令行等价于 `defaults write tracesOf.Uebersicht enableInteraction -bool true`，改完重启 Übersicht。）

摆件和菜单栏一样是**想点就点**的，但两者走的不是同一条路：摆件跑在 Übersicht 的网页视图里，读数据靠 `curl` 打本地服务，点按钮靠 `fetch`。所以——

- **摆件依赖本地服务**（5899）。服务挂了摆件会显示「连不上本地服务」，菜单栏则不受影响。
- **摆件显示的前提是 Übersicht 在跑**，它不常驻也没关系，需要时打开就行。

重装或改动摆件：

```bash
cd uebersicht && ./install.sh          # 装 / 覆盖更新（原地改文件）
cd uebersicht && ./install.sh -f       # 干净重装（先删掉再装）
cd uebersicht && ./install.sh -u       # 卸载
```

**更新默认是原地覆盖，不删了重建**。原地覆盖只是改文件，Übersicht 走热加载；删了再建会让它销毁实例重新来过，没必要。只有真出问题了才需要 `-f`。

改完 `uebersicht/worktime.widget/index.jsx` 要重新跑一次 `install.sh`，它才会把新版本拷进 Übersicht 的目录。Übersicht 这边是**自动热加载**的，不用重启 App。

## 命令行

调试和脚本用。菜单栏 App 其实就是调这些。

```bash
cd ~/"Claude code-课后素材"/worktime

python3 worktime.py start cls --note "探索4班"   # 开始（自动结束上一个）
python3 worktime.py pause                        # 暂停
python3 worktime.py status                       # 当前状态
python3 worktime.py status --json                # 给程序读

python3 worktime.py today                        # 今天明细
python3 worktime.py week                         # 本周明细
python3 worktime.py week --offset -1             # 上周
python3 worktime.py report --from 09-01 --to 09-14

python3 worktime.py add ops --date 2026-09-10 --start 09:00 --end 10:15 --note "排课表"
python3 worktime.py list                         # 带 id，方便改删
python3 worktime.py edit 7 --end 10:45
python3 worktime.py delete 7

python3 worktime.py config --day 1               # 改成周一起算（1=周一 … 7=周日）
python3 worktime.py config --day 3 --hour 6      # 周三早上 6 点起算

python3 worktime.py export --from 09-01 --to 09-30 > 工时.csv
```

`add` 和 `edit` 里**结束时间早于开始时间会自动算作跨零点**（比如 23:30–00:45）。

## 周期规则

一周的边界 = 「每周 X 的 H 点整」。

- 默认 `day=2`（周二）、`hour=0`，即周二 00:00 到下一个周二 00:00
- 周三 06:00 起算的话，周三早上 6 点前的记录算上一周
- 数据库里**不存**「这条属于哪一周」，全是查的时候现算的，所以改设置后历史自动重新分周，不用迁移数据

网页上那个「一周从 __ 开始」的下拉改的就是它。

## 文件

```
worktime/
  worktime_core.py        数据层：SQLite、周期算法、时长统计（唯一业务逻辑）
  worktime.py             命令行入口
  worktime_server.py      本地服务 127.0.0.1:5899
  static/worktime.html    回看页（单文件，无框架，跟着系统深色模式走）
  menubar/main.swift      菜单栏 App 入口（swiftc 要求顶层代码只在 main.swift 里）
  menubar/WorkTime.swift  菜单栏 App 界面
  menubar/Nudge.swift     解锁提醒：解锁弹窗 / 每小时横幅 / 免打扰判定
  menubar/build.sh        编译脚本（只要命令行工具，不用装 Xcode）
  menubar/Info.plist
  nudge_blocklist.txt     免打扰名单（游戏、播放器）
  uebersicht/worktime.widget/index.jsx   桌面摆件
  uebersicht/install.sh                  装/卸摆件
  launchd/install.sh      装/卸开机自启
  launchd/*.plist
  data/worktime.db        你的数据（已 gitignore）
```

数据库就是普通 SQLite，想备份直接拷 `data/` 整个文件夹。想看里面有什么：

```bash
sqlite3 data/worktime.db "select * from sessions order by start_ts desc limit 20"
```

## 维护

**改完代码重新编译菜单栏 App：**

```bash
cd menubar && ./build.sh --run
```

`build.sh` 会把 python3 和工时目录的绝对路径写进源码——所以**移动了这个文件夹就要重新编译一次**。

**改完 `worktime_server.py` 或 `worktime_core.py` 让服务生效：**

```bash
launchctl kickstart -k gui/$(id -u)/com.zhuguangpi.worktime
```

**日志：**

- 服务：`/tmp/worktime-server.log`、`/tmp/worktime-server.err`
- 菜单栏：`/tmp/worktime-menubar.log`
- 解锁提醒：`/tmp/worktime-nudge.log`（它「没出声」的原因都写在这儿）

**卸载开机自启**（数据和代码都留着）：

```bash
cd launchd && ./install.sh -u
```

## 已知的坑

- **首次打开菜单栏 App**，macOS 可能拦一下，说无法验证开发者。去 系统设置 → 隐私与安全性，点「仍要打开」。这是因为没有苹果开发者证书，只能 ad-hoc 签名。
- **`export` 导出的 CSV 里跨零点的记录是一行**（如 `23:30–00:45` 记 1.25 小时），而网页和 `week` 里是拆成两天的。导出是流水视角，统计是日历视角，两个都对，看你用哪个。
- 机器重启后菜单栏 App 会自动起来；如果从菜单里点了「退出」，那**这次登录期间**就不会再自动起来，重新打开一次 `menubar/WorkTime.app` 即可。
