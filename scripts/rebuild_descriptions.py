#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
就地重建已生成 source.json（不重新采集）：
- App 对象按增强版 Mach-O 反汇编结果精简（TSIPAPackage 解析簇）
- 删除 isLanZouCloud（二进制零引用）/ localizedDescription / tintColor / versions[]
- App 对象精简为 7 字段（去掉 identifier/developerName/description/
  versionDate/lock/type）
- 指纹含版本号：同名同版本只留一个，同名不同版本各自保留
- 去重择优按源顺序：zgios → lewsky → iosi → qlam → 其余
- 排序按该软件在全部网盘中的最新更新日期降序
- 描述格式：<源Key>·<日期> | <源Key>·<日期> / <真实介绍>
- 网盘 KEY 用域名主品牌简称：zgios / iosqh 等
- 源名 LEON🍎源，输出 leon.json 作为订阅路径

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

from core.config import OUTPUT_DIR, AppSettings, load_config, key_priority
from core.models import AppRecord
from core.enricher import AppEnricher
from core.filter import filter_apps
from core.merger import latest_date

_, settings = load_config()

DOMAIN_PREFIX = re.compile(r"^(?:(?:[a-z0-9-]+\.)+[a-z]{2,}|aggregate)\s*\|\s*", re.I)

# 旧 KEY -> 域名主品牌简称（用户约定：网盘 KEY 一律用域名主品牌）
KEY_ALIAS = {
    "gfm": "zgios",
    "qinghai": "iosqh",
}
def norm_key(k: str) -> str:
    k = (k or "").strip()
    return KEY_ALIAS.get(k.lower(), k)


def old_text(app: dict) -> str:
    return (app.get("versionDescription") or app.get("description")
            or app.get("localizedDescription") or "").strip()


_KEY_DATE = re.compile(r"^([A-Za-z][\w.-]*)(?:[·•]\s*(\d{4}[-/.]\d{1,2}[-/.]\d{1,2}))?$")


def parse_old_description(text: str):
    """解析 '<key>·<date> | <key>·<date> / <介绍>'。

    返回 (keys, dates, intro)。兼容单源无介绍、旧「另见于」文案。
    """
    text = re.sub(r"^来源：\s*[^\n]+\n?", "", (text or "").strip()).strip()
    keys, dates = [], {}
    head, sep, intro = text.partition(" / ")
    if not sep:
        head, intro = text, ""
    for seg in [s.strip() for s in head.split("|") if s.strip()]:
        m = _KEY_DATE.match(seg)
        if m:
            k = norm_key(m.group(1))
            if k:
                keys.append(k)
                if m.group(2):
                    dates[k] = m.group(2)
        else:
            intro = f"{seg} / {intro}".strip(" /") if intro else seg
    m = re.search(r"另见于\s*([^\n]+)", intro)
    if m:
        for k in re.split(r"[、,，\s]+", m.group(1)):
            if k.strip():
                keys.append(norm_key(k.strip()))
        intro = re.sub(r"\s*·?\s*另见于.*$", "", intro).strip()
    return list(dict.fromkeys(keys)), dates, intro.strip()


def extract_sources(app: dict) -> list:
    """从旧描述与 developerName 还原全部网盘源 Key（已转新简称）。"""
    keys, _, _ = parse_old_description(old_text(app))
    if not keys:
        keys = [norm_key(app.get("developerName", ""))]
    return keys


def extract_intro(app: dict, enricher: AppEnricher) -> str:
    """优先保留旧描述中的真实介绍，否则查内置词典；都没有则留空。"""
    _, _, intro = parse_old_description(old_text(app))
    if intro and not AppRecord._FAKE_DESC.search(intro):
        return intro
    return enricher.lookup_description(app.get("name", "")) or ""


def convert(app: dict, enricher: AppEnricher) -> AppRecord:
    srcs = extract_sources(app)
    _, source_dates, intro = parse_old_description(old_text(app))
    return AppRecord(
        name=app.get("name", ""),
        download_url=app.get("downloadURL", ""),
        size=int(app.get("size") or 0),
        source_key=srcs[0] if srcs else "aggregate",
        bundle_id=app.get("bundleIdentifier", "") or app.get("identifier", ""),
        version=app.get("version", ""),
        description=intro,
        icon_url=app.get("iconURL", ""),
        modified=app.get("versionDate", ""),
        all_sources=srcs,
        source_dates=source_dates,
    )


def dedup_and_sort(records: list):
    """同名同版本只留一个（按源顺序择优），再按最新网盘日期降序。"""
    from collections import defaultdict as _dd
    groups = _dd(list)
    for r in records:
        groups[r.fp].append(r)
    kept = []
    for fp, group in groups.items():
        group.sort(key=lambda a: (key_priority(a.source_key), -a.size, -bool(a.modified)))
        best = group[0]
        best.all_sources = list(dict.fromkeys(
            s for g in group for s in (g.all_sources or [g.source_key]) if s
        ))
        dates = {}
        for g in group:
            dates.update(g.source_dates or {})
            if g.source_key and g.modified:
                dates.setdefault(g.source_key, g.modified)
        best.source_dates = dates
        kept.append(best)
    kept.sort(key=lambda a: (latest_date(a), a.name), reverse=True)
    return kept, len(records) - len(kept)


def main() -> None:
    path = os.path.join(OUTPUT_DIR, "source.json")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    raw, removed = filter_apps(data.get("apps", []))
    enricher = AppEnricher(enabled=True)
    records = [convert(a, enricher) for a in raw]
    records, dup_removed = dedup_and_sort(records)
    apps = [r.to_altstore_app(settings) for r in records]

    by_source = Counter()
    for app in apps:
        # 字段精简后无 developerName，从版本描述前缀取主源 Key
        keys, _, _ = parse_old_description(app.get("versionDescription", ""))
        by_source[keys[0] if keys else "unknown"] += 1

    meta = data.setdefault("_meta", {})
    meta["total_apps"] = len(apps)
    stats = meta.setdefault("stats", {})
    stats["excluded_by_category"] = int(stats.get("excluded_by_category", 0)) + removed
    stats["duplicates_removed"] = stats.get("duplicates_removed", 0) + dup_removed
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
        "💡 描述格式：<源Key>·<日期> | <源Key>·<日期> / <软件介绍>；按最新网盘日期排序",
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
