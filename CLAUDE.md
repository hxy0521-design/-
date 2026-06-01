# CLAUDE.md — 追光π 思辨课堂素材生成工具

## 项目概述
这组 Python 脚本把思辨课堂的文字记录自动生成五样素材：长图、单人总结卡、金句海报、课后反馈、课堂实录。

## 自动授权（不用再确认）
- `python3` 命令：直接执行
- `pip3 install`：直接执行
- 文件读写：以下路径直接操作
  - `/Users/meowmeow/Claude code test/`
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
