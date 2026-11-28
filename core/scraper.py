#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AList 采集引擎
- 递归扫描每个数据源的 IPA 目录
- 支持密码保护的目录（密码由 password_fetcher 动态获取）
- 并发请求、重试、限速
- 输出统一 AppRecord 列表
"""
from __future__ import annotations

import json
import ssl
import time
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any, Optional, Tuple

from .config import SourceConfig, AppSettings
from .models import AppRecord
from .filter import is_excluded_dir

CTX = ssl._create_unverified_context()
UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
      "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1")


class AListScraper:
    """单个 AList 站点采集器"""

    def __init__(self, source: SourceConfig, settings: AppSettings, password: str = "",
                 deadline: float = None):
        self.src = source
        self.settings = settings
        self.password = password
        self.base = source.base_url.rstrip("/")
        self.session_stats = {"api_calls": 0, "errors": 0, "files": 0}
        # 单站采集总时限（秒），防止深层目录里某个请求悬挂拖垮全局
        self.deadline = deadline if deadline else (time.time() + getattr(settings, "site_timeout", 90))

    def _post(self, endpoint: str, payload: dict, retry: int = 1) -> Optional[dict]:
        """POST AList JSON API，带重试和全局时限保护。"""
        if time.time() > self.deadline:
            return None
        url = self.base + endpoint
        body = json.dumps(payload).encode("utf-8")
        for attempt in range(retry + 1):
            try:
                req = urllib.request.Request(
                    url, data=body,
                    headers={"User-Agent": UA, "Content-Type": "application/json"},
                    method="POST",
                )
                # 单次超时取「配置的超时」与「剩余时限」的较小值
                remaining = self.deadline - time.time()
                if remaining <= 0:
                    return None
                req_timeout = max(1, min(self.settings.request_timeout, remaining))
                with urllib.request.urlopen(req, context=CTX, timeout=req_timeout) as r:
                    self.session_stats["api_calls"] += 1
                    return json.loads(r.read().decode("utf-8", errors="replace"))
            except urllib.error.HTTPError as he:
                # WAF 拦截（418/403/429/502）：本机出口 IP 被封，快速失败不重试
                if he.code in (418, 403, 429, 502, 503):
                    self.session_stats["errors"] += 1
                    self.session_stats.setdefault("waf_blocked", 0)
                    self.session_stats["waf_blocked"] += 1
                    return None
                if attempt >= retry or time.time() > self.deadline:
                    self.session_stats["errors"] += 1
                    return None
                time.sleep(0.3 * (attempt + 1))
            except Exception:
                if attempt >= retry or time.time() > self.deadline:
                    self.session_stats["errors"] += 1
                    return None
                time.sleep(0.3 * (attempt + 1))
        return None

    def list_dir(self, path: str) -> List[dict]:
        """列出目录全部内容（含密码），自动翻页 até 覆盖 >per_page 的目录。

        情海网盘 iOS资源专区等单目录文件数可能超过 500，旧版只取第一页，
        导致子目录与后半段 IPA 被漏采 —— 这是「抓取不全」的根因。
        """
        per = max(100, int(getattr(self.settings, "per_page", 500)))
        content: List[dict] = []
        page = 1
        max_pages = 40  # 单目录硬上限，防止异常总数导致死循环
        while page <= max_pages and time.time() <= self.deadline:
            resp = self._post("/api/fs/list", {
                "path": path,
                "password": self.password,
                "page": page,
                "per_page": per,
                "refresh": False,
            })
            if not resp or resp.get("code") != 200:
                break
            data = resp.get("data") or {}
            part = data.get("content", []) or []
            content.extend(part)
            # AList 返回 total；无 total 且返回不足一页即视为末页
            total = int(data.get("total") or 0)
            if not part or len(part) < per or (total and len(content) >= total):
                break
            page += 1
        return content

    def _need_sign(self) -> bool:
        """探测本站 /d/ 直链是否需要 AList 签名（site 级缓存结果）。"""
        if hasattr(self, "_need_sign_cached"):
            return self._need_sign_cached
        self._need_sign_cached = False
        # 用已知目录首个元素做探测：调用 /api/fs/get 看是否返回 sign
        try:
            probe_path = None
            for p in self.src.paths[:3]:
                items = self.list_dir(p)
                if items:
                    probe_path = p.rstrip("/") + "/" + items[0].get("name", "")
                    break
            if not probe_path:
                return False
            req = urllib.request.Request(
                self.base + "/api/fs/get",
                data=json.dumps({"path": probe_path, "password": self.password}).encode("utf-8"),
                headers={"User-Agent": UA, "Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, context=CTX, timeout=self.settings.request_timeout) as r:
                resp = json.loads(r.read().decode("utf-8", errors="replace"))
            sign = ((resp.get("data") or {}).get("sign") or "")
            self._need_sign_cached = bool(sign)
        except Exception:
            pass
        return self._need_sign_cached

    def build_download_url(self, raw_path: str) -> str:
        """构造 AList 下载直链：签名站从 /api/fs/get 取永久 sign 拼到 /d/。"""
        from urllib.parse import quote
        encoded = "/".join(quote(seg, safe="") for seg in raw_path.split("/") if seg)
        url = f"{self.base}/d/{encoded}"
        if not self._need_sign():
            return url
        # 需要签名：每个文件取 sign（形如 'xxx=:0'，':0' 表示永不过期）
        try:
            req = urllib.request.Request(
                self.base + "/api/fs/get",
                data=json.dumps({"path": raw_path, "password": self.password}).encode("utf-8"),
                headers={"User-Agent": UA, "Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, context=CTX, timeout=self.settings.request_timeout) as r:
                resp = json.loads(r.read().decode("utf-8", errors="replace"))
            sign = ((resp.get("data") or {}).get("sign") or "")
            if sign:
                url += "?sign=" + quote(sign, safe="")
        except Exception:
            self.session_stats["errors"] += 1
        return url

    def walk(self, path: str, depth: int = 0, seen: Optional[set] = None) -> List[AppRecord]:
        """递归遍历目录，收集 IPA 文件。"""
        if seen is None:
            seen = set()
        if path in seen or depth > self.src.max_depth or time.time() > self.deadline:
            return []
        seen.add(path)

        items = self.list_dir(path)
        results: List[AppRecord] = []
        # 采集阶段剪枝：游戏/越狱/插件目录整棵跳过，不进入递归
        items = [it for it in items
                 if not (it.get("is_dir") and is_excluded_dir(path.rstrip("/") + "/" + it.get("name", "")))]
        for item in items:
            if time.time() > self.deadline:
                break
            name = item.get("name", "")
            full_path = (path.rstrip("/") + "/" + name)
            if item.get("is_dir"):
                results.extend(self.walk(full_path, depth + 1, seen))
            elif name.lower().endswith(".ipa"):
                size = int(item.get("size") or 0)
                if size < self.settings.min_size_mb * 1024 * 1024:
                    continue
                if any(kw.lower() in name.lower() for kw in self.settings.skip_keywords):
                    continue
                results.append(AppRecord(
                    name=name,
                    download_url=self.build_download_url(full_path),
                    size=size,
                    source_key=self.src.key,
                    source_name=self.src.name,
                    source_priority=self.src.priority,
                    modified=item.get("modified", ""),
                    created=item.get("created", ""),
                    raw_path=full_path,
                ))
                self.session_stats["files"] += 1
        return results

    def scrape(self) -> List[AppRecord]:
        """采集该站所有配置路径（共享 seen，避免跨路径重复递归）。"""
        all_apps: List[AppRecord] = []
        seen: set = set()
        for p in self.src.paths:
            try:
                all_apps.extend(self.walk(p, depth=0, seen=seen))
            except Exception as e:
                self.session_stats["errors"] += 1
        return all_apps


class MultiSiteCollector:
    """多站点并发采集协调器"""

    def __init__(self, sources: List[SourceConfig], settings: AppSettings, passwords: dict):
        self.sources = [s for s in sources if s.enabled]
        self.settings = settings
        self.passwords = passwords
        self.report: List[dict] = []

    def _scrape_one(self, src: SourceConfig) -> Tuple[str, List[AppRecord], dict]:
        pwd = self.passwords.get(src.password_key, "") or src.password
        # 情海网盘三个目标目录层级深、文件多，单独放宽时限防止截断
        timeout = 180 if src.key == "iosqh" else None
        deadline = (time.time() + timeout) if timeout else None
        scraper = AListScraper(src, self.settings, password=pwd, deadline=deadline)
        apps = scraper.scrape()
        return src.key, apps, scraper.session_stats

    def collect(self) -> List[AppRecord]:
        """并发采集全部数据源。"""
        all_apps: List[AppRecord] = []
        with ThreadPoolExecutor(max_workers=self.settings.max_workers) as ex:
            futures = {ex.submit(self._scrape_one, s): s for s in self.sources}
            for fut in as_completed(futures):
                src = futures[fut]
                try:
                    key, apps, stats = fut.result()
                    self.report.append({
                        "key": key, "name": src.name, "priority": src.priority,
                        "count": len(apps), **stats,
                    })
                    all_apps.extend(apps)
                    print(f"  [{key}] {len(apps)} IPA (API {stats['api_calls']} 次, 错误 {stats['errors']})")
                except Exception as e:
                    self.report.append({"key": src.key, "name": src.name, "error": str(e)})
                    print(f"  [{src.key}] 失败: {e}")
        return all_apps

    def report_table(self) -> str:
        lines = [f"{'站点':<14}{'优先级':<8}{'IPA数':<8}{'API调用':<10}{'错误'}", "-" * 50]
        for r in self.report:
            if "error" in r:
                lines.append(f"{r['key']:<14}{'-':<8}{'-':<8}{'-':<10}{r['error'][:20]}")
            else:
                lines.append(f"{r['key']:<14}{r['priority']:<8}{r['count']:<8}{r['api_calls']:<10}{r['errors']}")
        return "\n".join(lines)
