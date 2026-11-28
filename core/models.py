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
    all_sources: List[str] = field(default_factory=list)  # 去重合并后命中的全部网盘源 Key
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
    def _source_host(url: str) -> str:
        """从下载直链提取网盘域名，如 lm.zgios.top / gfm.zgios.cn。"""
        from urllib.parse import urlparse
        try:
            host = urlparse(url or "").netloc
            if not host:
                m = re.match(r"https?://([^/?#]+)", url or "", re.I)
                host = m.group(1) if m else ""
            host = host.split("@")[-1].split(":")[0].strip()
            return host or "aggregate"
        except Exception:
            return "aggregate"

    # 伪描述模板：无真实介绍时不再生成这类占位文案
    _FAKE_DESC = re.compile(
        r"来自\s*\w+\s*的\s*iOS\s*应用|——\s*[\d.]+\s*iOS\s*应用|iOS\s*应用。",
        re.I,
    )

    @classmethod
    def build_description(cls, sources: List[str], intro: str = "") -> str:
        """描述格式：<源Key>[ | <源Key>...][ | <软件介绍>]。

        - 有真实介绍：gfm | 微信——腾讯出品…
        - 无真实介绍：zgios | lewsky | qlam（只列来源，绝不写占位文案）
        """
        keys = list(dict.fromkeys([s.strip() for s in (sources or []) if s and s.strip()]))
        if not keys:
            keys = ["aggregate"]
        body = re.sub(r"^来源：\s*[^\n]+\n?", "", intro or "").strip()
        body = re.sub(r"\s*·\s*另见于.*$", "", body).strip()
        if cls._FAKE_DESC.search(body):
            body = ""
        prefix = " | ".join(keys)
        return f"{prefix} | {body}" if body else prefix

    def to_altstore_app(self, settings) -> Dict[str, Any]:
        """转换为巨魔增强版 IPA 源 App 对象（与 ipa.312752.cn/appstore 同构）。

        客户端 TSIPAPackage 实际读取：name / bundleIdentifier / version /
        versionDescription / downloadURL / iconURL / size / lock。
        不输出 versions[]：客户端不读取该字段，且会显著增大源文件。
        """
        srcs = list(dict.fromkeys(
            self.all_sources or ([self.source_key] if self.source_key else [])
        ))
        desc = self.build_description(srcs, self.description)

        # bundle id：优先真实 id，否则用规范化名的 ASCII 部分；全中文名用指纹哈希兜底
        if self.bundle_id:
            bid = self.bundle_id
        else:
            ascii_part = re.sub(r"[^a-z0-9]", "", normalize_app_name(self.name))[:32]
            suffix = ascii_part if len(ascii_part) >= 4 else hashlib.md5(self.name.encode("utf-8")).hexdigest()[:12]
            bid = f"cn.aggregate.{suffix}"

        return {
            "name": re.sub(r"\.ipa$", "", self.name, flags=re.I),
            "type": 0,
            "bundleIdentifier": bid,
            "developerName": srcs[0],
            # 增强版详情页首选 versionDescription，其次 description
            "versionDescription": desc,
            "description": desc,
            "localizedDescription": desc,
            "version": self.version or "1.0",
            "versionDate": self.modified or "",
            "downloadURL": self.download_url,
            "iconURL": self.icon_url,
            # size 必须是数值：客户端按 NSNumber 读取后展示大小
            "size": int(self.size or 0),
            "lock": "0",
            "isLanZouCloud": "0",
            "tintColor": "",
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
