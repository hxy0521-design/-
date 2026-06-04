"""TiDB Cloud data layer — shared between 欣欣 and 饼干"""
import os, json, pymysql, threading

TIDB_HOST = os.environ.get("TIDB_HOST", "gateway01.ap-southeast-1.prod.alicloud.tidbcloud.com")
TIDB_PORT = int(os.environ.get("TIDB_PORT", "4000"))
TIDB_USER = os.environ.get("TIDB_USER", "34ipvAFzinPcerR.root")
TIDB_PASS = os.environ.get("TIDB_PASS", "CphkRDoBKvwA2OEY")
TIDB_DB = os.environ.get("TIDB_DB", "test")

_local = threading.local()

def get_db():
    if not hasattr(_local, "conn") or _local.conn is None:
        _local.conn = pymysql.connect(
            host=TIDB_HOST, port=TIDB_PORT, user=TIDB_USER, password=TIDB_PASS,
            database=TIDB_DB, autocommit=True, connect_timeout=10,
            ssl_verify_cert=False, charset='utf8mb4'
        )
    return _local.conn

class Row:
    def __init__(self, cols, values):
        self._cols = cols
        self._vals = values
    def __getitem__(self, key):
        if isinstance(key, int): return self._vals[key]
        return self._vals[self._cols.index(key)] if key in self._cols else None
    def keys(self): return self._cols
    def values(self): return self._vals
    def items(self): return list(zip(self._cols, self._vals))

class Result:
    def __init__(self, cur, rows):
        cols = [d[0] for d in cur.description] if cur.description else []
        self._rows = [Row(cols, list(r)) for r in rows]
        self._cols = cols
    def fetchall(self): return self._rows
    def fetchone(self): return self._rows[0] if self._rows else None
    def __iter__(self): return iter(self._rows)

def _execute(db, sql, params=None):
    cur = db.cursor()
    if params:
        # Replace ? with %s for MySQL
        sql = sql.replace('?', '%s')
    cur.execute(sql, params or [])
    try: rows = cur.fetchall()
    except: rows = []
    return Result(cur, rows)

def init_db():
    pass  # Tables already created during migration

def migrate_from_json():
    pass

# ------- Config API -------

def config_all():
    db = get_db()
    rows = _execute(db, "SELECT class_name, unit_code, unit_name, path, created_by, class_time FROM config ORDER BY class_name").fetchall()
    cfg = {}
    for r in rows:
        if r["class_name"] not in cfg:
            cfg[r["class_name"]] = {}
        cfg[r["class_name"]][r["unit_code"]] = {
            "name": r["unit_name"], "path": r["path"],
            "created_by": r["created_by"], "class_time": r["class_time"]
        }
    return cfg

def config_update(cfg):
    db = get_db()
    _execute(db, "DELETE FROM config")
    for cls_name, units in cfg.items():
        for unit_code, info in units.items():
            _execute(db, "INSERT INTO config VALUES (%s,%s,%s,%s,%s,%s)",
                [cls_name, unit_code, info.get("name",""), info.get("path",""), info.get("created_by",""), info.get("class_time","")])

def config_add_class(cls_name, created_by="", class_time=""):
    db = get_db()
    r = _execute(db, "SELECT COUNT(*) as cnt FROM config WHERE class_name=%s AND unit_code!=%s", [cls_name, '']).fetchone()
    if r and r["cnt"] > 0: return
    _execute(db, "INSERT INTO config VALUES (%s,%s,%s,%s,%s,%s)", [cls_name, "2605", cls_name, "", created_by, class_time])

def config_remove_class(cls_name):
    _execute(get_db(), "DELETE FROM config WHERE class_name=%s", [cls_name])

def config_add_unit(cls_name, unit_code, unit_name, path, created_by=""):
    _execute(get_db(), "INSERT INTO config VALUES (%s,%s,%s,%s,%s,%s)", [cls_name, unit_code, unit_name, path, created_by, ""])

def config_remove_unit(cls_name, unit_code):
    _execute(get_db(), "DELETE FROM config WHERE class_name=%s AND unit_code=%s", [cls_name, unit_code])

def config_get_unit(cls_name, unit_code):
    r = _execute(get_db(), "SELECT unit_name, path FROM config WHERE class_name=%s AND unit_code=%s", [cls_name, unit_code]).fetchone()
    return {"name": r["unit_name"], "path": r["path"]} if r else {}

def config_update_unit_path(cls_name, unit_code, path):
    _execute(get_db(), "UPDATE config SET path=%s WHERE class_name=%s AND unit_code=%s", [path, cls_name, unit_code])

# ------- Lessons -------

def lesson_list(cls_name, unit_code):
    return lesson_list_batch().get(cls_name, {}).get(unit_code, [])

def lesson_list_batch():
    db = get_db()
    cfg = config_all()
    rows = _execute(db, "SELECT class_name, unit_code, lesson_num, title, updated_at FROM lessons ORDER BY class_name, unit_code, lesson_num").fetchall()
    result = {}
    for r in rows:
        cn, uc = r["class_name"], r["unit_code"]
        unit_name = cfg.get(cn, {}).get(uc, {}).get("name", uc)
        if cn not in result: result[cn] = {}
        if uc not in result[cn]: result[cn][uc] = []
        result[cn][uc].append({
            "folder": f"{cn}-{uc}-{r['lesson_num']}",
            "lesson": str(r["lesson_num"]),
            "title": r["title"],
            "date": (r["updated_at"] or "")[:10],
            "unit_name": unit_name
        })
    return result

def lesson_get(cls_name, unit_code, lesson_num):
    r = _execute(get_db(), "SELECT title, content FROM lessons WHERE class_name=%s AND unit_code=%s AND lesson_num=%s", [cls_name, unit_code, lesson_num]).fetchone()
    return (r["title"], r["content"]) if r else ("", "")

def lesson_save(cls_name, unit_code, lesson_num, title, content):
    from datetime import datetime
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db = get_db()
    r = _execute(db, "SELECT lesson_num FROM lessons WHERE class_name=%s AND unit_code=%s AND lesson_num=%s", [cls_name, unit_code, lesson_num]).fetchone()
    if r:
        _execute(db, "UPDATE lessons SET title=%s, content=%s, updated_at=%s WHERE class_name=%s AND unit_code=%s AND lesson_num=%s", [title, content, now, cls_name, unit_code, lesson_num])
    else:
        _execute(db, "INSERT INTO lessons VALUES (%s,%s,%s,%s,%s,%s)", [cls_name, unit_code, lesson_num, title, content, now])

# ------- Student Ext -------

def student_ext_all():
    rows = _execute(get_db(), "SELECT * FROM student_ext ORDER BY student_name").fetchall()
    cols = ["student_name","student_code","source","status","segment","enrolled_class","purchased_lessons","used_lessons","remaining_lessons","notes"]
    return [dict(zip(cols, [r[c] for c in cols])) for r in rows]

def student_ext_upsert(name, data):
    db = get_db()
    r = _execute(db, "SELECT student_name FROM student_ext WHERE student_name=%s", [name]).fetchone()
    vals = [data.get("student_code",""), data.get("source",""), data.get("status",""), data.get("segment",""), data.get("enrolled_class",""), int(data.get("purchased_lessons",0)), int(data.get("used_lessons",0)), int(data.get("remaining_lessons",0)), data.get("notes","")]
    if r:
        _execute(db, "UPDATE student_ext SET student_code=%s,source=%s,status=%s,segment=%s,enrolled_class=%s,purchased_lessons=%s,used_lessons=%s,remaining_lessons=%s,notes=%s WHERE student_name=%s", vals + [name])
    else:
        _execute(db, "INSERT INTO student_ext VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", [name] + vals)

# ------- Attendance -------

def attendance_batch(records):
    from datetime import datetime
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db = get_db()
    for r in records:
        _execute(db, "DELETE FROM attendance WHERE class_name=%s AND lesson_num=%s AND student_name=%s", [r["class_name"], r["lesson_num"], r["student_name"]])
        _execute(db, "INSERT INTO attendance (class_name,unit_code,lesson_num,lesson_title,lesson_date,student_name,status,note,recorded_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)", [r["class_name"], r.get("unit_code",""), r["lesson_num"], r.get("lesson_title",""), r.get("lesson_date",""), r["student_name"], r.get("status","出席"), r.get("note",""), now])

def attendance_get(class_name=None, date_from=None, date_to=None):
    db = get_db()
    sql = "SELECT * FROM attendance WHERE 1=1"
    params = []
    if class_name: sql += " AND class_name=%s"; params.append(class_name)
    if date_from: sql += " AND lesson_date >= %s"; params.append(date_from)
    if date_to: sql += " AND lesson_date <= %s"; params.append(date_to)
    sql += " ORDER BY lesson_date DESC, class_name, student_name"
    rows = _execute(db, sql, params).fetchall()
    cols = ["id","class_name","unit_code","lesson_num","lesson_title","lesson_date","student_name","status","note","recorded_at"]
    return [dict(zip(cols, [r[c] for c in cols])) for r in rows]

def attendance_stats(class_name=None):
    db = get_db()
    sql = "SELECT status, COUNT(*) as cnt FROM attendance WHERE 1=1"
    params = []
    if class_name: sql += " AND class_name=%s"; params.append(class_name)
    sql += " GROUP BY status"
    rows = _execute(db, sql, params).fetchall()
    return {r["status"]: r["cnt"] for r in rows}

def attendance_by_lesson(class_name=None, cycle=None, limit=50, page=1):
    db = get_db()
    base_where = "WHERE 1=1"
    w_params = []
    if class_name: base_where += " AND class_name=%s"; w_params.append(class_name)
    if cycle: base_where += " AND cycle=%s"; w_params.append(cycle)
    # Count total
    count_sql = f"SELECT COUNT(DISTINCT CONCAT(class_name,'-',lesson_title,'-',lesson_date)) as cnt FROM attendance {base_where}"
    total_row = _execute(db, count_sql, w_params).fetchone()
    total_count = int(total_row["cnt"]) if total_row else 0
    # Paginated grouped query
    offset = (page - 1) * limit
    sql = f"SELECT class_name, lesson_title, lesson_date, ANY_VALUE(cycle) as cycle, COUNT(*) as total, SUM(CASE WHEN status='出席' THEN 1 ELSE 0 END) as present FROM attendance {base_where}"
    sql += " GROUP BY class_name, lesson_title, lesson_date ORDER BY lesson_date DESC, class_name LIMIT %s OFFSET %s"
    rows = _execute(db, sql, w_params + [limit, offset]).fetchall()
    if not rows: return [], 0
    # One bulk query for all student details
    detail_sql = "SELECT class_name, lesson_title, lesson_date, student_name, status, note FROM attendance WHERE (class_name, lesson_title, lesson_date) IN ("
    detail_params = []
    for r in rows:
        detail_sql += "(%s,%s,%s),"
        detail_params.extend([r["class_name"], r["lesson_title"], r["lesson_date"]])
    detail_sql = detail_sql[:-1] + ")"
    all_students = _execute(db, detail_sql, detail_params).fetchall()
    # Group students by lesson key
    from collections import defaultdict
    student_map = defaultdict(list)
    for s in all_students:
        key = (s["class_name"], s["lesson_title"], s["lesson_date"])
        student_map[key].append(s)
    cfg = config_all()
    _DAY_MAP = {"一":"周一","二":"周二","三":"周三","四":"周四","五":"周五","六":"周六","日":"周日"}
    # Pre-load all pricing once
    price_map = {}
    for pr in _execute(db, "SELECT segment, unit_price FROM pricing WHERE course_type='正式课' AND discount_type='一课一销'").fetchall():
        price_map[pr["segment"]] = float(pr["unit_price"])
    result = []
    for r in rows:
        cn = r["class_name"]
        raw_title = r["lesson_title"] or ""
        if "," in raw_title: raw_title = raw_title.split(",")[0]
        import re
        lesson_num_match = re.search(r'-(\d+)$', raw_title)
        lesson_num = lesson_num_match.group(1) if lesson_num_match else ""
        display_title = raw_title
        cls_cfg = cfg.get(cn, {})
        unit_info = list(cls_cfg.values())[0] if cls_cfg else {}
        class_time = unit_info.get("class_time", "")
        weekday_cn = cn[1] if len(cn) > 1 else ""
        weekday = _DAY_MAP.get(weekday_cn, "")
        # Price: detect segment from class name
        seg_display = ""
        for seg, kw in [("探索段","探索"),("启航段","启航"),("先锋段","先锋"),("领航1V1","领航"),("领航1V2","领航"),("成人班","成人")]:
            if kw in cn: seg_display = seg; break
        price = price_map.get(seg_display, 0)
        total = int(r["total"] or 0)
        present = int(r["present"] or 0)
        # Get students from the bulk-loaded map
        key = (cn, r["lesson_title"], r["lesson_date"])
        students = student_map.get(key, [])
        student_names = [s["student_name"] for s in students if s["status"] == "出席"]
        # Build notes - just collect unique non-empty notes
        notes_list = list(set(str(s["note"]).strip() for s in students if s["note"] and str(s["note"]).strip() and str(s["note"]).strip() != "None"))
        leave_notes = notes_list[0] if len(notes_list) == 1 else (" | ".join(notes_list) if notes_list else "")
        lesson_revenue = present * price
        result.append({
            "class_name": cn, "lesson_title": display_title, "lesson_num": lesson_num,
            "lesson_date": r["lesson_date"], "weekday": weekday,
            "cycle": r["cycle"] or "", "segment": seg_display, "time": class_time,
            "total": total, "present": present,
            "price": price, "lesson_revenue": round(lesson_revenue, 1),
            "per_person": round(lesson_revenue / present, 1) if present > 0 else 0,
            "students": student_names, "leave_notes": leave_notes,
        })
    return result, total_count

# ------- Roster -------

def roster_get(class_name):
    rows = _execute(get_db(), "SELECT student_name FROM class_roster WHERE class_name=%s ORDER BY student_name", [class_name]).fetchall()
    return [r["student_name"] for r in rows]

def roster_set(class_name, students):
    db = get_db()
    _execute(db, "DELETE FROM class_roster WHERE class_name=%s", [class_name])
    for s in students:
        _execute(db, "INSERT INTO class_roster VALUES (%s,%s)", [class_name, s])

# ------- Purchases -------

def purchase_add(data):
    db = get_db()
    oid = data.get("order_id","")
    if oid:
        r = _execute(db, "SELECT id FROM purchases WHERE order_id=%s", [oid]).fetchone()
        if r:
            _execute(db, "UPDATE purchases SET student_name=%s,student_code=%s,charge_code=%s,segment=%s,course_type=%s,method=%s,discount_type=%s,lesson_count=%s,amount=%s,refund_amount=%s,actual_pay_date=%s,xiaohongshu_received=%s,notes=%s WHERE order_id=%s", [data.get(k,"") if k not in ("lesson_count","amount","refund_amount","xiaohongshu_received") else float(data.get(k,0)) for k in ["student_name","student_code","charge_code","segment","course_type","method","discount_type","lesson_count","amount","refund_amount","actual_pay_date","xiaohongshu_received","notes"]] + [oid])
            return "updated"
    _execute(db, "INSERT INTO purchases (student_name,student_code,charge_code,segment,course_type,method,discount_type,lesson_count,amount,refund_amount,actual_pay_date,order_id,xiaohongshu_received,notes) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", [data.get("student_name",""), data.get("student_code",""), data.get("charge_code",""), data.get("segment",""), data.get("course_type",""), data.get("method",""), data.get("discount_type",""), int(data.get("lesson_count",0)), float(data.get("amount",0)), float(data.get("refund_amount",0)), data.get("actual_pay_date",""), oid, float(data.get("xiaohongshu_received",0)), data.get("notes","")])
    return "new"

def purchase_list(student_name=None, date_from=None, date_to=None, limit=200):
    db = get_db()
    sql = "SELECT * FROM purchases WHERE 1=1"
    params = []
    if student_name: sql += " AND student_name=%s"; params.append(student_name)
    if date_from: sql += " AND actual_pay_date >= %s"; params.append(date_from)
    if date_to: sql += " AND actual_pay_date <= %s"; params.append(date_to)
    sql += " ORDER BY actual_pay_date DESC LIMIT %s"
    params.append(limit)
    rows = _execute(db, sql, params).fetchall()
    cols = ["id","student_name","student_code","charge_code","segment","course_type","method","discount_type","lesson_count","amount","refund_amount","actual_pay_date","order_id","xiaohongshu_received","notes"]
    return [dict(zip(cols, [r[c] for c in cols])) for r in rows]

def purchases_paginated(page=1, limit=100):
    db = get_db()
    offset = (page - 1) * limit
    total = _execute(db, "SELECT COUNT(*) as cnt FROM purchases").fetchone()
    tc = int(total["cnt"]) if total else 0
    rows = _execute(db, "SELECT * FROM purchases ORDER BY actual_pay_date DESC, id DESC LIMIT %s OFFSET %s", [limit, offset]).fetchall()
    cols = ["id","student_name","student_code","charge_code","segment","course_type","method","discount_type","lesson_count","amount","refund_amount","actual_pay_date","order_id","xiaohongshu_received","notes"]
    return {"total": tc, "page": page, "limit": limit, "rows": [dict(zip(cols, [r[c] for c in cols])) for r in rows]}

# ------- Costs -------

def cost_add(data):
    _execute(get_db(), "INSERT INTO costs (reason,cycle,cost_type,channel,cost_date,amount,notes) VALUES (%s,%s,%s,%s,%s,%s,%s)", [data.get("reason",""), data.get("cycle",""), data.get("cost_type",""), data.get("channel",""), data.get("cost_date",""), float(data.get("amount",0)), data.get("notes","")])

def cost_list(limit=200):
    rows = _execute(get_db(), "SELECT * FROM costs ORDER BY cost_date DESC LIMIT %s", [limit]).fetchall()
    cols = ["id","reason","cycle","cost_type","channel","cost_date","amount","notes"]
    return [dict(zip(cols, [r[c] for c in cols])) for r in rows]

# ------- Pricing -------

def pricing_all():
    rows = _execute(get_db(), "SELECT * FROM pricing ORDER BY segment, course_type, discount_type").fetchall()
    cols = ["segment","course_type","discount_type","unit_price","discount_multiplier"]
    return [dict(zip(cols, [r[c] for c in cols])) for r in rows]

def pricing_set(segment, course_type, discount_type, unit_price, discount_multiplier):
    _execute(get_db(), "REPLACE INTO pricing VALUES (%s,%s,%s,%s,%s)", [segment, course_type, discount_type, float(unit_price), float(discount_multiplier)])

def calc_price(segment, course_type, discount_type, lesson_count):
    r = _execute(get_db(), "SELECT unit_price, discount_multiplier FROM pricing WHERE segment=%s AND course_type=%s AND discount_type=%s", [segment, course_type, discount_type]).fetchone()
    if r: return float(r["unit_price"]) * int(lesson_count) * float(r["discount_multiplier"])
    return 0

def init_pricing():
    defaults = [
        ("启航段","正式课","一课一销",160,1.0), ("启航段","正式课","月度9折",160,0.9),
        ("探索段","正式课","一课一销",180,1.0), ("探索段","正式课","月度9折",180,0.9),
        ("先锋段","正式课","一课一销",200,1.0),
        ("领航1V1","正式课","一课一销",385,1.0), ("领航1V2","正式课","一课一销",330,1.0),
        ("成人班","正式课","一课一销",69.9,1.0),
        ("领航1V1","试听课","试听折扣",99.9,1.0),
        ("探索段","试听课","试听折扣",69.9,1.0), ("启航段","试听课","试听折扣",69.9,1.0),
        ("混龄特典","正式课","单人特典",69.9,1.0), ("混龄特典","正式课","亲子特典",109.9,1.0),
    ]
    for s, ct, dt, price, mult in defaults:
        pricing_set(s, ct, dt, price, mult)

# ------- Dashboard -------

def dashboard_summary():
    db = get_db()
    from datetime import datetime
    month_str = datetime.now().strftime("%Y-%m")
    active = _execute(db, "SELECT COUNT(*) as cnt FROM student_ext WHERE status=%s", ["在读中"]).fetchone()
    month_att = _execute(db, "SELECT COUNT(*) as cnt, SUM(CASE WHEN status='出席' THEN 1 ELSE 0 END) as present FROM attendance WHERE lesson_date LIKE %s", [month_str + "%"]).fetchone()
    total_purchases = _execute(db, "SELECT COALESCE(SUM(amount),0) as t FROM purchases WHERE actual_pay_date LIKE %s", [month_str + "%"]).fetchone()
    return {
        "active_students": int(active["cnt"]) if active else 0,
        "month_lessons": int(month_att["cnt"]) if month_att else 0,
        "month_present": int(month_att["present"]) if month_att else 0,
        "month_revenue": float(total_purchases["t"]) if total_purchases else 0.0
    }

def dashboard_weekly():
    cfg = config_all()
    _DAY_MAP = {"一":"周一","二":"周二","三":"周三","四":"周四","五":"周五","六":"周六","日":"周日"}
    weekly = []
    for cn, units in cfg.items():
        ct = list(units.values())[0].get("class_time", "")
        cb = list(units.values())[0].get("created_by", "")
        weekday_cn = cn[1] if len(cn) > 1 else ""
        weekday = _DAY_MAP.get(weekday_cn, "")
        roster = roster_get(cn)
        weekly.append({"class_name": cn, "time": ct, "teacher": cb, "weekday": weekday, "students": roster, "color": "#8b5cf6" if cb == "欣欣" else "#3b82f6"})
    return weekly

# ------- Teacher Coefficients -------

def teacher_coefficients_all():
    rows = _execute(get_db(), "SELECT * FROM teacher_coefficients").fetchall()
    return [{"teacher_name": r["teacher_name"], "coefficient": r["coefficient"], "hourly_rate": r["hourly_rate"]} for r in rows]

def teacher_coefficient_set(name, coefficient, hourly_rate):
    _execute(get_db(), "REPLACE INTO teacher_coefficients VALUES (%s,%s,%s)", [name, float(coefficient), float(hourly_rate)])

# ------- Revenue Splits -------

def revenue_split_list(cycle=None):
    db = get_db()
    if cycle: rows = _execute(db, "SELECT * FROM revenue_splits WHERE cycle=%s ORDER BY id", [cycle]).fetchall()
    else: rows = _execute(db, "SELECT * FROM revenue_splits ORDER BY id").fetchall()
    cols = ["id","cycle","content","expected_revenue","trial_count","formal_count","lesson_50pct","research_ratio","research_xinxin_coef","research_xinxin","research_sitong_coef","research_sitong","research_biscuit_coef","research_biscuit","source_20pct","new_enroll","recruitment_trial","renewal_remaining","neukol_fee","other_cost","notes"]
    return [dict(zip(cols, [r[c] for c in cols])) for r in rows]

def revenue_split_upsert(data):
    db = get_db()
    rid = data.get("id", 0)
    fields = ["cycle","content","expected_revenue","trial_count","formal_count","lesson_50pct","research_ratio","research_xinxin_coef","research_xinxin","research_sitong_coef","research_sitong","research_biscuit_coef","research_biscuit","source_20pct","new_enroll","recruitment_trial","renewal_remaining","neukol_fee","other_cost","notes"]
    vals = [data.get(f, 0) if f not in ("cycle","content","notes") else data.get(f, "") for f in fields]
    if rid:
        sets = ", ".join(f"{f}=%s" for f in fields)
        _execute(db, f"UPDATE revenue_splits SET {sets} WHERE id=%s", vals + [rid])
    else:
        placeholders = ",".join(["%s"]*len(fields))
        _execute(db, f"INSERT INTO revenue_splits ({','.join(fields)}) VALUES ({placeholders})", vals)

# ------- Finance Summary -------

def finance_summary():
    db = get_db()
    rev = _execute(db, "SELECT COALESCE(SUM(amount),0) as t FROM purchases").fetchone()
    cost = _execute(db, "SELECT COALESCE(SUM(amount),0) as t FROM costs").fetchone()
    students = _execute(db, "SELECT COUNT(*) as t FROM student_ext WHERE status=%s", ["在读中"]).fetchone()
    return {"total_revenue": float(rev["t"]), "total_cost": float(cost["t"]), "balance": float(rev["t"])-float(cost["t"]), "active_students": int(students["t"])}

# ------- Student Profiles (existing DB compatibility) -------

def profiles_load(cls_name=None):
    return {}

def profiles_save_lesson(cls_name, name, date, title, speech_count, topic_count, traits, best_quote):
    pass

def profiles_save_gender(cls_name, all_names, gender_map, default_gender):
    pass

def profiles_delete_class(cls_name):
    pass

# ------- Recycle -------

def recycle_add(info):
    _execute(get_db(), "INSERT INTO recycle (class_name, unit_code, unit_name, path, deleted_at) VALUES (%s,%s,%s,%s,%s)", [info.get("class",""), info.get("unit_code",""), info.get("name",""), info.get("path",""), info.get("deleted_at","")])

def recycle_all():
    rows = _execute(get_db(), "SELECT * FROM recycle ORDER BY id DESC").fetchall()
    return [dict(zip(["id","class_name","unit_code","unit_name","path","deleted_at"], [r[c] for c in ["id","class_name","unit_code","unit_name","path","deleted_at"]])) for r in rows]

# ------- Combined config load -------

def config_and_lessons():
    from datetime import datetime
    month_str = datetime.now().strftime("%Y-%m")
    db = get_db()
    cur = db.cursor()

    cur.execute("SELECT class_name, unit_code, unit_name, path, created_by, class_time FROM config ORDER BY class_name")
    cfg_rows = [Row([d[0] for d in cur.description], list(r)) for r in cur.fetchall()]
    cfg = {}
    for r in cfg_rows:
        if r["class_name"] not in cfg: cfg[r["class_name"]] = {}
        cfg[r["class_name"]][r["unit_code"]] = {"name": r["unit_name"], "path": r["path"], "created_by": r["created_by"], "class_time": r["class_time"]}

    cur.execute("SELECT class_name, unit_code, lesson_num, title, updated_at FROM lessons ORDER BY class_name, unit_code, lesson_num")
    lesson_rows = [Row([d[0] for d in cur.description], list(r)) for r in cur.fetchall()]
    lessons = {}
    for r in lesson_rows:
        cn, uc = r["class_name"], r["unit_code"]
        unit_name = cfg.get(cn, {}).get(uc, {}).get("name", uc)
        if cn not in lessons: lessons[cn] = {}
        if uc not in lessons[cn]: lessons[cn][uc] = []
        lessons[cn][uc].append({"folder": f"{cn}-{uc}-{r['lesson_num']}", "lesson": str(r["lesson_num"]), "title": r["title"], "date": (r["updated_at"] or "")[:10], "unit_name": unit_name})

    cur.execute("SELECT COUNT(*) as cnt FROM student_ext WHERE status=%s", ["在读中"])
    active = Row([d[0] for d in cur.description], list(cur.fetchone()))

    cur.execute(f"SELECT COUNT(*) as cnt, SUM(CASE WHEN status='出席' THEN 1 ELSE 0 END) as present FROM attendance WHERE lesson_date LIKE '{month_str}%'")
    month_att = Row([d[0] for d in cur.description], list(cur.fetchone()))

    cur.execute(f"SELECT COALESCE(SUM(amount),0) as t FROM purchases WHERE actual_pay_date LIKE '{month_str}%'")
    month_rev = Row([d[0] for d in cur.description], list(cur.fetchone()))

    summary = {"active_students": int(active["cnt"] or 0), "month_lessons": int(month_att["cnt"] or 0), "month_present": int(month_att["present"] or 0), "month_revenue": float(month_rev["t"] or 0)}
    weekly = dashboard_weekly()

    return cfg, lessons, summary, weekly

# ------- Init -------
if __name__ == "__main__":
    print("TiDB connected OK")
    init_pricing()
    for n, c, r in [("欣欣", 0.9, 0), ("思童", 0.1, 0), ("饼干", 0, 0)]:
        try: teacher_coefficient_set(n, c, r)
        except: pass
    print("Init complete")