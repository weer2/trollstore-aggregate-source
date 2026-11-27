#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
就地修复已生成 source.json，不重新采集：
- 重新执行分类过滤（含 _全功能.ipa 等游戏条目）
- 为每条应用写入 versionDescription（巨魔增强版详情页实际读取字段）
- 统一格式：<网盘域名> | <软件功能描述>
- 同步 description / localizedDescription，兼容其它客户端
- 同步 _meta 与公告中的应用总数/剔除数

用法：python scripts/rebuild_descriptions.py
"""
from __future__ import annotations

import json
import os
import re
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from core.config import OUTPUT_DIR
from core.models import AppRecord
from core.filter import filter_apps


def build_desc(app: dict) -> str:
    body = app.get("description") or app.get("localizedDescription") or app.get("versionDescription") or ""
    body = re.sub(r"^来源：\s*[^\n]+\n?", "", body).strip()
    # 幂等：去掉已经写入的域名前缀（重复执行不会叠加）
    while True:
        cleaned = re.sub(r"^(?:[a-z0-9-]+\.)+[a-z]{2,}\s*\|\s*", "", body, flags=re.I).strip()
        if cleaned == body:
            break
        body = cleaned
    if not body:
        name = app.get("name", "")
        ver = app.get("version") or "1.0"
        body = f"{name} —— {ver} iOS 应用。"
    return f"{AppRecord._source_host(app.get('downloadURL', ''))} | {body}"


def main() -> None:
    path = os.path.join(OUTPUT_DIR, "source.json")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 1) 重新分类过滤（新增 _全功能.ipa 等游戏判据）
    removed_src: dict = {}
    for app in data.get("apps", []):
        if "全功能" in (app.get("name", "") + app.get("downloadURL", "")):
            k = app.get("developerName", "unknown")
            removed_src[k] = removed_src.get(k, 0) + 1
    apps, removed = filter_apps(data.get("apps", []))
    data["apps"] = apps
    print(f"分类过滤剔除 {removed} 条（其中全功能 {sum(removed_src.values())} 条）")

    # 2) 描述字段
    for app in apps:
        desc = build_desc(app)
        app["description"] = desc
        app["localizedDescription"] = desc
        app["versionDescription"] = desc

    # 3) 同步统计与公告
    meta = data.setdefault("_meta", {})
    meta["total_apps"] = len(apps)
    stats = meta.setdefault("stats", {})
    stats["excluded_by_category"] = int(stats.get("excluded_by_category", 0)) + removed
    # 来源分布按当前保留列表重新统计，避免显示去重前数字
    from collections import Counter
    by_source = dict(Counter(a.get("developerName", "unknown") for a in apps).most_common())
    stats["by_source"] = by_source
    meta.setdefault("filter", {})["excluded_by_category"] = stats["excluded_by_category"]
    meta["sources"] = by_source
    ts = __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    data["description"] = "\n".join([
        "🍎Leon聚合中文源 · 每日自动更新",
        f"📅 本次更新：{ts}",
        f"📦 应用总数：{len(apps)}",
        f"🚫 分类剔除 {stats['excluded_by_category']} 条（游戏/美化/越狱/电脑/安卓/证书/插件）",
        "📚 来源分布：" + "、".join(f"{k} {v}" for k, v in by_source.items()),
        "💡 应用描述格式：<网盘域名> | <软件功能描述>",
    ])

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))

    pretty = os.path.join(OUTPUT_DIR, "source_pretty.json")
    with open(pretty, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)

    size = os.path.getsize(path)
    print(f"已修复 {len(data.get('apps', []))} 条描述")
    print(f"source.json: {size} bytes ({size / 1024:.1f} KB)")
    print(json.dumps(data["apps"][0], ensure_ascii=False, indent=1)[:900])


if __name__ == "__main__":
    main()
