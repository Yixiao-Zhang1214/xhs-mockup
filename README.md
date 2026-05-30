# 小红书「大家补充了」Skill

**把评论区变成正文的一部分。**

---

## 为什么做这个？

小红书攻略帖的评论区藏着一座「金矿」：正文没写的坑、进阶技巧、替代方案，全在评论里。

但问题是：

- **读者看不到**。正文读完就走了，评论区几百条，根本翻不动。
- **作者顾不上**。发帖时想不到读者会问什么，等评论堆起来想补正文，精华已经被淹了。
- **后来者找不到**。同样的问题被问了一遍又一遍，高赞回答没人记得。

---

## 这个 Demo 做了什么？

用 AI 自动分析评论，识别「有人提问 + 有人回答」的高质量问答，加上「大家都在说」的评价摘要，打包成「大家补充了」模块，直接塞进正文下方。

读者不用翻评论，5 分钟内就能 get 全文精华 + 社区补充。

### 🎯 核心能力

1. **智能解析评论**
   - 自动识别问题类评论
   - 匹配高赞回复作为解答
   - 过滤无价值内容

2. **结构化输出**
   - ⚠️ 有人补充了（有解答的问题）
   - 💬 大家都在说（高赞评价摘要）
   - 🔥 最新热议（实时热门讨论）

3. **多链接支持**
   - 支持完整URL和短链接
   - 自动提取评论数据
   - 支持分页获取全量评论

## 快速体验

### 演示模式（无需登录）

👉 打开 [xhs-skill-test.html](xhs-skill-test.html)

直接体验完整交互流程，预置模拟数据。

### 真实模式（需Cookie认证）

1. **登录小红书账号**
   - 在浏览器打开 xiaohongshu.com 并登录
   - 按 F12 → Application → Cookies → xiaohongshu.com
   - 复制 `a1` 或 `web_session` 的 Value

2. **粘贴Cookie**
   - 打开 [xhs-skill-test.html](xhs-skill-test.html)
   - 粘贴Cookie → 确认登录

3. **粘贴任意小红书链接测试**

## 技术架构

```
┌─────────────────────────────────────┐
│           用户输入层                  │
│   (小红书链接 / Cookie 认证)          │
└────────────────┬────────────────────┘
                 │
┌────────────────▼────────────────────┐
│         数据获取层 (xhs_cli)          │
│   Python API → 结构化 JSON 返回       │
└────────────────┬────────────────────┘
                 │
┌────────────────▼────────────────────┐
│          AI 分析层 (LLM)             │
│   评论聚类 → 要点归纳 → 格式生成       │
└────────────────┬────────────────────┘
                 │
┌────────────────▼────────────────────┐
│           输出渲染层                   │
│   「大家补充了」卡片 → 小红书样式       │
└─────────────────────────────────────┘
```

## 项目结构

```
web/
├── xhs-mockup.html           # 完整Mockup展示
├── xhs-skill-test.html      # Skill测试页面
├── skills/
│   └── xiaohongshu-comments/
│       ├── SKILL.md         # Skill定义文档
│       ├── scripts/
│       │   ├── xhs_fetch.py       # 数据获取脚本
│       │   └── media_extractor.py # 媒体提取
│       ├── references/       # 参考文档
│       └── tests/            # 测试场景
└── ...
```

## 开发指南

### 本地运行

```bash
# 克隆仓库
git clone https://github.com/Yixiao-Zhang1214/xhs-mockup.git
cd xhs-mockup

# 安装依赖
pip install xhs-cli

# 登录小红书（浏览器Cookie）
xhs-cli login

# 启动本地服务（可选，用于真实模式）
cd scripts
python xhs_skill_server.py

# 用浏览器打开
open ../web/xhs-skill-test.html
```

### 部署到云端

#### GitHub Pages（静态页面）

1. Fork 本仓库
2. 进入 Settings → Pages
3. Source 选择 `main` 分支 `/ (root)`
4. 等待部署完成

#### 云端后端（真实模式）

真实模式需要部署后端服务来处理小红书API请求：

| 平台 | 部署方式 |
|------|----------|
| Vercel | Edge Functions |
| Netlify | Functions |
| Railway | 原生Python支持 |
| Cloudflare | Workers (需JS/WASM) |

## 常见问题

### Q: 为什么需要Cookie？
小红书API需要登录态认证。Cookie存储在本地浏览器中，不会上传到云端服务器。

### Q: Cookie安全吗？
Cookie仅存储在你的本地浏览器（localStorage）中。云端部署的页面不会访问你的账号数据。

### Q: 支持短链接吗？
支持。会自动跟踪重定向获取真实URL。

## 相关文档

- [SKILL.md](skills/xiaohongshu-comments/SKILL.md) - 完整Skill定义
- [技术方案](../小红书大家补充了_Skill_技术方案_v1.2.md) - 架构设计文档

## License

MIT
