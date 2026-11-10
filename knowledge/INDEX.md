# GT_plan 本地知识库索引（知识地图）

> 知识库三层结构。本文件是唯一入口地图，新增知识须同步加一行索引。
> 检索：Claude Code 每次提问由 `.claude/kb/kb_search.py`（BM25）自动检索注入 `[KB]` 片段。
> 转换：外部 office 文档用 `.claude/kb/kb_convert.py` 增量转 md（每日 08:30 定时任务自动跑）。

## 一、AI 会话沉淀（knowledge/sessions/）

> 重要决策 / Bug 根因 / 新约定按 `YYYYMMDD-主题.md` 追加，格式见 CLAUDE.md。

| 日期 | 主题 | 文件 |
|------|------|------|
| 2026-11-03 | 本地知识库搭建（BM25 + hook 自动注入，含 Windows 编码坑） | [sessions/20261103-本地知识库搭建.md](sessions/20261103-本地知识库搭建.md) |
| 2026-11-10 | 知识库重建（未跟踪文件被删事件 + git 入库决策） | [sessions/20261110-知识库重建.md](sessions/20261110-知识库重建.md) |
| 2026-11-10 | 外部文档全量入库（69 office + 14 md，覆盖度 100%） | [sessions/20261110-外部文档全量入库.md](sessions/20261110-外部文档全量入库.md) |

## 二、外部导入资料（knowledge/external/）

> 外部目录（如桌面「税务平台」）的 office 文档经 `kb_convert.py` 转换入库，md 头部 `source:` 可回溯原文件。

| 主题 | 来源 | 位置 |
|------|------|------|
| CITAR 税审平台 office 文档全量（**69 个**：docx 22 / xlsx 39 / pdf 8，含真实案例资料、底稿取数规则填制、科目清单_完整版、税审底稿 206 表、CPAS 数据链路） | `C:\Users\baiji\Desktop\文件\税务平台` | `external/税务平台/` |
| 外部知识 md（**14 个**，直接检索不转换：CITAR tax-attestation-platform 与 gt-tax-working-paper 的 spec 三件套、AI知识库与问答业务设计 V1.0、CITAR_kbqa README、FunASR 部署与财税热词表、Qwen 纪要 Prompt、workpaper-calculation） | 同上 | 原件位于外部目录，由 `kb_search.py` 的 `EXTERNAL_DIRS` 直接扫描 |

> 覆盖度：office 文档 69/69 已转换（失败 0）；md 14/14 已纳入检索。合计 **83 份**外部资料可被 `[KB]` 命中。

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
