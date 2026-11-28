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
    source_dates: Dict[str, str] = field(default_factory=dict)  # 源Key -> 该网盘更新日期(YYYY.MM.DD)
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

    @staticmethod
    def _fmt_date(value: str) -> str:
        """把 ISO 日期转成 YYYY.MM.DD；无效返回空串。"""
        m = re.search(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", value or "")
        return f"{m.group(1)}.{int(m.group(2)):02d}.{int(m.group(3)):02d}" if m else ""

    @classmethod
    def build_description(cls, sources: List[str], intro: str = "",
                          source_dates: Optional[Dict[str, str]] = None) -> str:
        """描述格式：<源Key>·<日期> | <源Key>·<日期> / <软件介绍>。

        - 有真实介绍：gfm·2026.11.28 | lewsky·2026.11.27 / 微信——腾讯出品…
        - 无真实介绍：qlam·2026.11.29（仅列来源与日期）
        无日期的来源只写 Key；绝不生成「XX 来自 YY 的 iOS 应用」占位文案。
        """
        keys = list(dict.fromkeys([s.strip() for s in (sources or []) if s and s.strip()]))
        if not keys:
            keys = ["aggregate"]
        dates = source_dates or {}
        parts = []
        for k in keys:
            d = cls._fmt_date(dates.get(k, ""))
            parts.append(f"{k}·{d}" if d else k)
        prefix = " | ".join(parts)
        body = re.sub(r"^来源：\s*[^\n]+\n?", "", intro or "").strip()
        body = re.sub(r"\s*·\s*另见于.*$", "", body).strip()
        if cls._FAKE_DESC.search(body):
            body = ""
        return f"{prefix} / {body}" if body else prefix

    def to_altstore_app(self, settings) -> Dict[str, Any]:
        """转换为巨魔增强版 IPA 源 App 对象。

        依据增强版 Mach-O 反汇编，TSIPAPackage 解析 key 连续簇为：
            identifier / versionDescription / description /
            iconURL / downloadURL / size / lock
        另有 setBundleIdentifier: selector（iTunes 元数据区亦有该 key）。
        因此同时输出 identifier 与 bundleIdentifier（值相同），确保详情页
        「标识符」在任一读取路径下都能显示 —— 参考源恰好两者皆缺，这正是
        用户反馈「标识符不显示」的根因。

        已删除的冗余字段（反汇编证据）：
            isLanZouCloud —— 二进制内零引用（无该字符串）
            localizedDescription —— 不在解析簇内
            tintColor —— 仅 UI 着色，源数据给空串无意义
            versions[] —— 客户端不读取且显著增大体积
        保留 description 作为 versionDescription 的 fallback（解析簇内紧跟
        "No description available."），保留 lock（解析簇内）。

        size 必须是数值：客户端按 NSNumber 读取后展示大小；参考源给字符串
        "0" 导致大小不显示。
        """
        srcs = list(dict.fromkeys(
            self.all_sources or ([self.source_key] if self.source_key else [])
        ))
        desc = self.build_description(srcs, self.description, self.source_dates)

        # bundle id：优先真实 id，否则用规范化名的 ASCII 部分；全中文名用指纹哈希兜底
        if self.bundle_id:
            bid = self.bundle_id
        else:
            ascii_part = re.sub(r"[^a-z0-9]", "", normalize_app_name(self.name))[:32]
            suffix = ascii_part if len(ascii_part) >= 4 else hashlib.md5(self.name.encode("utf-8")).hexdigest()[:12]
            bid = f"cn.aggregate.{suffix}"

        app = {
            "name": re.sub(r"\.ipa$", "", self.name, flags=re.I),
            "type": 0,
            # identifier 是解析簇首位 key；bundleIdentifier 亦有 setter，两者同值
            "identifier": bid,
            "bundleIdentifier": bid,
            "developerName": srcs[0],
            # 增强版详情页首选 versionDescription，description 为 fallback
            "versionDescription": desc,
            "description": desc,
            "version": self.version or "1.0",
            "versionDate": self.modified or "",
            "downloadURL": self.download_url,
            "iconURL": self.icon_url,
            # size 必须是数值：客户端按 NSNumber 读取后展示大小
            "size": int(self.size or 0),
            "lock": "0",
        }
        return app


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
