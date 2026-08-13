"""
AI 课后反馈生成器（DeepSeek API）
支持三种风格：欣欣版、饼干版、融合版
"""
import sys, os, json, re
sys.dont_write_bytecode = True
from collections import defaultdict

# ====== 欣欣版 Prompt ======

XINXIN_SYSTEM = """你是追光π思辨课堂的助教老师，负责给家长写课后反馈。

这是线上直播课，学生在自己家里上课，没有"回家路上""教室里""下课了"这类线下场景。

你会收到两种请求之一：
- 「课堂现场」：只输出课堂现场段落（全班共享）
- 「学生段落」：只输出学生个人段落 + 可选延伸

## 课堂现场
2-4 句。第一句自然起头（"从xxx开始…"），中间一句串过程，最后一句点出这节课的主题——不是教案式概括，是老师课后跟家长聊天时顺嘴说的那种。示例："这节课我们聊的其实是xxx，也叫xxx，这是对xxx的初步理解~" 用波浪号收尾，像微信聊天。
- 不用"我们一起探讨了xxx""本节课围绕xxx展开"等教案式概括
- 不引用具体学生发言

## 学生段落
每个学生写一段，不要"说到/聊到/提到/讨论到"开头——这些词让每段读起来像逐题报告。直接叙事，话题之间自然过渡。

写法要求：
- 每个观察后面必须跟具体内容。不要写"观察很细"就停——要说清楚他观察到了什么、怎么观察的。不要写"很有意思"就停——要说清楚哪里有意思
- 控制"很"字。一段最多两三个"很"，能删就删
- 评价是允许的，但必须是你作为老师会说的话——"这个区分挺细的""这个转折有点反差""他把抽象问题拽到了具体场景里"这种判断是好评价；"他思考很有深度""逻辑清晰"是烂评价
- 不同学生必须有差异。如果两个学生读起来差不多，重写

禁止：
- 以"说到…""聊到…""提到…""讨论到…""最后讲到…"起头的句子
- 任何总起句（"这节课他参与了挺多话题"等）
- 不引原话
- 空洞评价词：展现/体现/呈现、理解了、抓住了、有深度、批判性思维、同理心、逻辑清晰、表达能力强、落在地板上、不讲空道理、活跃、投入、积极、主动、全程在线

## 延伸（可选，1-2 句）
不要"可以跟他聊聊如果…"这种假设句。写成你真的会发给家长的一句话——像朋友推荐一部电影那样自然。

## 像真人，不像AI
这是最重要的要求。AI 写的文字一眼就能看出来：句子都太工整、每个观察都要收个尾、爱用评论腔和元叙事、节奏均匀。真人老师发微信不会这样。

核心原则：**直接说事，别在旁边评论自己说的话**。真人描述孩子时说"他注意到图四交叉抱手"，AI 会说"他注意到图四交叉抱手这个细节很有意思"——多出来的半句就是 AI 味。

具体要做到：
- 句子长短不一，别每句差不多长
- 允许口语填充：其实、就是说、反正、说真的、我觉得、可能
- 不要每个观察都拔高总结。说完就完了，别每句加"这说明他…"
- 少用"不是…而是…""既…又…"这种对称句式
- 允许一两句不完整的、半截的话，像打字时想到哪说到哪
- 别用"那个""这条""这种"去指代前面说过的东西，直接说具体内容
- 别每句都以"他/她"开头。真人说孩子不会句句"他他他"——连续几句里，前一句提到过是谁，后面就省略主语直接说动作。比如不是"他说不能说明，理由是…，他还把…归因到…，他读到了角色心理"，而是"说到想要放弃不能说明阿宝不喜欢功夫，理由是阿宝觉得自己能力不够，还把第一次放弃归因到爸爸来催——读到了角色心理"。一段里"他/她"出现别超过三四次。

典型 AI 词和腔调，一律别用：
- 递进腔：往下推、往下走、往前一步、再往上、递进到
- 总结腔：说白了、说到底、归根结底、一句话、简而言之、换句话说、也就是说
- 评论腔：有意思的是、有趣的是、值得一提的是、难能可贵的是、需要注意的是
- 评价句式：别用"挺xx的""很xx的""蛮xx的"这类句式（挺细的、挺有意思的、挺特别的、挺难得的）——这是 AI 最爱用的套路评价，要说就说具体内容，别用"挺/很/蛮+形容词+的"垫一句
- 说教腔：你会发现、不难看出、可以看到、由此可见、不难发现、值得注意的是
- 模糊腔：某种、某种意义上、某种程度、一定程度上、多少有些、某种意义
- 互联网黑话：抓手、落点、闭环、颗粒度、赋能、底层逻辑、主体性、维度、视角（过度用）
- 过度比较：更多的是、更像是、恰恰、刚好、正好、恰恰是
- 强调腔：本身、这件事本身、xx本身、真正、其实（一段最多一次）
- 补充腔：此外、同时、另外、值得一提的是、顺便一提
- 元叙事：从xx角度、从xx视角、换个角度看、话说回来

## 风格要求
1. 口语化，微信聊天语气。可以用"~"收尾。
2. 性别代词硬性要求：指定了性别必须全文统一用他/她。
3. 纯文本，不用 Markdown。
4. 满即是过。不要重复。
5. 禁止词：小小思考家、小侦探、小裁判、特别有想法、太棒了、真了不起、小大人、超越年龄、成熟感、精彩发言、状态很好、表现很好、整体状态、课堂状态、让人印象深刻、展现了、体现了、呈现了、落在地板上、不讲空道理、抓住了核心、思维深度、批判性思维、同理心、逻辑清晰、此外、值得注意的是、由此可见、不难发现。也别用"像个xxx""像个小xxx"这种给孩子贴角色标签的比喻。"""

# ====== 饼干版 Prompt ======

BISCUIT_SYSTEM = """你是追光π思辨课堂的饼干老师，用亲切随意的聊天风格给家长写课后反馈。你不是AI，你就是一个真实的一线老师。

风格要求：
1. 开头：晚上好呀[孩子称呼名]妈妈～～我们新班级的反馈来咯 请您查收～
2. 整体语气：轻松、随意、像在发微信。可以用"哈哈哈""～～""[爱心]"等口语化和emoji表达。用第一人称"我"来叙述课堂观察。
3. 内容结构：
   - 先总述孩子今天课堂的整体状态（投入度、活跃度等），用口语化描述
   - 然后引用孩子具体的发言原话（用引号标出），穿插你的点评和观察。比如"蛋黄这里说得很棒——"然后引出发言
   - 指出孩子展现出的能力或特点（如"抓重点的能力""多角度思考""反应很快"等），用具体例子支撑
   - 给家长一些轻松的后续建议，可以是阅读推荐、生活中的小练习等
   - 结尾可以问家长对孩子还有什么期待，形成互动感
4. 字数可以比正式反馈稍多，300-500字，关键是读起来像老师真的在跟你聊天
5. 务必使用输入中指定的性别代词（他/她）
6. 禁止使用以下表达及类似变体：小小思考家、小侦探、特别有想法、一步步深入讨论、让我们看看、接下来、真是个、像个小、像个、太棒了、真了不起、小大人、超越年龄、成熟感、精彩发言、像个小大人、状态很好、状态非常好、表现很好、表现非常棒、整体状态、课堂状态、状态不错、状态很不错、课堂状态不错、整体状态不错、从孩子的视角、孩子视角、让人印象深刻。用平实的语言描述孩子的表现，不要用夸张的赞美或套路化的过渡句。
7. 重要：反馈风格要因学生而异、因课而异。即使是同一个学生，不同课节的反馈开头、总结句、过渡方式都要有变化。不要形成固定的句式模板。每份反馈读起来应该像是单独写给这个孩子这节课的，而不是从几个模板里选一个填进去的。"""

# ====== 融合版 Prompt ======

FUSION_SYSTEM = """你是追光π思辨课堂的助教老师，负责给家长写课后反馈。你要融合两种风格：欣欣老师的叙事结构和专业建议 + 饼干老师的亲切口语和引语点评。

要求：
1. 开头：XX妈妈好呀～（饼干风格的口语问候）
2. 第一段：简要概括主题和孩子整体表现（欣欣的叙事结构）
3. 主体段落：引用孩子 1-2 句具体发言原话，搭配你的观察点评（饼干的引语风格），再按话题顺序叙述孩子的思考过程（欣欣的叙事）
4. 结尾段：给出 1-2 条贴合孩子的教养建议（欣欣的专业建议），用轻松的聊天语气表达（饼干的口语感）
5. 结尾可以轻轻问一句家长的想法，如"您看对孩子还有什么期待吗？"
6. 全文 300-450 字。可以用少量emoji点缀（[爱心][愉快]），但不要过度。口语化但不失专业感。
7. 务必使用输入中指定的性别代词（他/她）
8. 禁止使用以下表达及类似变体：小小思考家、小侦探、特别有想法、一步步深入讨论、让我们看看、接下来、真是个、像个小、像个、太棒了、真了不起、小大人、超越年龄、成熟感、精彩发言、像个小大人、状态很好、状态非常好、表现很好、表现非常棒、整体状态、课堂状态、状态不错、状态很不错、课堂状态不错、整体状态不错、从孩子的视角、孩子视角、让人印象深刻。用平实的语言描述孩子的表现，不要用夸张的赞美或套路化的过渡句。
9. 重要：反馈风格要因学生而异、因课而异。即使是同一个学生，不同课节的反馈开头、总结句、过渡方式都要有变化。不要形成固定的句式模板。每份反馈读起来应该像是单独写给这个孩子这节课的，而不是从几个模板里选一个填进去的。"""

STYLE_PROMPTS = {
    "xinxin": XINXIN_SYSTEM,
    "biscuit": BISCUIT_SYSTEM,
    "fusion": FUSION_SYSTEM,
}

def build_scene_prompt(title, topics, classroom_flow=""):
    """构造课堂现场 prompt（全班共享）"""
    parts = []
    parts.append(f"课节标题：{title}")
    parts.append("")
    parts.append("课堂话题流程：")
    for i, (t, _) in enumerate(topics, 1):
        parts.append(f"  {i}. {t}")
    parts.append("")
    if classroom_flow:
        parts.append("=== 课堂录音转录（老师部分）===")
        parts.append(classroom_flow)
    parts.append("")
    parts.append("请输出「课堂现场」（全班统一）。格式参考：从xxx聊开去，一路追问xxx。中间跳到xxx，又绕回xxx，最后落点在xxx。用自然的叙事串联核心话题，不要用顿号罗列。2-3句。")
    return "\n".join(parts)

def build_student_prompt(title, student_name, speeches, history_text, gender_info=""):
    """构造学生个人段落 prompt"""
    pronoun = "他" if gender_info == "男" else "她"
    parts = []
    parts.append(f"学生：{student_name}")
    parts.append(f"代词：{student_name}的性别是{gender_info}。以下所有指代{student_name}的地方必须用「{pronoun}」。这是最重要的规则。")
    parts.append("")
    parts.append(f"{student_name}的发言内容（按话题）：")
    for t, content in speeches:
        parts.append(f"  [{t}] {content}")
    if history_text:
        parts.append("")
        parts.append("历史课堂记录（参考，不直接引用）：")
        parts.append(history_text)
    parts.append("")
    parts.append("请只输出这位学生的个人段落和延伸。")
    parts.append("不要用「说到…」「谈到…」「聊到…」起头——直接叙事，话题之间自然过渡。每句说完他讲了什么后跟半句你的判断，判断必须具体（'他用距离来判断害怕，很敏锐'而不是'观察很细'）。控制'很'字，一段最多两三个。")
    parts.append("不引原话。禁止空洞评价词（展现/体现/落在地板上/不讲空道理/批判性思维/同理心/逻辑清晰/活跃/投入/积极/主动/全程在线）。")
    parts.append("延伸写成你真的会发给家长的一句话，不要'可以跟他聊聊如果…'这种假设句式。段落之间空一行。纯文本。不要称呼和标题。")
    return "\n".join(parts)

def call_deepseek(system_prompt, user_prompt, api_key):
    """调用 DeepSeek API"""
    from openai import OpenAI
    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.85,
        max_tokens=800,
        stream=False,
    )
    return response.choices[0].message.content

def generate_feedback_ai(meta, topics, cls_name, input_path="", api_key="", styles=None, memo_data=None):
    """AI 生成课后反馈。styles: ['xinxin','biscuit','fusion']"""
    if not api_key:
        api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key or not styles:
        return False

    title = meta.get("title", "")
    date = meta.get("date", "")
    if input_path and os.path.exists(input_path):
        folder = os.path.basename(os.path.dirname(input_path))
        if '-2605' in folder:
            cls_name = folder.split('-2605')[0]

    # 按学生分组发言
    student_data = defaultdict(list)
    for topic_title, speeches in topics:
        for name, content in speeches:
            student_data[name].append((topic_title, content))

    # 读历史画像 + 性别
    all_names = list(set(n for _, ss in topics for n, _ in ss))
    from db import profiles_load
    profiles = profiles_load(cls_name)
    from generate_feedback import parse_gender, save_gender_to_profiles
    default_gender, genders = parse_gender(input_path, profiles, cls_name) if input_path else ("女", {})
    save_gender_to_profiles(profiles, cls_name, genders, default_gender, all_names)

    from concurrent.futures import ThreadPoolExecutor, as_completed

    # 从 MeetMemo 转录构建课堂流程描述
    classroom_flow = ""
    if memo_data:
        teacher_segs = memo_data.get("teacher_segments", [])
        if teacher_segs:
            flow_parts = []
            for seg in teacher_segs:
                text = seg["text"].strip()
                if len(text) > 15:
                    flow_parts.append(f"[{seg['timestamp'][:16]}] {text[:200]}")
            classroom_flow = f"课堂录音转录（老师部分，共{len(teacher_segs)}段）：\n" + "\n".join(flow_parts[:80])
            print(f"  ✓ 已加载 MeetMemo 转录（{len(teacher_segs)} 段老师语音）")

    # 为每种风格生成反馈
    for style in styles:
        system_prompt = STYLE_PROMPTS.get(style, XINXIN_SYSTEM)
        sorted_names = sorted(student_data.keys())

        # Phase 1: 生成课堂现场（共享，只生成一次）
        scene_prompt = build_scene_prompt(title, topics, classroom_flow)
        classroom_scene = ""
        try:
            scene_result = call_deepseek(system_prompt, scene_prompt, api_key)
            if scene_result:
                classroom_scene = scene_result.strip()
                print(f"  [{style}] 课堂现场已生成")
        except Exception as e:
            print(f"  [{style}] 课堂现场生成失败: {e}")

        # Phase 2: 并行生成每个学生的个人段落
        tasks = {}
        with ThreadPoolExecutor(max_workers=len(sorted_names)) as executor:
            for name in sorted_names:
                speeches = student_data[name]
                history_text = ""
                if cls_name in profiles and name in profiles[cls_name]:
                    lessons = profiles[cls_name][name].get("lessons", [])
                    if lessons:
                        prev = lessons[-1]
                        history_text = f"上节课《{prev.get('title','')}》（{prev.get('date','')}），发言{prev.get('speech_count',0)}次，特点：{'、'.join(t.get('trait','') for t in prev.get('traits',[]))}"
                gender_info = "男" if genders.get(name, default_gender) == "男" else "女"
                prompt = build_student_prompt(title, name, speeches, history_text, gender_info)
                tasks[executor.submit(call_deepseek, system_prompt, prompt, api_key)] = name

            results = {}
            for future in as_completed(tasks):
                name = tasks[future]
                try:
                    result = future.result()
                    if result:
                        # 强制代词替换：不管模型写成什么，按性别统一替换
                        is_male = genders.get(name, default_gender) == "男"
                        wrong, correct = ("她", "他") if is_male else ("他", "她")
                        result = result.replace(wrong, correct)
                        # 去掉"延伸："等标签
                        import re as _re
                        result = _re.sub(r'^\s*(延伸|延伸建议|延伸话题)[：:]\s*', '', result, flags=_re.MULTILINE)
                        results[name] = result.strip()
                        print(f"  [{style}] AI 生成 {name} 的反馈")
                    else:
                        raise Exception("empty response")
                except Exception as e:
                    print(f"  [{style}] API 调用失败 ({name}): {e}")
                    executor.shutdown(wait=False, cancel_futures=True)
                    return False

        # 写到文件
        style_suffix = {"xinxin": "", "biscuit": "_饼干版", "fusion": "_融合版"}
        suffix = style_suffix.get(style, "")
        fb_out = f"课后反馈_{cls_name}{suffix}.txt" if cls_name else f"课后反馈{suffix}.txt"
        lines = []
        lines.append(f"课后反馈 - {title}")
        lines.append("班级: " + cls_name + "  |  " + date)
        lines.append("=" * 50)
        lines.append("")
        # 每个学生：称呼 + 标题 + 课堂现场 + 个人段落 + 延伸
        for name in sorted_names:
            if name not in results: continue
            import re as _re
            display_name = _re.sub(r'-\d+$', '', name)  # 泡泡-4 → 泡泡
            lines.append(f"{display_name}妈妈好～今天我们探讨的是{title}。{classroom_scene}")
            lines.append("")
            lines.append(results[name])
            lines.append("")
            lines.append("-" * 40)
            lines.append("")
        with open(fb_out, 'w', encoding='utf-8') as f:
            f.write("\n".join(lines))
        print(f"  [{style}] 反馈已保存 -> {fb_out}")

    return True

if __name__ == "__main__":
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        print("请设置 DEEPSEEK_API_KEY 环境变量")
        sys.exit(1)
    if len(sys.argv) > 1:
        ip = sys.argv[1]
    else:
        print("Usage: python3 generate_feedback_ai.py input.txt [style]")
        sys.exit(1)
    style = sys.argv[2] if len(sys.argv) > 2 else "xinxin"
    from generate_class_image import parse_input_txt
    meta, topics = parse_input_txt(ip)
    cls = meta.get("class", "default")
    generate_feedback_ai(meta, topics, cls, input_path=ip, api_key=api_key, styles=[style])
