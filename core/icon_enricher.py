#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
图标与简介联网增强器
- 主来源：参考源 ipa.312752.cn/appstore 的 iconURL/versionDescription 映射表（一次抓取）
- 补充：iTunes Search API（limit<=10，低频串行 + 永久缓存，规避 403 限流）
- 名称严格匹配防错配：核心名互含或相似度>=0.75 才采纳
- 结果缓存到 data/icon_meta_cache.json，重复执行零网络请求

用法：
    from core.icon_enricher import IconEnricher
    e = IconEnricher(offline=False)
    e.enrich(apps)   # apps: list[dict]，就地写 iconURL / _intro
"""
from __future__ import annotations

import json
import os
import re
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional

from .config import DATA_DIR

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Version/17.0 Mobile/15E148 Safari/604.1"

REF_SOURCE_URL = "https://ipa.312752.cn/appstore"
ITUNES_API = "https://itunes.apple.com/search"
REF_CACHE = os.path.join(DATA_DIR, "ref_source_cache.json")
META_CACHE = os.path.join(DATA_DIR, "icon_meta_cache.json")

_EMOJI = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F\u200d]")
_SUFFIX = re.compile(
    r"(管替|双指长按|要开魔法|无广告|内置版|破解版|汉化版|修改版|iOS\d+\+?|"
    r"标准版|正式版|国际版|海外版|测试版|免费版|专业版|会员版|纯净版|增强版|"
    r"稳定版|最新版|官方版|中文版|绿色版|解锁版|兼容版)"
)


def core_name(name: str) -> str:
    """提取用于匹配的核心应用名。"""
    if not isinstance(name, str):
        return ""
    s = re.sub(r"\.ipa$", "", name, flags=re.I)
    s = re.sub(r"[_\-]v?\d+(\.\d+){0,5}.*$", "", s)
    s = re.sub(r"[（(].*?[)）]", "", s)
    s = _EMOJI.sub("", s)
    s = _SUFFIX.sub("", s)
    s = re.sub(r"[_\s+]+.*$", "", s)   # 保留 - 供英文名使用
    return s.strip()[:24]


def short_intro(text: str, limit: int = 46) -> str:
    """把 iTunes 长简介压成一行短介绍。"""
    if not text:
        return ""
    s = re.sub(r"\s+", " ", str(text)).strip()
    # 取前两句/前 limit 字，遇到明显营销符号截断
    s = re.split(r"[●◆★■【]", s)[0].strip()
    if len(s) > limit:
        cut = s[:limit]
        p = max(cut.rfind("。"), cut.rfind("，"), cut.rfind(" "))
        s = cut[:p] if p >= limit // 2 else cut
    return s.rstrip("，,。 ")


class IconEnricher:
    def __init__(self, offline: bool = False, itunes_limit: int = 0):
        """
        offline=True：只用缓存与参考源，不发 iTunes 请求
        itunes_limit：本次最多新增多少个 iTunes 查询（0=不限，由 offline 控制）
        """
        self.offline = offline
        self.itunes_limit = itunes_limit
        self.ref_map: Dict[str, dict] = {}
        self.meta: Dict[str, dict] = {}
        self.stats = {"ref_exact": 0, "ref_fuzzy": 0, "itunes": 0, "cache": 0, "queries": 0, "blocked": 0}
        self._itunes_blocked = False   # 连续 403 触发熔断，后续全部走缓存
        self._load()

    # ---------- 缓存 ----------
    def _load(self) -> None:
        if os.path.exists(META_CACHE):
            try:
                self.meta = json.load(open(META_CACHE, "r", encoding="utf-8"))
            except Exception:
                self.meta = {}
        if os.path.exists(REF_CACHE):
            try:
                self.ref_map = json.load(open(REF_CACHE, "r", encoding="utf-8"))
                return
            except Exception:
                pass
        self._fetch_ref()

    def _save(self) -> None:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(META_CACHE, "w", encoding="utf-8") as f:
            json.dump(self.meta, f, ensure_ascii=False)
        with open(REF_CACHE, "w", encoding="utf-8") as f:
            json.dump(self.ref_map, f, ensure_ascii=False)

    def _fetch_ref(self) -> None:
        """抓参考源，建立核心名 -> {icon, intro} 映射。"""
        try:
            req = urllib.request.Request(REF_SOURCE_URL, headers={"User-Agent": UA})
            data = json.loads(urllib.request.urlopen(req, timeout=45, context=CTX).read())
            for a in data.get("apps", []):
                c = core_name(a.get("name", ""))
                if not c:
                    continue
                rec = self.ref_map.setdefault(c, {"icon": "", "intro": ""})
                if a.get("iconURL") and not rec["icon"]:
                    rec["icon"] = a["iconURL"]
                desc = (a.get("versionDescription") or a.get("description") or "").strip()
                # 参考源有真实介绍（非链接/联系方式）才采纳
                if desc and len(desc) >= 6 and not desc.startswith("http") and not rec["intro"]:
                    rec["intro"] = short_intro(desc)
        except Exception as e:
            print(f"  ⚠ 参考源抓取失败: {type(e).__name__} {str(e)[:80]}")
        self._save()

    # ---------- iTunes ----------
    def _itunes_query(self, term: str) -> Optional[dict]:
        """单次 iTunes 查询，limit<=10，返回匹配结果或 None。"""
        if term in self.meta:
            self.stats["cache"] += 1
            return self.meta[term] or None
        if self.offline or self._itunes_blocked:
            return None
        if self.itunes_limit and self.stats["queries"] >= self.itunes_limit:
            return None
        url = ITUNES_API + "?" + urllib.parse.urlencode(
            {"term": term, "entity": "software", "country": "cn", "limit": 10}
        )
        result = None
        for attempt in range(2):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": UA})
                resp = urllib.request.urlopen(req, timeout=12, context=CTX)
                data = json.loads(resp.read())
                best = None
                for x in data.get("results", []):
                    tn = (x.get("trackName") or "").strip()
                    tc = core_name(tn)
                    if len(tc) < 2:
                        continue
                    if tc == term:
                        score = 100
                    elif tc in term or term in tc:
                        score = 92
                    else:
                        score = round(SequenceMatcher(None, term.lower(), tc.lower()).ratio() * 100)
                    if score >= 85 and (best is None or score > best[0]):
                        best = (score, x)
                if best:
                    x = best[1]
                    result = {
                        "icon": x.get("artworkUrl512") or x.get("artworkUrl100") or "",
                        "intro": short_intro(x.get("description") or ""),
                        "matched": x.get("trackName", ""),
                    }
                break
            except urllib.error.HTTPError as he:
                if he.code in (403, 429):
                    # 出口 IP 被限流：熔断，后续所有查询直接走缓存
                    self._itunes_blocked = True
                    self.stats["blocked"] += 1
                    break
                if attempt == 0:
                    time.sleep(1.5)
            except Exception:
                if attempt == 0:
                    time.sleep(1.5)   # 触发错误后退避
        self.stats["queries"] += 1
        self.meta[term] = result       # None 也缓存，避免重复请求
        time.sleep(0.3)                # 串行低频，规避限流
        return result

    # ---------- 主入口 ----------
    def lookup(self, name: str) -> dict:
        c = core_name(name)
        if not c:
            return {}
        # 1) 参考源精确匹配
        if c in self.ref_map:
            self.stats["ref_exact"] += 1
            return self.ref_map[c]
        # 2) 参考源模糊匹配（长度接近 + 高相似度，防错配）
        best = None
        for k, v in self.ref_map.items():
            if abs(len(k) - len(c)) > 3 or len(k) < 2:
                continue
            r = SequenceMatcher(None, c.lower(), k.lower()).ratio()
            if r >= 0.86 and (best is None or r > best[0]):
                best = (r, v)
        if best:
            self.stats["ref_fuzzy"] += 1
            return best[1]
        # 3) iTunes 查询（仅对短核心名，降低无意义请求）
        if 2 <= len(c) <= 12:
            r = self._itunes_query(c)
            if r:
                self.stats["itunes"] += 1
                return r
        return {}

    def enrich_records(self, records: List[Any]) -> List[Any]:
        """就地增强 AppRecord 列表（dataclass），写入 icon_url / description。"""
        for rec in records:
            info = self.lookup(getattr(rec, "name", ""))
            if info.get("icon") and not getattr(rec, "icon_url", ""):
                rec.icon_url = info["icon"]
            if info.get("intro") and not getattr(rec, "description", ""):
                rec.description = info["intro"]
        self._save()
        return records

    def enrich(self, apps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        for a in apps:
            info = self.lookup(a.get("name", ""))
            if info.get("icon") and not a.get("iconURL"):
                a["iconURL"] = info["icon"]
            if info.get("intro"):
                a["_intro"] = info["intro"]
            elif a.get("versionDescription"):
                # 保留已有真实介绍
                text = a["versionDescription"]
                text = re.sub(r"^[^|]+\|\s*", "", text).strip()
                if text and len(text) >= 6 and not re.search(r"iOS\s*应用", text):
                    a["_intro"] = text
        self._save()
        return apps
