<!-- 自动生成 by backend/scripts/regen_docs_index.py，请勿手动编辑 -->
<!-- 改文件后跑：python backend/scripts/regen_docs_index.py -->

# 文档索引

按用途分类，统一查阅入口。最后生成：**2026-05-29**

## 目录概览

| 子目录 | 用途 | 文件数 |
|--------|------|-------|
| [`adr/`](./adr/) | 架构决策记录（ADR） | 29 |
| [`architecture/`](./architecture/) | 系统架构与模块设计 | 4 |
| [`deployment/`](./deployment/) | 部署与运维手册 | 9 |
| [`frontend/`](./frontend/) | 前端专项指南 | 4 |
| [`i18n/`](./i18n/) | 国际化与术语表 | 1 |
| [`operations/`](./operations/) | 运维剧本（健康度/降级/工作流） | 4 |
| [`proposals/`](./proposals/) | 设计建议书（含历史版本） | 8 |
| [`reference/`](./reference/) | 参考手册（变更日志/配置/对齐/DSL） | 5 |
| [`templates/`](./templates/) | 文档/代码模板 | 1 |
| [`uat/`](./uat/) | UAT 验收报告与产物 | 4 |

## 顶层文件

- `requirements.md` — 私有化审计作业与合并系统 — 需求文档（整理版 v10）

## 各子目录详情

### `adr/` — 架构决策记录（ADR）（29 个）

- `adr/ADR-001-auxiliary-dimension-redundant-storage.md` — ADR-001：辅助维度冗余存储模型
- `adr/ADR-002-ledger-view-refactor.md` — ADR-002：账表导入可见性视图化重构（B' 架构）
- `adr/ADR-003-ledger-import-recovery-playbook.md` — ADR-003: Ledger Import Recovery Playbook
- `adr/ADR-004-ledger-activate-isolation.md` — ADR-004: Ledger Activate Transaction Isolation
- `adr/ADR-005-async-activate.md` — ADR-005: 异步 Activate — 用户不等 200 万行 metadata 切换
- `adr/ADR-006-sse-vs-polling-import-progress.md` — ADR-006: SSE vs 轮询 — 导入进度追踪
- `adr/ADR-007-note-triple-format-source-of-truth.md` — ADR-007: 附注三式联动 — `DisclosureNote.table_data` 唯一真源
- `adr/ADR-008-note-cell-mode-persistence.md` — ADR-008: 附注单元格 三态模式持久化（auto / manual / locked）
- `adr/ADR-009-gt-word-template-style-namespace.md` — ADR-009: 致同 Word 导出 — `GTNote*` 样式命名空间隔离
- `adr/ADR-010-note-custom-template-versioning.md` — ADR-010: 自定义附注模板的版本化与回滚策略
- `adr/ADR-011-note-dynamic-row-column-engine.md` — ADR-011: 附注动态行/列引擎
- `adr/ADR-012-note-wp-data-multi-source-fallback.md` — ADR-012: 附注 wp_data 多源 fallback 链
- `adr/ADR-013-note-auto-trim-v2-three-level.md` — ADR-013: 附注 auto_trim v2 三级裁剪
- `adr/ADR-014-note-jinja-paragraph-engine.md` — ADR-014: 附注文字段落 Jinja 模板引擎
- `adr/ADR-015-group-note-baseline-multi-level.md` — ADR-015: 集团附注模板基线多层级 lineage
- `adr/ADR-016-note-collaboration-lock-integration.md` — ADR-016: 附注章节级协作锁集成
- `adr/ADR-017-consol-note-aggregation-service.md` — ADR-017: 合并附注汇总服务
- `adr/ADR-018-consol-elimination-rules-registry.md` — ADR-018: 合并附注内部抵销规则注册器
- `adr/ADR-019-note-section-numbering-restructure.md` — ADR-019: 附注章节编号体系重构（section_number → section_id + level + parent + ...
- `adr/ADR-020-note-section-5-level-format-registry.md` — ADR-020: 章节序号 5 级层级格式注册器
- `adr/ADR-021-soe-listed-template-conversion.md` — ADR-021: 国企↔上市附注模板丝滑切换
- `adr/ADR-022-note-offline-distribution.md` — ADR-022: 附注离线分发与一键导入
- `adr/ADR-023-consol-disclosure-v2-full-section-set.md` — ADR-023: 合并附注 V2 完整章节集（180 章节）
- `adr/ADR-024-d6-vs-alembic-selection.md` — ADR-024: 数据库迁移系统选型 — D6 SQL 替代 Alembic
- `adr/ADR-025-exec-driver-sql-bind-bypass.md` — ADR-025: 迁移 SQL 用 exec_driver_sql 绕开 SQLAlchemy bind 解析
- `adr/ADR-026-repo-frontend-layout-selection.md` — ADR-026: 仓库前端 layout 选型
- `adr/ADR-027-git-hook-toolchain-selection.md` — ADR-027: git hook 工具链选型
- `adr/ADR-028-default-branch-main-over-master.md` — ADR-028: 默认分支 main 替代 master
- `adr/INDEX.md` — ADR 索引

### `architecture/` — 系统架构与模块设计（4 个）

- `architecture/global-linkage-proposal.md` — 全局联动架构改进方案
- `architecture/ledger-import-v2.md` — 账表导入 v2 引擎架构文档
- `architecture/penetration-map.md` — 穿透闭环路径文档
- `architecture/service-dependency.md` — 后端服务依赖图（MT-5）

### `deployment/` — 部署与运维手册（9 个）

- `deployment/f-cycle-notes.md` — F 采购存货循环 — 部署注意事项
- `deployment/kubernetes-probes.md` — Kubernetes Liveness / Readiness Probe 配置
- `deployment/mineru.md` — MinerU 部署指南
- `deployment/phase8/api-reference.md` — Phase 8 API 文档
- `deployment/phase8/deployment.md` — Phase 8 部署文档
- `deployment/phase8/guide.md` — Phase 8 综合指南（API + 部署 + 用户手册）
- `deployment/phase8/user-guide.md` — Phase 8 用户手册
- `deployment/smoke-test-checklist.md` — 发版前冒烟测试清单
- `deployment/tenant-id-migration.md` — tenant_id 渐进迁移计划

### `frontend/` — 前端专项指南（4 个）

- `frontend/component-usage.md` — GT 平台组件选型指南
- `frontend/css-variable-audit.md` — CSS 变量覆盖率审计报告
- `frontend/loading-pattern.md` — 加载状态规范文档
- `frontend/workpaper-side-panel.md` — WorkpaperSidePanel 使用指南

### `i18n/` — 国际化与术语表（1 个）

- `i18n/business-glossary.md` — 业务术语中英对照表

### `operations/` — 运维剧本（健康度/降级/工作流）（4 个）

- `operations/event-cascade-health.md` — 事件级联健康度运维指南
- `operations/git-workflow.md` — Git 工作流（repo-git-workflow-unification spec）
- `operations/time-machine-capacity-planning.md` — 时光机快照容量规划 — V3 Req 11.9
- `operations/todo-inventory-2026-05-29.md` — TODO/FIXME 清单（2026-05-29 全仓扫描）

### `proposals/` — 设计建议书（含历史版本）（8 个）

- `proposals/disclosure-note-improvement-v2.md` — 附注模块改进建议（v2.0）
- `proposals/ledger-import-priority.md` — 账表导入智能优先落地实施方案（权威整合版）
- `proposals/platform-global-2026-05-21.md` — 审计平台全局建议书
- `proposals/refinement-v1.md` — 审计平台全局打磨建议 v1（深度版）
- `proposals/refinement-v2.md` — 审计平台全局打磨建议 v2（深度续篇）
- `proposals/refinement-v3-2026-05-16.md` — refinement-v3-2026-05-16
- `proposals/refinement-v3.md` — 致同审计作业平台 · 全局深度复盘建议书 v3.0
- `proposals/workpaper-development-v2.md` — 审计底稿系统深度开发方案（重构版）

### `reference/` — 参考手册（变更日志/配置/对齐/DSL）（5 个）

- `reference/api-changelog.md` — API 端点变更日志
- `reference/configuration.md` — 配置中心参考文档（CONFIGURATION_REFERENCE）
- `reference/explain-analyze-view.md` — EXPLAIN ANALYZE — 账表四表查询改造前后对比
- `reference/frontend-backend-alignment.md` — 前后端联动测试 — 关键端点 Response Checklist
- `reference/note-formula-dsl.md` — 附注公式 DSL — 完整语法参考

### `templates/` — 文档/代码模板（1 个）

- `templates/NEW_API_ENDPOINT.md` — 新增 API 端点"三件套"模板

### `uat/` — UAT 验收报告与产物（4 个）

- `uat/disclosure-note-uat-report-2026-05-27.md` — 附注模块 v2.0 UAT 验收报告（F-1）
- `uat/note-spec-uat-2026-05-28.md` — 附注模块全维度增强 UAT 报告
- `uat/disclosure-note-uat-heping-2025.docx` — disclosure-note-uat-heping-2025.docx
- `uat/disclosure-note-uat-shouqi-zuche-2025.docx` — disclosure-note-uat-shouqi-zuche-2025.docx

## 维护规约

- 新增文档放对应子目录，不要平铺到 `docs/` 根（仅 `requirements.md` / `README.md` 例外）
- 文件名：英文小写 + 连字符（如 `event-cascade-health.md`）
- 文档头部加 `# 标题` 一级标题（脚本提取作为索引说明）
- 新增子目录后在 `regen_docs_index.py` 的 `SUBDIR_DESC` 字典补用途
- 改完跑 `python backend/scripts/regen_docs_index.py` 重生成索引
