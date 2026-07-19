# 文档索引

按用途分类，统一查阅入口。最后更新：**2026-07-19**

## 目录概览

| 子目录 | 用途 | 说明 |
|--------|------|------|
| [`acnr/`](./acnr/) | ACNR 地址坐标名称库 | 规则冻结、贡献指南、fixtures/schemas |
| [`adr/`](./adr/) | 架构决策记录（ADR） | 56 条决策（通用32 + 合并13 + 公式2 + 报表1），含 INDEX.md |
| [`architecture/`](./architecture/) | 系统架构 | 服务依赖图、规模快照、穿透图、Ledger 等 |
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

## 使用说明

- **新建 ADR**：按 `ADR-{序号}-{kebab-slug}.md` 命名，写入 `adr/`，更新 `adr/INDEX.md`
- **新建提案**：写入 `proposals/`，标注日期和基线分支
- **新建运维剧本**：写入 `operations/`
- **发布前**：执行 `deployment/platform-smoke-checklist.md` 三层检查
