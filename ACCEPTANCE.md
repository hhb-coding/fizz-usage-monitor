# v0.1.0 验收记录 / Acceptance

这是可公开的功能验收摘要，不包含某台机器的操作记录、运行数据库路径或部署信息。
A portable acceptance summary, not a host-specific operations log.

| 检查 / Check | 结果 / Result |
| --- | --- |
| 双账号 / Accounts | 稳定 ID、可修改别名、数据隔离、不保存登录邮箱 |
| 数据模型 / Schema | 七张表，整数 cents/MB，唯一约束、事务 UPSERT |
| 历史 / History | Toronto 完整自然日、跨周期、缺失与零值、30 天显示和更早历史保存 |
| 财务和流量 / Summaries | mock Wallet、月费、付款日期、五类批次及有效期 |
| 完整 Dashboard / Full | 摘要、趋势、表格、最后成功、读取失败/过期提示 |
| Lite | 大字体基础 HTML/CSS，无 JS/CDN；实际 iOS 9 设备验证待完成 |
| 告警 / Alerts | 默认严格低于 1000 MB 红色，0–3 天到期黄色，未知或陈旧不报正常 |
| Provider | Mock 已实现；手工导入和浏览器仅预留接口 |
| 数据安全 / Storage | 工作区外私有目录、权限检查、未知已有数据拒绝覆盖 |
| 测试 / Tests | 43 项 unittest，隔离临时 synthetic/mock 数据，不接触持久化数据库 |

页面和接口通过 Flask 测试客户端验证，不等同于旧设备实机测试或真实 HTTP 部署测试。数据库重新打开测试验证持久化逻辑，不等同于实际操作系统重启测试。
Test-client and reopen checks do not substitute for real-device or OS reboot validation.

重复启动使用现有模拟数据，不自动刷新采集时间。旧数据可能正确显示陈旧状态。全部过期的有效总量为零；无记录则未知。新 schema 的 CHECK 约束不自动迁移已有数据库。
Old mock data can be stale; existing schemas are not automatically migrated.

安全边界见 [SECURITY.md](SECURITY.md)；安装、测试及通用启动命令见 [README.md](README.md)。内部发布前报告仅本地保留，不随 Public 仓库分发。
See the public security and setup documentation. The internal preparation report stays local; no remote publication is performed by acceptance checks.
