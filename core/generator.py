#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AltStore/SideStore 动态源生成器
输出增强版巨魔兼容的标准 JSON 源文件。
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from typing import List, Dict, Any

from .config import AppSettings, OUTPUT_DIR
from .models import AppRecord


class SourceGenerator:
    """生成 AltStore 格式动态源"""

    # 订阅源硬性上限：留足余量，保证 pretty 版也小于 1MB
    MAX_BYTES = 850_000

    def __init__(self, settings: AppSettings):
        self.settings = settings

    @staticmethod
    def _dump_size(source: Dict[str, Any]) -> int:
        return len(json.dumps(source, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))

    def _ensure_size(self, source: Dict[str, Any]) -> Dict[str, Any]:
        """超过上限时按已排序的日期倒序截断，保留最新应用。"""
        if self._dump_size(source) <= self.MAX_BYTES:
            return source
        apps = source["apps"]
        lo, hi = 0, len(apps)
        while lo < hi:
            mid = (lo + hi + 1) // 2
            source["apps"] = apps[:mid]
            if self._dump_size(source) <= self.MAX_BYTES:
                lo = mid
            else:
                hi = mid - 1
        source["apps"] = apps[:lo]
        source["_meta"]["total_apps"] = lo
        source["_meta"]["size_limited"] = True
        lines = source.get("description", "").split("\n")
        for i, line in enumerate(lines):
            if line.startswith("📦 应用总数："):
                lines[i] = f"📦 应用总数：{lo}（体积上限保护）"
        source["description"] = "\n".join(lines)
        return source

    def build_source(self, apps: List[AppRecord], stats: dict = None,
                     changes: Any = None) -> Dict[str, Any]:
        """构建完整源 JSON。"""
        app_objs = [a.to_altstore_app(self.settings) for a in apps]

        # 公告信息：写入统计与更新时间
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        msg_lines = [
            "🍎 聚合中文源 · 每日自动更新",
            f"📅 本次更新：{ts}",
            f"📦 应用总数：{len(apps)}",
        ]
        if stats:
            msg_lines.append(f"🔄 去重：{stats.get('before', 0)} → {stats.get('after', 0)}（去除重复 {stats.get('duplicates_removed', 0)}）")
            by_src = stats.get("by_source", {})
            if by_src:
                msg_lines.append("📚 来源分布：" + "、".join(f"{k} {v}" for k, v in by_src.items()))
        if changes:
            msg_lines.append(f"✨ 变更：新增 {len(changes.added)} / 移除 {len(changes.removed)} / 更新 {len(changes.updated)}")
        if stats and stats.get("excluded_by_category"):
            msg_lines.append(f"🚫 分类剔除 {stats['excluded_by_category']} 条（游戏/美化/越狱/电脑/安卓/证书/插件）")
        msg_lines.append("💡 重复软件以宅哥 zgios 源为准；点击应用选版本安装。")

        source = {
            "name": self.settings.source_name,
            "identifier": self.settings.source_identifier,
            "subtitle": self.settings.source_subtitle,
            "description": "\n".join(msg_lines),
            "website": self.settings.source_website,
            "iconURL": self.settings.source_icon,
            "sourceURL": "https://raw.githubusercontent.com/weer2/trollstore-aggregate-source/refs/heads/main/output/source.json",
            "apps": app_objs,
            "_meta": {
                "generated_at": ts,
                "total_apps": len(apps),
                "stats": stats or {},
                "changes": {
                    "added": len(changes.added) if changes else 0,
                    "removed": len(changes.removed) if changes else 0,
                    "updated": len(changes.updated) if changes else 0,
                } if changes else {},
                "sources": (stats or {}).get("by_source", {}),
                "filter": {
                    "excluded_by_category": (stats or {}).get("excluded_by_category", 0),
                    "categories": ["游戏", "美化", "越狱", "电脑", "安卓", "证书/签名", "插件"],
                },
            },
        }
        return self._ensure_size(source)

    def save(self, source: Dict[str, Any], filename: str = "source.json") -> str:
        """保存源文件到 output 目录。"""
        path = os.path.join(OUTPUT_DIR, filename)
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(source, f, ensure_ascii=False, separators=(",", ":"))
        return path

    def save_pretty(self, source: Dict[str, Any], filename: str = "source_pretty.json") -> str:
        """保存美化版（便于查看）。"""
        path = os.path.join(OUTPUT_DIR, filename)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(source, f, ensure_ascii=False, indent=1)
        return path
