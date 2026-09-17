#!/usr/bin/env python3
"""地产大亨交易记录 → 课后素材风格长图"""
import os
from PIL import Image, ImageDraw, ImageFont

# 路径
FONT_PATH = os.path.expanduser("~/Library/Fonts/荆南麦圆体.ttf")
LOGO_PATH = "/Users/meowmeow/Claude code-课后素材/logo.png"
SLOGAN_PATH = "/Users/meowmeow/Claude code-课后素材/slogan.png"
INPUT_PATH = os.path.expanduser("~/Downloads/交易记录.txt")
OUTPUT_PATH = os.path.expanduser("~/Desktop/交易记录_长图.png")

# 字体
def font(size):
    if os.path.exists(FONT_PATH):
        return ImageFont.truetype(FONT_PATH, size)
    return ImageFont.truetype("/System/Library/Fonts/Hiragino Sans GB.ttc", size)

# 读 txt
if not os.path.exists(INPUT_PATH):
    print(f"找不到 {INPUT_PATH}")
    print("请先在网页里点「导出交易记录」，txt 会下载到 Downloads")
    exit(1)

with open(INPUT_PATH, encoding="utf-8") as f:
    lines = [l.rstrip() for l in f if l.strip()]

# 布局参数
WIDTH = 1080
PADDING_X = 60
TOP = 60
LINE_H = 44
TITLE_SIZE = 48
SUB_SIZE = 26
TEXT_SIZE = 30
SMALL_SIZE = 24

# 配色（暖色，跟课后素材长图一致）
BG = (255, 250, 242)
HEADER = (60, 50, 40)
SUB = (150, 140, 130)
TEXT = (70, 60, 50)
ACCENT = (190, 140, 90)
DIVIDER = (210, 200, 185)
ROUND_COLOR = (170, 120, 70)

# 先算总高度
draw_tmp = ImageDraw.Draw(Image.new("RGB", (10, 10)))
f_title = font(TITLE_SIZE)
f_sub = font(SUB_SIZE)
f_text = font(TEXT_SIZE)

# 标题区
title = "地产大亨 · 交易记录"
round_line = lines[1] if len(lines) > 1 else ""

# 分行测量内容高度
content_lines = []
in_content = False
for l in lines:
    if l.startswith("【") or "交易记录" in l or "结算轮次" in l or "最终资产" in l:
        continue
    if l.strip():
        content_lines.append(l)

# 估算高度
def wrap(text, font, max_w):
    draw_tmp = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    result = []
    for para in text.split("\n"):
        if not para:
            result.append("")
            continue
        cur = ""
        for ch in para:
            if draw_tmp.textlength(cur + ch, font=font) <= max_w:
                cur += ch
            else:
                result.append(cur)
                cur = ch
        result.append(cur)
    return result

# 计算总高度
total_h = TOP + 80  # 标题 + 空行
for l in content_lines:
    wrapped = wrap(l, f_text, WIDTH - 2 * PADDING_X)
    total_h += len(wrapped) * LINE_H
total_h += 120  # 底部留白 + slogan

img = Image.new("RGB", (WIDTH, total_h), BG)
draw = ImageDraw.Draw(img)

# logo 右上
y = TOP
if os.path.exists(LOGO_PATH):
    logo = Image.open(LOGO_PATH).convert("RGBA")
    h = 80
    ratio = h / logo.height
    lw = int(logo.width * ratio)
    logo = logo.resize((lw, h), Image.LANCZOS)
    img.paste(logo, (WIDTH - PADDING_X - lw, y), logo)
    logo_w = lw
else:
    logo_w = 0

# 标题
draw.text((PADDING_X, y), title, fill=HEADER, font=f_title)
y += 60
if round_line:
    draw.text((PADDING_X, y), round_line, fill=SUB, font=f_sub)
    y += 40
y += 20

# 分隔线
draw.line([(PADDING_X, y), (WIDTH - PADDING_X, y)], fill=DIVIDER, width=2)
y += 30

# 内容
for l in content_lines:
    wrapped = wrap(l, f_text, WIDTH - 2 * PADDING_X)
    for wl in wrapped:
        # 轮次着色
        if wl.startswith("第") and "轮" in wl[:8]:
            # 找到轮次部分
            idx = wl.find("轮")
            draw.text((PADDING_X, y), wl[:idx+1], fill=ROUND_COLOR, font=f_text)
            draw.text((PADDING_X + draw.textlength(wl[:idx+1], font=f_text), y), wl[idx+1:], fill=TEXT, font=f_text)
        else:
            draw.text((PADDING_X, y), wl, fill=TEXT, font=f_text)
        y += LINE_H
    y += 6

# slogan 底部
if os.path.exists(SLOGAN_PATH):
    slogan = Image.open(SLOGAN_PATH).convert("RGBA")
    max_w = WIDTH - 2 * PADDING_X
    if slogan.width > max_w:
        ratio = max_w / slogan.width
        slogan = slogan.resize((max_w, int(slogan.height * ratio)), Image.LANCZOS)
    sw, sh = slogan.size
    sx = (WIDTH - sw) // 2
    sy = total_h - 60 - sh
    img.paste(slogan, (sx, sy), slogan)

img.save(OUTPUT_PATH)
print(f"长图已生成：{OUTPUT_PATH}")
