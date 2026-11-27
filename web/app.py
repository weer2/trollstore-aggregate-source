#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Web 状态站（Flask）
- 展示源统计、站点采集报告、更新历史
- 应用搜索
- 可直接输出 source.json 供巨魔订阅
部署：GitHub Pages 用静态页；本地/Docker 用此 Flask 服务。
"""
from __future__ import annotations

import os
import sys
import json
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from flask import Flask, render_template, jsonify, send_from_directory, request

DATA_DIR = os.path.join(BASE_DIR, "data")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")

app = Flask(__name__, template_folder="templates", static_folder="static")


def _load_json(path, default):
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return default


@app.route("/")
def index():
    source = _load_json(os.path.join(OUTPUT_DIR, "source.json"), {})
    history = _load_json(os.path.join(DATA_DIR, "history.json"), [])
    meta = source.get("_meta", {})
    return render_template(
        "index.html",
        source_name=source.get("name", "—"),
        total=meta.get("total_apps", len(source.get("apps", []))),
        generated=meta.get("generated_at", "—"),
        by_source=meta.get("sources", {}),
        changes=meta.get("changes", {}),
        history=history[:30],
        now=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )


@app.route("/source.json")
def source_json():
    """巨魔订阅地址：/source.json"""
    return send_from_directory(OUTPUT_DIR, "source.json", mimetype="application/json")


@app.route("/api/stats")
def api_stats():
    source = _load_json(os.path.join(OUTPUT_DIR, "source.json"), {})
    return jsonify({
        "name": source.get("name"),
        "total": len(source.get("apps", [])),
        "meta": source.get("_meta", {}),
    })


@app.route("/api/search")
def api_search():
    q = request.args.get("q", "").strip()
    source = _load_json(os.path.join(OUTPUT_DIR, "source.json"), {})
    apps = source.get("apps", [])
    if q:
        apps = [a for a in apps if q.lower() in a.get("name", "").lower()
                or q in a.get("localizedDescription", "")]
    return jsonify([{
        "name": a.get("name"),
        "version": a.get("version"),
        "size": a.get("size"),
        "developerName": a.get("developerName"),
        "description": a.get("localizedDescription", "")[:200],
        "downloadURL": a.get("downloadURL"),
    } for a in apps[:100]])


@app.route("/api/history")
def api_history():
    return jsonify(_load_json(os.path.join(DATA_DIR, "history.json"), []))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=False)
