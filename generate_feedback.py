"""
课后反馈生成器（跨课记忆版）
用法: python3 generate_feedback.py your_file.txt
      支持 @gender 男 Bruce 阿恒
输出: 课后反馈_班级.txt
记忆: student_profiles.json（同目录，自动累积）
"""
import sys, os, re, json, random
sys.dont_write_bytecode = True
from collections import defaultdict
from generate_class_image import parse_input_txt, split_sentences, score_sentence

def load_profiles(cls_name=None):
    """加载学生画像（从 SQLite）"""
    from db import profiles_load
    return profiles_load(cls_name)

def save_profiles(profiles):
    """无需手动保存（SQLite 自动持久化），保留接口兼容"""
    pass

def record_lesson(profiles, cls, name, date, title, speech_count, topic_count, traits, best_quote):
    """往学生画像里追加一节课的记录（SQLite）"""
    from db import profiles_save_lesson
    profiles_save_lesson(cls, name, date, title, speech_count, topic_count, traits, best_quote)

def parse_gender(filepath, profiles=None, cls_name=None):
    """@gender 男 Bruce 阿恒 -> 这俩人男，其余女
       无 @gender 时回退到 student_profiles.json 中该班的性别记忆
       @gender 男           -> 全男（无名字=全班默认）
       @gender 女           -> 全女（默认行为）
       注意：前端保证全班同一性别时用无名格式（如 @gender Male），
       列名字时走"列出的=少数例外"语义，默认性别为相反。"""
    default = "女"
    gender_map = {}
    # 1. 从 txt 读 @gender
    if filepath and os.path.exists(filepath):
        with open(filepath, encoding='utf-8') as f:
            for line in f:
                s = line.strip()
                if s.startswith("@gender"):
                    parts = s[1:].split(None)
                    if len(parts) >= 2:
                        raw_g = parts[1]
                        g = "男" if ("男" in raw_g or raw_g.lower() == "male") else "女"
                        names = parts[2:]
                        if names:
                            default = "女" if g == "男" else "男"
                            gender_map = {n: g for n in names}
                        else:
                            default = g
                        return default, gender_map  # txt 优先，直接返回
    # 2. 回退到 profiles 中的性别记忆
    if profiles and cls_name:
        cls_profiles = profiles.get(cls_name, {})
        for name, data in cls_profiles.items():
            saved_g = data.get("gender", "")
            if saved_g and name not in gender_map:
                gender_map[name] = saved_g
        if gender_map:
            boy_count = sum(1 for g in gender_map.values() if g == "男")
            girl_count = sum(1 for g in gender_map.values() if g == "女")
            if boy_count > 0 and girl_count == 0:
                default = "男"
            elif girl_count > 0 and boy_count == 0:
                default = "女"
    return default, gender_map

def save_gender_to_profiles(profiles, cls_name, gender_map, default_gender, all_names):
    """把当前课节的性别信息存入 SQLite"""
    from db import profiles_save_gender
    profiles_save_gender(cls_name, all_names, gender_map, default_gender)

def trim_at_sentence(text, min_len=20, max_len=55):
    if len(text) <= max_len:
        return text
    cut = max_len
    for sep in "!?":  # fullwidth punctuation
        idx = text.rfind(sep, min_len, max_len+10)
        if idx > 0: cut = idx + 1; break
    return text[:cut]

def lesson_summary(profiles, cls, name):
    """返回'这是XXX的第N节课'及历史摘要"""
    if cls not in profiles or name not in profiles[cls]:
        return "", []
    lessons = profiles[cls][name]["lessons"]
    n = len(lessons)
    if n <= 1:
        return "", []
    # 收集历史特点（去重）
    all_traits = []
    seen = set()
    for l in lessons[:-1]:  # 不含本节课
        for t in l.get("traits", []):
            key = t.get("trait","")
            if key not in seen:
                seen.add(key)
                all_traits.append(t)
    summary = f"（这是{name}在{cls}的第{n}次课）"
    return summary, all_traits

def pick_history_context(profiles, cls, name, ta, current_traits):
    """从历史画像中捞1-2个值得对比的点"""
    if cls not in profiles or name not in profiles[cls]:
        return ""
    lessons = profiles[cls][name]["lessons"]
    if len(lessons) <= 1:
        return ""

    prev = lessons[-2]  # 上节课
    prev_traits = [t["trait"] for t in prev.get("traits", [])]
    curr_traits = [t["trait"] for t in current_traits]

    # 新增的特点
    new_traits = [t for t in curr_traits if t not in prev_traits]
    # 持续的特点
    kept_traits = [t for t in curr_traits if t in prev_traits]

    lines = []
    if new_traits:
        lines.append(f"{ta}这节课展现出了一些新的思考方式，比如{new_traits[0]}。")
    if kept_traits:
        lines.append(f"{ta}保持了{kept_traits[0]}的习惯，这已经是连续几节课都看到的特质了。")

    return " ".join(lines) if lines else ""

def make_opener(title, topics):
    """从话题标题提取高频主题词，生成自然开场白"""
    import random, re
    from collections import Counter
    r = random.Random(hash(title) + len(topics))
    title_short = title[:20] if title else ""

    # 从所有话题标题中提取 2-3 字词频
    stop_chars = set('，。、；：？！""''「」『』《》的了吧呢吗啊呀着过这在是不有和与或就还也要能把被让给向对从到为以因所以但而虽然而当')
    word_freq = Counter()
    for t, _ in topics:
        # 去掉标点
        t_clean = re.sub(r'[？?！!。，,、\s""「」『』《》…—\-]', '', t)
        # 去掉语气词/连接词前缀
        t_clean = re.sub(r'你觉得|你认为|为什么|怎么|什么样|是不是|会不会|有没有|不都是|怎么办|行不行|说一下|讲一讲', '', t_clean)
        t_clean = re.sub(r'尝试|描述|看看|说说|聊聊|讨论|思考|判断|如果|假如|假设|想象|试着|能不能|可以|应该|要不要', '', t_clean)
        t_clean = re.sub(r'哪一个|区别在|分别代|什么|哪里|怎么判断|愿不愿意|如何|你会|你会怎|应该|要不要', '', t_clean)
        # 提取 2-3 字词（汉字）
        for wl in [3, 2]:
            for i in range(len(t_clean) - wl + 1):
                w = t_clean[i:i+wl]
                # 跳过含标点、数字、英文的
                if re.match(r'^[一-鿿]+$', w) and all(c not in stop_chars for c in w):
                    word_freq[w] += 1

    # 取频率最高的 3 个词，过滤太通用的
    generic = {'其他人','一个人','每个人','所有人','有些人','这些人','三个人','两个人',
               '是什么','会不会','是不是','能不能','愿不愿','怎么办','怎么样','行不行',
               '你会','你能','你要','你想','你说','你看','你觉','这样','那种','这次',
               '他们','她们','它们','我们','大家','东西','事情','问题','情况',
               '其他','他人','哪个','这边','那边','这边','区别','什么','怎么','哪里',
               '但是','而且','或者','如果','因为','所以','虽然','不过','还是','只是',
               '一定','可能','应该','可以','需要','能够','愿意','希望','觉得','认为',
               '一个','两个','三个','很多','一些','很少','每个'}
    keywords = [w for w, c in word_freq.most_common(10) if c >= 2 and len(w) >= 2 and w not in generic]
    # 去重：去掉被更长词包含的（如 "泼水" 和 "泼水节"，保留 "泼水节"）
    filtered = []
    for w in keywords:
        if not any(w != other and w in other for other in keywords):
            filtered.append(w)
    keywords = filtered[:3]

    if not keywords:
        # fallback: 用标题本身
        return "今天「" + title_short + "」这节课，孩子们讨论得很投入。"

    a, b, c = (keywords + ["", "", ""])[:3]

    styles = []
    if c:
        styles = [
            "今天「" + title_short + "」这节课，我们聊的是关于" + a + "的话题，提到了" + b + "和" + c + "，孩子们讨论得很投入。",
            "这节课「" + title_short + "」，我们围绕" + a + "展开讨论，从" + b + "聊到" + c + "，每个人都有不少自己的想法。",
            "今天课堂上，孩子们聊了" + a + "——从" + b + "到" + c + "，话题跟生活很近，讨论也很活跃。",
        ]
    elif b:
        styles = [
            "今天「" + title_short + "」这节课，我们聊的是" + a + "和" + b + "的话题，孩子们讨论得很投入。",
            "这节课「" + title_short + "」，我们围绕" + a + "和" + b + "展开了讨论，每个人都有不少自己的想法。",
        ]
    else:
        styles = [
            "今天「" + title_short + "」这节课，我们聊的是关于" + a + "的话题，孩子们讨论得很投入。",
            "这节课「" + title_short + "」，我们围绕" + a + "展开了讨论，每个人都有不少自己的想法。",
        ]

    return styles[r.randint(0, len(styles)-1)]

def make_suggestion(name, ta, selected, all_sents):
    """根据学生实际表现生成具体有用的收尾建议"""
    import random
    r = random.Random(name + str(len(all_sents)))

    # 根据特点选最贴切的建议
    first = selected[0] if selected else ""

    suggestions = []

    if "独立" in first or "坚持" in first:
        suggestions = [
            ta + "有自己的判断，不跟风。平时家里聊天可以故意跟" + ta + "站反方，让" + ta + "练习把自己的理由说清楚。",
            ta + "不怕跟别人不一样，这很难得。生活中可以鼓励" + ta + "不仅说出'我不同意'，也试着说出'为什么'和'那应该怎样'。",
            ta + "能坚持自己的看法。比如买东西、选餐厅这种小事，也可以让" + ta + "来做决定并说出理由——坚持不只是态度，也是能力。",
        ]

    if "生活" in first or "经历" in first or "真实" in first:
        suggestions = [
            ta + "很会从生活中找例子。平时聊天可以多问" + ta + "一句：'这件事除了你遇到的情况，还有没有别的可能？'",
            ta + "的发言有画面感，因为总带着自己的经历。生活中可以让" + ta + "帮家人朋友出出主意——从自己的经验跳到别人的处境。",
            ta + "习惯从自己的经验出发来理解问题。偶尔可以挑战" + ta + "一下：'如果完全没经历过这件事，你会怎么想？'",
        ]

    if "角度" in first or "多视角" in first or "立场" in first:
        suggestions = [
            ta + "天然会从不同人的角度想问题。生活中家庭讨论时可以问" + ta + "：'你替别人想过了，那你自己觉得呢？'",
            ta + "的同理心强，会照顾每个人的立场。在理解所有人的基础上，帮" + ta + "练习落回到自己的判断——理解别人不等于放弃自己。",
        ]

    if "总结" in first or "收拢" in first:
        suggestions = [
            ta + "很会总结别人的观点。平时可以问" + ta + "：'你把他们说的串起来了，那你自己要加一句什么？'",
            ta + "擅长提炼和收拢。可以鼓励" + ta + "在总结之后追问自己：'串起来之后，我的结论跟他们一样吗？'",
        ]

    if "参与" in first or "覆盖" in first or "活跃" in first:
        suggestions = [
            ta + "参与度很高，每个话题都愿意试。生活中可以偶尔提醒" + ta + "：发言前多停10秒——慢一点的思考有时候更锋利。",
            ta + "在讨论中很活跃。可以偶尔换一种方式：先听完所有人，最后一个开口，看看自己的判断会不会有变化。",
        ]

    if "安静" in first or "话不多" in first or "分量" in first:
        suggestions = [
            ta + "话不多，但每次开口都有内容。平时可以鼓励" + ta + "先说——" + ta + "的想法值得被先听到。",
            ta + "发言不多，但思考有分量。可以告诉" + ta + "：想法不完整也可以说出来，生活中很多讨论都是边想边说的。",
        ]

    if not suggestions:
        suggestions = [
            ta + "有自己的思考节奏，保持住就好。平时聊天多问" + ta + "'你怎么看'，让" + ta + "习惯在更多场合表达。",
            ta + "每次发言都经过认真思考。有时候第一个冒出来的想法反而是最真实的，可以试试更快一点说出来。",
        ]

    return r.choice(suggestions)

def analyze_student(name, speeches, topics, gender="女", all_stats=None):
    ta = "她" if gender == "女" else "他"
    all_sents = []
    for _, c in speeches:
        all_sents.extend(t for t, _, _ in split_sentences(c))
    if not all_sents: return [], "", ta

    rebuttal_sents = [s for s in all_sents if any(kw in s for kw in
        ["不认同","不一定","没道理","不对","不太符合","前后矛盾","不浪费","不算浪费","我不觉得"])]
    personal_sents = [s for s in all_sents if any(kw in s for kw in
        ["我妈","我爸","我之前","我小时候","我自己","如果是我","我成为","我打算","我站在","从我","春游","研学","出去玩","上次","去过"])]
    perspective_sents = [s for s in all_sents if sum(1 for kw in
        ["角度","站在","女儿","妻子","父母","邻居","旁人","老爷爷","奶奶","如果我是"] if kw in s) >= 2]
    rhetorical = [s for s in all_sents if "?" in s and any(kw in s for kw in ["谁","怎么","为什么","难道"])]
    summary_sents = [s for s in all_sents if any(kw in s for kw in ["其实","就是","说到底","核心","关键","最重要","本质","重点","总的来说"])]
    feeling_count = sum(1 for s in all_sents for kw in ["开心","难过","害怕","不舒服","难受","喜欢","讨厌","落寞","遗憾","感动"] if kw in s)
    logic_count = sum(1 for s in all_sents for kw in ["因为","所以","如果","但是","虽然","因此","不仅","而且"] if kw in s)
    topic_count = len(set(t for t, _ in speeches))

    best_rebuttal = trim_at_sentence(rebuttal_sents[0]) if rebuttal_sents else ""
    best_personal = trim_at_sentence(personal_sents[-1]) if personal_sents else ""
    best_summary = trim_at_sentence(summary_sents[-1]) if summary_sents else ""

    avg_summary = 0
    if all_stats:
        totals = [s.get("summary",0) for s in all_stats.values()]
        avg_summary = sum(totals)/len(totals) if totals else 0

    # 构建 trait 记录（用于 JSON 存档）
    trait_records = []
    selected = []

    if len(rebuttal_sents) >= 3 and best_rebuttal:
        selected.append(ta + "在好几个话题上都有自己独立的判断，不跟着别人的思路走。比如" + ta + "觉得'" + best_rebuttal + "'--这个角度当时其他小朋友没有提到。")
        trait_records.append({"trait":"独立判断","context":best_rebuttal[:40],"type":"rebuttal"})
    elif len(rebuttal_sents) >= 1 and best_rebuttal:
        selected.append(ta + "不一定每次都说很多，但在" + ta + "在意的问题上会坚持自己的看法，比如" + ta + "说过'" + best_rebuttal + "'。")
        trait_records.append({"trait":"坚持己见","context":best_rebuttal[:40],"type":"rebuttal"})

    if len(personal_sents) >= 3 and best_personal:
        selected.append(ta + "的发言经常带着生活气息--比如" + ta + "提到'" + best_personal + "'，这种从自己真实经历出发的思考方式，让" + ta + "的观点特别具体、有说服力。")
        trait_records.append({"trait":"生活例子","context":best_personal[:40],"type":"personal"})
    elif len(personal_sents) >= 1 and best_personal:
        selected.append(ta + "偶尔会用自己的真实经历来回应讨论，比如" + ta + "说起'" + best_personal + "'，说明" + ta + "在把课堂和自己的生活做连接。")
        trait_records.append({"trait":"联系生活","context":best_personal[:40],"type":"personal"})

    if len(perspective_sents) >= 2:
        selected.append(ta + "在分析问题时，不会只从一个角度出发--" + ta + "会试着站在不同人的立场去想。这种多视角的思考习惯在讨论中很突出。")
        trait_records.append({"trait":"多视角","context":"从多个角度分析问题","type":"perspective"})

    if len(rhetorical) >= 2:
        selected.append(ta + "不太直接给答案，而是喜欢先反问再引出自己的观点，有一种带着大家一起想的感觉。")
        trait_records.append({"trait":"提问式思考","context":"喜欢先反问再表达","type":"rhetorical"})

    if len(summary_sents) >= 3 and len(summary_sents) > avg_summary * 1.5 and best_summary:
        selected.append("讨论进入中后段时，" + ta + "有一个很出彩的习惯: 把前面几个人的观点收拢起来，给出自己的总结性判断。比如" + ta + "说'" + best_summary + "'--这句话把散落的讨论串在了一起。")
        trait_records.append({"trait":"总结提炼","context":best_summary[:40],"type":"summary"})

    if topic_count >= 8 or len(speeches) >= 8:
        selected.append("今天的参与度拉满！" + ta + "几乎每个话题都在线，而且每次发言都有自己新的想法。")
    elif len(speeches) >= 5:
        selected.append("今天参与度很高！" + ta + "在好几个话题里都有主动表达，想清楚了就会说出来。")
    elif len(speeches) <= 3:
        selected.append(ta + "今天发言次数不算多，但每次开口都有自己真正想说的话，不是凑热闹。这种安静但有分量的参与方式，有时候比说很多话更有力。")
    else:
        selected.append("今天参与度比较高~ " + ta + "跟着课堂的节奏走，有自己的想法就会说出来。")

    if len(selected) < 3:
        if feeling_count > logic_count * 2 and feeling_count >= 3:
            selected.append("还有一个细节: " + ta + "在分析问题时，往往先从人的感受出发--别人在讲道理的时候，" + ta + "会先想到当事人的感受会怎样。")
            trait_records.append({"trait":"感受先行","context":"分析时先关注人的感受","type":"feeling"})
        elif logic_count > feeling_count * 3 and logic_count >= 5:
            selected.append(ta + "的思考偏理性，习惯把前因后果捋清楚再下结论，条理很清晰。")
            trait_records.append({"trait":"理性分析","context":"先理清因果再下结论","type":"logic"})

    suggestion = make_suggestion(name, ta, selected, all_sents)
    return selected, suggestion, ta, trait_records

def generate_feedback(meta, topics, output_path, input_path=""):
    cls = meta.get("class", "")
    # 如果有 input_path，优先用文件夹名做 key（区分启航1/启航2）
    if input_path and os.path.exists(input_path):
        folder = os.path.basename(os.path.dirname(input_path))
        if '-2605' in folder:
            cls = folder.split('-2605')[0]
    title = meta.get("title", "")
    date = meta.get("date", "")
    profiles = load_profiles()
    all_names = list(set(n for _, ss in topics for n, _ in ss))
    default_gender, genders = parse_gender(input_path, profiles, cls) if input_path else ("女", {})
    save_gender_to_profiles(profiles, cls, genders, default_gender, all_names)
    import random as _rnd2
    # 新开场白：xx妈妈好～本周我们讨论的是{title}，我们一起探讨{theme}。
    # 从话题提取主题词（全班统一）
    import re as _re2
    from collections import Counter as _Counter
    all_topic_text = ' '.join(t for t,_ in topics)
    # 简单主题抽取：去掉常见虚词，取高频2-3字词
    stop_words = set('的了是我们在这一起讨论关于话题你怎么为会要怎么什么哪不是就行')
    words = []
    for wl in [2, 3]:
        for i in range(len(all_topic_text) - wl + 1):
            w = all_topic_text[i:i+wl]
            if _re2.match(r'^[一-鿿]+$', w) and not any(c in stop_words for c in w):
                words.append(w)
    wc = _Counter(words)
    top = [w for w, _ in wc.most_common(3) if len(w) >= 2][:2]
    theme = '、'.join(top) if top else title[:12]
    greets = ["妈妈好～本周我们讨论的是" + title + "，我们一起探讨" + theme + "。"]
    _gr = _rnd2.Random(hash(title))

    student_data = defaultdict(list)
    for topic_title, speeches in topics:
        for name, content in speeches:
            student_data[name].append((topic_title, content))

    all_stats = {}
    for name, speeches in student_data.items():
        all_sents = [s for _, c in speeches for s, _, _ in split_sentences(c)]
        all_stats[name] = {
            "summary": sum(1 for s in all_sents if any(kw in s for kw in
                ["其实","就是","说到底","核心","关键","最重要","本质","重点","总的来说"])),
            "count": len(speeches),
        }

    lines = []
    lines.append("课后反馈 - " + title)
    lines.append("班级: " + cls + "  |  " + date)
    lines.append("=" * 50)
    lines.append("")

    for name, speeches in sorted(student_data.items()):
        gender = genders.get(name, default_gender)
        ta = "她" if gender == "女" else "他"
        traits, suggestion, _, trait_records = analyze_student(name, speeches, topics, gender, all_stats)
        all_sents = [s for _, c in speeches for s, _, _ in split_sentences(c)]

        # 存档画像
        best_quote = max(all_sents, key=lambda s: score_sentence(s, name, {})) if all_sents else ""
        record_lesson(profiles, cls, name, date, title, len(speeches), len(set(t for t,_ in speeches)), trait_records, best_quote[:100])

        # 历史上下文
        hist_summary, hist_traits = lesson_summary(profiles, cls, name)
        hist_context = pick_history_context(profiles, cls, name, ta, trait_records)

        greet = _gr.choice(greets)
        lines.append(name + greet)

        used_in_traits = set()
        for t in traits:
            for s in all_sents:
                if len(s) > 10 and s[:20] in t:
                    used_in_traits.add(s)
                    break

        viewpoint_sents = []
        scored = [(score_sentence(s, name, {}), s) for s in all_sents if 15 < len(s) < 80 and s not in used_in_traits]
        scored.sort(key=lambda x: -x[0])
        seen = set()
        for _, s in scored:
            if s not in seen and len(viewpoint_sents) < 2:
                seen.add(s); viewpoint_sents.append(s)

        if viewpoint_sents:
            lines.append("")
            parts = []
            for vs in viewpoint_sents:
                topic_for_this = ""
                for t, c in speeches:
                    if vs in c: topic_for_this = t; break
                tag = "聊到" + topic_for_this[:18] + "时" if topic_for_this else "讨论中"
                parts.append(ta + "在" + tag + "说: " + vs)
            merged = "。".join(p.rstrip("。") for p in parts)
            if not merged.endswith("。"):
                merged += "。"
            lines.append(merged)

        lines.append("")
        for t in traits: lines.append(t)
        if hist_context:
            lines.append("")
            lines.append(hist_context)
        total_s = len(speeches)
        if total_s >= 5 or len(traits) >= 3:
            lines.append("")
            lines.append(suggestion)
        lines.append("")
        lines.append("-" * 40)
        lines.append("")

    save_profiles(profiles)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(lines))
    print("反馈已保存 -> " + output_path)
    print("学生画像已更新 -> " + PROFILE_FILE)

if __name__ == "__main__":
    ip = None
    if len(sys.argv) > 1:
        ip = sys.argv[1]
    else:
        from generate_all import scan_input_files
        files = scan_input_files()
        if not files: print("没有可用的 txt 文件。"); sys.exit(1)
        if len(files) == 1:
            ip = files[0][0]; print("唯一可用: " + ip)
        else:
            import datetime
            print("选择文件:")
            for i, (f, cls, tit, mt) in enumerate(files):
                dt = datetime.datetime.fromtimestamp(mt).strftime("%m/%d %H:%M")
                label = f"{cls} | {tit}" if cls and tit else f
                print(f"  [{i+1}] {label}  ({dt})  <- {f}")
            ch = input(f"选 (1-{len(files)}): ").strip()
            try:
                idx = int(ch)-1
                if 0 <= idx < len(files): ip = files[idx][0]
            except: pass
    if not ip: print("Usage: python3 generate_feedback.py your_file.txt"); sys.exit(1)

    meta, topics = parse_input_txt(ip)
    cls = meta.get("class", "")
    cls_safe = cls.replace(" ", "").replace("-", "-") if cls else "default"
    out = "课后反馈_" + cls_safe + ".txt" if cls else "课后反馈.txt"
    generate_feedback(meta, topics, out, input_path=ip)
