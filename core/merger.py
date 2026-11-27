#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
去重合并 + 变更检测引擎
- 以指纹去重（bundle id 优先，其次规范化文件名）
- 重复项按 source_priority 取最优（宅哥 zgios = 1 最高）
- 与上一轮快照对比，检测新增/移除/更新
"""
from __future__ import annotations

import json
import os
from collections import defaultdict
from typing import List, Dict, Any, Tuple

from .config import DATA_DIR, AppSettings
from .models import AppRecord, ChangeSet


class AppMerger:
    """应用去重合并器"""

    @staticmethod
    def deduplicate(apps: List[AppRecord], settings: AppSettings) -> Tuple[List[AppRecord], dict]:
        """
        去重：同一指纹只保留优先级最高（数字最小）的记录。
        返回 (去重后列表, 统计信息)
        """
        groups: Dict[str, List[AppRecord]] = defaultdict(list)
        for a in apps:
            groups[a.fp].append(a)

        merged: List[AppRecord] = []
        dup_count = 0
        sources_used = defaultdict(int)

        for fp, group in groups.items():
            # 按优先级排序，优先级相同取信息更全的（有大小、有日期）
            group.sort(key=lambda a: (
                a.source_priority,
                -a.size,
                -bool(a.modified),
            ))
            best = group[0]
            # 合并来源信息：若多个源都有，标注全部来源
            if len(group) > 1:
                dup_count += len(group) - 1
                all_sources = list(dict.fromkeys(g.source_key for g in group if g.source_key))
                # 以主源为准，但保留"另见于"信息到描述
                extra = all_sources[1:] if len(all_sources) > 1 else []
                if extra:
                    best.description = (best.description + " · 另见于 " + "、".join(extra[:3])).strip(" ·")
            merged.append(best)
            sources_used[best.source_key] += 1

        # 排序：默认按更新日期降序（最新更新的软件排在最前）
        if getattr(settings, "sort_by_date", True):
            merged.sort(key=lambda a: (
                a.modified or a.created or "",   # ISO 日期字符串可直接比较
                a.name,
            ), reverse=True)
        else:
            merged.sort(key=lambda a: a.name)

        # 上限保护（防止源过大导致巨魔解析失败）
        if len(merged) > settings.max_apps:
            merged = merged[:settings.max_apps]

        stats = {
            "before": len(apps),
            "after": len(merged),
            "duplicates_removed": dup_count,
            "by_source": dict(sources_used),
        }
        return merged, stats


class ChangeDetector:
    """每日变更检测器"""

    def __init__(self, snapshot_path: str = None):
        self.snapshot_path = snapshot_path or os.path.join(DATA_DIR, "snapshot.json")

    def load_snapshot(self) -> Dict[str, dict]:
        if not os.path.exists(self.snapshot_path):
            return {}
        try:
            d = json.load(open(self.snapshot_path, "r", encoding="utf-8"))
            return d.get("apps", {})
        except Exception:
            return {}

    def save_snapshot(self, apps: List[AppRecord]):
        snap = {
            "apps": {a.fp: {
                "name": a.name,
                "download_url": a.download_url,
                "size": a.size,
                "modified": a.modified,
                "source_key": a.source_key,
            } for a in apps}
        }
        os.makedirs(os.path.dirname(self.snapshot_path), exist_ok=True)
        with open(self.snapshot_path, "w", encoding="utf-8") as f:
            json.dump(snap, f, ensure_ascii=False, indent=2)

    def detect(self, current: List[AppRecord]) -> ChangeSet:
        """对比快照，返回变更集。"""
        from datetime import datetime
        old = self.load_snapshot()
        new = {a.fp: a for a in current}

        cs = ChangeSet(timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        for fp, a in new.items():
            if fp not in old:
                cs.added.append(a)
            elif old[fp].get("download_url") != a.download_url or old[fp].get("size") != a.size:
                cs.updated.append(a)
        for fp, o in old.items():
            if fp not in new:
                # 从当前列表找不到，构造一个最小 AppRecord 表示移除
                cs.removed.append(AppRecord(
                    name=o.get("name", ""),
                    download_url=o.get("download_url", ""),
                    size=o.get("size", 0),
                    source_key=o.get("source_key", ""),
                ))
        return cs
