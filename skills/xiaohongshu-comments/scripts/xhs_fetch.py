#!/usr/bin/env python3
"""
小红书数据获取脚本 — 封装 xhs_cli.XhsClient，供 Skill 调用
用法:
  python3 xhs_fetch.py note <note_id> [--xsec-token TOKEN] [--xsec-source SRC]
  python3 xhs_fetch.py comments <note_id> [--xsec-token TOKEN] [--xsec-source SRC] [--max-pages N]

输出: JSON 到 stdout (结构化 envelope)
错误: JSON {"ok": false, "error": {"type": "...", "message": "..."}} 到 stderr + exit 1
"""

import json
import sys
import os
import time
import traceback

# ── 导入 XHS 客户端 ──
try:
    from xhs_cli.client import XhsClient
    from xhs_cli.exceptions import (
        NeedVerifyError, NoCookieError, IpBlockedError,
        SessionExpiredError, XhsApiError,
    )
except ImportError as e:
    error_out("IMPORT_ERROR", f"无法导入 xiaohongshu-cli: {e}", exit_code=1)

# ── Cookie 路径 ──
COOKIE_PATH = os.path.expanduser("~/.xiaohongshu-cli/cookies.json")

# ── 风控重试配置 ──
MAX_RETRIES = 3
COOLDOWN_BASE = 10  # 首次冷却秒数


def load_cookies():
    """加载本地 Cookie 文件"""
    if not os.path.exists(COOKIE_PATH):
        error_out("NO_COOKIE", f"Cookie 文件不存在: {COOKIE_PATH}", exit_code=1)
    with open(COOKIE_PATH, "r") as f:
        cookies = json.load(f)
    # 检查关键 cookie
    if not cookies.get("a1"):
        error_out("INVALID_COOKIE", "Cookie 中缺少 a1 字段", exit_code=1)
    return cookies


def create_client():
    """创建并返回已认证的 XhsClient 实例"""
    cookies = load_cookies()
    try:
        client = XhsClient(cookies=cookies)
        return client
    except Exception as e:
        error_out("CLIENT_ERROR", f"创建客户端失败: {e}", exit_code=1)


def fetch_note(client, note_id, xsec_token="", xsec_source=""):
    """
    获取笔记详情
    返回 dict 或 None
    """
    return client.get_note_by_id(note_id)


def fetch_all_comments(client, note_id, xsec_token="", xsec_source="", max_pages=20):
    """
    获取全部评论（带自动风控重试）
    返回 dict (含 comments/has_more/total_fetched/pages_fetched) 或 None
    """
    last_error = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            result = client.get_all_comments(
                note_id=note_id,
                xsec_token=xsec_token,
                xsec_source=xsec_source,
                max_pages=max_pages,
            )
            return result
        except NeedVerifyError as e:
            # 风控验证码 → 冷却后重试
            last_error = e
            if attempt < MAX_RETRIES:
                cooldown = COOLDOWN_BASE * (2 ** (attempt - 1))
                print(
                    json.dumps({
                        "_warning": True,
                        "attempt": attempt,
                        "max_retries": MAX_RETRIES,
                        "cooldown_seconds": cooldown,
                        "message": f"触发风控验证码，等待 {cooldown}s 后重试 ({attempt}/{MAX_RETRIES})",
                    }, ensure_ascii=False),
                    file=sys.stderr,
                )
                time.sleep(cooldown)
            continue
        except (IpBlockedError, SessionExpiredError) as e:
            # IP封锁 / 过期 → 不可恢复
            raise
        except XhsApiError as e:
            # API 错误 → 可重试
            last_error = e
            if attempt < MAX_RETRIES:
                time.sleep(5 * attempt)
            continue

    # 所有重试耗尽
    if isinstance(last_error, NeedVerifyError):
        error_out(
            "VERIFY_FAILED",
            f"评论获取失败：连续{MAX_RETRIES}次触发风控验证码。"
            f"建议在浏览器访问 xiaohongshu.com 完成验证后重试。",
            exit_code=1,
        )
    error_out(
        "API_ERROR",
        f"评论获取失败（已重试{MAX_RETRIES}次）: {last_error}",
        exit_code=1,
    )


# ── 输出工具函数 ──
def output_ok(data):
    """输出成功结果到 stdout"""
    envelope = {
        "ok": True,
        "schema_version": "1",
        "data": data,
    }
    json.dump(envelope, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    sys.stdout.flush()


def error_out(error_type, message, exit_code=1):
    """输出错误信息到 stderr 并退出"""
    envelope = {
        "ok": False,
        "error": {
            "type": error_type,
            "message": message,
        },
    }
    json.dump(envelope, sys.stderr, ensure_ascii=False)
    sys.stderr.write("\n")
    sys.stderr.flush()
    sys.exit(exit_code)


# ── CLI 入口 ──
def main():
    if len(sys.argv) < 3:
        error_out(
            "USAGE",
            f"用法: {sys.argv[0]} <note|comments> <note_id> [选项]\n"
            f"选项:\n"
            f"  --xsec-token TOKEN   安全令牌\n"
            f"  --xsec-source SOURCE 来源标识\n"
            f"  --max-pages N         最大翻页数(默认20)\n",
            exit_code=2,
        )

    command = sys.argv[1].lower()
    note_id = sys.argv[2]
    xsec_token = ""
    xsec_source = ""
    max_pages = 20

    # 解析可选参数
    i = 3
    while i < len(sys.argv):
        arg = sys.argv[i]
        if arg == "--xsec-token" and i + 1 < len(sys.argv):
            xsec_token = sys.argv[i + 1]
            i += 2
        elif arg == "--xsec-source" and i + 1 < len(sys.argv):
            xsec_source = sys.argv[i + 1]
            i += 2
        elif arg == "--max-pages" and i + 1 < len(sys.argv):
            max_pages = int(sys.argv[i + 1])
            i += 2
        else:
            i += 1

    # 创建客户端
    client = create_client()

    try:
        if command == "note":
            data = fetch_note(client, note_id, xsec_token, xsec_source)
            output_ok(data)

        elif command == "comments":
            data = fetch_all_comments(
                client, note_id, xsec_token, xsec_source, max_pages
            )
            output_ok(data)

        else:
            error_out(
                "UNKNOWN_COMMAND",
                f"未知命令: {command}，支持: note | comments",
                exit_code=2,
            )

    except NeedVerifyError as e:
        error_out("NEED_VERIFY", f"需要验证码: 请在浏览器完成验证后重试")
    except NoCookieError as e:
        error_out(
            "NO_COOKIE",
            f"未找到有效 Cookie。请运行: xhs login --qrcode 扫码登录",
        )
    except SessionExpiredError as e:
        error_out(
            "SESSION_EXPIRED",
            f"登录态过期。请运行: xhs login 刷新",
        )
    except IpBlockedError as e:
        error_out(
            "IP_BLOCKED",
            f"当前 IP 被小红书限制。请切换网络(WiFi/热点)后重试",
        )
    except Exception as e:
        error_out(
            "UNEXPECTED",
            f"未知错误({type(e).__name__}): {e}",
        )


if __name__ == "__main__":
    main()
