"""
金句日历 + 电影推荐卡片（票根风格）
用法：python3 generate_golden_card.py golden_card.txt
"""
import sys
sys.dont_write_bytecode = True
from PIL import Image, ImageDraw, ImageFont
import os, datetime, random

W, P = 420, 24
NOTCH_R = 16; NOTCH_STEP = 34; DIV_R = 20
POSTER_H = 180
_PROJ_DIR = os.path.dirname(os.path.abspath(__file__))
_ICLOUD_DIR = os.path.expanduser("~/Library/Mobile Documents/com~apple~CloudDocs/追光π课后素材生成系统")
def _resolve_asset(bd, name):
    for d in [bd, _PROJ_DIR, _ICLOUD_DIR]:
        p = os.path.join(d, name)
        if os.path.exists(p): return p
    return os.path.join(bd, name)
_FONT_CFG = os.path.join(_PROJ_DIR, ".font_path")
if os.path.exists(_FONT_CFG):
    with open(_FONT_CFG) as _f:
        FONT_PATH = _f.read().strip()
else:
    FONT_PATH = os.path.expanduser("~/Library/Fonts/荆南麦圆体.ttf")
if not os.path.exists(FONT_PATH):
    FONT_PATH = "/System/Library/Fonts/Hiragino Sans GB.ttc"

PALETTES = [
    {"bg":(240,228,215),"accent":(200,115,45),"name":"暖橘"},
    {"bg":(235,225,218),"accent":(170,85,55),"name":"陶土"},
    {"bg":(238,230,218),"accent":(145,115,70),"name":"古铜"},
    {"bg":(238,228,225),"accent":(160,100,70),"name":"赭石"},
    {"bg":(228,235,228),"accent":(120,140,85),"name":"苔绿"},
    {"bg":(235,228,235),"accent":(135,95,130),"name":"藕紫"},
]

def parse_card_txt(fp):
    meta = {"title":"","unit":"","date":"","class":"","quote":"","author":"","topic":"",
            "movie":"","poster":"","rating":"","line":""}
    with open(fp,'r',encoding='utf-8') as f:
        for line in f:
            s=line.strip()
            if s.startswith('@'):
                p=s[1:].split(None,1); k=p[0].lower(); v=p[1] if len(p)>1 else ""
                if k in meta: meta[k]=v
    return meta

def _wrap(draw,text,font,mw):
    lines,cur=[],""
    for ch in text:
        t=cur+ch; w,_=draw.textbbox((0,0),t,font=font)[2:4]
        if w>mw and cur:
            if ch in "，。、；：？！》」』）】" and cur:
                lines.append(cur[:-1]); cur=cur[-1]+ch
            else:
                lines.append(cur); cur=ch
        else: cur=t
    if cur: lines.append(cur)
    return lines

def pick_palette(poster_path, bd):
    if not poster_path: return random.choice(PALETTES)
    pp = poster_path if os.path.isabs(poster_path) else os.path.join(bd, poster_path)
    if not os.path.exists(pp): return random.choice(PALETTES)
    try:
        img = Image.open(pp).convert("RGB").resize((30,30))
        pixels = list(img.getdata())
        dark = [p for p in pixels if sum(p) < 400] or pixels
        r,g,b = sum(p[0] for p in dark)//len(dark), sum(p[1] for p in dark)//len(dark), sum(p[2] for p in dark)//len(dark)
        best,score = PALETTES[0],999
        for pal in PALETTES:
            br,bg,bb=pal["bg"]; s=abs(br-r)+abs(bg-g)+abs(bb-b)
            if s<score: score=s; best=pal
        return best
    except: return random.choice(PALETTES)

def make_card(meta, out="golden_card.png", base_dir=None):
    bd = base_dir or os.path.dirname(os.path.abspath(out))
    pal = pick_palette(meta.get("poster",""), bd)
    BG, ACC = pal["bg"], pal["accent"]
    print(f"Palette: {pal['name']}")

    # 字体
    f_ctitle = ImageFont.truetype(FONT_PATH, 30)
    f_month  = ImageFont.truetype(FONT_PATH, 24)
    f_day    = ImageFont.truetype(FONT_PATH, 90)
    f_wday   = ImageFont.truetype(FONT_PATH, 17)
    f_title  = ImageFont.truetype(FONT_PATH, 18)
    f_unit   = ImageFont.truetype(FONT_PATH, 16)
    f_quote  = ImageFont.truetype(FONT_PATH, 27)
    f_author = ImageFont.truetype(FONT_PATH, 20)
    f_movie  = ImageFont.truetype(FONT_PATH, 24)
    f_rating = ImageFont.truetype(FONT_PATH, 15)
    f_line   = ImageFont.truetype(FONT_PATH, 15)

    # 日期
    ds=meta.get("date","")
    mc={"01":"一","02":"二","03":"三","04":"四","05":"五","06":"六",
        "07":"七","08":"八","09":"九","10":"十","11":"十一","12":"十二"}
    mm=ds[5:7] if len(ds)>=7 else ""; dd=ds[8:10] if len(ds)>=10 else ""
    mon=mc.get(mm,"")+"月" if mm else ""
    try:
        y,m,d=int(ds[:4]),int(ds[5:7]),int(ds[8:10])
        wday=["一","二","三","四","五","六","日"][datetime.date(y,m,d).weekday()]
    except: wday=""

    # 数据
    quote=meta.get("quote","")
    author=meta.get("author","")
    title=meta.get("title","")
    unit=meta.get("unit","")

    _di=Image.new("RGB",(100,100)); _d=ImageDraw.Draw(_di)
    ql=_wrap(_d,quote,f_quote,W-P*2-8)
    tl=_wrap(_d,title,f_title,W-P*2) if title else []

    date_items=[]
    if mon: date_items.append((mon, f_month, ACC))
    if dd: date_items.append((dd, f_day, (55,50,45)))
    if wday: date_items.append((f"周{wday}", f_wday, (150,145,140)))
    date_w=max(_d.textbbox((0,0),t,font=f)[2] for t,f,_ in date_items) if date_items else 0
    date_h=sum(_d.textbbox((0,0),t,font=f)[3]+(4 if i<len(date_items)-1 else 0) for i,(t,f,_) in enumerate(date_items)) if date_items else 0

    # ---- 计算各段高度 ----
    logo_h = 0
    if os.path.exists(_resolve_asset(bd,"logo.png")):
        logo_h = 50+4

    top_sec = 30 + logo_h + max(_d.textbbox((0,0),"金句日历",font=f_ctitle)[3], date_h) + 10
    perf1_y = top_sec
    tlines = _wrap(_d, f"话题：{meta.get('topic','')}", f_unit, W-P*2) if meta.get("topic") else []
    quote_sec = 14 + len(ql)*38 + 18 + (32 if author else 0) + len(tlines)*20 + 14 + len(tl)*22 + (6 if title else 0) + (22 if unit else 0) + 12
    divider_y = top_sec + quote_sec
    poster_sec = 14 + POSTER_H

    # slogan
    slogan=None; slogan_h=0
    sp=_resolve_asset(bd,"slogan单人.png")
    if os.path.exists(sp):
        try:
            slogan=Image.open(sp).convert("RGBA")
            if slogan.width>W-P*2:
                slogan=slogan.resize((W-P*2,int(slogan.height*(W-P*2)/slogan.width)),Image.LANCZOS)
            slogan_h=slogan.height+10
        except: pass

    bottom_pad = slogan_h + 20
    h = top_sec + quote_sec + poster_sec + bottom_pad

    # ---- 画布（透明锯齿 + 白底）----
    canvas = Image.new("RGBA", (W, h), (0,0,0,0))
    cdraw = ImageDraw.Draw(canvas)
    cdraw.rounded_rectangle([4,4,W-4,h-4], radius=10, fill=BG+(255,))

    # 上下半圆锯齿
    for ey in [0, h]:
        for nx in range(NOTCH_STEP//2, W-NOTCH_STEP//2, NOTCH_STEP):
            cdraw.ellipse([nx-NOTCH_R, ey-NOTCH_R, nx+NOTCH_R, ey+NOTCH_R], fill=(0,0,0,0))
    # 分割线处左右大锯齿
    for sx in [0, W]:
        cdraw.ellipse([sx-DIV_R, divider_y-DIV_R, sx+DIV_R, divider_y+DIV_R], fill=(0,0,0,0))

    # 合到白底
    final = Image.new("RGB", (W, h), (255,255,255))
    final.paste(canvas, (0,0), canvas)
    draw = ImageDraw.Draw(final)

    # ---- 渲染 ----
    y=30

    # Logo 右上
    logo_path = _resolve_asset(bd,"logo.png")
    if os.path.exists(logo_path):
        try:
            logo=Image.open(logo_path).convert("RGBA")
            r=50/logo.height; logo=logo.resize((int(logo.width*r),50),Image.LANCZOS)
            final.paste(logo,(W-P-logo.width,y-4),logo)
            y+=50
        except: pass

    # 金句日历(左1/4) + 日期(居中偏右) + 周一(底部对齐11)
    ct="✦ 金句日历"
    cw,ch=draw.textbbox((0,0),ct,font=f_ctitle)[2:4]
    left_x = P + 4
    right_x = W//2 + 20

    # 金句日历 垂直居中
    cal_cy = y + date_h//2
    draw.text((left_x, cal_cy-ch//2), ct, fill=ACC, font=f_ctitle)

    # 日期堆叠
    day_bottom = 0  # 11 的底部 y
    dy=y
    for t,f,c in date_items:
        tw,th=draw.textbbox((0,0),t,font=f)[2:4]
        if t.startswith("周"):
            pass  # 后面单独画
        else:
            draw.text((right_x + (date_w-tw)//2, dy), t, fill=c, font=f)
            if dd and t == dd:
                day_bottom = dy + th
        dy+=th+4

    # 周一：跟11底部对齐
    if wday:
        ww2, wh2 = draw.textbbox((0,0),f"周{wday}",font=f_wday)[2:4]
        wx = right_x + date_w + 16
        wy = day_bottom - wh2 + 4  # 微调
        draw.text((wx, wy), f"周{wday}", fill=(150,145,140), font=f_wday)
    y=top_sec

    # 穿孔线1
    for dx in range(P+8, W-P-8, 9):
        r=3 if(dx//9)%3==0 else 1.5
        draw.ellipse([dx-r,y-r,dx+r,y+r],fill=(190,185,175))
    y+=14

    # 金句
    for line in ql:
        draw.text((P, y), line, fill=(55,50,45), font=f_quote); y+=38
    y+=6
    if author:
        at=f"—— {author}"; aw,_=draw.textbbox((0,0),at,font=f_author)[2:4]
        draw.text((W-P-aw, y), at, fill=ACC, font=f_author); y+=32
    # 分隔线（金句与标题之间）
    sep_y = y
    for dx in range(P+8, W-P-8, 12):
        r = 2 if (dx//12)%3 == 0 else 1
        draw.ellipse([dx-r, sep_y-r, dx+r, sep_y+r], fill=(200,195,188))
    y += 14

    # 话题（小字浅色，自动换行）
    topic = meta.get("topic","")
    if topic:
        for tline in _wrap(draw, f"话题：{topic}", f_unit, W - P*2):
            draw.text((P, y), tline, fill=(160,155,148), font=f_unit); y += 20

    if title:
        for line in tl:
            draw.text((P, y), line, fill=(110,110,115), font=f_title); y+=22
    if unit:
        draw.text((P, y+2), unit, fill=(160,160,165), font=f_unit); y+=24
    y+=12

    # 穿孔分割线
    for dx in range(P+8, W-P-8, 9):
        r=3 if(dx//9)%3==0 else 1.5
        draw.ellipse([dx-r,divider_y-r,dx+r,divider_y+r],fill=(190,185,175))
    y=divider_y+14

    # 电影海报
    pl=False
    if meta.get("poster"):
        pp=meta["poster"]
        # Resolve /api/img-proxy to download external image
        if pp.startswith("/api/img-proxy"):
            try:
                import urllib.request, tempfile
                tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
                tmp.write(urllib.request.urlopen(f"http://localhost:5888{pp}", timeout=10).read())
                tmp.close(); pp = tmp.name
            except: pp = ""
        # Resolve /api/material-file/ paths to local files
        elif pp.startswith("/api/material-file/"):
            fname = pp.replace("/api/material-file/", "")
            fname = urllib.parse.unquote(fname)
            pp = os.path.expanduser(f"~/Library/Mobile Documents/com~apple~CloudDocs/追光π课后素材生成系统/素材库/{fname}")
        # Download external URLs
        elif pp.startswith("http://") or pp.startswith("https://"):
            try:
                import urllib.request, tempfile
                tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
                tmp.write(urllib.request.urlopen(pp, timeout=10).read())
                tmp.close(); pp = tmp.name
            except: pp = ""
        elif not os.path.isabs(pp): pp=os.path.join(bd,pp)
        if os.path.exists(pp):
            try:
                pi=Image.open(pp).convert("RGBA"); pw,ph=pi.size
                nw=W-P*2; nh=int(ph*(nw/pw))
                pi=pi.resize((nw,nh),Image.LANCZOS)
                cy=max(0,(nh-POSTER_H)//4)
                pi=pi.crop((0,cy,nw,cy+POSTER_H))
                ov=Image.new("RGBA",(nw,POSTER_H),(0,0,0,150))
                pi=Image.alpha_composite(pi,ov)
                mk=Image.new("L",(nw,POSTER_H),0)
                md=ImageDraw.Draw(mk); md.rounded_rectangle([0,0,nw,POSTER_H],radius=8,fill=255)
                pi.putalpha(mk)
                final.paste(pi,(P,y),pi); pl=True
            except: pass
    if not pl:
        for i in range(POSTER_H):
            draw.line([(P,y+i),(W-P-1,y+i)],fill=(40+i//8,42+i//10,58+i//7))

    ix,iy=P+18,y+22
    draw.text((ix,iy),"🎬 推荐素材",fill=(255,210,140),font=f_unit); iy+=28
    mv=meta.get("movie","")
    if mv: draw.text((ix,iy),mv,fill=(255,255,255),font=f_movie); iy+=30
    rt2=meta.get("rating","")
    if rt2:
        rt=f"豆瓣评分 ★ {rt2}"; rw,rh=draw.textbbox((0,0),rt,font=f_rating)[2:4]
        draw.rounded_rectangle([ix,iy,ix+rw+12,iy+rh+6],radius=5,fill=(248,185,50))
        draw.text((ix+6,iy+3),rt,fill=(255,255,255),font=f_rating)
    lt2=meta.get("line","")
    if lt2:
        lt=f"「{lt2}」"
        max_lw = W - P*2 - 32
        llines = _wrap(draw, lt, f_line, max_lw)
        lh_total = sum(draw.textbbox((0,0),l,font=f_line)[3] for l in llines) + (len(llines)-1)*4
        ly_start = y + POSTER_H - 16 - lh_total
        # 背景
        lw_max = max(draw.textbbox((0,0),l,font=f_line)[2] for l in llines)
        draw.rectangle([ix-6, ly_start-6, ix+lw_max+6, ly_start+lh_total+6], fill=(45, 40, 38))
        lcy = ly_start
        for l in llines:
            _, lh2 = draw.textbbox((0,0),l,font=f_line)[2:4]
            draw.text((ix, lcy), l, fill=(210,205,200), font=f_line)
            lcy += lh2 + 4
    y+=POSTER_H+10

    # Slogan
    if slogan: sx=(W-slogan.width)//2; final.paste(slogan,(sx,y),slogan)

    final.save(out,"PNG",optimize=True)
    return W,h

if __name__=="__main__":
    if len(sys.argv)>1: ip=sys.argv[1]
    elif os.path.exists("golden_card.txt"): ip="golden_card.txt"
    else: print("Usage: python3 generate_golden_card.py golden_card.txt"); sys.exit(1)
    meta=parse_card_txt(ip)
    cls = meta.get("class","")
    out = f"金句_{cls}.png" if cls else "golden_card.png"
    w,h=make_card(meta, out)
    print(f"Saved ({w}x{h})")
