#!/usr/bin/env python3
"""
小红书「大家补充了」Skill — 媒体资源提取脚本

功能：
1. 从 xiaohongshu-cli 的 JSON 输出中提取图片 URL 列表
2. 批量下载图片到指定目录
3. 生成图片索引文件供后续多模态处理使用

用法：
  python3 media_extractor.py --input <xhs_read_json_output> --output-dir <download_dir>
  python3 media_extractor.py --urls <url1,url2,url3> --output-dir <download_dir>
  python3 media_extractor.py --note-id <note_id> --images <image_list_json>

依赖：requests 或 curl（二选一）
"""

import argparse
import json
import os
import sys
import time
import subprocess
from pathlib import Path


def extract_image_urls_from_xhs_output(json_data: dict) -> list[dict]:
    """
    从 xhs read --json 的输出中提取图片信息。

    返回:
    [
        {
            "index": 0,
            "url_wb_prv": "高清预览版URL",
            "url_default": "默认版URL",
            "width": 1440,
            "height": 2400,
            "filename": "img_0.webp"
        },
        ...
    ]
    """
    items = json_data.get("data", {}).get("items", [])
    if not items:
        print("[!] 未找到笔记数据", file=sys.stderr)
        return []

    note_card = items[0].get("note_card", {})
    image_list = note_card.get("image_list", [])

    results = []
    for i, img in enumerate(image_list):
        # 提取 WB_PRV 高清版 URL
        wb_prv_url = ""
        default_url = img.get("url_default", "")

        info_list = img.get("info_list", [])
        for info in info_list:
            if info.get("image_scene") == "WB_PRV":
                wb_prv_url = info.get("url", "")
                break

        # 如果没有 WB_PRV，回退到 url_pre 或 url_default
        if not wb_prv_url:
            wb_prv_url = img.get("url_pre", "") or default_url

        if not wb_prv_url and not default_url:
            continue

        results.append({
            "index": i,
            "url_wb_prv": wb_prv_url or default_url,
            "url_default": default_url or wb_prv_url,
            "width": img.get("width", 0),
            "height": img.get("height", 0),
            "filename": f"img_{i}.webp"
        })

    return results


def download_image(url: str, output_path: str, timeout: int = 10) -> bool:
    """
    下载单张图片。优先使用 curl，fallback 到 urllib。
    """
    try:
        # 使用 curl 下载（更可靠）
        result = subprocess.run(
            ["curl", "-sL", "--max-time", str(timeout), "-o", output_path, url],
            capture_output=True,
            text=True,
            timeout=timeout + 5
        )
        if result.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 100:
            return True
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    # Fallback: urllib
    try:
        import urllib.request
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
            if len(data) > 100:
                with open(output_path, "wb") as f:
                    f.write(data)
                return True
    except Exception as e:
        print(f"[!] urllib 下载失败: {e}", file=sys.stderr)

    return False


def batch_download(images: list[dict], output_dir: str, note_id: str = "") -> dict:
    """
    批量下载图片。

    返回:
    {
        "total": 10,
        "success": 8,
        "failed": 2,
        "files": ["/path/to/img_0.webp", ...],
        "failures": [{"index": 2, "reason": "404"}, ...]
    }
    """
    os.makedirs(output_dir, exist_ok=True)

    prefix = f"{note_id}_" if note_id else ""
    results = {"total": len(images), "success": 0, "failed": 0, "files": [], "failures": []}

    for img_info in images:
        idx = img_info["index"]
        filename = f"{prefix}img_{idx}.webp"
        output_path = os.path.join(output_dir, filename)

        url = img_info["url_wb_prv"]
        print(f"  [{idx+1}/{len(images)}] 下载 img_{idx}.webp ...", end=" ", flush=True)

        success = download_image(url, output_path)

        if success:
            size_kb = os.path.getsize(output_path) / 1024
            print(f"✅ ({size_kb:.0f}KB)")
            results["success"] += 1
            results["files"].append(output_path)
        else:
            print("❌ 失败")
            results["failed"] += 1
            results["failures"].append({"index": idx, "reason": "download_failed"})

        # 礼貌延迟（避免 CDN 限流）
        if idx < len(images) - 1:
            time.sleep(0.3)

    return results


def generate_index_file(output_dir: str, images: list[dict], download_results: dict, note_id: str = ""):
    """生成图片索引用 JSON 文件。"""
    index_data = {
        "note_id": note_id,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "images": [],
        "summary": download_results
    }

    for img_info in images:
        idx = img_info["index"]
        prefix = f"{note_id}_" if note_id else ""
        filename = f"{prefix}img_{idx}.webp"
        filepath = os.path.join(output_dir, filename)
        index_data["images"].append({
            **img_info,
            "local_path": filepath if os.path.exists(filepath) else None,
            "downloaded": os.path.exists(filepath)
        })

    index_path = os.path.join(output_dir, "index.json")
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index_data, f, ensure_ascii=False, indent=2)
    print(f"\n📄 索引文件: {index_path}")


def main():
    parser = argparse.ArgumentParser(description="小红书笔记媒体资源提取工具")
    parser.add_argument("--input", "-i", help="xhs read --json 输出的 JSON 文件路径")
    parser.add_argument("--urls", help="逗号分隔的图片 URL 列表")
    parser.add_argument("--note-id", help="笔记 ID（用于文件命名）")
    parser.add_argument("--images", help="image_list 的 JSON 字符串")
    parser.add_argument("--output-dir", "-o", default="/tmp/xhs_skill", help="输出目录（默认: /tmp/xhs_skill）")

    args = parser.parse_args()
    images = []

    if args.input:
        with open(args.input, "r", encoding="utf-8") as f:
            data = json.load(f)
        images = extract_image_urls_from_xhs_output(data)
    elif args.urls:
        for i, url in enumerate(args.urls.split(",")):
            images.append({
                "index": i,
                "url_wb_prv": url.strip(),
                "url_default": url.strip(),
                "width": 0,
                "height": 0,
                "filename": f"img_{i}.webp"
            })
    elif args.images:
        image_list = json.loads(args.images)
        images = extract_image_urls_from_xhs_output({"data": {"items": [{"note_card": {"image_list": image_list}}]}})
    else:
        parser.print_help()
        sys.exit(1)

    if not images:
        print("[!] 没有找到可下载的图片", file=sys.stderr)
        sys.exit(1)

    print(f"📷 发现 {len(images)} 张图片，开始下载到 {args.output_dir}/")

    download_results = batch_download(images, args.output_dir, args.note_id or "")

    generate_index_file(args.output_dir, images, download_results, args.note_id or "")

    print(f"\n✅ 完成: {download_results['success']}/{download_results['total']} 张成功下载")
    if download_results["failed"]:
        print(f"⚠️ {download_results['failed']} 张失败")


if __name__ == "__main__":
    main()
