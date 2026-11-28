#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
去重合并 + 变更检测引擎
- 指纹 = 软件标识 + 版本号：同名同版本只留一个，同名不同版本各自保留
- 重复项按用户指定源顺序择优：zgios → lewsky → iosi → qlam → 其余
- 排序键 = 该软件在全部网盘中的最新更新日期（非仅主源）
- 与上一轮快照对比，检测新增/移除/更新
"""
from __future__ import annotations

import json
import os
from collections import defaultdict
from typing import List, Dict, Any, Tuple

from .config import DATA_DIR, AppSettings, key_priority
from .models import AppRecord, ChangeSet


def latest_date(app: AppRecord) -> str:
    """该软件在所有网盘中的最新更新日期；无日期时回退 modified/created。

    source_dates 的值是各源原始日期（ISO 或 YYYY.MM.DD），取字符串最大值
    即可（两种格式内部各自的字典序均与时间序一致）。
    """
    dates = [d for d in (getattr(app, "source_dates", {}) or {}).values() if d]
    dates.append(app.modified or "")
    dates.append(app.created or "")
    return max(dates) if dates else ""


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
            # 按用户指定源顺序择优：zgios → lewsky → iosi → qlam → 其余
            group.sort(key=lambda a: (
                key_priority(a.source_key),
                -a.size,
                -bool(a.modified),
            ))
            best = group[0]
            # 合并来源信息：结构化保存全部源 Key，描述由 models 统一拼成
            # "<源Key> | <源Key> | <真实介绍>"，不再写入「另见于」占位文案。
            all_sources = list(dict.fromkeys(g.source_key for g in group if g.source_key))
            best.all_sources = all_sources or ([best.source_key] if best.source_key else [])
            # 聚合每个网盘自己的更新日期，供描述显示「源Key·日期」
            best.source_dates = {
                g.source_key: g.modified for g in group
                if g.source_key and g.modified
            }
            if len(group) > 1:
                dup_count += len(group) - 1
            merged.append(best)
            sources_used[best.source_key] += 1

        # 单站贡献上限：某站翻页修复后可能暴涨（如 qlam 8407），
        # 若不限制会在体积截断时挤掉其他站。保留每个站最新的 N 个。
        per_source_cap = 1200
        by_src: Dict[str, int] = defaultdict(int)
        capped: List[AppRecord] = []
        # 先按最新网盘日期降序，保证每站保留的是最新条目
        prelim = sorted(merged, key=lambda a: (latest_date(a), a.name), reverse=True)
        for a in prelim:
            key = a.source_key or "unknown"
            if by_src[key] >= per_source_cap:
                continue
            by_src[key] += 1
            capped.append(a)
        merged = capped

        # 排序：按该软件在全部网盘中的最新更新日期降序（最新在前）
        if getattr(settings, "sort_by_date", True):
            merged.sort(key=lambda a: (latest_date(a), a.name), reverse=True)
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
