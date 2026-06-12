"""
追光π 课后素材 · Web UI
python3 server.py → http://localhost:5888
"""
import sys, os, json, tempfile, shutil, ssl
sys.dont_write_bytecode = True
ssl._create_default_https_context = ssl._create_unverified_context
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, request, jsonify, send_from_directory
app = Flask(__name__, static_folder='static')
app.json.sort_keys = False

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_SHARED = os.path.expanduser("~/Library/Mobile Documents/com~apple~CloudDocs/追光π课后素材生成系统")
_DEFAULT_WORK = os.environ.get("ZG_WORK", "/Users/meowmeow/追光π/2605春季班/2605课后材料")
os.environ.setdefault("ZG_DB", os.path.join(_SHARED, "data.db"))
_PORT = int(os.environ.get("ZG_PORT", "5888"))
_DAY_ORDER = {'四':1,'五':2,'六':3,'日':4,'一':5,'二':6,'三':7}

import db
db.init_db()
db.migrate_from_json()

def _time_minutes(t):
    """'HH:MM' → 分钟数，无效则返回一个大数排到最后"""
    try:
        parts = t.split(':')
        return int(parts[0])*60 + int(parts[1])
    except: return 99999

def sort_class_names(names):
    cfg = db.config_all()
    def _key(x):
        day = _DAY_ORDER.get(x[1] if len(x)>1 else '', 99)
        # 取该班级第一个单元的 class_time
        tm = 99999
        if x in cfg:
            for u in cfg[x].values():
                t = u.get('class_time', '')
                if t:
                    tm = _time_minutes(t)
                    break
        return (day, tm, x)
    return sorted(names, key=_key)

def get_config():
    return db.config_all()

def cls_from_folder(folder):
    import re
    # 先去掉 -new 后缀
    if folder.endswith('-new'):
        folder = folder[:-4]
    m = re.match(r'(.+)-(\d{4})-\d+', folder)
    return m.group(1) if m else folder

def unit_from_folder(folder):
    import re
    m = re.match(r'.+-(\d{4})-\d+', folder)
    return m.group(1) if m else "2605"

def unit_path(cls_name, unit_code):
    u = db.config_get_unit(cls_name, unit_code)
    return u.get("path", "")

# ====== Helpers ======

def find_cards(folder, base_path):
    cards = []
    fp = os.path.join(base_path, folder)
    if os.path.isdir(fp):
        for c in sorted(os.listdir(fp)):
            if c.startswith("单人总结_") and c.endswith(".png"):
                cards.append({"name": c, "path": f"/api/file/{folder}/{c}"})
    return cards

def find_golden(folder, cls_name, base_path):
    g = []
    fp = os.path.join(base_path, folder)
    if os.path.isdir(fp):
        for f in sorted(os.listdir(fp)):
            if "_金句_" in f and f.endswith(".png"):
                g.append({"name": f"金句/{f}", "path": f"/api/file/{folder}/{f}"})
    d2 = os.path.join(base_path, folder, f"金句_{cls_name}")
    if os.path.isdir(d2):
        for f in sorted(os.listdir(d2)):
            if f.endswith(".png"):
                g.append({"name": f"金句/{f}", "path": f"/api/file/{folder}/金句_{cls_name}/{f}"})
    return g

def scan_lessons(cls_name, unit_code, unit_path_dir):
    """从 Turso 读取课节列表"""
    return db.lesson_list(cls_name, unit_code)

# ====== API ======

@app.route("/")
def index():
    return send_from_directory(os.path.join(BASE_DIR, "static"), "index.html")

@app.route("/test")
def test_page():
    return send_from_directory(os.path.join(BASE_DIR, "static"), "test.html")

_CONFIG_CACHE = {"data": None, "ts": 0}
_ATT_CACHE = {}
def _clear_config_cache():
    _CONFIG_CACHE["ts"] = 0
    _ATT_CACHE.clear()

@app.route("/api/config")
def get_config_api():
    import time
    now = time.time()
    if _CONFIG_CACHE["data"] and (now - _CONFIG_CACHE["ts"]) < 60:
        return jsonify(_CONFIG_CACHE["data"])
    from collections import OrderedDict
    cfg, all_lessons, summary, weekly = db.config_and_lessons()
    out = OrderedDict()
    for k in sort_class_names(cfg.keys()):
        out[k] = cfg[k]
    zg_user = os.environ.get("ZG_USER", "")
    data = {"classes": out, "lessons": all_lessons, "zg_user": zg_user, "summary": summary, "weekly": weekly}
    _CONFIG_CACHE["data"] = data
    _CONFIG_CACHE["ts"] = now
    return jsonify(data)

@app.route("/api/pick-folder")
def pick_folder():
    import subprocess, platform
    p = ""
    try:
        if platform.system() == "Darwin":
            r = subprocess.run(["osascript", "-e",
                'tell application "System Events" to activate',
                "-e", 'set f to choose folder with prompt "选择课后素材的存放文件夹，如「2605课后材料」"',
                "-e", 'return POSIX path of f'],
                capture_output=True, text=True, timeout=60)
            p = r.stdout.strip()
        else:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk(); root.withdraw()
            p = filedialog.askdirectory(title="选择输出目录") or ""
            root.destroy()
    except: pass
    if p and os.path.isdir(p):
        return jsonify({"path": p})
    return jsonify({"path": ""})

@app.route("/api/classes")
def list_classes():
    cfg = get_config()
    if not cfg: return jsonify({})
    from collections import OrderedDict
    # 一次查询所有课节（避免 N 次 Turso HTTP 请求）
    all_lessons = db.lesson_list_batch()
    cls = OrderedDict()
    for class_name in sort_class_names(cfg.keys()):
        cls[class_name] = {}
        for unit_code, info in cfg[class_name].items():
            ls = all_lessons.get(class_name, {}).get(unit_code, [])
            cls[class_name][unit_code] = ls
            if not ls:
                cls[class_name][unit_code] = [{"folder":"","lesson":"","title":"","date":"","unit_name": info.get("name", unit_code)}]
    return jsonify(cls)

@app.route("/api/classes", methods=["POST"])
def create_class():
    data = request.json
    name = data.get("name", "").strip()
    if not name: return jsonify({"status": "error", "message": "班级名不能为空"}), 400
    cfg = get_config()
    if name in cfg: return jsonify({"status": "error", "message": "班级已存在"}), 400
    created_by = data.get("created_by", "").strip()
    class_time = data.get("class_time", "").strip()
    db.config_add_class(name, created_by, class_time)
    _clear_config_cache(); return jsonify({"status": "ok", "name": name})

@app.route("/api/classes/<cls_name>", methods=["DELETE"])
def delete_class(cls_name):
    cfg = get_config()
    if cls_name not in cfg: return jsonify({"status": "error", "message": "班级不存在"}), 404
    ts = __import__('datetime').datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for uc, info in cfg[cls_name].items():
        db.recycle_add({"class": cls_name, "unit_code": uc, "name": info.get("name",""), "path": info.get("path",""), "deleted_at": ts})
    recycle_dir = os.path.join(BASE_DIR, "recycle")
    os.makedirs(recycle_dir, exist_ok=True)
    ts_dir = ts.replace(" ", "_").replace(":", "-")
    for uc, info in cfg[cls_name].items():
        p = info.get("path", "")
        if p and os.path.isdir(p):
            dest = os.path.join(recycle_dir, f"{cls_name}_{uc}_{ts_dir}")
            os.makedirs(dest, exist_ok=True)
            for f in os.listdir(p):
                if f.startswith(f"{cls_name}-") and os.path.isdir(os.path.join(p, f)):
                    shutil.move(os.path.join(p, f), os.path.join(dest, f))
    db.config_remove_class(cls_name)
    _clear_config_cache(); return jsonify({"status": "ok"})

@app.route("/api/classes/<cls_name>/units", methods=["POST"])
def create_unit(cls_name):
    cfg = get_config()
    if cls_name not in cfg: return jsonify({"status": "error", "message": "班级不存在"}), 404
    data = request.json
    unit_code = data.get("code", "").strip()
    unit_name = data.get("name", "").strip()
    path = data.get("path", "").strip()
    if not unit_code or not path: return jsonify({"status": "error", "message": "单元编号和路径不能为空"}), 400
    if not os.path.isdir(path): return jsonify({"status": "error", "message": "路径不存在"}), 400
    if unit_code in cfg[cls_name]: return jsonify({"status": "error", "message": "单元已存在"}), 400
    created_by = data.get("created_by", "").strip()
    db.config_add_unit(cls_name, unit_code, unit_name or unit_code, path, created_by)
    _clear_config_cache(); return jsonify({"status": "ok", "code": unit_code})

@app.route("/api/classes/<cls_name>/units/<unit_code>", methods=["PUT"])
def update_unit_path(cls_name, unit_code):
    cfg = get_config()
    if cls_name not in cfg: return jsonify({"status": "error", "message": "班级不存在"}), 404
    if unit_code not in cfg[cls_name]: return jsonify({"status": "error", "message": "单元不存在"}), 404
    data = request.json
    path = data.get("path", "").strip()
    if not path or not os.path.isdir(path): return jsonify({"status": "error", "message": "路径不存在"}), 400
    db.config_update_unit_path(cls_name, unit_code, path)
    return jsonify({"status": "ok"})

@app.route("/api/classes/<cls_name>/units/<unit_code>", methods=["DELETE"])
def delete_unit(cls_name, unit_code):
    cfg = get_config()
    if cls_name not in cfg or unit_code not in cfg.get(cls_name, {}):
        return jsonify({"status": "error", "message": "单元不存在"}), 404
    info = cfg[cls_name][unit_code]
    info.update({"class": cls_name, "unit_code": unit_code,
        "deleted_at": __import__('datetime').datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
    db.recycle_add(info)
    recycle_dir = os.path.join(BASE_DIR, "recycle")
    os.makedirs(recycle_dir, exist_ok=True)
    ts = info["deleted_at"].replace(" ", "_").replace(":", "-")
    p = info.get("path", "")
    if p and os.path.isdir(p):
        dest = os.path.join(recycle_dir, f"{cls_name}_{unit_code}_{ts}")
        os.makedirs(dest, exist_ok=True)
        for f in os.listdir(p):
            if f.startswith(f"{cls_name}-{unit_code}-") and os.path.isdir(os.path.join(p, f)):
                shutil.move(os.path.join(p, f), os.path.join(dest, f))
    db.config_remove_unit(cls_name, unit_code)
    return jsonify({"status": "ok"})

@app.route("/api/load/<folder>")
def load_lesson(folder):
    cls_name = cls_from_folder(folder)
    unit_code = unit_from_folder(folder)
    base = unit_path(cls_name, unit_code)
    if not base: return jsonify({"error":"未找到该课节所属单元的路径"}), 404
    lesson_num = folder.split(f"-{unit_code}-")[-1] if f"-{unit_code}-" in folder else "1"
    # 从 Turso 读课节 TXT 内容
    title, content = db.lesson_get(cls_name, unit_code, int(lesson_num))
    import tempfile
    if content:
        tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8')
        tmp.write(content); tmp.close()
        from generate_class_image import parse_input_txt
        meta, topics = parse_input_txt(tmp.name)
        os.unlink(tmp.name)
    else:
        meta, topics = {}, []
    outputs = []
    # 本地输出目录
    p = os.path.join(base, folder)
    if os.path.isdir(p):
        for f in sorted(os.listdir(p)):
            if f.endswith(".png") and "金句" not in f and "单人" not in f:
                outputs.append({"name": f, "path": f"/api/file/{folder}/{f}"})
    outputs += find_cards(folder, base)
    outputs += find_golden(folder, cls_name, base)
    for label in ["课后反馈","课堂实录"]:
        for loc in [p, base]:
            if not os.path.isdir(loc): continue
            for cn in [cls_name, meta.get("class","")]:
                fb = os.path.join(loc, f"{label}_{cn}.txt")
                if os.path.exists(fb):
                    outputs.append({"name": os.path.basename(fb), "path": f"/api/file/{folder}/{os.path.basename(fb)}"}); break
            else: continue; break
    # 加载已保存的图片
    topic_images = {}
    img_dir = os.path.join(p, "images") if os.path.isdir(p) else ""
    if img_dir and os.path.isdir(img_dir):
        for f in sorted(os.listdir(img_dir)):
            import re as _re
            m = _re.match(r'topic(\d+)_(\d+)', f)
            if m:
                ti = int(m.group(1)); idx = int(m.group(2))
                if ti not in topic_images: topic_images[ti] = []
                topic_images[ti].append(f"/api/file/{folder}/images/{f}")
    # 从磁盘图片重建 [img:N] 标记（前端刷新后 _images 会丢失）
    if topic_images:
        for ti, img_urls in topic_images.items():
            if ti < len(topics):
                title, speeches = topics[ti]
                markers = ' '.join(f'[img:{i}]' for i in range(len(img_urls)))
                # 检查是否已有标记，避免重复
                all_content = ' '.join(c for _, c in speeches)
                if '[img:' not in all_content:
                    if speeches:
                        name, content = speeches[-1]
                        speeches[-1] = (name, content + ' ' + markers)
                    else:
                        speeches.append(('', markers))
                    topics[ti] = (title, speeches)
    return jsonify({"meta":meta, "topics":[{"title":t,"speeches":[{"name":n,"content":c}for n,c in s]} for t,s in topics], "outputs":outputs, "base_path": base, "images": topic_images})

@app.route("/api/save", methods=["POST"])
def save_lesson():
    """保存编辑中的课节到 txt 文件"""
    data = request.json
    meta = data.get("meta",{})
    topics_data = data.get("topics",[])
    folder = data.get("folder","")
    if not folder: return jsonify({"status":"error","message":"no folder"}), 400
    cls_name = cls_from_folder(folder)
    unit_code = unit_from_folder(folder)
    base = unit_path(cls_name, unit_code)
    if not base:
        # 兜底：用共享文件夹下的课后材料目录
        base = os.path.join(os.path.dirname(os.environ.get("ZG_DB", ".")), "课后材料")
        os.makedirs(base, exist_ok=True)
        db.config_add_unit(cls_name, unit_code, unit_code, base, "")
    # auto-number only for new (unsaved) folders
    is_new = folder.endswith("-new")
    if is_new:
        prefix = folder.replace("-new", "")
        max_n = 0
        if os.path.isdir(base):
            for f in os.listdir(base):
                if f.startswith(prefix + "-") and os.path.isdir(os.path.join(base, f)):
                    try: n = int(f.rsplit("-",1)[-1]); max_n = max(max_n, n)
                    except: pass
        folder = f"{prefix}-{max_n + 1}"
    lesson_num = folder.split(f"-{unit_code}-")[-1] if f"-{unit_code}-" in folder else "1"
    # 确保本地输出目录存在
    p = os.path.join(base, folder)
    if not os.path.isdir(p): os.makedirs(p, exist_ok=True)
    # 保存图片到本地
    images = data.get("images", {})
    if images:
        import base64 as _b64
        img_dir = os.path.join(p, "images")
        os.makedirs(img_dir, exist_ok=True)
        for ti, img_list in images.items():
            for idx, img_data in enumerate(img_list):
                if img_data and img_data.startswith("data:"):
                    try:
                        header, data = img_data.split(",", 1)
                        ext = "png" if "png" in header else "jpg"
                        with open(os.path.join(img_dir, f"topic{ti}_{idx}.{ext}"), "wb") as _f:
                            _f.write(_b64.b64decode(data))
                    except: pass
    # 写 TXT 到 Turso
    content_lines = [f"# ====== 课节信息 ======\n@title {meta.get('title','')}\n@unit {meta.get('unit','')}\n@date {meta.get('date','')}\n@class {meta.get('class','')}\n"]
    if meta.get('gender'): content_lines.append(f"@gender {meta['gender']}\n")
    content_lines.append("\n# ====== 课堂发言 ======\n")
    for t in topics_data:
        content_lines.append(t.get("title","") + "\n")
        for s in t.get("speeches",[]):
            content_lines.append(f"{s.get('name','')}：{s.get('content','')}\n")
        content_lines.append("\n")
    content = ''.join(content_lines)
    db.lesson_save(cls_name, unit_code, int(lesson_num), meta.get('title',''), content)
    _clear_config_cache(); return jsonify({"status":"ok","folder":folder})

@app.route("/api/parse", methods=["POST"])
def parse_text():
    data = request.json
    text = data.get("text","")
    tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8')
    tmp.write(text); tmp.close()
    from generate_class_image import parse_input_txt, split_sentences, score_sentence
    meta, topics = parse_input_txt(tmp.name)
    os.unlink(tmp.name)
    golden = set()
    for t,s in topics:
        for n,c in s:
            sc = [(score_sentence(st,n,{}),st) for st,_,_ in split_sentences(c) if len(st)>10]
            sc.sort(key=lambda x:-x[0])
            for _,st in sc[:3]: golden.add(st)
    return jsonify({"meta":meta,"topics":[{"title":t,"speeches":[{"name":n,"content":c}for n,c in s]} for t,s in topics],"golden_sents":list(golden)})

@app.route("/api/score", methods=["POST"])
def score_sentences():
    from generate_class_image import split_sentences
    data = request.json
    sentences = data.get("sentences", [])
    meta = data.get("meta", {})
    title = meta.get("title", "")
    topic_list = data.get("topics", meta.get("topics", []))

    # 不拆句——预览金句按整段发言为单位，拆句会导致 key 对不上
    all_sents = sentences

    # 尝试 DeepSeek 打分
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if api_key and all_sents and title:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
            # 按学生分组
            by_name = {}
            for s in all_sents:
                n = s["name"]
                if n not in by_name: by_name[n] = []
                by_name[n].append(s["text"])
            # 并行调用 DeepSeek（每学生一次）
            from concurrent.futures import ThreadPoolExecutor, as_completed
            import re as _re
            topic_text = ""
            if topic_list:
                topic_text = "本节课讨论的话题：\n" + "\n".join(f"· {t}" for t in topic_list[:10]) + "\n\n"
            def score_one(name, sents):
                prompt = f"课节标题：{title}\n\n{topic_text}学生：{name}\n\n以下是{name}在课堂上的所有发言句子，请按「思辨深度」给每句话打 1-10 分。\n"
                prompt += "标准：句子的逻辑性、多角度思考、联系生活经验、反驳他人观点、总结提炼能力。\n\n"
                for i, t in enumerate(sents, 1):
                    prompt += f"{i}. {t}\n"
                prompt += f"\n请按格式返回每句的分数：\n序号:分数"
                resp = client.chat.completions.create(
                    model="deepseek-chat",
                    messages=[{"role":"user","content": prompt}],
                    temperature=0.3, max_tokens=300, stream=False)
                text = resp.choices[0].message.content
                scores = {}
                for line in text.split("\n"):
                    m = _re.search(r'(\d+)\s*[：:.\-]\s*(\d+)', line.strip())
                    if m: scores[int(m.group(1))] = int(m.group(2))
                result = []
                for i, t in enumerate(sents, 1):
                    sc = scores.get(i, 5)
                    result.append({"text": t, "score": sc, "name": name})
                return result
            all_results = []
            with ThreadPoolExecutor(max_workers=len(by_name)) as ex:
                futures = {ex.submit(score_one, n, s): n for n, s in by_name.items()}
                for f in as_completed(futures):
                    try: all_results.extend(f.result())
                    except Exception as e: print(f"  DeepSeek score failed: {e}")
            all_results.sort(key=lambda x: -x["score"])
            return jsonify(all_results)
        except Exception as e:
            print(f"  DeepSeek 打分异常: {e}，回退关键词打分")

    # 回退：关键词打分
    from generate_class_image import score_sentence
    results = []
    for s in all_sents:
        sc = score_sentence(s["text"], s["name"], {})
        results.append({"text": s["text"], "score": sc, "name": s["name"]})
    results.sort(key=lambda x: -x["score"])
    return jsonify(results)

@app.route("/api/topics/sources")
def list_topic_sources():
    return jsonify(sort_class_names(list(get_config().keys())))

@app.route("/api/topics/inherit")
def inherit_topics():
    src = request.args.get("from","")
    cfg = get_config()
    if not src or src not in cfg: return jsonify([])
    from generate_class_image import parse_input_txt
    for unit_code, info in cfg.get(src, {}).items():
        path = info.get("path", "")
        if not os.path.isdir(path): continue
        for f in sorted(os.listdir(path)):
            if not os.path.isdir(os.path.join(path, f)) or f"{src}-" not in f: continue
            short = f.rsplit("-",1)[0]
            txt = os.path.join(path, f, f"{short}.txt")
            if not os.path.exists(txt):
                txt = os.path.join(path, f, f"{f}.txt")
            if os.path.exists(txt):
                _, tps = parse_input_txt(txt)
                return jsonify([t for t,_ in tps])
    return jsonify([])

@app.route("/api/generate", methods=["POST"])
def generate_all():
    data = request.json
    meta = data.get("meta",{})
    topics_data = data.get("topics",[])
    movies = data.get("movies",{})
    gender = data.get("gender","")
    golden_qs = data.get("golden_quotes",{})
    poster_qs = data.get("poster_quotes",{})
    feedback_styles = [s for s in data.get("feedback_styles","").split(",") if s]
    images = data.get("images", {})

    cls = meta.get("class","未命名")
    title = meta.get("title","")
    unit = meta.get("unit","")
    date = meta.get("date","")

    unit_code = "2605"
    cfg = get_config()
    for code, info in cfg.get(cls, {}).items():
        if info.get("name","") == unit or code in unit:
            unit_code = code; break
    if unit_code not in cfg.get(cls, {}):
        import re
        m = re.search(r'(\d{4})', unit)
        if m: unit_code = m.group(1)

    base = unit_path(cls, unit_code)
    if not base:
        return jsonify({"status": "error", "message": f"未找到班级「{cls}」单元「{unit_code}」的路径，请先在左侧新建单元"}), 400

    folder_base = data.get("tab_name", cls)
    is_new_lesson = folder_base.endswith("-new")
    if is_new_lesson:
        prefix = folder_base.replace("-new", "")
        max_n = 0
        if os.path.isdir(base):
            for f in os.listdir(base):
                if f.startswith(prefix + "-") and os.path.isdir(os.path.join(base, f)):
                    try: n = int(f.rsplit("-",1)[-1]); max_n = max(max_n, n)
                    except: pass
        # 也查 Turso 已有课节，避免跳号
        existing = db.lesson_list(cls, unit_code)
        for l in existing:
            try: n = int(l["lesson"]); max_n = max(max_n, n)
            except: pass
        folder = f"{prefix}-{max_n + 1}"
    elif f"-{unit_code}-" in folder_base:
        folder = folder_base
    else:
        folder = f"{folder_base}-{unit_code}-1"
    folder_path = os.path.join(base, folder)
    os.makedirs(folder_path, exist_ok=True)

    # 保存粘贴的图片
    if images:
        import base64 as _b64
        img_dir = os.path.join(folder_path, "images")
        os.makedirs(img_dir, exist_ok=True)
        for ti, img_list in images.items():
            for idx, img_data in enumerate(img_list):
                if img_data and img_data.startswith("data:"):
                    try:
                        header, data = img_data.split(",", 1)
                        ext = "png" if "png" in header else "jpg"
                        fname = f"topic{ti}_{idx}.{ext}"
                        with open(os.path.join(img_dir, fname), "wb") as _f:
                            _f.write(_b64.b64decode(data))
                    except: pass

    # 构建 TXT 内容
    short = folder.split(f"-{unit_code}-")[0]
    txt_path = os.path.join(folder_path, f"{short}.txt")
    content_lines = [f"# ====== 课节信息 ======\n@title {title}\n@unit {unit}\n@date {date}\n@class {cls}\n"]
    if gender: content_lines.append(f"@gender {gender}\n")
    content_lines.append("\n# ====== 推荐 ======\n")
    for name, info in movies.items():
        if info.get("movie"):
            content_lines.append(f"@student {name}\n")
            if info.get("quote"): content_lines.append(f"@quote {info['quote']}\n")
            content_lines.append(f"@movie {info['movie']}\n")
            if info.get("poster"): content_lines.append(f"@poster {info['poster']}\n")
            if info.get("rating"): content_lines.append(f"@rating {info['rating']}\n")
            if info.get("line"): content_lines.append(f"@line {info['line']}\n")
            content_lines.append("\n")
    for name, info in poster_qs.items():
        if info.get("movie") or info.get("quote"):
            content_lines.append(f"@student {name}\n")
            if info.get("quote"): content_lines.append(f"@quote {info['quote']}\n")
            if info.get("movie"): content_lines.append(f"@movie {info['movie']}\n")
            if info.get("poster"): content_lines.append(f"@poster {info['poster']}\n")
            if info.get("rating"): content_lines.append(f"@rating {info['rating']}\n")
            if info.get("line"): content_lines.append(f"@line {info['line']}\n")
            content_lines.append("\n")
    content_lines.append("\n# ====== 课堂发言 ======\n")
    for t in topics_data:
        content_lines.append(t["title"] + "\n")
        for s in t["speeches"]:
            content_lines.append(f"{s['name']}：{str(s['content'])}\n")
        content_lines.append("\n")
    content = ''.join(content_lines)
    # 写本地临时文件供生成脚本读取（生成完后删除）
    with open(txt_path, 'w', encoding='utf-8') as f:
        f.write(content)
    # 保存到 TiDB 云端
    lesson_num = folder.split(f"-{unit_code}-")[-1] if f"-{unit_code}-" in folder else "1"
    # 新课（TiDB 中不存在）自动写入；已存在的课节不覆盖（保护手动编辑的内容）
    existing_title, _ = db.lesson_get(cls, unit_code, int(lesson_num))
    if not existing_title:
        db.lesson_save(cls, unit_code, int(lesson_num), title, content)
    _clear_config_cache()

    font_path = os.path.expanduser("~/Library/Fonts/荆南麦圆体.ttf")
    font_warning = None
    if not os.path.exists(font_path):
        alt = "/System/Library/Fonts/Hiragino Sans GB.ttc"
        if os.path.exists(alt):
            font_warning = "荆南麦圆体未安装，使用系统字体替代，排版效果可能不佳"
        else:
            font_warning = "未找到任何中文字体，图片可能无法正常生成"

    # 生成输出到本地目录（unit_path）
    cwd = os.getcwd(); os.chdir(base)
    try:
        from generate_all import generate_all as ga
        img_dir = os.path.join(folder_path, "images")
        ga(txt_path, feedback_styles=feedback_styles, golden_quotes=golden_qs, images_dir=img_dir if os.path.isdir(img_dir) else None)
    except Exception as e:
        os.chdir(cwd)
        # 清理失败的生成物（只删输出文件夹，底表保留）
        try:
            if is_new_lesson and os.path.isdir(folder_path):
                shutil.rmtree(folder_path)
        except: pass
        return jsonify({"status": "error", "message": f"生成失败: {str(e)}"}), 500
    finally:
        os.chdir(cwd)

    # 归拢散落文件到 lesson 文件夹
    for f in os.listdir(base):
        fp = os.path.join(base, f)
        if os.path.isfile(fp) and (cls in f or meta.get('class','') in f or f.startswith("单人总结_")):
            if f.endswith((".png",".txt",".json")):
                dest = os.path.join(folder_path, f)
                if os.path.exists(dest): os.remove(dest)
                shutil.move(fp, dest)
    for sub in [f"金句_{cls}", f"金句_{meta.get('class','')}"]:
        src = os.path.join(base, sub)
        if os.path.isdir(src):
            dest = os.path.join(folder_path, sub)
            if os.path.exists(dest): shutil.rmtree(dest)
            shutil.move(src, dest)

    outputs = []
    for f in sorted(os.listdir(folder_path)):
        if f.endswith(".png") and "金句" not in f and "单人" not in f:
            outputs.append({"name":f, "path":f"/api/file/{folder}/{f}"})
    outputs += find_cards(folder, base)
    outputs += find_golden(folder, cls, base)
    for label in ["课后反馈","课堂实录"]:
        for cn in [cls, meta.get("class","")]:
            fb = os.path.join(folder_path, f"{label}_{cn}.txt")
            if os.path.exists(fb):
                outputs.append({"name": os.path.basename(fb), "path":f"/api/file/{folder}/{os.path.basename(fb)}"}); break
            fb2 = os.path.join(base, f"{label}_{cn}.txt")
            if os.path.exists(fb2):
                outputs.append({"name": os.path.basename(fb2), "path":f"/api/file/{folder}/{os.path.basename(fb2)}"}); break
    return jsonify({"status":"ok","outputs":outputs,"folder":folder,"font_warning":font_warning})

@app.route("/api/file/<folder>/images/<filename>")
def serve_image(folder, filename):
    cls_name = cls_from_folder(folder)
    unit_code = unit_from_folder(folder)
    base = unit_path(cls_name, unit_code)
    if base:
        fp = os.path.join(base, folder, "images")
        if os.path.isfile(os.path.join(fp, filename)):
            return send_from_directory(fp, filename)
    return jsonify({"error":"not found"}), 404

@app.route("/api/file/<folder>/<filename>")
def serve_file(folder, filename):
    cls_name = cls_from_folder(folder)
    unit_code = unit_from_folder(folder)
    base = unit_path(cls_name, unit_code)
    if base:
        fp = os.path.join(base, folder)
        if os.path.isfile(os.path.join(fp, filename)):
            return send_from_directory(fp, filename)
    return jsonify({"error":"file not found"}), 404

@app.route("/api/preview-poster", methods=["POST"])
def preview_poster():
    data = request.json
    from generate_golden_card import make_card as make_golden_card
    tmp = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
    tmp.close()
    gmeta = {
        "title": data.get("title",""), "unit": data.get("unit",""),
        "date": data.get("date",""), "class": data.get("class",""),
        "quote": data.get("quote",""), "author": data.get("author",""),
        "topic": data.get("topic",""),
        "movie": data.get("movie",""), "poster": data.get("poster",""),
        "rating": data.get("rating",""), "line": data.get("line",""),
    }
    make_golden_card(gmeta, tmp.name)
    return jsonify({"path": f"/api/tmp/{os.path.basename(tmp.name)}"})

@app.route("/api/tmp/<filename>")
def serve_tmp(filename):
    return send_from_directory(tempfile.gettempdir(), filename)

@app.route("/api/tmdb/search")
def tmdb_search():
    import urllib.request, urllib.parse
    q = request.args.get("q", "").strip()
    if not q: return jsonify([])
    api_key = os.environ.get("TMDB_API_KEY", "97f5317f472b218e43f77db067ca7784")
    url = f"https://api.themoviedb.org/3/search/movie?api_key={api_key}&query={urllib.parse.quote(q)}&language=zh-CN"
    try:
        r = urllib.request.urlopen(url, timeout=10)
        data = json.loads(r.read())
        results = []
        for m in data.get("results", [])[:5]:
            results.append({
                "title": m.get("title", ""),
                "original_title": m.get("original_title", ""),
                "year": m.get("release_date", "")[:4],
                "overview": m.get("overview", ""),
                "rating": str(m.get("vote_average", "")),
                "poster": f"https://image.tmdb.org/t/p/w500{m['poster_path']}" if m.get("poster_path") else "",
                "id": m.get("id"),
            })
        return jsonify(results)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ====== 考勤 ======

@app.route("/api/attendance/student-counts")
def attendance_student_counts():
    """返回 {student_name: 实际出勤次数}"""
    return jsonify(db.attendance_student_counts())

@app.route("/api/attendance/lesson", methods=["DELETE"])
def attendance_delete():
    data = request.json
    db.attendance_delete_lesson(data.get("class_name",""), int(data.get("lesson_num",0)), data.get("lesson_title",""), data.get("lesson_date",""))
    _clear_config_cache()
    return jsonify({"status":"ok"})

@app.route("/api/attendance/content-label", methods=["POST"])
def attendance_update_content_label():
    data = request.json
    from db import get_db, _execute
    _execute(get_db(), "UPDATE attendance SET content_label=%s WHERE class_name=%s AND lesson_title=%s AND lesson_date=%s", [data.get("content_label",""), data.get("class_name",""), data.get("lesson_title",""), data.get("lesson_date","")])
    _clear_config_cache(); return jsonify({"status":"ok"})

@app.route("/api/attendance/cycle", methods=["POST"])
def attendance_update_cycle():
    data = request.json
    from db import get_db, _execute
    _execute(get_db(), "UPDATE attendance SET cycle=%s WHERE class_name=%s AND lesson_title=%s AND lesson_date=%s", [data.get("cycle",""), data.get("class_name",""), data.get("lesson_title",""), data.get("lesson_date","")])
    _clear_config_cache(); return jsonify({"status":"ok"})

@app.route("/api/attendance/suggest", methods=["POST"])
def attendance_suggest():
    data = request.json
    cls_name = data.get("class_name", "")
    topics = data.get("topics", [])
    # 从发言中提取学生
    speakers = set()
    for t in topics:
        for s in t.get("speeches", []):
            n = s.get("name", "").strip()
            if n and n != "图": speakers.add(n)
    # 取班级花名册
    roster = db.roster_get(cls_name)
    # 取学生扩展信息
    from db import student_ext_all as _se
    # 构建建议
    result = []
    seen = set()
    # Build fuzzy match map: short name → roster names
    fuzzy = {}
    for rn in roster:
        for sn in speakers:
            if sn != rn and (sn in rn or rn.startswith(sn)):
                fuzzy[sn] = rn
    # 花名册中的学生
    for name in roster:
        seen.add(name)
        status = "出席" if name in speakers or name in fuzzy.values() else ""
        # If matched via fuzzy, use the roster name
        result.append({"name": name, "status": status, "note": "", "inRoster": True})
    # 在发言中但不在花名册的（新生）
    for name in speakers:
        if name not in seen and name not in fuzzy:
            result.append({"name": name, "status": "出席", "note": "", "inRoster": False, "isNew": True})
    return jsonify({"roster": result, "speakers": list(speakers)})

@app.route("/api/attendance/save", methods=["POST"])
def attendance_save():
    data = request.json
    cls_name = data.get("class_name", "")
    unit_code = data.get("unit_code", "")
    lesson_num = int(data.get("lesson_num", 1))
    lesson_title = data.get("lesson_title", "")
    lesson_date = data.get("lesson_date", "")
    records = data.get("records", [])
    # 如果有新生，也加入花名册
    new_students = data.get("new_students", [])
    for ns in new_students:
        roster = db.roster_get(cls_name)
        if ns["name"] not in roster:
            db.roster_set(cls_name, roster + [ns["name"]])
        # 同时注册到 student_ext，确保学生 tab 可见
        from db import get_db, _execute
        exist = _execute(get_db(), "SELECT student_name FROM student_ext WHERE student_name=%s", [ns["name"]]).fetchone()
        if not exist:
            _execute(get_db(), "INSERT INTO student_ext (student_name,student_code,source,status,segment,enrolled_class,purchased_lessons,used_lessons,remaining_lessons,notes) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", [ns["name"], '', '考勤新增', '仅试听', '', cls_name, 0, 0, 0, ns.get("note","")])
    batch = []
    cycle = data.get("cycle", "")
    content_label = data.get("content_label", "")
    for r in records:
        batch.append({
            "class_name": cls_name, "unit_code": unit_code,
            "lesson_num": lesson_num, "lesson_title": lesson_title,
            "lesson_date": lesson_date, "student_name": r["name"],
            "status": r.get("status", "出席"), "note": r.get("note", ""),
            "cycle": cycle, "content_label": content_label
        })
    db.attendance_batch(batch)
    # 更新 student_ext 的消课计数
    names = list(set(r["name"] for r in records if r.get("status","出席") == "出席"))
    for name in names:
        used = _execute(get_db(), "SELECT COUNT(*) as cnt FROM attendance WHERE student_name=%s AND status='出席'", [name]).fetchone()
        if used:
            _execute(get_db(), "UPDATE student_ext SET used_lessons=%s, remaining_lessons=purchased_lessons-%s WHERE student_name=%s", [used["cnt"], used["cnt"], name])
    _clear_config_cache(); return jsonify({"status": "ok", "count": len(batch)})

# ====== 财务 ======

@app.route("/api/finance/summary")
def finance_summary():
    s = db.finance_summary()
    return jsonify(s)

@app.route("/api/finance/records")
def finance_records():
    rtype = request.args.get("type", "revenue")
    cls = request.args.get("class", "")
    student = request.args.get("student", "")
    limit = int(request.args.get("limit", 50))
    if rtype == "cost":
        records = db.cost_list(limit)
    elif rtype == "attendance":
        records = db.attendance_get(class_name=cls or None)
    else:
        records = db.purchase_list(student_name=student or None, limit=limit)
    return jsonify(records)

# ====== 花名册 ======

@app.route("/api/roster/<cls_name>")
def roster_get(cls_name):
    return jsonify(db.roster_get(cls_name))

@app.route("/api/roster/<cls_name>", methods=["POST"])
def roster_set(cls_name):
    students = request.json.get("students", [])
    db.roster_set(cls_name, students)
    return jsonify({"status": "ok"})

@app.route("/api/classes/<cls_name>/off-weeks", methods=["PUT"])
def set_off_weeks(cls_name):
    from db import get_db as _gdb
    cur = _gdb().cursor()
    cur.execute("UPDATE config SET off_weeks=%s WHERE class_name=%s", [request.json.get("off_weeks",""), cls_name])
    _gdb().commit()
    _clear_config_cache(); return jsonify({"status": "ok"})

@app.route("/api/classes/off-weeks", methods=["PUT"])
def set_off_weeks_global():
    from db import get_db as _gdb
    cur = _gdb().cursor()
    cur.execute("UPDATE config SET off_weeks=%s", [request.json.get("off_weeks","")])
    _gdb().commit()
    _clear_config_cache(); return jsonify({"status": "ok"})

# ====== Excel 导入 ======

@app.route("/api/import-excel", methods=["POST"])
def import_excel():
    if "file" not in request.files:
        return jsonify({"status": "error", "message": "请上传文件"}), 400
    file = request.files["file"]
    import tempfile, openpyxl
    tmp = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
    file.save(tmp.name)
    tmp.close()
    stats = {"student_ext": 0, "purchases_new": 0, "purchases_updated": 0, "attendance": 0, "costs": 0, "roster": 0}
    try:
        from db import get_db
        wb = openpyxl.load_workbook(tmp.name, data_only=True)
        stmts = []  # batch SQL statements for pipeline

        def esc(v):
            if v is None: return 'NULL'
            if isinstance(v, (int, float)): return str(v)
            return "'" + str(v).replace("'", "''") + "'"

        # 学生基础信息
        if "学生基础信息" in wb.sheetnames:
            ws = wb["学生基础信息"]
            for row in ws.iter_rows(min_row=2, values_only=True):
                if not row[0]: continue
                stmts.append(f"INSERT OR REPLACE INTO student_ext VALUES ({esc(str(row[0]))},{esc(str(row[2] or ''))},{esc(str(row[1] or ''))},{esc(str(row[3] or ''))},{esc(str(row[4] or ''))},{esc(str(row[5] or ''))},{int(row[6] or 0)},{int(row[7] or 0)},{int(row[8] or 0)},{esc(str(row[9] or ''))})")
                stats["student_ext"] += 1
                if len(stmts) >= 100:
                    get_db()._req({"requests": [{"type":"execute","stmt":{"sql":s}} for s in stmts] + [{"type":"close"}]})
                    stmts = []
        # 收费明细
        if "收费明细" in wb.sheetnames:
            ws = wb["收费明细"]
            for row in ws.iter_rows(min_row=2, values_only=True):
                if not row[0]: continue
                amt = str(row[9] or "0").replace("¥","").replace(",","").replace(" ","")
                ref = str(row[10] or "0").replace("¥","").replace(",","").replace(" ","")
                xs = str(row[15] or "0").replace("¥","").replace(",","").replace(" ","")
                oid = str(row[12] or "")
                vals = f"{esc(str(row[0]))},{esc(str(row[1] or ''))},{esc(str(row[2] or ''))},{esc(str(row[4] or ''))},{esc(str(row[5] or ''))},{esc(str(row[6] or ''))},{esc(str(row[7] or ''))},{int(row[8] or 0)},{float(amt) if amt else 0},{float(ref) if ref else 0},{esc(str(row[11] or ''))},{esc(oid)},{float(xs) if xs else 0},{esc(str(row[16] or ''))}"
                if oid:
                    stmts.append(f"DELETE FROM purchases WHERE order_id={esc(oid)}")
                    stats["purchases_updated"] += 1
                    stmts.append(f"INSERT INTO purchases (student_name,student_code,charge_code,segment,course_type,method,discount_type,lesson_count,amount,refund_amount,actual_pay_date,order_id,xiaohongshu_received,notes) VALUES ({vals})")
                else:
                    # 检查重复：完全相同的记录不重复插入
                    dup_check = f"SELECT COUNT(*) as cnt FROM purchases WHERE student_name={esc(str(row[0]))} AND actual_pay_date={esc(str(row[11] or '')[:10])} AND lesson_count={int(row[8] or 0)} AND amount={float(amt) if amt else 0}"
                    stmts.append(f"INSERT INTO purchases (student_name,student_code,charge_code,segment,course_type,method,discount_type,lesson_count,amount,refund_amount,actual_pay_date,order_id,xiaohongshu_received,notes) SELECT {vals} FROM DUAL WHERE NOT EXISTS (SELECT 1 FROM purchases WHERE student_name={esc(str(row[0]))} AND actual_pay_date={esc(str(row[11] or '')[:10])} AND lesson_count={int(row[8] or 0)} AND amount={float(amt) if amt else 0})")
                    stats["purchases_new"] += 1
                if len(stmts) >= 80:
                    get_db()._req({"requests": [{"type":"execute","stmt":{"sql":s}} for s in stmts] + [{"type":"close"}]})
                    stmts = []
        # 销课情况
        if "销课情况" in wb.sheetnames:
            ws = wb["销课情况"]
            for row in ws.iter_rows(min_row=2, values_only=True):
                cls_name = str(row[2] or "")
                date_val = str(row[6] or "")[:10]
                rec = str(row[17] or "")
                if not rec or not cls_name: continue
                for name in rec.replace("，",",").split(","):
                    n = name.strip()
                    if not n: continue
                    stmts.append(f"INSERT OR IGNORE INTO attendance (class_name,unit_code,lesson_num,lesson_title,lesson_date,student_name,status,note,recorded_at) VALUES ({esc(cls_name)},'2605',0,{esc(str(row[4] or ''))},{esc(date_val)},{esc(n)},'出席','',{esc(date_val)})")
                    stats["attendance"] += 1
                    if len(stmts) >= 100:
                        get_db()._req({"requests": [{"type":"execute","stmt":{"sql":s}} for s in stmts] + [{"type":"close"}]})
                        stmts = []
        # 成本
        if "成本" in wb.sheetnames:
            ws = wb["成本"]
            for row in ws.iter_rows(min_row=2, values_only=True):
                if not row[0]: continue
                amt = str(row[5] or "0").replace("¥","").replace(",","").replace(" ","")
                stmts.append(f"INSERT INTO costs (reason,cycle,cost_type,channel,cost_date,amount,notes) VALUES ({esc(str(row[0] or ''))},{esc(str(row[1] or ''))},{esc(str(row[2] or ''))},{esc(str(row[3] or ''))},{esc(str(row[4] or '')[:10])},{float(amt) if amt else 0},{esc(str(row[7] or ''))})")
                stats["costs"] += 1
                if len(stmts) >= 100:
                    get_db()._req({"requests": [{"type":"execute","stmt":{"sql":s}} for s in stmts] + [{"type":"close"}]})
                    stmts = []
        # 排课表 → roster (batch at end)
        class_names_set = {}
        if "排课表" in wb.sheetnames:
            ws = wb["排课表"]
            for row in ws.iter_rows(min_row=2, values_only=True):
                cls_name = str(row[3] or "")
                students_str = str(row[4] or "")
                if not cls_name or not students_str: continue
                names = [n.strip() for n in students_str.replace("，",",").split(",") if n.strip()]
                if cls_name not in class_names_set: class_names_set[cls_name] = set()
                class_names_set[cls_name].update(names)
            for cls_name, names in class_names_set.items():
                existing = db.roster_get(cls_name)
                merged = list(set(existing + list(names)))
                for n in merged:
                    stmts.append(f"INSERT OR IGNORE INTO class_roster VALUES ({esc(cls_name)},{esc(n)})")
                stats["roster"] += len(merged)
                if len(stmts) >= 100:
                    get_db()._req({"requests": [{"type":"execute","stmt":{"sql":s}} for s in stmts] + [{"type":"close"}]})
                    stmts = []
        # Flush remaining
        if stmts:
            get_db()._req({"requests": [{"type":"execute","stmt":{"sql":s}} for s in stmts] + [{"type":"close"}]})
        os.unlink(tmp.name)
        return jsonify({"status": "ok", "stats": stats})
    except Exception as e:
        try: os.unlink(tmp.name)
        except: pass
        return jsonify({"status": "error", "message": str(e)}), 500

# ====== 定价 ======

@app.route("/api/pricing")
def pricing_list():
    return jsonify(db.pricing_all())

@app.route("/api/pricing", methods=["POST"])
def pricing_update():
    data = request.json
    db.pricing_set(data["segment"], data["course_type"], data["discount_type"], data["unit_price"], data["discount_multiplier"])
    return jsonify({"status": "ok"})

# ====== 财务 CRUD ======

@app.route("/api/finance/add-revenue", methods=["POST"])
def finance_add_revenue():
    data = request.json
    from db import purchase_add
    purchase_add(data)
    return jsonify({"status": "ok"})

@app.route("/api/finance/delete-purchase", methods=["POST"])
def finance_delete_purchase():
    data = request.json
    db.purchase_delete(int(data.get("id", 0)))
    return jsonify({"status": "ok"})

@app.route("/api/finance/add-cost", methods=["POST"])
def finance_add_cost():
    data = request.json
    db.cost_add(data)
    return jsonify({"status": "ok"})

@app.route("/api/finance/delete-cost", methods=["POST"])
def finance_delete_cost():
    data = request.json
    from db import get_db, _execute
    _execute(get_db(), "DELETE FROM costs WHERE id=%s", [int(data.get("id", 0))])
    return jsonify({"status": "ok"})

# ====== 学生扩展 CRUD ======

@app.route("/api/students")
def students_list():
    rows = db.student_ext_all()
    return jsonify(rows)

@app.route("/api/students/next-code")
def students_next_code():
    cur = db.get_db().cursor()
    cur.execute("SELECT MAX(CAST(student_code AS UNSIGNED)) as mx FROM student_ext WHERE student_code REGEXP '^[0-9]+$'")
    row = cur.fetchone()
    next_code = str(int(row[0] or 0) + 1).zfill(3) if row and row[0] else "001"
    return jsonify({"code": next_code})

@app.route("/api/students", methods=["POST"])
def students_upsert():
    data = request.json
    db.student_ext_upsert(data.get("student_name", ""), data)
    _clear_config_cache()
    return jsonify({"status": "ok"})

# ====== 总览 Dashboard ======

@app.route("/api/dashboard/summary")
def dashboard_summary():
    return jsonify(db.dashboard_summary())

@app.route("/api/dashboard/weekly")
def dashboard_weekly():
    return jsonify(db.dashboard_weekly())

# ====== 消课 by Lesson ======

@app.route("/api/attendance/cycles")
def attendance_cycles():
    db2 = db.get_db()
    cur = db2.cursor()
    cur.execute("SELECT DISTINCT cycle FROM attendance WHERE cycle!='' ORDER BY cycle")
    return jsonify([r[0] for r in cur.fetchall()])

@app.route("/api/attendance/by-lesson")
def attendance_by_lesson():
    cls = request.args.get("class", "")
    cycle = request.args.get("cycle", "")
    page = int(request.args.get("page", 1))
    limit = int(request.args.get("limit", 50))
    cache_key = f"{cls}|{cycle}|{page}|{limit}"
    now = __import__('time').time()
    if cache_key in _ATT_CACHE:
        cached = _ATT_CACHE[cache_key]
        if now - cached["ts"] < 30:  # 30秒缓存
            return jsonify(cached["data"])
    result, total = db.attendance_by_lesson(class_name=cls or None, cycle=cycle or None, limit=limit, page=page)
    data = {"rows": result, "total": total, "page": page, "limit": limit}
    _ATT_CACHE[cache_key] = {"data": data, "ts": now}
    return jsonify(data)

# ====== 缴费分页 ======

@app.route("/api/purchases")
def purchases_paginated():
    page = int(request.args.get("page", 1))
    limit = int(request.args.get("limit", 100))
    student = request.args.get("student", "").strip() or None
    segment = request.args.get("segment", "").strip() or None
    class_name = request.args.get("class", "").strip() or None
    search = request.args.get("search", "").strip() or None
    discount = request.args.get("discount", "").strip() or None
    return jsonify(db.purchases_paginated(page, limit, student_name=student, segment=segment, class_name=class_name, search=search, discount_type=discount))

# ====== 分账 ======

@app.route("/api/revenue-splits/generate", methods=["POST"])
def revenue_splits_generate():
    """从 attendance 自动生成分账行"""
    from db import get_db, _execute
    # Save existing coefficients, notes, other_cost, neukol_fee before wiping
    saved = {}
    for old in _execute(get_db(), "SELECT cycle, content_label, xinxin_coef, sitong_coef, biscuit_coef, notes, other_cost, neukol_fee FROM revenue_splits").fetchall():
        saved[(old['cycle'], old['content_label'])] = {
            'xc': old['xinxin_coef'] if old['xinxin_coef'] is not None else 0.9,
            'sc': old['sitong_coef'] if old['sitong_coef'] is not None else 0.1,
            'bc': old['biscuit_coef'] if old['biscuit_coef'] is not None else 0.0,
            'notes': old['notes'] or '',
            'other': float(old['other_cost'] or 0),
            'neukol': float(old['neukol_fee'] or 0),
            'rxc': float(old['recruit_xin_coef'] if old['recruit_xin_coef'] is not None else 1.0)
        }
    _execute(get_db(), "DELETE FROM revenue_splits")
    # Step 1: 每班正价 = 众数非零价（已是9折后）
    price_rows = _execute(get_db(), """
        SELECT class_name, consumed_price, COUNT(*) as cnt
        FROM attendance WHERE consumed_price>0 AND status='出席'
        GROUP BY class_name, consumed_price
    """).fetchall()
    cls_price = {}  # class_name -> unit_price
    cls_counts = {}
    for pr in price_rows:
        cn, cp, cnt = pr['class_name'], float(pr['consumed_price']), int(pr['cnt'])
        if cn not in cls_counts or cnt > cls_counts[cn]:
            cls_counts[cn] = cnt
            cls_price[cn] = cp
    ref_sup = {}  # (cycle, content_label) -> {'total': 0, 'xin': 0, 'bis': 0}
    # Step 2a: 转介绍赠 → consumed_price=0 的消耗记录
    ref_rows = _execute(get_db(), """
        SELECT a.cycle, a.content_label, ANY_VALUE(ct.teacher) as teacher, a.class_name, COUNT(DISTINCT a.id) as free_cnt
        FROM attendance a
        LEFT JOIN (SELECT class_name, ANY_VALUE(created_by) as teacher FROM config GROUP BY class_name) ct ON a.class_name=ct.class_name
        WHERE a.status='出席' AND a.consumed_price=0 AND a.cycle!='' AND a.content_label!=''
          AND a.student_name IN (SELECT DISTINCT student_name FROM purchases WHERE discount_type='转介绍赠')
        GROUP BY a.cycle, a.content_label, a.class_name
    """).fetchall()
    for rr in ref_rows:
        key = (rr['cycle'], rr['content_label'])
        if key not in ref_sup: ref_sup[key] = {'total':0,'xin':0,'bis':0}
        up = cls_price.get(rr['class_name'], 180.0)
        amt = round(up * int(rr['free_cnt']), 2)
        ref_sup[key]['total'] += amt
        t = (rr['teacher'] or '').strip()
        if t == '欣欣': ref_sup[key]['xin'] += amt
        elif t == '饼干': ref_sup[key]['bis'] += amt
    # Step 2b: 已退款 → 已消耗的课节，按消耗记录所在周期
    refund_rows = _execute(get_db(), """
        SELECT a.cycle, a.content_label, a.class_name, COUNT(DISTINCT a.id) as cnt
        FROM attendance a
        WHERE a.status='出席' AND a.cycle!='' AND a.content_label!=''
          AND a.student_name IN (SELECT DISTINCT student_name FROM purchases WHERE discount_type='已退款')
        GROUP BY a.cycle, a.content_label, a.class_name
    """).fetchall()
    for rr in refund_rows:
        key = (rr['cycle'], rr['content_label'])
        if key not in ref_sup: ref_sup[key] = {'total':0,'xin':0,'bis':0}
        up = cls_price.get(rr['class_name'], 180.0)
        amt = round(up * int(rr['cnt']), 2)
        ref_sup[key]['total'] += amt
        tchr_row = _execute(get_db(), "SELECT ANY_VALUE(created_by) as t FROM config WHERE class_name=%s GROUP BY class_name", [rr['class_name']]).fetchone()
        t = (tchr_row['t'].strip() if tchr_row and tchr_row['t'] else '') if tchr_row else ''
        if t == '欣欣': ref_sup[key]['xin'] += amt
        elif t == '饼干': ref_sup[key]['bis'] += amt
    # Step 2c: 平台服务费 → 按缴费日期归入 (cycle, content_label) 的日期范围
    plat_fees = {}  # (cycle, content_label) -> total
    all_purchases = _execute(get_db(), "SELECT method, amount, actual_pay_date FROM purchases WHERE method IN ('微信转账','支付宝转账','小红书订单','其他')").fetchall()
    # Build (cycle, content_label) -> (min_date, max_date) ranges from attendance
    cl_ranges = _execute(get_db(), """
        SELECT cycle, content_label, MIN(lesson_date) as d1, MAX(lesson_date) as d2
        FROM attendance WHERE cycle!='' AND content_label!='' AND status='出席'
        GROUP BY cycle, content_label
    """).fetchall()
    range_list = []
    for cr in cl_ranges:
        range_list.append((cr['cycle'], cr['content_label'], cr['d1'], cr['d2']))
    def find_cl(pd):
        # Find range where pd falls, or closest range
        # For each cycle, find the content_label whose d1 is largest among those <= pd
        best = None
        for cyc, cl, d1, d2 in range_list:
            if d1 <= pd and (best is None or d1 > best[0]):
                best = (d1, cyc, cl)
        if best: return (best[1], best[2])
        # pd is before all ranges — use earliest range
        earliest = min(range_list, key=lambda x: x[2]) if range_list else None
        return (earliest[0], earliest[1]) if earliest else ('','')
    for ap in all_purchases:
        mtd = ap['method'] or ''; amt = float(ap['amount'] or 0); pd = (ap['actual_pay_date'] or '')[:10]
        if not amt or not pd: continue
        fee = 0
        if mtd in ('微信转账','其他'): fee = amt * 0.001
        elif mtd == '支付宝转账': fee = amt * 0.006
        elif mtd == '小红书订单': fee = amt * (0.006 if pd < '2026-05-30' else 0.02)
        if not fee: continue
        cyc, cl = find_cl(pd)
        if cyc and cl:
            key = (cyc, cl)
            plat_fees[key] = round((plat_fees.get(key, 0) + fee), 2)
    # Step 3: 新入班数 = 学生首次出勤所在的 (cycle, content_label)
    first_att = {}
    fa_rows = _execute(get_db(), """
        SELECT student_name, cycle, content_label FROM attendance a
        WHERE status='出席' AND cycle!='' AND content_label!=''
        AND lesson_date = (SELECT MIN(lesson_date) FROM attendance WHERE student_name=a.student_name AND status='出席')
    """).fetchall()
    for fa in fa_rows:
        key = (fa['cycle'], fa['content_label'])
        first_att[key] = first_att.get(key, 0) + 1
    # Step 4: 主汇总查询（用子查询避免 config 多行导致膨胀）
    rows = _execute(get_db(), """
        SELECT a.cycle, a.content_label,
            COALESCE(SUM(CASE WHEN a.status='出席' THEN a.consumed_price ELSE 0 END),0) as revenue,
            COUNT(DISTINCT CASE WHEN a.status='出席' AND a.consumed_price IN (69.9, 99.9) THEN a.student_name END) as trial_count,
            COUNT(DISTINCT CASE WHEN a.status='出席' AND a.consumed_price NOT IN (69.9, 99.9, 0) THEN a.student_name END) as formal_count,
            COALESCE(SUM(CASE WHEN a.status='出席' AND ct.teacher='欣欣' THEN a.consumed_price ELSE 0 END)*0.5,0) as xin_base,
            COALESCE(SUM(CASE WHEN a.status='出席' AND ct.teacher='饼干' THEN a.consumed_price ELSE 0 END)*0.5,0) as bis_base
        FROM attendance a
        LEFT JOIN student_ext se ON a.student_name=se.student_name
        LEFT JOIN (SELECT class_name, ANY_VALUE(created_by) as teacher FROM config GROUP BY class_name) ct ON a.class_name=ct.class_name
        WHERE a.status='出席' AND a.cycle!='' AND a.content_label!=''
        GROUP BY a.cycle, a.content_label ORDER BY a.cycle, a.content_label
    """).fetchall()
    for r in rows:
        rev = float(r['revenue'])
        key = (r['cycle'], r['content_label'])
        rs = ref_sup.get(key, {'total':0,'xin':0,'bis':0})
        ref = rs['total']
        base = rev + ref  # 收入 + 转介/补
        xin_lesson = round(float(r['xin_base']) + rs['xin'] * 0.5, 2)
        bis_lesson = round(float(r['bis_base']) + rs['bis'] * 0.5, 2)
        l50 = round(base*0.5,2)
        t20 = round(base*0.2,2)
        s20 = round(base*0.2,2)
        sv = saved.get((r['cycle'], r['content_label']), {})
        xc = float(sv.get('xc', 0.9)); sc = float(sv.get('sc', 0.1)); bc = float(sv.get('bc', 0.0))
        # Normalize: if sum != 1.0, adjust proportionally
        coe_sum = xc + sc + bc
        if coe_sum > 0 and abs(coe_sum - 1.0) > 0.001:
            xc = round(xc / coe_sum, 2); sc = round(sc / coe_sum, 2); bc = round(1.0 - xc - sc, 2)
        xs = round(t20*xc,2)
        ss = round(t20*sc,2)
        bs = round(t20*bc,2)
        pf = plat_fees.get((r['cycle'], r['content_label']), 0.0)
        other_val = sv.get('other', 0.0)
        neukol_val = sv.get('neukol', 0.0)
        notes_val = sv.get('notes', '')
                # 生源拆分: 招生 / 转化 / 续费
        trial = int(r['trial_count'])
        converted_cnt = 0
        if trial > 0:
            trial_names = [row['student_name'] for row in _execute(get_db(), """
                SELECT DISTINCT a.student_name FROM attendance a
                WHERE a.cycle=%s AND a.content_label=%s AND a.status='出席' AND a.consumed_price IN (69.9, 99.9)
                AND a.lesson_date = (SELECT MIN(lesson_date) FROM attendance WHERE student_name=a.student_name AND status='出席')
            """, [r['cycle'], r['content_label']]).fetchall()]
            if trial_names:
                placeholders = ','.join(['%s']*len(trial_names))
                later_rows = _execute(get_db(), f"SELECT DISTINCT student_name FROM attendance WHERE student_name IN ({placeholders}) AND status='出席' AND consumed_price>70 AND (cycle!=%s OR content_label!=%s)", trial_names + [r['cycle'], r['content_label']]).fetchall()
                converted_names = {lr['student_name'] for lr in later_rows}
                converted_cnt = sum(1 for n in trial_names if n in converted_names)
        # Teacher split ratio
        total_les = xin_lesson + bis_lesson
        les_xin_ratio = xin_lesson / total_les if total_les > 0 else 1.0
        # Count trial students per teacher for this content
        trial_xin = trial_bis = 0
        if trial > 0:
            t_rows = _execute(get_db(), """
                SELECT ANY_VALUE(ct.teacher) as t FROM attendance a
                LEFT JOIN (SELECT class_name, ANY_VALUE(created_by) as teacher FROM config GROUP BY class_name) ct ON a.class_name=ct.class_name
                WHERE a.cycle=%s AND a.content_label=%s AND a.status='出席' AND a.consumed_price IN (69.9, 99.9)
                AND a.lesson_date = (SELECT MIN(lesson_date) FROM attendance WHERE student_name=a.student_name AND status='出席')
                GROUP BY a.student_name
            """, [r['cycle'], r['content_label']]).fetchall()
            for tr in t_rows:
                t = (tr['t'] or '').strip()
                if t == '饼干': trial_bis += 1
                elif t == '欣欣': trial_xin += 1
        actual_trial = trial_xin + trial_bis
        # 招生 = 试听 × 40
        recruitment = actual_trial * 40
        # 转化: 每师保底¥20 + 成功¥40（成功按试听老师分配）
        # Use trial_xin/trial_bis counts already computed; for bonus, assume same ratio
        if actual_trial > 0:
            converted_xin = int(converted_cnt * trial_xin / actual_trial)
            converted_bis = converted_cnt - converted_xin
        else:
            converted_xin = converted_bis = 0
        conversion_xin = trial_xin * 20 + converted_xin * 40
        conversion_bis = trial_bis * 20 + converted_bis * 40
        conversion = conversion_xin + conversion_bis
        # 续费 = 正式人次 × 20, 按老师实际正式学生数拆分
        formal_xin = formal_bis = 0
        f_rows = _execute(get_db(), """
            SELECT ANY_VALUE(ct.teacher) as t, COUNT(DISTINCT a.student_name) as cnt FROM attendance a
            LEFT JOIN (SELECT class_name, ANY_VALUE(created_by) as teacher FROM config GROUP BY class_name) ct ON a.class_name=ct.class_name
            WHERE a.cycle=%s AND a.content_label=%s AND a.status='出席' AND a.consumed_price NOT IN (69.9, 99.9, 0)
            GROUP BY ct.teacher
        """, [r['cycle'], r['content_label']]).fetchall()
        for fr in f_rows:
            tchr = (fr['t'] or '').strip(); cnt = int(fr['cnt'])
            if tchr == '欣欣': formal_xin = cnt
            elif tchr == '饼干': formal_bis = cnt
        retention_xin = formal_xin * 20
        retention_bis = formal_bis * 20
        retention = retention_xin + retention_bis
        # 招生拆分: 手动欣%
        rxc = float(sv.get('rxc', 1.0))
        recruit_xin = round(recruitment * rxc, 2)
        recruit_bis = round(recruitment - recruit_xin, 2)
        # Net balance
        s20 = 0  # 生源不再作为固定比例扣除
        nb = round(base-l50-xs-ss-bs-recruitment-conversion-retention-pf-other_val,2)
        _execute(get_db(), """INSERT INTO revenue_splits
            (cycle,content_label,revenue,trial_count,formal_count,referral_supplement,platform_fee,new_enroll,recruitment,recruit_xin_coef,recruit_xin,recruit_bis,conversion,conversion_xin,conversion_bis,retention,retention_xin,retention_bis,
             lesson_50pct,xinxin_lesson_share,biscuit_lesson_share,teaching_20pct,
             xinxin_coef,xinxin_share,sitong_coef,sitong_share,biscuit_coef,biscuit_share,source_20pct,neukol_fee,other_cost,notes,net_balance)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            [r['cycle'], r['content_label'], rev, int(r['trial_count']), int(r['formal_count']), ref, pf, trial, recruitment, rxc, recruit_xin, recruit_bis, conversion, conversion_xin, conversion_bis, retention, retention_xin, retention_bis,
             l50, xin_lesson, bis_lesson, t20,
             xc, xs, sc, ss, bc, bs, retention, neukol_val, other_val, notes_val, nb])
    return jsonify({"status":"ok"})

@app.route("/api/revenue-splits")
def revenue_splits_list():
    cycle = request.args.get("cycle", "")
    return jsonify(db.revenue_split_list(cycle=cycle or None))

def rebuild_net_balance(rid):
    """重算单行结余: 收入 - 课时50% - 教研(三师) - 生源20% - Neu - 其他"""
    from db import get_db, _execute
    r = _execute(get_db(), "SELECT revenue, lesson_50pct, xinxin_share, sitong_share, biscuit_share, source_20pct, neukol_fee, other_cost, platform_fee FROM revenue_splits WHERE id=%s", [rid]).fetchone()
    if not r: return
    nb = round(float(r['revenue']) - float(r['lesson_50pct']) - float(r['xinxin_share']) - float(r['sitong_share']) - float(r['biscuit_share']) - float(r['recruitment'] or 0) - float(r['conversion'] or 0) - float(r['retention'] or 0) - float(r['other_cost'] or 0) - float(r['platform_fee'] or 0), 2)
    _execute(get_db(), "UPDATE revenue_splits SET net_balance=%s WHERE id=%s", [nb, rid])

@app.route("/api/revenue-splits", methods=["POST"])
def revenue_splits_save():
    data = request.json
    from db import get_db, _execute
    rid = data.get("id", 0)
    if data.get("coef_update"):
        teacher = data.get("teacher")
        val = float(data.get("value", 0))
        if teacher == 'recruit_xin':
            # 招生欣比例: recruit_xin_coef
            _execute(get_db(), "UPDATE revenue_splits SET recruit_xin_coef=%s WHERE id=%s", [val, rid])
            r = _execute(get_db(), "SELECT recruitment FROM revenue_splits WHERE id=%s", [rid]).fetchone()
            if r:
                rec = float(r['recruitment'])
                _execute(get_db(), "UPDATE revenue_splits SET recruit_xin=%s, recruit_bis=%s WHERE id=%s", [round(rec*val,2), round(rec*(1-val),2), rid])
        else:
            # 更新教研系数并重算份额: 教研20% × 系数
            col = teacher + "_coef"
            _execute(get_db(), f"UPDATE revenue_splits SET {col}=%s WHERE id=%s", [val, rid])
            r = _execute(get_db(), "SELECT teaching_20pct FROM revenue_splits WHERE id=%s", [rid]).fetchone()
            if r:
                t20 = float(r['teaching_20pct'])
                share = round(t20 * val, 2)
                share_col = teacher + "_share"
                _execute(get_db(), f"UPDATE revenue_splits SET {share_col}=%s WHERE id=%s", [share, rid])
            rebuild_net_balance(rid)
    elif data.get("num_update"):
        field = data.get("field")
        if field == "notes":
            val = data.get("value", "")
            _execute(get_db(), f"UPDATE revenue_splits SET notes=%s WHERE id=%s", [val, rid])
        else:
            val = float(data.get("value", 0))
            if field == "neukol": field = "neukol_fee"
            elif field == "other": field = "other_cost"
            _execute(get_db(), f"UPDATE revenue_splits SET {field}=%s WHERE id=%s", [val, rid])
            if field in ("neukol_fee", "other_cost"):
                rebuild_net_balance(rid)
        if field in ("neukol_fee", "other_cost"):
            rebuild_net_balance(rid)
    else:
        db.revenue_split_upsert(data)
    return jsonify({"status": "ok"})

@app.route("/api/revenue-splits/import-neukol", methods=["POST"])
def revenue_splits_import_neukol():
    """从 Excel 导入 Neukol 服务费，按 cycle + content_label 汇总"""
    if "file" not in request.files:
        return jsonify({"status": "error", "message": "请上传文件"}), 400
    file = request.files["file"]
    import tempfile, openpyxl
    tmp = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
    file.save(tmp.name)
    tmp.close()
    from db import get_db, _execute
    updated = 0
    try:
        wb = openpyxl.load_workbook(tmp.name, data_only=True)
        # Use neukol时长明细 sheet if exists, else active
        ws = wb['neukol时长明细'] if 'neukol时长明细' in wb.sheetnames else wb.active
        # Aggregate fees by (cycle, content_label)
        fees = {}  # (cycle, content_label) -> total
        for row in ws.iter_rows(min_row=2, values_only=True):
            if not row[0]: continue
            cycle = str(row[0] or "").strip()
            content_label = str(row[1] or "").strip()
            fee = float(str(row[11] or "0").replace("¥","").replace(",","").replace(" ","") or 0)
            if not cycle or not content_label or not fee: continue
            key = (cycle, content_label)
            fees[key] = round(fees.get(key, 0) + fee, 2)
        for (cycle, cl), fee in fees.items():
            r = _execute(get_db(), "SELECT id FROM revenue_splits WHERE cycle=%s AND content_label=%s", [cycle, cl]).fetchone()
            if r:
                _execute(get_db(), "UPDATE revenue_splits SET neukol_fee=%s WHERE id=%s", [fee, r['id']])
                # Neukol is informational, no rebuild_net_balance
                updated += 1
        return jsonify({"status": "ok", "updated": updated})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        os.unlink(tmp.name)

@app.route("/api/teacher-coefficients")
def teacher_coefficients_list():
    return jsonify(db.teacher_coefficients_all())

@app.route("/api/teacher-coefficients", methods=["POST"])
def teacher_coefficients_save():
    data = request.json
    db.teacher_coefficient_set(data["teacher_name"], data["coefficient"], data["hourly_rate"])
    return jsonify({"status": "ok"})

# ====== 班级消课情况 ======

@app.route("/api/attendance/class-breakdown")
def class_breakdown():
    from db import get_db, _execute
    rows = _execute(get_db(), """
        SELECT cycle, content_label, class_name,
            COUNT(DISTINCT CASE WHEN consumed_price IN (69.9, 99.9) THEN student_name END) as trial,
            COUNT(DISTINCT CASE WHEN consumed_price NOT IN (69.9, 99.9, 0) THEN student_name END) as formal,
            GROUP_CONCAT(DISTINCT CASE WHEN consumed_price IN (69.9, 99.9) THEN student_name END SEPARATOR ', ') as trial_names
        FROM attendance WHERE status='出席' AND cycle!='' AND content_label!=''
        GROUP BY cycle, content_label, class_name
        ORDER BY cycle, content_label, class_name
    """).fetchall()
    result = {}
    for r in rows:
        key = r['cycle'] + '|' + r['content_label']
        if key not in result: result[key] = []
        result[key].append({'class': r['class_name'], 'trial': int(r['trial'] or 0), 'formal': int(r['formal'] or 0), 'trial_names': r['trial_names'] or ''})
    return jsonify(result)

# ====== 课后素材图片 ======

@app.route("/api/class-material", methods=["POST"])
def class_material_upload():
    if "file" not in request.files:
        return jsonify({"status": "error", "message": "请上传文件"}), 400
    file = request.files["file"]
    segment = request.form.get("segment", "")
    if segment not in ("探索段", "启航段"):
        return jsonify({"status": "error", "message": "无效分段"}), 400
    # Store in static/class-material/
    import os as _os
    mat_dir = _os.path.join(BASE_DIR, "static", "class-material")
    _os.makedirs(mat_dir, exist_ok=True)
    # 探索段 from 周四探索, 启航段 from 周五启航
    fname = f"课后素材-{segment}.png"
    fpath = _os.path.join(mat_dir, fname)
    file.save(fpath)
    return jsonify({"status": "ok", "path": f"/static/class-material/{fname}"})

# ====== 结算单 ======

@app.route("/api/settlements")
def settlements_list():
    return jsonify(db.settlement_list())

@app.route("/api/settlements", methods=["POST"])
def settlements_create():
    data = request.json
    if data.get("batch"):
        # Batch create from selected cycles
        results = []
        for item in data.get("items", []):
            item["created_at"] = data.get("created_at", "")
            db.settlement_create(item)
            results.append(item)
        return jsonify({"status": "ok", "count": len(results)})
    else:
        db.settlement_create(data)
        return jsonify({"status": "ok"})

@app.route("/api/settlements/<int:sid>", methods=["POST"])
def settlements_update(sid):
    data = request.json
    db.settlement_update_status(sid, data.get("status", "已结算"), data.get("settled_date", ""))
    return jsonify({"status": "ok"})

@app.route("/api/settlements/<int:sid>", methods=["DELETE"])
def settlements_delete(sid):
    db.settlement_delete(sid)
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    print(f"追光π 课后素材 → http://localhost:{_PORT}")
    if not os.environ.get("DEEPSEEK_API_KEY"):
        print("  Tip: export DEEPSEEK_API_KEY=sk-xxx  → 启用 AI 课后反馈")
    else:
        print("  AI 课后反馈: 已启用 (DeepSeek)")
    # 预热 TiDB 连接和缓存
    print("  预热中...")
    try:
        db.get_db()
        from collections import OrderedDict
        cfg, all_lessons, summary, weekly = db.config_and_lessons()
        out = OrderedDict()
        for k in sort_class_names(cfg.keys()): out[k] = cfg[k]
        zg_user = os.environ.get("ZG_USER", "")
        import time
        _CONFIG_CACHE["data"] = {"classes": out, "lessons": all_lessons, "zg_user": zg_user, "summary": summary, "weekly": weekly}
        _CONFIG_CACHE["ts"] = time.time()
        print("  数据库就绪 ✓")
    except Exception as e:
        print(f"  预热跳过: {e}")
    app.run(host="127.0.0.1", port=_PORT, debug=False, threaded=True)
