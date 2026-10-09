# 安全与公开代码边界 / Security and public boundary

此项目仅处理 synthetic/mock 演示数据，不实现真实登录、采集或认证信息存储。
This public candidate handles synthetic/mock data only and contains no real collector.

## 私有运行数据 / Private runtime data

数据目录必须位于 Git 工作区之外，目录 700、数据库 600。不要存登录邮箱、密码、Cookie、Token、Session、浏览器 profile、真实账单、真实用量或截图。本项目不需要这些资料。
Use private external storage; credentials and personal records are unnecessary for this version.

`.gitignore` 覆盖环境/真实配置、数据库及 sidecar、备份、日志、缓存、虚拟环境、认证/profile 文件、截图和常见个人文档。允许 `.env.example`、代码、测试及生成式 mock 数据。文件扩展名规则不能识别任意文本中的个人数据，不能移除已跟踪文件或历史秘密。
Ignore patterns prevent accidental additions only; they are not content filters or history cleanup.

未来 Collector 必须独立 Private，不能以子目录、子模块、打包资源或依赖副本的方式带入 Public 候选文件。认证状态及个人运行数据保持在其独立私有目录。
Future real collection must stay in a separate private repository and storage boundary.

## 日志与访问 / Logging and access

接口错误使用安全诊断码，不返回底层异常、数据库内容或认证载荷。不要在 URL 查询参数、别名或配置中放入秘密；开发服务器的访问日志可能记录请求路径。访问日志不应纳入 Git。
Safe errors do not make arbitrary request URLs safe to log. Never place secrets in URLs or aliases.

默认仅回环监听，不提供账号认证或生产部署方案。HomeLab 集成必须在以后单独审核，不能把本地开发服务器直接暴露给网络。
The local server is read-only and unauthenticated; production access is outside this version's scope.

## 审计 / Audit

`PUBLIC_FILES.txt` 是本地候选清单，不代表文件已暂存；它和内部 `PRE_RELEASE_REPORT.md` 被 Git 排除，不分发到 Public 仓库。公开克隆需先建立并复核本地清单，再运行工具。`tools/security_audit.py` 只读检查：

- 候选公开文件内容、未追踪文件与清单差异。
- 常见邮箱、电话号码、IP、主机专用路径及凭据模式；报告只输出类别与路径。
- 应用源代码中的网络/浏览器客户端导入。
- 忽略规则，以及索引和可达历史中的文件类别与内容（如存在）。

The audit reports categories and paths without printing matched values. It does not initialize or modify Git metadata or read external runtime directories. Ignored environment/cache folders are inventoried through Git exclusions, not scanned as public source.
The manifest and preparation report stay local and ignored. A public clone must supply its own reviewed local manifest before running the audit.

限制：模式扫描可能漏报或误报，不能证明所有主机网络活动、已删除但不可达的 Git 对象、任意秘密格式或第三方软件包都安全。发布前必须人工审核最终 staged diff、提交身份、许可证及仓库公开设置。
Pattern scanning is bounded. Review the final staged content, commit identity, license and visibility manually before publication.

## 发现问题 / Findings

如发现真实个人数据或秘密，停止发布准备，仅报告类别及路径；不要复制匹配值到 issue、日志或报告，不擅自删除数据。泄露处置及历史清理需所有者单独批准；凭据应由所有者在私有渠道处理。
Stop on genuine sensitive findings. Do not include secret values in reports or public issues, and do not delete data without approval.

项目尚未发布，也没有专门的私有漏洞报告渠道。不要在公开 issue 中提交真实账号、账单或认证信息。
No public disclosure channel is configured; never post personal or authentication data publicly.
