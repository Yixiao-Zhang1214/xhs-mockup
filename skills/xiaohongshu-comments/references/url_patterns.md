# URL 格式与解析规则

> 小红书「大家补充了」Skill — 输入解析模块参考
> 版本：v1.2 | 日期：2026-05-30

---

## 一、支持的 URL 格式

### 1.1 三种标准格式

| 编号 | 格式类型 | 示例 | 处理方式 |
|------|---------|------|---------|
| A | **短链（xhslink.com）** | `http://xhslink.com/o/7m19VOgHvtj` | WebFetch 跟踪 302 重定向 → 提取真实 URL + xsec_token |
| B | **explore 链接** | `https://www.xiaohongshu.com/explore/6a18efa20000000007010199` | 直接传给 xhs CLI（CLI 自行处理 token） |
| C | **discovery/item 链接** | `https://www.xiaohongshu.com/discovery/item/6a18efa20000000007010199?xsec_token=CBeO922Rb7CBA7YS8wMTn9M-tjhistxTJVHKNMlEaNDhA=` | 确认含 xsec_token → 直接使用 |

### 1.2 分享链接变体

分享卡片中可能包含额外参数，需要清理：

```
# 原始分享链接（含多余参数）
https://www.xiaohongshu.com/discovery/item/6a18efa20000000007010199?xsec_token=xxx&source_type=share&app_id=xxx&...

# 清理后（仅保留核心参数）
https://www.xiaohongshu.com/discovery-item/6a18efa20000000007010199?xsec_token=xxx
```

**保留参数**：note_id + xsec_token
**丢弃参数**：source_type, app_id, share_id, utm_* 等追踪参数

---

## 二、短链解析流程

### 2.1 解析步骤

```
输入: http://xhslink.com/o/7m19VOgHvtj
  ↓
Step 1: WebFetch 请求该短链
  ↓
服务端返回 302 重定向，Location header 为:
https://www.xiaohongshu.com/discovery/item/6a18efa20000000007010199?xsec_token=CBeO922Rb7CBA7YS8wMTn9M-tjhistxTJVHKNMlEaNDhA=&source_type=share&...
  ↓
Step 2: 正则提取核心信息
  ↓
提取规则:
  - note_id: /discovery\/item\/([a-f0-9]{24})/
  - xsec_token: /xsec_token=([^&]+)/)
  ↓
Step 3: 拼接完整 URL → 传给 xhs CLI
```

### 2.2 提取正则

```regex
# note_id（24位十六进制）
/discovery\/item\/([a-f0-9]{24})/

# xsec_token（Base64编码的token）
/xsec_token=([^&\s]+)/
```

### 2.3 解析失败处理

| 失败场景 | 原因 | 处理方式 |
|---------|------|---------|
| WebFetch 返回非 302 | 短链已失效/被撤销 | "这个短链接已经失效了，你可以试试用完整链接～" |
| Location 中无 note_id | 链接格式变化 | "短链解析失败了，建议直接用完整的小红书链接" |
| 网络超时 | 网络问题 | "网络有点慢，稍后再试或者用完整链接也行～" |

---

## 三、URL 校验规则

### 3.1 正则校验（初筛）

```regex
# 小红书 URL 通用匹配（宽松）
https?://(www\.)?xiaohongshu\.com/(explore|discover|discovery/item|note)/.*

# 短链匹配
https?://xhslink\.com/.*
```

### 3.2 格式错误提示

当用户输入不匹配以上任一模式时：

> "这个链接看起来不像小红书的链接哦～请确认是小红书笔记的分享链接或短链接"

---

## 四、可选参数识别

### 4.1 参数列表

| 参数 | 触发关键词示例 | 默认值 | 说明 |
|------|--------------|--------|------|
| `focus` | "避坑"/"认可"/"变化"/"补充"/"只看提醒" | 全部分析 | 分析侧重点 |
| `version` | "简短版"/"详细版"/"简略"/"详细点" | 标准版 | 输出长度控制 |
| `need_evidence` | "需要原评论"/"带引用"/"给证据"/"举例" | 不引用 | 是否附带代表性原评论文本 |
| `need_visual_ref` | "帮我看图"/"对照图片"/"图对不对" | 自动校验（默认开启） | 图片理解与图文校验 |

### 4.2 focus 映射表

| 用户说 | 对应分析侧重 |
|-------|------------|
| "避坑"/"注意"/"小心" | 加权 warning 类聚类 |
| "认可"/"赞同"/"支持" | 加权 consensus 类聚类 |
| "变化"/"更新"/"最近" | 加权 recent_change + 最新时间权重 |
| "补充"/"还有啥" | 加权 supplement 类聚类 |
| "不一样"/"不同意见" | 加权 different_exp 类聚类 |
| "图片"/"P图"/"滤镜" | 加权 visual_dispute + 强制开启多模态 |

---

## 五、特殊输入场景

### 5.1 多链接处理

用户同时发送多个链接时：
- **串行处理**（避免触发频率限制）
- 每个链接独立输出结果
- 进度提示："正在分析第 N / M 个链接..."

### 5.2 混合模式

用户同时发了链接 + 截图/图片：
- **主路径**：API 获取文本数据（更全更准）
- **辅助路径**：截图用于补充图片理解（如果 API 图片下载失败）

### 5.3 纯截图/纯文本降级

无链接时的降级入口，详见 SKILL.md Phase 1Backup。
