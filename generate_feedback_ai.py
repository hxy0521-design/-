"""
AI 课后反馈生成器（DeepSeek API）
支持三种风格：欣欣版、饼干版、融合版

欣欣版 = 统一的一份【📍本节内容】 + 每个孩子一段【🌟个人亮点】
"""
import sys, os, json, re, time
sys.dont_write_bytecode = True
from collections import defaultdict

# ====== 欣欣版 Prompt ======

XINXIN_SYSTEM = """你是追光π思辨课堂的老师，课后要给家长写这节课的反馈。反馈分两部分：📍本节内容（全班共用一份）和 🌟个人亮点（每个孩子一段）。

你会收到两种请求之一：
- 「本节内容」：只输出全班共用的那一段，不出现任何孩子的名字
- 「个人亮点」：只输出某一个孩子的那一段

语音是线上直播课，学生在自己家里上课，没有"回家路上""教室里""下课了"这类线下场景。

## 本节内容
230 字上下，一段话，固定成这个顺序：
1. 今天用什么形式上完了一个什么议题的探讨，主题是《课节名》~
2. 交代这节课的情境从哪儿开始，孩子跟着走过了哪几步
3. 孩子在这些节点上做了什么动作（感受立场、带入角色、做出选择、替谁算账）
4. 最后一句收在这节课真正在聊的是什么上，用"这节课我们聊的其实是……"起头

只写这一节课自己的东西。凡是换到别的课上也成立的话，一句都别写——"引导孩子理解……""不再用简单的好/坏评判复杂的公共问题""锻炼了表达能力"这类全是废话，这一条最要紧。收尾不要追加反问，不要来一句金句。

## 个人亮点
每个孩子一段，两到三段，长短不一。这个孩子说得多的可以写长，没什么可写的就写短，不用凑。
1. 第一句给这个孩子这节课整体的位置或心态，可以带上全班。
2. 中间锚在这节课具体的地方——哪个环节、哪段材料、哪个角色预设，孩子在那里是怎么说的、怎么想的。孩子是引子，环节和预设本身也要讲到。
3. 挑一到两处孩子的原话照录，保留口语和语病，短的直接嵌进句子中间。实录里的话不要翻译成书面语。
4. 结尾是你自己的感慨，落在孩子、以后、这个世界，不给这个孩子下判断。

范例按孩子类型分了三份：话多的、常规的、状态时好时坏的。写之前先看这个孩子的发言量和他接住了哪些环节，判断他更像哪一类，主要照那一份的结构和长度写；另外两份只用来对语气。

## 必须避开（前面几版就是栽在这里）
- 禁止对偶句，特别是"不是A，是B""既A又B"这种对称结构，一个孩子的段落里最多出现一处。要表达递进就换成"不止于A，还会B"，或者干脆拆成两句分开说。修理例子：不写"他挑的不是最好说的立场，是中间那个最难站直的立场"，改成"他挑的是中间那个最难站直的立场"；不写"她想的不是鸟会不会伤心，是这一顿吃不吃得完"，改成"她先想到的是这一顿吃不吃得完，下一顿还找不找得到"。
- 禁止用评审式的句子给孩子下定义："他是最较真的一个""他是用算账的方式站过去的""代入得挺快的""展现出很强的思辨能力""这个观察很敏锐"。孩子的特点要用他说了什么、做了什么、没做什么带出来。
- 禁止：抽象名词短语；这说明/体现了/展现了；也许可以聊聊；给孩子提炼特点；把孩子的话整理成一条逻辑链；分成发言/表达/亮点那样的小标题；结尾来一句金句；猜性别；替孩子开脱或美言；编造你自己的动作和反应（"我当时愣住了""我把这句话记在听课本子上""我扫了眼全班的表情"）。
- 不许编造孩子没说过的语气、表情、心理、动机——"她说得很干脆""他犹豫了一下""别看他嘴上说得狠"这类一律别写。你只知道他说了什么。
- 不许提别的孩子的名字和发言，也不要拿这个孩子跟另一个孩子比。说"今天的多数孩子""全班"可以。如果这个孩子的原话里带到了别人的名字（"兆兆和淼淼的想法有一个问题"这种），转述时把名字换成"前面几个同学""前面有人"，不要照录名字。
- 每个孩子的开头和结尾不许用同一个句式。不要人人都"XX今天属于全班里最……的那个"，不要人人都"以后……应该会……吧~"。有的孩子可以就停在事实上，不写感慨。
- 破折号全文最多一处。
- 评价直接说，不要用"挺+形容词"垫（"挺细""挺准""挺有意思"）。"很+形容词"是正常的。

## 语气
像老师课后跟家长聊天的口气，不是评估报告。可以用我、口语、语气词、波浪号、不那么工整的句子。语气可以有个性，但不要每段都一个调子。纯文本，不用 Markdown。
"""

# 定稿范例（我们自己写的），照这个写法和语气来
SECTION_EXAMPLE = """今天我们用全局剧本杀的形式完成了一个拆迁议题下人与人关系和利益抉择的探讨，主题是梧桐里的最后一天~40多年的老小区梧桐里要拆迁了，从梧桐里中6个居民的身份故事开始，感受不同的角色的不同立场，并带入角色，在自己的立场做出选择。站在不同人群视角表达观点、思考集体决策规则、讨论少数人的意见如何被对待。这节课我们聊的其实是"少数人的坚持"和"人的需求被观察到"之间的距离。"""

# 三种孩子类型各一份定稿。先判断要写的孩子像哪一类，主要照那一份写。
HIGHLIGHT_EXAMPLE = """=== 范例一 · 话多的孩子（班上最能说、发言量最大的那类）===

小A或者今天的多数孩子，都是以人类亏钱了鸟太多的心态进行的陈述。这节课有一个刁钻的问题，为了9只鸟让庞大的进出口贸易减速或者换地方，这值不值得？他没有直接回答我，而是反问了一个问题：口在哪儿都一样，便宜几百公里而已，为什么非得建在这块鸟用了十年的人工洼地上呢？还总结一句很朴素但真诚的道理：船是死的，鸟是活的。

今天最后有一个多视角的环节，小A选了大家都比较抵触的"反派角色"道路建设人员，当鸟类的保护影响到自己已经进行一半的工作，道路建设人员是不在乎、甚至轻视的，鸟而已，不行就克隆。听起来很离谱的预设，其实实际上是对人和鸟类利益冲突的深刻理解，如果不是大家都这么想，怎么会接二连三地挤压濒危鸟类的生存空间呢。

但还好，年轻的孩子们还具有着丰盈的同理心~我想在他们掌管的未来，动物的空间和生存权利会更被重视的~

=== 范例二 · 常规的孩子（发言不多不少、稳稳当当的那类）===

这节课班里大多数人是站在鸟这边的，小B也是。从勺嘴鹬的外形开始，不是美不美观，都是功能和实用价值上：嘴像雨靴，嘴和脚都是黑的，能吃鱼贝壳和蠕虫，嘴可以当吸管放进去，口大就吸得进去。当视频里的博主说可以两全其美，他没有直接给对方下定义，说对方太傻太蠢太人类视角，而是呈现事实，为什么让鸟挪呢，让港口挪开不好吗，船可以等一等，贸易也不是非得靠这一块地撑着，但鸟失去这次机会可能就再也回不来了。今天最后有一个多视角的环节，他挑了自驾营地负责人。这个角色可以一路喊着修路，小B看到了修路的好与坏：新路能带来更多营地的客人，可也会破坏这里；他又不希望路改得太远太晚，怕长了几公里就找不到路。我想这样的两难，此刻在鸟的利益和营地的收益之间摆动，未来还会在更多时刻，摆动在互相掣肘的两方或者在小B的心里。

=== 范例三 · 状态时好时坏的孩子（有的环节接得住、有的环节没动静）===

今天小C贯穿始终的都是鸟类爱好者的身份，日常生活就是爱鸟的，也有自己的小鸟。从最开始观察照片，她很直白哈哈，先说好圆啊像颗球，再注意到身后的沙地有很多贝壳的碎片，从这儿推出这是一只水鸟。不止于外貌，还会结合图片里的其他信息还有自己的背景知识去观察和思考是它吃什么、住在什么环境里。

今天最后有一个多视角的环节，她也挑了鸟类爱好者，当人类公路穿越鸟类栖息地：鸟少了以后作为食物的螃蟹和虾会跑到路上来，人坐在车上也看不到鸟可能会发生事故；还想到的鸟的视角，如果你家附近出现很多怪物，跑得飞快很可能会压死你，那你还会住在这里吗。对动物的观察和理解，对动物处境的留意和感知，是非常重要也非常美妙的能力。像是勺嘴鹬这样的鸟类受到人类影响的困顿，会一直停留在像小C这样的鸟类爱好者心里，未来世界的孩子们，会更友好的对待动物们的！"""

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


def build_section_prompt(title, topics, classroom_flow=""):
    """构造📍本节内容 prompt（全班共享，不出现孩子名字）"""
    parts = []
    parts.append("这节课的标题：" + title)
    parts.append("")
    parts.append("课堂话题流程（这节课从哪儿开始、走过哪几步）：")
    for i, (t, _) in enumerate(topics, 1):
        parts.append(f"  {i}. {t}")
    all_speeches = [(n, c) for _, ss in topics for n, c in ss]
    if all_speeches:
        parts.append("")
        parts.append("孩子们在这节课上说过的关键内容（只当作情境参考，不要写进本节内容，更不要出现任何名字）：")
        for n, c in all_speeches:
            parts.append("  - " + c[:120])
    if classroom_flow:
        parts.append("")
        parts.append("=== 课堂录音转录（老师部分，情境背景）===")
        parts.append(classroom_flow)
    parts.append("")
    parts.append("=== 定稿范例（照这个写法、这个长度、这个语气）===")
    parts.append(SECTION_EXAMPLE)
    parts.append("")
    parts.append("请只输出「📍本节内容」这一部分，一段话，全班共用，不出现任何孩子的名字，也不要写称呼。230 字上下，不要超出太多。")
    return "\n".join(parts)


def build_student_prompt(title, student_name, speeches, history_text, gender_info=""):
    """构造学生个人段落 prompt（饼干版/融合版用的旧写法）"""
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


def build_highlight_prompt(title, student_name, speeches, topics, history_text, gender_info="",
                           class_size=0, classroom_flow=""):
    """构造 🌟个人亮点 prompt（只写这一个孩子）"""
    pronoun = "他" if gender_info == "男" else "她"
    parts = []
    parts.append("这节课的标题：" + title)
    parts.append(f"你要写的孩子：{student_name}")
    parts.append(f"口语里指代{student_name}用「{pronoun}」。")
    if class_size:
        parts.append(f"这个班今天一共 {class_size} 个孩子。可以带全班说话，但不要提别的孩子的名字和发言。")
    parts.append("")
    parts.append("这节课的环节流程（个人亮点中间要讲到环节或角色预设本身，孩子是引子）：")
    for i, (t, _) in enumerate(topics, 1):
        parts.append(f"  {i}. {t}")
    parts.append("")
    parts.append(f"{student_name}在这节课上的全部发言（原话照录，一到两处直接嵌进句子；其余按意思转述，不要翻译成书面语）：")
    for t, content in speeches:
        parts.append(f"  [{t}] {content}")
    if history_text:
        parts.append("")
        parts.append("历史课堂记录（背景参考，不要直接写进来）：")
        parts.append(history_text)
    if classroom_flow:
        parts.append("")
        parts.append("=== 课堂录音转录（老师部分，情境背景）===")
        parts.append(classroom_flow)
    parts.append("")
    parts.append("=== 定稿范例（三种孩子类型各一份，只学写法、结构和语气，句子一律不能照抄）===")
    parts.append(HIGHLIGHT_EXAMPLE)
    parts.append("")
    parts.append(f"请只输出【{student_name}】这一个孩子的「🌟个人亮点」，两到三段，长短按他的发言量来。先判断{student_name}更像范例里的哪一类，照那一份写。第一句先给位置或心态，中间锚到这节课具体的地方，结尾是你自己的感慨。不要写称呼，不要写标题，不要跟别的孩子比。")
    parts.append(f"提醒：范例里的小A、小B、小C是定稿时写别的孩子的。凡是范例里有、而{student_name}的发言和课堂录音里都没有的事（比如家里养了什么、平时爱好什么、性格怎样），一句都不许写。")
    return "\n".join(parts)


def call_deepseek(system_prompt, user_prompt, api_key):
    """调用 LLM API（默认 DeepSeek，可用 ZG_LLM_* 环境变量切换到其他 OpenAI 兼容服务）"""
    from openai import OpenAI
    base_url = os.environ.get("ZG_LLM_BASE_URL", "https://api.deepseek.com")
    model = os.environ.get("ZG_LLM_MODEL", "deepseek-v4-flash")
    client = OpenAI(api_key=api_key, base_url=base_url)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.85,
        max_tokens=4000,
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

        if style == "xinxin":
            _generate_xinxin(system_prompt, title, date, cls_name, topics, student_data,
                            sorted_names, classroom_flow, profiles, genders, default_gender, api_key)
            continue

        # ---------- 饼干版 / 融合版：沿用旧的「课堂现场 + 学生段落」写法 ----------
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
                result = strip_style_noise(result, name, genders, default_gender)
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
            display_name = re.sub(r'-\d+$', '', name)  # 泡泡-4 → 泡泡
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


def strip_style_noise(result, name, genders, default_gender):
    """统一后处理：代词纠正 + 去掉标签 + 挺/蛮 兜底替换"""
    is_male = genders.get(name, default_gender) == "男"
    wrong, correct = ("她", "他") if is_male else ("他", "她")
    # 「其他」「他们」里含「他/她」，不能被代词纠正误伤（其他→其她）
    guards = {"其他": "\x00G1\x00", "他们": "\x00G2\x00", "她们": "\x00G3\x00"}
    for k, v in guards.items():
        result = result.replace(k, v)
    result = result.replace(wrong, correct)
    for k, v in guards.items():
        result = result.replace(v, k)
    result = re.sub(r'^\s*(延伸|延伸建议|延伸话题)[：:]\s*', '', result, flags=re.MULTILINE)
    return result.replace('挺', '很').replace('蛮', '很')


def _generate_xinxin(system_prompt, title, date, cls_name, topics, student_data, sorted_names,
                     classroom_flow, profiles, genders, default_gender, api_key):
    """欣欣版：📍本节内容（一份，全班共用） + 🌟个人亮点（每个孩子一段）"""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    def _kid_history(name):
        if cls_name in profiles and name in profiles[cls_name]:
            lessons = profiles[cls_name][name].get("lessons", [])
            if lessons:
                prev = lessons[-1]
                return (f"上节课《{prev.get('title','')}》（{prev.get('date','')}），"
                        f"发言{prev.get('speech_count',0)}次")
        return ""

    # 本节内容 和 每个孩子的个人亮点 都是独立请求，一起丢进线程池并发
    kid_prompts = {}
    with ThreadPoolExecutor(max_workers=3) as ex:
        section_future = ex.submit(
            _call_with_retry, system_prompt,
            build_section_prompt(title, topics, classroom_flow), api_key, "本节内容")
        for name in sorted_names:
            gender_info = "男" if genders.get(name, default_gender) == "男" else "女"
            kid_prompts[name] = ex.submit(
                _call_with_retry, system_prompt,
                build_highlight_prompt(
                    title, name, student_data[name], topics, _kid_history(name),
                    gender_info, class_size=len(sorted_names),
                    classroom_flow="\n".join(classroom_flow.split("\n")[:30])),
                api_key, name)

    # 本节内容
    section_text = ""
    try:
        section_text = (section_future.result() or "").strip()
    except Exception as e:
        print(f"  [xinxin] 本节内容生成失败: {e}")
    if section_text:
        # 本节内容里绝不允许出现孩子名字，出现就换成「孩子」（不能盲替代词，「其他」会被改坏）
        for n in sorted_names:
            section_text = section_text.replace(n, "孩子")
        section_text = section_text.replace('挺', '很').replace('蛮', '很')
        # 模型常常自己带上「📍本节内容」标题（有时还会带两遍），统一剥掉
        section_text = re.sub(r'^(📍\s*本节内容\s*)+', '', section_text).strip()
        print("  [xinxin] 📍本节内容 已生成")

    results = {}
    for name in sorted_names:
        try:
            result = kid_prompts[name].result()
        except Exception as e:
            print(f"  [xinxin] API 调用失败 ({name}): {e}")
            continue
        if not result:
            print(f"  [xinxin] API 调用失败 ({name}): 3次均空响应")
            continue
        results[name] = strip_style_noise(result, name, genders, default_gender).strip()
        # 剥掉模型自己带的标题（【名字】/🌟个人亮点 / Markdown 加粗）
        results[name] = re.sub(r'^\s*(\*\*)?【[^】]*】(\*\*)?\s*', '', results[name])
        results[name] = re.sub(r'^\s*(🌟\s*)?个人亮点\s*[:：]?\s*', '', results[name])
        print(f"  [xinxin] 🌟个人亮点 {name} 已生成")

    if not section_text and not results:
        print("  [xinxin] 全部生成失败，跳过")
        return

    fb_out = f"课后反馈_{cls_name}.txt" if cls_name else "课后反馈.txt"
    lines = []
    lines.append(f"课后反馈 - {title}")
    lines.append("班级: " + cls_name + "  |  " + date)
    lines.append("=" * 50)
    lines.append("")
    lines.append("📍本节内容")
    lines.append("")
    lines.append(section_text or "(本节内容生成失败)")
    lines.append("")
    lines.append("=" * 50)
    lines.append("")
    lines.append("🌟个人亮点")
    lines.append("")
    for name in sorted_names:
        if name not in results:
            continue
        display_name = re.sub(r'-\d+$', '', name)  # 泡泡-4 → 泡泡
        lines.append(f"【{display_name}】")
        lines.append("")
        lines.append(results[name])
        lines.append("")
        lines.append("-" * 40)
        lines.append("")
    with open(fb_out, 'w', encoding='utf-8') as f:
        f.write("\n".join(lines))
    print(f"  [xinxin] 反馈已保存 -> {fb_out}")


def _call_with_retry(system_prompt, prompt, api_key, name=""):
    """最多 3 次（含首次），处理 Flash 模型偶发空响应"""
    result = None
    for attempt in range(3):
        try:
            if attempt:
                time.sleep(0.8)
            result = call_deepseek(system_prompt, prompt, api_key)
            if result:
                return result
        except Exception as e:
            if attempt == 2:
                print(f"  [xinxin] API 调用异常 ({name}): {e}")
    return None


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
