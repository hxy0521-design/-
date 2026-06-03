"""Turso cloud data layer — shared between 欣欣 and 饼干"""
import os, json, requests

TURSO_URL = "https://p-hxy0521-design.aws-ap-northeast-1.turso.io/v2/pipeline"
TURSO_TOKEN = os.environ.get("TURSO_TOKEN", "eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhIjoicnciLCJpYXQiOjE3ODAzMTk5MDEsImlkIjoiMDE5ZTgyZjEtMjcwMS03ZmM2LTlhYTUtYTk0NjYxMjMzMzI3IiwicmlkIjoiZjgwNDdmNzktMzY1NC00NGQ1LTk3MzMtMmU1YTZmODA1YjU4In0.OyXpfUJT7sE-giEIdYNYIyO0W-7Lkq41WJNEHFJ7vVKdrE3dyGmzJ3OvGatLWnl6dJ9MBxKloDzx45nZ5CaWDA")

class Row:
    """Simulate sqlite3.Row"""
    def __init__(self, cols, values):
        self._cols = cols
        self._vals = values
    def __getitem__(self, key):
        if isinstance(key, int):
            return self._vals[key]
        if isinstance(key, str):
            return self._vals[self._cols.index(key)] if key in self._cols else None
        raise TypeError
    def keys(self):
        return self._cols
    def values(self):
        return self._vals
    def items(self):
        return list(zip(self._cols, self._vals))

class Result:
    """Simulate sqlite3.Cursor after execute"""
    def __init__(self, cols, rows):
        self._rows = [Row(cols, r) for r in rows]
    def fetchall(self):
        return self._rows
    def fetchone(self):
        return self._rows[0] if self._rows else None
    def __iter__(self):
        return iter(self._rows)

class _TursoConn:
    def __init__(self):
        self.row_factory = Row
        self._url = TURSO_URL
        self._token = TURSO_TOKEN

    def _req(self, payload):
        resp = requests.post(self._url,
            headers={'Authorization': f'Bearer {self._token}', 'Content-Type': 'application/json'},
            json=payload, timeout=30)
        if resp.status_code != 200:
            raise Exception(f"Turso HTTP {resp.status_code}: {resp.text}")
        return resp.json()

    def _parse_result(self, raw):
        results = raw.get('results', [])
        last_result = None
        for r in results:
            if r.get('type') == 'ok' and r.get('response', {}).get('type') == 'execute':
                last_result = r['response'].get('result', {})
        if last_result:
            cols = [c['name'] for c in last_result.get('cols', [])]
            rows = [[v.get('value', v) if isinstance(v, dict) else v for v in row] for row in last_result.get('rows', [])]
            return Result(cols, rows)
        return Result([], [])

    def execute(self, sql, params=None):
        if params:
            # Turso pipeline doesn't support ? params — inline them
            parts = sql.split('?')
            result_sql = parts[0]
            for i, p in enumerate(params):
                if isinstance(p, (int, float)):
                    result_sql += str(p)
                elif p is None:
                    result_sql += 'NULL'
                else:
                    result_sql += "'" + str(p).replace("'", "''") + "'"
                result_sql += parts[i + 1] if i + 1 < len(parts) else ''
            sql = result_sql
        req = {"requests": [
            {"type": "execute", "stmt": {"sql": sql}},
            {"type": "close"}
        ]}
        raw = self._req(req)
        return self._parse_result(raw)

    def executescript(self, sql):
        stmts = [s.strip() for s in sql.split(';') if s.strip()]
        if not stmts: return self
        requests_list = [{"type": "execute", "stmt": {"sql": s}} for s in stmts]
        requests_list.append({"type": "close"})
        self._req({"requests": requests_list})
        return self

    def commit(self):
        pass  # Turso auto-commits

    def close(self):
        pass

def get_db():
    if not hasattr(get_db, "_conn"):
        get_db._conn = _TursoConn()
        get_db._conn.row_factory = Row
    return get_db._conn

def init_db():
    db = get_db()
    db.executescript("""
        CREATE TABLE IF NOT EXISTS config (
            class_name TEXT NOT NULL,
            unit_code TEXT NOT NULL,
            unit_name TEXT DEFAULT '',
            path TEXT DEFAULT '',
            created_by TEXT DEFAULT '',
            class_time TEXT DEFAULT '',
            PRIMARY KEY (class_name, unit_code)
        );
        CREATE TABLE IF NOT EXISTS students (
            class_name TEXT NOT NULL,
            student_name TEXT NOT NULL,
            gender TEXT DEFAULT '',
            lessons_json TEXT DEFAULT '[]',
            PRIMARY KEY (class_name, student_name)
        );
        CREATE TABLE IF NOT EXISTS recycle (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            class_name TEXT,
            unit_code TEXT,
            unit_name TEXT,
            path TEXT,
            deleted_at TEXT
        );
        CREATE TABLE IF NOT EXISTS lessons (
            class_name TEXT NOT NULL,
            unit_code TEXT NOT NULL,
            lesson_num INTEGER NOT NULL DEFAULT 1,
            title TEXT DEFAULT '',
            content TEXT DEFAULT '',
            updated_at TEXT DEFAULT '',
            PRIMARY KEY (class_name, unit_code, lesson_num)
        );
        CREATE TABLE IF NOT EXISTS student_ext (
            student_name TEXT NOT NULL PRIMARY KEY,
            student_code TEXT DEFAULT '',
            source TEXT DEFAULT '',
            status TEXT DEFAULT '',
            segment TEXT DEFAULT '',
            enrolled_class TEXT DEFAULT '',
            purchased_lessons INTEGER DEFAULT 0,
            used_lessons INTEGER DEFAULT 0,
            remaining_lessons INTEGER DEFAULT 0,
            notes TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            class_name TEXT NOT NULL,
            unit_code TEXT NOT NULL,
            lesson_num INTEGER NOT NULL,
            lesson_title TEXT DEFAULT '',
            lesson_date TEXT DEFAULT '',
            student_name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT '出席',
            note TEXT DEFAULT '',
            recorded_at TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS purchases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_name TEXT NOT NULL,
            student_code TEXT DEFAULT '',
            charge_code TEXT DEFAULT '',
            segment TEXT DEFAULT '',
            course_type TEXT DEFAULT '',
            method TEXT DEFAULT '',
            discount_type TEXT DEFAULT '',
            lesson_count INTEGER DEFAULT 0,
            amount REAL DEFAULT 0,
            refund_amount REAL DEFAULT 0,
            actual_pay_date TEXT DEFAULT '',
            order_id TEXT DEFAULT '',
            xiaohongshu_received REAL DEFAULT 0,
            notes TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS costs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reason TEXT DEFAULT '',
            cycle TEXT DEFAULT '',
            cost_type TEXT DEFAULT '',
            channel TEXT DEFAULT '',
            cost_date TEXT DEFAULT '',
            amount REAL DEFAULT 0,
            notes TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS class_roster (
            class_name TEXT NOT NULL,
            student_name TEXT NOT NULL,
            PRIMARY KEY (class_name, student_name)
        );
        CREATE TABLE IF NOT EXISTS pricing (
            segment TEXT NOT NULL,
            course_type TEXT NOT NULL DEFAULT '正式课',
            discount_type TEXT NOT NULL DEFAULT '一课一销',
            unit_price REAL NOT NULL DEFAULT 0,
            discount_multiplier REAL NOT NULL DEFAULT 1.0,
            PRIMARY KEY (segment, course_type, discount_type)
        );
        CREATE TABLE IF NOT EXISTS teacher_coefficients (
            teacher_name TEXT NOT NULL PRIMARY KEY,
            coefficient REAL DEFAULT 1.0,
            hourly_rate REAL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS revenue_splits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cycle TEXT DEFAULT '',
            content TEXT DEFAULT '',
            expected_revenue REAL DEFAULT 0,
            trial_count INTEGER DEFAULT 0,
            formal_count INTEGER DEFAULT 0,
            lesson_50pct REAL DEFAULT 0,
            research_ratio REAL DEFAULT 0.15,
            research_xinxin_coef REAL DEFAULT 0.9,
            research_xinxin REAL DEFAULT 0,
            research_sitong_coef REAL DEFAULT 0.1,
            research_sitong REAL DEFAULT 0,
            research_biscuit_coef REAL DEFAULT 0,
            research_biscuit REAL DEFAULT 0,
            source_20pct REAL DEFAULT 0,
            new_enroll INTEGER DEFAULT 0,
            recruitment_trial REAL DEFAULT 0,
            renewal_remaining REAL DEFAULT 0,
            neukol_fee REAL DEFAULT 0,
            other_cost REAL DEFAULT 0,
            notes TEXT DEFAULT ''
        );
    """)
    db.commit()

def migrate_from_json():
    """仅本地迁移用，云端数据库跳过"""
    pass

# ------- Config API -------

def config_all():
    """返回 {class_name: {unit_code: {name, path, created_by, class_time}}}"""
    db = get_db()
    rows = db.execute("SELECT class_name, unit_code, unit_name, path, created_by, class_time FROM config ORDER BY class_name").fetchall()
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
    """全量覆盖 config 表"""
    db = get_db()
    # Use multiple statements in one pipeline
    stmts = ["DELETE FROM config"]
    for cls_name, units in cfg.items():
        for unit_code, info in units.items():
            name = info.get("name","").replace("'", "''")
            path = info.get("path","").replace("'", "''")
            cb = info.get("created_by","").replace("'", "''")
            ct = info.get("class_time","").replace("'", "''")
            cn = cls_name.replace("'", "''")
            stmts.append(f"INSERT OR REPLACE INTO config VALUES ('{cn}','{unit_code}','{name}','{path}','{cb}','{ct}')")
    for s in stmts:
        db.execute(s)

def config_add_class(cls_name, created_by="", class_time=""):
    db = get_db()
    r = db.execute("SELECT COUNT(*) as cnt FROM config WHERE class_name=? AND unit_code!=''", [cls_name]).fetchone()
    if r and r["cnt"] > 0: return
    db.execute("INSERT OR REPLACE INTO config (class_name, unit_code, unit_name, path, created_by, class_time) VALUES (?,?,?,?,?,?)",
        [cls_name, "2605", cls_name, "", created_by, class_time])

def config_remove_class(cls_name):
    db = get_db()
    db.execute("DELETE FROM config WHERE class_name=?", [cls_name])

def config_add_unit(cls_name, unit_code, unit_name, path, created_by=""):
    db = get_db()
    db.execute("INSERT OR REPLACE INTO config VALUES (?,?,?,?,?,?)",
        [cls_name, unit_code, unit_name, path, created_by, ""])

def config_remove_unit(cls_name, unit_code):
    db = get_db()
    db.execute("DELETE FROM config WHERE class_name=? AND unit_code=?", [cls_name, unit_code])

def config_get_unit(cls_name, unit_code):
    db = get_db()
    r = db.execute("SELECT unit_name, path FROM config WHERE class_name=? AND unit_code=?",
        [cls_name, unit_code]).fetchone()
    return {"name": r["unit_name"], "path": r["path"]} if r else {}

def config_update_unit_path(cls_name, unit_code, path):
    db = get_db()
    db.execute("UPDATE config SET path=? WHERE class_name=? AND unit_code=?", [path, cls_name, unit_code])

# ------- Lessons (TXT content in cloud) -------

def lesson_list(cls_name, unit_code):
    """返回课节列表，格式同 scan_lessons"""
    return lesson_list_batch().get(cls_name, {}).get(unit_code, [])

def config_and_lessons():
    """一次查询返回 config、lessons、dashboard summary、weekly 全量数据"""
    db = get_db()
    now = __import__('datetime').datetime.now()
    month_str = now.strftime("%Y-%m")
    req = {"requests": [
        {"type": "execute", "stmt": {"sql": "SELECT class_name, unit_code, unit_name, path, created_by, class_time FROM config ORDER BY class_name"}},
        {"type": "execute", "stmt": {"sql": "SELECT class_name, unit_code, lesson_num, title, updated_at FROM lessons ORDER BY class_name, unit_code, lesson_num"}},
        {"type": "execute", "stmt": {"sql": "SELECT COUNT(*) as cnt FROM student_ext WHERE status='在读中'"}},
        {"type": "execute", "stmt": {"sql": f"SELECT COUNT(*) as cnt, SUM(CASE WHEN status='出席' THEN 1 ELSE 0 END) as present FROM attendance WHERE lesson_date LIKE '{month_str}%'"}},
        {"type": "execute", "stmt": {"sql": f"SELECT COALESCE(SUM(amount),0) as t FROM purchases WHERE actual_pay_date LIKE '{month_str}%'"}},
        {"type": "close"}
    ]}
    raw = db._req(req)
    results = raw.get('results', [])

    def _v(val, default=0):
        if not val: return default
        if isinstance(val, dict): val = val.get("value", default)
        return int(val) if val and str(val).replace('-','').isdigit() else (float(val) if val else default)

    # Parse config
    cfg = {}
    cfg_rows = db._parse_result({"results": [results[0]]})
    for r in cfg_rows:
        if r["class_name"] not in cfg:
            cfg[r["class_name"]] = {}
        cfg[r["class_name"]][r["unit_code"]] = {
            "name": r["unit_name"], "path": r["path"],
            "created_by": r["created_by"], "class_time": r["class_time"]
        }

    # Parse lessons
    lessons = {}
    lesson_rows = db._parse_result({"results": [results[1]]})
    for r in lesson_rows:
        cn, uc = r["class_name"], r["unit_code"]
        unit_name = cfg.get(cn, {}).get(uc, {}).get("name", uc)
        if cn not in lessons: lessons[cn] = {}
        if uc not in lessons[cn]: lessons[cn][uc] = []
        lessons[cn][uc].append({
            "folder": f"{cn}-{uc}-{r['lesson_num']}",
            "lesson": str(r["lesson_num"]),
            "title": r["title"],
            "date": (r["updated_at"] or "")[:10],
            "unit_name": unit_name
        })

    # Parse dashboard summary
    active = db._parse_result({"results": [results[2]]}).fetchone()
    month_att = db._parse_result({"results": [results[3]]}).fetchone()
    month_rev = db._parse_result({"results": [results[4]]}).fetchone()
    summary = {
        "active_students": _v(active["cnt"]) if active else 0,
        "month_lessons": _v(month_att["cnt"]) if month_att else 0,
        "month_present": _v(month_att["present"]) if month_att else 0,
        "month_revenue": float(month_rev["t"]) if month_rev and month_rev["t"] else 0.0
    }

    # Build weekly schedule from config
    from datetime import datetime, timedelta
    now_dt = datetime.now()
    monday = now_dt - timedelta(days=now_dt.weekday())
    _DAY_MAP = {"一":"周一","二":"周二","三":"周三","四":"周四","五":"周五","六":"周六","日":"周日"}
    weekly = []
    for cn, units in cfg.items():
        ct = list(units.values())[0].get("class_time", "")
        cb = list(units.values())[0].get("created_by", "")
        weekday_cn = cn[1] if len(cn) > 1 else ""
        weekday = _DAY_MAP.get(weekday_cn, "")
        roster = roster_get(cn)
        weekly.append({
            "class_name": cn, "time": ct, "teacher": cb,
            "weekday": weekday, "students": roster,
            "color": "#8b5cf6" if cb == "欣欣" else "#3b82f6"
        })

    return cfg, lessons, summary, weekly

def lesson_list_batch():
    """一次查询返回所有课节 {class_name: {unit_code: [{lesson_dict}, ...]}}"""
    db = get_db()
    cfg = config_all()
    rows = db.execute("SELECT class_name, unit_code, lesson_num, title, updated_at FROM lessons ORDER BY class_name, unit_code, lesson_num").fetchall()
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
    """返回课节 TXT 内容"""
    db = get_db()
    r = db.execute(
        "SELECT title, content FROM lessons WHERE class_name=? AND unit_code=? AND lesson_num=?",
        [cls_name, unit_code, lesson_num]).fetchone()
    return (r["title"], r["content"]) if r else ("", "")

def lesson_save(cls_name, unit_code, lesson_num, title, content):
    """保存课节 TXT 内容"""
    from datetime import datetime
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db = get_db()
    # Check if exists
    r = db.execute(
        "SELECT lesson_num FROM lessons WHERE class_name=? AND unit_code=? AND lesson_num=?",
        [cls_name, unit_code, lesson_num]).fetchone()
    if r:
        db.execute(
            "UPDATE lessons SET title=?, content=?, updated_at=? WHERE class_name=? AND unit_code=? AND lesson_num=?",
            [title, content, now, cls_name, unit_code, lesson_num])
    else:
        db.execute(
            "INSERT INTO lessons (class_name, unit_code, lesson_num, title, content, updated_at) VALUES (?,?,?,?,?,?)",
            [cls_name, unit_code, lesson_num, title, content, now])

# ------- Student Profiles -------

def profiles_load(cls_name=None):
    db = get_db()
    if cls_name:
        rows = db.execute("SELECT student_name, gender, lessons_json FROM students WHERE class_name=?",
            [cls_name]).fetchall()
    else:
        rows = db.execute("SELECT class_name, student_name, gender, lessons_json FROM students").fetchall()
    result = {}
    for r in rows:
        cn = cls_name or r["class_name"]
        if cn not in result:
            result[cn] = {}
        result[cn][r["student_name"]] = {
            "gender": r["gender"],
            "lessons": json.loads(r["lessons_json"]) if r["lessons_json"] else []
        }
    return result

def profiles_save_lesson(cls_name, name, date, title, speech_count, topic_count, traits, best_quote):
    db = get_db()
    r = db.execute("SELECT gender, lessons_json FROM students WHERE class_name=? AND student_name=?",
        [cls_name, name]).fetchone()
    if r:
        lessons = json.loads(r["lessons_json"]) if r["lessons_json"] else []
    else:
        lessons = []
    for l in lessons:
        if l.get("date") == date and l.get("title") == title:
            l["speech_count"] = speech_count
            l["topics"] = topic_count
            l["traits"] = traits
            l["best_quote"] = best_quote
            db.execute("UPDATE students SET lessons_json=? WHERE class_name=? AND student_name=?",
                [json.dumps(lessons, ensure_ascii=False), cls_name, name])
            return
    lessons.append({
        "date": date, "title": title,
        "speech_count": speech_count, "topics": topic_count,
        "traits": traits, "best_quote": best_quote
    })
    gender = r["gender"] if r else ""
    db.execute("INSERT OR REPLACE INTO students (class_name, student_name, gender, lessons_json) VALUES (?,?,?,?)",
        [cls_name, name, gender, json.dumps(lessons, ensure_ascii=False)])

def profiles_save_gender(cls_name, all_names, gender_map, default_gender):
    db = get_db()
    for name in all_names:
        g = gender_map.get(name, default_gender)
        r = db.execute("SELECT lessons_json FROM students WHERE class_name=? AND student_name=?",
            [cls_name, name]).fetchone()
        lessons = r["lessons_json"] if r else "[]"
        db.execute("INSERT OR REPLACE INTO students (class_name, student_name, gender, lessons_json) VALUES (?,?,?,?)",
            [cls_name, name, g, lessons])

def profiles_delete_class(cls_name):
    db = get_db()
    db.execute("DELETE FROM students WHERE class_name=?", [cls_name])

# ------- Recycle Bin -------

def recycle_add(info):
    db = get_db()
    db.execute("INSERT INTO recycle (class_name, unit_code, unit_name, path, deleted_at) VALUES (?,?,?,?,?)",
        [info.get("class",""), info.get("unit_code",""), info.get("name",""), info.get("path",""), info.get("deleted_at","")])

def recycle_all():
    db = get_db()
    return [dict(zip(["id","class_name","unit_code","unit_name","path","deleted_at"],
        [r["id"],r["class_name"],r["unit_code"],r["unit_name"],r["path"],r["deleted_at"]]))
        for r in db.execute("SELECT * FROM recycle ORDER BY id DESC").fetchall()]

# ------- Student Ext -------

def student_ext_all():
    db = get_db()
    rows = db.execute("SELECT * FROM student_ext ORDER BY student_name").fetchall()
    return [dict(zip(["student_name","student_code","source","status","segment","enrolled_class","purchased_lessons","used_lessons","remaining_lessons","notes"], [r[col] for col in ["student_name","student_code","source","status","segment","enrolled_class","purchased_lessons","used_lessons","remaining_lessons","notes"]])) for r in rows]

def student_ext_upsert(name, data):
    db = get_db()
    r = db.execute("SELECT student_name FROM student_ext WHERE student_name=?", [name]).fetchone()
    if r:
        db.execute("UPDATE student_ext SET student_code=?,source=?,status=?,segment=?,enrolled_class=?,purchased_lessons=?,used_lessons=?,remaining_lessons=?,notes=? WHERE student_name=?",
            [data.get("student_code",""), data.get("source",""), data.get("status",""), data.get("segment",""), data.get("enrolled_class",""), int(data.get("purchased_lessons",0)), int(data.get("used_lessons",0)), int(data.get("remaining_lessons",0)), data.get("notes",""), name])
    else:
        db.execute("INSERT INTO student_ext (student_name,student_code,source,status,segment,enrolled_class,purchased_lessons,used_lessons,remaining_lessons,notes) VALUES (?,?,?,?,?,?,?,?,?,?)",
            [name, data.get("student_code",""), data.get("source",""), data.get("status",""), data.get("segment",""), data.get("enrolled_class",""), int(data.get("purchased_lessons",0)), int(data.get("used_lessons",0)), int(data.get("remaining_lessons",0)), data.get("notes","")])

# ------- Attendance -------

def attendance_batch(records):
    """records = [{class_name, unit_code, lesson_num, lesson_title, lesson_date, student_name, status, note}]"""
    from datetime import datetime
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db = get_db()
    for r in records:
        # Delete existing record for this student+lesson
        db.execute("DELETE FROM attendance WHERE class_name=? AND lesson_num=? AND student_name=?",
            [r["class_name"], r["lesson_num"], r["student_name"]])
        db.execute("INSERT INTO attendance (class_name,unit_code,lesson_num,lesson_title,lesson_date,student_name,status,note,recorded_at) VALUES (?,?,?,?,?,?,?,?,?)",
            [r["class_name"], r.get("unit_code",""), r["lesson_num"], r.get("lesson_title",""), r.get("lesson_date",""), r["student_name"], r.get("status","出席"), r.get("note",""), now])

def attendance_get(class_name=None, date_from=None, date_to=None):
    db = get_db()
    sql = "SELECT * FROM attendance WHERE 1=1"
    params = []
    if class_name:
        sql += " AND class_name=?"
        params.append(class_name)
    if date_from:
        sql += " AND lesson_date >= ?"
        params.append(date_from)
    if date_to:
        sql += " AND lesson_date <= ?"
        params.append(date_to)
    sql += " ORDER BY lesson_date DESC, class_name, student_name"
    rows = db.execute(sql, params).fetchall()
    return [dict(zip(["id","class_name","unit_code","lesson_num","lesson_title","lesson_date","student_name","status","note","recorded_at"], [r[c] for c in ["id","class_name","unit_code","lesson_num","lesson_title","lesson_date","student_name","status","note","recorded_at"]])) for r in rows]

def attendance_stats(class_name=None):
    db = get_db()
    sql = "SELECT status, COUNT(*) as cnt FROM attendance WHERE 1=1"
    params = []
    if class_name:
        sql += " AND class_name=?"
        params.append(class_name)
    sql += " GROUP BY status"
    rows = db.execute(sql, params).fetchall()
    return {r["status"]: r["cnt"] for r in rows}

# ------- Class Roster -------

def roster_get(class_name):
    db = get_db()
    rows = db.execute("SELECT student_name FROM class_roster WHERE class_name=? ORDER BY student_name", [class_name]).fetchall()
    return [r["student_name"] for r in rows]

def roster_set(class_name, students):
    db = get_db()
    db.execute("DELETE FROM class_roster WHERE class_name=?", [class_name])
    for s in students:
        db.execute("INSERT INTO class_roster (class_name,student_name) VALUES (?,?)", [class_name, s])

# ------- Purchases -------

def purchase_add(data):
    db = get_db()
    oid = data.get("order_id","")
    if oid:
        r = db.execute("SELECT id FROM purchases WHERE order_id=?", [oid]).fetchone()
        if r:
            # Update existing by order_id
            db.execute("UPDATE purchases SET student_name=?,student_code=?,charge_code=?,segment=?,course_type=?,method=?,discount_type=?,lesson_count=?,amount=?,refund_amount=?,actual_pay_date=?,xiaohongshu_received=?,notes=? WHERE order_id=?",
                [data.get("student_name",""), data.get("student_code",""), data.get("charge_code",""), data.get("segment",""), data.get("course_type",""), data.get("method",""), data.get("discount_type",""), int(data.get("lesson_count",0)), float(data.get("amount",0)), float(data.get("refund_amount",0)), data.get("actual_pay_date",""), float(data.get("xiaohongshu_received",0)), data.get("notes",""), oid])
            return "updated"
    db.execute("INSERT INTO purchases (student_name,student_code,charge_code,segment,course_type,method,discount_type,lesson_count,amount,refund_amount,actual_pay_date,order_id,xiaohongshu_received,notes) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [data.get("student_name",""), data.get("student_code",""), data.get("charge_code",""), data.get("segment",""), data.get("course_type",""), data.get("method",""), data.get("discount_type",""), int(data.get("lesson_count",0)), float(data.get("amount",0)), float(data.get("refund_amount",0)), data.get("actual_pay_date",""), oid, float(data.get("xiaohongshu_received",0)), data.get("notes","")])
    return "new"

def purchase_list(student_name=None, date_from=None, date_to=None, limit=200):
    db = get_db()
    sql = "SELECT * FROM purchases WHERE 1=1"
    params = []
    if student_name:
        sql += " AND student_name=?"
        params.append(student_name)
    if date_from:
        sql += " AND actual_pay_date >= ?"
        params.append(date_from)
    if date_to:
        sql += " AND actual_pay_date <= ?"
        params.append(date_to)
    sql += " ORDER BY actual_pay_date DESC LIMIT ?"
    params.append(limit)
    rows = db.execute(sql, params).fetchall()
    cols = ["id","student_name","student_code","charge_code","segment","course_type","method","discount_type","lesson_count","amount","refund_amount","actual_pay_date","order_id","xiaohongshu_received","notes"]
    return [dict(zip(cols, [r[c] for c in cols])) for r in rows]

# ------- Costs -------

def cost_add(data):
    db = get_db()
    db.execute("INSERT INTO costs (reason,cycle,cost_type,channel,cost_date,amount,notes) VALUES (?,?,?,?,?,?,?)",
        [data.get("reason",""), data.get("cycle",""), data.get("cost_type",""), data.get("channel",""), data.get("cost_date",""), float(data.get("amount",0)), data.get("notes","")])

def cost_list(limit=200):
    db = get_db()
    rows = db.execute("SELECT * FROM costs ORDER BY cost_date DESC LIMIT ?", [limit]).fetchall()
    cols = ["id","reason","cycle","cost_type","channel","cost_date","amount","notes"]
    return [dict(zip(cols, [r[c] for c in cols])) for r in rows]

# ------- Pricing -------

def pricing_all():
    db = get_db()
    rows = db.execute("SELECT * FROM pricing ORDER BY segment, course_type, discount_type").fetchall()
    cols = ["segment","course_type","discount_type","unit_price","discount_multiplier"]
    return [dict(zip(cols, [r[c] for c in cols])) for r in rows]

def pricing_set(segment, course_type, discount_type, unit_price, discount_multiplier):
    db = get_db()
    db.execute("INSERT OR REPLACE INTO pricing (segment,course_type,discount_type,unit_price,discount_multiplier) VALUES (?,?,?,?,?)",
        [segment, course_type, discount_type, float(unit_price), float(discount_multiplier)])

def calc_price(segment, course_type, discount_type, lesson_count):
    db = get_db()
    r = db.execute("SELECT unit_price, discount_multiplier FROM pricing WHERE segment=? AND course_type=? AND discount_type=?", [segment, course_type, discount_type]).fetchone()
    if r:
        return float(r["unit_price"]) * int(lesson_count) * float(r["discount_multiplier"])
    return 0

def init_pricing():
    """预填 Excel 定价公式的基准值"""
    defaults = [
        ("启航段","正式课","一课一销",160,1.0), ("启航段","正式课","月度9折",160,0.9), ("启航段","正式课","亲友85折",160,0.85),
        ("探索段","正式课","一课一销",180,1.0), ("探索段","正式课","月度9折",180,0.9), ("探索段","正式课","亲友85折",180,0.85),
        ("先锋段","正式课","一课一销",200,1.0), ("先锋段","正式课","月度9折",200,0.9),
        ("领航1V1","正式课","一课一销",385,1.0), ("领航1V1","正式课","月度9折",385,0.9),
        ("领航1V2","正式课","一课一销",330,1.0),
        ("成人班","正式课","一课一销",69.9,1.0),
        ("领航1V1","试听课","试听折扣",99.9,1.0),
        ("探索段","试听课","试听折扣",69.9,1.0), ("启航段","试听课","试听折扣",69.9,1.0), ("先锋段","试听课","试听折扣",69.9,1.0),
        ("混龄特典","正式课","单人特典",69.9,1.0), ("混龄特典","正式课","亲子特典",109.9,1.0),
    ]
    for s, ct, dt, price, mult in defaults:
        pricing_set(s, ct, dt, price, mult)

# ------- Finance Summary -------

def finance_summary():
    db = get_db()
    rev = db.execute("SELECT COALESCE(SUM(amount),0) as t FROM purchases").fetchone()
    cost = db.execute("SELECT COALESCE(SUM(amount),0) as t FROM costs").fetchone()
    students = db.execute("SELECT COUNT(*) as t FROM student_ext WHERE status='在读中'").fetchone()
    return {"total_revenue": float(rev["t"]), "total_cost": float(cost["t"]), "balance": float(rev["t"])-float(cost["t"]), "active_students": int(students["t"])}

# ------- Dashboard -------

def dashboard_summary():
    db = get_db()
    def _v(row, key, default=0):
        if not row: return default
        val = row[key]
        if isinstance(val, dict): val = val.get("value", default)
        return int(val) if val else default
    def _f(row, key, default=0.0):
        if not row: return default
        val = row[key]
        if isinstance(val, dict): val = val.get("value", default)
        return float(val) if val else default
    active = db.execute("SELECT COUNT(*) as cnt FROM student_ext WHERE status='在读中'").fetchone()
    now = __import__('datetime').datetime.now()
    month_str = now.strftime("%Y-%m")
    month_att = db.execute("SELECT COUNT(*) as cnt, SUM(CASE WHEN status='出席' THEN 1 ELSE 0 END) as present FROM attendance WHERE lesson_date LIKE ?", [month_str + "%"]).fetchone()
    total_purchases = db.execute("SELECT COALESCE(SUM(amount),0) as t FROM purchases WHERE actual_pay_date LIKE ?", [month_str + "%"]).fetchone()
    return {
        "active_students": _v(active, "cnt"),
        "month_lessons": _v(month_att, "cnt"),
        "month_present": _v(month_att, "present"),
        "month_revenue": _f(total_purchases, "t")
    }

def dashboard_weekly():
    """当周课表：从 config 和 class_roster 构建"""
    cfg = config_all()
    from datetime import datetime, timedelta
    now = datetime.now()
    monday = now - timedelta(days=now.weekday())
    days = [(monday + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)]
    day_names = ["周一","周二","周三","周四","周五","周六","周日"]
    _DAY_MAP = {"一":"周一","二":"周二","三":"周三","四":"周四","五":"周五","六":"周六","日":"周日"}
    result = []
    for cn, units in cfg.items():
        ct = list(units.values())[0].get("class_time", "")
        cb = list(units.values())[0].get("created_by", "")
        # Find the weekday from the class name
        weekday_cn = cn[1] if len(cn) > 1 else ""
        weekday = _DAY_MAP.get(weekday_cn, "")
        roster = roster_get(cn)
        result.append({
            "class_name": cn, "time": ct, "teacher": cb,
            "weekday": weekday, "students": roster,
            "color": "#8b5cf6" if cb == "欣欣" else "#3b82f6"
        })
    return result

# ------- Teacher Coefficients -------

def teacher_coefficients_all():
    db = get_db()
    rows = db.execute("SELECT * FROM teacher_coefficients").fetchall()
    return [{"teacher_name": r["teacher_name"], "coefficient": r["coefficient"], "hourly_rate": r["hourly_rate"]} for r in rows]

def teacher_coefficient_set(name, coefficient, hourly_rate):
    db = get_db()
    db.execute("INSERT OR REPLACE INTO teacher_coefficients VALUES (?,?,?)", [name, float(coefficient), float(hourly_rate)])

# ------- Revenue Splits -------

def revenue_split_list(cycle=None):
    db = get_db()
    if cycle:
        rows = db.execute("SELECT * FROM revenue_splits WHERE cycle=? ORDER BY id", [cycle]).fetchall()
    else:
        rows = db.execute("SELECT * FROM revenue_splits ORDER BY id").fetchall()
    cols = ["id","cycle","content","expected_revenue","trial_count","formal_count","lesson_50pct","research_ratio","research_xinxin_coef","research_xinxin","research_sitong_coef","research_sitong","research_biscuit_coef","research_biscuit","source_20pct","new_enroll","recruitment_trial","renewal_remaining","neukol_fee","other_cost","notes"]
    return [dict(zip(cols, [r[c] for c in cols])) for r in rows]

def revenue_split_upsert(data):
    db = get_db()
    rid = data.get("id", 0)
    fields = ["cycle","content","expected_revenue","trial_count","formal_count","lesson_50pct","research_ratio","research_xinxin_coef","research_xinxin","research_sitong_coef","research_sitong","research_biscuit_coef","research_biscuit","source_20pct","new_enroll","recruitment_trial","renewal_remaining","neukol_fee","other_cost","notes"]
    vals = [data.get(f, 0) if f not in ("cycle","content","notes") else data.get(f, "") for f in fields]
    if rid:
        sets = ", ".join(f"{f}=?" for f in fields)
        db.execute(f"UPDATE revenue_splits SET {sets} WHERE id=?", vals + [rid])
    else:
        placeholders = ",".join(["?"]*len(fields))
        db.execute(f"INSERT INTO revenue_splits ({','.join(fields)}) VALUES ({placeholders})", vals)

# ------- Attendance by Lesson -------

def attendance_by_lesson(class_name=None, limit=50):
    db = get_db()
    def _v(val, default=0):
        if isinstance(val, dict): val = val.get("value", default)
        return int(val) if val else default
    sql = "SELECT class_name, unit_code, lesson_num, lesson_title, lesson_date, COUNT(*) as total, SUM(CASE WHEN status='出席' THEN 1 ELSE 0 END) as present FROM attendance WHERE 1=1"
    params = []
    if class_name:
        sql += " AND class_name=?"
        params.append(class_name)
    sql += " GROUP BY class_name, lesson_num, lesson_date ORDER BY lesson_date DESC, class_name LIMIT ?"
    params.append(limit)
    rows = db.execute(sql, params).fetchall()
    return [{"class_name": r["class_name"], "lesson_num": _v(r["lesson_num"]), "lesson_title": r["lesson_title"], "lesson_date": r["lesson_date"], "total": _v(r["total"]), "present": _v(r["present"])} for r in rows]

# ------- Purchases paginated -------
def purchases_paginated(page=1, limit=100):
    db = get_db()
    def _v(val, default=""):
        if val is None: return default
        if isinstance(val, dict): val = val.get("value", default)
        return val
    offset = (page - 1) * limit
    total = db.execute("SELECT COUNT(*) as cnt FROM purchases").fetchone()
    tc = _v(total["cnt"], 0) if total else 0
    rows = db.execute("SELECT * FROM purchases ORDER BY COALESCE(actual_pay_date,'0000') DESC, id DESC LIMIT ? OFFSET ?", [limit, offset]).fetchall()
    cols = ["id","student_name","student_code","charge_code","segment","course_type","method","discount_type","lesson_count","amount","refund_amount","actual_pay_date","order_id","xiaohongshu_received","notes"]
    return {"total": int(tc), "page": page, "limit": limit, "rows": [dict(zip(cols, [_v(r[c]) for c in cols])) for r in rows]}

# ------- Init -------
init_db()
init_pricing()
# 初始化老师系数默认值
for n, c, r in [("欣欣", 0.9, 0), ("思童", 0.1, 0), ("饼干", 0, 0)]:
    if not get_db().execute("SELECT teacher_name FROM teacher_coefficients WHERE teacher_name=?", [n]).fetchone():
        teacher_coefficient_set(n, c, r)
