# 追光π 课后素材工作台

一个本地 Web 工具，把思辨课堂的文字记录一键生成五样素材：长图、单人总结卡、金句海报、课后反馈、课堂实录。

## 能做什么

- **长图** — 全课话题 + 发言 + 金句高亮，适合发家长群
- **单人总结卡** — 每人一张卡片，含得分、简评、高亮发言
- **金句海报** — 每人一句金句，可搭配电影/书籍推荐（选填）
- **课后反馈** — AI（DeepSeek）逐学生写个性化反馈，非模板拼凑
- **课堂实录** — 话题 + 发言文字整理

## 怎么用

1. 双击 `server.py` 或在终端 `python3 server.py`
2. 浏览器打开 `http://localhost:5888`
3. 新建班级 → 新建单元（指定文件夹）→ 新建课节
4. 贴发言 → 自动标金句 → 手动增减 → 调整性别 → 填海报金句
5. 点「全部生成」

## 给新用户

给饼干的话，需要先装 Python 3，终端跑：

```
pip3 install flask pillow openai
python3 server.py
```

然后浏览器打开 `http://localhost:5888`，页面会引导创建第一个班级和单元。

### 可选配置

- `export DEEPSEEK_API_KEY=sk-xxx` → 启用 AI 课后反馈（约 0.01 元/课）
- `export TMDB_API_KEY=xxx` → 金句海报自动搜电影信息（免费）

## 环境

- macOS / Windows / Linux
- Python 3.10+
- 荆南麦圆体（字体，放 `~/Library/Fonts/`）

## 技术

- 后端：Flask + Pillow
- AI 反馈：DeepSeek API
- 电影搜索：TMDB API（可选）
- 前端：原生 JS，零依赖
