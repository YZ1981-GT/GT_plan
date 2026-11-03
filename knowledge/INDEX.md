# GT_plan 本地知识库索引（知识地图）

> 知识库三层结构。本文件是唯一入口地图，新增知识须同步加一行索引。
> 检索：Claude Code 每次提问由 `.claude/kb/kb_search.py`（BM25）自动检索注入 `[KB]` 片段。

## 一、AI 会话沉淀（knowledge/sessions/）

> 重要决策 / Bug 根因 / 新约定按 `YYYYMMDD-主题.md` 追加，格式见 CLAUDE.md。

| 日期 | 主题 | 文件 |
|------|------|------|
| 2026-11-03 | 本地知识库搭建（BM25 + hook 自动注入，含 Windows 编码坑） | [sessions/20261103-本地知识库搭建.md](sessions/20261103-本地知识库搭建.md) |

## 二、外部导入资料（knowledge/external/）

> 外部目录（如桌面「税务平台」）的 office 文档经 `kb_convert.py` 转换入库，md 头部 `source:` 可回溯原文件。

| 主题 | 来源 | 位置 |
|------|------|------|
| CITAR 税审平台（PRD/功能清单/技术评估/底稿取数逻辑等 ~71 个 docx/xlsx/pdf） | `C:\Users\baiji\Desktop\文件\税务平台` | `external/税务平台/` |
| （暂无） | | |

## 三、项目内置知识源（仓库内，直接检索）

| 知识域 | 位置 | 说明 |
|--------|------|------|
| 平台总览 | `README.md` | 技术栈、核心功能、规模统计 |
| 架构与边界 | `.kiro/steering/architecture.md`、`.kiro/steering/service-boundaries.md`、`.kiro/steering/domain-boundaries.md` | 服务架构、模块边界 |
| 开发规范铁律 | `.kiro/steering/conventions.md` | spec 三件套、UI 中文化、测试要求 |
| 开发历史 | `.kiro/steering/dev-history.md` | 演进记录 |
| 术语表 | `.kiro/steering/glossary.md` | 审计循环代号 A–S、领域术语 |
| 架构专题 | `docs/architecture/` | 账表导入 v2、穿透地图、服务依赖账本 |
| 运维手册 | `docs/runbooks/`、`docs/operations/`、`docs/deployment/` | 启动、部署、运维 |
| 底稿开发指南 | `docs/workpaper-developer-guide.md` | 底稿模板开发 |
| ACNR 规则 | `docs/acnr/` | 科目注释规则 |
| 案例/模版 | `docs/案例/`、`docs/模版/` | 历史案例与文档模版 |
| 提案与 ADR | `docs/proposals/`、`docs/adr/` | 技术决策记录 |
