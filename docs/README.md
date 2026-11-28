# 文档索引

按用途分类，统一查阅入口。最后更新：**2026-07-19**

## 目录概览

| 子目录 | 用途 | 说明 |
|--------|------|------|
| [`acnr/`](./acnr/) | ACNR 地址坐标名称库 | 规则冻结、贡献指南、fixtures/schemas |
| [`adr/`](./adr/) | 架构决策记录（ADR） | 56 条决策（通用32 + 合并13 + 公式2 + 报表1），含 INDEX.md |
| [`architecture/`](./architecture/) | 系统架构 | 服务依赖图、规模快照、穿透图、Ledger 等 |
| [`contracts/`](./contracts/) | 接口与数据契约 | 程序链（裁剪 → 生成 → 委派 → 可见性）JSON Schema、共享用例、OpenAPI 子集，供 Java 版实现复用 |
| [`deployment/`](./deployment/) | 部署与运维 | 冒烟清单、K8s映射、零停机、启动手册 |
| [`frontend/`](./frontend/) | 前端规范 | 组件用法、CSS变量、显示偏好、加载态、侧面板 |
| [`i18n/`](./i18n/) | 术语与国际化 | 审计业务术语表 |
| [`operations/`](./operations/) | 运维剧本 | 依赖恢复、事件级联、Git工作流、容量规划 |
| [`proposals/`](./proposals/) | 设计建议书 | 合伙人复盘、模块状态评估、改进提案（含历史版本） |
| [`reference/`](./reference/) | 参考手册 | API变更日志、契约、配置、DSL、数据语义 |
| [`templates/`](./templates/) | 文档模板 | 新 API 端点模板 |
| [`uat/`](./uat/) | UAT 验收 | D1/D2/附注模块验收报告 |

## 顶层文件

| 文件 | 说明 |
|------|------|
| `workpaper-developer-guide.md` | 底稿组件开发指南（Runtime Boundary 模式） |
| `audit-project-workflow.md` | 审计项目流程：建项 → 导入 → 底稿 → 报表附注 → 签发 → 归档（2026-11-18） |
| `audit-platform-function-rules.md` | 整体功能规则：按 A~T 二十个模块拆分的业务规则与已知缺口（2026-11-18） |
| `database-tables.md` | 数据表结构概览：374 张 ORM 表 + 21 张只由迁移建的表，按 17 个业务域分组、核心表关系图（2026-11-18） |
| `database-tables-columns.md` | 数据表字段明细：每张表每个字段的中文名、说明、取值、类型、外键（2026-11-20 补中文说明） |
| `database-relationships.md` | 表关联关系分析：连接逻辑、外键与业务键、核心链路 JOIN 条件、配置依赖、风险（2026-11-18） |
| `database-relationships-fk.md` | 全部 831 条外键约束与无外键的引用列明细（2026-11-18） |
| `data-processing-rules.md` | 数据处理规则：Excel 解析落库、借贷方向与跨表计算、余额表到报表的映射、端到端示例（2026-11-18） |

## 使用说明

- **新建 ADR**：按 `ADR-{序号}-{kebab-slug}.md` 命名，写入 `adr/`，更新 `adr/INDEX.md`
- **新建提案**：写入 `proposals/`，标注日期和基线分支
- **新建运维剧本**：写入 `operations/`
- **发布前**：执行 `deployment/platform-smoke-checklist.md` 三层检查
