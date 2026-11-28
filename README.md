# 🍎 多网盘聚合巨魔动态源系统

自动采集 11 个 iOS IPA 网盘 → 智能去重（宅哥 zgios 优先）→ 生成巨魔增强版可直接订阅的动态软件源。
所有 IPA 直链指向各网盘官方 AList 下载接口，带来源/大小/更新日期/应用描述。

## 系统能力

| 能力 | 说明 |
|---|---|
| 多站采集 | 并发递归扫描 11 个 AList 站的 IPA 目录 |
| 免密码直采 | **所有采集目录经 AList 公开 API 空密码可读**，前端 PWD 仅为网站 UI 门禁，无需每日密码侦测 |
| 智能去重 | 按 bundle id / 文件名指纹去重；重复软件以宅哥 zgios 为准 |
| 分类过滤 | **剔除游戏 / 美化 / 越狱 / 电脑 / 安卓 / 证书类应用及插件**，源体积控制在 1MB 内 |
| 元数据增强 | 每条含来源、大小(MB)、更新日期、功能描述 |
| 日期排序 | **最新更新的软件排在最前** |
| 变更检测 | 每日对比快照，记录新增/移除/更新 |
| 动态源 | 输出标准 AltStore/SideStore JSON，巨魔增强版直接订阅 |
| 状态站 | Web 页展示统计、搜索应用、更新历史 |

## 数据源（11 站）

| 优先级 | Key | 站点 | 地址 | 采集路径 |
|---|---|---|---|---|
| 1 | zgios | 宅哥技术网盘（**去重基准**） | gfm.zgios.cn | /ipa分享 |
| 2 | aifeng | 爱锋助手 | alist.aifengzhushou.cn | /iOS应用 等 |
| 3 | yeziku | 叶子库 | pan.yeziku.cn | /IPA分享 等 |
| 4 | lewsky | 乐玩 iOS | ios.lewsky.top | /iOS资源 等 |
| 5 | qlam | 清烟资源库 | pan.qlam.cc | /苹果应用 等 |
| 6 | iossq | IOS神器 | pan.iossq.top | /苹果 |
| 7 | iosqh | 情海网盘 | wp.iosqh.top | /iOS资源专区 /情海定制 /Torllstore |
| 8 | iosi | IOSI 网盘 | pan.iosi.vip | /砸壳 /自签 /巨魔 |
| 9 | jiejingfan | 晴天网盘 | alist.jiejingfan.vip | /ipa资源 /Trollstore |
| 10 | w56 | 小胡爱折腾 | alist.5-6.vip | /01苹果IPA /trollstore |
| 11 | nyxz | NYXZ 分享 | share.nyxz166.com | /IOS-Games /IOS-TrollStore |

> **为什么不需要密码？** 实测 11 站的 `/api/fs/list` 传空密码均返回 `code:200`，所有采集目录（含宅哥 / 清烟 / 叶子库等原"带密码"站的 IPA 目录）都是 AList 公开可读的。网站前端的 `const PWD` / `let password` 只是 UI 门禁，不保护 API。仅真正的 VIP 目录（如 `pan.iosi.vip/VIP`）返回 403，但不在采集范围内。密码抓取模块保留为可选（`--fetch-passwords`），默认关闭。
>
> 情海网盘（wp.iosqh.top）的 WAF 会拦截部分出口 IP（返回 418/502）；GitHub Actions 的海外出口 IP 不受影响，部署后自动采集。本机采集报 WAF 错误属正常，不影响云端定时任务。

## 目录结构

```
trollstore-source-builder/
├── core/
│   ├── config.py            # 数据源与全局配置（可用 config/*.json 覆盖）
│   ├── models.py            # 统一 AppRecord 模型 / 指纹 / AltStore 转换
│   ├── password_fetcher.py  # 站点密码侦测（可选，默认关闭）
│   ├── scraper.py           # AList 并发递归采集（带时限保护）
│   ├── merger.py            # 去重（宅哥优先）+ 日期排序 + 变更检测
│   ├── filter.py            # 分类过滤（游戏/美化/越狱/电脑/安卓/证书/插件）
│   ├── enricher.py          # 应用描述词典与增强
│   └── generator.py         # 动态源生成
├── config/
│   ├── sites.json           # 站点配置（路径/优先级/深度）
│   └── settings.json        # 全局参数（超时/并发/排序开关）
├── data/
│   ├── passwords.json       # 当前密码（每日刷新）
│   ├── snapshot.json        # 上一轮快照（变更检测用）
│   ├── history.json         # 更新历史
│   └── custom_descriptions.json  # 自定义应用描述（可选）
├── output/
│   ├── source.json          # ★ 巨魔订阅的动态源（压缩）
│   └── source_pretty.json   # 美化版（便于查看）
├── web/app.py               # Flask 状态站
├── scripts/daily_update.py  # 每日更新主入口
├── .github/workflows/
│   └── daily-update.yml     # GitHub Actions 每日定时
├── Dockerfile
└── requirements.txt
```

## 本地运行

```bash
cd trollstore-source-builder
pip install -r requirements.txt          # 仅 Web 站需要 Flask
python scripts/daily_update.py           # 完整流程（默认免密码直采）
python scripts/daily_update.py --fetch-passwords  # 可选：强制跑一遍密码侦测
python web/app.py                        # 启动状态站 http://localhost:8080
```

产出：`output/source.json` 即动态源文件。

## 订阅地址

巨魔增强版 → 软件源 → + 从链接添加 → 粘贴（源名 **LEON🍎源**）：

`https://raw.githubusercontent.com/weer2/trollstore-aggregate-source/refs/heads/main/output/leon.json`

> 使用 `leon.json` 而不是旧的 `source.json`：增强版按 URL 缓存包列表（`.ipasource_pkg_cache`），
> 同时把 ETag/Last-Modified 存在源列表里。换文件名等于换缓存键，能彻底绕开旧 304 缓存导致的空白页／旧游戏残留。
> 若设备仍显示旧内容，先在「设置 → 清理 TrollStore 缓存」，删除旧源后用上面这条重新添加。

## 免费部署方案

### 方案 A：GitHub Actions + GitHub Pages（★ 最推荐，完全免费）

GitHub 提供免费的 Actions 运行时（每月 2000 分钟）和 Pages 静态托管，本系统零改造即可用。

步骤：
1. 在 GitHub 新建一个**公开仓库**（如 `my-troll-source`），把本项目所有文件传上去。
2. 进入仓库 **Settings → Pages**，Source 选 `Deploy from a branch`，分支选 `main`、目录选 `/ (root)`，保存。
3. 确认 `.github/workflows/daily-update.yml` 已存在（本项目自带）。
4. 进入 **Actions** 标签，找到「每日更新巨魔聚合源」，点 **Run workflow** 手动跑一次验证。
5. 跑完后 `output/source.json` 会被自动提交；订阅地址可直接用 raw 链接（见上节），无需等待 Pages。

工作流说明：
- `cron: '0 18 * * *'` = UTC 18:00 = 北京时间次日 02:00 运行。
- 每次运行流程：公开 API 免密码直采 → 多站采集 → 去重排序 → 变更检测 → 生成源 → 自动 git commit。
- 想改运行时间，编辑 workflow 里的 `cron`（注意用 UTC，北京时间减 8 小时）。

> 提示：GitHub Pages 直接托管整个仓库，所以订阅路径带 `/output/` 前缀。
> 如果想让路径更短（`.../source.json`），把 `output/source.json` 复制一份到仓库根目录即可，
> 或在 workflow 的提交步骤加一行 `cp output/source.json ./source.json && git add source.json`。

### 方案 B：Cloudflare Workers + Cron（免费额度大，动态生成）

适合想动态生成、不依赖 git commit 的场景。Cloudflare 免费版每天 10 万请求、Cron 定时免费。
需要把 Python 逻辑改写为 JS/TS（Workers 跑不了 Python），或用 Cloudflare Container（付费）。
**若坚持 Python，用方案 A 或 C 更省事。**

### 方案 C：Render / Fly.io 免费容器（跑完整 Python + Web 状态站）

- Render 免费 Web Service 可直接跑 `Dockerfile`，但免费实例闲置会休眠，定时任务可能漏跑。
- 更稳的做法：Render 跑 Web 状态站 + 用 GitHub Actions 负责定时采集（A+C 组合）。

## 配置与扩展

- **增删数据源**：编辑 `config/sites.json` 的 `sources` 数组：
  - `priority`：去重优先级，数字越小越优先（宅哥=1）。
  - `paths`：要扫描的 AList 目录，`max_depth`：递归深度。
  - `password_key`：对应 `data/passwords.json` 里的 `site` 字段。
- **密码机制**：`core/password_fetcher.py` 里每个站一个 `fetch_xxx()` 函数。新增站点照着加即可。
- **描述词典**：编辑 `data/custom_descriptions.json`（格式 `{"规范化应用名": "描述"}`）覆盖内置词典。
- **排序开关**：`config/settings.json` 的 `sort_by_date`（true=按更新日降序）。
- **应用上限**：`max_apps`（默认 3000），防止源过大导致巨魔解析失败。

## 常见问题

- **某站采集为 0**：检查该站是否触发 WAF（418/502）或路径变更；情海站对部分 IP 有限制，云端 Actions 可正常采。
- **单站很慢**：`site_timeout` 限制单站总时长（默认 75 秒），`max_depth` 控制递归深度。
- **源太大巨魔打不开**：调低 `max_apps`，或减小部分站的 `paths`。
- **下载链接失效**：AList 直链随网盘文件变动，每日采集会自动更新。


## 下载直链说明

- **签名站自动补签**：部分 AList 站（如乐玩 lewsky）的 `/d/` 直链需要签名，否则返回 51 字节的 `{"code":401,"message":"expire missing"}`。采集器会调用 `/api/fs/get` 获取形如 `xxx=:0` 的永久签名并拼到直链，保证下载到真实 IPA。
- **故障站剔除**：晴天网盘 jiejingfan 在部分网络环境不可达，小胡 5-6.vip 的 AList 存储配置损坏（`storage not found`），已从配置中禁用。
- **来源标注**：网盘 KEY 一律用域名主品牌简称（gfm.zgios.cn→`zgios`、wp.iosqh.top→`iosqh`，其余 `aifeng`/`yeziku`/`lewsky`/`qlam`/`iossq`/`iosi`/`jiejingfan`/`nyxz` 同理）；`developerName` 取主源 Key，应用描述以 `<KEY>·<日期>` 开头，多源以 ` | ` 并列。
- **游戏过滤**：游戏、美化、越狱、电脑、安卓、证书类应用及插件全部剔除；文件名含 `_全功能.ipa` 的条目一律按游戏剔除；源文件控制在 1MB 内。


## 图标与来源标注

- 软件源图标：`assets/logo.png`（紫粉渐变随机配色 + 8 个聚合节点），顶层 `iconURL` 指向该文件的 raw 地址，巨魔增强版列表中直接显示。
- 应用图标：`core/icon_enricher.py` 从参考源 `ipa.312752.cn/appstore` 的 564 条图标映射表匹配（精确核心名 + 相似度 ≥0.86 的模糊匹配防错配），不足部分由 iTunes Search API 低频补抓（命中即写入 `data/icon_meta_cache.json`，永久缓存、重复运行零请求；iTunes 出口 IP 被 403 限流时自动熔断）。匹配不到则 `iconURL` 留空。
- 应用来源仅用网盘源 Key（域名主品牌简称），例如 `lewsky`、`zgios`、`iosqh`、`qlam`；`developerName`、副标题、公告不出现中文网盘名。应用描述格式为 `<源Key>·<网盘更新日期> | <源Key>·<日期> / <软件介绍>`，例如 `jiejingfan·2026.11.26 / 抖音——字节跳动短视频社交平台…`；多网盘按 ` | ` 并列各自的更新日期，例如 `zgios·2026.11.26 | yeziku·2026.09.01 | qlam·2026.11.24 / 悬浮按钮可以开启功能…`。无真实介绍时只列来源与日期，绝不生成「XX —— 来自 YY 的 iOS 应用」占位文案。
- 软件介绍来源：内置词典 → 参考源 `versionDescription` 短句 → iTunes `description` 截取首句（≤46 字），均无则留空。
- 游戏目录硬过滤：`/ipa分享/游戏ipa` 及其全部子目录（5/4/3/游/游1/游2 等）在**采集阶段整棵剪枝**，并在 `filter.py` 再次兜底；不再依赖文件名关键词。
- 源文件约 330KB（字段精简后），低于 1MB。


## 巨魔增强版字段兼容说明

反汇编增强版二进制（`TSIPAPackage` 解析 key 连续簇 `identifier / versionDescription / description / iconURL / downloadURL / size / lock`，另有 `setBundleIdentifier:` selector）确认客户端实际读取字段：

| 详情页项 | 客户端读取字段 | 本源处理 |
|---|---|---|
| 应用描述 | `versionDescription`（回退 `description`，都没有才显示 `No description available.`） | 两个描述字段写同一内容 |
| 标识符 | `identifier` + `bundleIdentifier` | 两者写同值 `cn.aggregate.<指纹>`；参考源两者皆缺，故其标识符不显示 |
| 大小 | `size`（数值） | 写字节数整数；参考源给字符串 `"0"` 故大小不显示 |
| 版本 | `version` | 从文件名解析 |
| 下载 | `downloadURL` | AList 签名永久直链 |

已删除的冗余字段（反汇编证据）：`isLanZouCloud`（二进制内**零引用**，无该字符串）、`localizedDescription`（不在解析簇）、`tintColor`（空串无 UI 意义）、`versions[]`（不读取）、`subtitle`/`minOSVersion`。`description` 保留作 fallback（解析簇内紧跟 `No description available.`），`lock` 保留（解析簇内）。

`TSIPASource` 读取顶层 `sourceicon`/`iconURL` 作为源图标，`apps`（或 `packages`）作为应用数组——两者都已写入。

情海网盘（wp.iosqh.top）采集器已做两处修复：① `list_dir` 自动翻页（旧版只取第一页，单目录 >500 项时子目录被漏采，是「抓取不全」的根因）；② 只抓 `/iOS资源专区`、`/情海定制`、`/Torllstore` 三个目录，递归深度 5，单站时限 180s。
