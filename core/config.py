#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配置管理模块
- 六个带密码的 AList 数据源定义（密码由 password_fetcher.py 动态获取）
- 去重优先级（宅哥 zgios = 1 最高，重复软件以宅哥为准）
- 全局参数（超时、并发、输出路径等）

所有配置可通过 config/sites.json / config/settings.json 覆盖。
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
CONFIG_DIR = os.path.join(BASE_DIR, "config")

for _d in (DATA_DIR, OUTPUT_DIR, CONFIG_DIR):
    os.makedirs(_d, exist_ok=True)


@dataclass
class SourceConfig:
    """单个数据源配置"""
    key: str
    name: str
    kind: str                       # "alist"（本系统均为 AList）
    base_url: str
    priority: int                   # 去重优先级，越小越优先
    paths: List[str] = field(default_factory=list)
    password: str = ""              # 运行时由 password_fetcher 动态填充
    password_key: str = ""          # 对应 passwords.json 里的 site 字段
    max_depth: int = 3
    enabled: bool = True
    note: str = ""


# 六个真实网盘（密码机制已由 get_passwords.py 侦测）
# 去重优先级：宅哥 zgios = 1（最高）
DEFAULT_SOURCES: List[SourceConfig] = [
    SourceConfig(
        key="gfm", name="宅哥技术网盘（主源）", kind="alist",
        base_url="https://gfm.zgios.cn", priority=1,
        paths=["/ipa分享"],
        password_key="gfm.zgios.cn", max_depth=3,
        note="重复软件以此源为准。周期密码（3天轮换），含微信分身/游戏/巨魔插件",
    ),
    SourceConfig(
        key="aifeng", name="爱锋助手 iOS 网盘", kind="alist",
        base_url="https://alist.aifengzhushou.cn", priority=2,
        paths=["/iOS应用", "/iOS多开", "/iOS游戏", "/iOS巨魔", "/iOS越狱"],
        password_key="alist.aifengzhushou.cn", max_depth=3,
    ),
    SourceConfig(
        key="yeziku", name="叶子库网盘", kind="alist",
        base_url="https://pan.yeziku.cn", priority=3,
        paths=["/IPA分享", "/IOS巨魔"],
        password_key="pan.yeziku.cn", max_depth=3,
    ),
    SourceConfig(
        key="lewsky", name="乐玩 iOS 资源站", kind="alist",
        base_url="https://ios.lewsky.top", priority=4,
        paths=["/iOS资源", "/巨魔注入", "/越狱工具"],
        password_key="ios.lewsky.top", max_depth=3,
    ),
    SourceConfig(
        key="qlam", name="清烟资源库", kind="alist",
        base_url="https://pan.qlam.cc", priority=5,
        paths=["/苹果应用 - Appstore apps", "/巨魔商店 - TrollStore", "/微信多开 - WeChat multi-open"],
        password_key="pan.qlam.cc", max_depth=3,
        note="密码每日 00:00 轮换，需每天重新获取",
    ),
    SourceConfig(
        key="iossq", name="IOS神器", kind="alist",
        base_url="https://pan.iossq.top", priority=6,
        paths=["/苹果"],
        password_key="pan.iossq.top", max_depth=4,
    ),
]


@dataclass
class AppSettings:
    request_timeout: int = 12
    site_timeout: int = 75          # 单站采集总时限（秒），防止深层目录悬挂
    max_workers: int = 6
    per_page: int = 500
    max_apps: int = 3000
    sort_by_date: bool = True       # 源内按更新日期降序（最新在前）
    skip_keywords: List[str] = field(default_factory=lambda: [
        ".deb", "说明", "教程", "readme", ".dylib.zip", ".zip", ".rar", ".7z",
    ])
    min_size_mb: float = 0.05
    source_name: str = "🍎 聚合中文源（每日更新）"
    source_identifier: str = "cn.aggregate.trollstore.daily"
    source_subtitle: str = "多网盘聚合 · gfm 优先 · 每日自动同步"
    source_website: str = "https://github.com/weer2/trollstore-aggregate-source"
    gen_description: bool = True
    fetch_passwords: bool = False   # 默认不需要：公开目录 API 空密码可读
    source_icon: str = "https://raw.githubusercontent.com/weer2/trollstore-aggregate-source/refs/heads/main/assets/logo.png"


def load_config() -> tuple[List[SourceConfig], AppSettings]:
    """从 config/*.json 加载配置，不存在则写默认模板。"""
    cfg_path = os.path.join(CONFIG_DIR, "sites.json")
    settings_path = os.path.join(CONFIG_DIR, "settings.json")

    if os.path.exists(cfg_path):
        with open(cfg_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        sources = [SourceConfig(**s) for s in raw.get("sources", [])]
    else:
        sources = DEFAULT_SOURCES
        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump({"sources": [asdict(s) for s in sources]}, f, ensure_ascii=False, indent=2)

    if os.path.exists(settings_path):
        with open(settings_path, "r", encoding="utf-8") as f:
            settings = AppSettings(**json.load(f))
    else:
        settings = AppSettings()
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(asdict(settings), f, ensure_ascii=False, indent=2)

    return sources, settings


def load_passwords() -> dict:
    """读取 passwords.json，返回 {site: password}。"""
    p = os.path.join(DATA_DIR, "passwords.json")
    if not os.path.exists(p):
        return {}
    d = json.load(open(p, "r", encoding="utf-8"))
    return {s["site"]: s.get("password") for s in d.get("sites", []) if s.get("password")}


if __name__ == "__main__":
    srcs, st = load_config()
    print(f"加载 {len(srcs)} 个数据源")
    for s in srcs:
        print(f"  P{s.priority} {s.key}: {s.name} | paths={s.paths}")
    print("密码表:", list(load_passwords().keys()))
