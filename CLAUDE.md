# CLAUDE.md — 追光π 思辨课堂素材生成工具

## 项目概述
这组 Python 脚本把思辨课堂的文字记录自动生成五样素材：长图、单人总结卡、金句海报、课后反馈、课堂实录。

## 自动授权（不用再确认）
- `python3` 命令：直接执行
- `pip3 install`：直接执行
- 文件读写：以下路径直接操作
  - `/Users/meowmeow/Claude code-课后素材/`
  - `/Users/meowmeow/追光π/`
  - `/Users/meowmeow/Desktop/`
  - `/tmp/`
  - `/var/folders/` 下临时文件
- `find`、`ls`、`grep`、`sed` 等常规命令：直接执行

## 核心脚本
- `generate_all.py` — 五合一主入口
- `generate_class_image.py` — 长图 + 单人卡渲染 + txt 解析
- `generate_golden_card.py` — 金句海报
- `generate_feedback.py` — 课后反馈
- `generate_golden_card.py` — 独立金句日历

## 关键配置
- 字体：荆南麦圆体 (`~/Library/Fonts/荆南麦圆体.ttf`)，fallback Hiragino Sans GB
- 图表：`logo.png`、`slogan.png`、`slogan单人.png` 同目录
- 模板：`input_template.txt`
- 生成文件跳过：含 `template`、`golden`、`test` 的文件名

## 飞书回复规范
- 通过飞书 bridge 回复消息时，代码块控制在 15 行以内，超过的用文字概述代替
- 文件和路径引用用 `file.ts:42` 格式的链接，不要贴代码
- 回复优先用中文自然语言描述方案，避免大段代码

## 飞书消息路由
- 本窗口对应飞书机器人「欣欣的课后素材Claude」，**只回复 @本机器人 的消息**
- 未 @你 的消息一律不回复，包括其他 bot 的发言、群友之间的对话等
- 另一个机器人「欣欣的课程评估Claude」由课程评估窗口处理，本窗口不干涉
- 另一个机器人「饼干的小仆人」的发言与本窗口无关，不回复
