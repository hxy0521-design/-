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
    return folder.split("-2605")[0]

def unit_from_folder(folder):
    parts = folder.split("-")
    return parts[1] if len(parts) > 1 else "2605"

def unit_path(cls_name, unit_code):
    u = db.config_get_unit(cls_name, unit_code)
    return u.get("path", "")

def source_path():
    """共享底表路径（欣欣和饼干共用同一个）"""
    db_dir = os.path.dirname(os.environ.get("ZG_DB", ""))
    return os.path.join(db_dir, "底表")

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
    """扫描共享底表找课节 txt（格式：班级-单元名-#课节号 课节名.txt）"""
    lessons = []
    src = source_path()
    unit_info = db.config_get_unit(cls_name, unit_code)
    unit_name = unit_info.get("name", unit_code)
    unit_dir = os.path.join(src, unit_name)
    if not os.path.isdir(unit_dir): return lessons
    prefix = f"{cls_name}-{unit_name}-"
    for f in sorted(os.listdir(unit_dir)):
        if not f.startswith(prefix) or not f.endswith(".txt"): continue
        txt_path = os.path.join(unit_dir, f)
        # 解析文件名: 班级-单元名-#课节号 课节名.txt
        rest = f[len(prefix):-4]
        parts = rest.split(" ", 1)
        lesson_num = parts[0] if parts else "1"
        lesson_title = parts[1] if len(parts) > 1 else rest
        title, date = lesson_title, ""
        try:
            with open(txt_path, encoding='utf-8') as fh:
                for line in fh:
                    s = line.strip()
                    if s.startswith("@title"): title = s[7:].strip()
                    if s.startswith("@date"): date = s[6:].strip()
        except: pass
        folder = f"{cls_name}-{unit_code}-{lesson_num}"
        lessons.append({
            "folder": folder, "lesson": lesson_num,
            "title": title, "date": date, "unit_name": unit_name
        })
    return lessons

# ====== API ======

@app.route("/")
def index():
    return send_from_directory(os.path.join(BASE_DIR, "static"), "index.html")

@app.route("/test")
def test_page():
    return send_from_directory(os.path.join(BASE_DIR, "static"), "test.html")

@app.route("/api/config")
def get_config_api():
    from collections import OrderedDict
    cfg = get_config()
    out = OrderedDict()
    for k in sort_class_names(cfg.keys()):
        out[k] = cfg[k]
    zg_user = os.environ.get("ZG_USER", "")
    return jsonify({"classes": out, "zg_user": zg_user})

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
    cls = OrderedDict()
    for class_name in sort_class_names(cfg.keys()):
        cls[class_name] = {}
        for unit_code, info in cfg[class_name].items():
            path = info.get("path", "")
            ls = scan_lessons(class_name, unit_code, path)
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
    return jsonify({"status": "ok", "name": name})

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
    return jsonify({"status": "ok"})

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
    return jsonify({"status": "ok", "code": unit_code})

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
    # 从共享底表读源文件
    unit_info = db.config_get_unit(cls_name, unit_code)
    unit_name = unit_info.get("name", unit_code)
    src_dir = os.path.join(source_path(), unit_name)
    txt = None
    lesson_num = folder.split(f"-{unit_code}-")[-1] if f"-{unit_code}-" in folder else "1"
    prefix = f"{cls_name}-{unit_name}-{lesson_num} "
    if os.path.isdir(src_dir):
        for f in sorted(os.listdir(src_dir)):
            if f.startswith(prefix) and f.endswith(".txt"):
                txt = os.path.join(src_dir, f); break
    if not txt:
        # fallback: check unit_path
        short = folder.split(f"-{unit_code}-")[0]
        p = os.path.join(base, folder)
        txt = os.path.join(p, f"{short}.txt") if os.path.isdir(p) else None
    from generate_class_image import parse_input_txt
    meta, topics = parse_input_txt(txt) if txt and os.path.exists(txt) else ({}, [])
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
    if txt and os.path.exists(txt):
        outputs.append({"name": os.path.basename(txt), "path": f"/api/file/{folder}/{os.path.basename(txt)}"})
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
    # 写到共享底表
    unit_info = db.config_get_unit(cls_name, unit_code)
    unit_name = unit_info.get("name", unit_code)
    src_dir = os.path.join(source_path(), unit_name)
    os.makedirs(src_dir, exist_ok=True)
    lesson_num = folder.split(f"-{unit_code}-")[-1] if f"-{unit_code}-" in folder else "1"
    # 删除旧版同名文件（标题可能变了）
    old_prefix = f"{cls_name}-{unit_name}-{lesson_num} "
    if os.path.isdir(src_dir):
        for old_f in os.listdir(src_dir):
            if old_f.startswith(old_prefix) and old_f.endswith(".txt"):
                os.remove(os.path.join(src_dir, old_f))
    title_safe = meta.get("title", folder)[:30].replace("/", " ").replace(":", " ")
    txt_name = f"{cls_name}-{unit_name}-{lesson_num} {title_safe}.txt"
    txt_path = os.path.join(src_dir, txt_name)
    # 确保本地输出目录存在
    p = os.path.join(base, folder)
    if not os.path.isdir(p): os.makedirs(p, exist_ok=True)
    # 保存图片
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
    with open(txt_path, 'w', encoding='utf-8') as f:
        f.write(f"# ====== 课节信息 ======\n@title {meta.get('title','')}\n@unit {meta.get('unit','')}\n@date {meta.get('date','')}\n@class {meta.get('class','')}\n")
        if meta.get('gender'): f.write(f"@gender {meta['gender']}\n")
        f.write("\n# ====== 课堂发言 ======\n")
        for t in topics_data:
            f.write(t.get("title","") + "\n")
            for s in t.get("speeches",[]):
                f.write(f"{s.get('name','')}：{s.get('content','')}\n")
            f.write("\n")
    return jsonify({"status":"ok","folder":folder})

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
        # 也查底表已有文件，避免底表和输出目录不同步导致跳号
        unit_info_tmp = db.config_get_unit(cls, unit_code)
        unit_name_tmp = unit_info_tmp.get("name", unit_code)
        src_dir_tmp = os.path.join(source_path(), unit_name_tmp)
        if os.path.isdir(src_dir_tmp):
            for f in os.listdir(src_dir_tmp):
                if f.startswith(f"{cls}-{unit_name_tmp}-") and f.endswith(".txt"):
                    try:
                        n = int(f[len(f"{cls}-{unit_name_tmp}-"):].split(" ",1)[0])
                        max_n = max(max_n, n)
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

    # 写 TXT 到本地输出目录（供生成脚本读取，生成完后删除）
    short = folder.split(f"-{unit_code}-")[0]
    txt_path = os.path.join(folder_path, f"{short}.txt")
    with open(txt_path, 'w', encoding='utf-8') as f:
        f.write(f"# ====== 课节信息 ======\n@title {title}\n@unit {unit}\n@date {date}\n@class {cls}\n")
        if gender: f.write(f"@gender {gender}\n")
        f.write("\n# ====== 推荐 ======\n")
        for name, info in movies.items():
            if info.get("movie"):
                f.write(f"@student {name}\n")
                if info.get("quote"): f.write(f"@quote {info['quote']}\n")
                f.write(f"@movie {info['movie']}\n")
                if info.get("poster"): f.write(f"@poster {info['poster']}\n")
                if info.get("rating"): f.write(f"@rating {info['rating']}\n")
                if info.get("line"): f.write(f"@line {info['line']}\n")
                f.write("\n")
        for name, info in poster_qs.items():
            if info.get("movie") or info.get("quote"):
                f.write(f"@student {name}\n")
                if info.get("quote"): f.write(f"@quote {info['quote']}\n")
                if info.get("movie"): f.write(f"@movie {info['movie']}\n")
                if info.get("poster"): f.write(f"@poster {info['poster']}\n")
                if info.get("rating"): f.write(f"@rating {info['rating']}\n")
                if info.get("line"): f.write(f"@line {info['line']}\n")
                f.write("\n")
        f.write("\n# ====== 课堂发言 ======\n")
        for t in topics_data:
            f.write(t["title"] + "\n")
            for s in t["speeches"]:
                f.write(f"{s['name']}：{s['content']}\n")
            f.write("\n")

    # 同步复制到底表（持久化，供 scan_lessons 扫描）
    unit_info = db.config_get_unit(cls, unit_code)
    unit_name = unit_info.get("name", unit_code)
    src_dir = os.path.join(source_path(), unit_name)
    os.makedirs(src_dir, exist_ok=True)
    lesson_num = folder.split(f"-{unit_code}-")[-1] if f"-{unit_code}-" in folder else "1"
    old_prefix = f"{cls}-{unit_name}-{lesson_num} "
    if os.path.isdir(src_dir):
        for old_f in os.listdir(src_dir):
            if old_f.startswith(old_prefix) and old_f.endswith(".txt"):
                os.remove(os.path.join(src_dir, old_f))
    title_safe = title[:30].replace("/", " ").replace(":", " ")
    base_txt_name = f"{cls}-{unit_name}-{lesson_num} {title_safe}.txt"
    shutil.copy(txt_path, os.path.join(src_dir, base_txt_name))

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
    # 删除生成用的临时 TXT（底表已有持久副本，不留在输出目录）
    if os.path.exists(txt_path):
        os.remove(txt_path)

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
    # 优先查本地输出
    if base:
        fp = os.path.join(base, folder)
        if os.path.isfile(os.path.join(fp, filename)):
            return send_from_directory(fp, filename)
    # 再查共享底表
    unit_info = db.config_get_unit(cls_name, unit_code)
    unit_name = unit_info.get("name", unit_code)
    src_dir = os.path.join(source_path(), unit_name)
    if os.path.isfile(os.path.join(src_dir, filename)):
        return send_from_directory(src_dir, filename)
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

if __name__ == "__main__":
    print(f"追光π 课后素材 → http://localhost:{_PORT}")
    if not os.environ.get("DEEPSEEK_API_KEY"):
        print("  Tip: export DEEPSEEK_API_KEY=sk-xxx  → 启用 AI 课后反馈")
    else:
        print("  AI 课后反馈: 已启用 (DeepSeek)")
    app.run(host="127.0.0.1", port=_PORT, debug=False)
