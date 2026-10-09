# fizz-usage-monitor — v0.1.0

轻量级、只读的本地流量 Dashboard。本版本仅使用明确标记为 **synthetic/mock** 的模拟数据，不支持真实 Fizz 登录、自动采集或内部 API 调用。
A lightweight local usage dashboard. This version uses **synthetic/mock data only**; it has no real Fizz login, collection or internal API integration.

**非官方声明 / Unofficial notice:** 本项目与 Fizz 无官方关联，未经其认可或赞助。Fizz 名称仅用于说明项目背景。本项目未使用其网站图片、Logo、网页代码或其他受保护素材。
This project is not affiliated with, endorsed by or sponsored by Fizz. The name identifies the project context; no official images, logos or website code are included.

## 功能 / Features

- 独立 Account A / Account B，固定 account_id、可编辑别名，不保存登录邮箱。
  Two independent accounts with editable aliases; no login emails are stored.
- SQLite 保存账单周期、套餐月费、下次付款日期、Wallet 快照及五类流量批次。
  Billing cycles, monthly charges, next payment date, Wallet snapshots and plan/rollover/gift/perk/add-on buckets.
- 金额使用整数 cents（CAD），流量使用整数 MB；事务 UPSERT 支持重复导入与历史修正。
  Integer amounts and atomic upserts avoid floating-point storage and duplicate daily rows.
- America/Toronto 最近三个完整自然日及 30 天历史；跨周期读取，缺失 null 与真实零值分开。
  Complete local calendar days, cross-cycle history and explicit missing values. Daily usage is never inferred from bucket deltas.
- 完整 Dashboard 与基础 HTML/CSS Lite 页面；只读 JSON、健康检查、过期和失败提示。
  Full and Lite dashboards, read-only JSON, health checks and freshness warnings.
- Lite 独立低流量/有效期告警，未知或陈旧数据绝不显示绿色正常。
  Per-account low-balance and expiry alerts; unknown or stale data never appears healthy.

本阶段显示的付款信息仅为模拟月费和下次付款日期，不包含银行卡、真实账单或支付流水。
Payment information is limited to simulated charges and dates, not real transactions or card details.

## 环境与依赖 / Requirements

Python 3.10+（推荐 3.12）、Linux Mint 或其他提供 America/Toronto 时区数据的环境。适用于低功耗 CPU，无需 GPU、Node.js 或前端构建工具。
Python 3.10+ (3.12 recommended) and system timezone data. No GPU or frontend build tools are required.

唯一直接运行依赖是 Flask；SQLite、zoneinfo 和 unittest 来自 Python 标准库。HTML/CSS 均为本地资源，无 CDN、JavaScript 或前端框架。
Flask is the only direct runtime dependency. SQLite, timezone handling and tests use the standard library.

## 安装 / Installation

在项目目录执行，依赖仅安装到 `.venv`：
Run inside the project; dependencies install in the virtual environment:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

使用系统包管理器安装 Python/venv 是用户自己的环境准备步骤；本项目不修改系统服务。
System Python/venv installation is an environment prerequisite; the project does not configure services.

## 持久化模拟演示 / Persistent mock demo

```bash
umask 077
export FIZZ_DATA_DIR="$HOME/.local/share/fizz-usage-monitor"
export FIZZ_LOW_DATA_MB=1000
export FIZZ_STALE_HOURS=36
.venv/bin/python -m fizz_monitor start-demo --port 5000
```

首次创建私有目录（700）和数据库（600），数据位于 Git 工作区之外；后续启动复用数据，不重置别名或历史。未知已有数据库或非空目录会被拒绝，选择新演示目录即可，不要删除旧数据。
First run creates private persistent mock storage; later runs preserve it. Unrecognized existing data is refused rather than replaced. Choose a fresh directory when needed.

数据库路径为 `$FIZZ_DATA_DIR/monitor.sqlite3`；无秘密的 `.synthetic-demo` 标记仅识别该命令建立的演示库。标记不是对内容的安全认证，禁止在演示库中混入真实数据。
The demo marker identifies generated storage; it is not a security attestation. Keep real records out of demo databases.

访问 / URLs:

- 完整 / Full: http://127.0.0.1:5000/
- Lite: http://127.0.0.1:5000/lite
- Health: http://127.0.0.1:5000/health
- Read-only JSON: http://127.0.0.1:5000/api/v1/summary

默认只监听 127.0.0.1，debug/reloader 关闭。此为本地验收服务器；其他设备需要用户配置的 SSH 隧道，不能直接访问该回环地址。Ctrl+C 停止，不创建开机启动或 systemd 服务。
Loopback-only local Flask development server. Other devices require a user-managed SSH tunnel. Stop with Ctrl+C; no startup service is installed.

重启已有数据库（不重新写入 mock）：
Restart an existing initialized database without regenerating mock records:

```bash
export FIZZ_DATA_DIR="$HOME/.local/share/fizz-usage-monitor"
.venv/bin/python -m fizz_monitor doctor
.venv/bin/python -m fizz_monitor serve --port 5000
```

数据持久化不等于自动采集；模拟数据超过新鲜度阈值后显示陈旧提示。
Persistence does not simulate new collection; old mock data correctly becomes stale.

## 初始化与数据管理 / Initialization and management

如需单独初始化和写入 mock，请使用一个新的专用演示目录：
For separate initialization and seeding, use a fresh demo-only directory:

```bash
export FIZZ_DATA_DIR="$HOME/.local/share/fizz-usage-monitor-manual-demo"
.venv/bin/python -m fizz_monitor init
.venv/bin/python -m fizz_monitor demo
.venv/bin/python -m fizz_monitor alias account_a 'Account A demo'
.venv/bin/python -m fizz_monitor serve --port 5000
```

`init` 保留现有别名；`demo` 会更新模拟日用量并追加快照，拒绝含非 mock source 的数据集。未知用户数据应避免接触，优先使用 `start-demo`。已有数据库不自动迁移；新 schema 的整数 CHECK 不会回写旧库。
Initialization preserves aliases. Seeding modifies mock records only and refuses non-mock sources. Existing schemas are not automatically migrated.

## 配置 / Configuration

| 变量 / Variable | 默认 / Default | 用途 / Meaning |
| --- | --- | --- |
| FIZZ_DATA_DIR | ~/.local/share/fizz-usage-monitor | 私有数据库目录 / Private storage |
| FIZZ_LOW_DATA_MB | 1000 | 正整数 MB，严格低于触发红色 / Positive low threshold |
| FIZZ_STALE_HOURS | 36 | 数据新鲜度小时数 / Freshness hours |
| FIZZ_PORT | 5000 | 本机端口，可由 --port 覆盖 / Loopback port |

`.env.example` 只提供无秘密示例，不会自动加载；请在启动终端 export。路径在应用创建时固定。修改阈值后重新启动。
The example is not automatically loaded. Export configuration in the launch shell; restart after changes.

## 数据与告警规则 / Data and alerts

七张表：accounts、billing_cycles、plan_charges、wallet_snapshots、data_buckets、daily_usage、collection_status。日用量唯一键为 account_id + date；批次及 Wallet 使用账号与快照时间，保留历史。
Seven tables isolate records by account. Daily usage upserts by account/date; snapshots retain history.

30 天合计只累计有记录的日期，同时显示覆盖天数。缺失不是零，不代表完整月用量。最新完整流量快照决定有效总量，运营商延迟修正由每日记录 UPSERT 处理。
Totals cover known records only. Providers must supply complete bucket snapshots and explicit daily usage.

Lite：低于阈值红色；等于阈值不算低流量。有剩余量的批次在 0–3 天内到期黄色；到期日当天有效，已过期批次不计总量。全部过期且记录新鲜时总量为零。失败、缺失、陈旧或不可信时间戳显示未知/过期，旧总量仅供参考。
Lite uses red for low balance, yellow for expiry and green only for reliable sufficient data with no expiry warnings. Collection status and bucket freshness are checked independently.

Lite 使用大字体、基础单列布局，无 CSS Grid/Flex 或脚本；目标兼容 iOS 9 Safari，但尚未完成旧 iPad 实机验证。
Lite targets older Safari with a basic block layout; physical device verification is still required.

## 架构与 Public/Private 边界 / Architecture and boundaries

```text
fizz_monitor/
  db.py           SQLite schema and storage
  providers.py    Provider interface and synthetic MockProvider
  demo.py         Safe mock setup
  app.py          Read-only routes and statistics
  alerts.py       Per-account Lite alerts
  __main__.py     CLI
  templates/      Full and Lite HTML
  static/         Local CSS
```

Public 范围：通用数据库结构、统计、Dashboard、Lite、MockProvider、测试及 Provider 接口。ManualImportProvider 与 BrowserProvider 仅预留接口，调用时抛 NotImplementedError。
Public scope includes storage, statistics, UI, mocks, tests and generic interfaces only.

未来真实 Collector 必须是工作区外的独立 **Private 项目**。密码处理、网页登录自动化、内部 API、Cookie 获取、浏览器状态和真实数据采集不得加入本项目；认证信息、个人数据与账单绝不进入 Git 或日志。
Any future real collector must remain a separate private project. Authentication and personal runtime data do not belong in this repository.

## 测试与发布前审计 / Tests and pre-release audit

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python tools/security_audit.py
.venv/bin/python -m pip check
```

测试使用独立临时 synthetic/mock 数据库，不读取持久化账号数据。覆盖双账号、跨周期、缺失与零、历史修正、事务回滚、日期/权限、只读接口及告警边界。
Tests use isolated temporary synthetic databases and cover account isolation, history, corrections, permissions, read-only routes and alerts.

审计以本地 `PUBLIC_FILES.txt` 为候选公开清单，检查工作区候选内容、Git 索引及已有可达历史，只输出风险类别与路径；不初始化、暂存、提交或连接远程。详见 [SECURITY.md](SECURITY.md)。`PUBLIC_FILES.txt` 和 `PRE_RELEASE_REPORT.md` 是被 Git 排除的内部文件，不随 Public 仓库分发。
The audit is read-only and manifest-based. The manifest and preparation report are local-only ignored files; they are not distributed in the public repository. Human review remains necessary.

从公开仓库克隆后，使用审计工具前需在本地建立并人工核对清单。可从 `git ls-files` 结果生成 `PUBLIC_FILES.txt`，仅列出准备公开的文件，不包含运行数据或上述内部文件；该本地清单不会纳入 Git。
After cloning, create and review a local manifest before running the audit. Use the tracked-file list as a starting point, excluding runtime and internal preparation files. The audit requires this local manifest.

## 当前限制与未来计划 / Limitations and roadmap

当前没有真实 Fizz 自动采集、手工导入格式、每日调度、支付流水、通知推送或用户认证。健康接口代表数据库可读性，不代表运营商采集成功。
Real collection, manual import format, scheduling, payment transactions, notifications and authentication are not implemented.

后续可完善通用手工导入、备份和文档；真实 Collector 的私有开发及集成需单独设计。公开发布与 Git 操作由用户审核决定。
Future generic imports and backup workflows can be designed separately. Private collection and public release require separate review.

## 许可证 / License

本项目采用 [MIT License](LICENSE)。版权声明：Copyright (c) 2026 hhb-coding。完整授权条件及免责声明见 LICENSE 文件。
This project is licensed under the [MIT License](LICENSE). Copyright (c) 2026 hhb-coding. See LICENSE for the full terms and disclaimer.
