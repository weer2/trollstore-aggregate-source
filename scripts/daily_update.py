#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
每日更新主入口（GitHub Actions 定时调用）
流程：公开API直采（免密码）→ 多站采集 → 描述增强 → 智能去重 → 变更检测 → 生成源 → 写历史

用法：
    python scripts/daily_update.py
    python scripts/daily_update.py --fetch-passwords  # 可选：强制重抓密码
"""
from __future__ import annotations

import os
import sys
import json
import argparse
import subprocess
from datetime import datetime

# 保证可导入 core 包
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from core.config import load_config, load_passwords, DATA_DIR, OUTPUT_DIR
from core.models import AppRecord
from core.scraper import MultiSiteCollector
from core.merger import AppMerger, ChangeDetector
from core.enricher import AppEnricher, load_custom_descriptions
from core.generator import SourceGenerator
from core.filter import filter_apps
from core.icon_enricher import IconEnricher


def refresh_passwords() -> bool:
    """调用密码抓取脚本更新 passwords.json。"""
    fetcher = os.path.join(BASE_DIR, "core", "password_fetcher.py")
    if not os.path.exists(fetcher):
        print("  ⚠ 密码抓取脚本不存在，跳过")
        return False
    try:
        # 复制脚本到 data 目录运行（其输出路径指向那里）
        result = subprocess.run(
            [sys.executable, fetcher],
            capture_output=True, text=True, timeout=180,
            cwd=DATA_DIR,
        )
        ok = "已写入" in result.stdout or result.returncode == 0
        print(f"  {'✓' if ok else '⚠'} 密码抓取: {result.stdout.strip()[:120] if ok else result.stderr.strip()[:120]}")
        return ok
    except Exception as e:
        print(f"  ⚠ 密码抓取异常: {e}")
        return False


def append_history(entry: dict):
    """追加更新历史到 history.json。"""
    path = os.path.join(DATA_DIR, "history.json")
    try:
        history = json.load(open(path, "r", encoding="utf-8")) if os.path.exists(path) else []
    except Exception:
        history = []
    history.insert(0, entry)
    history = history[:90]  # 保留最近 90 天
    with open(path, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser(description="巨魔聚合源每日更新")
    parser.add_argument("--fetch-passwords", action="store_true",
                        help="强制重新抓取前端密码（默认不需要：所有采集目录经 AList 公开 API 空密码可读）")
    args = parser.parse_args()

    print("=" * 64)
    print(f"🚀 巨魔聚合源每日更新 · {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 64)

    sources, settings = load_config()

    # 1. 密码（默认跳过：AList 公开目录 API 空密码即可列出，前端 PWD 仅为网站 UI 门禁）
    #    仅当显式 --fetch-passwords 或 settings.fetch_passwords=true 时才抓取
    if args.fetch_passwords or settings.fetch_passwords:
        print("\n[1/6] 抓取站点当前密码（可选）...")
        refresh_passwords()
    else:
        print("\n[1/6] 跳过密码抓取（公开 API 直采，无需前端密码）")
    passwords = load_passwords()
    print(f"  密码表: {len(passwords)} 个站点（仅用于 VIP 目录兜底）")

    # 2. 多站采集
    print(f"\n[2/6] 并发采集 {len(sources)} 站 IPA...")
    collector = MultiSiteCollector(sources, settings, passwords)
    raw_apps = collector.collect()
    print(f"  采集合计: {len(raw_apps)} 个 IPA")
    print("\n" + collector.report_table())

    if not raw_apps:
        print("\n❌ 未采集到任何应用，保留上一次源，终止。")
        sys.exit(1)

    # 3. 描述增强
    print("\n[3/6] 应用元数据增强...")
    custom_desc = load_custom_descriptions(os.path.join(DATA_DIR, "custom_descriptions.json"))
    enricher = AppEnricher(custom_desc=custom_desc, enabled=settings.gen_description)
    enriched = enricher.enrich_all(raw_apps)
    print(f"  已增强 {len(enriched)} 条描述")

    # 4. 分类过滤前置：先剔除游戏等条目再去重，避免游戏版占用主源导致
    #    同一 app 的非游戏版本被连带剔除
    print("\n[4/7] 分类过滤（前置，游戏/美化/越狱/电脑/安卓/证书/插件）...")
    enriched, excluded = filter_apps(enriched)
    print(f"  剔除 {excluded} 条，保留 {len(enriched)} 条")

    # 5. 智能去重（宅哥优先）
    print("\n[5/7] 智能去重（宅哥 zgios 优先）...")
    merged, stats = AppMerger.deduplicate(enriched, settings)
    stats["excluded_by_category"] = excluded
    print(f"  去重: {stats['before']} → {stats['after']}（移除重复 {stats['duplicates_removed']}）")
    print(f"  来源分布: {stats['by_source']}")

    # 5.5 图标与简介联网增强（参考源映射 + iTunes 缓存，串行低频）
    print("\n[5.5/7] 图标与简介增强...")
    try:
        enricher_icon = IconEnricher(offline=False)
        merged = enricher_icon.enrich_records(merged)
        print(f"  图标/简介: {enricher_icon.stats}")
    except Exception as e:
        print(f"  ⚠ 图标增强跳过: {type(e).__name__} {str(e)[:80]}")

    # 6. 变更检测
    print("\n[6/7] 变更检测...")
    detector = ChangeDetector()
    changes = detector.detect(merged)
    print(f"  {changes.summary()}")

    # 7. 生成源
    print("\n[7/7] 生成 AltStore 动态源...")
    gen = SourceGenerator(settings)
    source = gen.build_source(merged, stats, changes)
    compact = gen.save(source, "source.json")
    # 新订阅路径：换文件名即换缓存键，彻底绕开客户端旧 ETag + .ipasource_pkg_cache
    live = gen.save(source, "leon.json")
    pretty = gen.save_pretty(source, "source_pretty.json")
    size_kb = round(os.path.getsize(compact) / 1024)
    print(f"  ✓ {compact} ({size_kb} KB)")
    print(f"  ✓ {live}")
    print(f"  ✓ {pretty}")

    # 保存快照
    detector.save_snapshot(merged)

    # 写历史
    append_history({
        "timestamp": changes.timestamp,
        "total": len(merged),
        "added": len(changes.added),
        "removed": len(changes.removed),
        "updated": len(changes.updated),
        "duplicates_removed": stats["duplicates_removed"],
        "excluded_by_category": excluded,
        "by_source": stats["by_source"],
        "site_report": collector.report,
        "size_kb": size_kb,
    })

    print("\n" + "=" * 64)
    print(f"✅ 完成！共 {len(merged)} 个应用，源已生成到 output/source.json")
    print("=" * 64)


if __name__ == "__main__":
    main()
