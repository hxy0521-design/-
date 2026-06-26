"""
AI 课后反馈生成器（DeepSeek API）
支持三种风格：欣欣版、饼干版、融合版
"""
import sys, os, json, re
sys.dont_write_bytecode = True
from collections import defaultdict

# ====== 欣欣版 Prompt ======

XINXIN_SYSTEM = """你是追光π思辨课堂的助教老师，负责给家长写课后反馈。

要求：
1. 开头必须严格使用格式：[孩子称呼名]妈妈好～本周我们讨论的是[课节完整标题]，我们一起探讨[用5-12个字概括的核心主题]。
   示例：嘟嘟妈妈好～本周我们讨论的是端午节特辑-一个节日够不够？，我们一起探讨节日的起源与传承。
   注意：标题用完整课节标题，不用方括号。主题概括要简洁自然，不要用方括号。同班同次反馈的开头必须完全一致。开头和后续正文之间直接换行即可。
2. 第二段：简要概括孩子的整体表现（1-2句），承上启下。
3. 主体段落：按照话题顺序，连贯地叙述孩子在不同话题下的观点和发言内容。不要罗列，要编织成一段自然的叙述，展现出孩子的思考过程。
4. 结尾段：给出 1-2 条在家可以实操的教养建议。建议要贴合孩子的特点，但必须避开本节课已经讨论过的话题和观点，往生活延伸或引入新角度。用"也许可以在家跟他/她聊聊……"开头。
5. 全文 300-400 字，口语化、亲切自然，像老师在跟家长聊天，不要用书面语或官方语气。不要使用emoji。
6. 务必使用输入中指定的性别代词（他/她），即使名字听起来像另一种性别也不要用错。
7. 禁止使用以下表达及类似变体：小小思考家、小侦探、特别有想法、一步步深入讨论、让我们看看、接下来、真是个、像个小、太棒了、真了不起、小大人、超越年龄、成熟感、精彩发言、像个小大人。用平实的语言描述孩子的表现，不要用夸张的赞美或套路化的过渡句。
8. 重要：反馈风格要因学生而异、因课而异。即使是同一个学生，不同课节的反馈开头、总结句、过渡方式都要有变化。不要形成固定的句式模板。总结句（最后一段之前的那句概括）尤其要换个说法，避免出现"这节课展现了……""总体来说……""综合来看……"这类高度重复的总结句式。每份反馈读起来应该像是单独写给这个孩子这节课的，而不是从几个模板里选一个填进去的。"""

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
6. 禁止使用以下表达及类似变体：小小思考家、小侦探、特别有想法、一步步深入讨论、让我们看看、接下来、真是个、像个小、太棒了、真了不起、小大人、超越年龄、成熟感、精彩发言、像个小大人。用平实的语言描述孩子的表现，不要用夸张的赞美或套路化的过渡句。
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
8. 禁止使用以下表达及类似变体：小小思考家、小侦探、特别有想法、一步步深入讨论、让我们看看、接下来、真是个、像个小、太棒了、真了不起、小大人、超越年龄、成熟感、精彩发言、像个小大人。用平实的语言描述孩子的表现，不要用夸张的赞美或套路化的过渡句。
9. 重要：反馈风格要因学生而异、因课而异。即使是同一个学生，不同课节的反馈开头、总结句、过渡方式都要有变化。不要形成固定的句式模板。每份反馈读起来应该像是单独写给这个孩子这节课的，而不是从几个模板里选一个填进去的。"""

STYLE_PROMPTS = {
    "xinxin": XINXIN_SYSTEM,
    "biscuit": BISCUIT_SYSTEM,
    "fusion": FUSION_SYSTEM,
}

def build_user_prompt(title, topics, student_name, speeches, history_text, gender_info=""):
    """构造给 DeepSeek 的用户 prompt"""
    parts = []
    parts.append(f"课节标题：{title}")
    parts.append("")
    parts.append("本节课的全部话题：")
    for i, (t, _) in enumerate(topics, 1):
        parts.append(f"  {i}. {t}")
    parts.append("")
    parts.append(f"学生：{student_name}")
    if gender_info:
        parts.append(f"性别：{gender_info}。重要：全文必须使用'{'他' if gender_info=='男' else '她'}'来指代{student_name}，严禁用错。")
    parts.append("")
    parts.append(f"{student_name}的发言记录（已按话题分组）：")
    for t, content in speeches:
        parts.append(f"  [{t}] {content}")
    if history_text:
        parts.append("")
        parts.append("该生的历史课堂记录（供参考，可用于对比进步或持续特点）：")
        parts.append(history_text)
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

def generate_feedback_ai(meta, topics, cls_name, input_path="", api_key="", styles=None):
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

    # 为每种风格生成反馈，每个学生每种风格一个文件
    for style in styles:
        system_prompt = STYLE_PROMPTS.get(style, XINXIN_SYSTEM)
        tasks = {}
        sorted_names = sorted(student_data.keys())

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
                prompt = build_user_prompt(title, topics, name, speeches, history_text, gender_info)
                tasks[executor.submit(call_deepseek, system_prompt, prompt, api_key)] = name

            results = {}
            for future in as_completed(tasks):
                name = tasks[future]
                try:
                    result = future.result()
                    if result:
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
        lines.append(f"课后反馈 - {title} ({STYLE_PROMPTS.get(style,'')[:10]}...)" if False else f"课后反馈 - {title}")
        lines.append("班级: " + cls_name + "  |  " + date)
        lines.append("=" * 50)
        lines.append("")
        for name in sorted_names:
            if name in results:
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
