// 工时记录 · Übersicht 桌面摆件
//
// 数据靠 curl 打本地服务（每秒一次，curl 只要几毫秒，比起 Python 进程便宜太多）；
// 按钮点击走 fetch。
//
// 注：Übersicht 1.6 的 JSX widget 里**没有** run() 这个全局函数，
// 所以按钮不能靠「执行 shell 命令」，只能走 HTTP——服务端起见 worktime_server.py
// 里的 CORS 处理。

export const command = `printf '%s\\n' "$(date '+%H:%M %u')"
curl -s --max-time 2 http://127.0.0.1:5899/api/status || echo '{}'
`;

export const refreshFrequency = 1000;

const API = "http://127.0.0.1:5899";

const CATS = { prep: "备课", ops: "运营", cls: "上课" };
const COLORS = { prep: "#38bdf8", ops: "#fb923c", cls: "#7c6ff7" };
const WEEKDAYS = ["", "周一", "周二", "周三", "周四", "周五", "周六", "周日"];

// 带秒的版本，只给「正在计时」那一行用——统计类的数字还是到分钟就好。
// 摆件本来就是每秒重绘一次（refreshFrequency = 1000），elapsed 也是每次现算的，
// 所以显示到秒**不增加任何轮询**，纯粹是少截掉一段。
// 配合样式里的 tabular-nums，十小时以内恒为 7 个字符，宽度不会跳。
function hms(sec) {
  const t = Math.max(0, Math.floor(sec || 0));
  return (
    Math.floor(t / 3600) +
    ":" +
    String(Math.floor(t / 60) % 60).padStart(2, "0") +
    ":" +
    String(t % 60).padStart(2, "0")
  );
}

function post(path, body) {
  try {
    fetch(API + path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    }).catch(function () {});
  } catch (e) {}
}

// ---------------------------------------------------------------- 拖动
//
// Übersicht 没给拖动功能，这段自己实现。两个坑：
//
// 1. render 每秒被调用一次，会把手动改过的 DOM 样式冲掉。所以坐标存在
//    模块级的 pos 里，render 每次都照着它重画——手动写 DOM 只是为了让
//    拖动跟手，两者写的是同一个值，不会打架。
// 2. 卡片上还有按钮，直接监听 mouseup 会把点按钮也当成拖动。所以按下后
//    移动超过 4px 才算拖，并且把随之而来的那次 click 吃掉。

let pos = null;        // 已保存的坐标 {top, left}；null = 还没拖过，用默认位置
let drag = null;       // 拖动进行中的临时数据
let swallow = false;   // 这次按下发生了拖动 → 吞掉紧跟着的 click

function onDragMove(e) {
  if (!drag) return;
  const dx = e.clientX - drag.x;
  const dy = e.clientY - drag.y;
  if (!drag.moved && Math.abs(dx) < 4 && Math.abs(dy) < 4) return;
  drag.moved = true;
  swallow = true;
  pos = { top: Math.max(0, drag.top + dy), left: Math.max(0, drag.left + dx) };
  // 直接写 DOM，这样每秒重渲染的间隙里也能跟手
  drag.el.style.position = "fixed";
  drag.el.style.right = "auto";
  drag.el.style.top = pos.top + "px";
  drag.el.style.left = pos.left + "px";
}

function onDragEnd() {
  window.removeEventListener("mousemove", onDragMove);
  window.removeEventListener("mouseup", onDragEnd);
  if (drag && drag.moved && pos) post("/api/widget_pos", pos);   // 松手存盘
  drag = null;
}

function onDragStart(e) {
  if (e.button !== 0) return;
  swallow = false;                       // 每次按下重新判断，避免漏吞或误吞
  const r = e.currentTarget.getBoundingClientRect();
  drag = { x: e.clientX, y: e.clientY, top: r.top, left: r.left, moved: false, el: e.currentTarget };
  window.addEventListener("mousemove", onDragMove);
  window.addEventListener("mouseup", onDragEnd);
}

// 按钮用：发生了拖动就吞掉这次点击，别让它误触发开始/暂停
function armClick() {
  if (swallow) {
    swallow = false;
    return false;
  }
  return true;
}

export const render = ({ output }) => {
  const raw = output || "";
  const nl = raw.indexOf("\n");
  const clockLine = (nl >= 0 ? raw.slice(0, nl) : "").trim();
  const jsonText = nl >= 0 ? raw.slice(nl + 1).trim() : "";

  const parts = clockLine.split(" ");
  const hhmm = parts[0];
  const dow = parts[1];

  let st = null;
  try {
    st = JSON.parse(jsonText);
  } catch (e) {
    st = null;
  }

  // 服务里存着的坐标只在第一帧读一次；之后以拖出来的 pos 为准
  if (!pos && st && st.widget_pos) pos = st.widget_pos;

  // 拖过就用存的坐标，没拖过就用 className 里的默认位置（右上角）
  const box = pos
    ? { ...card, position: "fixed", top: pos.top + "px", left: pos.left + "px", right: "auto" }
    : card;

  // 服务没起来 / 返回不完整
  if (!st || !st.week_totals_hm) {
    return (
      <div style={box} onMouseDown={onDragStart}>
        <div style={{ fontSize: "11.5px", color: "#f47289" }}>
          工时记录：连不上本地服务
        </div>
        <div style={{ fontSize: "10.5px", color: "#6b718a", marginTop: "5px" }}>
          launchctl kickstart -k gui/$(id -u)/com.zhuguangpi.worktime
        </div>
      </div>
    );
  }

  const running = st.running;
  const elapsed = running
    ? Math.max(
        0,
        (Date.now() - new Date(running.start_ts.replace(" ", "T")).getTime()) / 1000
      )
    : 0;

  return (
    <div style={box} onMouseDown={onDragStart}>
      {/* 时钟 —— 时:分，不显示秒 */}
      <div style={{ display: "flex", alignItems: "baseline", gap: "8px" }}>
        <span style={clock}>{hhmm || "--:--"}</span>
        <span style={{ fontSize: "12px", color: "#9aa0b4" }}>{WEEKDAYS[dow] || ""}</span>
      </div>

      <div style={hr} />

      {/* 本周 */}
      <div style={{ display: "flex", alignItems: "baseline", gap: "8px" }}>
        <span style={{ fontSize: "12px", color: "#9aa0b4" }}>本周</span>
        <span style={week}>{st.week_totals_hm.total}</span>
        <span style={{ fontSize: "10.5px", color: "#6b718a", marginLeft: "auto" }}>
          今日 {st.today_totals_hm.total}
        </span>
      </div>

      {/* 三类分项 */}
      <div style={{ display: "flex", gap: "12px", marginTop: "7px" }}>
        {Object.keys(CATS).map(function (k) {
          return (
            <div key={k} style={{ display: "flex", alignItems: "center", gap: "5px" }}>
              <span style={{ ...dot, background: COLORS[k] }} />
              <span style={{ fontSize: "11px", color: "#9aa0b4" }}>{CATS[k]}</span>
              <span style={num}>{st.week_totals_hm[k]}</span>
            </div>
          );
        })}
      </div>

      <div style={hr} />

      {/* 三个开始按钮 */}
      <div style={{ display: "flex", gap: "6px" }}>
        {Object.keys(CATS).map(function (k) {
          const on = running && running.category === k;
          return (
            <button
              key={k}
              style={{ ...btn, background: COLORS[k], opacity: on ? 0.45 : 1 }}
              onClick={function () {
                if (armClick()) post("/api/start", { category: k });
              }}
            >
              {(on ? "● " : "▶ ") + CATS[k]}
            </button>
          );
        })}
      </div>

      {/* 正在计时 */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "8px",
          marginTop: "9px",
          height: "20px",
        }}
      >
        {running ? (
          <div style={{ display: "flex", alignItems: "center", gap: "8px", width: "100%" }}>
            <span style={{ ...dot, background: COLORS[running.category] }} />
            <span style={{ fontSize: "12px", color: "#e8eaf0" }}>
              {CATS[running.category]}
              {running.note ? " · " + running.note : ""}
            </span>
            <span style={{ ...num, fontSize: "13px" }}>{hms(elapsed)}</span>
            <button
              onClick={function () {
                if (armClick()) post("/api/pause");
              }}
              style={pauseBtn}
            >
              ⏸ 暂停
            </button>
          </div>
        ) : (
          <span style={{ fontSize: "11.5px", color: "#6b718a" }}>没有在计时</span>
        )}
      </div>
    </div>
  );
};

// ---------------------------------------------------------------- 样式

const card = {
  // 跟 macOS 官方桌面小组件对齐（都是截图实测出来的）：
  //   宽度 —— 官方一格 163px，两格 + 中间 18px 间隙 = 343px，整块左右边缘对齐
  //   底色 —— 官方材质等效于「暖调近黑 + 约 2/3 不透明度」，壁纸的暖色能透上来；
  //           原来的 rgba(20,22,32,0.82) 太实又偏蓝，显得又暗又冷
  boxSizing: "border-box",
  width: "343px",
  cursor: "move",              // 提示整张卡都能拖（按钮自己有 pointer，会盖掉）
  padding: "14px 16px 13px",
  borderRadius: "16px",
  background: "rgba(29, 14, 10, 0.70)",
  border: "1px solid rgba(255,255,255,0.09)",
  boxShadow: "0 8px 28px rgba(0,0,0,0.34)",
  color: "#e8eaf0",
  // 这里原本有一条 WebkitBackdropFilter: blur(18px)，已删。
  //
  // 它其实什么都没模糊——卡片背后是透明的网页背景，不是壁纸，所以模糊等于没做。
  // 但它会让 WebKit 把这张卡提成一个独立的合成层，每次卡里内容一变就要重新解析
  // backdrop。实测下来，每秒跳秒时整张卡 3800 多个像素会被重画成略有差异的另一个
  // 样子，30 毫秒后再变回来——看上去就是「每秒闪一下」。
  //
  // 删掉之后这个重画就没了，视觉上毫无区别（本来也没糊到任何东西）。
  // 别再好心加回来。
};

const clock = {
  fontSize: "31px",
  fontWeight: "600",
  letterSpacing: "-1px",
  fontVariantNumeric: "tabular-nums",
  lineHeight: "1.1",
};

const week = {
  fontSize: "22px",
  fontWeight: "600",
  letterSpacing: "-0.5px",
  fontVariantNumeric: "tabular-nums",
};

const num = { fontSize: "12px", fontWeight: "600", fontVariantNumeric: "tabular-nums" };

const dot = {
  width: "7px",
  height: "7px",
  borderRadius: "50%",
  display: "inline-block",
  flex: "none",
};

const btn = {
  flex: "1",
  border: "none",
  borderRadius: "7px",
  padding: "6px 0",
  fontSize: "12px",
  fontWeight: "500",
  color: "#fff",
  cursor: "pointer",
};

const pauseBtn = {
  marginLeft: "auto",
  border: "1px solid #3a3f52",
  background: "transparent",
  color: "#a0a6bc",
  borderRadius: "6px",
  padding: "3px 10px",
  fontSize: "11.5px",
  cursor: "pointer",
};

const hr = { height: "1px", background: "rgba(255,255,255,0.08)", margin: "10px 0" };

// 位置
//
// 直接按住卡片拖就行，松手会自动存下来，下次打开还在原地（坐标存在本地服务的
// settings 表里，见 worktime_core.set_widget_pos）。
//
// 下面这段 CSS 只是**还没拖过时**的初始位置。想改初始位置改这两行就行，横竖各
// 给一个值。改完重跑 uebersicht/install.sh（Übersicht 会热加载，不用重启）。
//
export const className = `
  top: 44px;
  right: 24px;

  font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", system-ui, sans-serif;
`;
