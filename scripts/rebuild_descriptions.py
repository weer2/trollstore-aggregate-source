#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
就地重建已生成 source.json（不重新采集）：
- App 对象改成与 ipa.312752.cn/appstore 同构的扁平结构
- 去掉 versions[]（客户端不读取）
- 描述格式：<源Key>[ | <源Key>...][ | <真实软件介绍>]
- 无真实介绍只列来源 Key，绝不生成「XX —— 来自 YY 的 iOS 应用」占位文案
- 保留 bundleIdentifier 与数值 size，保证标识符/大小正确显示
- 源名改为 LEON🍎源，输出 leon.json 作为全新订阅路径

用法：python scripts/rebuild_descriptions.py
"""
from __future__ import annotations

import json
import os
import re
import sys
from collections import Counter
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from core.config import OUTPUT_DIR, AppSettings, load_config
from core.models import AppRecord
from core.enricher import AppEnricher
from core.filter import filter_apps

_, settings = load_config()

DOMAIN_PREFIX = re.compile(r"^(?:(?:[a-z0-9-]+\.)+[a-z]{2,}|aggregate)\s*\|\s*", re.I)


def old_text(app: dict) -> str:
    return (app.get("versionDescription") or app.get("description")
            or app.get("localizedDescription") or "").strip()


def extract_sources(app: dict) -> list:
    """从 developerName 与旧「另见于」文案还原全部网盘源 Key。"""
    keys = [app.get("developerName", "")]
    text = old_text(app)
    m = re.search(r"另见于\s*([^\n]+)", text)
    if m:
        keys += [x.strip() for x in re.split(r"[、,，\s]+", m.group(1)) if x.strip()]
    return list(dict.fromkeys(k for k in keys if k))


def extract_intro(app: dict, enricher: AppEnricher) -> str:
    """优先保留旧描述中的真实介绍，否则查内置词典；都没有则留空。"""
    text = re.sub(r"^来源：\s*[^\n]+\n?", "", old_text(app)).strip()
    text = DOMAIN_PREFIX.sub("", text).strip()
    text = re.sub(r"\s*·\s*另见于.*$", "", text).strip()
    if text and not AppRecord._FAKE_DESC.search(text):
        return text
    return enricher.lookup_description(app.get("name", "")) or ""


def convert(app: dict, enricher: AppEnricher) -> dict:
    srcs = extract_sources(app)
    intro = extract_intro(app, enricher)
    record = AppRecord(
        name=app.get("name", ""),
        download_url=app.get("downloadURL", ""),
        size=int(app.get("size") or 0),
        source_key=srcs[0] if srcs else "aggregate",
        bundle_id=app.get("bundleIdentifier", ""),
        version=app.get("version", ""),
        description=intro,
        icon_url=app.get("iconURL", ""),
        modified=app.get("versionDate", ""),
        all_sources=srcs,
    )
    return record.to_altstore_app(settings)


def main() -> None:
    path = os.path.join(OUTPUT_DIR, "source.json")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    apps, removed = filter_apps(data.get("apps", []))
    enricher = AppEnricher(enabled=True)
    apps = [convert(a, enricher) for a in apps]

    by_source = Counter()
    for app in apps:
        # 来源分布按主源统计
        by_source[app.get("developerName", "unknown")] += 1

    meta = data.setdefault("_meta", {})
    meta["total_apps"] = len(apps)
    stats = meta.setdefault("stats", {})
    stats["excluded_by_category"] = int(stats.get("excluded_by_category", 0)) + removed
    stats["by_source"] = dict(by_source.most_common())
    meta["sources"] = stats["by_source"]
    meta["filter"] = {
        "excluded_by_category": stats["excluded_by_category"],
        "categories": ["游戏", "美化", "越狱", "电脑", "安卓", "证书/签名", "插件"],
    }

    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    msg = "\n".join([
        f"{settings.source_name} · 每日自动更新",
        f"📅 本次更新：{ts}",
        f"📦 应用总数：{len(apps)}",
        f"🚫 分类剔除 {stats['excluded_by_category']} 条（游戏/美化/越狱/电脑/安卓/证书/插件）",
        "📚 来源分布：" + "、".join(f"{k} {v}" for k, v in stats["by_source"].items()),
        "💡 应用描述格式：<源Key> | <软件介绍>（无介绍时仅列来源 Key）",
    ])

    data["name"] = settings.source_name
    data["identifier"] = settings.source_identifier
    data["subtitle"] = settings.source_subtitle
    data["message"] = msg
    data["description"] = msg
    data["website"] = settings.source_website
    data["sourceicon"] = settings.source_icon
    data["iconURL"] = settings.source_icon
    data["sourceURL"] = "https://raw.githubusercontent.com/weer2/trollstore-aggregate-source/refs/heads/main/output/leon.json"
    data["apps"] = apps

    # 体积硬上限：按已有日期倒序截断，保证 <1MB
    compact_size = lambda: len(json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    if compact_size() > 850_000:
        lo, hi = 0, len(apps)
        while lo < hi:
            mid = (lo + hi + 1) // 2
            data["apps"] = apps[:mid]
            if compact_size() <= 850_000:
                lo = mid
            else:
                hi = mid - 1
        data["apps"] = apps[:lo]
        meta["total_apps"] = lo
        meta["size_limited"] = True
        msg = msg.replace(f"📦 应用总数：{len(apps)}", f"📦 应用总数：{lo}（体积上限保护）")
        data["message"] = data["description"] = msg
        print(f"体积保护：截断到 {lo} 条")

    for name in ("source.json", "leon.json"):
        with open(os.path.join(OUTPUT_DIR, name), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    with open(os.path.join(OUTPUT_DIR, "source_pretty.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)

    size = os.path.getsize(path)
    print(f"分类过滤剔除 {removed} 条；重建 {len(data['apps'])} 条")
    print(f"source.json / leon.json: {size} bytes ({size / 1024:.1f} KB)")
    print("样例:", json.dumps(data["apps"][0], ensure_ascii=False)[:400])


if __name__ == "__main__":
    main()
