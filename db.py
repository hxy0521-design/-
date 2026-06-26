"""TiDB Cloud data layer — shared between 欣欣 and 饼干"""
import os, json, pymysql, threading, sqlite3

TIDB_HOST = os.environ.get("TIDB_HOST", "gateway01.ap-southeast-1.prod.alicloud.tidbcloud.com")
TIDB_PORT = int(os.environ.get("TIDB_PORT", "4000"))
TIDB_USER = os.environ.get("TIDB_USER", "34ipvAFzinPcerR.root")
TIDB_PASS = os.environ.get("TIDB_PASS", "CphkRDoBKvwA2OEY")
TIDB_DB = os.environ.get("TIDB_DB", "test")
ZG_TEST = os.environ.get("ZG_TEST", "")

_local = threading.local()

class _SQLiteWrapper:
    """包装 sqlite3 连接，自动转换 MySQL 语法"""
    def __init__(self, conn):
        self._conn = conn
    def cursor(self):
        return _SQLiteCursor(self._conn.cursor())
    def commit(self): self._conn.commit()
    def __getattr__(self, name): return getattr(self._conn, name)

class _SQLiteCursor:
    def __init__(self, cur):
        self._cur = cur
    def execute(self, sql, params=None):
        if params: sql = sql.replace('%s', '?')
        sql = sql.replace('REPLACE INTO', 'INSERT OR REPLACE INTO')
        return self._cur.execute(sql, params or [])
    def __getattr__(self, name): return getattr(self._cur, name)
    @property
    def description(self): return self._cur.description
    def fetchall(self): return self._cur.fetchall()
    def fetchone(self): return self._cur.fetchone()

def get_db():
    if ZG_TEST:
        if not hasattr(_local, "conn") or _local.conn is None:
            db_path = os.environ.get("ZG_DB", "test_data.db")
            raw = sqlite3.connect(db_path, check_same_thread=False)
            raw.execute("PRAGMA journal_mode=WAL")
            _local.conn = _SQLiteWrapper(raw)
        return _local.conn
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
    if params and not ZG_TEST:
        sql = sql.replace('?', '%s')
    cur.execute(sql, params or [])
    try: rows = cur.fetchall()
    except: rows = []
    return Result(cur, rows)

def init_db():
    if ZG_TEST:
        db = get_db()
        db.executescript("""
            CREATE TABLE IF NOT EXISTS config (class_name TEXT, unit_code TEXT, unit_name TEXT, path TEXT, created_by TEXT, class_time TEXT, off_weeks TEXT DEFAULT '');
            CREATE TABLE IF NOT EXISTS lessons (class_name TEXT, unit_code TEXT, lesson_num INTEGER, title TEXT, content TEXT, updated_at TEXT);
            CREATE TABLE IF NOT EXISTS attendance (id INTEGER PRIMARY KEY AUTOINCREMENT, class_name TEXT, unit_code TEXT, lesson_num INTEGER, lesson_title TEXT, lesson_date TEXT, student_name TEXT, status TEXT, note TEXT, recorded_at TEXT, cycle TEXT);
            CREATE TABLE IF NOT EXISTS purchases (id INTEGER PRIMARY KEY AUTOINCREMENT, student_name TEXT, student_code TEXT, charge_code TEXT, segment TEXT, course_type TEXT, method TEXT, discount_type TEXT, lesson_count INTEGER, amount REAL, refund_amount REAL DEFAULT 0, actual_pay_date TEXT, order_id TEXT, xiaohongshu_received REAL DEFAULT 0, notes TEXT);
            CREATE TABLE IF NOT EXISTS student_ext (student_name TEXT PRIMARY KEY, student_code TEXT, source TEXT, status TEXT, segment TEXT, enrolled_class TEXT, purchased_lessons INTEGER DEFAULT 0, used_lessons INTEGER DEFAULT 0, remaining_lessons INTEGER DEFAULT 0, notes TEXT);
            CREATE TABLE IF NOT EXISTS class_roster (class_name TEXT, student_name TEXT);
            CREATE TABLE IF NOT EXISTS costs (id INTEGER PRIMARY KEY AUTOINCREMENT, reason TEXT, cycle TEXT, cost_type TEXT, channel TEXT, cost_date TEXT, amount REAL, notes TEXT);
            CREATE TABLE IF NOT EXISTS pricing (segment TEXT, course_type TEXT, discount_type TEXT, unit_price REAL, discount_multiplier REAL);
            CREATE TABLE IF NOT EXISTS teacher_coefficients (teacher_name TEXT PRIMARY KEY, coefficient REAL, hourly_rate REAL);
            CREATE TABLE IF NOT EXISTS revenue_splits (id INTEGER PRIMARY KEY AUTOINCREMENT, cycle TEXT, content_label TEXT, revenue REAL, trial_count INTEGER DEFAULT 0, formal_count INTEGER DEFAULT 0, referral_supplement REAL DEFAULT 0, platform_fee REAL DEFAULT 0, new_enroll INTEGER DEFAULT 0, recruitment REAL DEFAULT 0, recruit_xin_coef REAL DEFAULT 1.0, recruit_xin REAL DEFAULT 0, recruit_bis REAL DEFAULT 0, conversion REAL DEFAULT 0, conversion_xin REAL DEFAULT 0, conversion_bis REAL DEFAULT 0, retention REAL DEFAULT 0, retention_xin REAL DEFAULT 0, retention_bis REAL DEFAULT 0, lesson_50pct REAL, xinxin_lesson_share REAL DEFAULT 0, biscuit_lesson_share REAL DEFAULT 0, teaching_20pct REAL, xinxin_coef REAL DEFAULT 0.9, xinxin_share REAL, sitong_coef REAL DEFAULT 0.1, sitong_share REAL, biscuit_coef REAL DEFAULT 0, biscuit_share REAL, source_20pct REAL, neukol_fee REAL DEFAULT 0, other_cost REAL DEFAULT 0, notes TEXT, net_balance REAL);
            CREATE TABLE IF NOT EXISTS recycle (id INTEGER PRIMARY KEY AUTOINCREMENT, class_name TEXT, unit_code TEXT, unit_name TEXT, path TEXT, deleted_at TEXT);
            CREATE TABLE IF NOT EXISTS settlements (id INTEGER PRIMARY KEY AUTOINCREMENT, teacher_name TEXT, cycle TEXT, amount REAL DEFAULT 0, lesson_share REAL DEFAULT 0, teaching_share REAL DEFAULT 0, source_share REAL DEFAULT 0, detail TEXT, status TEXT DEFAULT '待结算', settled_date TEXT, notes TEXT, created_at TEXT);
        """)
        init_pricing()

def migrate_from_json():
    pass

# ------- Config API -------

def config_all():
    db = get_db()
    rows = _execute(db, "SELECT class_name, unit_code, unit_name, path, created_by, class_time, off_weeks FROM config ORDER BY class_name").fetchall()
    cfg = {}
    for r in rows:
        if r["class_name"] not in cfg:
            cfg[r["class_name"]] = {}
        cfg[r["class_name"]][r["unit_code"]] = {
            "name": r["unit_name"], "path": r["path"],
            "created_by": r["created_by"], "class_time": r["class_time"], "off_weeks": r["off_weeks"] or ""
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
    _execute(db, "INSERT INTO config VALUES (%s,%s,%s,%s,%s,%s,%s)", [cls_name, "2605", cls_name, "", created_by, class_time, ""])

def config_remove_class(cls_name):
    _execute(get_db(), "DELETE FROM config WHERE class_name=%s", [cls_name])

def config_add_unit(cls_name, unit_code, unit_name, path, created_by=""):
    _execute(get_db(), "INSERT INTO config VALUES (%s,%s,%s,%s,%s,%s,%s)", [cls_name, unit_code, unit_name, path, created_by, "", ""])

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

def lesson_delete(cls_name, unit_code, lesson_num):
    _execute(get_db(), "DELETE FROM lessons WHERE class_name=%s AND unit_code=%s AND lesson_num=%s", [cls_name, unit_code, lesson_num])

# ------- Student Ext -------

def attendance_student_counts():
    """返回 {student_name: 实际出勤次数}（仅 status='出席'）"""
    rows = _execute(get_db(), "SELECT student_name, COUNT(*) as cnt FROM attendance WHERE status='出席' GROUP BY student_name").fetchall()
    return {r["student_name"]: int(r["cnt"]) for r in rows}

def student_ext_cleanup_trial():
    """仅试听学生超过10天无缴费 → 移出班级（enrolled_class 清空）"""
    db = get_db()
    from datetime import datetime, timedelta
    cutoff = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d")
    # 找到所有仅试听且有班级的学生
    rows = _execute(db, "SELECT student_name, enrolled_class FROM student_ext WHERE status=%s AND enrolled_class IS NOT NULL AND enrolled_class != ''", ["仅试听"]).fetchall()
    for r in rows:
        name = r["student_name"]
        # 除了初始试听外，是否有新增缴费（≥2条 = 已转化，不处理）
        pay_cnt = _execute(db, "SELECT COUNT(*) as cnt FROM purchases WHERE student_name=%s", [name]).fetchone()
        if pay_cnt and int(pay_cnt["cnt"] or 0) > 1:
            continue  # 有新增缴费，已转化
        # 检查最近考勤：无任何考勤记录的新生不处理，有记录但超过10天的才移出
        recent_att = _execute(db, "SELECT MAX(lesson_date) as last_date FROM attendance WHERE student_name=%s", [name]).fetchone()
        last_date = recent_att["last_date"] if recent_att else None
        if not last_date:
            continue  # 完全没考勤记录的新生，不处理
        if str(last_date) >= cutoff:
            continue  # 最近10天内有考勤，不处理
        # 有考勤记录但超过10天无新考勤且无新增缴费 → 移出班级
        _execute(db, "UPDATE student_ext SET enrolled_class=%s WHERE student_name=%s", ["", name])

def student_ext_all():
    student_ext_cleanup_trial()  # 先清理超期试听
    rows = _execute(get_db(), "SELECT * FROM student_ext ORDER BY student_name").fetchall()
    cols = ["student_name","student_code","source","status","segment","enrolled_class","purchased_lessons","used_lessons","remaining_lessons","notes","added_by","gender"]
    return [dict(zip(cols, [r[c] for c in cols])) for r in rows]

def student_ext_upsert(name, data):
    db = get_db()
    r = _execute(db, "SELECT student_name FROM student_ext WHERE student_name=%s", [name]).fetchone()
    added_by = data.get("added_by","")
    vals = [data.get("student_code",""), data.get("source",""), data.get("status",""), data.get("segment",""), data.get("enrolled_class",""), int(data.get("purchased_lessons",0)), int(data.get("used_lessons",0)), int(data.get("remaining_lessons",0)), data.get("notes",""), added_by, data.get("gender","")]
    if r:
        _execute(db, "UPDATE student_ext SET student_code=%s,source=%s,status=%s,segment=%s,enrolled_class=%s,purchased_lessons=%s,used_lessons=%s,remaining_lessons=%s,notes=%s,added_by=%s,gender=%s WHERE student_name=%s", vals + [name])
    else:
        _execute(db, "INSERT INTO student_ext VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", [name] + vals)

# ------- Attendance -------

def cycle_from_unit(unit_code):
    """从单元编号推导周期标签，如 2605 → '2605春季班'"""
    if not unit_code: return ""
    # 尝试从已有考勤记录中找到匹配的周期
    row = _execute(get_db(), "SELECT cycle FROM attendance WHERE unit_code=%s AND cycle!='' ORDER BY lesson_date DESC LIMIT 1", [unit_code]).fetchone()
    if row and row["cycle"]: return row["cycle"]
    # 回退：根据月份推算课型
    try:
        m = int(unit_code[2:4]) if len(unit_code) >= 4 else 0
        sem = "试听期" if m == 9 else ("寒假班" if m in (1,2) else ("春季班" if 3<=m<=6 else "正式课"))
        return f"{unit_code}{sem}"
    except: return unit_code

def consume_lesson_for_student(student_name):
    """消耗1课时，返回价格。用实际出勤 vs 已购判断欠费。
    取该生最大金额的正式课购买作为单价（排除试听/转介绍）"""
    db = get_db()
    se = _execute(db, "SELECT purchased_lessons FROM student_ext WHERE student_name=%s", [student_name]).fetchone()
    if not se: return -1
    pur = int(se['purchased_lessons'] or 0)
    used = _execute(db, "SELECT COUNT(*) as cnt FROM attendance WHERE student_name=%s AND status='出席'", [student_name]).fetchone()
    used_cnt = int(used['cnt']) if used else 0
    if used_cnt > pur: return -1  # 欠费：已消超过已购
    # 取正式课单价（排除试听折扣/转介绍赠）
    price_row = _execute(db, """
        SELECT amount, lesson_count FROM purchases
        WHERE student_name=%s AND discount_type NOT IN ('试听折扣','转介绍赠')
        ORDER BY amount DESC LIMIT 1
    """, [student_name]).fetchone()
    if not price_row:
        price_row = _execute(db, "SELECT amount, lesson_count FROM purchases WHERE student_name=%s ORDER BY amount DESC LIMIT 1", [student_name]).fetchone()
    if not price_row: return -1
    price = float(price_row['amount']) / int(price_row['lesson_count']) if int(price_row['lesson_count']) > 0 else 0
    return round(price, 2)

def attendance_batch(records):
    from datetime import datetime
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db = get_db()
    for r in records:
        cycle = r.get("cycle","") or cycle_from_unit(r.get("unit_code",""))
        content_label = r.get("content_label","")
        consumed_price = 0
        if r.get("status","出席") == "出席":
            consumed_price = consume_lesson_for_student(r["student_name"])
            if consumed_price < 0: consumed_price = -1  # 欠费标记
        _execute(db, "DELETE FROM attendance WHERE class_name=%s AND unit_code=%s AND lesson_num=%s AND student_name=%s", [r["class_name"], r.get("unit_code",""), r["lesson_num"], r["student_name"]])
        _execute(db, "INSERT INTO attendance (class_name,unit_code,lesson_num,lesson_title,lesson_date,student_name,status,note,recorded_at,cycle,content_label,consumed_price) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", [r["class_name"], r.get("unit_code",""), r["lesson_num"], r.get("lesson_title",""), r.get("lesson_date",""), r["student_name"], r.get("status","出席"), r.get("note",""), now, cycle, content_label, consumed_price])

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

def attendance_delete_lesson(class_name, lesson_num, lesson_title="", lesson_date=""):
    """删除指定课节的全部考勤记录"""
    sql = "DELETE FROM attendance WHERE class_name=%s AND lesson_num=%s"
    params = [class_name, lesson_num]
    if lesson_title:
        sql += " AND lesson_title=%s"
        params.append(lesson_title)
    if lesson_date:
        sql += " AND lesson_date=%s"
        params.append(lesson_date)
    _execute(get_db(), sql, params)

def attendance_stats(class_name=None):
    db = get_db()
    sql = "SELECT status, COUNT(*) as cnt FROM attendance WHERE 1=1"
    params = []
    if class_name: sql += " AND class_name=%s"; params.append(class_name)
    sql += " GROUP BY status"
    rows = _execute(db, sql, params).fetchall()
    return {r["status"]: r["cnt"] for r in rows}

def attendance_by_lesson(class_name=None, cycle=None, student_name=None, limit=50, page=1):
    db = get_db()
    base_where = "WHERE 1=1"
    w_params = []
    if class_name: base_where += " AND class_name=%s"; w_params.append(class_name)
    if cycle: base_where += " AND cycle=%s"; w_params.append(cycle)
    if student_name: base_where += " AND student_name=%s"; w_params.append(student_name)
    # Count total
    count_sql = f"SELECT COUNT(DISTINCT CONCAT(class_name,'-',lesson_title,'-',lesson_date)) as cnt FROM attendance {base_where}"
    total_row = _execute(db, count_sql, w_params).fetchone()
    total_count = int(total_row["cnt"]) if total_row else 0
    # Paginated grouped query
    offset = (page - 1) * limit
    sql = f"SELECT class_name, lesson_title, lesson_date, ANY_VALUE(cycle) as cycle, ANY_VALUE(content_label) as content_label, COUNT(*) as total, SUM(CASE WHEN status='出席' THEN 1 ELSE 0 END) as present FROM attendance {base_where}"
    sql += " GROUP BY class_name, lesson_title, lesson_date ORDER BY lesson_date DESC, CASE class_name WHEN '周一探索' THEN 1 WHEN '周三启航' THEN 2 WHEN '周四探索' THEN 3 WHEN '周五启航' THEN 4 WHEN '周五领航' THEN 5 WHEN '周六启航' THEN 6 WHEN '周六探索' THEN 7 WHEN '周六先锋' THEN 8 WHEN '周日启航1' THEN 9 WHEN '周日启航2' THEN 10 WHEN '周日启航3' THEN 11 WHEN '周日探索' THEN 12 WHEN '寒假启航1' THEN 13 WHEN '寒假启航2' THEN 14 WHEN '寒假探索' THEN 15 WHEN '寒假先锋' THEN 16 WHEN '混龄特典' THEN 17 WHEN '纯试听' THEN 18 ELSE 0 END DESC, MAX(id) DESC LIMIT %s OFFSET %s"
    rows = _execute(db, sql, w_params + [limit, offset]).fetchall()
    if not rows: return [], 0
    # One bulk query for all student details
    detail_sql = "SELECT class_name, lesson_title, lesson_date, student_name, status, note, consumed_price FROM attendance WHERE (class_name, lesson_title, lesson_date) IN ("
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
    for pr in _execute(db, "SELECT segment, MIN(unit_price) as unit_price FROM pricing WHERE course_type=%s AND unit_price > %s GROUP BY segment", ["正式课", 0]).fetchall():
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
        for seg, kw in [("探索段","探索"),("启航段","启航"),("先锋段","先锋"),("领航1V1","领航"),("领航1V2","领航"),("成人班","成人"),("混龄特典","混龄")]:
            if kw in cn: seg_display = seg; break
        total = int(r["total"] or 0)
        present = int(r["present"] or 0)
        # Get students from the bulk-loaded map
        key = (cn, r["lesson_title"], r["lesson_date"])
        students = student_map.get(key, [])
        student_names = [s["student_name"] for s in students if s["status"] == "出席"]
        # Build notes: 分组显示 请假：xx xx | 缺席：xx
        qingjia = []; quexi = []
        for s in students:
            status = str(s["status"]).strip() if s["status"] else ""
            note = str(s["note"]).strip() if s["note"] and str(s["note"]) != "None" else ""
            if status == "请假":
                qingjia.append(s["student_name"])
            elif status == "缺席" or (status != "出席" and note == "缺席"):
                quexi.append(s["student_name"])
            elif status != "出席":
                # fallback: other non-出席 status
                qingjia.append(s["student_name"])
        parts = []
        if qingjia: parts.append("请假：" + " ".join(qingjia))
        if quexi: parts.append("缺席：" + " ".join(quexi))
        leave_notes = " | ".join(parts)
        # 用实际消耗价格算收入，无消耗价格的按0
        actual_revenue = _execute(db,
            f"SELECT COALESCE(SUM(consumed_price),0) as rev FROM attendance WHERE status='出席' AND (class_name=%s AND lesson_title=%s AND lesson_date=%s)",
            [cn, r["lesson_title"], r["lesson_date"]]).fetchone()
        lesson_revenue = round(float(actual_revenue["rev"]) if actual_revenue else 0, 2)
        # price: 正价（定价表），人均: 实际消耗均值
        nominal_price = price_map.get(seg_display, 0)
        # 折扣说明稍后批量处理
        price_label = ""
        # Compute欠费 info
        debt_students = [s["student_name"] for s in students if str(s["consumed_price"]) == "-1.00"]
        has_debt = len(debt_students) > 0
        debt_count = len(debt_students)
        debt_names = "、".join(debt_students)
        formal = student_names[:]  # 试听学生稍后批量标记
        trial = []
        result.append({
            "class_name": cn, "lesson_title": display_title, "_raw_title": r["lesson_title"] or "", "lesson_num": lesson_num,
            "lesson_date": r["lesson_date"], "weekday": weekday,
            "cycle": r["cycle"] or "", "content_label": r["content_label"] or "", "segment": seg_display, "time": class_time,
            "total": total, "present": present,
            "price": nominal_price, "price_label": price_label, "has_debt": has_debt, "debt_count": debt_count, "debt_names": debt_names,
            "lesson_revenue": round(lesson_revenue, 1),
            "per_person": round(lesson_revenue / present, 1) if present > 0 else 0,
            "students": formal, "trial_students": trial, "leave_notes": leave_notes,
        })
    # 批量计算价格标签和欠费：用原始 lesson_title（非 display_title）
    def _price_name(p, nominal):
        p = float(p or 0)
        if p == -1: return None  # 欠费，不计入价格标签
        if p == 0: return "转介绍-0"
        ratio = round(p / nominal, 2) if nominal > 0 else 0
        if ratio >= 0.99: return f"全价-{int(p)}"
        if ratio >= 0.88: return f"9折-{int(p)}"
        if ratio >= 0.83: return f"85折-{int(p)}"
        if p <= 70: return f"试听-{int(p)}"
        return f"{int(p)}"
    price_labels = {}
    if result:
        # 用原始 GROUP BY 标题（raw_titles）做匹配键
        lesson_set = set()
        for r in result:
            raw = r.get("_raw_title", r["lesson_title"])
            lesson_set.add((r["class_name"], raw, r["lesson_date"]))
        # 一次性拿所有消耗价（含人数统计）
        all_cps2 = _execute(db,
            "SELECT class_name, lesson_title, lesson_date, consumed_price, COUNT(*) as cnt FROM attendance WHERE status='出席' AND (class_name, lesson_title, lesson_date) IN (" +
            ",".join(["(%s,%s,%s)"]*len(lesson_set)) + ") GROUP BY class_name, lesson_title, lesson_date, consumed_price",
            [x for k in lesson_set for x in k]).fetchall()
        from collections import defaultdict
        cp_map = defaultdict(list)  # key → [(price, count)]
        for cp in all_cps2:
            key = (cp["class_name"], cp["lesson_title"], cp["lesson_date"])
            cp_map[key].append((float(cp["consumed_price"]), int(cp["cnt"])))
        for r in result:
            key = (r["class_name"], r["_raw_title"], r["lesson_date"])
            pc_list = cp_map.get(key, [])
            nominal_price = price_map.get(r["segment"], 0)
            parts = []
            # 排序：转介绍在前，然后全价/9折/85折/试听
            for p, cnt in sorted(pc_list, key=lambda x: (0 if x[0]==0 else 1, -x[0])):
                pn = _price_name(p, nominal_price)
                if pn: parts.append(f"{pn}/{cnt}节")
            r["price_label"] = f"{int(nominal_price)}/节（{' '.join(parts)}）" if parts else f"{int(nominal_price)}/节"
    # 批量区分试听生：consumed_price=69.9/99.9 且该生无正式课购买（排除 FIFO 误判）
    all_student_names = set()
    for r in result: all_student_names.update(r["students"])
    trial_set = set()
    if all_student_names:
        nl = list(all_student_names)
        phs = ','.join(['%s']*len(nl))
        # 有正式课购买的学生不算试听
        formal_pur = _execute(db, f"SELECT DISTINCT student_name FROM purchases WHERE student_name IN ({phs}) AND discount_type NOT IN ('试听折扣','转介绍赠')", nl).fetchall()
        formal_set = set(fp['student_name'] for fp in formal_pur)
    for r in result:
        key = (r["class_name"], r["_raw_title"], r["lesson_date"])
        att_students = student_map.get(key, [])
        trial = [s["student_name"] for s in att_students if float(s["consumed_price"] or 0) in (69.9, 99.9) and s["student_name"] in r["students"] and s["student_name"] not in formal_set]
        r["trial_students"] = trial
        r["students"] = [sn for sn in r["students"] if sn not in trial]
    for r in result:
        # 欠费数：consumed_price = -1 的人数
        debt_cnt = 0
        pc_items = cp_map.get((r["class_name"], r["_raw_title"], r["lesson_date"]), [])
        for pc in pc_items:
            if float(pc[0]) == -1: debt_cnt += pc[1]
        r["has_debt"] = debt_cnt > 0
        r["debt_count"] = debt_cnt
    return result, total_count

# ------- Roster -------

def roster_get(class_name):
    rows = _execute(get_db(), "SELECT student_name FROM class_roster WHERE class_name=%s ORDER BY student_name", [class_name]).fetchall()
    return [r["student_name"] for r in rows]

def roster_set(class_name, students):
    db = get_db()
    _execute(db, "DELETE FROM class_roster WHERE class_name=%s", [class_name])
    seen = set()
    for s in students:
        if s and s not in seen:
            seen.add(s)
            _execute(db, "INSERT INTO class_roster VALUES (%s,%s)", [class_name, s])

# ------- Purchases -------

def purchase_delete(rid):
    db = get_db()
    # 删之前查一下记录，用于更新 student_ext
    rec = _execute(db, "SELECT student_name, lesson_count FROM purchases WHERE id=%s", [int(rid)]).fetchone()
    _execute(db, "DELETE FROM purchases WHERE id=%s", [int(rid)])
    if rec:
        name = rec["student_name"]; cnt = int(rec["lesson_count"] or 0)
        if name and cnt > 0:
            r2 = _execute(db, "SELECT purchased_lessons FROM student_ext WHERE student_name=%s", [name]).fetchone()
            if r2 is not None:
                cur = int(r2["purchased_lessons"] or 0)
                new_pur = max(0, cur - cnt)
                new_rem = max(0, new_pur - (int(_execute(db, "SELECT COUNT(*) as cnt FROM attendance WHERE student_name=%s AND status='出席'", [name]).fetchone()["cnt"] or 0)))
                _execute(db, "UPDATE student_ext SET purchased_lessons=%s, remaining_lessons=%s WHERE student_name=%s", [new_pur, new_rem, name])

def purchase_add(data):
    db = get_db()
    # 按 ID 更新（用于订单号编辑等场景）
    rid = data.get("id", 0)
    if rid:
        sets = []
        vals = []
        for k in ["order_id","xiaohongshu_received","notes","student_name","student_code","charge_code","segment","course_type","method","discount_type","lesson_count","amount","refund_amount","actual_pay_date"]:
            if k in data:
                sets.append(f"{k}=%s")
                vals.append(data[k])
        if sets:
            _execute(db, f"UPDATE purchases SET {', '.join(sets)} WHERE id=%s", vals + [rid])
            return "updated"
    oid = data.get("order_id","")
    if oid:
        r = _execute(db, "SELECT id FROM purchases WHERE order_id=%s", [oid]).fetchone()
        if r:
            _execute(db, "UPDATE purchases SET student_name=%s,student_code=%s,charge_code=%s,segment=%s,course_type=%s,method=%s,discount_type=%s,lesson_count=%s,amount=%s,refund_amount=%s,actual_pay_date=%s,xiaohongshu_received=%s,notes=%s WHERE order_id=%s", [data.get(k,"") if k not in ("lesson_count","amount","refund_amount","xiaohongshu_received") else float(data.get(k,0)) for k in ["student_name","student_code","charge_code","segment","course_type","method","discount_type","lesson_count","amount","refund_amount","actual_pay_date","xiaohongshu_received","notes"]] + [oid])
            return "updated"
    # 检查是否已存在完全相同的记录（防重复导入）
    name = data.get("student_name","")
    date = data.get("actual_pay_date","")
    cnt = float(data.get("lesson_count",0))
    amt = float(data.get("amount",0))
    seg = data.get("segment","")
    ct = data.get("course_type","")
    method = data.get("method","")
    dt = data.get("discount_type","")
    # 同步更新 student_ext 的已购课时（先于重复检查，确保不丢）
    if name and cnt != 0:
        r2 = _execute(db, "SELECT purchased_lessons, used_lessons FROM student_ext WHERE student_name=%s", [name]).fetchone()
        if r2 is not None:
            cur_pur = float(r2["purchased_lessons"] or 0)
            cur_used = float(r2["used_lessons"] or 0)
            new_pur = max(0, cur_pur + cnt)
            new_rem = max(0, new_pur - cur_used)
            _execute(db, "UPDATE student_ext SET purchased_lessons=%s, remaining_lessons=%s WHERE student_name=%s", [new_pur, new_rem, name])
    exist = _execute(db, "SELECT id FROM purchases WHERE student_name=%s AND actual_pay_date=%s AND lesson_count=%s AND amount=%s AND COALESCE(segment,'')=%s AND COALESCE(course_type,'')=%s AND COALESCE(method,'')=%s AND COALESCE(discount_type,'')=%s", [name, date, cnt, amt, seg, ct, method, dt]).fetchone()
    if exist:
        return "duplicate"
    _execute(db, "INSERT INTO purchases (student_name,student_code,charge_code,segment,course_type,method,discount_type,lesson_count,amount,refund_amount,actual_pay_date,order_id,xiaohongshu_received,notes) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", [name, data.get("student_code",""), data.get("charge_code",""), seg, ct, method, dt, cnt, amt, float(data.get("refund_amount",0)), date, oid, float(data.get("xiaohongshu_received",0)), data.get("notes","")])
    # 自动清除该学生的欠费标记：每新增一课次，清除一条 consumed_price=-1 的记录
    if name and cnt > 0:
        debt_rows = _execute(db, "SELECT id, class_name FROM attendance WHERE student_name=%s AND consumed_price=-1 AND status='出席' ORDER BY lesson_date ASC", [name]).fetchall()
        clear_count = min(int(cnt), len(debt_rows))
        for dr in debt_rows[:clear_count]:
            # 取该班级的正价
            pr = _execute(db, "SELECT consumed_price FROM attendance WHERE class_name=%s AND consumed_price>0 AND status='出席' ORDER BY id DESC LIMIT 1", [dr['class_name']]).fetchone()
            price = float(pr['consumed_price']) if pr else 160.0
            _execute(db, "UPDATE attendance SET consumed_price=%s, note='' WHERE id=%s", [price, dr['id']])
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

def purchases_paginated(page=1, limit=100, student_name=None, segment=None, class_name=None, search=None, discount_type=None):
    db = get_db()
    offset = (page - 1) * limit
    joins = ""; conditions = []; params = []
    if student_name:
        conditions.append("p.student_name=%s"); params.append(student_name)
    if segment:
        conditions.append("p.segment=%s"); params.append(segment)
    if search:
        conditions.append("(p.student_name LIKE %s OR p.order_id LIKE %s)"); params.append("%"+search+"%"); params.append("%"+search+"%")
    if class_name:
        joins = " JOIN student_ext e ON p.student_name = e.student_name"
        conditions.append("e.enrolled_class=%s"); params.append(class_name)
    if discount_type:
        conditions.append("p.discount_type=%s"); params.append(discount_type)
    where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
    total = _execute(db, f"SELECT COUNT(*) as cnt FROM purchases p{joins}{where}", params).fetchone()
    tc = int(total["cnt"]) if total else 0
    rows = _execute(db, f"SELECT p.* FROM purchases p{joins}{where} ORDER BY CASE WHEN p.actual_pay_date IS NULL OR p.actual_pay_date='' THEN 0 ELSE 1 END, p.actual_pay_date DESC, p.id DESC LIMIT %s OFFSET %s", params + [limit, offset]).fetchall()
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
    now = datetime.now()
    month_str = now.strftime("%Y-%m")
    # 找当前周期：取最近一次考勤记录的 cycle
    cycle_row = _execute(db, "SELECT cycle FROM attendance WHERE cycle!='' ORDER BY lesson_date DESC LIMIT 1").fetchone()
    current_cycle = cycle_row["cycle"] if cycle_row else f"{now.strftime('%y%m')}春季班"
    # 按周期统计（不是日历月）
    month_att = _execute(db, f"SELECT COUNT(DISTINCT CONCAT(class_name,'-',lesson_title,'-',lesson_date)) as lessons, COUNT(*) as students, SUM(CASE WHEN status='出席' THEN 1 ELSE 0 END) as present FROM attendance WHERE cycle=%s", [current_cycle]).fetchone()
    active = _execute(db, "SELECT COUNT(*) as cnt FROM student_ext WHERE status=%s", ["在读中"]).fetchone()
    month_rev = _execute(db, "SELECT COALESCE(SUM(amount),0) as t FROM purchases WHERE actual_pay_date LIKE %s", [month_str + "%"]).fetchone()
    # 待销：已购 - 实际出勤（实时计算）
    att_counts = attendance_student_counts()
    all_students = _execute(db, "SELECT student_name, purchased_lessons FROM student_ext").fetchall()
    pending_count = 0
    for s in all_students:
        used = att_counts.get(s["student_name"], 0)
        pur = int(s["purchased_lessons"] or 0)
        if pur > used: pending_count += (pur - used)
    # 排课：从今天到月底的周数 × 每周课次
    weeks_left = 0
    try:
        end_of_month = datetime(now.year, now.month + 1, 1) if now.month < 12 else datetime(now.year + 1, 1, 1)
        from datetime import timedelta
        end_of_month = end_of_month - timedelta(days=1)
        days_left = (end_of_month - now_dt).days + 1
        weeks_left = min(4, max(0, days_left // 7 + (1 if days_left % 7 > 0 else 0)))
    except: pass
    total_classes_per_week = _execute(db, "SELECT COUNT(*) as cnt FROM config WHERE class_time != ''").fetchone()
    weekly_count = int(total_classes_per_week["cnt"]) if total_classes_per_week else 10
    # Get off weeks - count unique week numbers marked as off
    off_weeks_set = set()
    off_rows = _execute(db, "SELECT off_weeks FROM config WHERE off_weeks != ''").fetchall()
    for r in off_rows:
        for w in str(r["off_weeks"] or "").split(","):
            w = w.strip()
            if w.isdigit(): off_weeks_set.add(int(w))
    # Calculate which weeks from today to EOM are off
    current_week = (now_dt.day - 1) // 7 + 1
    weeks_in_range = set(range(current_week, current_week + weeks_left))
    off_count = len(weeks_in_range & off_weeks_set)
    schedule_remaining = (weeks_left - off_count) * weekly_count
    return {
        "active_students": int(active["cnt"]) if active else 0,
        "month_lessons": int(month_att["lessons"]) if month_att else 0,
        "month_present": int(month_att["present"]) if month_att else 0,
        "cycle": current_cycle,
        "cycle_students": int(month_att["students"]) if month_att else 0,
        "pending_paid": pending_count,
        "schedule_remaining": schedule_remaining,
        "month_revenue": float(month_rev["t"]) if month_rev else 0.0
    }

def dashboard_weekly():
    cfg = config_all()
    _DAY_MAP = {"一":"周一","二":"周二","三":"周三","四":"周四","五":"周五","六":"周六","日":"周日"}
    weekly = []
    for cn, units in cfg.items():
        roster = roster_get(cn)
        # 无花名册时，检查预填表（暑假班）
        if not roster:
            prefill_rows = _execute(get_db(), "SELECT student_name FROM prefill WHERE class_name=%s", [cn]).fetchall()
            roster = [r["student_name"] for r in prefill_rows]
        # 跳过无学生且非临时/非暑假的班级
        is_vacation = bool('临时' in cn or any(uc in units for uc in ['2607','2608']))
        if not roster and not is_vacation: continue
        ct = list(units.values())[0].get("class_time", "")
        cb = list(units.values())[0].get("created_by", "")
        color = "#8b5cf6" if cb == "欣欣" else "#3b82f6"
        # 处理双日课表：周一17:00/周三17:00 → 拆成两条
        if "/" in ct:
            for slot in ct.split("/"):
                slot = slot.strip()
                if not slot: continue
                weekday = slot[:2]  # e.g. "周一"
                time = slot[2:] if len(slot) > 2 else ""
                weekly.append({"class_name": cn, "time": time, "teacher": cb, "weekday": weekday, "students": roster, "color": color})
        else:
            weekday_cn = cn[1] if len(cn) > 1 else ""
            weekday = _DAY_MAP.get(weekday_cn, "")
            weekly.append({"class_name": cn, "time": ct, "teacher": cb, "weekday": weekday, "students": roster, "color": color})
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
    if cycle: rows = _execute(db, "SELECT * FROM revenue_splits WHERE cycle=%s ORDER BY CASE content_label WHEN '第一周' THEN 1 WHEN '第二周' THEN 2 WHEN '第三周' THEN 3 WHEN '第四周' THEN 4 WHEN '全月' THEN 5 ELSE 9 END, id", [cycle]).fetchall()
    else: rows = _execute(db, "SELECT * FROM revenue_splits ORDER BY cycle DESC, CASE content_label WHEN '第一周' THEN 1 WHEN '第二周' THEN 2 WHEN '第三周' THEN 3 WHEN '第四周' THEN 4 WHEN '全月' THEN 5 ELSE 9 END, id").fetchall()
    cols = ["id","cycle","content_label","revenue","trial_count","formal_count","referral_supplement","platform_fee","new_enroll","recruitment","recruit_xin_coef","recruit_xin","recruit_bis","conversion","conversion_xin","conversion_bis","retention","retention_xin","retention_bis","lesson_50pct","xinxin_lesson_share","biscuit_lesson_share","teaching_20pct","xinxin_coef","xinxin_share","sitong_coef","sitong_share","biscuit_coef","biscuit_share","source_20pct","neukol_fee","other_cost","notes","net_balance"]
    return [dict(zip(cols, [r[c] for c in cols])) for r in rows]

def revenue_split_upsert(data):
    db = get_db()
    rid = data.get("id", 0)
    fields = ["cycle","content_label","revenue","trial_count","formal_count","referral_supplement","platform_fee","new_enroll","recruitment","recruit_xin_coef","recruit_xin","recruit_bis","conversion","conversion_xin","conversion_bis","retention","retention_xin","retention_bis","lesson_50pct","xinxin_lesson_share","biscuit_lesson_share","teaching_20pct","xinxin_coef","xinxin_share","sitong_coef","sitong_share","biscuit_coef","biscuit_share","source_20pct","neukol_fee","other_cost","notes","net_balance"]
    vals = [data.get(f, 0) if f not in ("cycle","content_label") else data.get(f, "") for f in fields]
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

# ------- Settlements -------

def settlement_list():
    db = get_db()
    rows = _execute(db, "SELECT * FROM settlements ORDER BY cycle DESC, id").fetchall()
    cols = ["id","teacher_name","cycle","amount","lesson_share","teaching_share","source_share","detail","status","settled_date","notes","created_at"]
    return [dict(zip(cols, [r[c] for c in cols])) for r in rows]

def settlement_create(data):
    db = get_db()
    _execute(db, """INSERT INTO settlements (teacher_name,cycle,amount,lesson_share,teaching_share,source_share,detail,status,created_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        [data.get("teacher_name",""), data.get("cycle",""), data.get("amount",0), data.get("lesson_share",0),
         data.get("teaching_share",0), data.get("source_share",0), data.get("detail",""), data.get("status","待结算"),
         data.get("created_at","")])

def settlement_update_status(sid, status, settled_date=''):
    db = get_db()
    if settled_date:
        _execute(db, "UPDATE settlements SET status=%s, settled_date=%s WHERE id=%s", [status, settled_date, sid])
    else:
        _execute(db, "UPDATE settlements SET status=%s WHERE id=%s", [status, sid])

def settlement_delete(sid):
    _execute(get_db(), "DELETE FROM settlements WHERE id=%s", [sid])

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

    cur.execute("SELECT class_name, unit_code, unit_name, path, created_by, class_time, off_weeks FROM config ORDER BY class_name")
    cfg_rows = [Row([d[0] for d in cur.description], list(r)) for r in cur.fetchall()]
    cfg = {}
    for r in cfg_rows:
        if r["class_name"] not in cfg: cfg[r["class_name"]] = {}
        cfg[r["class_name"]][r["unit_code"]] = {"name": r["unit_name"], "path": r["path"], "created_by": r["created_by"], "class_time": r["class_time"], "off_weeks": r["off_weeks"] or ""}

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

    # 按当前周期统计（取最近一次考勤的 cycle）
    cur.execute("SELECT cycle FROM attendance WHERE cycle!='' ORDER BY lesson_date DESC LIMIT 1")
    cycle_row = cur.fetchone()
    current_cycle = cycle_row[0] if cycle_row else f"{datetime.now().strftime('%y%m')}春季班"
    cur.execute(f"SELECT COUNT(DISTINCT CONCAT(class_name,'-',lesson_title,'-',lesson_date)) as lessons, COUNT(*) as students, SUM(CASE WHEN status='出席' THEN 1 ELSE 0 END) as present FROM attendance WHERE cycle='{current_cycle}'")
    month_att = Row([d[0] for d in cur.description], list(cur.fetchone()))

    cur.execute(f"SELECT COALESCE(SUM(amount),0) as t FROM purchases WHERE actual_pay_date LIKE '{month_str}%'")
    month_rev = Row([d[0] for d in cur.description], list(cur.fetchone()))

    # 待消课时：已购 - 实际出勤
    att_counts2 = attendance_student_counts()
    cur.execute("SELECT student_name, purchased_lessons FROM student_ext")
    pending_count = 0
    for row in cur.fetchall():
        used2 = att_counts2.get(row[0], 0)
        pur2 = int(row[1] or 0)
        if pur2 > used2: pending_count += (pur2 - used2)

    from datetime import timedelta
    now_dt = datetime.now()
    end_of_month = datetime(now_dt.year, now_dt.month + 1, 1) if now_dt.month < 12 else datetime(now_dt.year + 1, 1, 1)
    end_of_month = end_of_month - timedelta(days=1)
    days_left = (end_of_month - now_dt).days + 1
    weeks_left = min(4, max(0, days_left // 7 + (1 if days_left % 7 > 0 else 0)))
    cur.execute("SELECT COUNT(*) as cnt FROM config WHERE class_time != ''")
    weekly_row = cur.fetchone()
    weekly_count = int(weekly_row[0]) if weekly_row else 10
    # Get off weeks
    cur.execute("SELECT off_weeks FROM config WHERE off_weeks != ''")
    off_weeks_set = set()
    for r in cur.fetchall():
        for w in str(r[0] or "").split(","):
            w = w.strip()
            if w.isdigit(): off_weeks_set.add(int(w))
    current_week = (now_dt.day - 1) // 7 + 1
    weeks_in_range = set(range(current_week, current_week + weeks_left))
    off_count = len(weeks_in_range & off_weeks_set)
    schedule_remaining = (weeks_left - off_count) * weekly_count

    summary = {
        "active_students": int(active["cnt"] or 0),
        "month_lessons": int(month_att["lessons"] or 0),
        "month_present": int(month_att["present"] or 0),
        "cycle": current_cycle,
        "cycle_students": int(month_att["students"] or 0),
        "pending_paid": pending_count,
        "schedule_remaining": schedule_remaining,
        "month_revenue": float(month_rev["t"] or 0)
    }
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