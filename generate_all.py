"""
一站式生成：长图 + 单人卡 + 每人金句海报
用法：python3 generate_all.py your_file.txt
"""
import sys, os, re
sys.dont_write_bytecode = True
from collections import defaultdict
from PIL import Image
from generate_class_image import (
    parse_input_txt, auto_select_highlights, split_sentences,
    generate_image, clean_content
)
from generate_golden_card import make_card as make_golden_card, PALETTES, pick_palette

HIGHLIGHTS_PER = 3; CARD_HL_PER = 5

def parse_extra_movies(filepath):
    """提取每人推荐信息：@student 名字 开头，后续 @quote/@movie/@poster/@rating/@line
       @quote 支持多行（后续行直到下一个 @ 字段）"""
    movies = defaultdict(dict)
    cur_student = None
    cur_key = None
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            s = line.strip()
            if not s:
                cur_key = None  # 空行结束多行值
                continue
            if s.startswith('@'):
                parts = s[1:].split(None, 1)
                key = parts[0].lower()
                val = parts[1] if len(parts) > 1 else ""
                if key == "student":
                    cur_student = val.strip() or None
                    cur_key = None
                elif key in ("movie","poster","rating","line") and cur_student:
                    movies[cur_student][key] = val
                    cur_key = key
                elif key == "quote" and cur_student:
                    if "quotes" not in movies[cur_student]:
                        movies[cur_student]["quotes"] = []
                    movies[cur_student]["quotes"].append(val)
                    movies[cur_student]["quote"] = val  # backward compat
                    cur_key = "quote"
                else:
                    cur_key = None
            elif cur_student and cur_key:
                # 续行：追加到当前字段
                prev = movies[cur_student].get(cur_key, "")
                movies[cur_student][cur_key] = prev + s
    return dict(movies)

def safe_fn(s):
    for ch in r'/:*?"<>|\\': s = s.replace(ch, "")
    return s.strip()

def generate_all(input_path, feedback_styles=None, golden_quotes=None, images_dir=None, memo_data=None):
    if feedback_styles is None: feedback_styles = ["xinxin"]
    if golden_quotes is None: golden_quotes = {}
    meta, topics = parse_input_txt(input_path)
    extra = parse_extra_movies(input_path)
    cls = safe_fn(meta.get("class", ""))
    title = safe_fn(meta.get("title","").replace("·","-"))

    print(f"Title: {meta.get('title','')}")
    print(f"Class: {cls}")
    print()

    # 保存课节记录到 TiDB（确保 CLI 生成也不会漏）
    try:
        from db import lesson_save, lesson_get, config_all
        with open(input_path, 'r', encoding='utf-8') as _f:
            _raw = _f.read()
        unit_code = "2605"
        unit_name = meta.get("unit","")
        _cfg = config_all()
        for _code, _info in _cfg.get(cls, {}).items():
            if _info.get("name","") == unit_name or _code in unit_name:
                unit_code = _code; break
        # 兜底：从路径中提取 unit_code（如 2606）
        if unit_code == "2605":
            _um = re.search(rf'{cls}-(\d{{4}})', input_path)
            if _um: unit_code = _um.group(1)
        lesson_num = 1
        # 从路径提取课节号: .../周日启航3-2606-3/xxx.txt → lesson_num=3
        _m = re.search(rf'{cls}-{unit_code}-(\d+)', input_path) or \
             re.search(rf'{cls}-{unit_code}-(\d+)', os.path.basename(os.path.dirname(input_path)))
        if not _m:
            _m = re.search(rf'/{cls}.*?-(\d+)\.txt$', input_path) or \
                 re.search(rf'{cls}-\d{{4}}-(\d+)', input_path)
        if _m:
            lesson_num = int(_m.group(1))
        _existing, _ = lesson_get(cls, unit_code, lesson_num)
        if not _existing:
            lesson_save(cls, unit_code, lesson_num, meta.get("title",""), _raw)
            print(f"  [DB] 课节记录已写入: {cls} {unit_code} #{lesson_num}")
    except Exception as _e:
        print(f"  [DB] 保存课节记录失败（不影响生成）: {_e}")

    # ====== 话题与发言对照 ======
    total_speeches = sum(len(s) for _, s in topics)
    print(f"本节课共 {len(topics)} 个小话题，{total_speeches} 次发言")

    print()
    for ti, (t, s) in enumerate(topics, 1):
        flag = "  ⚠ 无发言" if len(s) == 0 else ""
        print(f"  {ti}. [{len(s)}人] {t[:45]}{flag}")
    print()

    # ====== 自动检查 ======
    issues = []
    ok = []

    # 1. 字体
    font_path = None
    for p in [".font_path", os.path.expanduser("~/Library/Fonts/荆南麦圆体.ttf"),
              "/System/Library/Fonts/Hiragino Sans GB.ttc"]:
        if os.path.exists(p):
            font_path = p; break
    if font_path:
        # 如果是 .font_path 文件，读第一行作为真实字体名
        real_font = font_path
        if font_path.endswith(".font_path") and os.path.isfile(font_path):
            with open(font_path) as _f2:
                real_font = _f2.read().strip()
        ok.append("字体: " + os.path.basename(real_font))
    else:
        issues.append("字体: 未找到，请运行 setup.sh 或将字体放入目录")

    # 2. 图片资源
    for f, label in [("logo.png","logo"), ("slogan.png","slogan(长图)"), ("slogan单人.png","slogan(单人)")]:
        if os.path.exists(os.path.join(os.path.dirname(os.path.abspath(input_path)), f)):
            ok.append(label + " 存在")
        else:
            issues.append(label + " 缺失: " + f)

    # 3. 话题与发言
    empty_topics = [(t, len(s)) for t, s in topics if len(s) == 0]
    if empty_topics:
        for t, _ in empty_topics:
            issues.append("话题无匹配发言: " + t[:40])
    else:
        ok.append(f"{len(topics)}个话题全部匹配到发言")

    # 4. 学生性别
    from generate_feedback import parse_gender
    default_g, genders = parse_gender(input_path)
    all_names = set(n for _, ss in topics for n, _ in ss)
    missing_gender = all_names - set(genders.keys())
    if missing_gender:
        ok.append("性别: 默认" + default_g + "(" + str(len(missing_gender)) + "人未单独指定)")
    else:
        ok.append("性别: 全部已指定")

    # 5. 电影推荐
    golden_names = set(extra.keys()) & all_names
    if golden_names:
        ok.append("推荐: " + str(len(golden_names)) + "人有电影信息")
    else:
        ok.append("推荐: 未填写(金句海报将无电影区)")

    # 汇总
    print("检查结果:")
    for item in ok:
        print("  OK  " + item)
    for item in issues:
        print("  !!  " + item)
    print()
    if issues:
        print("以上问题修复后再跑。继续生成...")
        print()

    # --- 1. 长图 ---
    hl3 = auto_select_highlights(topics, per_student=HIGHLIGHTS_PER, title=meta.get("title",""))
    # 预览标了金句的学生：用标的结果覆盖自动选（不再合并）
    for name, quotes in golden_quotes.items():
        if not isinstance(quotes, list): quotes = [quotes]
        hl3[name] = quotes
    # poster_quotes 的学生也覆盖
    for name, info in extra.items():
        user_qs = info.get("quotes", [])
        if not user_qs and info.get("quote"):
            user_qs = [info["quote"]]
        if user_qs:
            hl3[name] = [info.get("quote","")]
    out_long = f"{title}_{cls}.png" if cls else f"{title}.png"

    # --- 2. 单人卡片 ---
    hl5 = auto_select_highlights(topics, per_student=CARD_HL_PER, title=meta.get("title",""))
    for name, info in extra.items():
        user_qs = info.get("quotes", [])
        if not user_qs and info.get("quote"):
            user_qs = [info["quote"]]
        if user_qs:
            if name not in hl5:
                hl5[name] = []
            hl5[name] = user_qs + [q for q in hl5[name] if q not in user_qs]
    input_dir = os.path.dirname(os.path.abspath(input_path))

    # 并行：长图 + 单人卡
    from concurrent.futures import ThreadPoolExecutor as _TPE
    with _TPE(max_workers=2) as _ex:
        _ex.submit(generate_image, meta, topics, out_long, highlights=hl3, images_dir=images_dir)
        _ex.submit(_gen_student_cards, meta, topics, input_dir, hl5, base_dir=input_dir)
    print(f"[1/5] 长图 → {out_long}")
    print(f"[2/5] 单人卡 → 单人总结_*.png")

    # --- 3. 每人金句海报 ---
    # 收集每人所有句子，选最高分一句 + 对应话题
    student_best = {}
    for name in set(n for _, ss in topics for n,_ in ss):
        all_sents = []
        for topic_title, ss in topics:
            for sn, sc in ss:
                if sn == name:
                    for st, _, _ in split_sentences(sc):
                        all_sents.append((st, topic_title))
        if all_sents:
            from generate_class_image import score_sentence
            scored = [(score_sentence(s, name, {}), s, t) for s, t in all_sents]
            scored.sort(key=lambda x: -x[0])
            student_best[name] = (scored[0][1], scored[0][2])

    golden_dir = "."
    golden_count = 0
    for name, quote in student_best.items():
        if name not in extra or "movie" not in extra[name]:
            continue
        poster = extra[name].get("poster","")
        if poster and not os.path.isabs(poster):
            poster = os.path.join(input_dir, poster)
        gmeta = {
            "title": meta.get("title",""),
            "unit": meta.get("unit",""),
            "date": meta.get("date",""),
            "class": meta.get("class",""),
            "quote": quote,
            "author": name,
            "movie": extra[name].get("movie",""),
            "poster": poster,
            "rating": extra[name].get("rating",""),
            "line": extra[name].get("line",""),
        }
        golden_count += 1

    golden_done = 0
    # 只生成有 poster_quotes 的学生（前端金句日历打勾的）
    has_poster_quotes = any(extra.get(n,{}).get("quote") for n in student_best)
    for name, (auto_quote, topic_title) in student_best.items():
        quote = extra.get(name, {}).get("quote","")
        if not quote: continue  # 没在金句日历打勾，跳过
        if not has_poster_quotes: continue
        if extra.get(name, {}).get("quote",""):
            for t, ss in topics:
                for sn, sc in ss:
                    if sn == name and quote in sc:
                        topic_title = t
                        break
        poster = extra.get(name, {}).get("poster","")
        if poster:
            # /api/material-file/... URL → 真实文件路径
            if poster.startswith("/api/material-file/"):
                _mat_base = os.environ.get("ZG_MATERIAL_BASE",
                    os.path.join(os.path.expanduser("~/Library/Mobile Documents/com~apple~CloudDocs/追光π课后素材生成系统"), "素材库"))
                poster = os.path.join(_mat_base, poster.replace("/api/material-file/", ""))
            elif not os.path.isabs(poster) and not poster.startswith("http"):
                poster = os.path.join(input_dir, poster)
        gmeta = {
            "title": meta.get("title",""), "unit": meta.get("unit",""),
            "date": meta.get("date",""), "class": meta.get("class",""),
            "quote": quote, "author": name, "topic": topic_title,
            "movie": extra.get(name, {}).get("movie",""), "poster": poster,
            "rating": extra.get(name, {}).get("rating",""), "line": extra.get(name, {}).get("line",""),
        }
        out = f"金句_{name}.png"
        make_golden_card(gmeta, out, base_dir=input_dir)
        golden_done += 1

    if golden_done > 1:
        print(f"[3/5] 金句海报 → {golden_dir}/ ({golden_done}人)")
    elif golden_done == 1:
        print(f"[3/5] 金句海报 → {out}")
    else:
        print(f"[3/5] 金句海报 → 无（未填写推荐信息）")

    # --- 4. 课后反馈 ---
    import os as _os
    ai_key = _os.environ.get("DEEPSEEK_API_KEY", "")
    from generate_feedback_ai import generate_feedback_ai
    fb_done = False
    if ai_key and feedback_styles:
        style_names = {"xinxin": "欣欣版", "biscuit": "饼干版", "fusion": "融合版"}
        try:
            generate_feedback_ai(meta, topics, cls, input_path=input_path, api_key=ai_key, styles=feedback_styles, memo_data=memo_data)
            fb_done = True
            print(f"[4/5] AI 课后反馈 → {', '.join(style_names.get(s,s) for s in feedback_styles)}")
        except Exception as e:
            print(f"  AI 反馈异常: {e}")
    if not fb_done:
        from generate_feedback import generate_feedback as gen_fb
        fb_out = f"课后反馈_{cls}.txt" if cls else "课后反馈.txt"
        gen_fb(meta, topics, fb_out, input_path=input_path)
        print(f"[4/5] 课后反馈 → {fb_out}")

    # --- 5. 课堂实录文字版 ---
    txt_out = f"课堂实录_{cls}.txt" if cls else "课堂实录.txt"
    with open(txt_out, 'w', encoding='utf-8') as f:
        f.write(title + "\n")
        if cls: f.write("班级: " + cls + "\n")
        if meta.get("date"): f.write("日期: " + meta["date"] + "\n")
        f.write("=" * 50 + "\n\n")
        for ti, (topic_title, speeches) in enumerate(topics):
            if ti > 0:
                f.write("\n" + "=" * 50 + "\n\n")
            f.write(topic_title + "\n")
            f.write("-" * 30 + "\n")
            for name, content in speeches:
                f.write(name + ": " + content + "\n")
    print(f"[5/5] 课堂实录 → {txt_out}")

def _load_logo(bd, h=30):
    lp = os.path.join(bd, "logo.png")
    if not os.path.exists(lp):
        lp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo.png")
    if not os.path.exists(lp):
        lp = os.path.expanduser("~/Library/Mobile Documents/com~apple~CloudDocs/追光π课后素材生成系统/logo.png")
    if os.path.exists(lp):
        try:
            logo = Image.open(lp).convert("RGBA")
            r = h / logo.height
            return logo.resize((int(logo.width*r), h), Image.LANCZOS)
        except: pass
    return None

def _load_slogan(bd):
    sp = os.path.join(bd, "slogan单人.png")
    if not os.path.exists(sp):
        sp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "slogan单人.png")
    if os.path.exists(sp):
        try:
            s = Image.open(sp).convert("RGBA")
            if s.width > 700:
                s = s.resize((700, int(s.height*700/s.width)), Image.LANCZOS)
            return s
        except: pass
    return None

# ---- 复用单人卡片生成（从 generate_class_image 提取） ----
def _gen_student_cards(meta, topics, output_dir, highlights, base_dir=None):
    bd = base_dir or os.path.dirname(os.path.abspath(output_dir)) if output_dir else "."
    from PIL import Image, ImageDraw, ImageFont
    FONT_PATH = os.path.expanduser("~/Library/Fonts/荆南麦圆体.ttf")
    if not os.path.exists(FONT_PATH):
        FONT_PATH = "/System/Library/Fonts/Hiragino Sans GB.ttc"

    student_data = defaultdict(list)
    for topic_title, speeches in topics:
        for name, content in speeches:
            student_data[name].append((topic_title, content))

    all_sents = defaultdict(list)
    from generate_class_image import score_sentence, split_sentences as sp2
    for name, speeches in student_data.items():
        for topic, content in speeches:
            for sent_text, _, _ in sp2(content):
                all_sents[name].append(score_sentence(sent_text, name, {}))

    _dummy_img = Image.new("RGB", (100,100))
    _dummy = ImageDraw.Draw(_dummy_img)

    for student_name, speeches in student_data.items():
        total_speeches = len(speeches)
        topic_variety = len(set(t for t,_ in speeches))
        hl_list = highlights.get(student_name, [])
        sent_scores = all_sents.get(student_name, [0])
        avg_quality = sum(sent_scores)/len(sent_scores) if sent_scores else 0

        score = 3.0
        if total_speeches >= 8: score += 0.8
        elif total_speeches >= 5: score += 0.5
        elif total_speeches >= 3: score += 0.3
        if avg_quality > 4: score += 0.7
        elif avg_quality > 2: score += 0.4
        elif avg_quality > 1: score += 0.2
        if topic_variety >= 7: score += 0.5
        elif topic_variety >= 4: score += 0.3
        score = min(5.0, round(score*2)/2)

        # Comment
        parts = []
        if total_speeches >= 8: parts.append("发言积极")
        elif total_speeches >= 5: parts.append("参与度高")
        else: parts.append("可以再多说说哦")
        if avg_quality >= 4: parts.append("金句频出")
        elif avg_quality >= 3: parts.append("表达有亮点")
        elif avg_quality >= 2: parts.append("有自己的思考")
        else: parts.append("试试多举自己的例子")
        if topic_variety >= 7: parts.append("每个话题都在线")
        elif topic_variety >= 4: parts.append("话题参与面广")
        else: parts.append("下次可以多聊几个话题")

        raw_sents = []
        for topic, content in speeches:
            raw_sents.extend(t for t,_,_ in sp2(content))
        has_rebuttal = any(s >= 6 for s in sent_scores)
        has_personal = any("如果是我" in s or "我妈" in s or "我之前" in s or "我成为" in s for s in raw_sents)
        extras = []
        if has_rebuttal: extras.append("敢质疑")
        if has_personal: extras.append("会联系生活")
        if extras: comment = "、".join(parts[:2]) + "，" + "、".join(extras) + "，超棒！"
        else: comment = "、".join(parts) + "，继续保持~"
        if score >= 5: comment += " 🌟"

        # 按原始话题顺序展示，上限5
        show_items = speeches[:5]

        name_font = ImageFont.truetype(FONT_PATH, 36)
        topic_font = ImageFont.truetype(FONT_PATH, 20)
        text_font = ImageFont.truetype(FONT_PATH, 22)
        score_font = ImageFont.truetype(FONT_PATH, 64)
        comment_font = ImageFont.truetype(FONT_PATH, 24)
        note_font = ImageFont.truetype(FONT_PATH, 16)

        card_w = 800
        logo = _load_logo(bd, h=56)
        slogan = _load_slogan(bd)
        # 先估算高度，多给一些余量，最后裁剪
        max_w = card_w - 100
        est_h = 300
        for _, content in show_items:
            est_h += 26 + len(_wrap2(_dummy, content, text_font, max_w))*28 + 16
        est_h += 200
        if slogan: est_h += slogan.height + 10

        img = Image.new("RGB", (card_w, est_h), (253,251,247))
        draw = ImageDraw.Draw(img)

        y = 30
        draw.text((40, y), student_name, fill=(180,70,30), font=name_font)
        y += 50

        for topic, content in show_items:
            short_topic = topic[:32]+"…" if len(topic) > 32 else topic
            draw.text((50, y), short_topic, fill=(120,120,130), font=topic_font)
            y += 26
            for line_text, _, _ in _wrap2(draw, content, text_font, max_w):
                draw.text((60, y), line_text, fill=(40,40,40), font=text_font)
                y += 28
            y += 16

        y += 10
        draw.line([(40, y), (card_w-40, y)], fill=(210,205,200), width=1)
        y += 20

        stxt = "3"
        draw.text((card_w-120, y-10), stxt, fill=(200,80,30), font=score_font)
        stars = "★★★"
        draw.text((card_w-120, y+55), stars, fill=(240,165,40), font=comment_font)
        draw.text((40, y+10), comment, fill=(80,80,85), font=comment_font)
        stats = f"本节课共 {len(topics)} 个小话题 · 参与 {total_speeches} 次发言"
        draw.text((40, y+48), stats, fill=(160,160,165), font=note_font)
        nh = note_font.size + 4
        draw.text((40, y+74), "部分导入/追问话题未单独计入", fill=(180,180,185), font=note_font)

        # y 推进到备注下方
        y = y + 74 + nh + 12

        # Logo 右上 + Slogan 底部居中
        if logo:
            img.paste(logo, (card_w - 24 - logo.width, 8), logo)
        if slogan:
            img.paste(slogan, ((card_w - slogan.width)//2, y), slogan)
            y += slogan.height + 8

        # 裁剪
        img = img.crop((0, 0, card_w, y + 4))

        out = os.path.join(output_dir, f"单人总结_{student_name}.png")
        img.save(out, "PNG", optimize=True)

def _wrap2(draw, text, font, max_w):
    lines, cur = [], ""
    for ch in text:
        t = cur+ch
        w, _ = draw.textbbox((0,0), t, font=font)[2:4]
        if w > max_w and cur:
            if ch in "，。、；：？！》」』）】" and cur:
                lines.append((cur[:-1],0,0)); cur = cur[-1]+ch
            else:
                lines.append((cur,0,0)); cur = ch
        else: cur = t
    if cur: lines.append((cur,0,0))
    return lines


def scan_input_files():
    """扫描可用 txt，返回 [(path, class, title, mtime), ...]"""
    files = []
    for f in sorted(os.listdir(".")):
        if not f.endswith(".txt"): continue
        if any(kw in f.lower() for kw in ["template","golden","test"]): continue
        if f.startswith(".") or "反馈" in f or "课堂实录" in f: continue
        cls, tit = "", ""
        try:
            with open(f, encoding='utf-8') as fh:
                for line in fh:
                    s = line.strip()
                    if s.startswith("@class"): cls = s[7:].strip()
                    elif s.startswith("@title"): tit = s[7:].strip()
                    if cls and tit: break
        except: pass
        files.append((f, cls, tit, os.path.getmtime(f)))
    return files

if __name__ == "__main__":
    ip = None
    if len(sys.argv) > 1: ip = sys.argv[1]
    else:
        files = scan_input_files()
        if not files: print("没有可用的 txt 文件。"); sys.exit(1)
        if len(files) == 1:
            ip = files[0][0]; print(f"唯一可用: {ip}")
        else:
            import datetime
            print("选择文件:")
            for i, (f, cls, tit, mt) in enumerate(files):
                dt = datetime.datetime.fromtimestamp(mt).strftime("%m/%d %H:%M")
                label = f"{cls} | {tit}" if cls and tit else f
                print(f"  [{i+1}] {label}  ({dt})  ← {f}")
            ch = input(f"选 (1-{len(files)}): ").strip()
            try:
                idx = int(ch)-1
                if 0 <= idx < len(files): ip = files[idx][0]
            except: pass
    if not ip: print("Usage: python3 generate_all.py your_file.txt"); sys.exit(1)
    generate_all(ip)
