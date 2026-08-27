"""
课堂讨论长图生成工具
用法：python3 generate_class_image.py input.txt
      输出同目录同名 .png，input.txt 模板见 input_template.txt
"""
import sys
sys.dont_write_bytecode = True
from PIL import Image, ImageDraw, ImageFont
import random, math, re, os
from collections import defaultdict

# ============================================================
# 默认配置
# ============================================================
WIDTH = 1200
PADDING_X = 60
TOP_PADDING = 50
BOTTOM_PADDING = 0
LINE_SPACING = 6
SPEECH_GAP = 14
TOPIC_GAP = 24
SECTION_PAD = 18
CONTENT_INDENT = 20
HIGHLIGHTS_PER_STUDENT = 3      # 长图用的高亮数
CARD_HIGHLIGHTS_PER_STUDENT = 5  # 单人卡片用的高亮数
LOGO_MAX_HEIGHT = 70

# 字体：优先读 setup.sh 生成的配置，其次本地荆南麦圆体，再次系统默认
_FONT_CFG = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".font_path")
if os.path.exists(_FONT_CFG):
    with open(_FONT_CFG) as _f:
        DEFAULT_FONT_PATH = _f.read().strip()
else:
    DEFAULT_FONT_PATH = os.path.expanduser("~/Library/Fonts/荆南麦圆体.ttf")
LOGO_PATH = "logo.png"        # 同目录下 logo 文件
SLOGAN_PATH = "slogan.png"    # 同目录下 slogan 图片（可选）
TOPIC_FONT_SIZE = 30
NAME_FONT_SIZE = 26
TEXT_FONT_SIZE = 24
TITLE_FONT_SIZE = 40
SUB_FONT_SIZE = 22
SLOGAN_FONT_SIZE = 20

# 默认配色（无 unit 时使用）
_BG = (253, 251, 247)
_TOPIC = (25, 55, 109)
_NAME = (180, 70, 30)
_TEXT = (40, 40, 40)
_HEADER = (40, 40, 45)
_SUB = (120, 120, 130)
_HL_BG = (255, 240, 200)
_HL_BAR = (240, 165, 40)
_HL_TEXT = (150, 55, 25)
_ACCENT = (75, 105, 165)
_ICON = (210, 180, 140)

def make_theme(unit_str):
    """从单元编号(如 2604)生成整套配色，同单元永远一致，换月自动变"""
    import re, colorsys
    m = re.search(r'(\d{2})(\d{2})', unit_str)
    if not m:
        return None
    yy, mm = int(m.group(1)), int(m.group(2))
    seed = (2000 + yy) * 12 + mm  # 2026*12+4 = 24316
    rng = random.Random(seed)

    def vary(base, dh=0.05, ds=0.1, dv=0.05):
        """微调 HSL"""
        r, g, b = base[0]/255, base[1]/255, base[2]/255
        h, l, s = colorsys.rgb_to_hls(r, g, b)
        h = (h + rng.uniform(-dh, dh)) % 1.0
        s = max(0, min(1, s + rng.uniform(-ds, ds)))
        l = max(0.05, min(0.95, l + rng.uniform(-dv, dv)))
        r, g, b = colorsys.hls_to_rgb(h, l, s)
        return (int(r*255), int(g*255), int(b*255))

    def warm_light():
        return (rng.randint(248, 255), rng.randint(245, 253), rng.randint(240, 250))
    def warm_mid():
        return (rng.randint(170, 220), rng.randint(140, 200), rng.randint(100, 170))

    # 用不同基色 + 微调生成每项
    bases = [
        (25, 55, 109),    # topic
        (180, 70, 30),     # name
        (40, 40, 40),      # text
        (40, 40, 45),      # header
        (120, 120, 130),   # sub
        (255, 240, 200),   # hl_bg
        (240, 165, 40),    # hl_bar
        (150, 55, 25),     # hl_text
        (75, 105, 165),    # accent
    ]
    varied = [vary(b, 0.08, 0.25, 0.08) for b in bases]

    # 分区底色：9 个暖调浅色
    tints = []
    for _ in range(9):
        r = rng.randint(246, 255)
        g = rng.randint(244, 253)
        b = rng.randint(238, 250)
        tints.append((r, g, b))

    # 图标色
    icon_color = (rng.randint(160, 220), rng.randint(130, 200), rng.randint(100, 180))

    # 背景色
    bg = (rng.randint(250, 255), rng.randint(248, 254), rng.randint(244, 250))

    return {
        "bg": bg,
        "topic": varied[0], "name": varied[1], "text": varied[2],
        "header": varied[3], "sub": varied[4],
        "hl_bg": varied[5], "hl_bar": varied[6], "hl_text": varied[7],
        "accent": varied[8], "icon": icon_color,
        "tints": tints,
        "unit": unit_str, "seed": seed,
    }

# ============================================================
# TXT 解析
# ============================================================
# @title    课节标题
# @unit     单元标题
# @date     2026-05-12
# @logo     logo.png（可选，同目录下）
# @slogan   让每个孩子都被看见（可选）
# @font     /path/to/font.ttc（可选，覆盖默认字体）
#
# 然后每个话题一行标题，下面跟 name：content ...

def safe_filename(s):
    """剔除文件名不安全字符（仅 ASCII 特殊字符，保留中文标点和空格）"""
    for ch in r'/:*?"<>|\\':
        s = s.replace(ch, "")
    return s.strip()

def clean_content(text):
    """清洗发言内容：去掉中文间多余空格、标点旁空格"""
    text = re.sub(r'([一-鿿]) ([一-鿿])', r'\1\2', text)
    text = re.sub(r'([，。、；：？！》）】』」]) +(?=[一-鿿])', r'\1', text)
    text = re.sub(r' +([，。、；：？！》）】』」])', r'\1', text)
    text = re.sub(r'([\d/+]) +(?=[一-鿿])', r'\1', text)
    text = re.sub(r'  +', ' ', text)
    return text

def parse_input_txt(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        raw = f.read()

    meta = {"title": "", "unit": "", "date": "", "class": ""}
    speech_pattern = re.compile(r'^([^\s：:]+)[：:](.*)$')

    lines = raw.split('\n')

    # ---- 提取 @meta ----
    body_start = 0
    _skip_cont = False
    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith('#'):
            continue
        if not s:
            _skip_cont = False
            continue
        if s.startswith('@'):
            parts = s[1:].split(None, 1)
            key = parts[0].lower()
            val = parts[1] if len(parts) > 1 else ""
            if key in meta:
                meta[key] = val
            _skip_cont = True  # @行后的续行也要跳过
            continue
        if _skip_cont:
            continue  # @quote等字段的续行
        body_start = i
        break

    # ---- 预收集学生名（短名>=1次，中名>=2次，长名排除）----
    _name_counts = {}
    for _j in range(body_start, len(lines)):
        _sm = speech_pattern.match(lines[_j].strip())
        if _sm:
            _n = _sm.group(1)
            _name_counts[_n] = _name_counts.get(_n, 0) + 1
    known_names = set()
    for n, c in _name_counts.items():
        if len(n) <= 3 and c >= 1: known_names.add(n)
        elif len(n) <= 6 and c >= 2: known_names.add(n)
        elif c >= 4: known_names.add(n)

    # ---- 判断是否为同事格式：话题间和学生间都是1空行 ----
    # 检查 transcript 中空行后跟的是否都是 name：行（同事格式）还是混合（你的格式）
    _blank_followed_by_name = 0
    _blank_followed_by_other = 0
    _in_ts = False
    for _i in range(body_start, len(lines)):
        _s = lines[_i].strip()
        if '课堂发言' in _s or '课堂记录' in _s or '以上是' in _s:
            _in_ts = True; continue
        if not _in_ts: continue
        if not _s:
            # 找下一个非空行
            for _j in range(_i+1, len(lines)):
                _ns = lines[_j].strip()
                if not _ns: continue
                if speech_pattern.match(_ns): _blank_followed_by_name += 1
                else: _blank_followed_by_other += 1
                break
    _colleague_mode = (_blank_followed_by_name > _blank_followed_by_other * 2 and _blank_followed_by_name >= 3)

    # ---- 判断格式：收集开头非 name：的连续行作为候选提纲 ----
    # 跳过 @ 行及其续行之间的内容
    outline_candidates = []
    transcript_start = body_start
    _skip_until_blank = False
    for i in range(body_start, len(lines)):
        s = lines[i].strip()
        if not s:
            _skip_until_blank = False
            continue
        if s.startswith("#"):
            continue
        if s.startswith("@"):
            _skip_until_blank = True
            continue
        if _skip_until_blank:
            continue  # @ 行的续行，跳过
        m = speech_pattern.match(s)
        if m and (len(m.group(1)) < 6 or m.group(1) in known_names):
            transcript_start = i
            break
        # 纯图片标记行也算发言（不能当提纲跳过）
        if re.findall(r'\[img:\d+\]', s):
            transcript_start = i
            break
        if '以上是' in s and ('以下' in s or '课堂' in s or '记录' in s or '框架' in s):
            transcript_start = i + 1
            break
        outline_candidates.append(s)

    # 二次过滤：排除名字是话题标题前半截的情况
    _fake2 = set()
    for n in known_names:
        for ol in outline_candidates:
            if ol.startswith(n + '：') or ol.startswith(n + ':'):
                _fake2.add(n)
    known_names -= _fake2

    # 如果有 >= 2 个候选提纲行 → 原始格式
    is_raw = len(outline_candidates) >= 2

    if is_raw:
        outline = outline_candidates

        # 解析原始记录：合并同一人多行，用连续空行(>=2)分隔区块
        blocks = []
        current_block = []
        current_name = None
        current_content = []
        blank_count = 0

        for i in range(transcript_start, len(lines)):
            raw_line = lines[i]
            s = raw_line.strip()

            if not s:
                blank_count += 1
                continue
            if s.startswith(('#', '@')):
                continue  # skip comments and meta tags

            # 同事模式用>=2(学生间隔1行)，你的模式用>=1
            _sep = 2 if _colleague_mode else 1
            if blank_count >= _sep:
                if current_name and current_content:
                    current_block.append((current_name, clean_content(' '.join(current_content))))
                    current_name = None
                    current_content = []
                if current_block:
                    blocks.append(current_block)
                current_block = []

            blank_count = 0

            m = speech_pattern.match(s)
            if m and (len(m.group(1)) < 6 or m.group(1) in known_names):  # 短名或已知学生
                if current_name and current_content:
                    current_block.append((current_name, clean_content(' '.join(current_content))))
                current_name = m.group(1)
                current_content = [m.group(2)]
            else:
                # 非发言行：如果在提纲中 → 新话题（服务器生成的 txt 用）
                if s in outline:
                    if current_name and current_content:
                        current_block.append((current_name, clean_content(' '.join(current_content))))
                        current_name = None
                        current_content = []
                    if current_block:
                        blocks.append(current_block)
                    current_block = []
                elif current_name:
                    current_content.append(s)

        # 最后一个发言 + 最后一个区块
        if current_name and current_content:
            current_block.append((current_name, clean_content(' '.join(current_content))))
        if current_block:
            blocks.append(current_block)

        # 提纲与 blocks 顺次对应
        topics = []
        for ti, title in enumerate(outline):
            if ti < len(blocks):
                topics.append((title, blocks[ti]))
        if len(blocks) > len(outline) and topics:
            for extra in blocks[len(outline):]:
                topics[-1] = (topics[-1][0], topics[-1][1] + extra)

        if not topics:
            raise ValueError(f"未能从 {filepath} 解析出话题和发言，请检查格式。")
        return meta, topics

    # ---- 干净格式：话题标题直接穿插在发言中 ----
    topics = []
    current_topic = None
    current_speeches = []
    prev_blank = True
    in_meta = True

    for line in lines:
        stripped = line.strip()
        if not stripped:
            in_meta = False
            prev_blank = True
            continue
        if stripped.startswith("#"):
            continue  # 注释行，不影响 in_meta 状态

        if in_meta and stripped.startswith("@"):
            continue  # already parsed

        in_meta = False
        if stripped.startswith(("#", "@")):
            continue  # skip comments and @meta
        # 修复 [img： 为 [img:（完整形冒号）
        stripped = re.sub(r'\[img：', '[img:', stripped)
        # 纯图片标记行——合并到上一个发言（或创建新的）
        img_only = re.findall(r'\[img:\d+\]', stripped)
        if img_only and re.fullmatch(r'(\[img:\d+\]\s*)+', stripped):
            if current_speeches:
                name, content = current_speeches[-1]
                current_speeches[-1] = (name, content + ' ' + ' '.join(img_only))
            elif current_topic is not None:
                current_speeches.append(('', ' '.join(img_only)))
            in_meta = False
            continue
        # 空名图片标记行（如 "：[img:0] [img:1]"）
        if img_only and re.fullmatch(r'[：:]?\s*(\[img:\d+\]\s*)+', stripped):
            if current_speeches:
                name, content = current_speeches[-1]
                current_speeches[-1] = (name, content + ' ' + ' '.join(img_only))
            elif current_topic is not None:
                current_speeches.append(('', ' '.join(img_only)))
            in_meta = False
            continue
        match = speech_pattern.match(stripped)
        if match and (len(match.group(1)) < 6 or match.group(1) in known_names):
            name = match.group(1)
            # 从名字中提取 [img:N] 标记并移到内容前面
            img_tags = re.findall(r'\[img:\d+\]', name)
            name = re.sub(r'\[img:\d+\]\s*', '', name).strip()
            content = clean_content(match.group(2))
            if img_tags:
                content = ' '.join(img_tags) + ' ' + content
            if current_topic is not None:
                current_speeches.append((name, content))
            prev_blank = False
        else:
            # 续行：前一行为非空且不是空行分隔
            if not prev_blank and current_topic is not None and current_speeches:
                name, content = current_speeches[-1]
                current_speeches[-1] = (name, content + '\n' + stripped)
            else:
                if current_topic is not None:
                    topics.append((current_topic, current_speeches))
                current_topic = stripped
                current_speeches = []
            prev_blank = False

    if current_topic is not None:
        topics.append((current_topic, current_speeches))
    if not topics:
        raise ValueError(f"未能从 {filepath} 解析出话题和发言，请检查格式。")

    return meta, topics

# ============================================================
# 自动高亮
# ============================================================
def split_sentences(text):
    sents, cur, start = [], "", 0
    for i, ch in enumerate(text):
        cur += ch
        if ch in "。！？\n" and cur.strip():
            sents.append((cur.strip(), start, i + 1))
            cur, start = "", i + 1
    if cur.strip():
        sents.append((cur.strip(), start, len(text)))
    return sents

def score_sentence(sent, student_name, all_other_texts):
    score = 0
    rebuttal_kw = ["不认同", "我不觉得", "反驳", "不一定", "没道理", "不对",
                   "不是", "不太符合", "做不到", "不太ok", "前后矛盾",
                   "不浪费", "不算浪费", "没有道理"]
    if any(kw in sent for kw in rebuttal_kw):
        score += 3
    if re.search(r"[谁哪什么怎么][^？。]*[？]$", sent):
        score += 3
    if any(kw in sent for kw in ["另一个", "换一个", "相反"]):
        score += 2
    personal_kw = ["我妈", "我爸", "我之前", "我小时候", "我以前", "我自己",
                   "如果是我", "我成为", "我打算", "我站在", "从我", "如果我是"]
    if any(kw in sent for kw in personal_kw):
        score += 3
    summary_kw = ["其实", "就是", "总之", "说到底", "核心", "关键", "最重要", "本质", "重点"]
    if any(kw in sent for kw in summary_kw):
        score += 2
    if len(sent) >= 25:
        score += 1
    logic_kw = ["因为", "所以", "如果", "但是", "然而", "虽然", "因此", "不仅", "而且"]
    logic_count = sum(1 for kw in logic_kw if kw in sent)
    score += min(logic_count, 3)
    vivid_kw = ["发光发热", "延续", "注入", "支柱", "担子", "落寞", "白日梦",
                "三心二意", "知恩图报", "选择的权利", "荒废", "倾倒", "基础", "热爱", "快乐"]
    if any(kw in sent for kw in vivid_kw):
        score += 2
    if len(sent) < 6:
        score -= 3
    if len(sent) > 200:
        score -= 1
    return score

def auto_select_highlights(topics, per_student=None, title=""):
    if per_student is None: per_student = HIGHLIGHTS_PER_STUDENT
    student_sents = defaultdict(list)
    for topic, speeches in topics:
        for name, content in speeches:
            for sent_text, start, end in split_sentences(content):
                if len(sent_text) > 8:
                    student_sents[name].append(sent_text)
    # 尝试 DeepSeek
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if api_key and title:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
            # 话题列表
            topic_names = [t for t, _ in topics]
            topic_text = "本节课讨论的话题：\n" + "\n".join(f"· {t}" for t in topic_names[:10]) + "\n\n"
            result = {}
            for name, sents in student_sents.items():
                sp_count = sum(1 for t, ss in topics for n, c in ss if n == name)
                tp_count = len(set(t for t, ss in topics for n, c in ss if n == name))
                n_hl = per_student if (sp_count >= 5 and tp_count >= 5) else max(2, per_student - 1)
                # 长图: per_student=HIGHLIGHTS_PER(3), so active=3, others=2
                # 随机打乱顺序避免 AI 位置偏见
                idxs = list(range(len(sents)))
                random.shuffle(idxs)
                shuffled = [sents[i] for i in idxs]
                prompt = f"课节标题：{title}\n\n{topic_text}学生：{name}\n\n以下是{name}的发言句子，请按「思辨深度」选出最精彩的 {n_hl} 句。\n"
                prompt += "标准：逻辑严密、观点独立、联系生活、视角独特、总结精辟。\n\n"
                for i, t in enumerate(shuffled, 1):
                    prompt += f"{i}. {t}\n"
                prompt += f"\n请返回选中的句子序号，每行一个数字，共 {n_hl} 个。"
                resp = client.chat.completions.create(
                    model="deepseek-v4-flash",
                    messages=[{"role":"user","content": prompt}],
                    temperature=0.3, max_tokens=1000, stream=False)
                text = resp.choices[0].message.content
                import re
                picks = [int(x) for x in re.findall(r'\d+', text)[:n_hl]]
                top = []
                for shuf_idx in picks:
                    if 1 <= shuf_idx <= len(shuffled):
                        orig_idx = idxs[shuf_idx - 1]
                        orig_sent = sents[orig_idx]
                        if orig_sent not in top:
                            top.append(orig_sent)
                if len(top) < n_hl:
                    # 不够的用关键词打分补
                    remaining = [s for s in sents if s not in top]
                    scored = [(score_sentence(s, name, {}), s) for s in remaining]
                    scored.sort(key=lambda x: -x[0])
                    for _, s in scored:
                        if len(top) >= n_hl: break
                        if s not in top: top.append(s)
                result[name] = top[:n_hl]
            return result
        except Exception as e:
            print(f"  DeepSeek highlight error: {e}, fallback to keyword")

    # 回退关键词打分
    student_stats = {}
    all_texts = {}
    for name in student_sents:
        sp_count = sum(1 for t, ss in topics for n, c in ss if n == name)
        tp_count = len(set(t for t, ss in topics for n, c in ss if n == name))
        student_stats[name] = (sp_count, tp_count)
        all_texts[name] = " ".join(student_sents[name])
    result = {}
    for name, sents in student_sents.items():
        sp, tp = student_stats[name]
        n_hl = per_student if (sp >= 5 and tp >= 5) else max(2, per_student - 1)
        other_texts = {n: t for n, t in all_texts.items() if n != name}
        scored = [(score_sentence(txt, name, other_texts), txt) for txt in sents]
        scored.sort(key=lambda x: -x[0])
        seen = set()
        top = []
        for s, txt in scored:
            if txt not in seen:
                seen.add(txt)
                top.append(txt)
            if len(top) >= n_hl: break
        result[name] = top
    return result

# ============================================================
# 渲染引擎
# ============================================================
def measure(draw, text, font):
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]

def wrap_lines(draw, text, font, max_w):
    """自动换行，中文标点不单独出现在行首"""
    result, cur, cur_start = [], "", 0
    for i, ch in enumerate(text):
        test = cur + ch
        w, _ = measure(draw, test, font)
        if w > max_w:
            if cur:
                # 如果下一行首字是标点，把上一行末字移下来
                if ch in "，。、；：？！》」』）】" and cur:
                    result.append((cur[:-1], cur_start, i-1))
                    cur = cur[-1] + ch
                    cur_start = i-1
                else:
                    result.append((cur, cur_start, i))
                    cur, cur_start = ch, i
            else:
                cur, cur_start = ch, i
        else:
            cur = test
    if cur:
        result.append((cur, cur_start, len(text)))
    return result

def render_header(draw, meta, fonts, w, colors):
    """Render header area: logo (right), title + unit + date (left). Returns y offset after header."""
    y = TOP_PADDING
    logo_img = None
    logo_right = 0
    logo_bottom = 0

    # Logo on the right (hardcoded path from config)
    base_dir = os.path.dirname(os.path.abspath(__file__)) if "__file__" in dir() else os.getcwd()
    logo_path = os.path.join(base_dir, LOGO_PATH)
    if os.path.exists(logo_path):
        try:
            logo_img = Image.open(logo_path).convert("RGBA")
            h = min(LOGO_MAX_HEIGHT, logo_img.height)
            ratio = h / logo_img.height
            lw = int(logo_img.width * ratio)
            logo_img = logo_img.resize((lw, h), Image.LANCZOS)
            logo_right = w - PADDING_X
            logo_bottom = y + h
        except Exception as e:
            print(f"Warning: failed to load logo: {e}")
            logo_img = None

    # Title on the left
    title = meta.get("title", "")
    unit = meta.get("unit", "")
    date = meta.get("date", "")

    title_font = fonts["title"]
    sub_font = fonts["sub"]

    title_x = PADDING_X
    max_text_w = w - 2 * PADDING_X - (logo_img.width + 30 if logo_img else 0)

    if title:
        _, th = measure(draw, title, title_font)
        draw.text((title_x, y), title, fill=colors["header"], font=title_font)
        y += th + 6

    if unit:
        _, uh = measure(draw, unit, sub_font)
        draw.text((title_x, y), unit, fill=colors["sub"], font=sub_font)
        y += uh + 4

    if date:
        _, dh = measure(draw, date, sub_font)
        draw.text((title_x, y), date, fill=colors["sub"], font=sub_font)
        y += dh

    # Store logo placement for later pasting on the real image
    if logo_img:
        logo_x = logo_right - logo_img.width
        logo_y = TOP_PADDING
        y = max(y, logo_bottom)
        meta["_logo_surface"] = (logo_img, logo_x, logo_y)

    y += 20  # spacing after header
    # Thin separator line
    draw.line([(PADDING_X, y), (w - PADDING_X, y)], fill=colors["sub"], width=1)
    y += 20

    return y

def render_footer(img, w, img_h):
    """Render footer: slogan image at bottom center."""
    base_dir = os.path.dirname(os.path.abspath(__file__)) if "__file__" in dir() else os.getcwd()
    slogan_path = os.path.join(base_dir, SLOGAN_PATH)
    if not os.path.exists(slogan_path):
        return
    try:
        slogan_img = Image.open(slogan_path).convert("RGBA")
        max_w = w - 2 * PADDING_X
        if slogan_img.width > max_w:
            ratio = max_w / slogan_img.width
            new_h = int(slogan_img.height * ratio)
            slogan_img = slogan_img.resize((max_w, new_h), Image.LANCZOS)
        sw, sh = slogan_img.size
        sx = (w - sw) // 2
        sy = img_h - BOTTOM_PADDING - sh
        img.paste(slogan_img, (sx, sy), slogan_img)
    except Exception as e:
        print(f"Warning: failed to load slogan image: {e}")

def generate_image(meta, topics, output_path="output.png", highlights=None, images_dir=None):
    # 主题
    theme = make_theme(meta.get("unit", ""))
    if theme is None:
        theme = {"bg": _BG, "topic": _TOPIC, "name": _NAME, "text": _TEXT,
                 "header": _HEADER, "sub": _SUB, "hl_bg": _HL_BG, "hl_bar": _HL_BAR,
                 "hl_text": _HL_TEXT, "accent": _ACCENT, "icon": _ICON,
                 "tints": [(255,250,242),(250,251,248),(255,249,244),(248,250,246),
                           (254,249,243),(249,251,247),(255,250,245),(250,250,246),(253,248,244)],
                 "unit": "default", "seed": 0}
    print(f"Theme: unit={theme['unit']} seed={theme.get('seed','-')}")

    font_path = DEFAULT_FONT_PATH
    if not os.path.exists(font_path):
        font_path = "/System/Library/Fonts/Hiragino Sans GB.ttc"
        print(f"Warning: default font not found, falling back to Hiragino Sans GB")
    if highlights is None:
        highlights = auto_select_highlights(topics, per_student=HIGHLIGHTS_PER_STUDENT, title=meta.get("title",""))
    print("Highlights:")
    for name, hls in highlights.items():
        for i, h in enumerate(hls):
            print(f"  {name}[{i}]: {h[:70]}{'...' if len(h)>70 else ''}")

    fonts = {
        "title": ImageFont.truetype(font_path, TITLE_FONT_SIZE),
        "sub": ImageFont.truetype(font_path, SUB_FONT_SIZE),
        "topic": ImageFont.truetype(font_path, TOPIC_FONT_SIZE),
        "name": ImageFont.truetype(font_path, NAME_FONT_SIZE),
        "text": ImageFont.truetype(font_path, TEXT_FONT_SIZE),
        "slogan": ImageFont.truetype(font_path, SLOGAN_FONT_SIZE),
    }
    topic_font = fonts["topic"]
    name_font = fonts["name"]
    text_font = fonts["text"]
    MAX_TEXT_WIDTH = WIDTH - 2 * PADDING_X - CONTENT_INDENT
    TOPIC_MAX_WIDTH = WIDTH - 2 * PADDING_X

    _dummy = Image.new("RGB", (100, 100))
    _draw = ImageDraw.Draw(_dummy)
    used_highlights = set()

    # --- 计算内容高度 ---
    # More precise header calc
    _header_h = 0
    _y_tmp = TOP_PADDING
    if meta.get("title"):
        _, th = measure(_draw, meta["title"], fonts["title"])
        _y_tmp += th + 6
    if meta.get("unit"):
        _, uh = measure(_draw, meta["unit"], fonts["sub"])
        _y_tmp += uh + 4
    if meta.get("date"):
        _, dh = measure(_draw, meta["date"], fonts["sub"])
        _y_tmp += dh
    _y_tmp += 20 + 1 + 20  # spacing + separator + spacing
    HEADER_H = _y_tmp

    # Footer height (slogan image)
    FOOTER_H = 0
    base_dir = os.path.dirname(os.path.abspath(__file__)) if "__file__" in dir() else os.getcwd()
    slogan_path = os.path.join(base_dir, SLOGAN_PATH)
    if os.path.exists(slogan_path):
        try:
            simg = Image.open(slogan_path)
            max_w = WIDTH - 2 * PADDING_X
            if simg.width > max_w:
                ratio = max_w / simg.width
                FOOTER_H = BOTTOM_PADDING + int(simg.height * ratio) + 0
            else:
                FOOTER_H = BOTTOM_PADDING + simg.height + 0
        except:
            pass

    # 预计算图片高度
    import re as _re2
    def _calc_img_height(content, ti):
        h = 0
        if images_dir and os.path.isdir(images_dir):
            for m in _re2.finditer(r'\[img:(\d+)\]', content):
                idx = int(m.group(1))
                for ext in ['.png', '.jpg', '.jpeg']:
                    fpath = os.path.join(images_dir, f"topic{ti}_{idx}{ext}")
                    if os.path.exists(fpath):
                        try:
                            pi = Image.open(fpath)
                            max_w = MAX_TEXT_WIDTH
                            r = min(1, max_w / pi.width) if pi.width > max_w else 1
                            h += int(pi.height * r) + 6
                        except: pass
                        break
        return h

    section_ranges = []
    y = HEADER_H
    for ti, (topic, speeches) in enumerate(topics):
        sec_start = y
        for tl_text, _, _ in wrap_lines(_draw, topic, topic_font, TOPIC_MAX_WIDTH):
            _, th = measure(_draw, tl_text, topic_font)
            y += th + 6
        y += 8
        for name, content in speeches:
            _, nh = measure(_draw, name, name_font)
            y += nh + 4
            clean = _re2.sub(r'\[img:\d+\]', '', content).strip()
            for line_text, _, _ in wrap_lines(_draw, clean, text_font, MAX_TEXT_WIDTH):
                _, lh = measure(_draw, line_text, text_font)
                y += lh + LINE_SPACING
            y += _calc_img_height(content, ti)
            y += SPEECH_GAP
        sec_end = y + 0
        section_ranges.append((sec_start - SECTION_PAD, sec_end))
        if ti < len(topics) - 1:
            y += TOPIC_GAP
    total_h = y + FOOTER_H

    # --- 重建图标函数(使用主题色) ---
    t_icon = theme["icon"]
    t_accent = theme["accent"]
    def _icon_color(base):
        return tuple(max(0, min(255, c + random.Random(theme['seed']).randint(-20, 20))) for c in base)

    # 生成图标函数（内联，使用主题色）
    # Scale factors normalized so all icons have roughly the same visual footprint
    def _mk_icon(idx):
        c1 = _icon_color(t_icon)
        c2 = _icon_color(t_accent)
        if idx == 0:  # success (star)
            return lambda d, cx, cy, s: [
                d.polygon([
                    (cx+math.cos(math.radians(a))*s*0.6, cy+math.sin(math.radians(a))*s*0.6-r),
                    (cx+math.cos(math.radians(a))*s*0.6+r, cy+math.sin(math.radians(a))*s*0.6),
                    (cx+math.cos(math.radians(a))*s*0.6, cy+math.sin(math.radians(a))*s*0.6+r),
                    (cx+math.cos(math.radians(a))*s*0.6-r, cy+math.sin(math.radians(a))*s*0.6),
                ], fill=c1) for a in [0,72,144,216,288] for r in [s*0.16]
            ][0]
        elif idx == 1:  # standard (waves)
            return lambda d, cx, cy, s: (
                d.line([(cx-s*0.6,cy),(cx+s*0.6,cy)], fill=c2, width=2),
                [d.line([(cx+i*s*0.24,cy-(s*0.2 if i==0 else s*0.12)),
                         (cx+i*s*0.24,cy+(s*0.2 if i==0 else s*0.12))], fill=c2, width=1) for i in range(-2,3)]
            )
        elif idx == 2:  # choice (venn circles)
            c3 = _icon_color((220,120,120)); c4 = _icon_color((120,160,220)); c5 = _icon_color((120,200,140))
            return lambda d, cx, cy, s: (
                d.ellipse([cx-s*0.55,cy-s*0.45,cx+s*0.55,cy+s*0.55], outline=c1, width=2),
                [d.ellipse([cx+dx*s-r2,cy+dy*s-r2,cx+dx*s+r2,cy+dy*s+r2], fill=cl)
                 for dx,dy,cl in [(-0.22,-0.17,c3),(0.22,-0.12,c4),(0,0.22,c5)] for r2 in [s*0.12]]
            )
        elif idx == 3:  # regret (face)
            return lambda d, cx, cy, s: (
                d.ellipse([cx-s*0.55,cy-s*0.55,cx+s*0.55,cy+s*0.55], outline=c2, width=2),
                [d.ellipse([cx+dx*s-r2,cy+dy*s-r2,cx+dx*s+r2,cy+dy*s+r2], fill=c2) for dx,dy in [(-0.2,0),(0,0),(0.2,0)] for r2 in [s*0.08]]
            )
        elif idx == 4:  # chef/book
            return lambda d, cx, cy, s: (
                d.rectangle([cx-s*0.5,cy-s*0.4,cx+s*0.5,cy+s*0.4], outline=c1, width=2),
                d.line([(cx,cy-s*0.4),(cx,cy+s*0.4)], fill=c1, width=1)
            )
        elif idx == 5:  # society (buildings)
            return lambda d, cx, cy, s: [
                d.rectangle([x-s*0.14,cy-h*s,x+s*0.14,cy], outline=c2, width=2)
                for dx,h in [(-0.28,0.55),(0,0.75),(0.28,0.45)] for x in [cx+dx*s]
            ]
        elif idx == 6:  # advice (speech bubble)
            return lambda d, cx, cy, s: (
                d.rounded_rectangle([cx-s*0.55,cy-s*0.45,cx+s*0.55,cy+s*0.35], radius=s*0.14, outline=c2, width=2),
                d.polygon([(cx-s*0.12,cy+s*0.35),(cx-s*0.22,cy+s*0.65),(cx+s*0.12,cy+s*0.25)], fill=c2)
            )
        elif idx == 7:  # dance (spiral)
            return lambda d, cx, cy, s: [
                d.line([pts[i],pts[i+1]], fill=(c1[0],c1[1]-20,c1[2]), width=2)
                for pts in [[(cx+math.cos(t/math.pi*1.5)*s*0.55*(1-t/(math.pi*1.5)*0.6),
                              cy+math.sin(t*0.8)*s*0.55) for t in [i/19*math.pi*1.5 for i in range(20)]]]
                for i in range(19)
            ]
        elif idx == 8:  # balance (scales)
            return lambda d, cx, cy, s: (
                d.line([(cx-s*0.55,cy+s*0.35),(cx+s*0.55,cy+s*0.35)], fill=c2, width=2),
                d.line([(cx,cy-s*0.25),(cx,cy+s*0.35)], fill=c2, width=1),
                [d.arc([cx+dx*s-s*0.18,cy+s*0.15,cx+dx*s+s*0.18,cy+s*0.45],0,180,fill=c2,width=1) for dx in [-0.45,0.45]]
            )
        return lambda d, cx, cy, s: None

    ICON_FUNCS = [_mk_icon(i) for i in range(9)]

    # --- 绘图 ---
    img = Image.new("RGB", (WIDTH, total_h), theme["bg"])
    draw = ImageDraw.Draw(img)

    # Header
    render_header(draw, meta, fonts, WIDTH, theme)

    # Paste logo onto actual image
    if "_logo_surface" in meta:
        logo_img, lx, ly = meta.pop("_logo_surface")
        img.paste(logo_img, (lx, ly), logo_img)

    # Section backgrounds + icons
    for ti, (y0, y1) in enumerate(section_ranges):
        tint = theme["tints"][ti % len(theme["tints"])]
        ol = (max(0,tint[0]-25), max(0,tint[1]-28), max(0,tint[2]-30))
        draw.rounded_rectangle([20, y0, WIDTH - 20, y1], radius=18, fill=tint, outline=ol, width=1)

    # Subtle dots
    random.seed(123)
    for _ in range(60):
        cx = random.randint(30, WIDTH - 30)
        cy = random.randint(30, total_h - 30)
        r = random.uniform(1.0, 2.5)
        c = random.randint(180, 210)
        draw.ellipse([cx-r, cy-r, cx+r, cy+r], fill=(c, c-5, c-15))

    # Left accent
    draw.rectangle([0, 0, 6, total_h], fill=theme["accent"])

    # --- 话题文本 ---
    y = HEADER_H
    for ti, (topic, speeches) in enumerate(topics):
        ICON_FUNCS[ti % len(ICON_FUNCS)](draw, PADDING_X - 33, y + 18, 35)
        topic_lines = wrap_lines(draw, topic, topic_font, TOPIC_MAX_WIDTH)
        for tl_text, _, _ in topic_lines:
            _, th = measure(draw, tl_text, topic_font)
            draw.text((PADDING_X, y), tl_text, fill=theme["topic"], font=topic_font)
            y += th + 6
        y += 8

        for name, content in speeches:
            # 提取并移除 [img:n] 标记
            img_markers = []
            import re as _re
            def _strip_imgs(m):
                img_markers.append(int(m.group(1)))
                return ""
            clean_content = _re.sub(r'\[img:(\d+)\]', _strip_imgs, content).strip()
            # 清除残留的裸 [N] 或 [[ 或 ]]
            clean_content = _re.sub(r'\[\d*\]', '', clean_content)

            draw.text((PADDING_X, y), name, fill=theme["name"], font=name_font)
            _, nh = measure(draw, name, name_font)
            y += nh + 4

            hl_list = highlights.get(name, [])
            active_hls = []
            for h in hl_list:
                if (name, h) not in used_highlights:
                    idx = clean_content.find(h)
                    if idx < 0 and '\n' in h:
                        idx = clean_content.find(h.replace('\n', ' '))
                        if idx >= 0: h = h.replace('\n', ' ')
                    if idx < 0:
                        idx = clean_content.find(' '.join(h.split()))
                        if idx >= 0: h = ' '.join(h.split())
                    if idx >= 0:
                        active_hls.append((idx, idx + len(h), h))

            lines = wrap_lines(draw, clean_content, text_font, MAX_TEXT_WIDTH)

            for line_text, c_start, c_end in lines:
                lw, lh = measure(draw, line_text, text_font)
                x = PADDING_X + CONTENT_INDENT

                overlaps = []
                for hl_start, hl_end, hl_str in active_hls:
                    if hl_end > c_start and hl_start < c_end:
                        seg_s = max(hl_start, c_start)
                        seg_e = min(hl_end, c_end)
                        overlaps.append((seg_s, seg_e, hl_str, hl_end))

                if not overlaps:
                    draw.text((x, y), line_text, fill=theme["text"], font=text_font)
                else:
                    overlaps.sort(key=lambda o: o[0])
                    pos = 0
                    for seg_s, seg_e, hl_str, hl_end in overlaps:
                        seg_start_in_line = seg_s - c_start
                        seg_end_in_line = seg_e - c_start
                        # skip highlights already fully covered by a previous one
                        if seg_end_in_line <= pos:
                            if seg_e >= hl_end:
                                used_highlights.add((name, hl_str))
                            continue
                        if seg_start_in_line < pos:
                            seg_start_in_line = pos
                        if seg_start_in_line > pos:
                            before = line_text[pos:seg_start_in_line]
                            bw, _ = measure(draw, before, text_font)
                            draw.text((x, y), before, fill=theme["text"], font=text_font)
                            x += bw
                        hl_part = line_text[seg_start_in_line:seg_end_in_line]
                        hlw, _ = measure(draw, hl_part, text_font)
                        pad = 3
                        draw.rectangle([x, y - pad, x + hlw, y + lh + pad], fill=theme["hl_bg"])
                        draw.rectangle([x, y - pad, x + 4, y + lh + pad], fill=theme["hl_bar"])
                        draw.text((x, y), hl_part, fill=theme["hl_text"], font=text_font)
                        x += hlw
                        pos = seg_end_in_line
                        if seg_e >= hl_end:
                            used_highlights.add((name, hl_str))
                    if pos < len(line_text):
                        draw.text((x, y), line_text[pos:], fill=theme["text"], font=text_font)

                y += lh + LINE_SPACING
            # 渲染图片
            if img_markers and images_dir and os.path.isdir(images_dir):
                print(f"  Embedding images for topic {ti}: markers={img_markers}, dir={images_dir}")
                for img_idx in img_markers:
                    for ext in ['.png', '.jpg', '.jpeg']:
                        fname = f"topic{ti}_{img_idx}{ext}"
                        fpath = os.path.join(images_dir, fname)
                        if os.path.exists(fpath):
                            try:
                                pil_img = Image.open(fpath).convert("RGBA")
                                max_w = MAX_TEXT_WIDTH
                                if pil_img.width > max_w:
                                    ratio = max_w / pil_img.width
                                    pil_img = pil_img.resize((max_w, int(pil_img.height * ratio)), Image.LANCZOS)
                                iw, ih = pil_img.size
                                img.paste(pil_img, (PADDING_X + CONTENT_INDENT, int(y)), pil_img)
                                y += ih + 6
                            except: pass
                            break
            y += SPEECH_GAP
        if ti < len(topics) - 1:
            y += TOPIC_GAP

    # Footer slogan image
    render_footer(img, WIDTH, total_h)

    img = img.crop((0, 0, WIDTH, total_h))
    img.save(output_path, "PNG", optimize=True)
    return img.size, used_highlights, highlights

# ============================================================
# 单人卡片生成
# ============================================================
def generate_student_cards(meta, topics, output_dir, highlights=None):
    """为每个学生生成独立卡片 PNG"""
    from collections import defaultdict

    student_data = defaultdict(list)
    for topic_title, speeches in topics:
        for name, content in speeches:
            student_data[name].append((topic_title, content))

    # 计算每句质量分（用于打分区分）
    all_sents = defaultdict(list)
    for name, speeches in student_data.items():
        for topic, content in speeches:
            for sent_text, _, _ in split_sentences(content):
                s = score_sentence(sent_text, name, {})
                all_sents[name].append(s)

    _dummy_img = Image.new("RGB", (100, 100))
    _dummy = ImageDraw.Draw(_dummy_img)

    font_path = DEFAULT_FONT_PATH
    if not os.path.exists(font_path):
        font_path = "/System/Library/Fonts/Hiragino Sans GB.ttc"

    name_font = ImageFont.truetype(font_path, 36)
    topic_font = ImageFont.truetype(font_path, 20)
    text_font = ImageFont.truetype(font_path, 22)
    score_font = ImageFont.truetype(font_path, 64)
    comment_font = ImageFont.truetype(font_path, 24)

    for student_name, speeches in student_data.items():
        total_speeches = len(speeches)
        topic_variety = len(set(t for t, _ in speeches))
        hl_list = highlights.get(student_name, []) if highlights else []

        # 质量分: 所有句子的平均分
        sent_scores = all_sents.get(student_name, [0])
        avg_quality = sum(sent_scores) / len(sent_scores) if sent_scores else 0

        # 打分: 数量 + 质量
        score = 3.0
        if total_speeches >= 8:
            score += 0.8
        elif total_speeches >= 5:
            score += 0.5
        elif total_speeches >= 3:
            score += 0.3
        if avg_quality > 4:
            score += 0.7
        elif avg_quality > 2:
            score += 0.4
        elif avg_quality > 1:
            score += 0.2
        if topic_variety >= 7:
            score += 0.5
        elif topic_variety >= 4:
            score += 0.3
        score = min(5.0, score)
        score = round(score * 2) / 2

        # 简评（根据实际情况组合）
        parts = []
        if total_speeches >= 8:
            parts.append("发言积极")
        elif total_speeches >= 5:
            parts.append("参与度高")
        else:
            parts.append("可以再多说说哦")

        if avg_quality >= 4:
            parts.append("金句频出")
        elif avg_quality >= 3:
            parts.append("表达有亮点")
        elif avg_quality >= 2:
            parts.append("有自己的思考")
        else:
            parts.append("试试多举自己的例子")

        if topic_variety >= 7:
            parts.append("每个话题都在线")
        elif topic_variety >= 4:
            parts.append("话题参与面广")
        else:
            parts.append("下次可以多聊几个话题")

        # 检查是否有反驳/修辞问句/个人例子
        raw_sents = []
        for topic, content in speeches:
            raw_sents.extend(t for t, _, _ in split_sentences(content))

        has_rebuttal = any(s >= 6 for s in sent_scores)
        has_personal = any("如果是我" in s or "我妈" in s or "我之前" in s or "我成为" in s for s in raw_sents)
        has_rhetorical = any("？" in s and ("谁" in s or "怎么" in s or "为什么" in s) for s in raw_sents)

        extras = []
        if has_rebuttal:
            extras.append("敢质疑")
        if has_personal:
            extras.append("会联系生活")
        if has_rhetorical:
            extras.append("会提问")

        if extras:
            comment = "、".join(parts[:2]) + "，" + "、".join(extras) + "，超棒！"
        else:
            comment = "、".join(parts) + "，继续保持~"

        if score >= 5:
            comment += " 🌟"

        # 卡片: 只展示高亮句 + 统计（太多发言卡片太长）
        # 按原始话题顺序展示，上限5
        show_items = speeches[:5]

        # 预计算卡片高度
        card_w = 800
        y = 30 + 50  # name
        for topic, content in show_items:
            y += 26
            max_w = card_w - 100
            lines = wrap_lines(_dummy, content, text_font, max_w)
            y += len(lines) * 28 + 16
        # 预计算评价行高
        comment_max_w = card_w - 180
        c_lines = wrap_lines(_dummy, comment, comment_font, comment_max_w)
        comment_h = max(26, len(c_lines) * 26)
        y += 10 + 1 + 20 + comment_h + 26 + 22  # separator + score + comment + stats + note
        card_h = y + 40

        img = Image.new("RGB", (card_w, card_h), (253, 251, 247))
        draw = ImageDraw.Draw(img)

        y = 30
        draw.text((40, y), student_name, fill=(180, 70, 30), font=name_font)
        y += 50

        for topic, content in show_items:
            short_topic = topic[:32] + "…" if len(topic) > 32 else topic
            draw.text((50, y), short_topic, fill=(120, 120, 130), font=topic_font)
            y += 26
            # 完整回答，自动换行
            max_w = card_w - 100
            for line_text, _, _ in wrap_lines(draw, content, text_font, max_w):
                draw.text((60, y), line_text, fill=(40, 40, 40), font=text_font)
                y += 28
            y += 16

        y += 10
        draw.line([(40, y), (card_w - 40, y)], fill=(210, 205, 200), width=1)
        y += 20

        # 分数 + 星星（右对齐）
        score_text = f"{score:.1f}" if score != int(score) else f"{int(score)}"
        draw.text((card_w - 120, y - 10), score_text, fill=(200, 80, 30), font=score_font)
        stars = "★" * int(score) + ("☆" if score != int(score) else "")
        draw.text((card_w - 120, y + 55), stars, fill=(240, 165, 40), font=comment_font)

        # 简评（左侧，限制宽度避免和分数重叠，预计算已留空间）
        comment_max_w = card_w - 180
        comment_lines = wrap_lines(_dummy, comment, comment_font, comment_max_w)
        comment_f = comment_font if len(comment_lines) <= 1 else ImageFont.truetype(font_path, 20)
        if len(comment_lines) > 1:
            comment_lines = wrap_lines(_dummy, comment, comment_f, comment_max_w)
        ch = 0
        for cl in comment_lines:
            draw.text((40, y + 10 + ch), cl, fill=(80, 80, 85), font=comment_f)
            ch += 24
        stats = f"本节课共 {len(topics)} 个话题 · 参与 {total_speeches} 次发言"
        note = "部分导入/追问话题未单独填入"
        draw.text((40, y + 48), stats, fill=(160, 160, 165), font=topic_font)
        note_font = ImageFont.truetype(font_path, 16)
        draw.text((40, y + 74), note, fill=(180, 180, 185), font=note_font)

        out_path = os.path.join(output_dir, f"单人总结_{student_name}.png")
        img.save(out_path, "PNG", optimize=True)
        print(f"  {student_name}: {score}分 — {comment}")

# ============================================================
# 入口
# ============================================================
if __name__ == "__main__":
    if len(sys.argv) > 1:
        input_path = sys.argv[1]
    else:
        # 自动找同目录下任意 .txt（跳过模板和输出文件）
        candidates = [f for f in os.listdir(".") if f.endswith(".txt")
                      and "template" not in f.lower()
                      and "test" not in f.lower()
                      and not f.startswith(".")]
        if candidates:
            input_path = candidates[0]
            print(f"Auto-detected: {input_path}")
        else:
            input_path = None

    if input_path:
        meta, topics = parse_input_txt(input_path)
        cls = safe_filename(meta.get("class", ""))
        # 长图：课节名称_分段班级
        t = safe_filename(meta.get("title","").replace("·", "-"))
        output_path = (f"{t}_{cls}.png" if cls else f"{t}.png") if t else "output.png"
    else:
        print("No input file found. Put input_template.txt in the same directory, or run:")
        print("  python3 generate_class_image.py your_file.txt")
        sys.exit(1)
        output_path = "课堂整理_长图.png"

    print(f"Meta: { {k:v for k,v in meta.items() if v and k != '_logo_surface'} }")
    print(f"Topics: {len(topics)}")
    print(f"Speeches: {sum(len(s) for _, s in topics)}")
    size, used, highlights = generate_image(meta, topics, output_path)
    print(f"\nSaved: {output_path}")
    print(f"Size: {size[0]}x{size[1]}")
    print(f"Highlights: {len(used)}/{sum(len(v) for v in highlights.values())}")

    # ---- 生成单人卡片（用更多高亮数） ----
    card_highlights = auto_select_highlights(topics, per_student=CARD_HIGHLIGHTS_PER_STUDENT, title=meta.get("title",""))
    base_dir = os.path.dirname(os.path.abspath(input_path))
    generate_student_cards(meta, topics, base_dir, card_highlights)
    print(f"Student cards saved: 单人总结_*.png")
