#!/usr/bin/env python3
"""工时记录 · 命令行入口。

菜单栏 App 靠调它工作（`status --json` 拿状态，`start`/`pause` 做动作），
也可以自己在终端里用。

    python3 worktime.py start cls --note "探索4班"
    python3 worktime.py pause
    python3 worktime.py status --json
    python3 worktime.py today
    python3 worktime.py week --offset -1
    python3 worktime.py report --from 2026-09-01 --to 2026-09-14
    python3 worktime.py export --from 2026-09-01 --to 2026-09-14 --csv > 工时.csv
"""

import argparse
import csv
import io
import json
import sys
from datetime import date, datetime, timedelta

import worktime_core as core

CAT_KEYS = list(core.CATEGORIES)
CAT_HINT = " / ".join(f"{k}={v['label']}" for k, v in core.CATEGORIES.items())


def _parse_date(s: str) -> date:
    s = (s or "").strip()
    for f in ("%Y-%m-%d", "%Y/%m/%d", "%m-%d", "%m/%d"):
        try:
            d = datetime.strptime(s, f).date()
            if f in ("%m-%d", "%m/%d"):
                d = d.replace(year=date.today().year)
            return d
        except ValueError:
            continue
    raise argparse.ArgumentTypeError(f"日期格式不对：{s!r}（应为 2026-09-01 或 09-01）")


# ---------------------------------------------------------------- 输出helpers


def _totals_line(totals: dict, hm: dict) -> str:
    parts = [f"{core.CATEGORIES[c]['label']} {hm.get(c, '0:00')}" for c in CAT_KEYS]
    return "  ".join(parts) + f"   |   合计 {hm.get('total', '0:00')}"


def cmd_start(args):
    res = core.start(args.category, note=args.note or "")
    if res.get("already_running"):
        s = res["started"]
        print(f"⏱ 已经在记录「{s['label']}」了（{s['start']} 开始），没有重开。")
        return 0
    prev = res["auto_ended"]
    if prev:
        print(f"已结束「{prev['label']}」{prev['duration_hm']}，自动切换。")
    s = res["started"]
    print(f"▶ 开始记录「{s['label']}」 {s['start']}"
          + (f"  备注：{s['note']}" if s["note"] else ""))
    return 0


def cmd_pause(args):
    ended = core.pause()
    if not ended:
        print("当前没有在计时的记录。")
        return 0
    print(f"⏸ 已暂停「{ended['label']}」 {ended['start']}–{ended['end']}  "
          f"共 {ended['duration_cn']}")
    return 0


def _print_status(st: dict):
    run = st["running"]
    if run:
        print(f"⏱ 正在记录：{run['label']}  已 {run['duration_cn']}  （{run['start']} 开始）")
    else:
        print("⏱ 当前没有在计时")
    print(f"本周（{st['week']['label']}）：{_totals_line(st['week_totals'], st['week_totals_hm'])}")
    print(f"今日：{_totals_line(st['today_totals'], st['today_totals_hm'])}")


def cmd_status(args):
    st = core.status()
    if args.json:
        print(json.dumps(st, ensure_ascii=False))
    else:
        _print_status(st)
    return 0


def cmd_today(args):
    d = core.now().date() if not args.date else _parse_date(args.date)
    rep = core.daily_report(d, d)
    if not rep["days"]:
        print(f"{core.day_label(d)}：没有记录")
        return 0
    day = rep["days"][0]
    print(f"{day['label']}   合计 {day['total_cn']}")
    print("-" * 52)
    for s in day["sessions"]:
        end = s["seg_end"] or "计时中"
        note = f"   {s['note']}" if s["note"] else ""
        cont = "  (接上一日)" if s.get("continued") else ""
        print(f"  {s['label']}   {s['seg_start']}–{end}   {s['seg_cn']}{cont}{note}")
    print("-" * 52)
    print("  " + "  ".join(
        f"{core.CATEGORIES[c]['label']} {day['by_category_hm'].get(c, '0:00')}" for c in CAT_KEYS
    ))
    return 0


def cmd_week(args):
    w_start, w_end = core.week_bounds(offset=args.offset)
    rep = core.daily_report(w_start.date(), (w_end - timedelta(days=1)).date())
    print(f"本周 {core.week_label(w_start, w_end)}   "
          f"合计 {rep['total_cn']}（{rep['total_hm']}）")
    print("=" * 52)
    if not rep["days"]:
        print("  本周还没有记录")
    for day in rep["days"]:
        print(f"\n{day['label']}   合计 {day['total_cn']}")
        for s in day["sessions"]:
            end = s["seg_end"] or "计时中"
            note = f"   {s['note']}" if s["note"] else ""
            cont = "  (接上一日)" if s.get("continued") else ""
            print(f"    {s['label']}   {s['seg_start']}–{end}   {s['seg_cn']}{cont}{note}")
    print("\n" + "=" * 52)
    tot = core.totals_between(w_start, w_end)
    print("  " + "  ".join(
        f"{core.CATEGORIES[c]['label']} {core.fmt_cn(tot[c])}" for c in CAT_KEYS
    ) + f"   总计 {core.fmt_cn(tot['total'])}")
    return 0


def cmd_report(args):
    f = _parse_date(args.from_) if args.from_ else core.now().date() - timedelta(days=13)
    t = _parse_date(args.to) if args.to else core.now().date()
    if f > t:
        f, t = t, f
    rep = core.daily_report(f, t)
    print(f"{rep['from']} ~ {rep['to']}   合计 {rep['total_cn']}（{rep['total_hm']}）")
    print("=" * 52)
    if not rep["days"]:
        print("  该区间没有记录")
    for day in rep["days"]:
        cats = "  ".join(
            f"{core.CATEGORIES[c]['label']} {day['by_category_hm'].get(c, '0:00')}"
            for c in CAT_KEYS if day["by_category"].get(c)
        )
        print(f"\n{day['label']}   合计 {day['total_cn']}   {cats}")
        for s in day["sessions"]:
            end = s["seg_end"] or "计时中"
            note = f"   {s['note']}" if s["note"] else ""
            cont = "  (接上一日)" if s.get("continued") else ""
            print(f"    {s['label']}   {s['seg_start']}–{end}   {s['seg_cn']}{cont}{note}")
    return 0


def cmd_export(args):
    f = _parse_date(args.from_) if args.from_ else core.now().date() - timedelta(days=30)
    t = _parse_date(args.to) if args.to else core.now().date()
    rows = core.export_rows(f, t)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["日期", "开始", "结束", "时长", "类别", "备注", "小时数"])
    w.writerows(rows)
    # BOM：Excel 打开中文 CSV 不乱码
    print("﻿" + buf.getvalue(), end="")
    return 0


def cmd_add(args):
    date_s = args.date or core.now().strftime("%Y-%m-%d")
    s = core.add_session(args.category, f"{date_s} {args.start}", f"{date_s} {args.end}",
                         note=args.note or "")
    print(f"已补记「{s['label']}」{s['date']} {s['start']}–{s['end']}  {s['duration_cn']}")
    return 0


def cmd_edit(args):
    fields = {}
    if args.category:
        fields["category"] = args.category
    if args.start:
        d = args.date or core.get_session(args.id)["date"]
        fields["start_ts"] = f"{d} {args.start}"
    if args.end:
        s = core.get_session(args.id)
        d = args.date or s["date"]
        fields["end_ts"] = f"{d} {args.end}"
    if args.note is not None:
        fields["note"] = args.note
    if not fields:
        print("没给任何要改的内容。", file=sys.stderr)
        return 2
    s = core.update_session(args.id, **fields)
    print(f"已更新 #{s['id']}：{s['label']} {s['date']} {s['start']}–{s['end'] or '计时中'}"
          f"  {s['duration_cn']}")
    return 0


def cmd_delete(args):
    if core.delete_session(args.id):
        print(f"已删除 #{args.id}")
        return 0
    print(f"记录不存在：{args.id}", file=sys.stderr)
    return 1


def cmd_config(args):
    if args.day is None and args.hour is None:
        cfg = core.get_week_config()
        print(f"一周起点：{core.WEEKDAY_CN[cfg['week_start_day'] - 1]} "
              f"{cfg['week_start_hour']:02d}:00")
        return 0
    cur = core.get_week_config()
    cfg = core.set_week_config(
        args.day if args.day is not None else cur["week_start_day"],
        args.hour if args.hour is not None else cur["week_start_hour"],
    )
    print(f"已改为：一周从{core.WEEKDAY_CN[cfg['week_start_day'] - 1]} "
          f"{cfg['week_start_hour']:02d}:00 开始。历史统计已按新周期重算。")
    return 0


def cmd_list(args):
    f = _parse_date(args.from_) if args.from_ else core.now().date() - timedelta(days=6)
    t = _parse_date(args.to) if args.to else core.now().date()
    rep = core.daily_report(f, t)
    for day in rep["days"]:
        for s in day["sessions"]:
            end = s["seg_end"] or "计时中"
            print(f"#{s['id']:<5} {s['date']}  {s['seg_start']}–{end:<8} "
                  f"{s['label']}  {s['seg_cn']}{'  ' + s['note'] if s['note'] else ''}")
    return 0


# ---------------------------------------------------------------- 参数


def build_parser():
    p = argparse.ArgumentParser(
        prog="worktime", description="工时记录（备课 / 运营 / 上课）",
        formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__,
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("start",
                        help="开始记录某个类别（会自动结束正在跑的那个；"
                             "要开的就是正在跑的那个则什么都不做）")
    sp.add_argument("category", choices=CAT_KEYS, help=CAT_HINT)
    sp.add_argument("--note", default="", help="备注，比如班级名")
    sp.set_defaults(func=cmd_start)

    sub.add_parser("pause", help="暂停记录").set_defaults(func=cmd_pause)

    sp = sub.add_parser("status", help="当前状态")
    sp.add_argument("--json", action="store_true", help="输出 JSON（菜单栏用）")
    sp.set_defaults(func=cmd_status)

    sp = sub.add_parser("today", help="今天的明细")
    sp.add_argument("--date", help="指定日期，默认今天")
    sp.set_defaults(func=cmd_today)

    sp = sub.add_parser("week", help="本周明细（按当前周期设置）")
    sp.add_argument("--offset", type=int, default=0, help="0=本周，-1=上周，1=下周")
    sp.set_defaults(func=cmd_week)

    sp = sub.add_parser("report", help="任意区间的明细")
    sp.add_argument("--from", dest="from_", help="起始日期")
    sp.add_argument("--to", help="结束日期")
    sp.set_defaults(func=cmd_report)

    sp = sub.add_parser("export", help="导出 CSV")
    sp.add_argument("--from", dest="from_", help="起始日期")
    sp.add_argument("--to", help="结束日期")
    sp.add_argument("--csv", action="store_true", help="（默认就是 CSV，加不加都行）")
    sp.set_defaults(func=cmd_export)

    sp = sub.add_parser("add", help="补记一段")
    sp.add_argument("category", choices=CAT_KEYS, help=CAT_HINT)
    sp.add_argument("--date", help="日期，默认今天")
    sp.add_argument("--start", required=True, help="开始时间 HH:MM")
    sp.add_argument("--end", required=True, help="结束时间 HH:MM（早于开始则算跨天）")
    sp.add_argument("--note", default="")
    sp.set_defaults(func=cmd_add)

    sp = sub.add_parser("list", help="列出记录（带 id，方便改删）")
    sp.add_argument("--from", dest="from_")
    sp.add_argument("--to")
    sp.set_defaults(func=cmd_list)

    sp = sub.add_parser("edit", help="修改一条记录")
    sp.add_argument("id", type=int)
    sp.add_argument("--date")
    sp.add_argument("--start", help="HH:MM")
    sp.add_argument("--end", help="HH:MM")
    sp.add_argument("--category", choices=CAT_KEYS)
    sp.add_argument("--note")
    sp.set_defaults(func=cmd_edit)

    sp = sub.add_parser("delete", help="删除一条记录")
    sp.add_argument("id", type=int)
    sp.set_defaults(func=cmd_delete)

    sp = sub.add_parser("config", help="查看/设置一周从哪天开始")
    sp.add_argument("--day", type=int, choices=range(1, 8),
                    help="1=周一 … 7=周日（默认周二）")
    sp.add_argument("--hour", type=int, choices=range(0, 24), help="一周从几点起算，默认 0")
    sp.set_defaults(func=cmd_config)

    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except ValueError as e:
        print(f"错误：{e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
