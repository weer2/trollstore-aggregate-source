#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""分类过滤器：剔除游戏、美化、越狱、电脑、安卓、证书类应用及插件。

判定基于 AList 下载路径（解码后）与应用名/包名，路径与名称任一命中即剔除。
自签目录仅是分发渠道，不单独作为证书类判据；只有含签名/证书字样的条目才剔除。
"""
from __future__ import annotations

import re
import urllib.parse
from typing import Any, Dict, List, Tuple

# 仅按名称判定时使用的正则（避免把 Design 等误判为签名工具）
_CERT_NAME = (
    r"证书|签名|p12|mobileprovision|企业签|超级签|重签|描述文件|UDID|"
    r"\bSign(?:ing|er)?\b|LCSign|自签助手"
)
# 按路径判定时，只匹配明确的证书/签名目录
_CERT_PATH = (
    r"证书|签名工具|p12|mobileprovision|企业签|超级签|重签|描述文件|UDID|Signing"
)

_RULES: List[Tuple[str, str, str]] = [
    (
        "游戏",
        r"游戏|Games?|Crack|无敌|秒杀|作弊|修改版|内购|无限|攻略|竞技|"
        r"枪战|三国|仙侠|传奇|冒险|塔防|卡牌|休闲|动作|射击|模拟经营|养成|"
        r"解谜|跑酷|棋牌|斗地主|麻将|ROM|宝可梦|原神|王者|和平精英|"
        r"地铁跑酷|使命召唤|植物大战僵尸|Subway|Minecraft|GTA|Roblox|存档|"
        r"军团|华夏|无悔|欲望|冷酷灵魂|失控进化|三角洲|英雄联盟|视距|"
        r"无畏契约|穿越火线|火影|海贼王|数码宝贝|作战|战争|生存|女神|战场|突袭|"
        r"王国保卫战|失落城堡|迷雾大陆|明日方舟|保卫战|城堡|方舟|"
        r"崩坏|阴阳师|第五人格|金铲铲|云顶之弈|部落冲突|皇室战争|荒野乱斗|"
        r"植物大战|我的世界|迷你世界|全功能",
        r"游戏|Games?|Crack|无敌|秒杀|作弊|修改版|内购|无限|攻略|竞技|"
        r"枪战|三国|仙侠|传奇|冒险|塔防|卡牌|休闲|动作|射击|养成|解谜|"
        r"跑酷|棋牌|斗地主|麻将|ROM|宝可梦|原神|王者|和平精英|"
        r"地铁跑酷|使命召唤|植物大战僵尸|Subway|Minecraft|GTA|Roblox|"
        r"军团|华夏|无悔|欲望|冷酷灵魂|失控进化|三角洲|英雄联盟|视距|"
        r"无畏契约|穿越火线|火影|海贼王|数码宝贝|作战|战争|生存|女神|战场|突袭|"
        r"王国保卫战|失落城堡|迷雾大陆|明日方舟|保卫战|城堡|方舟|"
        r"崩坏|阴阳师|第五人格|金铲铲|云顶之弈|部落冲突|皇室战争|荒野乱斗|"
        r"植物大战|我的世界|迷你世界|全功能",
    ),
    (
        "美化",
        r"美化|主题|壁纸|图标|Theme|Icon|Widget|小组件|锁屏|桌面|灵动岛|动态岛|滤镜|字体|修图",
        r"美化|主题|壁纸|图标|Theme|Icon|Widget|小组件|锁屏|桌面|灵动岛|动态岛|滤镜|字体|修图",
    ),
    (
        "越狱/插件",
        r"越狱|Jailbreak|\bJB\b|Tweak|插件|Cydia|Sileo|注入|砸壳|\.deb|Activator|PreferenceLoader",
        r"越狱|Jailbreak|\bJB\b|Tweak|插件|Cydia|Sileo|注入|砸壳|\.deb|Activator|PreferenceLoader|"
        r"unc0ver|checkra1n|palera1n|Dopamine|Xina|Pongo|Odyssey|Chimera|Electra|Liberty|Karen|bootstrap|Serotonin|Relaxin",
    ),
    (
        "电脑",
        r"电脑|PC|Windows|macOS|\bMac\b|\.dmg|\.exe|计算机",
        r"电脑|PC|Windows|macOS|\bMac\b|\.dmg|\.exe|计算机",
    ),
    (
        "安卓",
        r"安卓|Android|\.apk|鸿蒙|Harmony",
        r"安卓|Android|\.apk|鸿蒙|Harmony",
    ),
    ("证书/签名", _CERT_PATH, _CERT_NAME),
]

# AList 显式游戏目录：命中即剔除整棵子树（含全部子文件夹）。
# gfm.zgios.cn 的 /ipa分享/游戏ipa 下有 5/4/3/游/游1/游2 等子目录，
# 其中大量文件名不含游戏关键词，必须按目录路径硬过滤。
_GAME_DIRS = (
    "/ipa分享/游戏ipa",           # gfm 宅哥源
    "/ipa分享/iOS游戏",           # aifeng 源
    "/iOS游戏",                   # 通用 iOS 游戏目录
    "/游戏ipa", "/游戏IPA",
    "/Games", "/games",
)

_COMPILED = [
    (label, re.compile(path_pat, re.I), re.compile(name_pat, re.I))
    for label, path_pat, name_pat in _RULES
]
_GAME_DIR_RX = re.compile(
    "|".join(re.escape(d) for d in _GAME_DIRS), re.I
)


def _get(app: Any, key: str, default: str = "") -> str:
    if isinstance(app, dict):
        return str(app.get(key) or default)
    return str(getattr(app, key, default) or default)


def decode_path(app: Any) -> str:
    """解码 downloadURL 的路径部分，中文目录名可直接匹配关键词。"""
    url = _get(app, "downloadURL")
    if not url:
        return ""
    return urllib.parse.unquote(urllib.parse.urlparse(url).path)


def exclude_reason(app: Any) -> str:
    """返回剔除原因；空字符串表示保留。"""
    path = decode_path(app)
    name = _get(app, "name")
    bid = _get(app, "bundleIdentifier")
    # 显式游戏目录优先：目录子树内一律剔除，不看文件名
    if _GAME_DIR_RX.search(path):
        return "游戏"
    for label, path_rx, name_rx in _COMPILED:
        if path_rx.search(path):
            return label
        if name_rx.search(name) or name_rx.search(bid):
            return label
    return ""


def is_excluded_dir(path: str) -> bool:
    """采集阶段剪枝：目录路径命中游戏/越狱/插件等硬目录即跳过整棵子树。"""
    p = urllib.parse.unquote(path or "")
    return bool(_GAME_DIR_RX.search(p)) or any(
        rx.search(p) for rx in (_CERT_PATH_RX,)
    )


_CERT_PATH_RX = re.compile(r"/(?:越狱工具|Dylib插件|巨魔插件|TrollFools|砸壳工具)", re.I)


def filter_apps(apps: List[Any]) -> Tuple[List[Any], int]:
    """过滤列表，返回 (保留列表, 剔除数量)。顺序与输入一致。"""
    kept: List[Any] = []
    removed = 0
    for app in apps:
        if exclude_reason(app):
            removed += 1
        else:
            kept.append(app)
    return kept, removed
