#!/usr/bin/env python3
"""工时记录 · 本地服务（127.0.0.1:5899）。

只监听本机，不对外。网页回看页和 Übersicht 桌面摆件都连这里。
菜单栏 App 不依赖它——它直接调 CLI，这样即使服务挂了也能随手记工时。

    python3 worktime_server.py
"""

import os
import sys
from datetime import date, datetime, timedelta

from flask import Flask, jsonify, request, send_from_directory

import worktime_core as core

BASE_DIR = core.BASE_DIR
STATIC_DIR = BASE_DIR / "static"
_PORT = int(os.environ.get("WORKTIME_PORT", "5899"))

app = Flask(__name__, static_folder=str(STATIC_DIR))
app.json.sort_keys = False


# ---------------------------------------------------------------- 工具


def _parse_date(s, default=None):
    if not s:
        return default
    s = str(s).strip()
    for f in ("%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, f).date()
        except ValueError:
            continue
    raise ValueError(f"日期格式不对：{s!r}")


def ok(**payload):
    return jsonify({"status": "ok", **payload})


def err(message, code=400):
    return jsonify({"status": "error", "message": message}), code


@app.errorhandler(ValueError)
def _on_value_error(e):
    return err(str(e), 400)


# ---------------------------------------------------------------- 跨域
#
# 桌面摆件跑在 Übersicht 的 WebView 里，页面来源是它自己起的
# http://127.0.0.1:<随机端口>，跟本服务不同端口，属于跨域。
#
# 只放行 127.0.0.1 / localhost 的来源——外网站的 Origin 不会匹配，
# 所以别的网页没法从浏览器里遥控你的计时器。


def _origin_allowed(origin: str) -> bool:
    return (origin.startswith("http://127.0.0.1:")
            or origin.startswith("http://localhost:"))


@app.before_request
def _handle_preflight():
    if request.method == "OPTIONS":
        return ("", 204)


@app.after_request
def _add_cors(resp):
    origin = request.headers.get("Origin", "")
    if _origin_allowed(origin):
        resp.headers["Access-Control-Allow-Origin"] = origin
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
        resp.headers["Access-Control-Max-Age"] = "600"
    return resp


# ---------------------------------------------------------------- 页面


@app.route("/")
def index():
    return send_from_directory(str(STATIC_DIR), "worktime.html")


@app.route("/static/<path:filename>")
def static_files(filename):
    return send_from_directory(str(STATIC_DIR), filename)


# ---------------------------------------------------------------- 读


@app.route("/api/status")
def api_status():
    st = core.status()
    return ok(**st)


@app.route("/api/categories")
def api_categories():
    return ok(categories=[
        {"key": k, "label": v["label"], "color": v["color"]}
        for k, v in core.CATEGORIES.items()
    ])


@app.route("/api/week")
def api_week():
    """某一周的按天明细。offset=0 本周，-1 上周。"""
    offset = int(request.args.get("offset", 0))
    w_start, w_end = core.week_bounds(offset=offset)
    rep = core.daily_report(w_start.date(), (w_end - timedelta(days=1)).date())
    return ok(**rep, week={"start": core.fmt_ts(w_start),
                           "end": core.fmt_ts(w_end),
                           "label": core.week_label(w_start, w_end)})


@app.route("/api/report")
def api_report():
    f = _parse_date(request.args.get("from"), core.now().date() - timedelta(days=13))
    t = _parse_date(request.args.get("to"), core.now().date())
    if f > t:
        f, t = t, f
    return ok(**core.daily_report(f, t))


@app.route("/api/export.csv")
def api_export():
    import csv
    import io

    f = _parse_date(request.args.get("from"), core.now().date() - timedelta(days=30))
    t = _parse_date(request.args.get("to"), core.now().date())
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["日期", "开始", "结束", "时长", "类别", "备注", "小时数"])
    w.writerows(core.export_rows(f, t))
    from flask import Response

    return Response(
        "﻿" + buf.getvalue(),  # BOM，Excel 打开中文不乱码
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition":
                 f'attachment; filename="worktime_{f}_{t}.csv"'},
    )


# ---------------------------------------------------------------- 写


@app.route("/api/start", methods=["POST"])
def api_start():
    data = request.get_json(silent=True) or {}
    cat = (data.get("category") or "").strip()
    note = (data.get("note") or "").strip()
    if cat not in core.CATEGORIES:
        return err(f"未知类别：{cat!r}")
    res = core.start(cat, note=note)
    return ok(started=res["started"], auto_ended=res["auto_ended"], **core.status())


@app.route("/api/pause", methods=["POST"])
def api_pause():
    core.pause()
    return ok(**core.status())


@app.route("/api/sessions", methods=["POST"])
def api_add_session():
    """补记一段。"""
    d = request.get_json(silent=True) or {}
    cat = (d.get("category") or "").strip()
    if cat not in core.CATEGORIES:
        return err(f"未知类别：{cat!r}")
    day = (d.get("date") or core.now().strftime("%Y-%m-%d")).strip()
    start, end = (d.get("start") or "").strip(), (d.get("end") or "").strip()
    if not start or not end:
        return err("开始和结束时间都要填")
    s = core.add_session(cat, f"{day} {start}", f"{day} {end}", note=d.get("note") or "")
    return ok(session=s, **core.status())


@app.route("/api/sessions/<int:sid>", methods=["PUT"])
def api_update_session(sid):
    cur = core.get_session(sid)
    if not cur:
        return err(f"记录不存在：{sid}", 404)
    d = request.get_json(silent=True) or {}
    fields = {}
    if d.get("category"):
        fields["category"] = d["category"]
    if d.get("start"):
        fields["start_ts"] = f"{d.get('date') or cur['date']} {d['start']}"
    if d.get("end"):
        fields["end_ts"] = f"{d.get('date') or cur['date']} {d['end']}"
    if "note" in d:
        fields["note"] = d["note"]
    if not fields:
        return err("没有要修改的内容")
    s = core.update_session(sid, **fields)
    return ok(session=s, **core.status())


@app.route("/api/sessions/<int:sid>", methods=["DELETE"])
def api_delete_session(sid):
    if not core.delete_session(sid):
        return err(f"记录不存在：{sid}", 404)
    return ok(**core.status())


@app.route("/api/config", methods=["GET", "POST"])
def api_config():
    if request.method == "GET":
        cfg = core.get_week_config()
        return ok(**cfg, week_start_choices=core.week_start_choices(),
                  weekdays=core.WEEKDAY_CN)
    d = request.get_json(silent=True) or {}
    cur = core.get_week_config()
    core.set_week_config(
        d.get("week_start_day", cur["week_start_day"]),
        d.get("week_start_hour", cur["week_start_hour"]),
    )
    # status() 里已经带了 week_start_day / week_start_hour，不用再单独塞
    return ok(**core.status())


@app.route("/api/widget_pos", methods=["POST"])
def api_widget_pos():
    """桌面摆件拖完把坐标存这儿；下次打开照着摆。"""
    d = request.get_json(silent=True) or {}
    if d.get("top") is None or d.get("left") is None:
        return err("top 和 left 都要给")
    return ok(widget_pos=core.set_widget_pos(d["top"], d["left"]))


# ---------------------------------------------------------------- 入口


def main():
    core.init_db()
    print(f"工时记录服务 · http://127.0.0.1:{_PORT}")
    print(f"数据库：{core.DB_PATH}")
    app.run(host="127.0.0.1", port=_PORT, debug=False, threaded=True)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
