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
    """一次查询返回 config 和 lessons 全量数据"""
    db = get_db()
    req = {"requests": [
        {"type": "execute", "stmt": {"sql": "SELECT class_name, unit_code, unit_name, path, created_by, class_time FROM config ORDER BY class_name"}},
        {"type": "execute", "stmt": {"sql": "SELECT class_name, unit_code, lesson_num, title, updated_at FROM lessons ORDER BY class_name, unit_code, lesson_num"}},
        {"type": "close"}
    ]}
    raw = db._req(req)
    results = raw.get('results', [])

    # Parse config result
    cfg = {}
    cfg_rows = db._parse_result({"results": [results[0]]})
    for r in cfg_rows:
        if r["class_name"] not in cfg:
            cfg[r["class_name"]] = {}
        cfg[r["class_name"]][r["unit_code"]] = {
            "name": r["unit_name"], "path": r["path"],
            "created_by": r["created_by"], "class_time": r["class_time"]
        }

    # Parse lessons result
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
    return cfg, lessons

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

# ------- Init -------
init_db()
