#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一数据模型
定义跨所有数据源的标准化 App 记录，以及变更检测结果。
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional


def fingerprint(name: str, bundle_id: str = "") -> str:
    """
    生成应用去重指纹。
    优先用 bundleIdentifier（最准确），否则用规范化文件名。
    """
    if bundle_id:
        return "bid:" + bundle_id.strip().lower()
    norm = normalize_app_name(name)
    return "name:" + hashlib.md5(norm.encode("utf-8")).hexdigest()


def normalize_app_name(name: str) -> str:
    """规范化应用名：去版本号/符号/空格，用于名称去重与匹配。"""
    s = name or ""
    s = re.sub(r"\.ipa$", "", s, flags=re.I)
    s = re.sub(r"[_\-]?v?\d+(\.\d+){0,4}.*$", "", s)   # 去版本号及之后
    s = re.sub(r"[@#].*$", "", s)                       # 去 @bundleid / 注释
    s = re.sub(r"[（(].*?[)）]", "", s)                  # 去括号内容
    s = re.sub(r"[\s\u200b\u200e\u200f]+", "", s)       # 去空白和零宽字符
    s = s.lower()
    return s


@dataclass
class AppRecord:
    """标准化 IPA 应用记录"""
    name: str                       # 显示名（保留中文）
    download_url: str               # 真实 IPA 直链
    size: int = 0                   # 字节
    source_key: str = ""            # 来源标识
    source_name: str = ""           # 来源显示名
    source_priority: int = 99       # 去重优先级
    modified: str = ""              # 更新日期（ISO）
    created: str = ""               # 创建日期
    bundle_id: str = ""             # bundleIdentifier（若有）
    version: str = ""               # 版本号（从文件名推断）
    description: str = ""           # 应用描述
    icon_url: str = ""              # 图标
    min_os: str = "14.0"            # 最低系统
    raw_path: str = ""              # 网盘原始路径
    fp: str = ""                    # 去重指纹

    def __post_init__(self):
        if not self.fp:
            self.fp = fingerprint(self.name, self.bundle_id)
        if not self.version:
            self.version = extract_version(self.name)
        if not self.bundle_id:
            self.bundle_id = extract_bundle_id(self.name)

    @staticmethod
    def _folder_from_url(url: str) -> str:
        """从下载 URL 反解网盘文件夹路径（不含文件名/域名）。"""
        from urllib.parse import urlparse, unquote
        try:
            path = unquote(urlparse(url).path)
        except Exception:
            return ""
        segs = [s for s in path.split("/") if s]
        # 去掉前导 'd'
        if segs and segs[0] == "d":
            segs = segs[1:]
        # 最后一段是文件名
        if segs:
            segs = segs[:-1]
        return "/".join(segs)

    @staticmethod
    def _short_source_label(url: str) -> str:
        """简短来源标签：域名/一级文件夹，如 ios.lewsky.top/iOS资源。"""
        from urllib.parse import urlparse, unquote
        try:
            u = urlparse(url)
            host = u.hostname or ""
            segs = [s for s in unquote(u.path).split("/") if s]
            if segs and segs[0] == "d":
                segs = segs[1:]
            if segs:
                segs = segs[:-1]  # 去掉文件名
            folder = segs[0] if segs else ""
            if host and folder:
                return f"{host}/{folder}"
            return host or folder
        except Exception:
            return ""

    def to_altstore_app(self, settings) -> Dict[str, Any]:
        """转换为 AltStore/SideStore 标准 App 对象（增强版巨魔兼容）。"""
        desc_parts = []
        if self.description:
            desc_parts.append(self.description)
        meta = []
        # 来源：简短格式「域名/一级文件夹」，避免描述过长
        short = self._short_source_label(self.download_url)
        if short:
            meta.append(f"来源：{short}")
        elif self.source_name:
            meta.append(f"来源：{self.source_name}")
        if self.size:
            meta.append(f"大小：{round(self.size/1024/1024, 1)} MB")
        if self.modified:
            meta.append(f"更新：{self.modified[:10]}")
        if meta:
            desc_parts.append(" · ".join(meta))
        localized = "\n".join(desc_parts) or f"{self.name}，来自 {self.source_name}。"

        # bundle id：优先真实 id，否则用规范化名的 ASCII 部分；全中文名用指纹哈希兜底
        if self.bundle_id:
            bid = self.bundle_id
        else:
            ascii_part = re.sub(r"[^a-z0-9]", "", normalize_app_name(self.name))[:32]
            suffix = ascii_part if len(ascii_part) >= 4 else hashlib.md5(self.name.encode("utf-8")).hexdigest()[:12]
            bid = f"cn.aggregate.{suffix}"

        return {
            "name": self.name,
            "bundleIdentifier": bid,
            "developerName": self.source_name or "聚合源",
            "subtitle": f"{self.version} · {round(self.size/1024/1024, 1) if self.size else '?'} MB",
            "localizedDescription": localized,
            "iconURL": self.icon_url,
            "size": self.size,
            "version": self.version or "1.0",
            "versionDate": self.modified or None,
            "downloadURL": self.download_url,
            "minOSVersion": self.min_os,
            # versions 只保留必要字段：描述/最低系统在顶层已有，避免源文件超过 1MB
            "versions": [{
                "version": self.version or "1.0",
                "date": self.modified or None,
                "size": self.size,
                "downloadURL": self.download_url,
            }],
        }


def extract_version(name: str) -> str:
    """从文件名提取版本号，如 微信_8.0.78.ipa -> 8.0.78"""
    m = re.search(r"[_ ]v?(\d+(?:\.\d+){1,4})", name or "", re.I)
    if m:
        return m.group(1)
    m = re.search(r"v?(\d+(?:\.\d+){1,4})", name or "")
    return m.group(1) if m else "1.0"


def extract_bundle_id(name: str) -> str:
    """从文件名提取 @com.xxx 形式的 bundle id"""
    m = re.search(r"@([a-zA-Z][\w.]+)", name or "")
    return m.group(1) if m else ""


@dataclass
class ChangeSet:
    """每日变更检测结果"""
    added: List[AppRecord] = field(default_factory=list)
    removed: List[AppRecord] = field(default_factory=list)
    updated: List[AppRecord] = field(default_factory=list)
    timestamp: str = ""

    def summary(self) -> str:
        return (f"新增 {len(self.added)} / 移除 {len(self.removed)} / 更新 {len(self.updated)}")
