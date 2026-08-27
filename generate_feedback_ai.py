"""
AI 课后反馈生成器（DeepSeek API）
支持三种风格：欣欣版、饼干版、融合版
"""
import sys, os, json, re, time
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
- 别用"跳到""绕回""转折到""岔到""聊开去""最后落在""落点在"这类词描述课堂推进——听起来像课乱了。直接说"从xx开始""接着聊xx""后来看了xx""最后聊到xx"，或者像"下半节课一起从xx看xx"这样自然带过

## 学生段落
这是"课后反馈"，不是"表现评估"。别写成对孩子发言的打分评语，要写成一封家长读了能感受到孩子在课堂里的样子的信。核心是让孩子这节课的**体验、情绪、收获**被家长看见，而不是"他回答得好不好"。

**写 1-2 个孩子在课堂上有真实反应的时刻**：当时聊到什么（一句话带出话题）→ 孩子当时的反应/状态 → 这个时刻里他体验到了什么、理解了点什么。比如他聊到某个话题时特别投入、突然想通了、被某个问题卡住了、纠正了自己之前的想法——这些"反应"比"他回答得准不准"更值得告诉家长。

然后**收尾一句写他这节课的收获或变化**：他理解了什么、观念有没有松动、对某个东西的看法有没有变。像"他这节课慢慢发现，喜欢和占有其实是两回事"这种成长记录，不是"表现很好"。

可选：如果有值得接着聊的，加一句"也许可以聊聊xxx"，没有就不写。

写法要求：
- 写体验和收获，少写"他答得好/观察准"这种评估结论
- 控制"很"字。一段最多两三个
- 不同学生必须有差异
- 不引原话
- 空洞评价词禁：展现/体现/呈现、理解了、抓住了、有深度、批判性思维、同理心、逻辑清晰、表达能力强、活跃、投入、积极、主动、全程在线
- **严禁揣测发言文字里没有的信息**：语气、表情、心理、时间、动机、真诚度，这些课堂记录里全都没有，编了就是瞎猜。典型例子（一律别写）："说得很干脆""早想过""不是临时接的""不是随口答的""那个瞬间他其实在琢磨""犹豫了一下""认真想了一会儿""他好像一直在找"。你只知道他"说了什么"，不知道他"怎么说、为什么说、心里怎么想"。要写就写他说了什么、想了什么角度。

## 像真人，不像AI
这是最重要的要求。AI 写的文字一眼就能看出来：句子都太工整、每个观察都要收个尾、爱用评论腔和元叙事、节奏均匀。真人老师发微信不会这样。

核心原则：**直接说事，别在旁边评论自己说的话**。真人描述孩子时说"他注意到图四交叉抱手"，AI 会说"他注意到图四交叉抱手这个细节很有意思"——多出来的半句就是 AI 味。

具体要做到：
- 句子长短不一，别每句差不多长
- 允许口语填充：就是说、反正、说真的、我觉得、可能
- 不要每个观察都拔高总结。说完就完了，别每句加"这说明他…"
- 少用"不是…而是…""既…又…"这种对称句式
- 允许一两句不完整的、半截的话，像打字时想到哪说到哪
- 别用"那个""这条""那条""这种""这/那+量词+名词"去指代前面说过的东西——"阿宝那条线""这个故事线"里的"那条"就是 AI 味，直接说"阿宝的故事线""故事线"。能用具体名词就别用这/那指代
- 别每句都以"他/她"开头。真人说孩子不会句句"他他他"——连续几句里，前一句提到过是谁，后面就省略主语直接说动作。比如不是"他说不能说明，理由是…，他还把…归因到…，他读到了角色心理"，而是"说到想要放弃不能说明阿宝不喜欢功夫，理由是阿宝觉得自己能力不够，还把第一次放弃归因到爸爸来催——读到了角色心理"。一段里"他/她"出现别超过三四次。

典型 AI 词和腔调，一律别用：
- 递进腔：往下推、往下走、往前一步、再往上、递进到
- 总结腔：说白了、说到底、归根结底、一句话、简而言之、换句话说、也就是说
- 评论腔：有意思的是、有趣的是、值得一提的是、难能可贵的是、需要注意的是
- 评价句式：别用"挺/蛮+形容词"（"挺细""挺准""挺真实""挺有意思"）——这是 AI 最爱用的套路评价。评价可以放在句子最后当独立短句（"很细致的观察""判断很准确"），也可以直接说内容，但别用"挺"字垫。注意："很+形容词"是正常的，"挺+形容词"才是 AI 味
- 说教腔：你会发现、不难看出、可以看到、由此可见、不难发现、值得注意的是
- 模糊腔：某种、某种意义上、某种程度、一定程度上、多少有些、某种意义
- 互联网黑话：抓手、落点、闭环、颗粒度、赋能、底层逻辑、主体性、维度、视角（过度用）
- 过度比较：更多的是、更像是、恰恰、刚好、正好、恰恰是
- 强调腔：本身、这件事本身、xx本身、真正
- 补充腔：此外、同时、另外、值得一提的是、顺便一提
- 元叙事：从xx角度、从xx视角、换个角度看、话说回来
- 网络流行语装口语：有点东西、有内味、绝了、太顶了、真香、拿捏、DNA动了——AI 一用这些就露馅，真人老师不这么说话
- 别话说一半：说"没把放弃简单归因到意志力上"就停是不完整的，要补上后面——"而是理解和感受人物的困难"。观点要说完
- 犹豫揣测词：好像、似乎、仿佛、其实、显然、那个时刻、这个瞬间、那一刻——AI 用它们引出编造的揣测。要么删掉直接说事实，要么换成确定的口吻（"他和陶匠都很在意"，不是"他好像很在意"）
- 抽象概括：别写"这个想法又进了一步""比前面更深""往前推了一层"这种没具体内容的概括。要说清楚跟什么比、具体差在哪（"和博物馆里的临摹件不同"）
- 评价可以写，但要直接、肯定、带温度：像"思维很活跃~""这一点很棒而且很难得~"这种确定的肯定很好；"他好像挺有想法的""他其实思考得不错"这种犹豫的、半信半疑的别写

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
    parts.append("请输出「课堂现场」（全班统一）。参考示例：\"从喜欢的东西开始，延续xxx的画面，讨论人和物品之间的情感连接。下半节课一起从xxx看情感浓度的变化，从A到B的转折。这节课我们聊的其实是'喜欢'这件事的层次，从热爱到痴迷的变化~\" 用自然叙事串联核心话题，不要用顿号罗列，不要'聊开去''跳到''绕回''最后落在'这类词。2-3句。")
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
    parts.append("请只输出这位学生的个人段落。")
    parts.append("写 1-2 个他在课堂上有真实反应的时刻：聊到什么话题 → 他当时的反应/状态 → 这个时刻他体验到或理解了点什么。这是课后反馈不是表现评估，别写'他答得好/观察准'这种评语。")
    parts.append("结尾一句写他这节课的收获或变化（理解了什么、观念有没有松动）。有值得聊的加'也许可以聊聊xxx'，没有不写。")
    parts.append("不引原话。禁止空洞评价词（展现/体现/落在地板上/不讲空道理/批判性思维/同理心/逻辑清晰/活跃/投入/积极/主动/全程在线）。")
    parts.append("纯文本，不要称呼和标题。")
    return "\n".join(parts)

def call_deepseek(system_prompt, user_prompt, api_key):
    """调用 LLM API（默认 DeepSeek，可用 ZG_LLM_* 环境变量切换到其他 OpenAI 兼容服务）"""
    from openai import OpenAI
    base_url = os.environ.get("ZG_LLM_BASE_URL", "https://api.deepseek.com")
    model = os.environ.get("ZG_LLM_MODEL", "deepseek-chat")
    client = OpenAI(api_key=api_key, base_url=base_url)
    response = client.chat.completions.create(
        model=model,
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
        api_key = os.environ.get("ZG_LLM_API_KEY", "") or os.environ.get("DEEPSEEK_API_KEY", "")
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

    # 记录本节课到画像（供下节课历史上下文）。AI 路径也要写，否则跨课记忆只在关键词路径累积
    try:
        from generate_feedback import record_lesson
        for name, speeches in student_data.items():
            record_lesson(profiles, cls_name, name, date, title, len(speeches), len(set(t for t, _ in speeches)), [], "")
    except Exception:
        pass

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
                classroom_scene = scene_result.strip().replace('挺', '很').replace('蛮', '很')
                print(f"  [{style}] 课堂现场已生成")
        except Exception as e:
            print(f"  [{style}] 课堂现场生成失败: {e}")

        # Phase 2: 并行生成每个学生的个人段落
        tasks = {}
        with ThreadPoolExecutor(max_workers=2) as executor:
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
                tasks[executor.submit(call_deepseek, system_prompt, prompt, api_key)] = (name, prompt)

            results = {}
            for future in as_completed(tasks):
                name, prompt = tasks[future]
                result = None
                # 最多重试 3 次（含首次），处理 Flash 模型偶发空响应
                for attempt in range(3):
                    try:
                        if attempt == 0:
                            result = future.result()
                        else:
                            time.sleep(0.8)
                            result = call_deepseek(system_prompt, prompt, api_key)
                        if result:
                            break
                    except Exception as e:
                        if attempt == 2:
                            print(f"  [{style}] API 调用失败 ({name}): {e}")
                if not result:
                    print(f"  [{style}] API 调用失败 ({name}): 3次均空响应")
                    continue
                # 强制代词替换：不管模型写成什么，按性别统一替换
                is_male = genders.get(name, default_gender) == "男"
                wrong, correct = ("她", "他") if is_male else ("他", "她")
                result = result.replace(wrong, correct)
                # 去掉"延伸："等标签
                import re as _re
                result = _re.sub(r'^\s*(延伸|延伸建议|延伸话题)[：:]\s*', '', result, flags=_re.MULTILINE)
                # 后处理：挺/蛮 → 很（兜底，AI 漏了也能拦住）
                result = result.replace('挺', '很').replace('蛮', '很')
                results[name] = result.strip()
                print(f"  [{style}] AI 生成 {name} 的反馈")

            if not results:
                print(f"  [{style}] 所有学生反馈均生成失败，跳过")
                continue

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
