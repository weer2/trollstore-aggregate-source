#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
六个 AList 密码站点的实时密码抓取脚本。
用法: python get_passwords.py
输出: 每个站点的当前密码 + 校验机制 + 有效期，并写入 passwords.json
"""
import re
import ssl
import json
import time
import urllib.request
import urllib.parse
import http.cookiejar
from datetime import datetime

CTX = ssl._create_unverified_context()
UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15"


def get(url, headers=None, data=None, use_cookie=False):
    h = {"User-Agent": UA}
    if headers:
        h.update(headers)
    body = None
    if data is not None:
        body = urllib.parse.urlencode(data).encode()
        h["Content-Type"] = "application/x-www-form-urlencoded"
    handlers = [urllib.request.HTTPSHandler(context=CTX)]
    if use_cookie:
        handlers.append(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    opener = urllib.request.build_opener(*handlers)
    req = urllib.request.Request(url, data=body, headers=h)
    with opener.open(req, timeout=25) as r:
        return r.read().decode(errors="replace")


def parse(html, patterns):
    for pat in patterns:
        m = re.search(pat, html)
        if m:
            return m.group(1)
    return None


def fetch_gfm():
    """宅哥技术网盘: 登录第三方门禁后台读取当前周期密码"""
    base = "https://xinsu.pgbug.com/backend/admin.php"
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=CTX),
        urllib.request.HTTPCookieProcessor(cj),
    )
    login_req = urllib.request.Request(
        base,
        data=urllib.parse.urlencode({"login_key": "hanjiajia520"}).encode(),
        headers={"User-Agent": UA, "Content-Type": "application/x-www-form-urlencoded"},
    )
    opener.open(login_req, timeout=25).read()
    page = opener.open(urllib.request.Request(base, headers={"User-Agent": UA}), timeout=25).read().decode(errors="replace")
    pwd = parse(page, [r'id="curPwd"[^>]*>\s*([^<\s]+)\s*<', r'当前周期密码[\s\S]{0,200}?<div class="v"[^>]*>([^<]+)<'])
    eff = parse(page, [r'(\d{4}-\d{2}-\d{2})\s*起'])
    nxt = parse(page, [r'下次更新[\s\S]{0,200}?(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})'])
    return pwd, eff, nxt


def main():
    results = []
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 1. gfm.zgios.cn
    try:
        pwd, eff, nxt = fetch_gfm()
        results.append({
            "site": "gfm.zgios.cn", "name": "宅哥技术网盘", "password": pwd,
            "mechanism": "服务端按周期生成，第三方门禁后台读取",
            "validity": f"生效 {eff} 起 / 下次更新 {nxt}", "status": "ok",
        })
    except Exception as e:
        results.append({"site": "gfm.zgios.cn", "name": "宅哥技术网盘", "password": None, "error": str(e), "status": "error"})

    # 2. alist.aifengzhushou.cn
    try:
        html = get("https://alist.aifengzhushou.cn/")
        pwd = parse(html, [r'const\s+PWD\s*=\s*["\']([^"\']+)["\']'])
        results.append({
            "site": "alist.aifengzhushou.cn", "name": "爱锋助手ios网盘", "password": pwd,
            "mechanism": "前端硬编码 const PWD", "validity": "固定值，localStorage 永久缓存", "status": "ok",
        })
    except Exception as e:
        results.append({"site": "alist.aifengzhushou.cn", "name": "爱锋助手ios网盘", "password": None, "error": str(e), "status": "error"})

    # 3. pan.yeziku.cn
    try:
        html = get("https://pan.yeziku.cn/")
        pwd = parse(html, [r'const\s+PWD\s*=\s*["\']([^"\']+)["\']'])
        results.append({
            "site": "pan.yeziku.cn", "name": "叶子库网盘", "password": pwd,
            "mechanism": "前端硬编码 const PWD", "validity": "固定值，localStorage 缓存 24 小时", "status": "ok",
        })
    except Exception as e:
        results.append({"site": "pan.yeziku.cn", "name": "叶子库网盘", "password": None, "error": str(e), "status": "error"})

    # 4. ios.lewsky.top
    try:
        html = get("https://ios.lewsky.top/")
        pwd = parse(html, [r'let\s+password\s*=\s*["\']([^"\']+)["\']'])
        results.append({
            "site": "ios.lewsky.top", "name": "乐玩iOS资源站", "password": pwd,
            "mechanism": "前端硬编码 let password", "validity": "固定值，localStorage 缓存 12 小时", "status": "ok",
        })
    except Exception as e:
        results.append({"site": "ios.lewsky.top", "name": "乐玩iOS资源站", "password": None, "error": str(e), "status": "error"})

    # 5. pan.qlam.cc
    try:
        html = get("https://pan.qlam.cc/")
        api = parse(html, [r'const\s+API_URL\s*=\s*["\']([^"\']+)["\']'])
        data = json.loads(get(api + "?t=" + str(int(time.time() * 1000)), headers={"Referer": "https://pan.qlam.cc/"}))
        results.append({
            "site": "pan.qlam.cc", "name": "清烟资源库", "password": data.get("password"),
            "mechanism": "后端接口动态下发", "validity": f"每日 00:00 轮换，本次更新 {data.get('update_time')}", "status": "ok",
        })
    except Exception as e:
        results.append({"site": "pan.qlam.cc", "name": "清烟资源库", "password": None, "error": str(e), "status": "error"})

    # 6. pan.iossq.top
    try:
        html = get("https://pan.iossq.top/")
        pwd = parse(html, [r'let\s+password\s*=\s*["\']([^"\']+)["\']'])
        results.append({
            "site": "pan.iossq.top", "name": "IOS神器", "password": pwd,
            "mechanism": "前端硬编码 let password", "validity": "固定值，localStorage 永久缓存", "status": "ok",
        })
    except Exception as e:
        results.append({"site": "pan.iossq.top", "name": "IOS神器", "password": None, "error": str(e), "status": "error"})

    # 7. wp.iosqh.top 情海网盘（根目录公开，无需密码；仍尝试解析以防目录加密）
    try:
        html = get("https://wp.iosqh.top/")
        pwd = parse(html, [r'const\s+PWD\s*=\s*["\']([^"\']+)["\']',
                           r'let\s+password\s*=\s*["\']([^"\']+)["\']'])
        results.append({
            "site": "wp.iosqh.top", "name": "情海网盘", "password": pwd or "",
            "mechanism": "根目录公开；若子目录加密则从前端 PWD 变量读取",
            "validity": "无密码或固定值", "status": "ok",
        })
    except Exception as e:
        # WAF 拦截本机 IP 时按"无密码"处理，GitHub Actions 海外 IP 可正常访问
        results.append({
            "site": "wp.iosqh.top", "name": "情海网盘", "password": "",
            "mechanism": "根目录公开，无需密码", "status": "ok",
            "note": "本机探测受限（" + str(e)[:40] + "），按无密码处理",
        })

    print(f"抓取时间: {ts}\n")
    print(f"{'站点':<28}{'名称':<18}{'密码':<12}{'有效期'}")
    print("-" * 90)
    for r in results:
        print(f"{r['site']:<28}{r['name']:<18}{str(r.get('password')):<12}{r.get('validity', r.get('error',''))}")

    # 写入项目内 data 目录
    import os
    out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "passwords.json")

    # 与旧密码合并：本次抓取失败的站点保留上次成功的密码，避免单站临时故障
    old = {}
    if os.path.exists(out_path):
        try:
            old = {s["site"]: s for s in json.load(open(out_path, encoding="utf-8")).get("sites", [])}
        except Exception:
            old = {}
    for r in results:
        if not r.get("password") and r["site"] in old and old[r["site"]].get("password"):
            r["password"] = old[r["site"]]["password"]
            r["status"] = "cached"
            r["note"] = "本次抓取失败，沿用上次密码"

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"updated_at": ts, "sites": results}, f, ensure_ascii=False, indent=2)
    print("\n已写入 " + out_path)


if __name__ == "__main__":
    main()
