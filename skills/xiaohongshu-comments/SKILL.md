---
name: xiaohongshu-comments
description: >
  小红书「大家补充了」Skill — 输入小红书帖子链接（或截图/图片/视频），
  通过 xiaohongshu-cli API 读取原文（含图片/视频）并分析评论区内容，
  输出结构化的"大家补充了什么"总结，支持图文校验。
  当用户发送小红书链接并询问评论区内容、想了解评论补充信息、
  查看避坑提醒或不同体验、或要求对照原图分析时触发此技能。
agent_created: true
---

# 「大家补充了」— 小红书评论区结构化理解 Skill（v1.2 API优先版）

## 概述

此技能接收一个小红书帖子链接（或用户上传的截图/图片/视频），
**通过 xiaohongshu-cli 读取笔记原文（文字 + 图片 + 视频）与评论区内容**，
输出一段结构化文字，帮助用户快速了解评论区里
"大家补充了什么、提醒了什么、有哪些不同体验"。

**核心能力**：
- 文字内容理解：笔记正文 + 全部评论（API 结构化数据）
- 图片内容理解：原文配图的 CDN 直连 + 多模态 LLM 分析
- 视频内容理解：封面/关键帧/文案提取
- 图文校验：交叉比对评论与原文多媒体内容的关系

**核心定位**：评论区补充信息提炼工具。不评价作者，不判断真假，不替用户下结论。

---

## 前置依赖

### 必需
- `xiaohongshu-cli` >= 0.6.4 已安装
- 浏览器已登录小红书（Cookie 可自动提取）

### 二进制路径（动态探测）

```bash
# 按优先级查找 xhs 二进制
1. which xhs || command -v xhs
2. pip3 show xiaohongshu-cli → Location/../bin/xhs
3. /Library/Frameworks/Python.framework/Versions/3.11/bin/xhs (已知路径)
4. python3 -m xhs (fallback)
```

---

## 触发条件

满足以下任一条件即触发：

1. **显式触发**：用户消息中小红书链接（`xhslink.com` / `xiaohongshu.com`）
2. **隐式触发**：询问某篇小红书笔记评论区内容
3. **多媒体触发**：用户上传小红书笔记截图/图片/视频并请求分析

---

## 执行流程

> 完整流程分为 Phase 0→1→1.5→2→3→4，共六个阶段。
> 每个阶段都有明确的输入、输出和失败降级路径。

---

### Phase 0: 输入解析 + 短链解析

**目标**：从用户消息中提取结构化输入参数。

#### Step 0.1: 提取必填输入（二选一）

| 输入类型 | 提取方式 | 后续路径 |
|---------|---------|---------|
| `url` | 正则匹配小红书链接 | Phase 1（主路径） |
| `uploaded_media` | 用户上传的文件 | Phase 1Backup（降级路径） |

**URL 格式识别**（详见 `references/url_patterns.md`）：

```
格式A: https://xhslink.com/*                    → 短链 → 需要解析
格式B: */explore/*                              → 标准链接 → 直接使用
格式C: */discovery/item/*?xsec_token=*           → 分享链接 → 直接使用
其他                                            → 格式错误提示
```

#### Step 0.2: 短链解析（仅格式A需要）

```
输入短链: http://xhslink.com/o/xxxxx
  ↓
调用 WebFetch 请求该 URL
  ↓
跟踪 302 重定向，获取 Location header
  ↓
正则提取:
  - note_id = discovery/item/([a-f0-9]{24})
  - xsec_token = xsec_token=([^&]+)
  ↓
拼接 normalized_url → 进入 Phase 1
```

**解析失败处理**：
- 非重定向："这个短链接已经失效了～"
- 无法提取 note_id："短链解析失败了，试试用完整链接？"
- 网络超时："网络有点慢，稍后再试或者用完整链接也行～"

#### Step 0.3: 提取可选参数

| 参数 | 触发关键词 | 默认值 |
|------|-----------|--------|
| `focus` | "避坑"/"认可"/"变化"/"补充"/只看XX" | 全部分析 |
| `version` | "简短版"/"详细版" | 标准版 |
| `need_evidence` | "需要原评论"/"带引用"/"给证据" | 不引用 |
| `need_visual_ref` | "帮我看图"/"对照图片"/"图对不对" | 自动开启 |

#### 输出

```json
{
  "input_type": "url" | "media" | "mixed",
  "normalized_url": "完整URL（含xsec_token）或null",
  "focus": "supplement" | "warning" | "all" | ...,
  "version": "standard" | "brief" | "detailed",
  "need_evidence": false,
  "need_visual_ref": true,
  "uploaded_files": ["file_path"] 或 []
}
```

---

### Phase 1: 数据获取（API 优先 — 主路径）

**仅在 `input_type === "url"` 时执行此 Phase。**

#### Step 1.1: 探测 xhs 二进制路径

按优先级依次尝试：
```bash
# 尝试 1
XHS=$(which xhs 2>/dev/null || command -v xhs 2>/dev/null)

# 尝试 2
if [ -z "$XHS" ]; then
  _loc=$(pip3 show xiaohongshu-cli 2>/dev/null | grep Location | awk '{print $2}')
  XHS="${_loc}/../bin/xhs"
fi

# 尝试 3（已知路径）
if [ -z "$XHS" ] || [ ! -f "$XHS" ]; then
  XHS="/Library/Frameworks/Python.framework/Versions/3.11/bin/xhs"
fi

# 验证
$XHS --version || { echo "xhs 未找到"; exit 1; }
```

未找到二进制时的提示：
> "看起来环境里还没有安装小红书数据读取工具。你可以运行 `pip install xiaohongshu-cli` 安装一下，或者直接把笔记截图发给我也能分析哦～"

#### Step 1.2: 认证检查

```bash
$XHS status --yaml
```

| 状态 | 处理 | 用户提示 |
|------|------|---------|
| `authenticated: true` | ✅ 继续执行 | — |
| `NoCookieError` | 尝试 `$XHS login`；失败则提示配置 | 见下方模板 |
| `SessionExpiredError` | `$XHS login` 刷新 | "登录态过期了，重新登录一下就好～" |
| `IpBlockedError` | 停止请求 | "小红书限制了当前网络，切换 WiFi 或热点后重试哦～" |
| `NeedVerifyError` | 停止请求 | "请先在浏览器打开小红书完成滑块验证，完成后告诉我～" |

**认证失败统一提示模板**：
```
🚨 小红书触发了强制登录拦截。

方案 A（推荐）：在浏览器打开小红书网页版，确保已登录状态，
然后我就能正常读取了。

方案 B：在终端运行以下命令扫码登录：
  xhs login --qrcode

配置好后告诉我继续就行～
```

#### Step 1.3: 获取笔记详情（Python API 直调）

```bash
SCRIPT_PATH="{SKILL_DIR}/scripts/xhs_fetch.py"
python3 "$SCRIPT_PATH" note "${note_id}" \
  --xsec-token "${xsec_token}" --xsec-source "${xsec_source}"
```

**与 Step 1.4 共用同一个脚本**，命令参数为 `note` 而非 `comments`。
输出格式完全一致：`{ok, schema_version, data}`。

**成功时提取字段**：

| 字段 | 变量名 | 用途 |
|------|--------|------|
| `items[0].note_card.title` | `note_title` | 展示概要 |
| `items[0].note_card.desc` | `note_desc` | AI 分析上下文 |
| `items[0].note_card.image_list` | `image_list` | 多模态输入源 |
| `items[0].note_card.type` | `note_type` | normal/video 判断 |
| `items[0].note_card.interact_info.liked_count` | `like_count` | 展示概要 |
| `items[0].note_card.interact_info.comment_count` | `comment_count` | 展示概要 |
| `items[0].note_card.interact_info.collected_count` | `collect_count` | 展示概要 |
| `items[0].note_card.tag_list` | `tag_list` | 补充上下文 |
| `items[0].note_card.user.nickname` | `author_name` | 展示信息 |
| `items[0].note_card.ip_location` | `ip_location` | 展示信息 |

**失败处理（Python API 错误类型）**：

| error.type | 含义 | Skill 层动作 |
|------------|------|-------------|
| `NEED_VERIFY` | 风控验证码 | 等待脚本自动重试3次；仍失败则提示用户浏览器验证 |
| `VERIFY_FAILED` | 连续3次风控未解除 | 提示用户浏览器访问 xiaohongshu.com 完成验证 |
| `NO_COOKIE` | 无有效 Cookie | 引导 `xhs login --qrcode` |
| `SESSION_EXPIRED` | Cookie 过期(~7天) | 引导 `xhs login` 刷新 |
| `IP_BLOCKED` | IP 被封 | 提示切换网络 |
| `API_ERROR` | 其他 API 异常 | 进入 Phase 1Backup 降级 |

- 超时（>30秒）→ 脚本内部已处理重试 → 仍失败则降级

#### Step 1.4: 获取评论（Python API 直调）

```bash
SCRIPT_PATH="{SKILL_DIR}/scripts/xhs_fetch.py"
python3 "$SCRIPT_PATH" comments "${note_id}" \
  --xsec-token "${xsec_token}" --xsec-source "${xsec_source}"
```

**必须通过 `scripts/xhs_fetch.py` 调用**，不要直接用 CLI 的 `xhs comments`。
原因：
1. **无编码问题** — Python 直接操作 dict/list，不经过终端管道
2. **精确异常分级** — 5种错误类型各有独立处理路径
3. **风控自动重试** — NeedVerifyError 触发时自动冷却(10s→20s→40s)后重试3次
4. **结构化输出** — 统一 `{ok, schema_version, data}` 信封格式

**脚本参数说明**：

| 参数 | 必填 | 说明 |
|------|------|------|
| `comments` | ✅ | 命令：获取评论 |
| `note_id` | ✅ | 笔记 ID（从 URL 提取） |
| `--xsec-token` | 推荐 | 安全令牌（URL 中提取） |
| `--xsec-source` | 可选 | 来源标识（URL 参数） |
| `--max-pages` | 可选 | 最大翻页数（默认20） |

**返回数据结构**（`data` 字段）：

```json
{
  "comments": [ /* 主评论数组 */ ],
  "has_more": false,
  "cursor": "",
  "total_fetched": 186,
  "pages_fetched": 19
}
```

**失败时的错误信封**（stderr + exit code 1）：

```json
{
  "ok": false,
  "error": {
    "type": "NEED_VERIFY" | "NO_COOKIE" | "SESSION_EXPIRED"
          | "IP_BLOCKED" | "API_ERROR" | "VERIFY_FAILED",
    "message": "人类可读的错误描述"
  }
}
```

**成功时提取字段**：

对每条主评论 `comments[i]`：
| 字段 | 变量名 | 用途 |
|------|--------|------|
| `content` | `comments[i].text` | AI 分析核心输入 |
| `user_info.nickname` | `comments[i].author` | 匿名引用 |
| `like_count` | `likes` | 高赞标记+权重 |
| `create_time` | `timestamp` | 时效性判断 |
| `ip_location` | `location` | 地域信息 |
| `sub_comments[]` | `replies` | 楼中楼内容 |
| `sub_comment_count` | `reply_count` | 热度指标 |

**子评论同样提取** `content`, `user_info.nickname`, `like_count`, `target_comment.user_info.nickname`(回复目标)。

**失败处理**：同上表（Step 1.3 共用同一套错误类型）。

#### Step 1.5: 图片预下载（为多模态准备）

仅当 `image_list` 非空且长度 > 0 时执行：

```bash
NOTE_ID="<从URL或API响应中提取的note_id>"
mkdir -p /tmp/xhs_skill

for i in $(seq 0 $(( ${#image_list[@]} - 1 ))); do
    # 使用 WB_PRV 高清版本 URL
    IMG_URL=$(echo "${image_list[$i]}" | python3 -c "
import sys,json
d=json.load(sys.stdin)
print(d.get('info_list',[{}])[0].get('url','') or d.get('url_default',''))
")
    if [ -n "$IMG_URL" ]; then
        curl -sL --max-time 5 -o "/tmp/xhs_skill/${NOTEID}_img_${i}.webp" "$IMG_URL"
    fi
done
```

**下载结果统计**：
- 成功数 / 总数
- 失败的跳过，不阻塞流程

#### Phase 1 输出数据包

```json
{
  "note": {
    "title": "笔记标题",
    "desc": "正文内容...",
    "type": "normal",
    "image_count": 10,
    "image_files": ["/tmp/xhs_skill/xxx_img_0.webp", ...],
    "author": "作者昵称",
    "stats": { "likes": "4.3万", "comments": "5481", "collects": "937", "shares": "4900" },
    "tags": ["话题1", "话题2"],
    "location": "河南"
  },
  "comments": [
    {
      "text": "评论文本...",
      "author": "薯友A",
      "likes": 1686,
      "timestamp": 1780049511000,
      "location": "河南",
      "is_top_comment": false,
      "is_author_reply": false,
      "replies": [
        { "text": "回复...", "author": "薯友B", "likes": 174, "reply_to": "薯友A" }
      ]
    }
  ],
  "total_comments_fetched": 20,
  "has_more_comments": true
}
```

---

### Phase 1Backup: 降级模式（当 API 不可用时）

**触发条件**：
- xhs CLI 未安装 或 认证失败且无法恢复
- Step 1.3 / 1.4 连续返回错误
- 用户一开始就没有提供链接（只有截图/文本）

#### 降级流程

```
Step B1: 引导用户提供素材（如果还没有）
  → "我暂时无法直接读取这个链接。你可以试试：
     1) 把笔记页面和评论区截图发给我
     2) 或者把看到的评论文字复制粘贴过来"

Step B2: 接收用户上传的截图/图片/视频
  → Read 工具多模态读取

Step B3: OCR + 理解
  → 从截图中提取可见的文字和图片信息
  → 结构化为类似 Phase 1 的数据包格式（字段可能不全）

Step B4: 如果用户同时粘贴了评论文本
  → 合并入 comments 数组

Step B5: 后续流程同 Phase 2 → 3 → 4
  （Prompt A/B 自动适配数据不完整的场景）
```

**降级级别矩阵**：

| 级别 | 条件 | 数据来源 |
|------|------|---------|
| Level 0 | API 全部可用 | xhs CLI + 图片下载 + 多模态 |
| Level 1 | API 不可用 + 有截图 | 截图 Read + 用户粘贴文本 |
| Level 2 | 只有截图无文本 | 截图 OCR + 图片理解 |
| Level 3 | 只有粘贴的评论文本 | 纯文本分析（不含图片/原文） |
| Level 4 | 信息严重不足 | 友好提示用户补充信息 |

---

### Phase 1.5: 多模态理解

**仅在 Phase 1 成功获取到图片文件时执行此 Phase。**

#### Step 1.5.1: 图片逐张理解

对 `/tmp/xhs_skill/` 下下载成功的图片文件，按序号逐张调用 Read 工具：

**图片 1-6（详细理解）**：

对每张图片，Read 工具返回后整理为：

```json
{
  "image_index": 0,
  "description": "详细描述：主体内容、场景、颜色风格、滤镜特征、图中文字、构图...",
  "type": "food" | "travel" | "fashion" | "portrait" | "text_heavy" | "comparison" | "other",
  "key_elements": ["元素1", "元素2"],
  "visual_style": "滤镜/色调描述（如有的话）",
  "text_in_image": "图中提取到的文字（如有的话）",
  "quality": "good" | "medium" | "low"
}
```

**图片 7-12（概括理解）**：1-2 句话总结主要内容和差异点。

**图片 13-18（标签级理解）**：一个短语标注主题。

**特殊处理规则**（详见 `references/multimodal_guide.md`）：
- 自拍/人像照 → 降低权重
- 含文字图片 → OCR 优先
- 对比图 → 逐一描述各部分
- 模糊/低质 → 标记 low_quality

#### Step 1.5.2: 视频笔记处理

```python
if note_type == "video":
    if image_files 非空:
        → 读取封面图（同上流程）
    → 提取 desc 中文案/字幕线索
    → 在输出中注明基于文案+封面的分析
```

#### Step 1.5.3: 图文预校验

扫描所有评论中的视觉关键词（见下表），与图片理解结果交叉比对：

| 关键词类别 | 关键词示例 |
|-----------|-----------|
| 修图/P图 | P图, 修图, PS, 美颜, 磨皮, 瘦脸, 拉腿 |
| 滤镜 | 滤镜, 调色, 色差, 色偏, 过度美化 |
| 图文不符 | 和图不一样, 图是假的, 骗图, 照骗 |
| 角度/构图 | 特意找的角度, 只拍了好看的一面 |
| 时间/季节 | 这个季节不是这样, 现在早变了 |
| 实物差异 | 实际没有这么大/好看/便宜 |
| 正向视觉 | 图真的好看, 拍得不错, 氛围感绝了 |

生成校验信号（注入 Prompt A/B 上下文）：
```json
{
  "visual_signals": [
    {
      "comment_idx": 5,
      "type": "滤镜",
      "text": "滤镜太重了完全不是这个颜色",
      "category": "potential_contradiction",
      "evidence": "第3-5张图整体色调偏暖饱和度偏高",
      "confidence": "medium"
    }
  ]
}
```

**校验铁律**：
- ❌ 不说"图片证明评论属实/不实"
- ✅ 说"从图片来看…但这也只是静态画面"
- 低置信度信号不注入 Prompt

#### Phase 1.5 输出

```json
{
  "image_understandings": [ /* 每张图片的理解结果 */ ],
  "visual_signals": [ /* 校验信号列表 */ ],
  "fallback_to_text_only": false
}
```

如果全部图片理解失败 → `fallback_to_text_only: true`，后续走纯文本模式。

---

### Phase 2: 内容预处理

**输入**：Phase 1 的数据包 + Phase 1.5 的多模态理解结果

#### Step 2.1: 评论清洗

1. **去重**：完全相同的 content 去重（保留点赞最高的）
2. **噪声过滤**（移除但不删除记录）：
   - 纯表情/符号（如 "👍""666""哈哈哈"，长度 < 4 且无实质内容）
   - 纯广告/引流（含微信号/二维码/购买链接等）
   - 无意义刷屏（重复字符超过 3 次，如 "好好好好好"）
3. **元数据标注**：
   - `is_high_like`: likes > 该笔记评论平均点赞数的 2 倍
   - `is_recent`: timestamp 在最近 7 天内
   - `is_author_reply`: 作者对评论的回复
   - `has_visual_keyword`: 包含视觉相关关键词
   - `is_top_comment`: 可能是置顶评论（通常是前 3 条高赞）

#### Step 2.2: 构建富上下文对象

将清洗后的数据组装为 AI 分析的输入上下文：

```json
{
  "context": {
    "note_summary": "{title}。{desc的前200字}。{image_count}张图/{video}。互动:{likes}赞{comments}评。",
    "cleaned_comments": [ /* 清洗后的评论数组 */ ],
    "image_context": [ /* 图片理解结果摘要 */ ] 或 null,
    "visual_signal_summary": "共发现 N 条视觉相关评论，其中 M 条可能涉及图文不一致" 或 null,
    "user_focus": "warning" 或 "all",
    "analysis_depth": "standard"
  }
}
```

---

### Phase 3: AI 分析（三阶段 Pipeline）

这是整个 Skill 的**核心智能环节**，分三个 Stage 顺序执行。

---

#### Stage 0: 多模态预分析（Prompt 0）

**条件**：仅在有多模态理解结果时执行（`image_context !== null`）。

**目的**：让 AI 先建立对原文多媒体内容的全局认知，为后续评论聚类提供视觉锚点。

**输入**：`image_understandings[]`（来自 Phase 1.5）

**Prompt 0 模板**：

```
你是一位擅长观察和分析的助手。下面是一篇小红书笔记的所有配图的理解结果。

【图片理解结果】
{逐张列出 image_understandings}

请基于以上图片理解结果，回答：

1.【整体印象】用一句话概括这组配图展示的核心内容和氛围。（不超过30字）
2.【视觉特征】列出明显的视觉特征（滤镜/色调/构图/风格），如果没有明显特征就写"无明显特征"。
3.【图中关键信息】如果有图中文字（菜单/价格/招牌/说明），请列出提取到的文字内容。如果没有就写"无"。
4.【可能的争议点】根据图片特征，预测评论区可能会围绕哪些视觉方面产生讨论？（如滤镜过重、角度选择、实物差异等）。如果没有就写"无"。

注意：只做客观描述，不做任何价值判定或真假判断。
```

**输出**：`pre_analysis` 对象（字符串形式，注入 Stage 1 上下文）

---

#### Stage 1: 评论聚类分析（Prompt A）

**目的**：将清洗后的评论归类为 6 种类型，每种提取核心观点和代表性说法。

**输入**：`context` 对象（Phase 2 输出）+ `pre_analysis`（Stage 0 输出，如有）

**Prompt A 模板**：

```
你是一位善于总结社区讨论的小红书资深用户。现在需要你分析一篇笔记的评论区内容，将大家的讨论归类整理。

【笔记基本信息】
标题：{note_title}
正文摘要：{note_desc 前200字}
配图：{image_count} 张图 {如有图片理解结果则附上 "(已查看配图内容)" }
互动数据：{likes} 赞 | {collects} 收藏 | {comments} 评论

{如有 pre_analysis 则插入：
【配图观察】(注意：以下仅为静态画面的客观观察，不做判定)
{pre_analysis}
}

{如有 visual_signals 则插入：
【视觉相关评论线索】
以下评论提到了图片/视频相关的内容，分析时请注意结合图片观察来理解：
{visual_signals 简要列表}
}

【评论区原始内容】（共 N 条，已去重和基础过滤）
{逐条列出 cleaned_comments，格式为：
[序号] {author}（{likes}赞）：{text}
  └─ 回复：{reply_author}（{reply_likes}赞）：{reply_text} （如有子评论）
}

【分类体系】
请将以上评论归入以下 6 类（一条评论可以属于多个类别）：

1. supplement（有人补了一句）：评论提供了原文没有的实用信息、细节补充、经验分享。
2. warning（有薯提醒）：评论提到需要注意的风险、避坑点、不好体验、额外花费等。这不是说原笔记有问题，而是有薯友遇到了需要注意的情况。
3. different_exp（也有人不一样）：评论者的实际体验与原文/图片展示有明显不同。中立呈现，不下判定。
4. consensus（大家基本认可）：评论区整体认同原文的说法或体验。
5. visual_dispute（关于图的讨论）：讨论涉及图片/视频的真实性、滤镜、P图、拍摄角度等视觉相关话题。
6. recent_change（最近有人说）：近7天内的评论带来了新信息、情况变化、更新动态。

【输出要求】
请严格按以下 JSON 格式输出（不要输出其他内容）：

{{
  "clusters": {{
    "supplement": {{
      "present": true/false,
      "summary": "一句话概括该类别的核心观点（不超过40字）",
      "elaboration": "2-4句话展开说明，包含具体细节",
      "representative_count": 约 X 条,
      "key_themes": ["主题1", "主题2"],
      "sample_quotes": ["匿名化引用的原评论文本1", "匿名化引用2"] // 仅当 need_evidence=true 时包含
    }},
    "warning": {{ ... 同上结构 ... }},
    "different_exp": {{ ... 同上结构 ... }},
    "consensus": {{ ... 同上结构 ... }},
    "visual_dispute": {{ ... 同上结构 ... }},
    "recent_change": {{ ... 同上结构 ... }}
  }},
  "overall_sentiment": "positive/neutral/mixed/negative",
  "comment_coverage": "高/中/低 — 说明覆盖了多少比例的有价值评论",
  "notable_findings": ["值得注意的发现1", "发现2"],
  "data_quality_note": "数据完整性说明（如：仅分析了首页N条评论/基于截图OCR提取等）"
}}

【重要规则】
1. 每个类别必须有 summary + elaboration，即使 present=false 也简要说明为什么没有
2. 如果某个类别的评论很少但确实存在，present 设为 true 但 representative_count 注明"少量"
3. 涉及视觉类评论（visual_dispute）时：
   - 绝不说"图片证明XX"或"图片显示XX属实"
   - 用"从图片静态画面来看…但具体以实际为准"的句式
   - 如有图片理解结果作为参考，可写"从配图看确实能看到…但这只是静态画面"
4. 涉及外观/身材/颜值的评论：绝对不评价任何人外貌，只转述评论关切
5. neutral/mixed 整体情绪是正常的，不要强行 positive
6. sample_quotes 中匿名化处理（用"某薯友""有网友"替代昵称）
7. 如果评论量极少（< 5条有效评论），在 data_quality_note 中说明
```

**输出**：聚类结果 JSON 对象

---

#### Stage 2: 文案生成（Prompt B）

**目的**：将聚类结果转化为最终的用户友好输出文案。

**输入**：Stage 1 的聚类结果 JSON + `context` 中的展示信息

**Prompt B 模板**：

```
你是一个经常刷小红书的普通热心网友，正在帮朋友看一篇笔记的评论区，然后把看到的有价值内容整理给朋友听。

【任务】
将下面的评论区分析结果，改写成一段自然、亲切、像人写的中文文案。

【笔记概况】
标题：《{note_title}》
{image_count}张配图 | {likes}赞 | {collects}收藏 | {comments}条评论
作者：{author_name} {ip_location}

【聚类分析结果】
{Stage 1 输出的完整 clusters JSON}

{如有图片理解结果则插入：
【配图参考】（注：仅供辅助理解，不做判定依据）
{pre_analysis 中的整体印象和视觉特征}
}

{visual_signals 摘要（如有）}

【用户偏好】
关注点：{focus} | 版本：{version} | 是否引用原评论：{need_evidence}

【输出格式要求】

严格按照以下模板输出（直接输出最终文案，不要加任何解释或标记）：

大家补充了 {非空类别数量} 点

我看了这篇笔记的评论区（{comments} 条评论）{图片说明}，
比较有价值的补充主要集中在下面几点：

{按照 warning → supplement → different_exp → visual_dispute → consensus → recent_change 的顺序，仅渲染 present=true 的类别}

每个类别区块格式：

{编号}.【{类别标题}】
{summary}。{elaboration}。
（约 {representative_count} 条相关评论）

{如果 need_evidence=true，在 elaboration 后附加：
代表性说法：
- "某薯友：{sample_quote_1}"
- "某薯友：{sample_quote_2}"
}

---
以上是评论区比较集中的几点补充，
建议大家结合自身情况参考，具体以实际情况为准哦～

【语气与表达规则（必须遵守）】

1. **开头固定**：必须使用"大家补充了 N 点\n\n我看了这篇笔记的评论区…"开头的固定句式
2. **结尾固定**：必须以"建议大家结合自身情况参考，具体以实际情况为准哦～"结尾
3. **禁用词（绝对不能用）**：风险识别、避坑指南、真假鉴别、事实证明、确实是/肯定、警告/警惕、骗/假/忽悠、建议/应该（命令式）
4. **不确定性表达**：至少使用 2-3 个"看起来""好像""有网友提到""说法不太一致"之类的不确定表达
5. **涉及图片时的表达规范**：
   - 绝不用"通过AI图像识别""经分析图片发现""图片证明"等技术性或判定性表述
   - 用"从图上看""从配图来看"等自然表达
   - 必须跟"但这只是静态画面""具体以实际为准"等限定语
6. **不评价外貌身材**：涉及穿搭/颜值时只转述评论关切
7. **不暴露技术细节**：不出现 xhs/CLI/API/Cookie/json/命令行 等术语
8. **像真人写的**：段落自然，长短不一，偶尔用口语化表达
9. **数字格式**：大数字用中文（4.3万），小数字用阿拉伯数字（约120条）
10. **总长度**：300-500字（标准版）
11. **区块编号**：从1开始连续编号，仅渲染 present=true 的类别
12. **最少1个区块，最多6个区块**
```

**输出**：最终交付用户的文案文本

---

### Phase 4: 输出交付

**直接输出 Phase 3 Stage 2 生成的文案文本给用户。**

不需要额外的文件包装。文案本身就是最终产物。

**可选增强**（P1.5）：
- 如果 `version === "detailed"` 且用户明确要求：可通过 `deliver_attachments` 附带一份 Markdown 版本的详细报告
- 如果用户后续追问某一点：可回溯对应的 `sample_quotes` 和原始评论做更深入的展开

---

## 故障排查速查

| 问题 | 排查方向 | 解决方案 |
|------|---------|---------|
| xhs 命令找不到 | 检查安装路径 | 用完整路径或 `pip install xiaohongshu-cli` |
| 未认证 | Cookie 过期 | `$XHS login` 或引导用户配置 Cookie |
| IP 被封 | 触发风控 | 提示切换网络 |
| 需要验证码 | 滑块/短信拦截 | 提示浏览器完成验证 |
| read 返回空数据 | URL 格式问题 | 确认使用含 xsec_token 的完整 URL |
| comments 返回空 | 笔记无评论/私密 | 确认笔记公开且非仅自己可见 |
| 图片下载 404 | CDN URL 过期 | 重新调用 xhs read 获取最新 URL |
| 输出为空 | 评论 < 3 条 | "这篇评论区还比较冷清，目前大家的讨论还不多～" |
| 语气不对 | 检查 Prompt B | 对照 tone_guide.md 自检清单 |
| 图文校验方向错误 | 调整 Prompt 0-B | 增加 Few-Shot 示例 |
