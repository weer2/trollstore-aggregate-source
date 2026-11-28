#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
元数据增强模块
- 从文件名解析应用中文名、版本号
- 内置常见应用功能描述词典（可搜索补充）
- 生成统一格式的应用描述
"""
from __future__ import annotations

import re
from typing import Dict

from .models import AppRecord, normalize_app_name


# 常见应用功能简介词典（key 为规范化名称）
KNOWN_DESCRIPTIONS: Dict[str, str] = {
    "微信": "微信（WeChat）——腾讯出品的即时通讯与社交生活平台，支持文字/语音/视频通话、朋友圈、支付及小程序。",
    "qq": "QQ——腾讯即时通讯软件，支持聊天、空间、文件传输与群组功能。",
    "抖音": "抖音——字节跳动短视频社交平台，收录海量创意短视频、直播与音乐内容。",
    "抖音pro": "抖音 Pro 增强版，提供额外功能与去广告体验。",
    "小红书": "小红书——生活方式分享社区，聚合美妆、穿搭、美食、旅行种草笔记与视频。",
    "支付宝": "支付宝——蚂蚁集团移动支付与生活服务平台，支持付款、理财、缴费与城市服务。",
    "网易云音乐": "网易云音乐——音乐流媒体平台，以个性化推荐、歌单与乐评社区著称。",
    "qq音乐": "QQ 音乐——腾讯音乐平台，海量正版曲库与高品质音频。",
    "酷狗音乐": "酷狗音乐——在线音乐播放器，支持海量歌曲搜索与 K 歌。",
    "酷我音乐": "酷我音乐——在线音乐与音频内容平台。",
    "汽水音乐": "汽水音乐——字节跳动旗下音乐流媒体应用，主打年轻化音乐推荐。",
    "番茄小说": "番茄小说——免费网络小说阅读平台，涵盖各类热门网文。",
    "番茄畅听": "番茄畅听——有声书与网络小说听书平台。",
    "youtube": "YouTube——全球最大视频分享平台，可在线观看与订阅海量视频内容。",
    "youtubemusic": "YouTube Music——谷歌音乐流媒体服务，含官方曲库与 MV。",
    "tiktok": "TikTok——抖音国际版，全球短视频社交平台。",
    "facebook": "Facebook——Meta 旗下社交网络平台。",
    "twitter": "Twitter / X——全球实时社交媒体平台。",
    "whatsapp": "WhatsApp——Meta 旗下跨平台即时通讯应用。",
    "instagram": "Instagram——Meta 旗下图片与短视频社交平台。",
    "百度网盘": "百度网盘——云存储服务，支持文件备份、分享与在线预览。",
    "wpsoffice": "WPS Office——金山办公套件，支持文档/表格/PPT 编辑。",
    "扫描全能王": "扫描全能王（CamScanner）——文档扫描与 PDF 转换工具。",
    "keep": "Keep——健身与运动训练平台，提供课程与运动记录。",
    "alook": "Alook 浏览器——轻量快速 iOS 浏览器，支持广告拦截与多标签。",
    "picsart": "PicsArt——功能强大的图片编辑与创意设计应用。",
    "美图秀秀": "美图秀秀——国民级图片美化与修图工具。",
    "b612咔叽": "B612 咔叽——自拍与相机美化应用，含海量贴纸滤镜。",
    " shadowrocket": "Shadowrocket——iOS 网络工具应用（需自行配置）。",
    "trollfools": "TrollFools——巨魔插件注入工具，可向已安装 App 注入 dylib  tweak。",
    "trollinstaller": "TrollInstallerX——TrollStore 巨魔安装器，用于安装持久化助手。",
    "livecontainer": "LiveContainer——应用容器，可在巨魔环境多开与运行未签名 App。",
    "dopamine": "Dopamine——iOS 越狱工具（rootless），支持安装越狱环境。",
    "unc0ver": "unc0ver——经典 iOS 越狱工具。",
    "filza": "Filza——iOS 文件管理器，越狱环境可访问系统目录。",
    "小红书": "小红书——生活方式分享社区。",
}


class AppEnricher:
    """应用元数据增强器"""

    def __init__(self, custom_desc: Dict[str, str] = None, enabled: bool = True):
        self.desc_dict = dict(KNOWN_DESCRIPTIONS)
        if custom_desc:
            self.desc_dict.update(custom_desc)
        self.enabled = enabled

    def lookup_description(self, name: str) -> str:
        """查词典 + 模糊匹配获取应用描述。"""
        norm = normalize_app_name(name)
        # 精确匹配
        if norm in self.desc_dict:
            return self.desc_dict[norm]
        # 包含匹配（取最长的匹配 key）
        best = ""
        for k, v in self.desc_dict.items():
            if k and (k in norm or norm in k):
                if len(k) > len(best):
                    best = k
        if best:
            return self.desc_dict[best]
        return ""

    def enrich(self, app: AppRecord) -> AppRecord:
        """为单个 App 补充描述。"""
        if not self.enabled:
            return app
        if not app.description:
            # 查不到真实介绍就留空，绝不生成「XX —— 来自 YY 的 iOS 应用」占位文案。
            # 描述前缀由 models.AppRecord.build_description() 统一拼成源 Key。
            app.description = self.lookup_description(app.name) or ""
        return app

    def enrich_all(self, apps: list) -> list:
        return [self.enrich(a) for a in apps]


def load_custom_descriptions(path: str) -> Dict[str, str]:
    """从外部 JSON 加载自定义描述词典。"""
    import json
    import os
    if not os.path.exists(path):
        return {}
    try:
        return json.load(open(path, "r", encoding="utf-8"))
    except Exception:
        return {}
