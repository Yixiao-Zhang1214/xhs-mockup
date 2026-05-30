# xiaohongshu-cli 集成指南

> 小红书「大家补充了」Skill — 数据获取层核心参考
> 版本：v1.3 | 日期：2026-05-30
> 基于 jackwener/xiaohongshu-cli v0.6.4 实测验证
> **架构升级：Python API 直调优先，CLI 作为备选**

---

## 一、环境依赖与安装

### 1.1 安装

```bash
pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org xiaohongshu-cli
```

### 1.2 数据获取方式（两层架构）

```
┌─────────────────────────────────────┐
│   Skill 调用层（SKILL.md）          │
│   ↓ 调用                            │
│   scripts/xhs_fetch.py              │ ← Python API 封装脚本（默认）
│   ↓ 内部调用                         │
│   xhs_cli.client.XhsClient          │ ← 核心客户端库
│   ↓ HTTP 请求                       │
│   小红书 Web API                     │
└─────────────────────────────────────┘

备选：CLI subprocess（xhs read / xhs comments --all）
      仅用于调试或 Python 环境不可用时降级
```

| 方式 | 命令/调用 | 编码 | 异常处理 | 推荐场景 |
|------|----------|------|---------|---------|
| **Python API（默认）** | `python3 xhs_fetch.py note\|comments <id>` | ✅ 无乱码 | ✅ 5级异常分级 + 风控自动重试 | **生产使用** |
| CLI 备选 | `$XHS read/comments ... --json` | ❌ 终端乱码 | ⚠️ 仅 exit code | 调试/降级 |

### 1.2 二进制路径动态探测

SKILL.md 执行时按以下优先级查找 `xhs` 二进制：

```bash
# 优先级 1: PATH 中直接可用
which xhs || command -v xhs

# 优先级 2: pip 安装位置
pip3 show xiaohongshu-cli | grep Location
# → Location: /Library/Frameworks/Python.framework/Versions/3.11/lib/python3.11/site-packages
# → 实际二进制: {Location}/../bin/xhs

# 优先级 3: 已知系统路径（macOS Apple Silicon）
/Library/Frameworks/Python.framework/Versions/3.11/bin/xhs

# 优先级 4: Python 模块调用（fallback）
python3 -m xhs
```

**实测确认路径**：`/Library/Frameworks/Python.framework/Versions/3.11/bin/xhs`

### 1.3 前置条件

| 条件 | 说明 | 检查方式 |
|------|------|---------|
| 浏览器已登录小红书 | Cookie 可被自动提取 | `$XHS status --yaml` |
| 或手动配置 Cookie | 写入配置文件 | `$XHS login --qrcode` 扫码 |

---

## 二、认证管理

### 2.1 认证状态检查

**每次执行数据获取前必须调用此命令**：

```bash
XHS="/Library/Frameworks/Python.framework/Versions/3.11/bin/xhs"
$XHS status --yaml
```

**预期输出（已认证）**：
```yaml
ok: true
data:
  authenticated: true
  user:
    name: momo
    red_id: "..."
```

### 2.2 认证状态矩阵

| 状态 | YAML 字段 | 含义 | 处理动作 |
|------|----------|------|---------|
| ✅ 已登录 | `authenticated: true` | Cookie 有效，可直接使用 | 继续执行 Step 1.2 |
| ❌ 无 Cookie | 报错含 `NoCookieError` | 从未登录过 | 尝试 `$XHS login`；失败→提示用户配置 |
| ⏰ 过期 | 报错含 `SessionExpiredError` | Cookie TTL（~7天）到期 | `$XHS login` 刷新 |
| 🚫 IP 封锁 | 报错含 `IpBlockedError` | 触发风控 | 提示用户切换网络/VPN |
| 🔒 需验证 | 报错含 `NeedVerifyError` | 触发滑块/短信验证 | 提示用户在浏览器完成验证 |

### 2.3 登录方式

#### 方式一：浏览器 Cookie 自动提取（推荐）

```bash
$XHS login
# 自动从本地浏览器读取小红书 Cookie
# 支持 Chrome / Safari / Firefox / Edge
```

#### 方式二：扫码登录

```bash
$XHS login --qrcode
# 输出二维码 → 用户手机扫码
```

#### 方式三：手动 Cookie 配置

```bash
# 创建目录
mkdir -p ~/.xiaohongshu-cli

# 写入 Cookie（从浏览器 Cookie-Editor 插件获取 Header String 格式）
cat > ~/.xiaohongshu-cli/cookies.json << 'EOF'
{
  "cookie_string": "a1=xxx; webId=xxx; ...",
  "user_agent": "Mozilla/5.0 ..."
}
EOF
```

### 2.4 未认证时的用户提示模板

```
🚨 小红书触发了强制登录拦截。

请在浏览器安装 [Cookie-Editor](https://chromewebstore.google.com/detail/cookie-editor/hlkenndednhfkekhgcdicdfddnkalmdm) 插件，
打开小红书网页版 (xiaohongshu.com)，点击插件图标，
选择 "Export As Header String"，把内容复制发给我，我来帮你配置环境。

或者你也可以试试：在终端运行以下命令扫码登录：
  xhs login --qrcode
```

---

## 三、核心命令

### 3.1 命令速查表

| 用途 | **Python API（推荐）** | CLI 备选 | 输出格式 |
|------|------------------------|---------|---------|
| 认证检查 | `$XHS status --yaml` | 同左 | YAML |
| **笔记详情** | **`python3 xhs_fetch.py note <id> [--xsec-token T]`** | `$XHS read "{url}" --json` | JSON envelope |
| **全量评论** | **`python3 xhs_fetch.py comments <id> [--all] [--max-pages N]`** | `$XHS comments "{url}" --all --json` | JSON envelope |

### 3.2 获取笔记详情

```bash
# 推荐：Python API
python3 "{SKILL_DIR}/scripts/xhs_fetch.py" note "${note_id}" \
  --xsec-token "${xsec_token}" --xsec-source "${xsec_source}"

# 备选：CLI（有编码问题）
$XHS read "${normalized_url}" --json
```

**输入**：note_id + 可选的 xsec_token / xsec_source
**输出**：结构化 JSON envelope `{ok, schema_version, data}`

**关键提取字段**：

| 字段路径 | 内容 | 用途 |
|---------|------|------|
| `items[0].note_card.title` | 笔记标题 | 展示给用户的概要 |
| `items[0].note_card.desc` | 笔记正文 | AI 分析上下文 |
| `items[0].note_card.image_list[]` | 图片列表 | 多模态理解的输入源 |
| `items[0].note_card.type` | normal / video | 决定后续处理策略 |
| `items[0].note_card.interact_info` | 点赞/收藏/评论/转发数 | 展示概要信息 |
| `items[0].note_card.tag_list[]` | 话题标签 | 补充上下文 |
| `items[0].note_card.user.nickname` | 作者昵称 | 展示信息 |
| `items[0].note_card.ip_location` | 发布地 IP 属地 | 展示信息 |

### 3.3 获取评论

```bash
# ✅ 推荐：Python API（自动翻页 + 风控重试 + 无编码问题）
python3 "{SKILL_DIR}/scripts/xhs_fetch.py" comments "${note_id}" \
  --xsec-token "${xsec_token}" --xsec-source "${xsec_source}"

# ⚠️ 备选：CLI（有终端乱码问题，仅调试用）
$XHS comments "${normalized_url}" --all --json
```

> **为什么必须用 Python API**：
> 1. CLI 输出中文到终端会变成 `????`（编码不匹配），虽然 JSON 结构完整但不便于管道处理
> 2. Python API 返回 native dict/list，无需二次 parse
> 3. 内置风控自动重试（NeedVerifyError → 冷却10s→20s→40s → 最多3次）
> 4. 可精确区分5种错误类型，每种对应不同的用户提示

**实测数据量对比**（618李佳琦帖，711评）：

| 方式 | 主评论 | 子评论 | 总计 | 翻页 |
|------|--------|--------|------|------|
| CLI 无 `--all` | ~10 | ~5 | ~15 | 第1页 |
| CLI 有 `--all` | **186** | **53** | **239** | **19页** |
| **Python API** | **186** | **53** | **239** | **max_pages=20** |

**默认策略：始终使用 Python API 的 `xhs_fetch.py comments`。**

**关键提取字段**：

| 字段路径 | 内容 | 用途 |
|---------|------|------|
| `comments[].content` | 评论文本 | AI 分析的核心输入 |
| `comments[].user_info.nickname` | 评论者昵称 | 展示时脱敏引用 |
| `comments[].user_info.image` | 头像 URL | 可选：判断是否为真人 |
| `comments[].like_count` | 点赞数 | 高赞标记 + 排序权重 |
| `comments[].create_time` | 时间戳(ms) | 时效性判断 + 最近评论筛选 |
| `comments[].ip_location` | IP 属地 | 地域分布（可选展示） |
| `comments[].sub_comments[]` | 子评论列表 | 楼中楼讨论内容 |
| `comments[].sub_comment_count` | 子评论数量 | 热度指标 |

### 3.4 内置反爬机制（无需额外处理）

xiaohongshu-cli 已内置以下措施，Skill 层无需重复实现：

| 措施 | 参数 | 说明 |
|------|------|------|
| 高斯延迟 | ~1-1.5s 间隔 | 请求间正态分布随机延迟 |
| 签名伪造 | x-s / x-s-common / x-t | 逆向自 Web 客户端签名算法 |
| 指纹伪装 | UA / sec-ch-ua | 对齐 macOS Chrome |
| 指数退避 | 最多 3 次 | 429 / 5xx 时自动重试 |
| webdriver 隐藏 | CDP 注入 | 隐藏自动化特征 |

**重要**：不要在外部添加额外的延迟或重试逻辑，避免与内置机制冲突。

### 3.5 `xhs_fetch.py` 脚本详解

> **位置**：`{SKILL_DIR}/scripts/xhs_fetch.py`
> **角色**：Skill 与 XHS API 之间的统一数据获取层

#### 脚本架构

```
xhs_fetch.py
├── load_cookies()        → 从 ~/.xiaohongshu-cli/cookies.json 加载
├── create_client()       → 实例化 XhsClient(cookies)
├── fetch_note()          → client.get_note_by_id(note_id)
├── fetch_all_comments()  → client.get_all_comments() + 风控自动重试
│   └── NeedVerifyError   → cooldown 10s→20s→40s (最多3次)
├── output_ok(data)       → stdout: {ok:true, schema_version, data}
└── error_out(type,msg)   → stderr: {ok:false, error:{type,message}}
```

#### 支持的命令

```bash
# 笔记详情
python3 xhs_fetch.py note <note_id> [--xsec-token T] [--xsec-source S]

# 全量评论（默认 max_pages=20）
python3 xhs_fetch.py comments <note_id> [--xsec-token T] [--xsec-source S] [--max-pages N]
```

#### 错误类型与退出码

| exit code | error.type | 触发原因 | 恢复方式 |
|-----------|-----------|---------|---------|
| 1 | `NEED_VERIFY` | 单次请求触发风控验证码 | 脚本自动冷却重试 |
| 1 | `VERIFY_FAILED` | 连续3次风控未解除 | 浏览器访问 xhs 完成验证 |
| 1 | `NO_COOKIE` | cookies.json 不存在或缺少 a1 | `xhs login --qrcode` |
| 1 | `SESSION_EXPIRED` | Cookie TTL(~7天) 到期 | `xhs login` 刷新 |
| 1 | `IP_BLOCKED` | IP 被小红书封禁 | 切换 WiFi/热点 |
| 1 | `API_ERROR` | 其他 API 异常（已重试耗尽） | 稍后重试或降级 |
| 2 | (usage) | 参数错误 | 检查命令格式 |

#### 输出格式

成功：stdout 写入 JSON envelope，exit 0
失败：stderr 写入 JSON error envelope，exit 非0

---

## 四、数据结构

### 4.1 笔记详情返回结构

```json
{
  "ok": true,
  "schema_version": "1",
  "data": {
    "items": [{
      "id": "6a18efa20000000007010199",
      "model_type": "note",
      "note_card": {
        "note_id": "6a18efa20000000007010199",
        "type": "normal",
        "user": {
          "user_id": "5dd0e98300000000010015bb",
          "nickname": "作者昵称",
          "avatar": "https://sns-avatar-qc.xhscdn.com/avatar/xxx.jpg"
        },
        "image_list": [
          {
            "width": 1440,
            "height": 2400,
            "url_pre": "http://sns-webpic-qc.xhscdn.com/...!nd_prv_wlteh_webp_3",
            "url_default": "http://sns-webpic-qc.xhscdn.com/...!nd_dft_wlteh_webp_3",
            "info_list": [
              {"image_scene": "WB_PRV", "url": "高清预览版URL"},
              {"image_scene": "WB_DFT", "url": "默认版URL"}
            ]
          }
        ],
        "title": "笔记标题",
        "desc": "笔记正文内容...",
        "time": 1780019106000,
        "interact_info": {
          "liked": false,
          "liked_count": "4.3万",
          "collected_count": "937",
          "comment_count": "5481",
          "share_count": "4900"
        },
        "tag_list": [
          {"type": "topic", "id": "...", "name": "话题名"}
        ],
        "ip_location": "河南"
      }
    }]
  }
}
```

### 4.2 评论返回结构

```json
{
  "ok": true,
  "schema_version": "1",
  "data": {
    "comments": [
      {
        "id": "6a196667000000002900edd9",
        "content": "评论内容文本...",
        "user_info": {
          "user_id": "67b5a167000000000e012861",
          "nickname": "评论者昵称",
          "image": "https://sns-avatar-qc.xhscdn.com/avatar/xxx.jpg",
          "ai_agent": false
        },
        "like_count": "1686",
        "create_time": 1780049511000,
        "ip_location": "河南",
        "sub_comment_count": "17",
        "sub_comments": [
          {
            "id": "6a19675d0000000028039b83",
            "content": "回复内容...",
            "user_info": {
              "nickname": "回复者",
              "image": "..."
            },
            "like_count": "174",
            "create_time": 1780049757000,
            "target_comment": {
              "id": "6a196667000000002900edd9",
              "user_info": {"nickname": "原评论者"}
            }
          }
        ],
        "sub_comment_has_more": true,
        "sub_comment_cursor": "6a19675d0000000028039b83"
      }
    ]
  }
}
```

---

## 五、错误处理

### 5.1 错误码映射表（xhs_fetch.py 输出）

| error.type | 触发原因 | Skill 层处理 | 用户提示 |
|-----------|---------|-------------|---------|
| `NO_COOKIE` | cookies.json 不存在或缺少 a1 字段 | 引导 `xhs login --qrcode` | 扫码登录指引 |
| `SESSION_EXPIRED` | Cookie TTL(~7天) 到期 | 引导 `xhs login` 刷新 | "登录态过期了，重新登录一下就好～" |
| `IP_BLOCKED` | IP 被小红书风控拦截 | 停止请求 | "小红书限制了当前网络，切换 WiFi 或热点后重试哦～" |
| `NEED_VERIFY` | 单次请求触发验证码 | **脚本自动冷却重试3次** | 通常无需用户干预 |
| `VERIFY_FAILED` | 连续3次风控验证码未解除 | 提示浏览器操作 | "请先在浏览器打开小红书完成滑块验证，完成后告诉我～" |
| `API_ERROR` | 其他 API 异常（已耗尽重试） | 降级到 Phase 1Backup | "暂时无法读取这个链接..." |

### 5.2 重试策略（内置在 xhs_fetch.py）

| 场景 | 重试次数 | 冷却间隔 | 实现位置 |
|------|---------|---------|---------|
| NeedVerifyError（风控） | **3 次** | 10s → 20s → 40s（指数增长） | xhs_fetch.py fetch_all_comments() |
| XhsApiError（API异常） | 3 次 | 5s → 10s → 15s（线性增长） | xhs_fetch.py fetch_all_comments() |
| CLI 内置退避(429/5xx) | 3 次 | 高斯延迟 + 指数退避 | xhs_cli.client._handle_response() |
| 认证类错误(NO_COOKIE/IP_BLOCKED) | **0 次** | — | 直接报错，引导用户操作 |

> **注意**：Skill 层**不需要**额外实现重试逻辑。xhs_fetch.py 已完整覆盖。

### 5.3 安全规范

| 规则 | 说明 |
|------|------|
| **绝不输出 Cookie 明文** | Cookie 仅存储于 ~/.xiaohongshu-cli/，不在聊天/日志中暴露 |
| **绝不暴露内部字段名** | 输出中不出现 `a1`, `web_id`, `xsec_token`, `note_id` 等技术术语 |
| **不绕过速率限制** | 遵循 CLI 内置延迟，不做加速处理 |
| **临时文件清理** | 下载到 /tmp 的图片不持久化存储 |
