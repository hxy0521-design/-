#!/usr/bin/env python3
"""工时记录 · 数据层与业务逻辑。

CLI、Flask 服务、桌面摆件都调这里，保证只有一套规则。
数据存本地 SQLite（WAL 模式），多进程同时读写没问题。

时间一律用 Mac 本地时间存 'YYYY-MM-DD HH:MM:SS'，不做 UTC 转换——
这是个个人工时本，不是分布式系统，本地时间可读性更重要。
"""

import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import date as _date, datetime, time as _time, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("WORKTIME_DB", BASE_DIR / "data" / "worktime.db"))

TS_FMT = "%Y-%m-%d %H:%M:%S"

# ---------------------------------------------------------------- 类别定义

CATEGORIES = {
    "prep": {"label": "备课", "color": "#38bdf8"},
    "ops":  {"label": "运营", "color": "#fb923c"},
    "cls":  {"label": "上课", "color": "#7c6ff7"},
}
DEFAULT_CATEGORY = "prep"

WEEKDAY_CN = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def cat_label(cat: str) -> str:
    return CATEGORIES.get(cat, {}).get("label", cat)


def week_start_choices():
    """给前端下拉用：1=周一 … 7=周日。"""
    return [{"value": i, "label": WEEKDAY_CN[i - 1]} for i in range(1, 8)]


# ---------------------------------------------------------------- 时间工具


def now() -> datetime:
    """取当前时间。集中一处，方便测试替换。"""
    return datetime.now()


def fmt_ts(dt: datetime) -> str:
    return dt.strftime(TS_FMT)


def parse_ts(s: str) -> datetime:
    s = (s or "").strip()
    for f in (TS_FMT, "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M"):
        try:
            return datetime.strptime(s, f)
        except ValueError:
            continue
    raise ValueError(f"时间格式不对：{s!r}（应为 YYYY-MM-DD HH:MM）")


def fmt_hm(seconds: float) -> str:
    """时:分，永不显示秒。负数/空值当 0。用于菜单栏、摆件等紧凑位置。"""
    seconds = max(0, int(seconds or 0))
    h, m = divmod(seconds // 60, 60)
    return f"{h}:{m:02d}"


def fmt_cn(seconds: float) -> str:
    """人类可读：'3小时05分' / '45分'。用于网页。"""
    seconds = max(0, int(seconds or 0))
    h, m = divmod(seconds // 60, 60)
    if h and m:
        return f"{h}小时{m:02d}分"
    if h:
        return f"{h}小时"
    return f"{m}分"


def week_start_for(t: datetime, start_day: int, start_hour: int = 0) -> datetime:
    """t 所属工作周的起点。

    一周的边界发生在「每周 start_day 的 start_hour 点整」。往前找最近的那个边界。
    比如 start_day=2(周二)、start_hour=0：周二 00:00 之前的时间属于上一周。
    """
    start_day = int(start_day)
    start_hour = int(start_hour)
    back = (t.isoweekday() - start_day) % 7
    cand = datetime(t.year, t.month, t.day, start_hour) - timedelta(days=back)
    if cand > t:
        cand -= timedelta(days=7)
    return cand


def week_label(start: datetime, end: datetime) -> str:
    """'9/8 周二 – 9/14 周一'（end 为开区间，展示时减一天）。"""
    last = end - timedelta(days=1)
    return (f"{start.month}/{start.day} {WEEKDAY_CN[start.isoweekday() - 1]}"
            f" – "
            f"{last.month}/{last.day} {WEEKDAY_CN[last.isoweekday() - 1]}")


def day_label(d: _date) -> str:
    return f"{d.month}月{d.day}日 {WEEKDAY_CN[d.isoweekday() - 1]}"


def split_by_day(s_start: datetime, s_end: datetime,
                 w_start: datetime = None, w_end: datetime = None):
    """把一段记录按自然日切开，跨零点的自动拆到两天。

    返回 [(date, seg_start, seg_end)]。w_start/w_end 给定时先裁到窗口内。
    """
    if w_start is not None:
        s_start = max(s_start, w_start)
    if w_end is not None:
        s_end = min(s_end, w_end)
    if s_end <= s_start:
        return []

    segs = []
    cur = s_start
    while cur < s_end:
        nxt_midnight = datetime.combine(cur.date() + timedelta(days=1), _time.min)
        seg_end = min(nxt_midnight, s_end)
        segs.append((cur.date(), cur, seg_end))
        cur = seg_end
    return segs


# ---------------------------------------------------------------- 数据库


_local = threading.local()


def get_conn() -> sqlite3.Connection:
    """每线程一个连接。WAL + busy_timeout：CLI / 服务 / 摆件三方并发写入也不会报 locked。

    建表挂在连接创建时做，这样任何入口（含 add/edit/delete）都不用自己记得初始化。
    """
    conn = getattr(_local, "conn", None)
    if conn is None:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(DB_PATH), timeout=5.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA synchronous=NORMAL")
        _ensure_schema(conn)
        _local.conn = conn
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS sessions (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            category   TEXT NOT NULL,
            start_ts   TEXT NOT NULL,
            end_ts     TEXT,
            note       TEXT NOT NULL DEFAULT '',
            created_at TEXT,
            updated_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_sessions_start ON sessions(start_ts);
        CREATE INDEX IF NOT EXISTS idx_sessions_end   ON sessions(end_ts);

        CREATE TABLE IF NOT EXISTS settings (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
    """)
    conn.commit()
    # 防御：正常情况下不存在，万一异常退出留下多条在跑的记录，保留最新一条，其余按零时长收尾
    rows = conn.execute(
        "SELECT id FROM sessions WHERE end_ts IS NULL ORDER BY start_ts DESC"
    ).fetchall()
    if len(rows) > 1:
        stale = [r["id"] for r in rows[1:]]
        conn.executemany(
            "UPDATE sessions SET end_ts = start_ts, updated_at = ? WHERE id = ?",
            [(fmt_ts(now()), i) for i in stale],
        )
        conn.commit()


@contextmanager
def tx():
    """写事务。SQLite 默认的隐式事务边界容易漏 commit，统一走这里。"""
    conn = get_conn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def init_db():
    """确保库和表都在。幂等，随便调。"""
    get_conn()


# ---------------------------------------------------------------- 设置


DEFAULTS = {
    "week_start_day": "2",   # 周二。用户确认的默认值
    "week_start_hour": "0",
}


def get_setting(key: str) -> str:
    init_db()
    row = get_conn().execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    if row is None:
        return DEFAULTS.get(key, "")
    return row["value"]


def set_setting(key: str, value: str) -> None:
    with tx() as conn:
        conn.execute(
            "INSERT INTO settings(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, str(value)),
        )


def get_week_config() -> dict:
    day = int(get_setting("week_start_day") or 2)
    hour = int(get_setting("week_start_hour") or 0)
    if not 1 <= day <= 7:
        day = 2
    if not 0 <= hour <= 23:
        hour = 0
    return {"week_start_day": day, "week_start_hour": hour}


def set_week_config(day: int, hour: int = 0) -> dict:
    day, hour = int(day), int(hour)
    if not 1 <= day <= 7:
        raise ValueError("一周起始日必须是 1（周一）到 7（周日）")
    if not 0 <= hour <= 23:
        raise ValueError("起始时刻必须是 0 到 23")
    set_setting("week_start_day", str(day))
    set_setting("week_start_hour", str(hour))
    return get_week_config()


# ---------------------------------------------------------------- 摆件位置
#
# Übersicht 1.6 本身没有「拖动摆放」这回事（它的摆件菜单里「Edit...」是用编辑器
# 打开源码）。所以拖动是摆件自己做的：按住拖，松手把坐标 POST 过来存这儿，
# 下次打开照着摆。
#
# 存的是「距屏幕左上角多少像素」，不是 right/bottom——右边和下边会随屏幕宽度
# 漂移，换算成左上角原点就稳定了。还没拖过时返回 None，摆件用它自带的默认位置。


def get_widget_pos() -> dict | None:
    top, left = get_setting("widget_top"), get_setting("widget_left")
    if not top or not left:          # 还没拖过（"0" 是真值，只有空串算没设过）
        return None
    try:
        return {"top": float(top), "left": float(left)}
    except ValueError:
        return None


def set_widget_pos(top: float, left: float) -> dict:
    top, left = float(top), float(left)
    # 兜个底，别让摆件被拖到屏幕外面再也抓不回来
    top = max(0.0, min(top, 5000.0))
    left = max(0.0, min(left, 8000.0))
    set_setting("widget_top", f"{top:.0f}")
    set_setting("widget_left", f"{left:.0f}")
    return {"top": top, "left": left}


# ---------------------------------------------------------------- 读写记录


def _row_to_dict(r: sqlite3.Row) -> dict:
    d = dict(r)
    d["label"] = cat_label(d["category"])
    d["color"] = CATEGORIES.get(d["category"], {}).get("color", "#888")
    start = parse_ts(d["start_ts"])
    end = parse_ts(d["end_ts"]) if d["end_ts"] else None
    d["start"] = start.strftime("%H:%M")
    d["end"] = end.strftime("%H:%M") if end else None
    d["date"] = start.strftime("%Y-%m-%d")
    d["running"] = end is None
    d["seconds"] = int((end - start).total_seconds()) if end else int((now() - start).total_seconds())
    d["duration_hm"] = fmt_hm(d["seconds"])
    d["duration_cn"] = fmt_cn(d["seconds"])
    d["crosses_midnight"] = bool(end and end.date() != start.date())
    return d


def running_session():
    row = get_conn().execute(
        "SELECT * FROM sessions WHERE end_ts IS NULL ORDER BY start_ts DESC LIMIT 1"
    ).fetchone()
    return _row_to_dict(row) if row else None


def start(category: str, note: str = "") -> dict:
    """开始记录。会自动结束正在跑的那一条——同一时刻只算一件事，不丢时长。

    但**要开的就是正在跑的那一类时，什么都不做**。原来的写法是无条件先
    pause() 再插一条新的，于是同一类别点两下会把一条连续记录从中间劈成两条：
    时长不丢，可「已 X 分」会从 0 重新数，看着像被清零了。
    菜单、网页、摆件、解锁弹窗都走这个函数，所以在这里挡一次就全都对了。

    `already_running` 让调用方知道这次是不是真的开了新的。
    """
    if category not in CATEGORIES:
        raise ValueError(f"未知类别：{category!r}（可选 {'/'.join(CATEGORIES)}）")
    init_db()

    cur = running_session()
    if cur and cur["category"] == category:
        # 备注给了就顺手补上，别让显式传进来的参数被悄悄丢掉
        note = (note or "").strip()
        if note and note != cur["note"]:
            return {"started": update_session(cur["id"], note=note),
                    "auto_ended": None, "id": cur["id"], "already_running": True}
        return {"started": cur, "auto_ended": None,
                "id": cur["id"], "already_running": True}

    ended = pause(reason="switch")
    ts = fmt_ts(now())
    with tx() as conn:
        conn.execute(
            "INSERT INTO sessions(category, start_ts, end_ts, note, created_at, updated_at) "
            "VALUES(?, ?, NULL, ?, ?, ?)",
            (category, ts, (note or "").strip(), ts, ts),
        )
        new_id = conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
    return {"started": running_session(), "auto_ended": ended,
            "id": new_id, "already_running": False}


def pause(reason: str = "") -> dict | None:
    """结束正在跑的那一条。没在跑就返回 None（不算错误，幂等）。"""
    init_db()
    cur = running_session()
    if not cur:
        return None
    ts = fmt_ts(now())
    with tx() as conn:
        conn.execute(
            "UPDATE sessions SET end_ts = ?, updated_at = ? WHERE id = ? AND end_ts IS NULL",
            (ts, ts, cur["id"]),
        )
    cur["end_ts"] = ts
    cur["running"] = False
    cur["end"] = now().strftime("%H:%M")
    cur["seconds"] = int((parse_ts(ts) - parse_ts(cur["start_ts"])).total_seconds())
    cur["duration_hm"] = fmt_hm(cur["seconds"])
    cur["duration_cn"] = fmt_cn(cur["seconds"])
    if reason == "switch":
        cur["auto_ended"] = True
    return cur


def add_session(category: str, start_ts: str, end_ts: str, note: str = "") -> dict:
    """补记一段。结束早于开始视为跨零点，自动加一天。"""
    if category not in CATEGORIES:
        raise ValueError(f"未知类别：{category!r}")
    s, e = parse_ts(start_ts), parse_ts(end_ts)
    if e == s:
        raise ValueError("开始和结束时间不能相同")
    if e < s:
        e += timedelta(days=1)
    ts = fmt_ts(now())
    with tx() as conn:
        cur = conn.execute(
            "INSERT INTO sessions(category, start_ts, end_ts, note, created_at, updated_at) "
            "VALUES(?, ?, ?, ?, ?, ?)",
            (category, fmt_ts(s), fmt_ts(e), (note or "").strip(), ts, ts),
        )
        new_id = cur.lastrowid
    return get_session(new_id)


def update_session(session_id: int, **fields) -> dict:
    """改已有记录。允许改的字段：category / start_ts / end_ts / note。"""
    cur = get_session(session_id)
    if not cur:
        raise ValueError(f"记录不存在：{session_id}")

    cat = fields.get("category", cur["category"])
    if cat not in CATEGORIES:
        raise ValueError(f"未知类别：{cat!r}")

    s_raw = fields.get("start_ts", cur["start_ts"])
    s = parse_ts(s_raw)

    # end_ts 有三种情况，别混：
    #   没传        → 保持原样（可能在计时，那 end_ts 本来就是 None）
    #   传 None / '' → 明确清空，变回「正在计时」
    #   传时间       → 改成那个时间
    # 早先这里用了 fields.get("end_ts", cur["end_ts"])，赶上正在计时的记录时
    # 拿到的是 None，一进 parse_ts 就报「时间格式不对」——补记改开始时间必踩。
    e_raw = fields["end_ts"] if "end_ts" in fields else cur["end_ts"]
    if not e_raw:
        e = None
    else:
        e = parse_ts(e_raw)
        if e == s:
            raise ValueError("开始和结束时间不能相同")
        if e < s:
            e += timedelta(days=1)

    note = fields.get("note", cur["note"])

    with tx() as conn:
        conn.execute(
            "UPDATE sessions SET category = ?, start_ts = ?, end_ts = ?, note = ?, updated_at = ? "
            "WHERE id = ?",
            (cat, fmt_ts(s), fmt_ts(e) if e else None, (note or "").strip(),
             fmt_ts(now()), session_id),
        )
    return get_session(session_id)


def delete_session(session_id: int) -> bool:
    with tx() as conn:
        cur = conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
    return cur.rowcount > 0


def get_session(session_id: int):
    row = get_conn().execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
    return _row_to_dict(row) if row else None


def sessions_in_range(w_start: datetime, w_end: datetime, include_running=True):
    """所有与窗口有交集的记录（含跨进窗口的和仍在跑的），按开始时间排序。"""
    init_db()
    now_ts = fmt_ts(now())
    rows = get_conn().execute(
        "SELECT * FROM sessions "
        "WHERE start_ts < ? AND (end_ts IS NULL OR end_ts > ?) "
        "ORDER BY start_ts",
        (fmt_ts(w_end), fmt_ts(w_start)),
    ).fetchall()
    out = []
    for r in rows:
        d = _row_to_dict(r)
        if d["running"] and not include_running:
            continue
        out.append(d)
    return out


# ---------------------------------------------------------------- 统计


def _totals_from_sessions(sessions, w_start: datetime, w_end: datetime) -> dict:
    """把记录按落进窗口的实际秒数累加。跨零点的记录在这里被自然拆开。"""
    totals = {c: 0 for c in CATEGORIES}
    for s in sessions:
        s_start = parse_ts(s["start_ts"])
        s_end = parse_ts(s["end_ts"]) if s["end_ts"] else now()
        for _d, seg_s, seg_e in split_by_day(s_start, s_end, w_start, w_end):
            totals[s["category"]] = totals.get(s["category"], 0) + int((seg_e - seg_s).total_seconds())
    totals["total"] = sum(v for k, v in totals.items() if k in CATEGORIES)
    return totals


def week_bounds(t: datetime = None, offset: int = 0):
    """offset=0 本周，-1 上周，1 下周。返回 (start, end) 开区间。"""
    cfg = get_week_config()
    t = t or now()
    start = week_start_for(t, cfg["week_start_day"], cfg["week_start_hour"])
    start += timedelta(days=7 * offset)
    return start, start + timedelta(days=7)


def day_bounds(d: _date = None):
    d = d or now().date()
    return datetime.combine(d, _time.min), datetime.combine(d, _time.min) + timedelta(days=1)


def totals_between(w_start: datetime, w_end: datetime) -> dict:
    return _totals_from_sessions(sessions_in_range(w_start, w_end), w_start, w_end)


def status() -> dict:
    """菜单栏 / 摆件 / 网页顶部都吃这一份。"""
    init_db()
    cfg = get_week_config()
    t = now()
    w_start, w_end = week_bounds(t)
    week_sessions = sessions_in_range(w_start, w_end)
    week_totals = _totals_from_sessions(week_sessions, w_start, w_end)

    d_start, d_end = day_bounds(t.date())
    today_totals = totals_between(d_start, d_end)

    run = running_session()
    return {
        "now": fmt_ts(t),
        "running": run,
        "week": {
            "start": fmt_ts(w_start),
            "end": fmt_ts(w_end),
            "label": week_label(w_start, w_end),
        },
        "week_totals": week_totals,
        "week_totals_hm": {k: fmt_hm(v) for k, v in week_totals.items()},
        "today_totals": today_totals,
        "today_totals_hm": {k: fmt_hm(v) for k, v in today_totals.items()},
        **cfg,
        "categories": [
            {"key": k, "label": v["label"], "color": v["color"]} for k, v in CATEGORIES.items()
        ],
        "widget_pos": get_widget_pos(),
        "db_path": str(DB_PATH),
    }


def daily_report(from_date: _date, to_date: _date) -> dict:
    """按天回看。from_date / to_date 都含当天。"""
    w_start = datetime.combine(from_date, _time.min)
    w_end = datetime.combine(to_date + timedelta(days=1), _time.min)
    sessions = sessions_in_range(w_start, w_end)

    # 先按「记录」铺开成「按天的片段」，再按天归拢
    by_day: dict[_date, list] = {}
    for s in sessions:
        s_start = parse_ts(s["start_ts"])
        s_end = parse_ts(s["end_ts"]) if s["end_ts"] else now()
        for d, seg_s, seg_e in split_by_day(s_start, s_end, w_start, w_end):
            by_day.setdefault(d, []).append({
                **s,
                "seg_start": seg_s.strftime("%H:%M"),
                "seg_end": seg_e.strftime("%H:%M") if not s["running"] else None,
                "seg_seconds": int((seg_e - seg_s).total_seconds()),
                "seg_hm": fmt_hm((seg_e - seg_s).total_seconds()),
                "seg_cn": fmt_cn((seg_e - seg_s).total_seconds()),
                # 跨零点被拆开的片段标记出来，网页上提示「接上一日」
                "continued": seg_s.time() != _time.min and d != s_start.date(),
            })

    days = []
    for d in sorted(by_day, reverse=True):
        items = sorted(by_day[d], key=lambda x: x["seg_start"])
        tot = sum(i["seg_seconds"] for i in items)
        per_cat = {c: 0 for c in CATEGORIES}
        for i in items:
            per_cat[i["category"]] = per_cat.get(i["category"], 0) + i["seg_seconds"]
        days.append({
            "date": d.strftime("%Y-%m-%d"),
            "label": day_label(d),
            "total_seconds": tot,
            "total_hm": fmt_hm(tot),
            "total_cn": fmt_cn(tot),
            "by_category": per_cat,
            "by_category_hm": {k: fmt_hm(v) for k, v in per_cat.items()},
            "sessions": items,
        })

    grand = sum(d["total_seconds"] for d in days)
    return {
        "from": from_date.strftime("%Y-%m-%d"),
        "to": to_date.strftime("%Y-%m-%d"),
        "days": days,
        "total_seconds": grand,
        "total_hm": fmt_hm(grand),
        "total_cn": fmt_cn(grand),
    }


def export_rows(from_date: _date, to_date: _date):
    """CSV 导出的原始行（按记录，不拆天——跨零点的原样一行，更接近真实流水）。"""
    w_start = datetime.combine(from_date, _time.min)
    w_end = datetime.combine(to_date + timedelta(days=1), _time.min)
    rows = []
    for s in sessions_in_range(w_start, w_end):
        rows.append([
            s["date"],
            s["start"],
            s["end"] or "计时中",
            s["duration_cn"] if not s["running"] else "—",
            s["label"],
            s["note"],
            f"{s['seconds'] / 3600:.2f}" if not s["running"] else "",
        ])
    return rows
