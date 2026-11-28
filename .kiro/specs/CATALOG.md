# Spec 功能域目录（CATALOG）

> 本项目 `_archive/` 按开发时间批次归档（append-only 审计轨迹），
> 本目录提供**按功能域的多维视图**：一个 spec 可同属多个域。
>
> 本文件由 `backend/scripts/analyze/build_spec_catalog.py` 生成，**请勿手工编辑**。
> 改域规则：分类模式 → `DOMAINS`；特例逐 spec 覆盖 → `OVERRIDES`；版式 → `render()`。
> 重新生成：`python backend/scripts/analyze/build_spec_catalog.py`
> 漂移校验：`python backend/scripts/analyze/build_spec_catalog.py --check`（不一致 exit 2，可入 CI）
>
> **统计**：全部 spec **814** = 活跃 **4** + 已归档 **810**；
> 功能域 **12**；未归类 **0**。

<a id="top"></a>
## 一、功能域概览

| 功能域 | spec 数 | 代码锚点 | 前端位置 |
| --- | --- | --- | --- |
| **[公式管理 / 公式推送 / 取数链](#domain-formula)** | 51 | `backend/app/services/formula_push` | `audit-platform/frontend/src/components/formula/` |
| **[附注 / 披露表 / 底稿→附注同步](#domain-note)** | 124 | `backend/app/routers/disclosure_notes.py` | `audit-platform/frontend/src/views/composables/noteDisclosureReverseJump.ts` |
| **[合并 / 集团 / 三码企业树](#domain-consol)** | 31 | `backend/app/routers/consolidation.py` | `audit-platform/frontend/src/views/ConsolidationIndex.vue` |
| **[底稿双向回写 / OO 在线编辑](#domain-writeback)** | 104 | `backend/app/services/workpaper_sync` | — |
| **[A~S 循环底稿业务（科目/程序/检查表）](#domain-cycle)** | 485 | `backend/app/services/auto_data_resolvers` | — |
| **[凭证 / 序时账 / 抽样审计](#domain-voucher)** | 26 | `backend/app/services/voucher_identity.py` | `audit-platform/frontend/src/components/workpaper/voucher-sampling/` |
| **[附件 / 证据 / 归档与交付件](#domain-attachment)** | 26 | `backend/app/services/attachment_service.py` | `audit-platform/frontend/src/components/deliverable/` |
| **[知识库 / AI / LLM / OCR](#domain-ai)** | 23 | `backend/app/services/ai_chat` | `audit-platform/frontend/src/composables/useKnowledge.ts` |
| **[ACNR 地址坐标名称库 / 交叉引用](#domain-acnr)** | 11 | `backend/app/services/acnr` | `audit-platform/frontend/src/components/formula/CellSelector.vue` |
| **[程序裁剪 / 生成 / 委派 / 权限](#domain-procedure)** | 29 | `backend/app/services/procedure_trim_engine.py` | — |
| **[平台基建 / 性能 / 治理 / 发布](#domain-platform)** | 157 | `backend/app/core/startup_registry.py` | — |
| **[高级查询 / 全局 7 横切](#domain-global-modules)** | 18 | `backend/app/routers/custom_query.py` | — |
| [（未归类）](#domain-unclassified) | 0 | — | — |

<a id="domain-formula"></a>
## 公式管理 / 公式推送 / 取数链（51 个）

| 状态 | Spec | 进度 | 需求标题 |
| --- | --- | --- | --- |
| 📦已归档 | [`101-note-chain-followup-optimizations`](_archive/101-note-chain-followup-optimizations/requirements.md) ⧉formula | 11/11 | 附注链后续优化 — 需求 |
| 📦已归档 | [`103-note-pull-residual-governance-closure`](_archive/103-note-pull-residual-governance-closure/requirements.md) ⧉consol+formula | 50/50 | 附注取数残留与治理收口 — 需求 |
| 📦已归档 | [`117-consol-note-formula-scope-and-roles`](_archive/117-consol-note-formula-scope-and-roles/requirements.md) ⧉formula | 8/8 | 需求文档：S7　合并附注公式的范围与角色 |
| 📦已归档 | [`119-note-pull-followup-closure`](_archive/119-note-pull-followup-closure/requirements.md) ⧉formula | 25/26 | 附注取数收口后续建议逐项修复 — 需求 |
| 📦已归档 | [`121-formula-provenance-envelope`](_archive/121-formula-provenance-envelope/requirements.md) ⧉note | — | 需求文档：S5　取数结果的来源信封 |
| 📦已归档 | [`140-formula-hub-release-blockers`](_archive/140-formula-hub-release-blockers/requirements.md) ⧉cycle+platform | 14/14 | 需求：公式管理阻断缺陷收口（formula-hub-release-blockers） |
| 📦已归档 | [`141-income-statement-lower-section-formulas`](_archive/141-income-statement-lower-section-formulas/requirements.md) ⧉cycle | 8/8 | 需求文档：S9　利润表净利润以下行的公式补全 |
| 📦已归档 | [`142-formula-management-repair-closure`](_archive/142-formula-management-repair-closure/requirements.md) | 21/21 | 需求：公式管理评估问题逐项修复（formula-management-repair-closure） |
| 📦已归档 | [`143-formula-management-residual-closure`](_archive/143-formula-management-residual-closure/requirements.md) | 7/7 | 需求：公式管理残留安全与可用性收口 |
| 📦已归档 | [`145-formula-e2e-ci-gate`](_archive/145-formula-e2e-ci-gate/requirements.md) ⧉platform | 7/7 | 需求文档：S8　公式 Playwright 规格接入真实运行的 CI |
| 📦已归档 | [`146-formula-template-dual-project-pilot`](_archive/146-formula-template-dual-project-pilot/requirements.md) | 7/7 | 需求文档：S6　公式模板双项目试点 |
| 📦已归档 | [`147-formula-settings-durable-outbox`](_archive/147-formula-settings-durable-outbox/requirements.md) | 8/8 | 需求文档：S4　公式设置的持久化 outbox |
| 📦已归档 | [`148-formula-grammar-resolver-unification`](_archive/148-formula-grammar-resolver-unification/requirements.md) ⧉platform | 11/11 | 需求文档：S1　公式语法与取数器单一来源 |
| 📦已归档 | [`150-formula-writer-ownership-and-stale`](_archive/150-formula-writer-ownership-and-stale/requirements.md) | 8/8 | 需求文档：S3　写入方归属与过期状态机 |
| 📦已归档 | [`155-formula-hub-integrity-closure`](_archive/155-formula-hub-integrity-closure/requirements.md) | 54/54 | 需求文档：公式中枢正确性与安全闭环（formula-hub-integrity-closure） |
| 📦已归档 | [`156-formula-integrity-and-propagation-closure`](_archive/156-formula-integrity-and-propagation-closure/requirements.md) | 10/10 | 公式正确性、编辑安全与传播闭环 |
| 📦已归档 | [`157-check-contract-and-note-executor`](_archive/157-check-contract-and-note-executor/requirements.md) ⧉note | 8/9 | 需求文档：S2　校对契约与附注执行器 |
| 📦已归档 | [`161-note-disclosure-pull-regression-and-headless-backend`](_archive/161-note-disclosure-pull-regression-and-headless-backend/requirements.md) ⧉formula | 19/19 | 附注取数回归修复与披露 builder 后端化 — 需求 |
| 📦已归档 | [`168-note-disclosure-formula-and-consolidation-chain-closure`](_archive/168-note-disclosure-formula-and-consolidation-chain-closure/requirements.md) ⧉consol+formula | 16/16 | 附注披露取数、公式与合并拉数闭环 — 需求 |
| 📦已归档 | [`169-note-table-structure-formula-pull-closure`](_archive/169-note-table-structure-formula-pull-closure/requirements.md) ⧉formula+consol | 42/42 | 附注表格结构、预设公式与合并拉数收口 — 需求 |
| 📦已归档 | [`52-formula-management-ux-improvements`](_archive/52-formula-management-ux-improvements/requirements.md) | 23/23 | 公式管理体验优化 — 需求文档 |
| 📦已归档 | [`58-formula-settings-wiring-closure`](_archive/58-formula-settings-wiring-closure/requirements.md) | 14/14 | 需求文档：公式设置接线收口与 stash 事故抢救（formula-settings-wiring-closure） |
| 📦已归档 | [`59-unified-formula-registry`](_archive/59-unified-formula-registry/requirements.md) | 18/18 | 需求：统一公式注册表（Unified Formula Registry） |
| 📦已归档 | [`60-formula-execution-path-convergence`](_archive/60-formula-execution-path-convergence/requirements.md) | 13/14 | 需求：公式执行路径收敛（Formula Execution Path Convergence） |
| 📦已归档 | [`62-formula-management-deep-optimization`](_archive/62-formula-management-deep-optimization/requirements.md) | 36/36 | 公式管理深度优化 — requirements.md |
| 📦已归档 | [`63-formula-push-subtable-expansion`](_archive/63-formula-push-subtable-expansion/requirements.md) | 19/19 | 公式推送子表级规则扩展 — 需求文档 |
| 📦已归档 | [`70-formula-input-param-completion`](_archive/70-formula-input-param-completion/requirements.md) | 21/21 | 需求：公式输入参数值智能补全 |
| 📦已归档 | [`71-formula-fetch-and-wp-generation-defect-closure`](_archive/71-formula-fetch-and-wp-generation-defect-closure/requirements.md) | 19/19 | 取数结果错误 / 底稿生成流程 / 测试欠账 收口 —— 需求 |
| 📦已归档 | [`83-formula-fetch-followup-defect-closure`](_archive/83-formula-fetch-followup-defect-closure/requirements.md) | 33/34 | 取数口径后续缺陷收口 —— 需求 |
| 📦已归档 | [`chain-closure-phase2-formula-push-engine`](_archive/23-formula-push-engine-complete/chain-closure-phase2-formula-push-engine/requirements.md) ⧉note | 18/18 | 需求：全链条闭环 · 阶段二（公式推送引擎 + 货币资金 E1 全链 canary） |
| 📦已归档 | [`custom-workpaper-formula-binding`](_archive/07-workpaper-slimdown/custom-workpaper-formula-binding/requirements.md) ⧉formula | 58/58 | Requirements Document |
| 📦已归档 | [`formula-engine-unification`](_archive/04-infra-architecture/formula-engine-unification/requirements.md) ⧉platform | 20/20 | 需求文档：formula-engine-unification（公式引擎统一架构） |
| 📦已归档 | [`formula-global-settings-sync`](_archive/55-batch-2026-10-21/formula-global-settings-sync/requirements.md) | 36/36 | 需求文档：公式全局设置、项目适配与一处修改全处生效（formula-global-settings-sync） |
| 📦已归档 | [`formula-management-library`](_archive/05-business-features/formula-management-library/requirements.md) | 92/92 | Requirements Document |
| 📦已归档 | [`formula-management-runtime-closure`](_archive/04-infra-architecture/formula-management-runtime-closure/requirements.md) | 18/18 | Requirements Document |
| 📦已归档 | [`formula-manager-closure`](_archive/55-batch-2026-10-21/formula-manager-closure/requirements.md) | 30/30 | 需求文档：公式管理平台缺陷闭环（formula-manager-closure） |
| 📦已归档 | [`formula-manager-runtime-integrity-closure`](_archive/55-batch-2026-10-21/formula-manager-runtime-integrity-closure/requirements.md) | 29/30 | 需求文档：公式管理运行时完整性闭环 |
| 📦已归档 | [`formula-push-all-subjects-rollout`](_archive/23-formula-push-engine-complete/formula-push-all-subjects-rollout/requirements.md) | 26/26 | 公式推送全科目接入（平台化 + 分批铺开） |
| 📦已归档 | [`formula-push-balance-adj-batch-c`](_archive/23-formula-push-engine-complete/formula-push-balance-adj-batch-c/requirements.md) | 11/11 | 需求：公式推送批 C — 资产负债类审定表族 |
| 📦已归档 | [`formula-push-income-stmt-batch-d`](_archive/23-formula-push-engine-complete/formula-push-income-stmt-batch-d/requirements.md) | 7/7 | 需求：公式推送批 D — 损益类审定表 |
| 📦已归档 | [`formula-push-note-rollout-batch-c`](_archive/23-formula-push-engine-complete/formula-push-note-rollout-batch-c/requirements.md) ⧉note | 7/7 | 公式推送附注铺开 · 批 C：已注册码加附注规则 |
| 📦已归档 | [`formula-push-note-rollout-batch-d`](_archive/23-formula-push-engine-complete/formula-push-note-rollout-batch-d/requirements.md) ⧉note | 8/8 | 公式推送附注铺开 · 批 D：简单型族 binding |
| 📦已归档 | [`formula-push-note-rollout-batch-e`](_archive/23-formula-push-engine-complete/formula-push-note-rollout-batch-e/requirements.md) ⧉note | 16/16 | 需求：公式推送批 E — 附注推送铺开 |
| 📦已归档 | [`formula-push-note-row-matching`](_archive/41-formula-push-note-skip-and-row-matching/formula-push-note-row-matching/requirements.md) ⧉note | 39/39 | 公式推送附注行匹配增强（formula-push-note-row-matching） |
| 📦已归档 | [`formula-push-note-skip-reduction`](_archive/41-formula-push-note-skip-and-row-matching/formula-push-note-skip-reduction/requirements.md) ⧉note | 30/30 | 公式推送附注跳过减少（formula-push-note-skip-reduction） |
| 📦已归档 | [`formula-push-tier-a-anchor-batch-b`](_archive/23-formula-push-engine-complete/formula-push-tier-a-anchor-batch-b/requirements.md) | 12/12 | 需求：公式推送批 B — Tier A 单公式锚点族 |
| 📦已归档 | [`formula-push-user-custom-cross-module`](_archive/23-formula-push-engine-complete/formula-push-user-custom-cross-module/requirements.md) | 11/11 | 需求：用户自定义公式 — 跨表格 / 跨科目 / 跨模块 |
| 📦已归档 | [`formula-row-name-alignment-confirmation`](_archive/05-business-features/formula-row-name-alignment-confirmation/requirements.md) | 15/15 | Requirements Document |
| 📦已归档 | [`formula-runtime-convergence`](_archive/04-infra-architecture/formula-runtime-convergence/requirements.md) | 18/18 | Requirements Document |
| 📦已归档 | [`report-config-account-code-integrity`](_archive/04-infra-architecture/report-config-account-code-integrity/requirements.md) ⧉cycle | 12/12 | Requirements Document |
| 📦已归档 | [`report-config-baseline`](_archive/04-infra-architecture/report-config-baseline/requirements.md) ⧉cycle | 12/12 | 需求文档：report-config-baseline（报表配置主模板回填 + 联动） |

[↑ 返回概览](#top)

<a id="domain-note"></a>
## 附注 / 披露表 / 底稿→附注同步（124 个）

| 状态 | Spec | 进度 | 需求标题 |
| --- | --- | --- | --- |
| 📦已归档 | [`101-note-chain-followup-optimizations`](_archive/101-note-chain-followup-optimizations/requirements.md) ⧉formula | 11/11 | 附注链后续优化 — 需求 |
| 📦已归档 | [`103-note-pull-residual-governance-closure`](_archive/103-note-pull-residual-governance-closure/requirements.md) ⧉consol+formula | 50/50 | 附注取数残留与治理收口 — 需求 |
| 📦已归档 | [`119-note-pull-followup-closure`](_archive/119-note-pull-followup-closure/requirements.md) ⧉formula | 25/26 | 附注取数收口后续建议逐项修复 — 需求 |
| 📦已归档 | [`121-formula-provenance-envelope`](_archive/121-formula-provenance-envelope/requirements.md) ⧉note | — | 需求文档：S5　取数结果的来源信封 |
| 📦已归档 | [`157-check-contract-and-note-executor`](_archive/157-check-contract-and-note-executor/requirements.md) ⧉note | 8/9 | 需求文档：S2　校对契约与附注执行器 |
| 📦已归档 | [`158-consol-note-save-integrity-closure`](_archive/158-consol-note-save-integrity-closure/requirements.md) ⧉note | 39/39 | 合并附注保存完整性收口 — 需求 |
| 📦已归档 | [`161-note-disclosure-pull-regression-and-headless-backend`](_archive/161-note-disclosure-pull-regression-and-headless-backend/requirements.md) ⧉formula | 19/19 | 附注取数回归修复与披露 builder 后端化 — 需求 |
| 📦已归档 | [`168-note-disclosure-formula-and-consolidation-chain-closure`](_archive/168-note-disclosure-formula-and-consolidation-chain-closure/requirements.md) ⧉consol+formula | 16/16 | 附注披露取数、公式与合并拉数闭环 — 需求 |
| 📦已归档 | [`169-note-table-structure-formula-pull-closure`](_archive/169-note-table-structure-formula-pull-closure/requirements.md) ⧉formula+consol | 42/42 | 附注表格结构、预设公式与合并拉数收口 — 需求 |
| 📦已归档 | [`22-disclosure-multitable-refresh-and-edit-writeback`](_archive/22-disclosure-multitable-refresh-and-edit-writeback/requirements.md) ⧉note | 8/8 | 附注多表刷新与编辑反写闭环 |
| 📦已归档 | [`48-consol-note-detail-template-and-mapping`](_archive/48-consol-note-detail-template-and-mapping/requirements.md) | 36/38 | 合并附注明细模板与多企业行映射规则 — 需求 |
| 📦已归档 | [`49-disclosure-note-template-word-realignment`](_archive/49-disclosure-note-template-word-realignment/requirements.md) | 36/38 | 附注模板按四版 Word 重新对齐 + 存量项目修复 + 编辑留痕补齐 + 大模型改为手动 + 和平药房重建 |
| 📦已归档 | [`50-disclosure-note-doc-upload-and-batch-fill`](_archive/50-disclosure-note-doc-upload-and-batch-fill/requirements.md) | 61/61 | 附注正文导入、批量编制与集团内容模板 |
| 📦已归档 | [`57-consol-note-mapping-reuse-and-reference-push`](_archive/57-consol-note-mapping-reuse-and-reference-push/requirements.md) | 23/29 | 合并附注映射规则复用与标准科目参考下推 |
| 📦已归档 | [`61-backend-disclosure-payload-builder`](_archive/61-backend-disclosure-payload-builder/requirements.md) | 26/26 | 后端披露表 payload builder — 需求文档 |
| 📦已归档 | [`65-consol-note-pull-from-standalone`](_archive/65-consol-note-pull-from-standalone/requirements.md) | 12/12 | 合并附注从单体附注拉取数据 |
| 📦已归档 | [`66-consol-note-template-push-to-subsidiaries`](_archive/66-consol-note-template-push-to-subsidiaries/requirements.md) | 12/12 | 集团级附注披露模板下推 |
| 📦已归档 | [`68-note-data-from-disclosure-table`](_archive/68-note-data-from-disclosure-table/requirements.md) | 30/31 | 附注数据统一从披露表获取 — 需求文档 |
| 📦已归档 | [`69-note-template-header-alignment-between-standalone-and-consol`](_archive/69-note-template-header-alignment-between-standalone-and-consol/requirements.md) | 7/7 | 单体与合并附注模板列名统一对齐 |
| 📦已归档 | [`75-note-pull-header-formula-closure`](_archive/75-note-pull-header-formula-closure/requirements.md) | 25/25 | 附注取数 / 多级表头 / 公式管理收口 — 需求 |
| 📦已归档 | [`84-consol-note-header-library-and-node-reaggregate`](_archive/84-consol-note-header-library-and-node-reaggregate/requirements.md) | 87/87 | 合并附注标题行库 + 节点子树重新汇总 — 需求 |
| 📦已归档 | [`a1-15-disclosure-checklist`](_archive/13-2026-06-29-batch/a1-15-disclosure-checklist/requirements.md) ⧉cycle | 43/43 | Requirements Document |
| 📦已归档 | [`advanced-query-disclosure-integration-hardening`](_archive/04-infra/advanced-query-disclosure-integration-hardening/requirements.md) ⧉note | 36/36 | Requirements Document |
| 📦已归档 | [`ai-chat-adopt-and-note-target-picker`](_archive/55-batch-2026-10-21/ai-chat-adopt-and-note-target-picker/requirements.md) ⧉note | 15/16 | 需求：AI 面板「采纳」「转存笔记」选择目标位置与文件 |
| 📦已归档 | [`applicable-standards-frontend-wiring`](_archive/08-disclosure-notes/applicable-standards-frontend-wiring/requirements.md) | 17/17 | Requirements Document |
| 📦已归档 | [`applicable-standards-runtime-and-sync-guard`](_archive/08-disclosure-notes/applicable-standards-runtime-and-sync-guard/requirements.md) ⧉platform | 26/26 | Requirements Document |
| 📦已归档 | [`chain-closure-phase1-root-cause-fixes`](_archive/06-engineering-governance/chain-closure-phase1-root-cause-fixes/requirements.md) | 10/10 | 需求：四表→公式→底稿→报表→附注 全链条闭环 · 阶段一（四个一行级根因） |
| 📦已归档 | [`chain-closure-phase2-formula-push-engine`](_archive/23-formula-push-engine-complete/chain-closure-phase2-formula-push-engine/requirements.md) ⧉note | 18/18 | 需求：全链条闭环 · 阶段二（公式推送引擎 + 货币资金 E1 全链 canary） |
| 📦已归档 | [`chain-closure-phase3-push-rollout`](_archive/25-2026-10-06-playwright-verified/chain-closure-phase3-push-rollout/requirements.md) | 15/22 | 需求：全链条闭环 · 阶段三（推送引擎入库 + 单一写入方收口 + 铺开） |
| 📦已归档 | [`consol-disclosure-note-persistence`](_archive/09-consolidation-phases/consol-disclosure-note-persistence/requirements.md) ⧉note | 9/9 | Requirements Document |
| 📦已归档 | [`consol-note-node-refresh-and-formula-orchestration`](_archive/25-2026-10-06-playwright-verified/consol-note-node-refresh-and-formula-orchestration/requirements.md) ⧉note | 28/28 | 需求文档：合并附注节点级自动刷新与公式编排 |
| 📦已归档 | [`consol-note-refresh-multi-header-fix`](_archive/24-consol-note-and-key-isolation/consol-note-refresh-multi-header-fix/requirements.md) ⧉note | 4/4 | 完善合并附注刷新对多级表头的列定位 |
| 📦已归档 | [`consol-note-tab-request-safety-and-identity`](_archive/55-batch-2026-10-21/consol-note-tab-request-safety-and-identity/requirements.md) ⧉note | 11/11 | 需求：合并附注页请求安全与身份校验（ConsolNoteTab CP-05） |
| 📦已归档 | [`consol-note-template-header-unification`](_archive/24-consol-note-and-key-isolation/consol-note-template-header-unification/requirements.md) ⧉note+platform | 7/7 | 统一合并附注模板与单体附注模板的表头格式 |
| 📦已归档 | [`d-cycle-disclosure-note-enhancement`](_archive/08-disclosure-notes/d-cycle-disclosure-note-enhancement/requirements.md) ⧉cycle | 13/13 | Requirements Document |
| 📦已归档 | [`d-cycle-four-table-extraction-and-disclosure-completion`](_archive/08-disclosure-notes/d-cycle-four-table-extraction-and-disclosure-completion/requirements.md) ⧉cycle | 31/31 | Requirements Document |
| 📦已归档 | [`d-cycle-remaining-disclosure-alignment`](_archive/08-disclosure-notes/d-cycle-remaining-disclosure-alignment/requirements.md) ⧉cycle | 48/48 | Requirements Document |
| 📦已归档 | [`d1-disclosure-note`](_archive/05-business-features/d1-disclosure-note/requirements.md) ⧉cycle | 57/57 | Requirements Document |
| 📦已归档 | [`d1-notes-receivable`](_archive/13-2026-06-29-batch/d1-notes-receivable/requirements.md) ⧉cycle | 76/76 | Requirements Document |
| 📦已归档 | [`d1-notes-receivable-disclosure-alignment`](_archive/08-disclosure-notes/d1-notes-receivable-disclosure-alignment/requirements.md) ⧉cycle | 135/135 | D1 应收票据披露表与附注对齐 — 需求 |
| 📦已归档 | [`d2-ar-disclosure-soe-alignment`](_archive/08-disclosure-notes/d2-ar-disclosure-soe-alignment/requirements.md) ⧉cycle | 25/25 | Requirements: d2-ar-disclosure-soe-alignment |
| 📦已归档 | [`d2-ar-disclosure-template-alignment`](_archive/08-disclosure-notes/d2-ar-disclosure-template-alignment/requirements.md) ⧉cycle | 31/31 | Requirements Document |
| 📦已归档 | [`d4-four-table-extraction-and-disclosure-alignment`](_archive/08-disclosure-notes/d4-four-table-extraction-and-disclosure-alignment/requirements.md) ⧉cycle | 33/33 | Requirements Document |
| 📦已归档 | [`disclosure-columns-coverage-rollout`](_archive/08-disclosure-notes/disclosure-columns-coverage-rollout/requirements.md) | 71/71 | Requirements Document |
| 📦已归档 | [`disclosure-note-follow-actual-content`](_archive/08-disclosure-notes/disclosure-note-follow-actual-content/requirements.md) | 74/74 | Requirements Document |
| 📦已归档 | [`disclosure-note-formula-and-report-sync`](_archive/08-disclosure-notes/disclosure-note-formula-and-report-sync/requirements.md) | 29/29 | Requirements Document |
| 📦已归档 | [`disclosure-note-formula-data-population`](_archive/08-disclosure-notes/disclosure-note-formula-data-population/requirements.md) | 25/25 | Requirements Document |
| 📦已归档 | [`disclosure-note-full-revamp`](_archive/08-disclosure-notes/disclosure-note-full-revamp/requirements.md) | 41/47 | 附注模块全栈改进 — 需求文档 |
| 📦已归档 | [`disclosure-note-knowledge-ai-enrichment`](_archive/08-disclosure-notes/disclosure-note-knowledge-ai-enrichment/requirements.md) ⧉note | 10/11 | Requirements Document |
| 📦已归档 | [`disclosure-note-linkage-and-slimdown`](_archive/08-disclosure-notes/disclosure-note-linkage-and-slimdown/requirements.md) | 53/53 | Requirements Document |
| 📦已归档 | [`disclosure-note-linkage-completion`](_archive/08-disclosure-notes/disclosure-note-linkage-completion/requirements.md) | 29/29 | Requirements Document |
| 📦已归档 | [`disclosure-note-quality-completion`](_archive/08-disclosure-notes/disclosure-note-quality-completion/requirements.md) | 16/16 | Requirements Document |
| 📦已归档 | [`disclosure-note-row-level-merge`](_archive/08-disclosure-notes/disclosure-note-row-level-merge/requirements.md) | 15/15 | Requirements Document |
| 📦已归档 | [`disclosure-note-semantic-structure-and-presentation`](_archive/08-disclosure-notes/disclosure-note-semantic-structure-and-presentation/requirements.md) | 145/145 | 需求文档：附注语义结构与前端呈现优化 |
| 📦已归档 | [`disclosure-note-validation-completion`](_archive/08-disclosure-notes/disclosure-note-validation-completion/requirements.md) | 9/9 | Requirements Document |
| 📦已归档 | [`disclosure-notes-selective-generation`](_archive/08-disclosure-notes/disclosure-notes-selective-generation/requirements.md) | 14/14 | Requirements Document |
| 📦已归档 | [`disclosure-payload-authority-source`](_archive/08-disclosure-notes/disclosure-payload-authority-source/requirements.md) | 25/26 | 需求文档：披露表 → 附注 同步载荷的权威源归属 |
| 📦已归档 | [`disclosure-sync-path-buildout`](_archive/08-disclosure-notes/disclosure-sync-path-buildout/requirements.md) | 58/58 | Requirements Document |
| 📦已归档 | [`disclosure-table-sync-convergence`](_archive/08-disclosure-notes/disclosure-table-sync-convergence/requirements.md) | 45/45 | Requirements Document |
| 📦已归档 | [`e-cycle-extraction-formula-and-disclosure-completion`](_archive/08-disclosure-notes/e-cycle-extraction-formula-and-disclosure-completion/requirements.md) ⧉cycle | 24/24 | Requirements Document |
| 📦已归档 | [`e1-four-table-extraction-and-disclosure-alignment`](_archive/08-disclosure-notes/e1-four-table-extraction-and-disclosure-alignment/requirements.md) ⧉cycle | 20/20 | Requirements Document |
| 📦已归档 | [`f-cycle-disclosure-parity`](_archive/08-disclosure-notes/f-cycle-disclosure-parity/requirements.md) ⧉cycle | 38/38 | Requirements: F 类披露表与附注对齐补齐（F1 / F3 / F4 追平 F2） |
| 📦已归档 | [`f-cycle-four-table-extraction-and-disclosure-completion`](_archive/08-disclosure-notes/f-cycle-four-table-extraction-and-disclosure-completion/requirements.md) ⧉cycle | 88/109 | Requirements Document |
| 📦已归档 | [`f1-extraction-chain-and-disclosure-source-fidelity`](_archive/08-disclosure-notes/f1-extraction-chain-and-disclosure-source-fidelity/requirements.md) ⧉cycle | 16/17 | Requirements Document |
| 📦已归档 | [`f1-four-table-extraction-and-disclosure-alignment`](_archive/08-disclosure-notes/f1-four-table-extraction-and-disclosure-alignment/requirements.md) ⧉cycle | 23/23 | Requirements Document |
| 📦已归档 | [`f1-prepayment-disclosure-template-alignment`](_archive/08-disclosure-notes/f1-prepayment-disclosure-template-alignment/requirements.md) ⧉cycle | 49/49 | F1 预付款项披露表 ↔ 附注模板对齐 — 需求 |
| 📦已归档 | [`f2-inventory-disclosure-template-alignment`](_archive/08-disclosure-notes/f2-inventory-disclosure-template-alignment/requirements.md) ⧉cycle | 141/141 | Requirements Document |
| 📦已归档 | [`f3-notes-payable`](_archive/05-business-features/f3-notes-payable/requirements.md) ⧉cycle | 39/39 | Requirements Document |
| 📦已归档 | [`formula-push-note-rollout-batch-c`](_archive/23-formula-push-engine-complete/formula-push-note-rollout-batch-c/requirements.md) ⧉note | 7/7 | 公式推送附注铺开 · 批 C：已注册码加附注规则 |
| 📦已归档 | [`formula-push-note-rollout-batch-d`](_archive/23-formula-push-engine-complete/formula-push-note-rollout-batch-d/requirements.md) ⧉note | 8/8 | 公式推送附注铺开 · 批 D：简单型族 binding |
| 📦已归档 | [`formula-push-note-rollout-batch-e`](_archive/23-formula-push-engine-complete/formula-push-note-rollout-batch-e/requirements.md) ⧉note | 16/16 | 需求：公式推送批 E — 附注推送铺开 |
| 📦已归档 | [`formula-push-note-row-matching`](_archive/41-formula-push-note-skip-and-row-matching/formula-push-note-row-matching/requirements.md) ⧉note | 39/39 | 公式推送附注行匹配增强（formula-push-note-row-matching） |
| 📦已归档 | [`formula-push-note-skip-reduction`](_archive/41-formula-push-note-skip-and-row-matching/formula-push-note-skip-reduction/requirements.md) ⧉note | 30/30 | 公式推送附注跳过减少（formula-push-note-skip-reduction） |
| 📦已归档 | [`four-panel-note-linkage`](_archive/08-disclosure-notes/four-panel-note-linkage/requirements.md) | 22/22 | Requirements Document |
| 📦已归档 | [`g-cycle-extraction-mapping-and-disclosure-alignment`](_archive/08-disclosure-notes/g-cycle-extraction-mapping-and-disclosure-alignment/requirements.md) ⧉cycle | 35/35 | Requirements Document |
| 📦已归档 | [`g5-four-table-extraction-and-disclosure-alignment`](_archive/08-disclosure-notes/g5-four-table-extraction-and-disclosure-alignment/requirements.md) ⧉cycle | 53/53 | Requirements Document |
| 📦已归档 | [`g6-four-table-extraction-and-disclosure-alignment`](_archive/08-disclosure-notes/g6-four-table-extraction-and-disclosure-alignment/requirements.md) ⧉cycle | 10/10 | Requirements Document |
| 📦已归档 | [`g7-four-table-extraction-and-disclosure-alignment`](_archive/08-disclosure-notes/g7-four-table-extraction-and-disclosure-alignment/requirements.md) ⧉cycle | 34/34 | Requirements Document |
| 📦已归档 | [`gt-c-note-table-shrink`](_archive/07-workpaper-slimdown/gt-c-note-table-shrink/requirements.md) | 30/33 | 需求文档：GtCNoteTable / GtEControlTest 超级 SFC 拆分 |
| 📦已归档 | [`h-cycle-extraction-formula-and-disclosure-completion`](_archive/08-disclosure-notes/h-cycle-extraction-formula-and-disclosure-completion/requirements.md) ⧉cycle | 18/18 | Requirements Document |
| 📦已归档 | [`h2-construction-in-progress-disclosure-alignment`](_archive/08-disclosure-notes/h2-construction-in-progress-disclosure-alignment/requirements.md) ⧉cycle | 7/7 | Requirements Document |
| 📦已归档 | [`h2-disclosure-linkage-and-prefill`](_archive/05-business-features/h2-disclosure-linkage-and-prefill/requirements.md) ⧉cycle | 12/18 | Requirements Document |
| 📦已归档 | [`h3-investment-property-disclosure-alignment`](_archive/08-disclosure-notes/h3-investment-property-disclosure-alignment/requirements.md) ⧉cycle | 11/11 | Requirements Document |
| 📦已归档 | [`h5-disclosure-note-linkage`](_archive/05-business-features/h5-disclosure-note-linkage/requirements.md) ⧉cycle | 7/8 | Requirements Document |
| 📦已归档 | [`h5-oil-gas-disclosure-alignment`](_archive/08-disclosure-notes/h5-oil-gas-disclosure-alignment/requirements.md) ⧉cycle | 8/8 | Requirements Document |
| 📦已归档 | [`h7-biological-assets-disclosure-rebuild`](_archive/08-disclosure-notes/h7-biological-assets-disclosure-rebuild/requirements.md) ⧉cycle+platform | 12/12 | Requirements Document |
| 📦已归档 | [`h8-right-of-use-disclosure-alignment`](_archive/08-disclosure-notes/h8-right-of-use-disclosure-alignment/requirements.md) ⧉cycle | 7/7 | Requirements Document |
| 📦已归档 | [`h9-h10-remaining-disclosure-alignment`](_archive/08-disclosure-notes/h9-h10-remaining-disclosure-alignment/requirements.md) ⧉cycle | 9/9 | Requirements Document |
| 📦已归档 | [`i-cycle-extraction-formula-and-disclosure-closure`](_archive/08-disclosure-notes/i-cycle-extraction-formula-and-disclosure-closure/requirements.md) ⧉cycle | 26/26 | Requirements Document |
| 📦已归档 | [`i-cycle-four-table-extraction-and-disclosure-alignment`](_archive/08-disclosure-notes/i-cycle-four-table-extraction-and-disclosure-alignment/requirements.md) ⧉cycle | 45/45 | Requirements Document |
| 📦已归档 | [`i1-i3-disclosure-positional-identity-and-classification-source`](_archive/17-2026-10-03-verified-batch/i1-i3-disclosure-positional-identity-and-classification-source/requirements.md) ⧉cycle | 22/22 | Requirements Document |
| 📦已归档 | [`j-cycle-four-table-extraction-and-disclosure-alignment`](_archive/08-disclosure-notes/j-cycle-four-table-extraction-and-disclosure-alignment/requirements.md) ⧉cycle | 19/19 | Requirements Document |
| 📦已归档 | [`j1-disclosure-note-linkage`](_archive/05-business-features/j1-disclosure-note-linkage/requirements.md) ⧉cycle | 12/12 | Requirements Document |
| 📦已归档 | [`j1-disclosure-template-alignment`](_archive/08-disclosure-notes/j1-disclosure-template-alignment/requirements.md) ⧉cycle | 61/61 | Requirements Document |
| 📦已归档 | [`k-cycle-disclosure-alignment`](_archive/08-disclosure-notes/k-cycle-disclosure-alignment/requirements.md) ⧉cycle | 34/34 | Requirements Document |
| 📦已归档 | [`k-cycle-extraction-formula-and-disclosure-closure`](_archive/08-disclosure-notes/k-cycle-extraction-formula-and-disclosure-closure/requirements.md) ⧉cycle | 25/25 | Requirements Document |
| 📦已归档 | [`k-cycle-four-table-extraction-and-disclosure-completion`](_archive/08-disclosure-notes/k-cycle-four-table-extraction-and-disclosure-completion/requirements.md) ⧉cycle | 23/23 | Requirements Document |
| 📦已归档 | [`k1-extraction-chain-and-note-alignment`](_archive/08-disclosure-notes/k1-extraction-chain-and-note-alignment/requirements.md) ⧉cycle | 28/28 | Requirements Document |
| 📦已归档 | [`k1-four-table-extraction-and-disclosure-alignment`](_archive/08-disclosure-notes/k1-four-table-extraction-and-disclosure-alignment/requirements.md) ⧉cycle | 27/27 | Requirements Document |
| 📦已归档 | [`k1-other-receivable-disclosure-alignment`](_archive/08-disclosure-notes/k1-other-receivable-disclosure-alignment/requirements.md) ⧉cycle | 54/54 | K1 其他应收款披露表与附注对齐增强 — 需求 |
| 📦已归档 | [`k2-other-current-assets-disclosure-alignment`](_archive/08-disclosure-notes/k2-other-current-assets-disclosure-alignment/requirements.md) ⧉cycle+platform | 27/27 | Requirements Document |
| 📦已归档 | [`l-cycle-extraction-formula-and-disclosure-completion`](_archive/08-disclosure-notes/l-cycle-extraction-formula-and-disclosure-completion/requirements.md) ⧉cycle | 26/26 | Requirements Document |
| 📦已归档 | [`l-cycle-four-table-extraction-and-disclosure-alignment`](_archive/08-disclosure-notes/l-cycle-four-table-extraction-and-disclosure-alignment/requirements.md) ⧉cycle | 21/21 | Requirements Document |
| 📦已归档 | [`m-cycle-four-table-extraction-and-disclosure-alignment`](_archive/08-disclosure-notes/m-cycle-four-table-extraction-and-disclosure-alignment/requirements.md) ⧉cycle | 76/85 | Requirements Document |
| 📦已归档 | [`n-cycle-note-template-and-disclosure-completion`](_archive/08-disclosure-notes/n-cycle-note-template-and-disclosure-completion/requirements.md) ⧉cycle | 13/13 | Requirements Document |
| 📦已归档 | [`n-cycle-tax-disclosure-alignment`](_archive/08-disclosure-notes/n-cycle-tax-disclosure-alignment/requirements.md) ⧉cycle | 52/52 | Requirements Document |
| 📦已归档 | [`n1-deferred-tax-disclosure-template-alignment`](_archive/08-disclosure-notes/n1-deferred-tax-disclosure-template-alignment/requirements.md) ⧉cycle | 62/62 | Requirements Document |
| 📦已归档 | [`n1-disclosure-note-linkage`](_archive/08-disclosure-notes/n1-disclosure-note-linkage/requirements.md) ⧉cycle | 12/12 | Requirements Document |
| 📦已归档 | [`n1-four-table-extraction-and-disclosure-alignment`](_archive/08-disclosure-notes/n1-four-table-extraction-and-disclosure-alignment/requirements.md) ⧉cycle | 24/24 | Requirements Document |
| 📦已归档 | [`n2-disclosure-and-extraction-alignment`](_archive/08-disclosure-notes/n2-disclosure-and-extraction-alignment/requirements.md) ⧉cycle | 19/19 | Requirements Document |
| 📦已归档 | [`note-dynamic-tables-and-template-inheritance`](_archive/08-disclosure-notes/note-dynamic-tables-and-template-inheritance/requirements.md) | 166/182 | 附注模块全维度增强 — 需求文档 |
| 📦已归档 | [`note-guidance-text-separation`](_archive/08-disclosure-notes/note-guidance-text-separation/requirements.md) | 44/44 | Requirements Document |
| 📦已归档 | [`note-per-table-guidance`](_archive/08-disclosure-notes/note-per-table-guidance/requirements.md) | 23/23 | 附注多表格 per-table 提示文字治理 |
| 📦已归档 | [`note-sub-table-formula-and-cross-check`](_archive/40-consol-note-defect-closure-and-template-alignment/note-sub-table-formula-and-cross-check/requirements.md) | 26/26 | 附注子表公式与跨表勾稽 — 需求文档 |
| 📦已归档 | [`note-template-columns-and-legacy-snapshot-closure`](_archive/08-disclosure-notes/note-template-columns-and-legacy-snapshot-closure/requirements.md) | 23/23 | Requirements Document |
| 📦已归档 | [`note-template-full-alignment-with-word-authority`](_archive/40-consol-note-defect-closure-and-template-alignment/note-template-full-alignment-with-word-authority/requirements.md) | 16/16 | 附注模板全量对齐 Word 权威源 — 需求文档 |
| 📦已归档 | [`parent-company-note-chapter-and-sourcing`](_archive/08-disclosure-notes/parent-company-note-chapter-and-sourcing/requirements.md) | 18/18 | Requirements Document |
| 📦已归档 | [`restricted-assets-note-row-scope-rollout`](_archive/08-disclosure-notes/restricted-assets-note-row-scope-rollout/requirements.md) ⧉platform | 16/16 | Requirements Document |
| 📦已归档 | [`s32-fraud-response-bundle`](_archive/05-business-features/s32-fraud-response-bundle/requirements.md) ⧉cycle | 23/23 | Requirements Document |
| 📦已归档 | [`s33-announcement14-bundle`](_archive/05-business-features/s33-announcement14-bundle/requirements.md) ⧉cycle | 23/23 | Requirements Document |
| 📦已归档 | [`s34-ipo-review-bundle`](_archive/05-business-features/s34-ipo-review-bundle/requirements.md) ⧉cycle | 40/40 | Requirements Document |
| 📦已归档 | [`s35-refinancing-bundle`](_archive/05-business-features/s35-refinancing-bundle/requirements.md) ⧉cycle | 22/22 | Requirements Document |
| 📦已归档 | [`semantic-account-resolver-full-rollout`](_archive/08-disclosure-notes/semantic-account-resolver-full-rollout/requirements.md) | 31/31 | Requirements Document |
| 📦已归档 | [`soe-listed-note-conversion-correctness`](_archive/08-disclosure-notes/soe-listed-note-conversion-correctness/requirements.md) | 19/19 | Requirements Document |

[↑ 返回概览](#top)

<a id="domain-consol"></a>
## 合并 / 集团 / 三码企业树（31 个）

| 状态 | Spec | 进度 | 需求标题 |
| --- | --- | --- | --- |
| 📦已归档 | [`103-note-pull-residual-governance-closure`](_archive/103-note-pull-residual-governance-closure/requirements.md) ⧉consol+formula | 50/50 | 附注取数残留与治理收口 — 需求 |
| 📦已归档 | [`104-tb-reclass-autosave-and-consol-drilldown-closure`](_archive/104-tb-reclass-autosave-and-consol-drilldown-closure/requirements.md) ⧉cycle | 17/17 | 需求：TB 重分类自动保存与合并汇总穿透收口 |
| 📦已归档 | [`115-batch-project-authorization-and-lock-hardening`](_archive/115-batch-project-authorization-and-lock-hardening/requirements.md) ⧉procedure | 59/59 | 需求：批量建项授权与拓扑锁加固 |
| 📦已归档 | [`117-consol-note-formula-scope-and-roles`](_archive/117-consol-note-formula-scope-and-roles/requirements.md) ⧉formula | 8/8 | 需求文档：S7　合并附注公式的范围与角色 |
| 📦已归档 | [`154-consolidation-run-and-workpaper-lifecycle-closure`](_archive/154-consolidation-run-and-workpaper-lifecycle-closure/requirements.md) | 58/58 | 需求文档：合并运行与底稿生命周期收口 |
| 📦已归档 | [`158-consol-note-save-integrity-closure`](_archive/158-consol-note-save-integrity-closure/requirements.md) ⧉note | 39/39 | 合并附注保存完整性收口 — 需求 |
| 📦已归档 | [`165-consol-group-code-entry-consistency`](_archive/165-consol-group-code-entry-consistency/requirements.md) | 57/57 | 三码入口一致与改上级并发保护 — 需求 |
| 📦已归档 | [`166-consol-status-semantics-closure`](_archive/166-consol-status-semantics-closure/requirements.md) | 46/46 | 合并链路状态语义收口 — 需求 |
| 📦已归档 | [`168-note-disclosure-formula-and-consolidation-chain-closure`](_archive/168-note-disclosure-formula-and-consolidation-chain-closure/requirements.md) ⧉consol+formula | 16/16 | 附注披露取数、公式与合并拉数闭环 — 需求 |
| 📦已归档 | [`169-note-table-structure-formula-pull-closure`](_archive/169-note-table-structure-formula-pull-closure/requirements.md) ⧉formula+consol | 42/42 | 附注表格结构、预设公式与合并拉数收口 — 需求 |
| 📦已归档 | [`171-batch-project-import-and-consol-tree-closure`](_archive/171-batch-project-import-and-consol-tree-closure/requirements.md) | 36/36 | 需求：批量建项与合并企业树导入收口 |
| 📦已归档 | [`27-consol-tree-three-code-autobuild`](_archive/27-consol-tree-three-code-autobuild/requirements.md) | 70/70 | 需求文档：合并企业树按三码自动构建（consol-tree-three-code-autobuild） |
| 📦已归档 | [`64-partner-manager-edit-permission`](_archive/64-partner-manager-edit-permission/requirements.md) ⧉procedure | 110/110 | Requirements Document |
| 📦已归档 | [`72-consol-autotree-linkage-closure`](_archive/72-consol-autotree-linkage-closure/requirements.md) | 24/24 | 需求：合并模块自动建树、左树联动与四维表收口 |
| 📦已归档 | [`73-consol-autotree-residual-closure`](_archive/73-consol-autotree-residual-closure/requirements.md) | 11/11 | 需求：合并自动建树范围外问题收口（报表域鉴权 / 操作门禁 / 状态名 / 合并范围单一来源） |
| 📦已归档 | [`advanced-query-consolidation`](_archive/05-business-features/advanced-query-consolidation/requirements.md) ⧉global-modules | 12/12 | Requirements Document |
| 📦已归档 | [`consol-comprehensive-runtime-defect-closure`](_archive/40-consol-note-defect-closure-and-template-alignment/consol-comprehensive-runtime-defect-closure/requirements.md) | 13/14 | 合并模块运行缺陷收口：需求 |
| 📦已归档 | [`consol-disclosure-note-persistence`](_archive/09-consolidation-phases/consol-disclosure-note-persistence/requirements.md) ⧉note | 9/9 | Requirements Document |
| 📦已归档 | [`consol-elimination-single-source-push`](_archive/09-consolidation-phases/consol-elimination-single-source-push/requirements.md) | 65/65 | 需求文档：合并抵销分录单源与差额表推送（consol-elimination-single-source-push） |
| 📦已归档 | [`consol-node-key-isolation-and-shared-context`](_archive/24-consol-note-and-key-isolation/consol-node-key-isolation-and-shared-context/requirements.md) | 64/64 | 需求文档：合并节点隔离、共享上下文与工作底稿联动 |
| 📦已归档 | [`consol-note-node-refresh-and-formula-orchestration`](_archive/25-2026-10-06-playwright-verified/consol-note-node-refresh-and-formula-orchestration/requirements.md) ⧉note | 28/28 | 需求文档：合并附注节点级自动刷新与公式编排 |
| 📦已归档 | [`consol-note-refresh-multi-header-fix`](_archive/24-consol-note-and-key-isolation/consol-note-refresh-multi-header-fix/requirements.md) ⧉note | 4/4 | 完善合并附注刷新对多级表头的列定位 |
| 📦已归档 | [`consol-note-tab-request-safety-and-identity`](_archive/55-batch-2026-10-21/consol-note-tab-request-safety-and-identity/requirements.md) ⧉note | 11/11 | 需求：合并附注页请求安全与身份校验（ConsolNoteTab CP-05） |
| 📦已归档 | [`consol-note-template-header-unification`](_archive/24-consol-note-and-key-isolation/consol-note-template-header-unification/requirements.md) ⧉note+platform | 7/7 | 统一合并附注模板与单体附注模板的表头格式 |
| 📦已归档 | [`consol-phase0-core-pipeline`](_archive/09-consolidation-phases/consol-phase0-core-pipeline/requirements.md) | 70/82 | 需求文档：consol-phase0-core-pipeline（合并模块 Phase 0 核心管线 + 基础设施修复） |
| 📦已归档 | [`consol-phase1-arch-lock`](_archive/09-consolidation-phases/consol-phase1-arch-lock/requirements.md) | 56/62 | 需求文档：consol-phase1-arch-lock（合并模块 Phase 1 架构修复 + 锁定闭环） |
| 📦已归档 | [`consol-phase2-orchestration`](_archive/09-consolidation-phases/consol-phase2-orchestration/requirements.md) | 63/69 | 需求文档：consol-phase2-orchestration（合并模块 Phase 2 编排 + 接线 + 报表穿透） |
| 📦已归档 | [`consol-phase3-frontend-drilldown`](_archive/09-consolidation-phases/consol-phase3-frontend-drilldown/requirements.md) | 57/64 | 需求文档：consol-phase3-frontend-drilldown（合并模块 Phase 3 前端联动 + 附注穿透） |
| 📦已归档 | [`enterprise-linkage`](_archive/05-business-features/enterprise-linkage/requirements.md) | 56/56 | 需求文档：企业级联动 |
| 📦已归档 | [`frontend-sse-connection-consolidation`](_archive/04-infra-architecture/frontend-sse-connection-consolidation/requirements.md) ⧉platform | 24/24 | Requirements Document |
| 📦已归档 | [`phase2-consolidation`](_archive/01-phase-foundation/phase2-consolidation/requirements.md) | 103/103 | 需求文档：第二阶段集团合并 — 集团架构+组成部分审计师+合并抵消+商誉+少数股东+外币折算+合并报表+合并附注 |

[↑ 返回概览](#top)

<a id="domain-writeback"></a>
## 底稿双向回写 / OO 在线编辑（104 个）

| 状态 | Spec | 进度 | 需求标题 |
| --- | --- | --- | --- |
| 📦已归档 | [`100-s-cycle-linkage-trimming-and-component-wiring`](_archive/100-s-cycle-linkage-trimming-and-component-wiring/requirements.md) ⧉writeback | 40/40 | Requirements Document |
| 📦已归档 | [`110-voucher-identity-writeback-and-audit-phase`](_archive/110-voucher-identity-writeback-and-audit-phase/requirements.md) ⧉writeback+cycle | 18/18 | 需求文档：凭证身份、底稿回写与预审/年审阶段（voucher-identity-writeback-and-audit-phase） |
| 📦已归档 | [`170-d2-voucher-check-import-export-endpoints`](_archive/170-d2-voucher-check-import-export-endpoints/requirements.md) ⧉writeback | 6/6 | D2-7 凭证检查表导入导出端点 — 需求 |
| 📦已归档 | [`174-wp-sync-conflict-adjudication-and-d4-32-modeling`](_archive/174-wp-sync-conflict-adjudication-and-d4-32-modeling/requirements.md) | 19/20 | 需求：同步冲突可裁决化 + D4-32 资金流水建模修正 |
| 📦已归档 | [`18-a-class-runtime-sheetname-and-carrier-exceptions`](_archive/18-a-class-runtime-sheetname-and-carrier-exceptions/requirements.md) | 13/13 | A 类运行时册名与载体例外车道 — 需求 |
| 📦已归档 | [`180-workpaper-html-onlyoffice-bidirectional-writeback-closure`](_archive/180-workpaper-html-onlyoffice-bidirectional-writeback-closure/requirements.md) | 47/50 | 底稿双向回写 umbrella spec 验收准则 |
| 📦已归档 | [`181-oo-writeback-template-parity-closure`](_archive/181-oo-writeback-template-parity-closure/requirements.md) | 54/54 | 需求：在线编辑双向回写收尾（模板缺陷 / 前端对齐 / 字段接通 / 篡改还原 / 转置表 / 插行签名 / 保护口径 / 后端红） |
| 📦已归档 | [`182-workpaper-writeback-data-loss-and-mirror-consistency-closure`](_archive/182-workpaper-writeback-data-loss-and-mirror-consistency-closure/requirements.md) | 59/59 | 需求：底稿双向回写保存安全与镜像一致性收口 |
| 📦已归档 | [`185-frozen-contract-read-path-and-legacy-operation-settlement`](_archive/185-frozen-contract-read-path-and-legacy-operation-settlement/requirements.md) | 12/12 | 需求：冻结契约的读侧重建 + 遗留 operation 结算 |
| 📦已归档 | [`189-b22a-whole-workbook-provider-lane`](_archive/189-b22a-whole-workbook-provider-lane/tasks.md) ⧉cycle | 6/6 | 任务：B22A 整册（whole-workbook）供给链交付 —— provider / 契约 / capability 终裁 |
| 📦已归档 | [`19-a-class-docx-authority-workbook-lanes`](_archive/19-a-class-docx-authority-workbook-lanes/requirements.md) | 13/14 | A 类 docx 权威册车道 — 需求 |
| 📦已归档 | [`20-e1-sync-coverage-and-first-canary`](_archive/20-e1-sync-coverage-and-first-canary/requirements.md) | 22/23 | Requirements Document |
| 📦已归档 | [`22-disclosure-multitable-refresh-and-edit-writeback`](_archive/22-disclosure-multitable-refresh-and-edit-writeback/requirements.md) ⧉note | 8/8 | 附注多表刷新与编辑反写闭环 |
| 📦已归档 | [`32-workpaper-sync-pure-static-lane-and-combined-workbook-resolution`](_archive/32-workpaper-sync-pure-static-lane-and-combined-workbook-resolution/requirements.md) | 72/72 | Requirements Document |
| 📦已归档 | [`36-m-cycle-bidirectional-pipeline`](_archive/36-m-cycle-bidirectional-pipeline/requirements.md) ⧉cycle | 29/29 | M 循环双向回写管线 · 需求 |
| 📦已归档 | [`37-m2-m3-m4-m7-m10-bidirectional-pipeline`](_archive/37-m2-m3-m4-m7-m10-bidirectional-pipeline/requirements.md) | 18/18 | M2/M3/M4/M7/M10 双向回写管线 · 需求 |
| 📦已归档 | [`39-oo-html-writeback-performance`](_archive/39-oo-html-writeback-performance/requirements.md) | 13/13 | OO/HTML 双向回写性能优化 — Requirements |
| 📦已归档 | [`42-d2-online-edit-platform-closure`](_archive/42-d2-online-edit-platform-closure/requirements.md) | 52/52 | 需求：D2 在线编辑恢复与「任意企业首次打开」平台闭环 |
| 📦已归档 | [`44-workpaper-sync-switch-performance`](_archive/44-workpaper-sync-switch-performance/requirements.md) | 25/29 | 底稿 HTML ↔ 在线编辑切换提速 — Requirements |
| 📦已归档 | [`45-d2-inspection-sync-coverage`](_archive/45-d2-inspection-sync-coverage/requirements.md) ⧉cycle | 38/40 | D2 检查底稿双向回写覆盖 — Requirements |
| 📦已归档 | [`77-oo-return-to-form-dead-end-and-save-speed`](_archive/77-oo-return-to-form-dead-end-and-save-speed/requirements.md) | 14/14 | 在线编辑回表单死路与回写提速 — Requirements |
| 📦已归档 | [`78-workpaper-sync-save-path-cpu-hotspots`](_archive/78-workpaper-sync-save-path-cpu-hotspots/requirements.md) ⧉platform | 9/9 | 双向回写 CPU 热点与事件循环阻塞 — Requirements |
| 📦已归档 | [`80-writeback-followup-issue-closure`](_archive/80-writeback-followup-issue-closure/requirements.md) | 13/25 | 双向回写提速后遗留问题收口 — Requirements |
| 📦已归档 | [`82-d2-skeleton-slot-reuse-and-writeback-speed`](_archive/82-d2-skeleton-slot-reuse-and-writeback-speed/requirements.md) | 24/25 | D2 模板骨架槽位复用 + 双向回写提速 — Requirements |
| 📦已归档 | [`85-oo-formula-recompute-not-tamper`](_archive/85-oo-formula-recompute-not-tamper/requirements.md) | 11/11 | 需求：OnlyOffice 重算公式格不再当成篡改 |
| 📦已归档 | [`a-cycle-online-edit-driver-closure`](_archive/55-batch-2026-10-21/a-cycle-online-edit-driver-closure/requirements.md) ⧉cycle | 10/10 | 需求：A 循环在线编辑驱动收口 |
| 📦已归档 | [`a-cycle-sync-foundation-and-first-canary`](_archive/17-2026-10-03-verified-batch/a-cycle-sync-foundation-and-first-canary/requirements.md) ⧉cycle | 22/22 | A 循环双向回写地基与首张 canary — 需求 |
| 📦已归档 | [`a1-12-dual-mode-checklist`](_archive/13-2026-06-29-batch/a1-12-dual-mode-checklist/requirements.md) ⧉cycle | 24/37 | Requirements Document |
| 📦已归档 | [`b-class-orphan-carrier-and-host-inline-lanes`](_archive/16-workpaper-sync-cycle-lanes/b-class-orphan-carrier-and-host-inline-lanes/requirements.md) | 23/27 | B 类孤儿载体与宿主内联门控通道 — 需求 |
| 📦已归档 | [`b-class-shared-base-carrier-lanes`](_archive/16-workpaper-sync-cycle-lanes/b-class-shared-base-carrier-lanes/requirements.md) | 19/21 | B 类共享基类载体通道 — 需求 |
| 📦已归档 | [`b-cycle-sync-foundation-and-first-canary`](_archive/16-workpaper-sync-cycle-lanes/b-cycle-sync-foundation-and-first-canary/requirements.md) ⧉cycle | 27/33 | B 循环双向回写地基与首张 canary — 需求 |
| 📦已归档 | [`c-cycle-sync-foundation-and-first-canary`](_archive/16-workpaper-sync-cycle-lanes/c-cycle-sync-foundation-and-first-canary/requirements.md) ⧉cycle | 28/37 | C 循环双向回写地基与首张 canary — 需求 |
| 📦已归档 | [`c22-itgc-no-switch-and-domain-code-sheet-lane`](_archive/16-workpaper-sync-cycle-lanes/c22-itgc-no-switch-and-domain-code-sheet-lane/requirements.md) ⧉cycle | 13/17 | C22 ITGC 无开关与域码 sheet 名通道 — 需求 |
| 📦已归档 | [`custom-workpaper-dual-mode-formula-and-batch`](_archive/05-business-features/custom-workpaper-dual-mode-formula-and-batch/requirements.md) | 29/29 | Requirements Document |
| 📦已归档 | [`custom-workpaper-template-ingestion-and-sync-closure`](_archive/17-2026-10-03-verified-batch/custom-workpaper-template-ingestion-and-sync-closure/requirements.md) ⧉writeback | 15/19 | Requirements Document |
| 📦已归档 | [`d-cycle-sheet-bidirectional-expansion`](_archive/17-2026-10-03-verified-batch/d-cycle-sheet-bidirectional-expansion/tasks.md) ⧉cycle | 9/9 | Implementation Plan — D-cycle sheet bidirectional expansion |
| 📦已归档 | [`d-cycle-tier-a-writeback-detail-seed`](_archive/05-business-features/d-cycle-tier-a-writeback-detail-seed/requirements.md) ⧉cycle | 20/21 | Requirements Document |
| 📦已归档 | [`d0-onlyoffice-migration`](_archive/04-infra-architecture/d0-onlyoffice-migration/requirements.md) ⧉cycle+platform | 10/10 | 需求：多 sheet 底稿非核心 Sheet 切换到 OnlyOffice 渲染 |
| 📦已归档 | [`d1-sync-row-table-engine-and-d1-coverage`](_archive/31-row-table-engine-and-d1-coverage/d1-sync-row-table-engine-and-d1-coverage/requirements.md) ⧉cycle | 36/36 | Requirements Document |
| 📦已归档 | [`d2-sync-coverage-via-row-table-engine`](_archive/16-workpaper-sync-cycle-lanes/d2-sync-coverage-via-row-table-engine/requirements.md) ⧉cycle | 16/18 | Requirements Document |
| 📦已归档 | [`d3-sync-coverage-via-row-table-engine`](_archive/17-2026-10-03-verified-batch/d3-sync-coverage-via-row-table-engine/requirements.md) ⧉cycle | 17/17 | Requirements Document |
| 📦已归档 | [`d4-1-adjudication-bidirectional-writeback-and-formula-io`](_archive/14-d4-bidirectional-writeback/d4-1-adjudication-bidirectional-writeback-and-formula-io/requirements.md) ⧉cycle | 12/12 | Requirements Document |
| 📦已归档 | [`d4-12-transposed-writeback`](_archive/14-d4-bidirectional-writeback/d4-12-transposed-writeback/requirements.md) ⧉cycle | 15/15 | Requirements — D4-12 合同检查表 转置双向回写 |
| 📦已归档 | [`d4-14-walkthrough-writeback`](_archive/14-d4-bidirectional-writeback/d4-14-walkthrough-writeback/requirements.md) ⧉cycle | 12/13 | Requirements — D4-14 营业收入发生检查表（穿行测试）双向回写 |
| 📦已归档 | [`d4-21-24-oo-bidirectional-and-cross-sheet-formula`](_archive/14-d4-bidirectional-writeback/d4-21-24-oo-bidirectional-and-cross-sheet-formula/requirements.md) ⧉cycle | 10/11 | D4-21~24 需求 |
| 📦已归档 | [`d4-33-36-writeback-formula-and-io-closure`](_archive/14-d4-bidirectional-writeback/d4-33-36-writeback-formula-and-io-closure/requirements.md) ⧉cycle | 35/42 | Requirements Document |
| 📦已归档 | [`d4-4-adjustment-summary-bidirectional-writeback`](_archive/17-2026-10-03-verified-batch/d4-4-adjustment-summary-bidirectional-writeback/requirements.md) ⧉cycle | 23/23 | D4-4 营业收入调整分录汇总 —— HTML ↔ OnlyOffice 双向回写 |
| 📦已归档 | [`d4-9-customer-structure-bidirectional-writeback`](_archive/14-d4-bidirectional-writeback/d4-9-customer-structure-bidirectional-writeback/requirements.md) ⧉cycle | 12/15 | Requirements — D4-9 重要客户结构分析 HTML↔OnlyOffice 双向回写 |
| 📦已归档 | [`d4-adjustment-and-analysis-gap-closure`](_archive/14-d4-bidirectional-writeback/d4-adjustment-and-analysis-gap-closure/requirements.md) ⧉cycle | 1/1 | D4-4/8/12调整与分析遗漏闭环 |
| 📦已归档 | [`d4-cutoff-return-writeback-formula-io`](_archive/14-d4-bidirectional-writeback/d4-cutoff-return-writeback-formula-io/requirements.md) ⧉cycle | 13/13 | Requirements Document |
| 📦已归档 | [`d4-dual-mode-formula-governance`](_archive/14-d4-bidirectional-writeback/d4-dual-mode-formula-governance/requirements.md) ⧉cycle+platform | 16/16 | D4 双模式公式治理与36底稿覆盖总纲 |
| 📦已归档 | [`d4-inspection-writeback-formula-io`](_archive/14-d4-bidirectional-writeback/d4-inspection-writeback-formula-io/requirements.md) ⧉cycle | 9/16 | Requirements Document |
| 📦已归档 | [`d4-ipo-checklist-dual-mode-writeback-and-formula`](_archive/14-d4-bidirectional-writeback/d4-ipo-checklist-dual-mode-writeback-and-formula/requirements.md) ⧉cycle | 28/30 | Requirements Document |
| 📦已归档 | [`d4-ipo-fraud-writeback-formula-io`](_archive/14-d4-bidirectional-writeback/d4-ipo-fraud-writeback-formula-io/requirements.md) ⧉cycle | 11/11 | Requirements Document |
| 📦已归档 | [`d4-price-analysis-writeback-linkage`](_archive/14-d4-bidirectional-writeback/d4-price-analysis-writeback-linkage/requirements.md) ⧉cycle | 9/10 | Requirements — D4 价格分析双向回写联动（D4-10/11）+ 行同步回写死代码修复 |
| 📦已归档 | [`d4-revenue-matrix-bidirectional`](_archive/14-d4-bidirectional-writeback/d4-revenue-matrix-bidirectional/requirements.md) ⧉cycle | 13/14 | Requirements Document |
| 📦已归档 | [`d567-sync-coverage-via-row-table-engine`](_archive/17-2026-10-03-verified-batch/d567-sync-coverage-via-row-table-engine/requirements.md) ⧉cycle | 23/23 | Requirements Document |
| 📦已归档 | [`deliverable-lineage-and-writeback`](_archive/05-business-features/deliverable-lineage-and-writeback/requirements.md) ⧉writeback | 92/92 | 需求文档：出品物溯源与回填（deliverable-lineage-and-writeback） |
| 📦已归档 | [`deliverable-lineage-wiring-and-writeback-closure`](_archive/05-business-features/deliverable-lineage-wiring-and-writeback-closure/requirements.md) ⧉writeback | 40/40 | Requirements Document |
| 📦已归档 | [`deliverable-writeback-and-online-edit-integrity`](_archive/55-batch-2026-10-21/deliverable-writeback-and-online-edit-integrity/requirements.md) ⧉writeback | 29/29 | 交付件回填 / 在线编辑保存 / 签发清单完整性 |
| 📦已归档 | [`excel-structural-row-insertion-and-shift-aware-verification`](_archive/17-2026-10-03-verified-batch/excel-structural-row-insertion-and-shift-aware-verification/requirements.md) | 26/27 | Requirements Document |
| 📦已归档 | [`excel-template-override-layer-and-onlyoffice-template-editor`](_archive/17-2026-10-03-verified-batch/excel-template-override-layer-and-onlyoffice-template-editor/requirements.md) | 26/26 | Requirements Document |
| 📦已归档 | [`excel-workbook-wide-row-change-propagation`](_archive/17-2026-10-03-verified-batch/excel-workbook-wide-row-change-propagation/requirements.md) | 30/30 | Requirements Document |
| 📦已归档 | [`f1-sync-coverage-and-first-canary`](_archive/34-f-cycle-sync-coverage/f1-sync-coverage-and-first-canary/requirements.md) ⧉cycle | 22/22 | Introduction |
| 📦已归档 | [`f2-sync-coverage-four-entry-lanes`](_archive/34-f-cycle-sync-coverage/f2-sync-coverage-four-entry-lanes/requirements.md) ⧉cycle | 26/27 | Introduction |
| 📦已归档 | [`f3-sync-coverage-and-first-canary`](_archive/34-f-cycle-sync-coverage/f3-sync-coverage-and-first-canary/requirements.md) ⧉cycle | 19/20 | Requirements Document |
| 📦已归档 | [`f4-sync-coverage-and-first-canary`](_archive/34-f-cycle-sync-coverage/f4-sync-coverage-and-first-canary/requirements.md) ⧉cycle | 19/20 | Requirements Document |
| 📦已归档 | [`f5-sync-coverage-and-first-canary`](_archive/34-f-cycle-sync-coverage/f5-sync-coverage-and-first-canary/requirements.md) ⧉cycle | 21/22 | Requirements Document |
| 📦已归档 | [`frontend-excel-io-single-entry-convergence`](_archive/06-engineering-governance/frontend-excel-io-single-entry-convergence/requirements.md) ⧉writeback | 15/15 | Requirements Document |
| 📦已归档 | [`g-cycle-single-region-detail-lanes`](_archive/16-workpaper-sync-cycle-lanes/g-cycle-single-region-detail-lanes/requirements.md) ⧉cycle | 18/18 | Requirements Document |
| 📦已归档 | [`g-cycle-sync-foundation-and-first-canary`](_archive/16-workpaper-sync-cycle-lanes/g-cycle-sync-foundation-and-first-canary/requirements.md) ⧉cycle | 19/19 | Requirements Document |
| 📦已归档 | [`g4-g6-shared-workbook-three-entry-lanes`](_archive/18-g4-g6-shared-workbook/g4-g6-shared-workbook-three-entry-lanes/requirements.md) ⧉cycle | 18/18 | Requirements Document |
| 📦已归档 | [`h-cycle-sync-foundation-and-first-canary`](_archive/16-workpaper-sync-cycle-lanes/h-cycle-sync-foundation-and-first-canary/requirements.md) ⧉cycle | 22/24 | Requirements Document |
| 📦已归档 | [`h2-h6-h10-pilot-cross-reference-lanes`](_archive/16-workpaper-sync-cycle-lanes/h2-h6-h10-pilot-cross-reference-lanes/requirements.md) ⧉cycle | 18/20 | Requirements Document |
| 📦已归档 | [`h3-h5-h7-variant-axis-and-dynamic-column-paradigm`](_archive/16-workpaper-sync-cycle-lanes/h3-h5-h7-variant-axis-and-dynamic-column-paradigm/requirements.md) ⧉cycle | 17/18 | Requirements Document |
| 📦已归档 | [`h4-h8-sub-entry-lanes-and-seed-identity-defects`](_archive/16-workpaper-sync-cycle-lanes/h4-h8-sub-entry-lanes-and-seed-identity-defects/requirements.md) ⧉cycle | 17/18 | Requirements Document |
| 📦已归档 | [`i-cycle-sync-foundation-and-first-canary`](_archive/17-2026-10-03-verified-batch/i-cycle-sync-foundation-and-first-canary/requirements.md) ⧉cycle | 26/26 | Requirements Document |
| 📦已归档 | [`i2-i4-i5-carrier-and-structure-exceptions`](_archive/17-2026-10-03-verified-batch/i2-i4-i5-carrier-and-structure-exceptions/requirements.md) ⧉cycle | 26/26 | Requirements Document |
| 📦已归档 | [`j-cycle-sync-foundation-and-first-canary`](_archive/17-2026-10-03-verified-batch/j-cycle-sync-foundation-and-first-canary/requirements.md) ⧉cycle | 34/34 | Requirements Document |
| 📦已归档 | [`j2-j3-non-entry-hosts-and-orphan-cleanup`](_archive/16-workpaper-sync-cycle-lanes/j2-j3-non-entry-hosts-and-orphan-cleanup/requirements.md) ⧉cycle | 19/19 | Requirements Document |
| 📦已归档 | [`k-cycle-sync-foundation-and-first-canary`](_archive/26-workpaper-sync-cycle-lanes-kln/k-cycle-sync-foundation-and-first-canary/requirements.md) ⧉cycle | 27/30 | K 循环双向回写地基与首张 canary — 需求 |
| 📦已归档 | [`k1-k7-inlined-iife-hosts-and-orphan-cleanup`](_archive/26-workpaper-sync-cycle-lanes-kln/k1-k7-inlined-iife-hosts-and-orphan-cleanup/requirements.md) ⧉cycle | 24/25 | K1~K7 内联 IIFE 宿主与 orphan 清理 — 需求 |
| 📦已归档 | [`l-cycle-sync-foundation-and-first-canary`](_archive/17-2026-10-03-verified-batch/l-cycle-sync-foundation-and-first-canary/requirements.md) ⧉cycle | 37/37 | L 循环双向回写地基与首张 canary — 需求 |
| 📦已归档 | [`l2-l3-l4-orphan-twins-and-sheet-granularity-collapse`](_archive/26-workpaper-sync-cycle-lanes-kln/l2-l3-l4-orphan-twins-and-sheet-granularity-collapse/requirements.md) ⧉cycle | 22/23 | L2 / L3 / L4 孤儿孪生与 sheet 粒度折叠车道 — 需求 |
| 📦已归档 | [`l5-l8-inert-switch-and-child-tab-carriers`](_archive/26-workpaper-sync-cycle-lanes-kln/l5-l8-inert-switch-and-child-tab-carriers/requirements.md) ⧉cycle | 26/27 | L5 ~ L8 死开关与子 Tab 专属载体车道 — 需求 |
| 📦已归档 | [`m-cycle-sync-foundation-and-first-canary`](_archive/26-workpaper-sync-cycle-lanes-kln/m-cycle-sync-foundation-and-first-canary/requirements.md) ⧉cycle | 45/46 | M 循环双向回写地基与首张 canary — 需求 |
| 📦已归档 | [`m1-m5-m8-m9-mode-value-and-carrier-exceptions`](_archive/35-g5-m1-cycle-sync-lanes/m1-m5-m8-m9-mode-value-and-carrier-exceptions/requirements.md) ⧉cycle | 27/27 | M1 / M5 / M8 / M9 —— mode 取值与载体例外收口 · 需求 |
| 📦已归档 | [`multi-sheet-materialize-defined-name-shift-normalization`](_archive/15-workpaper-sync-engine-hardening/multi-sheet-materialize-defined-name-shift-normalization/requirements.md) | 15/15 | Requirements — 多 sheet materialize 的 defined-name 位移归一化 |
| 📦已归档 | [`n-cycle-sync-foundation-and-first-canary`](_archive/26-workpaper-sync-cycle-lanes-kln/n-cycle-sync-foundation-and-first-canary/requirements.md) ⧉cycle | 26/27 | N 循环双向回写地基与首张 canary — 需求 |
| 📦已归档 | [`n1-n3-host-inline-router-and-shared-adoption`](_archive/26-workpaper-sync-cycle-lanes-kln/n1-n3-host-inline-router-and-shared-adoption/requirements.md) ⧉cycle | 18/20 | N1 / N3 宿主内联路由与共享路由采纳 — 需求 |
| 📦已归档 | [`onlyoffice-integration-hardening`](_archive/04-infra-architecture/onlyoffice-integration-hardening/requirements.md) | 21/21 | Requirements Document |
| 🟢活跃 | [`onlyoffice-sheet-open-via-published-artifact`](onlyoffice-sheet-open-via-published-artifact/requirements.md) | 26/35 | Sheet 级 OnlyOffice 入口改走 Published Representation |
| 📦已归档 | [`oo-single-pass-materialize-and-room-leave`](_archive/15-workpaper-sync-engine-hardening/oo-single-pass-materialize-and-room-leave/requirements.md) | 11/11 | 需求：OO 物化单趟写入 + participant 主动离开 |
| 📦已归档 | [`published-representation-production-path-and-lane-adjudication`](_archive/17-2026-10-03-verified-batch/published-representation-production-path-and-lane-adjudication/requirements.md) ⧉cycle | 43/43 | Requirements Document |
| 📦已归档 | [`sync-editor-host-discovery-contract-closure`](_archive/17-2026-10-03-verified-batch/sync-editor-host-discovery-contract-closure/requirements.md) | 17/17 | Requirements — 同步编辑器宿主纳入挂点发现契约（平台级缺陷闭环） |
| 📦已归档 | [`tb-writeback-explicit-publish-gate`](_archive/06-engineering-governance/tb-writeback-explicit-publish-gate/requirements.md) ⧉cycle | 21/21 | Requirements Document |
| 📦已归档 | [`word-template-dual-mode`](_archive/05-business-features/word-template-dual-mode/requirements.md) | 38/38 | Requirements Document |
| 📦已归档 | [`workpaper-html-onlyoffice-bidirectional-writeback-closure`](_archive/17-2026-10-03-verified-batch/workpaper-html-onlyoffice-bidirectional-writeback-closure/requirements.md) ⧉cycle | 66/72 | Requirements Document |
| 📦已归档 | [`workpaper-sync-adopt-overwrite-and-refresh-source`](_archive/25-2026-10-06-playwright-verified/workpaper-sync-adopt-overwrite-and-refresh-source/requirements.md) ⧉cycle | 58/58 | Requirements Document |
| 📦已归档 | [`workpaper-sync-managed-row-convergence`](_archive/30-workpaper-sync-managed-row-convergence/workpaper-sync-managed-row-convergence/requirements.md) ⧉cycle | 16/33 | Requirements — 受管行双向收敛（刷新取数来源可选 + materialize 行收敛） |
| 📦已归档 | [`workpaper-sync-materialize-large-table-performance`](_archive/15-workpaper-sync-engine-hardening/workpaper-sync-materialize-large-table-performance/requirements.md) ⧉cycle | 12/12 | Requirements Document |
| 📦已归档 | [`workpaper-sync-registration-isolation-and-d2-republish`](_archive/15-workpaper-sync-engine-hardening/workpaper-sync-registration-isolation-and-d2-republish/requirements.md) ⧉cycle | 14/15 | Requirements — workpaper-sync 注册隔离 + 通用对齐守卫 + D2 sibling 发布 |
| 📦已归档 | [`workpaper-sync-row-deletion-multi-region-propagation`](_archive/17-2026-10-03-verified-batch/workpaper-sync-row-deletion-multi-region-propagation/requirements.md) ⧉cycle | 74/74 | Requirements Document |
| 📦已归档 | [`workpaper-sync-static-cell-sheet-writeback`](_archive/15-workpaper-sync-engine-hardening/workpaper-sync-static-cell-sheet-writeback/requirements.md) ⧉cycle | 12/12 | Requirements Document |

[↑ 返回概览](#top)

<a id="domain-cycle"></a>
## A~S 循环底稿业务（科目/程序/检查表）（485 个）

| 状态 | Spec | 进度 | 需求标题 |
| --- | --- | --- | --- |
| 📦已归档 | [`100-s-cycle-linkage-trimming-and-component-wiring`](_archive/100-s-cycle-linkage-trimming-and-component-wiring/requirements.md) ⧉writeback | 40/40 | Requirements Document |
| 📦已归档 | [`104-tb-reclass-autosave-and-consol-drilldown-closure`](_archive/104-tb-reclass-autosave-and-consol-drilldown-closure/requirements.md) ⧉cycle | 17/17 | 需求：TB 重分类自动保存与合并汇总穿透收口 |
| 📦已归档 | [`107-attachment-confirmation-evidence-loop`](_archive/107-attachment-confirmation-evidence-loop/requirements.md) ⧉cycle | 12/12 | 需求：函证证据闭环（attachment-confirmation-evidence-loop） |
| 📦已归档 | [`110-voucher-identity-writeback-and-audit-phase`](_archive/110-voucher-identity-writeback-and-audit-phase/requirements.md) ⧉writeback+cycle | 18/18 | 需求文档：凭证身份、底稿回写与预审/年审阶段（voucher-identity-writeback-and-audit-phase） |
| 📦已归档 | [`111-ledger-incremental-append-true-merge`](_archive/111-ledger-incremental-append-true-merge/requirements.md) ⧉cycle | 6/6 | 需求文档：序时账增量追加改为真追加（ledger-incremental-append-true-merge） |
| 📦已归档 | [`112-adjustment-hall-entry-review-closure`](_archive/112-adjustment-hall-entry-review-closure/requirements.md) | 10/10 | 需求文档：调整分录大厅——录入、导入导出、推送与复核通知收口（adjustment-hall-entry-review-closure） |
| 📦已归档 | [`134-attachment-contract-identity-and-domain-closure`](_archive/134-attachment-contract-identity-and-domain-closure/requirements.md) ⧉cycle | 25/25 | Spec F — attachment-contract-identity-and-domain-closure 需求 |
| 📦已归档 | [`135-attachment-voucher-evidence-binding`](_archive/135-attachment-voucher-evidence-binding/requirements.md) ⧉attachment+cycle | 12/12 | 需求：抽凭证据绑定（attachment-voucher-evidence-binding） |
| 📦已归档 | [`140-formula-hub-release-blockers`](_archive/140-formula-hub-release-blockers/requirements.md) ⧉cycle+platform | 14/14 | 需求：公式管理阻断缺陷收口（formula-hub-release-blockers） |
| 📦已归档 | [`141-income-statement-lower-section-formulas`](_archive/141-income-statement-lower-section-formulas/requirements.md) ⧉cycle | 8/8 | 需求文档：S9　利润表净利润以下行的公式补全 |
| 📦已归档 | [`149-voucher-workflow-linkage-lineage-closure`](_archive/149-voucher-workflow-linkage-lineage-closure/requirements.md) ⧉cycle | 22/22 | 凭证模块联动、流程与溯源收口 — 需求 |
| 📦已归档 | [`175-adjustment-practice-linkage-integrity-closure`](_archive/175-adjustment-practice-linkage-integrity-closure/requirements.md) | 50/50 | 需求文档：调整模块实务、联动与完整性闭环 |
| 📦已归档 | [`176-adjustment-client-booking-status`](_archive/176-adjustment-client-booking-status/requirements.md) | 9/9 | 需求文档：调整分录阶段与「客户已入账」（adjustment-client-booking-status） |
| 📦已归档 | [`183-m-cycle-key-naming-unification`](_archive/183-m-cycle-key-naming-unification/requirements.md) ⧉platform | 14/14 | Requirements — M 循环键名统一（前端驼峰 ↔ 契约下划线） |
| 📦已归档 | [`184-m-cycle-form-storage-cell-projection`](_archive/184-m-cycle-form-storage-cell-projection/requirements.md) | 33/33 | Requirements — M 循环表单存储 → 单元格投影 |
| 📦已归档 | [`189-b22a-whole-workbook-provider-lane`](_archive/189-b22a-whole-workbook-provider-lane/tasks.md) ⧉cycle | 6/6 | 任务：B22A 整册（whole-workbook）供给链交付 —— provider / 契约 / capability 终裁 |
| 📦已归档 | [`28-four-table-extraction-entry-completion`](_archive/28-four-table-extraction-entry-completion/requirements.md) | 24/24 | Requirements Document |
| 📦已归档 | [`36-m-cycle-bidirectional-pipeline`](_archive/36-m-cycle-bidirectional-pipeline/requirements.md) ⧉cycle | 29/29 | M 循环双向回写管线 · 需求 |
| 📦已归档 | [`45-d2-inspection-sync-coverage`](_archive/45-d2-inspection-sync-coverage/requirements.md) ⧉cycle | 38/40 | D2 检查底稿双向回写覆盖 — Requirements |
| 📦已归档 | [`46-voucher-attach-account-mapping-closure`](_archive/46-voucher-attach-account-mapping-closure/requirements.md) ⧉cycle | 23/23 | voucher-attach-account-mapping-closure — 需求文档 |
| 📦已归档 | [`47-multi-window-ledger-workbench`](_archive/47-multi-window-ledger-workbench/requirements.md) ⧉cycle+platform | 24/24 | 多窗口查账工作台 — 需求 |
| 📦已归档 | [`56-voucher-sampling-reconcile-balance-source`](_archive/56-voucher-sampling-reconcile-balance-source/requirements.md) ⧉cycle | 11/12 | 抽凭总体完整性核对接入科目余额表 + 预览内就地放行 — 需求 |
| 📦已归档 | [`74-audit-year-calendar-fallback-ratchet`](_archive/74-audit-year-calendar-fallback-ratchet/requirements.md) ⧉cycle | 29/29 | 审计年度兜底取今年 / 写死年度 —— 棘轮与收口（audit-year-calendar-fallback-ratchet） |
| 📦已归档 | [`A00-completion-infra`](_archive/10-A~S-workpaper-all-cycles-complete/A00-completion-infra/requirements.md) | 16/16 | 完成阶段公共基础设施（A7–A18 共用） |
| 📦已归档 | [`A01-completion-a7-a15`](_archive/10-A~S-workpaper-all-cycles-complete/A01-completion-a7-a15/requirements.md) | 66/66 | A7–A15 完成阶段底稿（关联交易→持续经营） |
| 📦已归档 | [`A02-misstatement-a13`](_archive/10-A~S-workpaper-all-cycles-complete/A02-misstatement-a13/requirements.md) | 3/3 | A13 错报底稿套件（子 spec） |
| 📦已归档 | [`A03-control-deficiency-a14`](_archive/10-A~S-workpaper-all-cycles-complete/A03-control-deficiency-a14/requirements.md) | 4/4 | A14 内部控制缺陷底稿族（子 spec） |
| 📦已归档 | [`A04-representation-letter-a16`](_archive/10-A~S-workpaper-all-cycles-complete/A04-representation-letter-a16/requirements.md) | 24/24 | A16 管理层声明书底稿 |
| 📦已归档 | [`A05-summary-a17`](_archive/10-A~S-workpaper-all-cycles-complete/A05-summary-a17/requirements.md) | 25/25 | A17 重大事项概要底稿（上市公司 A 类业务） |
| 📦已归档 | [`A06-regulatory-a18`](_archive/10-A~S-workpaper-all-cycles-complete/A06-regulatory-a18/requirements.md) | 13/13 | A18 监管沟通函结构化底稿 |
| 📦已归档 | [`A07-review-a21-a25`](_archive/10-A~S-workpaper-all-cycles-complete/A07-review-a21-a25/requirements.md) | 28/28 | A21~A25 各角色复核底稿（配置驱动重构） |
| 📦已归档 | [`A08-analytical-review-a1-13-14`](_archive/10-A~S-workpaper-all-cycles-complete/A08-analytical-review-a1-13-14/requirements.md) | 9/10 | 分析性复核底稿 — 需求文档 |
| 📦已归档 | [`A09-cash-flow-a5`](_archive/10-A~S-workpaper-all-cycles-complete/A09-cash-flow-a5/requirements.md) | 9/9 | 现金流量表支持底稿 — 需求文档 |
| 📦已归档 | [`A10-checklist-a1-15-16`](_archive/10-A~S-workpaper-all-cycles-complete/A10-checklist-a1-15-16/design.md) | 10/11 | 核对表底稿完整渲染 Design |
| 📦已归档 | [`A11-goodwill-a3-8`](_archive/10-A~S-workpaper-all-cycles-complete/A11-goodwill-a3-8/requirements.md) | 9/9 | 商誉减值+可收回金额测试底稿 — 需求文档 |
| 📦已归档 | [`A12-segment-a4`](_archive/10-A~S-workpaper-all-cycles-complete/A12-segment-a4/requirements.md) | 9/9 | 经营分部审定表 — 需求文档 |
| 📦已归档 | [`X01-editing-guidance`](_archive/10-A~S-workpaper-all-cycles-complete/X01-editing-guidance/requirements.md) | 48/48 | 底稿编制指导助手 — 需求文档 |
| 📦已归档 | [`X02-inline-popup`](_archive/10-A~S-workpaper-all-cycles-complete/X02-inline-popup/requirements.md) | 9/9 | 子底稿弹窗式联动 — 需求文档 |
| 📦已归档 | [`X03-editing-lock`](_archive/10-A~S-workpaper-all-cycles-complete/X03-editing-lock/requirements.md) | 40/40 | Requirements Document |
| 📦已归档 | [`X04-group-tree`](_archive/10-A~S-workpaper-all-cycles-complete/X04-group-tree/requirements.md) | 54/54 | Requirements Document |
| 📦已归档 | [`a-cycle-docx-online`](_archive/12-2026-06-23-batch/a-cycle-docx-online/requirements.md) | 40/40 | Requirements Document |
| 📦已归档 | [`a-cycle-online-edit-driver-closure`](_archive/55-batch-2026-10-21/a-cycle-online-edit-driver-closure/requirements.md) ⧉cycle | 10/10 | 需求：A 循环在线编辑驱动收口 |
| 📦已归档 | [`a-cycle-sync-foundation-and-first-canary`](_archive/17-2026-10-03-verified-batch/a-cycle-sync-foundation-and-first-canary/requirements.md) ⧉cycle | 22/22 | A 循环双向回写地基与首张 canary — 需求 |
| 📦已归档 | [`a-review-checklist-rbac`](_archive/12-2026-06-23-batch/a-review-checklist-rbac/requirements.md) ⧉cycle | 31/40 | Requirements Document |
| 📦已归档 | [`a1-11-signing-control-form`](_archive/13-2026-06-29-batch/a1-11-signing-control-form/requirements.md) | 30/30 | Requirements Document |
| 📦已归档 | [`a1-12-dual-mode-checklist`](_archive/13-2026-06-29-batch/a1-12-dual-mode-checklist/requirements.md) ⧉cycle | 24/37 | Requirements Document |
| 📦已归档 | [`a1-15-disclosure-checklist`](_archive/13-2026-06-29-batch/a1-15-disclosure-checklist/requirements.md) ⧉cycle | 43/43 | Requirements Document |
| 📦已归档 | [`a1-dashboard-bundle-upgrade`](_archive/13-2026-06-29-batch/a1-dashboard-bundle-upgrade/requirements.md) | 15/30 | 需求文档：A1 Dashboard 子底稿内嵌升级 |
| 📦已归档 | [`a11-1-subsequent-events-inquiry`](_archive/13-2026-06-29-batch/a11-1-subsequent-events-inquiry/requirements.md) | 19/21 | Requirements Document |
| 📦已归档 | [`a12-1-legal-confirmation`](_archive/13-2026-06-29-batch/a12-1-legal-confirmation/requirements.md) | 20/20 | Requirements Document |
| 📦已归档 | [`a13-misstatement-aggregation`](_archive/12-2026-06-23-batch/a13-misstatement-aggregation/requirements.md) | 48/48 | Requirements Document |
| 📦已归档 | [`a16-representation-bundle`](_archive/13-2026-06-29-batch/a16-representation-bundle/requirements.md) | 11/23 | 需求文档：A16 管理层声明书聚合组件 |
| 📦已归档 | [`a17-1-audit-summary`](_archive/13-2026-06-29-batch/a17-1-audit-summary/requirements.md) | 20/20 | Requirements Document |
| 📦已归档 | [`a17-2-1-kam`](_archive/13-2026-06-29-batch/a17-2-1-kam/requirements.md) | 18/18 | Requirements Document |
| 📦已归档 | [`a17-3-1-consultation-execution`](_archive/13-2026-06-29-batch/a17-3-1-consultation-execution/requirements.md) | 15/16 | Requirements Document |
| 📦已归档 | [`a17-3-consultation-record`](_archive/13-2026-06-29-batch/a17-3-consultation-record/requirements.md) | 16/17 | Requirements Document |
| 📦已归档 | [`a17-4-disagreement-record`](_archive/13-2026-06-29-batch/a17-4-disagreement-record/requirements.md) | 16/17 | Requirements Document |
| 📦已归档 | [`a17-6-closing-meeting`](_archive/13-2026-06-29-batch/a17-6-closing-meeting/requirements.md) | 15/15 | Requirements Document |
| 📦已归档 | [`a17-7-independence-declaration`](_archive/13-2026-06-29-batch/a17-7-independence-declaration/requirements.md) | 20/21 | Requirements Document |
| 📦已归档 | [`a17-audit-summary-bundle`](_archive/13-2026-06-29-batch/a17-audit-summary-bundle/requirements.md) | 23/44 | 需求文档：A17 审计总结聚合升级 |
| 📦已归档 | [`a17-summary-enhancement`](_archive/12-2026-06-23-batch/a17-summary-enhancement/requirements.md) | 45/45 | Requirements Document |
| 📦已归档 | [`a18-1-regulatory-submission`](_archive/13-2026-06-29-batch/a18-1-regulatory-submission/requirements.md) | 15/15 | Requirements Document |
| 📦已归档 | [`a18-2-regulatory-communication`](_archive/13-2026-06-29-batch/a18-2-regulatory-communication/requirements.md) | 14/15 | Requirements Document |
| 📦已归档 | [`a27-1-it-audit-memo`](_archive/13-2026-06-29-batch/a27-1-it-audit-memo/requirements.md) | 24/24 | Requirements Document |
| 📦已归档 | [`a3-8-goodwill-impairment`](_archive/13-2026-06-29-batch/a3-8-goodwill-impairment/requirements.md) | 9/9 | Requirements — A3-8 商誉减值测试专属组件 |
| 📦已归档 | [`a5-1-cashflow-audit`](_archive/13-2026-06-29-batch/a5-1-cashflow-audit/requirements.md) | 23/25 | Requirements — A5-1 现金流量表审计 精美 HTML 专属组件 |
| 📦已归档 | [`a8-1-other-info-representation`](_archive/13-2026-06-29-batch/a8-1-other-info-representation/requirements.md) | 22/22 | Requirements Document |
| 📦已归档 | [`a9-1-deficiency-letter`](_archive/13-2026-06-29-batch/a9-1-deficiency-letter/requirements.md) | 28/28 | Requirements Document |
| 📦已归档 | [`a9-2-deficiency-letter-governance`](_archive/13-2026-06-29-batch/a9-2-deficiency-letter-governance/requirements.md) ⧉platform | 18/18 | Requirements Document |
| 📦已归档 | [`adj-formula-repair-and-approval-gate-wiring`](_archive/06-engineering-governance/adj-formula-repair-and-approval-gate-wiring/requirements.md) | 40/40 | 需求文档：ADJ 取数修复与调整分录确认门接线 |
| 📦已归档 | [`adjudication-export-template`](_archive/05-business-features/adjudication-export-template/requirements.md) ⧉attachment | 37/37 | Requirements Document |
| 📦已归档 | [`adjustment-collaboration-and-propagation`](_archive/05-business-features/adjustment-collaboration-and-propagation/requirements.md) | 16/17 | Requirements Document |
| 📦已归档 | [`adjustment-detail-account-code`](_archive/05-business-features/adjustment-detail-account-code/requirements.md) | 21/21 | Requirements Document |
| 📦已归档 | [`adjustment-import-export-contract`](_archive/05-business-features/adjustment-import-export-contract/requirements.md) | 26/26 | Requirements Document |
| 📦已归档 | [`aging-config-enhancement`](_archive/05-business-features/aging-config-enhancement/requirements.md) | 40/40 | Requirements Document |
| 📦已归档 | [`audit-check-review-gate-hardening`](_archive/05-business-features/audit-check-review-gate-hardening/requirements.md) | 27/27 | Requirements Document |
| 📦已归档 | [`audit-evidence-attachment-preview-format-expansion`](_archive/05-business-features/audit-evidence-attachment-preview-format-expansion/requirements.md) ⧉cycle | 20/20 | Requirements Document |
| 📦已归档 | [`audit-review-dialog`](_archive/05-business-features/audit-review-dialog/requirements.md) | 47/47 | Requirements Document |
| 📦已归档 | [`audit-sheet-editable`](_archive/07-workpaper-slimdown/audit-sheet-editable/requirements.md) ⧉cycle | 18/18 | Requirements: 审定表可编辑升级 (GtAuditSheet) |
| 📦已归档 | [`b-cycle-sync-foundation-and-first-canary`](_archive/16-workpaper-sync-cycle-lanes/b-cycle-sync-foundation-and-first-canary/requirements.md) ⧉cycle | 27/33 | B 循环双向回写地基与首张 canary — 需求 |
| 📦已归档 | [`b-cycle-workpapers`](_archive/10-A~S-workpaper-all-cycles-complete/b-cycle-workpapers/requirements.md) | 50/53 | B 类底稿（承接与计划）— 需求文档 |
| 📦已归档 | [`b1-4-due-diligence-report`](_archive/13-2026-06-29-batch/b1-4-due-diligence-report/requirements.md) | 35/35 | Requirements Document |
| 📦已归档 | [`b2-predecessor-communication-hardening`](_archive/05-business-features/b2-predecessor-communication-hardening/requirements.md) | 17/17 | B2 前任-后任注册会计师沟通模块加固 — 需求 |
| 📦已归档 | [`b22-entity-control-rework`](_archive/05-business-features/b22-entity-control-rework/requirements.md) | 32/32 | Requirements Document |
| 📦已归档 | [`b22a-control-matrix`](_archive/13-2026-06-29-batch/b22a-control-matrix/requirements.md) | 47/47 | Requirements Document |
| 📦已归档 | [`b22b-deficiency-evaluation`](_archive/13-2026-06-29-batch/b22b-deficiency-evaluation/requirements.md) | 45/45 | Requirements Document |
| 📦已归档 | [`b23-business-control-rework`](_archive/05-business-features/b23-business-control-rework/requirements.md) | 26/27 | Requirements Document |
| 📦已归档 | [`b23-process-control`](_archive/13-2026-06-29-batch/b23-process-control/requirements.md) | 59/59 | Requirements Document |
| 📦已归档 | [`b30-group-audit`](_archive/13-2026-06-29-batch/b30-group-audit/requirements.md) | 26/63 | Requirements Document |
| 📦已归档 | [`b50-risk-assessment`](_archive/13-2026-06-29-batch/b50-risk-assessment/requirements.md) ⧉platform | 41/41 | Requirements Document |
| 📦已归档 | [`b50-workpaper-rework`](_archive/05-business-features/b50-workpaper-rework/requirements.md) | 10/10 | Requirements Document |
| 📦已归档 | [`b60-dedicated-component`](_archive/05-business-features/b60-dedicated-component/requirements.md) | 37/37 | Requirements Document |
| 📦已归档 | [`bad-debt-sheet-enhancement`](_archive/05-business-features/bad-debt-sheet-enhancement/requirements.md) | 24/35 | Requirements Document |
| 📦已归档 | [`c-cycle-sync-foundation-and-first-canary`](_archive/16-workpaper-sync-cycle-lanes/c-cycle-sync-foundation-and-first-canary/requirements.md) ⧉cycle | 28/37 | C 循环双向回写地基与首张 canary — 需求 |
| 📦已归档 | [`c-cycle-workpapers`](_archive/10-A~S-workpaper-all-cycles-complete/c-cycle-workpapers/requirements.md) | 42/42 | C 类底稿（控制测试）— 需求文档 |
| 📦已归档 | [`c1-entity-level-control`](_archive/05-business-features/c1-entity-level-control/requirements.md) | 22/22 | Requirements Document |
| 📦已归档 | [`c22-itgc-bundle`](_archive/05-business-features/c22-itgc-bundle/requirements.md) | 26/26 | Requirements Document |
| 📦已归档 | [`c22-itgc-no-switch-and-domain-code-sheet-lane`](_archive/16-workpaper-sync-cycle-lanes/c22-itgc-no-switch-and-domain-code-sheet-lane/requirements.md) ⧉cycle | 13/17 | C22 ITGC 无开关与域码 sheet 名通道 — 需求 |
| 📦已归档 | [`c23-c24-journal-entry-testing`](_archive/05-business-features/c23-c24-journal-entry-testing/requirements.md) | 25/25 | Requirements Document |
| 📦已归档 | [`c25-c26-internal-audit-info-control`](_archive/05-business-features/c25-c26-internal-audit-info-control/requirements.md) | 20/20 | Requirements Document |
| 📦已归档 | [`confirmation-alternative-d0-5`](_archive/11-confirmation-d0-module/confirmation-alternative-d0-5/requirements.md) | 31/31 | Requirements Document |
| 📦已归档 | [`confirmation-alternative-d0-6`](_archive/11-confirmation-d0-module/confirmation-alternative-d0-6/requirements.md) | 14/14 | Requirements Document |
| 📦已归档 | [`confirmation-alternative-factory-convergence`](_archive/05-business-features/confirmation-alternative-factory-convergence/requirements.md) | 13/13 | Requirements Document |
| 📦已归档 | [`confirmation-alternative-structure-alignment`](_archive/05-business-features/confirmation-alternative-structure-alignment/requirements.md) | 19/19 | Requirements Document |
| 📦已归档 | [`confirmation-attachment-ocr-linkage`](_archive/05-business-features/confirmation-attachment-ocr-linkage/requirements.md) ⧉attachment+cycle | 28/28 | Requirements Document |
| 📦已归档 | [`confirmation-coverage-single-source`](_archive/05-business-features/confirmation-coverage-single-source/requirements.md) | 8/8 | Requirements Document |
| 📦已归档 | [`confirmation-diff-checklist-d0-4b`](_archive/11-confirmation-d0-module/confirmation-diff-checklist-d0-4b/requirements.md) | 28/28 | Requirements Document |
| 📦已归档 | [`confirmation-diff-reconcile-d0-4`](_archive/11-confirmation-d0-module/confirmation-diff-reconcile-d0-4/requirements.md) | 34/34 | Requirements Document |
| 📦已归档 | [`confirmation-entity-verify-d0-2`](_archive/11-confirmation-d0-module/confirmation-entity-verify-d0-2/requirements.md) | 35/35 | Requirements Document |
| 📦已归档 | [`confirmation-followup-d0-3`](_archive/11-confirmation-d0-module/confirmation-followup-d0-3/requirements.md) | 32/32 | Requirements Document |
| 📦已归档 | [`confirmation-fraud-risk-d0-8`](_archive/11-confirmation-d0-module/confirmation-fraud-risk-d0-8/requirements.md) | 20/20 | Requirements Document |
| 📦已归档 | [`confirmation-hub-workbench-tabs`](_archive/05-business-features/confirmation-hub-workbench-tabs/requirements.md) | 32/33 | Requirements Document |
| 📦已归档 | [`confirmation-linkage-completion`](_archive/11-confirmation-d0-module/confirmation-linkage-completion/requirements.md) | 19/19 | Requirements Document |
| 📦已归档 | [`confirmation-module-coordination`](_archive/11-confirmation-d0-module/confirmation-module-coordination/requirements.md) | 19/19 | Requirements Document |
| 📦已归档 | [`confirmation-orphan-and-amount-format-closure`](_archive/11-confirmation-d0-module/confirmation-orphan-and-amount-format-closure/requirements.md) | 13/13 | Requirements Document |
| 📦已归档 | [`confirmation-reliability-d0-7`](_archive/11-confirmation-d0-module/confirmation-reliability-d0-7/requirements.md) | 25/25 | Requirements Document |
| 📦已归档 | [`confirmation-shared-model-extension`](_archive/05-business-features/confirmation-shared-model-extension/requirements.md) | 19/19 | Requirements Document |
| 📦已归档 | [`custom-workpaper-formula-binding`](_archive/07-workpaper-slimdown/custom-workpaper-formula-binding/requirements.md) ⧉formula | 58/58 | Requirements Document |
| 📦已归档 | [`custom-workpaper-template-ingestion-and-sync-closure`](_archive/17-2026-10-03-verified-batch/custom-workpaper-template-ingestion-and-sync-closure/requirements.md) ⧉writeback | 15/19 | Requirements Document |
| 📦已归档 | [`cutoff-test-architecture-convergence`](_archive/05-business-features/cutoff-test-architecture-convergence/requirements.md) ⧉platform | 16/17 | Requirements Document |
| 📦已归档 | [`cutoff-test-auto-sampling`](_archive/05-business-features/cutoff-test-auto-sampling/requirements.md) ⧉cycle+platform | 45/45 | Requirements Document: 通用截止测试自动提取组件 |
| 📦已归档 | [`cycle-palette-single-source`](_archive/05-business-features/cycle-palette-single-source/requirements.md) | 11/11 | 审计循环色板单一真源 — Requirements |
| 📦已归档 | [`d-cycle-disclosure-note-enhancement`](_archive/08-disclosure-notes/d-cycle-disclosure-note-enhancement/requirements.md) ⧉cycle | 13/13 | Requirements Document |
| 📦已归档 | [`d-cycle-extraction-chain-completion`](_archive/08-disclosure-notes/d-cycle-extraction-chain-completion/requirements.md) | 26/26 | Requirements Document |
| 📦已归档 | [`d-cycle-four-table-extraction-and-disclosure-completion`](_archive/08-disclosure-notes/d-cycle-four-table-extraction-and-disclosure-completion/requirements.md) ⧉cycle | 31/31 | Requirements Document |
| 📦已归档 | [`d-cycle-four-table-extraction-formulas`](_archive/05-business-features/d-cycle-four-table-extraction-formulas/requirements.md) | 30/30 | Requirements Document |
| 📦已归档 | [`d-cycle-remaining-disclosure-alignment`](_archive/08-disclosure-notes/d-cycle-remaining-disclosure-alignment/requirements.md) ⧉cycle | 48/48 | Requirements Document |
| 📦已归档 | [`d-cycle-sheet-bidirectional-expansion`](_archive/17-2026-10-03-verified-batch/d-cycle-sheet-bidirectional-expansion/tasks.md) ⧉cycle | 9/9 | Implementation Plan — D-cycle sheet bidirectional expansion |
| 📦已归档 | [`d-cycle-tier-a-writeback-detail-seed`](_archive/05-business-features/d-cycle-tier-a-writeback-detail-seed/requirements.md) ⧉cycle | 20/21 | Requirements Document |
| 📦已归档 | [`d-cycle-workpapers`](_archive/10-A~S-workpaper-all-cycles-complete/d-cycle-workpapers/requirements.md) | 47/47 | D 类底稿（销售收入循环）— 需求文档 |
| 📦已归档 | [`d0-onlyoffice-migration`](_archive/04-infra-architecture/d0-onlyoffice-migration/requirements.md) ⧉cycle+platform | 10/10 | 需求：多 sheet 底稿非核心 Sheet 切换到 OnlyOffice 渲染 |
| 📦已归档 | [`d1-adjudication-table`](_archive/05-business-features/d1-adjudication-table/requirements.md) | 50/50 | Requirements Document |
| 📦已归档 | [`d1-disclosure-note`](_archive/05-business-features/d1-disclosure-note/requirements.md) ⧉cycle | 57/57 | Requirements Document |
| 📦已归档 | [`d1-ecl-provision`](_archive/05-business-features/d1-ecl-provision/requirements.md) | 36/36 | Requirements Document |
| 📦已归档 | [`d1-endorsement-discount`](_archive/05-business-features/d1-endorsement-discount/requirements.md) | 51/51 | Requirements Document |
| 📦已归档 | [`d1-extraction-chain-completion`](_archive/08-disclosure-notes/d1-extraction-chain-completion/requirements.md) | 28/28 | Requirements Document |
| 📦已归档 | [`d1-four-table-extraction-formula-wiring`](_archive/08-disclosure-notes/d1-four-table-extraction-formula-wiring/requirements.md) | 14/14 | Requirements Document |
| 📦已归档 | [`d1-inspection-check`](_archive/05-business-features/d1-inspection-check/requirements.md) | 52/52 | Requirements Document |
| 📦已归档 | [`d1-notes-receivable`](_archive/13-2026-06-29-batch/d1-notes-receivable/requirements.md) ⧉cycle | 76/76 | Requirements Document |
| 📦已归档 | [`d1-notes-receivable-disclosure-alignment`](_archive/08-disclosure-notes/d1-notes-receivable-disclosure-alignment/requirements.md) ⧉cycle | 135/135 | D1 应收票据披露表与附注对齐 — 需求 |
| 📦已归档 | [`d1-sync-row-table-engine-and-d1-coverage`](_archive/31-row-table-engine-and-d1-coverage/d1-sync-row-table-engine-and-d1-coverage/requirements.md) ⧉cycle | 36/36 | Requirements Document |
| 📦已归档 | [`d1-writeoff-check`](_archive/05-business-features/d1-writeoff-check/requirements.md) | 24/24 | Requirements Document |
| 📦已归档 | [`d2-7-voucher-check-enhancement`](_archive/05-business-features/d2-7-voucher-check-enhancement/requirements.md) ⧉cycle | 31/31 | Requirements Document |
| 📦已归档 | [`d2-accounts-receivable`](_archive/13-2026-06-29-batch/d2-accounts-receivable/requirements.md) | 43/77 | Requirements Document |
| 📦已归档 | [`d2-accounts-receivable-refactor`](_archive/05-business-features/d2-accounts-receivable-refactor/requirements.md) | 92/115 | Requirements Document: D2 应收账款底稿精细化组件拆分 |
| 📦已归档 | [`d2-ar-disclosure-soe-alignment`](_archive/08-disclosure-notes/d2-ar-disclosure-soe-alignment/requirements.md) ⧉cycle | 25/25 | Requirements: d2-ar-disclosure-soe-alignment |
| 📦已归档 | [`d2-ar-disclosure-template-alignment`](_archive/08-disclosure-notes/d2-ar-disclosure-template-alignment/requirements.md) ⧉cycle | 31/31 | Requirements Document |
| 📦已归档 | [`d2-post-review-fixes`](_archive/05-business-features/d2-post-review-fixes/tasks.md) | 7/7 | Implementation Plan: D2 复盘修复 |
| 📦已归档 | [`d2-sync-coverage-via-row-table-engine`](_archive/16-workpaper-sync-cycle-lanes/d2-sync-coverage-via-row-table-engine/requirements.md) ⧉cycle | 16/18 | Requirements Document |
| 📦已归档 | [`d3-prepaid-accounts`](_archive/05-business-features/d3-prepaid-accounts/requirements.md) | 83/83 | Requirements Document: D3 预收账款底稿专属HTML精美组件 |
| 📦已归档 | [`d3-sync-coverage-via-row-table-engine`](_archive/17-2026-10-03-verified-batch/d3-sync-coverage-via-row-table-engine/requirements.md) ⧉cycle | 17/17 | Requirements Document |
| 📦已归档 | [`d4-1-adjudication-bidirectional-writeback-and-formula-io`](_archive/14-d4-bidirectional-writeback/d4-1-adjudication-bidirectional-writeback-and-formula-io/requirements.md) ⧉cycle | 12/12 | Requirements Document |
| 📦已归档 | [`d4-12-contract-inspection`](_archive/05-business-features/d4-12-contract-inspection/requirements.md) | 43/43 | D4-12 合同检查表升级 — 需求文档 |
| 📦已归档 | [`d4-12-transposed-writeback`](_archive/14-d4-bidirectional-writeback/d4-12-transposed-writeback/requirements.md) ⧉cycle | 15/15 | Requirements — D4-12 合同检查表 转置双向回写 |
| 📦已归档 | [`d4-14-walkthrough-test`](_archive/05-business-features/d4-14-walkthrough-test/requirements.md) | 73/74 | D4-14 营业收入发生检查表（穿行测试）升级 — 需求文档 |
| 📦已归档 | [`d4-14-walkthrough-writeback`](_archive/14-d4-bidirectional-writeback/d4-14-walkthrough-writeback/requirements.md) ⧉cycle | 12/13 | Requirements — D4-14 营业收入发生检查表（穿行测试）双向回写 |
| 📦已归档 | [`d4-21-24-oo-bidirectional-and-cross-sheet-formula`](_archive/14-d4-bidirectional-writeback/d4-21-24-oo-bidirectional-and-cross-sheet-formula/requirements.md) ⧉cycle | 10/11 | D4-21~24 需求 |
| 📦已归档 | [`d4-33-36-writeback-formula-and-io-closure`](_archive/14-d4-bidirectional-writeback/d4-33-36-writeback-formula-and-io-closure/requirements.md) ⧉cycle | 35/42 | Requirements Document |
| 📦已归档 | [`d4-4-adjustment-summary-bidirectional-writeback`](_archive/17-2026-10-03-verified-batch/d4-4-adjustment-summary-bidirectional-writeback/requirements.md) ⧉cycle | 23/23 | D4-4 营业收入调整分录汇总 —— HTML ↔ OnlyOffice 双向回写 |
| 📦已归档 | [`d4-9-customer-structure-bidirectional-writeback`](_archive/14-d4-bidirectional-writeback/d4-9-customer-structure-bidirectional-writeback/requirements.md) ⧉cycle | 12/15 | Requirements — D4-9 重要客户结构分析 HTML↔OnlyOffice 双向回写 |
| 📦已归档 | [`d4-adjustment-and-analysis-gap-closure`](_archive/14-d4-bidirectional-writeback/d4-adjustment-and-analysis-gap-closure/requirements.md) ⧉cycle | 1/1 | D4-4/8/12调整与分析遗漏闭环 |
| 📦已归档 | [`d4-cutoff-return-writeback-formula-io`](_archive/14-d4-bidirectional-writeback/d4-cutoff-return-writeback-formula-io/requirements.md) ⧉cycle | 13/13 | Requirements Document |
| 📦已归档 | [`d4-dual-mode-formula-governance`](_archive/14-d4-bidirectional-writeback/d4-dual-mode-formula-governance/requirements.md) ⧉cycle+platform | 16/16 | D4 双模式公式治理与36底稿覆盖总纲 |
| 📦已归档 | [`d4-four-table-extraction-and-disclosure-alignment`](_archive/08-disclosure-notes/d4-four-table-extraction-and-disclosure-alignment/requirements.md) ⧉cycle | 33/33 | Requirements Document |
| 📦已归档 | [`d4-html-to-oo-store-contract-alignment`](_archive/15-workpaper-sync-engine-hardening/d4-html-to-oo-store-contract-alignment/requirements.md) | 18/18 | Requirements Document |
| 📦已归档 | [`d4-inspection-writeback-formula-io`](_archive/14-d4-bidirectional-writeback/d4-inspection-writeback-formula-io/requirements.md) ⧉cycle | 9/16 | Requirements Document |
| 📦已归档 | [`d4-ipo-checklist-dual-mode-writeback-and-formula`](_archive/14-d4-bidirectional-writeback/d4-ipo-checklist-dual-mode-writeback-and-formula/requirements.md) ⧉cycle | 28/30 | Requirements Document |
| 📦已归档 | [`d4-ipo-fraud-writeback-formula-io`](_archive/14-d4-bidirectional-writeback/d4-ipo-fraud-writeback-formula-io/requirements.md) ⧉cycle | 11/11 | Requirements Document |
| 📦已归档 | [`d4-operating-revenue`](_archive/05-business-features/d4-operating-revenue/requirements.md) | 85/85 | Requirements Document: D4 营业收入底稿专属HTML精美组件 |
| 📦已归档 | [`d4-price-analysis-writeback-linkage`](_archive/14-d4-bidirectional-writeback/d4-price-analysis-writeback-linkage/requirements.md) ⧉cycle | 9/10 | Requirements — D4 价格分析双向回写联动（D4-10/11）+ 行同步回写死代码修复 |
| 📦已归档 | [`d4-revenue-matrix-bidirectional`](_archive/14-d4-bidirectional-writeback/d4-revenue-matrix-bidirectional/requirements.md) ⧉cycle | 13/14 | Requirements Document |
| 📦已归档 | [`d5-enhancement-polish`](_archive/05-business-features/d5-enhancement-polish/requirements.md) | 15/15 | Requirements: D5 应收款项融资底稿增强打磨 |
| 📦已归档 | [`d5-receivables-financing`](_archive/05-business-features/d5-receivables-financing/requirements.md) | 58/58 | Requirements Document: D5 应收款项融资底稿专属HTML精美组件 |
| 📦已归档 | [`d567-sync-coverage-via-row-table-engine`](_archive/17-2026-10-03-verified-batch/d567-sync-coverage-via-row-table-engine/requirements.md) ⧉cycle | 23/23 | Requirements Document |
| 📦已归档 | [`d6-contract-assets`](_archive/05-business-features/d6-contract-assets/requirements.md) ⧉platform | 85/85 | Requirements Document: D6 合同资产底稿专属HTML精美组件 |
| 📦已归档 | [`d6-enhancement-polish`](_archive/05-business-features/d6-enhancement-polish/requirements.md) | 17/17 | Requirements: D6 合同资产底稿增强打磨 |
| 📦已归档 | [`d7-contract-liabilities`](_archive/05-business-features/d7-contract-liabilities/requirements.md) | 77/77 | Requirements Document: D7 合同负债底稿专属HTML精美组件 |
| 📦已归档 | [`d7-contract-liabilities-enhancement`](_archive/05-business-features/d7-contract-liabilities-enhancement/requirements.md) | 13/13 | Requirements Document |
| 📦已归档 | [`d7-enhancement-polish`](_archive/05-business-features/d7-enhancement-polish/requirements.md) | 15/15 | Requirements: D7 合同负债底稿增强打磨 |
| 📦已归档 | [`e-cycle-extraction-formula-and-disclosure-completion`](_archive/08-disclosure-notes/e-cycle-extraction-formula-and-disclosure-completion/requirements.md) ⧉cycle | 24/24 | Requirements Document |
| 📦已归档 | [`e-cycle-workpapers`](_archive/10-A~S-workpaper-all-cycles-complete/e-cycle-workpapers/requirements.md) | 39/39 | E 类底稿（货币资金循环）— 需求文档 |
| 📦已归档 | [`e0-confirmation-completion`](_archive/08-disclosure-notes/e0-confirmation-completion/requirements.md) | 18/18 | Requirements Document |
| 📦已归档 | [`e0-send-list-components`](_archive/05-business-features/e0-send-list-components/requirements.md) | 12/12 | Requirements Document |
| 📦已归档 | [`e0-send-list-dedicated-components`](_archive/08-disclosure-notes/e0-send-list-dedicated-components/requirements.md) | 18/18 | Requirements Document |
| 📦已归档 | [`e1-four-table-extraction-and-disclosure-alignment`](_archive/08-disclosure-notes/e1-four-table-extraction-and-disclosure-alignment/requirements.md) ⧉cycle | 20/20 | Requirements Document |
| 📦已归档 | [`e1-monetary-fund-refactor`](_archive/05-business-features/e1-monetary-fund-refactor/requirements.md) | 66/66 | Requirements Document: E1 货币资金专属组件 |
| 📦已归档 | [`e1-orphan-components-wiring`](_archive/08-disclosure-notes/e1-orphan-components-wiring/requirements.md) | 14/14 | Requirements Document |
| 📦已归档 | [`e1-sheet-content-completion`](_archive/05-business-features/e1-sheet-content-completion/tasks.md) | 25/25 | Implementation Plan: E1 货币资金各 sheet 内容完整性补全 |
| 📦已归档 | [`e1-variant-recalc-and-mutation-denominator-closure`](_archive/08-disclosure-notes/e1-variant-recalc-and-mutation-denominator-closure/requirements.md) | 13/19 | Requirements Document |
| 📦已归档 | [`e2e-business-flow`](_archive/05-business-features/e2e-business-flow/requirements.md) | 58/58 | 业务流程端到端联调 — 需求文档 v2.0 |
| 📦已归档 | [`f-cycle-disclosure-parity`](_archive/08-disclosure-notes/f-cycle-disclosure-parity/requirements.md) ⧉cycle | 38/38 | Requirements: F 类披露表与附注对齐补齐（F1 / F3 / F4 追平 F2） |
| 📦已归档 | [`f-cycle-four-table-extraction-and-disclosure-completion`](_archive/08-disclosure-notes/f-cycle-four-table-extraction-and-disclosure-completion/requirements.md) ⧉cycle | 88/109 | Requirements Document |
| 📦已归档 | [`f-cycle-workpapers`](_archive/10-A~S-workpaper-all-cycles-complete/f-cycle-workpapers/requirements.md) | 58/58 | F 类底稿（采购存货循环）— 需求文档 |
| 📦已归档 | [`f0-confirmation`](_archive/05-business-features/f0-confirmation/requirements.md) | 21/21 | Requirements Document |
| 📦已归档 | [`f0-confirmation-linkage-and-structural-enhancement`](_archive/11-confirmation-d0-module/f0-confirmation-linkage-and-structural-enhancement/requirements.md) | 144/144 | Requirements Document |
| 📦已归档 | [`f1-extraction-chain-and-disclosure-source-fidelity`](_archive/08-disclosure-notes/f1-extraction-chain-and-disclosure-source-fidelity/requirements.md) ⧉cycle | 16/17 | Requirements Document |
| 📦已归档 | [`f1-four-table-extraction-and-disclosure-alignment`](_archive/08-disclosure-notes/f1-four-table-extraction-and-disclosure-alignment/requirements.md) ⧉cycle | 23/23 | Requirements Document |
| 📦已归档 | [`f1-prepayment`](_archive/05-business-features/f1-prepayment/requirements.md) | 75/75 | Requirements Document |
| 📦已归档 | [`f1-prepayment-disclosure-template-alignment`](_archive/08-disclosure-notes/f1-prepayment-disclosure-template-alignment/requirements.md) ⧉cycle | 49/49 | F1 预付款项披露表 ↔ 附注模板对齐 — 需求 |
| 📦已归档 | [`f1-sync-coverage-and-first-canary`](_archive/34-f-cycle-sync-coverage/f1-sync-coverage-and-first-canary/requirements.md) ⧉cycle | 22/22 | Introduction |
| 📦已归档 | [`f2-adjudication-import-export`](_archive/05-business-features/f2-adjudication-import-export/requirements.md) | 9/10 | Requirements Document |
| 📦已归档 | [`f2-detail-ledger-pull`](_archive/05-business-features/f2-detail-ledger-pull/requirements.md) ⧉cycle | 11/11 | Requirements Document |
| 📦已归档 | [`f2-four-table-extraction-refresh`](_archive/05-business-features/f2-four-table-extraction-refresh/requirements.md) | 22/22 | Requirements Document |
| 📦已归档 | [`f2-inventory-account-mapping-and-linkage`](_archive/08-disclosure-notes/f2-inventory-account-mapping-and-linkage/requirements.md) | 13/13 | Requirements Document |
| 📦已归档 | [`f2-inventory-cross-sheet-hardening`](_archive/05-business-features/f2-inventory-cross-sheet-hardening/requirements.md) | 18/18 | Requirements Document |
| 📦已归档 | [`f2-inventory-disclosure-template-alignment`](_archive/08-disclosure-notes/f2-inventory-disclosure-template-alignment/requirements.md) ⧉cycle | 141/141 | Requirements Document |
| 📦已归档 | [`f2-inventory-main`](_archive/05-business-features/f2-inventory-main/requirements.md) | 85/85 | Requirements Document |
| 📦已归档 | [`f2-inventory-special`](_archive/05-business-features/f2-inventory-special/requirements.md) | 71/71 | Requirements Document |
| 📦已归档 | [`f2-inventory-stocktake`](_archive/05-business-features/f2-inventory-stocktake/requirements.md) | 40/40 | Requirements: F2 存货监盘专属 HTML 组件 |
| 📦已归档 | [`f2-inventory-valuation-impairment`](_archive/05-business-features/f2-inventory-valuation-impairment/requirements.md) | 46/59 | Requirements Document |
| 📦已归档 | [`f2-sync-coverage-four-entry-lanes`](_archive/34-f-cycle-sync-coverage/f2-sync-coverage-four-entry-lanes/requirements.md) ⧉cycle | 26/27 | Introduction |
| 📦已归档 | [`f3-notes-payable`](_archive/05-business-features/f3-notes-payable/requirements.md) ⧉cycle | 39/39 | Requirements Document |
| 📦已归档 | [`f3-sync-coverage-and-first-canary`](_archive/34-f-cycle-sync-coverage/f3-sync-coverage-and-first-canary/requirements.md) ⧉cycle | 19/20 | Requirements Document |
| 📦已归档 | [`f4-accounts-payable`](_archive/05-business-features/f4-accounts-payable/requirements.md) | 42/42 | Requirements Document |
| 📦已归档 | [`f4-aging-enum-unification`](_archive/05-business-features/f4-aging-enum-unification/requirements.md) ⧉platform | 23/24 | Requirements Document |
| 📦已归档 | [`f4-sync-coverage-and-first-canary`](_archive/34-f-cycle-sync-coverage/f4-sync-coverage-and-first-canary/requirements.md) ⧉cycle | 19/20 | Requirements Document |
| 📦已归档 | [`f5-cost-of-sales`](_archive/05-business-features/f5-cost-of-sales/requirements.md) | 42/42 | Requirements Document |
| 📦已归档 | [`f5-sync-coverage-and-first-canary`](_archive/34-f-cycle-sync-coverage/f5-sync-coverage-and-first-canary/requirements.md) ⧉cycle | 21/22 | Requirements Document |
| 📦已归档 | [`fghi-sheet-content-completion`](_archive/05-business-features/fghi-sheet-content-completion/requirements.md) | 97/97 | Requirements Document |
| 📦已归档 | [`g-cycle-adjudication-sheets-coverage`](_archive/33-g-cycle-adjudication-sheets-coverage/g-cycle-adjudication-sheets-coverage/requirements.md) | 12/12 | Requirements |
| 📦已归档 | [`g-cycle-extraction-mapping-and-disclosure-alignment`](_archive/08-disclosure-notes/g-cycle-extraction-mapping-and-disclosure-alignment/requirements.md) ⧉cycle | 35/35 | Requirements Document |
| 📦已归档 | [`g-cycle-single-region-detail-lanes`](_archive/16-workpaper-sync-cycle-lanes/g-cycle-single-region-detail-lanes/requirements.md) ⧉cycle | 18/18 | Requirements Document |
| 📦已归档 | [`g-cycle-sync-foundation-and-first-canary`](_archive/16-workpaper-sync-cycle-lanes/g-cycle-sync-foundation-and-first-canary/requirements.md) ⧉cycle | 19/19 | Requirements Document |
| 📦已归档 | [`g-cycle-workpapers`](_archive/10-A~S-workpaper-all-cycles-complete/g-cycle-workpapers/requirements.md) | 50/50 | G 类底稿（投资循环）— 需求文档 |
| 📦已归档 | [`g0-confirmation`](_archive/05-business-features/g0-confirmation/requirements.md) | 27/27 | Requirements Document |
| 📦已归档 | [`g0-confirmation-source-alignment`](_archive/11-confirmation-d0-module/g0-confirmation-source-alignment/requirements.md) | 23/23 | Requirements Document |
| 📦已归档 | [`g0-investment-diff-model`](_archive/05-business-features/g0-investment-diff-model/requirements.md) | 14/14 | Requirements Document |
| 📦已归档 | [`g1-trading-financial-assets`](_archive/05-business-features/g1-trading-financial-assets/requirements.md) ⧉platform | 49/50 | Requirements Document |
| 📦已归档 | [`g10-trading-financial-liabilities`](_archive/05-business-features/g10-trading-financial-liabilities/requirements.md) | 53/53 | Requirements Document |
| 📦已归档 | [`g11-investment-income`](_archive/05-business-features/g11-investment-income/requirements.md) | 51/51 | Requirements Document |
| 📦已归档 | [`g12-net-hedge-gains`](_archive/05-business-features/g12-net-hedge-gains/requirements.md) | 63/63 | Requirements Document |
| 📦已归档 | [`g13-fair-value-changes`](_archive/05-business-features/g13-fair-value-changes/requirements.md) | 35/35 | Requirements Document |
| 📦已归档 | [`g14-credit-impairment-loss`](_archive/05-business-features/g14-credit-impairment-loss/requirements.md) | 36/36 | Requirements Document |
| 📦已归档 | [`g2-interest-receivable`](_archive/05-business-features/g2-interest-receivable/requirements.md) | 41/41 | Requirements Document |
| 📦已归档 | [`g3-dividend-receivable`](_archive/05-business-features/g3-dividend-receivable/requirements.md) | 39/39 | Requirements Document |
| 📦已归档 | [`g4-bond-investment-ecl`](_archive/05-business-features/g4-bond-investment-ecl/requirements.md) | 36/56 | Requirements Document |
| 📦已归档 | [`g4-bond-investment-main`](_archive/05-business-features/g4-bond-investment-main/requirements.md) | 71/71 | Requirements Document |
| 📦已归档 | [`g4-bond-investment-sppi`](_archive/05-business-features/g4-bond-investment-sppi/requirements.md) | 45/45 | Requirements Document |
| 📦已归档 | [`g4-g6-shared-workbook-three-entry-lanes`](_archive/18-g4-g6-shared-workbook/g4-g6-shared-workbook-three-entry-lanes/requirements.md) ⧉cycle | 18/18 | Requirements Document |
| 📦已归档 | [`g5-four-table-extraction-and-disclosure-alignment`](_archive/08-disclosure-notes/g5-four-table-extraction-and-disclosure-alignment/requirements.md) ⧉cycle | 53/53 | Requirements Document |
| 📦已归档 | [`g5-long-term-receivable`](_archive/05-business-features/g5-long-term-receivable/requirements.md) | 71/71 | Requirements Document |
| 📦已归档 | [`g5-nested-sections-and-template-defects`](_archive/35-g5-m1-cycle-sync-lanes/g5-nested-sections-and-template-defects/requirements.md) | 14/14 | Requirements Document |
| 📦已归档 | [`g6-four-table-extraction-and-disclosure-alignment`](_archive/08-disclosure-notes/g6-four-table-extraction-and-disclosure-alignment/requirements.md) ⧉cycle | 10/10 | Requirements Document |
| 📦已归档 | [`g6-other-bond-investment-ecl`](_archive/05-business-features/g6-other-bond-investment-ecl/requirements.md) | 39/39 | Requirements Document |
| 📦已归档 | [`g6-other-bond-investment-main`](_archive/05-business-features/g6-other-bond-investment-main/requirements.md) | 43/43 | Requirements Document |
| 📦已归档 | [`g6-other-bond-investment-sppi`](_archive/05-business-features/g6-other-bond-investment-sppi/requirements.md) | 45/45 | Requirements Document |
| 📦已归档 | [`g7-column-alignment-and-extraction-closure`](_archive/08-disclosure-notes/g7-column-alignment-and-extraction-closure/requirements.md) | 24/24 | Requirements Document |
| 📦已归档 | [`g7-four-table-extraction-and-disclosure-alignment`](_archive/08-disclosure-notes/g7-four-table-extraction-and-disclosure-alignment/requirements.md) ⧉cycle | 34/34 | Requirements Document |
| 📦已归档 | [`g7-linkage-extraction-completion`](_archive/05-business-features/g7-linkage-extraction-completion/requirements.md) | 26/26 | Requirements Document |
| 📦已归档 | [`g7-long-term-equity-main`](_archive/05-business-features/g7-long-term-equity-main/requirements.md) | 42/42 | Requirements Document |
| 📦已归档 | [`g7-long-term-equity-method`](_archive/05-business-features/g7-long-term-equity-method/requirements.md) | 42/42 | Requirements Document |
| 📦已归档 | [`g7-long-term-equity-subsidiary`](_archive/05-business-features/g7-long-term-equity-subsidiary/requirements.md) | 50/50 | Requirements Document |
| 📦已归档 | [`g8-other-equity-instruments`](_archive/05-business-features/g8-other-equity-instruments/requirements.md) | 56/57 | Requirements Document |
| 📦已归档 | [`g9-other-noncurrent-financial`](_archive/05-business-features/g9-other-noncurrent-financial/requirements.md) | 53/57 | Requirements Document |
| 📦已归档 | [`h-cycle-extraction-formula-and-disclosure-completion`](_archive/08-disclosure-notes/h-cycle-extraction-formula-and-disclosure-completion/requirements.md) ⧉cycle | 18/18 | Requirements Document |
| 📦已归档 | [`h-cycle-four-table-extraction-and-account-mapping`](_archive/08-disclosure-notes/h-cycle-four-table-extraction-and-account-mapping/requirements.md) | 25/25 | Requirements Document |
| 📦已归档 | [`h-cycle-legacy-cleanup-and-platform-hygiene`](_archive/08-disclosure-notes/h-cycle-legacy-cleanup-and-platform-hygiene/requirements.md) | 19/19 | Requirements Document |
| 📦已归档 | [`h-cycle-sync-foundation-and-first-canary`](_archive/16-workpaper-sync-cycle-lanes/h-cycle-sync-foundation-and-first-canary/requirements.md) ⧉cycle | 22/24 | Requirements Document |
| 📦已归档 | [`h-cycle-workpapers`](_archive/10-A~S-workpaper-all-cycles-complete/h-cycle-workpapers/requirements.md) | 46/46 | H 类底稿（固定资产循环）— 需求文档 |
| 📦已归档 | [`h0-confirmation`](_archive/05-business-features/h0-confirmation/requirements.md) | 22/22 | Requirements Document: H0 固定资产循环函证 |
| 📦已归档 | [`h0-confirmation-source-fidelity-and-linkage`](_archive/11-confirmation-d0-module/h0-confirmation-source-fidelity-and-linkage/requirements.md) | 24/24 | Requirements Document |
| 📦已归档 | [`h1-fixed-assets`](_archive/05-business-features/h1-fixed-assets/requirements.md) ⧉platform | 83/83 | Requirements Document: H1 固定资产底稿专属HTML精美组件 |
| 📦已归档 | [`h1-four-table-extraction`](_archive/05-business-features/h1-four-table-extraction/requirements.md) | 30/30 | Requirements Document |
| 📦已归档 | [`h10-asset-disposal-income`](_archive/05-business-features/h10-asset-disposal-income/requirements.md) ⧉platform | 30/30 | Requirements Document: H10 资产处置损益底稿专属HTML精美组件 |
| 📦已归档 | [`h2-construction-in-progress`](_archive/05-business-features/h2-construction-in-progress/requirements.md) | 72/72 | Requirements Document: H2 在建工程底稿专属HTML精美组件 |
| 📦已归档 | [`h2-construction-in-progress-disclosure-alignment`](_archive/08-disclosure-notes/h2-construction-in-progress-disclosure-alignment/requirements.md) ⧉cycle | 7/7 | Requirements Document |
| 📦已归档 | [`h2-disclosure-linkage-and-prefill`](_archive/05-business-features/h2-disclosure-linkage-and-prefill/requirements.md) ⧉cycle | 12/18 | Requirements Document |
| 📦已归档 | [`h2-h6-h10-pilot-cross-reference-lanes`](_archive/16-workpaper-sync-cycle-lanes/h2-h6-h10-pilot-cross-reference-lanes/requirements.md) ⧉cycle | 18/20 | Requirements Document |
| 📦已归档 | [`h3-cross-workpaper-reconciliation`](_archive/05-business-features/h3-cross-workpaper-reconciliation/requirements.md) ⧉cycle | 9/9 | Requirements Document |
| 📦已归档 | [`h3-h5-h7-variant-axis-and-dynamic-column-paradigm`](_archive/16-workpaper-sync-cycle-lanes/h3-h5-h7-variant-axis-and-dynamic-column-paradigm/requirements.md) ⧉cycle | 17/18 | Requirements Document |
| 📦已归档 | [`h3-investment-property`](_archive/05-business-features/h3-investment-property/requirements.md) | 76/76 | Requirements Document: H3 投资性房地产底稿专属HTML精美组件 |
| 📦已归档 | [`h3-investment-property-disclosure-alignment`](_archive/08-disclosure-notes/h3-investment-property-disclosure-alignment/requirements.md) ⧉cycle | 11/11 | Requirements Document |
| 📦已归档 | [`h4-engineering-materials`](_archive/05-business-features/h4-engineering-materials/requirements.md) | 32/32 | Requirements Document: H4 工程物资底稿专属HTML精美组件 |
| 📦已归档 | [`h4-four-table-extraction`](_archive/05-business-features/h4-four-table-extraction/requirements.md) | 10/10 | Requirements Document |
| 📦已归档 | [`h4-h8-sub-entry-lanes-and-seed-identity-defects`](_archive/16-workpaper-sync-cycle-lanes/h4-h8-sub-entry-lanes-and-seed-identity-defects/requirements.md) ⧉cycle | 17/18 | Requirements Document |
| 📦已归档 | [`h5-disclosure-note-linkage`](_archive/05-business-features/h5-disclosure-note-linkage/requirements.md) ⧉cycle | 7/8 | Requirements Document |
| 📦已归档 | [`h5-oil-gas-assets`](_archive/05-business-features/h5-oil-gas-assets/requirements.md) ⧉platform | 40/40 | Requirements Document: H5 油气资产底稿专属HTML精美组件 |
| 📦已归档 | [`h5-oil-gas-disclosure-alignment`](_archive/08-disclosure-notes/h5-oil-gas-disclosure-alignment/requirements.md) ⧉cycle | 8/8 | Requirements Document |
| 📦已归档 | [`h6-asset-disposal-clearing`](_archive/05-business-features/h6-asset-disposal-clearing/requirements.md) ⧉platform | 27/27 | Requirements Document: H6 固定资产清理底稿专属HTML精美组件 |
| 📦已归档 | [`h7-biological-assets`](_archive/05-business-features/h7-biological-assets/requirements.md) ⧉platform | 44/44 | Requirements Document: H7 生产性生物资产底稿专属HTML精美组件 |
| 📦已归档 | [`h7-biological-assets-disclosure-rebuild`](_archive/08-disclosure-notes/h7-biological-assets-disclosure-rebuild/requirements.md) ⧉cycle+platform | 12/12 | Requirements Document |
| 📦已归档 | [`h8-right-of-use-assets`](_archive/05-business-features/h8-right-of-use-assets/requirements.md) ⧉platform | 38/38 | Requirements Document: H8 使用权资产底稿专属HTML精美组件 |
| 📦已归档 | [`h8-right-of-use-disclosure-alignment`](_archive/08-disclosure-notes/h8-right-of-use-disclosure-alignment/requirements.md) ⧉cycle | 7/7 | Requirements Document |
| 📦已归档 | [`h9-h10-remaining-disclosure-alignment`](_archive/08-disclosure-notes/h9-h10-remaining-disclosure-alignment/requirements.md) ⧉cycle | 9/9 | Requirements Document |
| 📦已归档 | [`h9-lease-liabilities`](_archive/05-business-features/h9-lease-liabilities/requirements.md) | 33/33 | Requirements Document: H9 租赁负债底稿专属HTML精美组件 |
| 📦已归档 | [`hi-cycle-four-table-extraction`](_archive/05-business-features/hi-cycle-four-table-extraction/requirements.md) | 14/14 | Requirements Document |
| 📦已归档 | [`i-cycle-extraction-formula-and-disclosure-closure`](_archive/08-disclosure-notes/i-cycle-extraction-formula-and-disclosure-closure/requirements.md) ⧉cycle | 26/26 | Requirements Document |
| 📦已归档 | [`i-cycle-four-table-extraction-and-disclosure-alignment`](_archive/08-disclosure-notes/i-cycle-four-table-extraction-and-disclosure-alignment/requirements.md) ⧉cycle | 45/45 | Requirements Document |
| 📦已归档 | [`i-cycle-orchestration`](_archive/05-business-features/i-cycle-orchestration/tasks.md) | 1/14 | Implementation Plan: I 循环总调度（i-cycle-orchestration） |
| 📦已归档 | [`i-cycle-sync-foundation-and-first-canary`](_archive/17-2026-10-03-verified-batch/i-cycle-sync-foundation-and-first-canary/requirements.md) ⧉cycle | 26/26 | Requirements Document |
| 📦已归档 | [`i-cycle-workpapers`](_archive/10-A~S-workpaper-all-cycles-complete/i-cycle-workpapers/requirements.md) | 38/38 | I 类底稿（无形资产循环）— 需求文档 |
| 📦已归档 | [`i1-i3-disclosure-positional-identity-and-classification-source`](_archive/17-2026-10-03-verified-batch/i1-i3-disclosure-positional-identity-and-classification-source/requirements.md) ⧉cycle | 22/22 | Requirements Document |
| 📦已归档 | [`i1-intangible-assets`](_archive/05-business-features/i1-intangible-assets/requirements.md) ⧉platform | 58/58 | Requirements Document: I1 无形资产、累计摊销及减值准备底稿专属HTML精美组件 |
| 📦已归档 | [`i2-development-expenditure`](_archive/05-business-features/i2-development-expenditure/requirements.md) | 52/52 | Requirements Document: I2 开发支出底稿专属HTML精美组件 |
| 📦已归档 | [`i2-i4-i5-carrier-and-structure-exceptions`](_archive/17-2026-10-03-verified-batch/i2-i4-i5-carrier-and-structure-exceptions/requirements.md) ⧉cycle | 26/26 | Requirements Document |
| 📦已归档 | [`i3-goodwill`](_archive/05-business-features/i3-goodwill/requirements.md) | 44/44 | Requirements Document: I3 商誉底稿专属HTML精美组件 |
| 📦已归档 | [`i4-long-term-prepaid`](_archive/05-business-features/i4-long-term-prepaid/requirements.md) | 38/38 | Requirements Document: I4 长期待摊费用底稿专属HTML精美组件 |
| 📦已归档 | [`i5-other-noncurrent-assets`](_archive/05-business-features/i5-other-noncurrent-assets/requirements.md) ⧉platform | 32/32 | Requirements Document: I5 其他非流动资产底稿专属HTML精美组件 |
| 📦已归档 | [`i6-research-development-expense`](_archive/05-business-features/i6-research-development-expense/requirements.md) | 41/41 | Requirements Document: I6 研发费用底稿专属HTML精美组件 |
| 📦已归档 | [`j-cycle-four-table-extraction-and-disclosure-alignment`](_archive/08-disclosure-notes/j-cycle-four-table-extraction-and-disclosure-alignment/requirements.md) ⧉cycle | 19/19 | Requirements Document |
| 📦已归档 | [`j-cycle-orchestration`](_archive/05-business-features/j-cycle-orchestration/tasks.md) | 13/13 | Implementation Plan: J 循环总调度（j-cycle-orchestration） |
| 📦已归档 | [`j-cycle-sync-foundation-and-first-canary`](_archive/17-2026-10-03-verified-batch/j-cycle-sync-foundation-and-first-canary/requirements.md) ⧉cycle | 34/34 | Requirements Document |
| 📦已归档 | [`j-cycle-workpapers`](_archive/10-A~S-workpaper-all-cycles-complete/j-cycle-workpapers/requirements.md) | 32/32 | J 类底稿（职工薪酬循环）— 需求文档 |
| 📦已归档 | [`j1-disclosure-note-linkage`](_archive/05-business-features/j1-disclosure-note-linkage/requirements.md) ⧉cycle | 12/12 | Requirements Document |
| 📦已归档 | [`j1-disclosure-template-alignment`](_archive/08-disclosure-notes/j1-disclosure-template-alignment/requirements.md) ⧉cycle | 61/61 | Requirements Document |
| 📦已归档 | [`j1-employee-compensation`](_archive/05-business-features/j1-employee-compensation/requirements.md) | 48/48 | Requirements Document: J1 应付职工薪酬底稿专属HTML精美组件 |
| 📦已归档 | [`j1-post-publish-semantic-and-evidence-closure`](_archive/17-2026-10-03-verified-batch/j1-post-publish-semantic-and-evidence-closure/requirements.md) ⧉cycle | 9/9 | J1 发布后语义与证据闭环 — 需求 |
| 📦已归档 | [`j2-defined-benefit-plan`](_archive/05-business-features/j2-defined-benefit-plan/requirements.md) | 37/37 | Requirements Document: J2 长期应付职工薪酬-设定受益计划净资产底稿专属HTML精美组件 |
| 📦已归档 | [`j2-j3-non-entry-hosts-and-orphan-cleanup`](_archive/16-workpaper-sync-cycle-lanes/j2-j3-non-entry-hosts-and-orphan-cleanup/requirements.md) ⧉cycle | 19/19 | Requirements Document |
| 📦已归档 | [`j3-share-based-payment`](_archive/05-business-features/j3-share-based-payment/requirements.md) | 33/33 | Requirements Document: J3 股份支付底稿专属HTML精美组件 |
| 📦已归档 | [`k-admin-cycle-post-review-fix`](_archive/05-business-features/k-admin-cycle-post-review-fix/design.md) | 18/18 | K 管理循环实施后复盘修复 — Bugfix Design |
| 📦已归档 | [`k-cycle-disclosure-alignment`](_archive/08-disclosure-notes/k-cycle-disclosure-alignment/requirements.md) ⧉cycle | 34/34 | Requirements Document |
| 📦已归档 | [`k-cycle-extraction-formula-and-disclosure-closure`](_archive/08-disclosure-notes/k-cycle-extraction-formula-and-disclosure-closure/requirements.md) ⧉cycle | 25/25 | Requirements Document |
| 📦已归档 | [`k-cycle-four-table-extraction-and-disclosure-completion`](_archive/08-disclosure-notes/k-cycle-four-table-extraction-and-disclosure-completion/requirements.md) ⧉cycle | 23/23 | Requirements Document |
| 📦已归档 | [`k-cycle-orchestration`](_archive/05-business-features/k-cycle-orchestration/tasks.md) | 1/15 | Implementation Plan: K 循环总调度（k-cycle-orchestration） |
| 📦已归档 | [`k-cycle-sync-foundation-and-first-canary`](_archive/26-workpaper-sync-cycle-lanes-kln/k-cycle-sync-foundation-and-first-canary/requirements.md) ⧉cycle | 27/30 | K 循环双向回写地基与首张 canary — 需求 |
| 📦已归档 | [`k-cycle-workpapers`](_archive/10-A~S-workpaper-all-cycles-complete/k-cycle-workpapers/requirements.md) | 49/49 | K 类底稿（管理循环）— 需求文档 |
| 📦已归档 | [`k0-confirmation`](_archive/05-business-features/k0-confirmation/requirements.md) | 26/26 | Requirements Document |
| 📦已归档 | [`k0-confirmation-source-alignment`](_archive/11-confirmation-d0-module/k0-confirmation-source-alignment/requirements.md) | 18/18 | Requirements Document |
| 📦已归档 | [`k1-extraction-chain-and-note-alignment`](_archive/08-disclosure-notes/k1-extraction-chain-and-note-alignment/requirements.md) ⧉cycle | 28/28 | Requirements Document |
| 📦已归档 | [`k1-four-table-extraction-and-disclosure-alignment`](_archive/08-disclosure-notes/k1-four-table-extraction-and-disclosure-alignment/requirements.md) ⧉cycle | 27/27 | Requirements Document |
| 📦已归档 | [`k1-k7-inlined-iife-hosts-and-orphan-cleanup`](_archive/26-workpaper-sync-cycle-lanes-kln/k1-k7-inlined-iife-hosts-and-orphan-cleanup/requirements.md) ⧉cycle | 24/25 | K1~K7 内联 IIFE 宿主与 orphan 清理 — 需求 |
| 📦已归档 | [`k1-other-receivable-disclosure-alignment`](_archive/08-disclosure-notes/k1-other-receivable-disclosure-alignment/requirements.md) ⧉cycle | 54/54 | K1 其他应收款披露表与附注对齐增强 — 需求 |
| 📦已归档 | [`k1-other-receivables`](_archive/05-business-features/k1-other-receivables/requirements.md) | 35/35 | Requirements Document: K1 其他应收款底稿专属HTML精美组件 |
| 📦已归档 | [`k10-other-income`](_archive/05-business-features/k10-other-income/requirements.md) | 31/31 | Requirements Document: K10 其他收益底稿专属HTML精美组件 |
| 📦已归档 | [`k11-asset-impairment-loss`](_archive/05-business-features/k11-asset-impairment-loss/requirements.md) ⧉platform | 29/29 | Requirements Document: K11 资产减值损失底稿专属HTML精美组件 |
| 📦已归档 | [`k12-non-operating-income`](_archive/05-business-features/k12-non-operating-income/requirements.md) | 29/29 | Requirements Document: K12 营业外收入底稿专属HTML精美组件 |
| 📦已归档 | [`k13-non-operating-expense`](_archive/05-business-features/k13-non-operating-expense/requirements.md) | 29/29 | Requirements Document: K13 营业外支出底稿专属HTML精美组件 |
| 📦已归档 | [`k2-four-table-extraction-and-dynamic-rows`](_archive/08-disclosure-notes/k2-four-table-extraction-and-dynamic-rows/requirements.md) | 13/13 | Requirements Document |
| 📦已归档 | [`k2-other-current-assets`](_archive/05-business-features/k2-other-current-assets/requirements.md) ⧉platform | 31/31 | Requirements Document: K2 其他流动资产底稿专属HTML精美组件 |
| 📦已归档 | [`k2-other-current-assets-disclosure-alignment`](_archive/08-disclosure-notes/k2-other-current-assets-disclosure-alignment/requirements.md) ⧉cycle+platform | 27/27 | Requirements Document |
| 📦已归档 | [`k3-other-payables`](_archive/05-business-features/k3-other-payables/requirements.md) | 30/30 | Requirements Document: K3 其他应付款底稿专属HTML精美组件 |
| 📦已归档 | [`k4-other-current-liabilities`](_archive/05-business-features/k4-other-current-liabilities/requirements.md) | 29/29 | Requirements Document: K4 其他流动负债底稿专属HTML精美组件 |
| 📦已归档 | [`k5-provisions`](_archive/05-business-features/k5-provisions/requirements.md) | 32/32 | Requirements Document: K5 预计负债底稿专属HTML精美组件 |
| 📦已归档 | [`k6-held-for-sale`](_archive/05-business-features/k6-held-for-sale/requirements.md) | 32/32 | Requirements Document: K6 持有待售资产和负债底稿专属HTML精美组件 |
| 📦已归档 | [`k7-deferred-income`](_archive/05-business-features/k7-deferred-income/requirements.md) | 31/31 | Requirements Document: K7 递延收益底稿专属HTML精美组件 |
| 📦已归档 | [`k8-k9-k11-k12-k13-dedicated-composable-and-cross-cycle-hub`](_archive/26-workpaper-sync-cycle-lanes-kln/k8-k9-k11-k12-k13-dedicated-composable-and-cross-cycle-hub/requirements.md) | 19/20 | K8/K9/K11/K12/K13 专用 composable 与跨循环枢纽 — 需求 |
| 📦已归档 | [`k8-selling-expenses`](_archive/05-business-features/k8-selling-expenses/requirements.md) | 31/32 | Requirements Document: K8 销售费用底稿专属HTML精美组件 |
| 📦已归档 | [`k9-admin-expenses`](_archive/05-business-features/k9-admin-expenses/requirements.md) | 32/32 | Requirements Document: K9 管理费用底稿专属HTML精美组件 |
| 📦已归档 | [`l-cycle-extraction-formula-and-disclosure-completion`](_archive/08-disclosure-notes/l-cycle-extraction-formula-and-disclosure-completion/requirements.md) ⧉cycle | 26/26 | Requirements Document |
| 📦已归档 | [`l-cycle-four-table-extraction-and-disclosure-alignment`](_archive/08-disclosure-notes/l-cycle-four-table-extraction-and-disclosure-alignment/requirements.md) ⧉cycle | 21/21 | Requirements Document |
| 📦已归档 | [`l-cycle-sync-foundation-and-first-canary`](_archive/17-2026-10-03-verified-batch/l-cycle-sync-foundation-and-first-canary/requirements.md) ⧉cycle | 37/37 | L 循环双向回写地基与首张 canary — 需求 |
| 📦已归档 | [`l-cycle-true-adapter-registration`](_archive/17-2026-10-03-verified-batch/l-cycle-true-adapter-registration/requirements.md) | 17/17 | L 循环真双向改线（adapter 注册）— 需求 |
| 📦已归档 | [`l-cycle-workpapers`](_archive/10-A~S-workpaper-all-cycles-complete/l-cycle-workpapers/requirements.md) | 43/43 | L 类底稿（筹资循环）— 需求文档 |
| 📦已归档 | [`l0-confirmation`](_archive/05-business-features/l0-confirmation/requirements.md) | 23/23 | Requirements Document |
| 📦已归档 | [`l0-confirmation-source-alignment`](_archive/11-confirmation-d0-module/l0-confirmation-source-alignment/requirements.md) | 20/20 | Requirements Document |
| 📦已归档 | [`l1-short-term-loans`](_archive/05-business-features/l1-short-term-loans/requirements.md) | 34/34 | Requirements Document: L1 短期借款底稿专属HTML精美组件 |
| 📦已归档 | [`l2-interest-payable`](_archive/05-business-features/l2-interest-payable/requirements.md) | 29/29 | Requirements Document: L2 应付利息底稿专属HTML精美组件 |
| 📦已归档 | [`l2-l3-l4-orphan-twins-and-sheet-granularity-collapse`](_archive/26-workpaper-sync-cycle-lanes-kln/l2-l3-l4-orphan-twins-and-sheet-granularity-collapse/requirements.md) ⧉cycle | 22/23 | L2 / L3 / L4 孤儿孪生与 sheet 粒度折叠车道 — 需求 |
| 📦已归档 | [`l3-long-term-loans`](_archive/05-business-features/l3-long-term-loans/requirements.md) | 35/35 | Requirements Document: L3 长期借款底稿专属HTML精美组件 |
| 📦已归档 | [`l4-bonds-payable`](_archive/05-business-features/l4-bonds-payable/requirements.md) | 37/37 | Requirements Document: L4 应付债券底稿专属HTML精美组件 |
| 📦已归档 | [`l5-l8-inert-switch-and-child-tab-carriers`](_archive/26-workpaper-sync-cycle-lanes-kln/l5-l8-inert-switch-and-child-tab-carriers/requirements.md) ⧉cycle | 26/27 | L5 ~ L8 死开关与子 Tab 专属载体车道 — 需求 |
| 📦已归档 | [`l5-long-term-payables`](_archive/05-business-features/l5-long-term-payables/requirements.md) | 32/32 | Requirements Document: L5 长期应付款底稿专属HTML精美组件 |
| 📦已归档 | [`l6-special-payables`](_archive/05-business-features/l6-special-payables/requirements.md) | 28/28 | Requirements Document: L6 专项应付款底稿专属HTML精美组件 |
| 📦已归档 | [`l7-other-noncurrent-liabilities`](_archive/05-business-features/l7-other-noncurrent-liabilities/requirements.md) | 28/28 | Requirements Document: L7 其他非流动负债底稿专属HTML精美组件 |
| 📦已归档 | [`l8-financial-expenses`](_archive/05-business-features/l8-financial-expenses/requirements.md) | 33/33 | Requirements Document: L8 财务费用底稿专属HTML精美组件 |
| 📦已归档 | [`ledger-balance-diagnostics-report-line-coverage`](_archive/05-business-features/ledger-balance-diagnostics-report-line-coverage/requirements.md) ⧉cycle | 74/74 | 需求文档：借贷不平衡诊断与报表行次覆盖治理 |
| 📦已归档 | [`ledger-import-header-adapter-contract`](_archive/05-business-features/ledger-import-header-adapter-contract/requirements.md) ⧉cycle | 57/57 | 需求文档：账表导入表头识别与适配器契约 |
| 📦已归档 | [`ledger-import-sign-convention-migration`](_archive/05-business-features/ledger-import-sign-convention-migration/requirements.md) ⧉cycle+platform | 64/64 | 需求文档：账表导入符号约定与历史迁移 |
| 📦已归档 | [`ledger-import-unification`](_archive/99-superseded/ledger-import-unification/requirements.md) ⧉cycle+platform | 86/138 | 账表导入统一方案 — 需求文档 |
| 📦已归档 | [`ledger-import-view-refactor`](_archive/05-business-features/ledger-import-view-refactor/requirements.md) ⧉cycle | 243/243 | Requirements — Ledger Import 四表上传解析入库整体重构 |
| 📦已归档 | [`ledger-raw-extra-column-display`](_archive/05-business-features/ledger-raw-extra-column-display/requirements.md) ⧉cycle+platform | 24/24 | Requirements Document |
| 📦已归档 | [`ledger-sign-convention-unify`](_archive/05-business-features/ledger-sign-convention-unify/requirements.md) ⧉cycle | 39/39 | 账表符号约定统一 — 需求文档 |
| 📦已归档 | [`lmn-four-table-extraction`](_archive/05-business-features/lmn-four-table-extraction/requirements.md) | 12/13 | Requirements Document |
| 📦已归档 | [`m-cycle-four-table-extraction-and-disclosure-alignment`](_archive/08-disclosure-notes/m-cycle-four-table-extraction-and-disclosure-alignment/requirements.md) ⧉cycle | 76/85 | Requirements Document |
| 📦已归档 | [`m-cycle-sync-foundation-and-first-canary`](_archive/26-workpaper-sync-cycle-lanes-kln/m-cycle-sync-foundation-and-first-canary/requirements.md) ⧉cycle | 45/46 | M 循环双向回写地基与首张 canary — 需求 |
| 📦已归档 | [`m-cycle-workpapers`](_archive/10-A~S-workpaper-all-cycles-complete/m-cycle-workpapers/requirements.md) | 46/46 | M 类底稿（股东权益循环）— 需求文档 |
| 📦已归档 | [`m1-dividends-payable`](_archive/05-business-features/m1-dividends-payable/requirements.md) | 31/31 | Requirements Document: M1 应付股利（利润）底稿专属HTML精美组件 |
| 📦已归档 | [`m1-m5-m8-m9-mode-value-and-carrier-exceptions`](_archive/35-g5-m1-cycle-sync-lanes/m1-m5-m8-m9-mode-value-and-carrier-exceptions/requirements.md) ⧉cycle | 27/27 | M1 / M5 / M8 / M9 —— mode 取值与载体例外收口 · 需求 |
| 📦已归档 | [`m10-other-equity-instruments`](_archive/05-business-features/m10-other-equity-instruments/requirements.md) | 31/31 | Requirements Document: M10 其他权益工具底稿专属HTML精美组件 |
| 📦已归档 | [`m2-paid-in-capital`](_archive/05-business-features/m2-paid-in-capital/requirements.md) | 32/32 | Requirements Document: M2 实收资本（股本）底稿专属HTML精美组件 |
| 📦已归档 | [`m3-treasury-stock`](_archive/05-business-features/m3-treasury-stock/requirements.md) | 31/31 | Requirements Document: M3 库存股底稿专属HTML精美组件 |
| 📦已归档 | [`m4-capital-reserve`](_archive/05-business-features/m4-capital-reserve/requirements.md) | 30/30 | Requirements Document: M4 资本公积底稿专属HTML精美组件 |
| 📦已归档 | [`m5-surplus-reserve`](_archive/05-business-features/m5-surplus-reserve/requirements.md) | 31/31 | Requirements Document: M5 盈余公积底稿专属HTML精美组件 |
| 📦已归档 | [`m6-retained-earnings`](_archive/05-business-features/m6-retained-earnings/requirements.md) | 31/31 | Requirements Document: M6 未分配利润底稿专属HTML精美组件 |
| 📦已归档 | [`m7-special-reserve`](_archive/05-business-features/m7-special-reserve/requirements.md) | 31/31 | Requirements Document: M7 专项储备底稿专属HTML精美组件 |
| 📦已归档 | [`m8-general-risk-reserve`](_archive/05-business-features/m8-general-risk-reserve/requirements.md) | 29/29 | Requirements Document: M8 一般风险准备底稿专属HTML精美组件 |
| 📦已归档 | [`m9-other-comprehensive-income`](_archive/05-business-features/m9-other-comprehensive-income/requirements.md) | 30/30 | Requirements Document: M9 其他综合收益底稿专属HTML精美组件 |
| 📦已归档 | [`multi-standard-unification`](_archive/05-business-features/multi-standard-unification/requirements.md) ⧉platform | 26/26 | 需求文档：多准则状态统一（multi-standard-unification） |
| 📦已归档 | [`n-cycle-note-template-and-disclosure-completion`](_archive/08-disclosure-notes/n-cycle-note-template-and-disclosure-completion/requirements.md) ⧉cycle | 13/13 | Requirements Document |
| 📦已归档 | [`n-cycle-sync-foundation-and-first-canary`](_archive/26-workpaper-sync-cycle-lanes-kln/n-cycle-sync-foundation-and-first-canary/requirements.md) ⧉cycle | 26/27 | N 循环双向回写地基与首张 canary — 需求 |
| 📦已归档 | [`n-cycle-tax-disclosure-alignment`](_archive/08-disclosure-notes/n-cycle-tax-disclosure-alignment/requirements.md) ⧉cycle | 52/52 | Requirements Document |
| 📦已归档 | [`n-cycle-workpapers`](_archive/10-A~S-workpaper-all-cycles-complete/n-cycle-workpapers/requirements.md) | 40/40 | N 类底稿（税费循环）— 需求文档 |
| 📦已归档 | [`n1-deferred-tax-assets`](_archive/05-business-features/n1-deferred-tax-assets/requirements.md) ⧉platform | 34/34 | Requirements Document: N1 递延所得税资产底稿专属HTML精美组件 |
| 📦已归档 | [`n1-deferred-tax-disclosure-template-alignment`](_archive/08-disclosure-notes/n1-deferred-tax-disclosure-template-alignment/requirements.md) ⧉cycle | 62/62 | Requirements Document |
| 📦已归档 | [`n1-disclosure-note-linkage`](_archive/08-disclosure-notes/n1-disclosure-note-linkage/requirements.md) ⧉cycle | 12/12 | Requirements Document |
| 📦已归档 | [`n1-four-table-extraction-and-disclosure-alignment`](_archive/08-disclosure-notes/n1-four-table-extraction-and-disclosure-alignment/requirements.md) ⧉cycle | 24/24 | Requirements Document |
| 📦已归档 | [`n1-loss-check-source-alignment`](_archive/05-business-features/n1-loss-check-source-alignment/requirements.md) | 25/25 | Requirements Document |
| 📦已归档 | [`n1-n3-host-inline-router-and-shared-adoption`](_archive/26-workpaper-sync-cycle-lanes-kln/n1-n3-host-inline-router-and-shared-adoption/requirements.md) ⧉cycle | 18/20 | N1 / N3 宿主内联路由与共享路由采纳 — 需求 |
| 📦已归档 | [`n2-disclosure-and-extraction-alignment`](_archive/08-disclosure-notes/n2-disclosure-and-extraction-alignment/requirements.md) ⧉cycle | 19/19 | Requirements Document |
| 📦已归档 | [`n2-n5-json-table-identity-and-cross-entry-readonly`](_archive/26-workpaper-sync-cycle-lanes-kln/n2-n5-json-table-identity-and-cross-entry-readonly/requirements.md) | 17/19 | N2 / N5 整表 JSON 行身份与跨 entry 只读 — 需求 |
| 📦已归档 | [`n2-taxes-payable`](_archive/05-business-features/n2-taxes-payable/requirements.md) | 42/42 | Requirements Document: N2 应交税费底稿专属HTML精美组件 |
| 📦已归档 | [`n2-vat-calc-source-alignment`](_archive/08-disclosure-notes/n2-vat-calc-source-alignment/requirements.md) | 19/19 | Requirements Document |
| 📦已归档 | [`n3-deferred-tax-liabilities`](_archive/05-business-features/n3-deferred-tax-liabilities/requirements.md) | 28/28 | Requirements Document: N3 递延所得税负债底稿专属HTML精美组件 |
| 📦已归档 | [`n345-four-table-extraction-alignment`](_archive/08-disclosure-notes/n345-four-table-extraction-alignment/requirements.md) | 26/26 | Requirements Document |
| 📦已归档 | [`n4-taxes-and-surcharges`](_archive/05-business-features/n4-taxes-and-surcharges/requirements.md) | 29/29 | Requirements Document: N4 税金及附加底稿专属HTML精美组件 |
| 📦已归档 | [`n5-income-tax-expense`](_archive/05-business-features/n5-income-tax-expense/requirements.md) | 42/42 | Requirements Document: N5 所得税费用底稿专属HTML精美组件 |
| 📦已归档 | [`prefill-wp-prev-resolution-repair`](_archive/04-infra-architecture/prefill-wp-prev-resolution-repair/requirements.md) | 17/17 | Requirements Document |
| 📦已归档 | [`published-representation-production-path-and-lane-adjudication`](_archive/17-2026-10-03-verified-batch/published-representation-production-path-and-lane-adjudication/requirements.md) ⧉cycle | 43/43 | Requirements Document |
| 📦已归档 | [`report-config-account-code-integrity`](_archive/04-infra-architecture/report-config-account-code-integrity/requirements.md) ⧉cycle | 12/12 | Requirements Document |
| 📦已归档 | [`report-config-baseline`](_archive/04-infra-architecture/report-config-baseline/requirements.md) ⧉cycle | 12/12 | 需求文档：report-config-baseline（报表配置主模板回填 + 联动） |
| 📦已归档 | [`report-module-enhancement`](_archive/05-business-features/report-module-enhancement/requirements.md) | 15/28 | Requirements Document |
| 📦已归档 | [`review-prompt-sheet-level-split`](_archive/05-business-features/review-prompt-sheet-level-split/requirements.md) | 42/42 | Requirements Document |
| 📦已归档 | [`s-cycle-workpapers`](_archive/10-A~S-workpaper-all-cycles-complete/s-cycle-workpapers/requirements.md) | 47/47 | S 类底稿（专项循环）— 需求文档 |
| 📦已归档 | [`s-estimate-calculation-workpapers`](_archive/05-business-features/s-estimate-calculation-workpapers/requirements.md) | 29/29 | Requirements Document |
| 📦已归档 | [`s-special-transaction-workpapers`](_archive/05-business-features/s-special-transaction-workpapers/requirements.md) | 28/28 | Requirements Document |
| 📦已归档 | [`s32-fraud-response-bundle`](_archive/05-business-features/s32-fraud-response-bundle/requirements.md) ⧉cycle | 23/23 | Requirements Document |
| 📦已归档 | [`s33-announcement14-bundle`](_archive/05-business-features/s33-announcement14-bundle/requirements.md) ⧉cycle | 23/23 | Requirements Document |
| 📦已归档 | [`s34-ipo-review-bundle`](_archive/05-business-features/s34-ipo-review-bundle/requirements.md) ⧉cycle | 40/40 | Requirements Document |
| 📦已归档 | [`s35-refinancing-bundle`](_archive/05-business-features/s35-refinancing-bundle/requirements.md) ⧉cycle | 22/22 | Requirements Document |
| 📦已归档 | [`sampling-compliance-closure`](_archive/05-business-features/sampling-compliance-closure/requirements.md) ⧉cycle | 25/25 | Requirements Document |
| 📦已归档 | [`sampling-evaluation-and-governance-closure`](_archive/05-business-features/sampling-evaluation-and-governance-closure/requirements.md) ⧉cycle+platform | 19/19 | Requirements Document |
| 📦已归档 | [`tb-adjustment-column-formula-closure`](_archive/25-2026-10-06-playwright-verified/tb-adjustment-column-formula-closure/requirements.md) | 44/44 | 试算平衡表调整列取数收口（tb-adjustment-column-formula-closure） |
| 📦已归档 | [`tb-writeback-explicit-publish-gate`](_archive/06-engineering-governance/tb-writeback-explicit-publish-gate/requirements.md) ⧉cycle | 21/21 | Requirements Document |
| 📦已归档 | [`trial-balance-cross-comparison`](_archive/05-business-features/trial-balance-cross-comparison/requirements.md) | 6/6 | Requirements Document |
| 📦已归档 | [`trial-balance-version-timemachine`](_archive/05-business-features/trial-balance-version-timemachine/requirements.md) | 8/8 | Requirements Document |
| 📦已归档 | [`voucher-check-sampling-integration`](_archive/05-business-features/voucher-check-sampling-integration/requirements.md) ⧉cycle | 14/14 | Requirements Document |
| 📦已归档 | [`voucher-sampling-account-scope-and-attach-closure`](_archive/05-business-features/voucher-sampling-account-scope-and-attach-closure/requirements.md) ⧉cycle | 59/61 | Requirements — 抽凭科目真源接线与挂凭链路收口 |
| 📦已归档 | [`voucher-sampling-engine`](_archive/05-business-features/voucher-sampling-engine/requirements.md) ⧉cycle | 48/48 | Requirements Document: 通用抽凭引擎组件 |
| 📦已归档 | [`voucher-sampling-hardening`](_archive/05-business-features/voucher-sampling-hardening/requirements.md) ⧉cycle | 40/41 | Requirements Document |
| 📦已归档 | [`workpaper-account-multifile-aggregation`](_archive/05-business-features/workpaper-account-multifile-aggregation/requirements.md) | 55/56 | 需求文档：科目底稿多文件聚合、联动与行业可扩展 |
| 📦已归档 | [`workpaper-account-package-d1-d2-pilot`](_archive/05-business-features/workpaper-account-package-d1-d2-pilot/requirements.md) | 81/81 | 需求文档：D1/D2 科目工作包试点 |
| 📦已归档 | [`workpaper-adjustment-centralization`](_archive/05-business-features/workpaper-adjustment-centralization/requirements.md) | 13/13 | Requirements Document |
| 📦已归档 | [`workpaper-ai-conclusion-copilot`](_archive/05-business-features/workpaper-ai-conclusion-copilot/requirements.md) ⧉cycle | 58/58 | 需求文档：底稿科目结论 AI 副驾驶 |
| 📦已归档 | [`workpaper-bad-debt-nested-structure`](_archive/05-business-features/workpaper-bad-debt-nested-structure/requirements.md) | 55/55 | Requirements Document |
| 📦已归档 | [`workpaper-bulk-tab-import-export`](_archive/05-business-features/workpaper-bulk-tab-import-export/requirements.md) | 39/39 | Requirements Document |
| 📦已归档 | [`workpaper-cf-verification`](_archive/07-workpaper-slimdown/workpaper-cf-verification/requirements.md) | 24/24 | Requirements: 现金流量表核查模块 |
| 📦已归档 | [`workpaper-collaboration-presence`](_archive/02-workpaper-cycles/workpaper-collaboration-presence/requirements.md) | 20/20 | 底稿协同感增强 — 需求文档 |
| 📦已归档 | [`workpaper-completion-foundation`](_archive/02-workpaper-cycles/workpaper-completion-foundation/requirements.md) | 38/38 | Requirements Document |
| 📦已归档 | [`workpaper-content-semantic-contract`](_archive/05-business-features/workpaper-content-semantic-contract/requirements.md) | 57/57 | 需求文档：底稿内容语义契约 |
| 📦已归档 | [`workpaper-cycle-d-revenue`](_archive/02-workpaper-cycles/workpaper-cycle-d-revenue/requirements.md) | 31/31 | Requirements Document |
| 📦已归档 | [`workpaper-d-sales-cycle`](_archive/02-workpaper-cycles/workpaper-d-sales-cycle/requirements.md) | 53/53 | D 销售循环底稿优化 — Requirements |
| 📦已归档 | [`workpaper-deep-optimization`](_archive/02-workpaper-cycles/workpaper-deep-optimization/requirements.md) | 119/120 | 需求文档：底稿深度优化（v2.0 整合版） |
| 📦已归档 | [`workpaper-e1-cash-optimization`](_archive/02-workpaper-cycles/workpaper-e1-cash-optimization/requirements.md) | 91/91 | 货币资金 E1 底稿优化 - 需求文档 |
| 📦已归档 | [`workpaper-editor-refactor`](_archive/02-workpaper-cycles/workpaper-editor-refactor/requirements.md) | 33/37 | Workpaper Editor 拆分重构 — Requirements |
| 📦已归档 | [`workpaper-editor-shrink-phase2`](_archive/07-workpaper-slimdown/workpaper-editor-shrink-phase2/requirements.md) | 36/36 | Requirements Document — workpaper-editor-shrink-phase2 |
| 📦已归档 | [`workpaper-editor-slimdown`](_archive/07-workpaper-slimdown/workpaper-editor-slimdown/requirements.md) | 121/121 | 底稿编辑器瘦身与跨模块联动 — 需求文档 |
| 📦已归档 | [`workpaper-f-purchase-inventory`](_archive/02-workpaper-cycles/workpaper-f-purchase-inventory/requirements.md) | 58/58 | F 采购存货循环底稿优化 — Requirements |
| 📦已归档 | [`workpaper-foundation-kit`](_archive/07-workpaper-slimdown/workpaper-foundation-kit/requirements.md) | 27/27 | Requirements: 底稿基础设施套件（A循环改造地基） |
| 📦已归档 | [`workpaper-frontend-large-component-split`](_archive/07-workpaper-slimdown/workpaper-frontend-large-component-split/requirements.md) | 29/29 | 需求文档：底稿前端大组件拆分（P1，Top 3） |
| 📦已归档 | [`workpaper-g-investment-cycle`](_archive/02-workpaper-cycles/workpaper-g-investment-cycle/requirements.md) | 55/55 | G 投资循环底稿优化 — Requirements |
| 📦已归档 | [`workpaper-guardrail-cleanup`](_archive/05-business-features/workpaper-guardrail-cleanup/design.md) ⧉platform | 22/22 | 设计文档：底稿模块防退化卡点治理 |
| 📦已归档 | [`workpaper-guidance-content-closure`](_archive/17-2026-10-03-verified-batch/workpaper-guidance-content-closure/requirements.md) | 19/23 | Requirements Document |
| 📦已归档 | [`workpaper-h-fixed-assets-cycle`](_archive/02-workpaper-cycles/workpaper-h-fixed-assets-cycle/requirements.md) ⧉platform | 59/59 | H 固定资产循环底稿优化 — Requirements |
| 📦已归档 | [`workpaper-header-and-metadata`](_archive/07-workpaper-slimdown/workpaper-header-and-metadata/requirements.md) | 24/24 | Requirements: 底稿表头自动填充与业务分类裁剪 |
| 📦已归档 | [`workpaper-html-onlyoffice-bidirectional-writeback-closure`](_archive/17-2026-10-03-verified-batch/workpaper-html-onlyoffice-bidirectional-writeback-closure/requirements.md) ⧉cycle | 66/72 | Requirements Document |
| 📦已归档 | [`workpaper-html-renderer`](_archive/07-workpaper-slimdown/workpaper-html-renderer/requirements.md) | 73/75 | 底稿 HTML 渲染器（通用组件） — 需求汇总 |
| 📦已归档 | [`workpaper-i-intangible-assets-cycle`](_archive/02-workpaper-cycles/workpaper-i-intangible-assets-cycle/requirements.md) ⧉platform | 62/62 | I 无形资产循环底稿优化 — Requirements |
| 📦已归档 | [`workpaper-import-export-lifecycle-closure`](_archive/05-business-features/workpaper-import-export-lifecycle-closure/requirements.md) | 25/25 | Requirements Document |
| 📦已归档 | [`workpaper-j-payroll-cycle`](_archive/02-workpaper-cycles/workpaper-j-payroll-cycle/requirements.md) | 38/38 | J 职工薪酬循环底稿优化 — Requirements |
| 📦已归档 | [`workpaper-k-admin-cycle`](_archive/02-workpaper-cycles/workpaper-k-admin-cycle/requirements.md) | 38/38 | K 管理循环底稿优化 — Requirements |
| 📦已归档 | [`workpaper-l-debt-cycle`](_archive/02-workpaper-cycles/workpaper-l-debt-cycle/requirements.md) | 39/39 | L 筹资循环底稿优化 — Requirements |
| 📦已归档 | [`workpaper-list-shrink`](_archive/07-workpaper-slimdown/workpaper-list-shrink/requirements.md) | 30/41 | Requirements Document — workpaper-list-shrink |
| 📦已归档 | [`workpaper-m-equity-cycle`](_archive/02-workpaper-cycles/workpaper-m-equity-cycle/requirements.md) | 28/28 | M 权益循环底稿优化 — Requirements |
| 📦已归档 | [`workpaper-maintainability-convergence`](_archive/06-engineering-governance/workpaper-maintainability-convergence/requirements.md) | 37/37 | Requirements Document |
| 📦已归档 | [`workpaper-maintainability-convergence-followup`](_archive/06-engineering-governance/workpaper-maintainability-convergence-followup/requirements.md) | 36/36 | Requirements Document |
| 📦已归档 | [`workpaper-misstatement-auto`](_archive/07-workpaper-slimdown/workpaper-misstatement-auto/requirements.md) | 22/22 | Requirements: A13 错报自动生成与跨模块溯源 |
| 📦已归档 | [`workpaper-module-health-pass2`](_archive/07-workpaper-slimdown/workpaper-module-health-pass2/requirements.md) | 32/38 | 底稿模块健康度二期 — 需求文档 |
| 📦已归档 | [`workpaper-module-large-file-split`](_archive/07-workpaper-slimdown/workpaper-module-large-file-split/requirements.md) | 28/28 | 需求文档：底稿模块大文件拆分（P0 / pass3） |
| 📦已归档 | [`workpaper-module-large-file-split-pass4`](_archive/07-workpaper-slimdown/workpaper-module-large-file-split-pass4/requirements.md) | 24/24 | 需求文档：底稿模块大文件拆分 pass4（P1） |
| 📦已归档 | [`workpaper-n-tax-cycle`](_archive/02-workpaper-cycles/workpaper-n-tax-cycle/requirements.md) | 27/27 | N 税金循环底稿优化 — Requirements |
| 📦已归档 | [`workpaper-page-formula-toolbar-closure`](_archive/05-business-features/workpaper-page-formula-toolbar-closure/requirements.md) | 17/17 | Requirements Document |
| 📦已归档 | [`workpaper-procedure-table-html`](_archive/07-workpaper-slimdown/workpaper-procedure-table-html/requirements.md) ⧉cycle | 27/27 | Requirements: A循环程序表 HTML 化 |
| 📦已归档 | [`workpaper-render-config-refactor`](_archive/07-workpaper-slimdown/workpaper-render-config-refactor/requirements.md) | 26/26 | 底稿渲染配置重构 |
| 📦已归档 | [`workpaper-report-analysis`](_archive/07-workpaper-slimdown/workpaper-report-analysis/requirements.md) | 30/30 | Requirements: 报表模块完善（TB完整视图/比率分析/趋势分析/期初核对） |
| 📦已归档 | [`workpaper-review-workflow`](_archive/07-workpaper-slimdown/workpaper-review-workflow/requirements.md) | 29/29 | Requirements: 复核流程 HTML 化与签署工作流 |
| 📦已归档 | [`workpaper-save-orchestrator`](_archive/12-2026-06-23-batch/workpaper-save-orchestrator/requirements.md) | 12/12 | Requirements Document |
| 📦已归档 | [`workpaper-silent-exception-cleanup`](_archive/07-workpaper-slimdown/workpaper-silent-exception-cleanup/requirements.md) | 24/24 | 需求文档：底稿模块静默吞异常治理（P1） |
| 📦已归档 | [`workpaper-sync-adopt-overwrite-and-refresh-source`](_archive/25-2026-10-06-playwright-verified/workpaper-sync-adopt-overwrite-and-refresh-source/requirements.md) ⧉cycle | 58/58 | Requirements Document |
| 📦已归档 | [`workpaper-sync-managed-row-convergence`](_archive/30-workpaper-sync-managed-row-convergence/workpaper-sync-managed-row-convergence/requirements.md) ⧉cycle | 16/33 | Requirements — 受管行双向收敛（刷新取数来源可选 + materialize 行收敛） |
| 📦已归档 | [`workpaper-sync-materialize-large-table-performance`](_archive/15-workpaper-sync-engine-hardening/workpaper-sync-materialize-large-table-performance/requirements.md) ⧉cycle | 12/12 | Requirements Document |
| 📦已归档 | [`workpaper-sync-registration-isolation-and-d2-republish`](_archive/15-workpaper-sync-engine-hardening/workpaper-sync-registration-isolation-and-d2-republish/requirements.md) ⧉cycle | 14/15 | Requirements — workpaper-sync 注册隔离 + 通用对齐守卫 + D2 sibling 发布 |
| 📦已归档 | [`workpaper-sync-row-deletion-multi-region-propagation`](_archive/17-2026-10-03-verified-batch/workpaper-sync-row-deletion-multi-region-propagation/requirements.md) ⧉cycle | 74/74 | Requirements Document |
| 📦已归档 | [`workpaper-sync-static-cell-sheet-writeback`](_archive/15-workpaper-sync-engine-hardening/workpaper-sync-static-cell-sheet-writeback/requirements.md) ⧉cycle | 12/12 | Requirements Document |
| 📦已归档 | [`workpaper-unified-import-export`](_archive/05-business-features/workpaper-unified-import-export/requirements.md) | 85/85 | Requirements Document |
| 📦已归档 | [`workpaper-version-trail`](_archive/05-business-features/workpaper-version-trail/requirements.md) | 53/53 | Requirements Document |
| 📦已归档 | [`wp-ai-review-ux-fix`](_archive/05-business-features/wp-ai-review-ux-fix/design.md) ⧉cycle | 8/8 | 设计文档：wp-ai-review-ux-fix（底稿 AI 复核弹窗 UX 缺陷修复） |
| 📦已归档 | [`wp-evidence-collection`](_archive/05-business-features/wp-evidence-collection/requirements.md) ⧉cycle | 19/19 | 需求文档：审计证据收集体系（wp-evidence-collection） |
| 📦已归档 | [`wp-frontend-ux-polish`](_archive/05-business-features/wp-frontend-ux-polish/requirements.md) ⧉cycle | 30/32 | 需求文档：底稿前端体验优化 |
| 📦已归档 | [`wp-functional-actions`](_archive/05-business-features/wp-functional-actions/requirements.md) ⧉cycle | 33/33 | 需求文档：底稿功能行为联动（wp-functional-actions） |
| 📦已归档 | [`wp-generation-pipeline`](_archive/05-business-features/wp-generation-pipeline/requirements.md) ⧉cycle | 37/37 | 需求文档 |
| 📦已归档 | [`wp-locate-foundation`](_archive/05-business-features/wp-locate-foundation/requirements.md) ⧉cycle | 22/27 | 需求文档：底稿定位基础设施 |
| 📦已归档 | [`wp-performance-virtualization`](_archive/05-business-features/wp-performance-virtualization/requirements.md) ⧉cycle | 8/9 | 需求文档：底稿性能与虚拟滚动 |
| 📦已归档 | [`wp-traceability-panel`](_archive/05-business-features/wp-traceability-panel/requirements.md) | 24/24 | 需求文档：统一溯源面板 + 附件入网 |
| 📦已归档 | [`x3-adjustment-entry-import-export`](_archive/05-business-features/x3-adjustment-entry-import-export/requirements.md) | 63/63 | Requirements Document |

[↑ 返回概览](#top)

<a id="domain-voucher"></a>
## 凭证 / 序时账 / 抽样审计（26 个）

| 状态 | Spec | 进度 | 需求标题 |
| --- | --- | --- | --- |
| 📦已归档 | [`110-voucher-identity-writeback-and-audit-phase`](_archive/110-voucher-identity-writeback-and-audit-phase/requirements.md) ⧉writeback+cycle | 18/18 | 需求文档：凭证身份、底稿回写与预审/年审阶段（voucher-identity-writeback-and-audit-phase） |
| 📦已归档 | [`111-ledger-incremental-append-true-merge`](_archive/111-ledger-incremental-append-true-merge/requirements.md) ⧉cycle | 6/6 | 需求文档：序时账增量追加改为真追加（ledger-incremental-append-true-merge） |
| 📦已归档 | [`135-attachment-voucher-evidence-binding`](_archive/135-attachment-voucher-evidence-binding/requirements.md) ⧉attachment+cycle | 12/12 | 需求：抽凭证据绑定（attachment-voucher-evidence-binding） |
| 📦已归档 | [`149-voucher-workflow-linkage-lineage-closure`](_archive/149-voucher-workflow-linkage-lineage-closure/requirements.md) ⧉cycle | 22/22 | 凭证模块联动、流程与溯源收口 — 需求 |
| 📦已归档 | [`170-d2-voucher-check-import-export-endpoints`](_archive/170-d2-voucher-check-import-export-endpoints/requirements.md) ⧉writeback | 6/6 | D2-7 凭证检查表导入导出端点 — 需求 |
| 📦已归档 | [`173-voucher-runtime-integrity-and-visibility-closure`](_archive/173-voucher-runtime-integrity-and-visibility-closure/requirements.md) | 17/17 | 凭证运行完整性与可见性收口 (voucher-runtime-integrity-and-visibility-closure) |
| 📦已归档 | [`46-voucher-attach-account-mapping-closure`](_archive/46-voucher-attach-account-mapping-closure/requirements.md) ⧉cycle | 23/23 | voucher-attach-account-mapping-closure — 需求文档 |
| 📦已归档 | [`47-multi-window-ledger-workbench`](_archive/47-multi-window-ledger-workbench/requirements.md) ⧉cycle+platform | 24/24 | 多窗口查账工作台 — 需求 |
| 📦已归档 | [`56-voucher-sampling-reconcile-balance-source`](_archive/56-voucher-sampling-reconcile-balance-source/requirements.md) ⧉cycle | 11/12 | 抽凭总体完整性核对接入科目余额表 + 预览内就地放行 — 需求 |
| 📦已归档 | [`balance-import-annual-column-semantics`](_archive/05-business-features/balance-import-annual-column-semantics/requirements.md) | 21/22 | Requirements Document |
| 📦已归档 | [`cutoff-test-auto-sampling`](_archive/05-business-features/cutoff-test-auto-sampling/requirements.md) ⧉cycle+platform | 45/45 | Requirements Document: 通用截止测试自动提取组件 |
| 📦已归档 | [`d2-7-voucher-check-enhancement`](_archive/05-business-features/d2-7-voucher-check-enhancement/requirements.md) ⧉cycle | 31/31 | Requirements Document |
| 📦已归档 | [`f2-detail-ledger-pull`](_archive/05-business-features/f2-detail-ledger-pull/requirements.md) ⧉cycle | 11/11 | Requirements Document |
| 📦已归档 | [`ledger-balance-diagnostics-report-line-coverage`](_archive/05-business-features/ledger-balance-diagnostics-report-line-coverage/requirements.md) ⧉cycle | 74/74 | 需求文档：借贷不平衡诊断与报表行次覆盖治理 |
| 📦已归档 | [`ledger-import-header-adapter-contract`](_archive/05-business-features/ledger-import-header-adapter-contract/requirements.md) ⧉cycle | 57/57 | 需求文档：账表导入表头识别与适配器契约 |
| 📦已归档 | [`ledger-import-sign-convention-migration`](_archive/05-business-features/ledger-import-sign-convention-migration/requirements.md) ⧉cycle+platform | 64/64 | 需求文档：账表导入符号约定与历史迁移 |
| 📦已归档 | [`ledger-import-unification`](_archive/99-superseded/ledger-import-unification/requirements.md) ⧉cycle+platform | 86/138 | 账表导入统一方案 — 需求文档 |
| 📦已归档 | [`ledger-import-view-refactor`](_archive/05-business-features/ledger-import-view-refactor/requirements.md) ⧉cycle | 243/243 | Requirements — Ledger Import 四表上传解析入库整体重构 |
| 📦已归档 | [`ledger-raw-extra-column-display`](_archive/05-business-features/ledger-raw-extra-column-display/requirements.md) ⧉cycle+platform | 24/24 | Requirements Document |
| 📦已归档 | [`ledger-sign-convention-unify`](_archive/05-business-features/ledger-sign-convention-unify/requirements.md) ⧉cycle | 39/39 | 账表符号约定统一 — 需求文档 |
| 📦已归档 | [`sampling-compliance-closure`](_archive/05-business-features/sampling-compliance-closure/requirements.md) ⧉cycle | 25/25 | Requirements Document |
| 📦已归档 | [`sampling-evaluation-and-governance-closure`](_archive/05-business-features/sampling-evaluation-and-governance-closure/requirements.md) ⧉cycle+platform | 19/19 | Requirements Document |
| 📦已归档 | [`voucher-check-sampling-integration`](_archive/05-business-features/voucher-check-sampling-integration/requirements.md) ⧉cycle | 14/14 | Requirements Document |
| 📦已归档 | [`voucher-sampling-account-scope-and-attach-closure`](_archive/05-business-features/voucher-sampling-account-scope-and-attach-closure/requirements.md) ⧉cycle | 59/61 | Requirements — 抽凭科目真源接线与挂凭链路收口 |
| 📦已归档 | [`voucher-sampling-engine`](_archive/05-business-features/voucher-sampling-engine/requirements.md) ⧉cycle | 48/48 | Requirements Document: 通用抽凭引擎组件 |
| 📦已归档 | [`voucher-sampling-hardening`](_archive/05-business-features/voucher-sampling-hardening/requirements.md) ⧉cycle | 40/41 | Requirements Document |

[↑ 返回概览](#top)

<a id="domain-attachment"></a>
## 附件 / 证据 / 归档与交付件（26 个）

| 状态 | Spec | 进度 | 需求标题 |
| --- | --- | --- | --- |
| 📦已归档 | [`105-attachment-evidence-intake`](_archive/105-attachment-evidence-intake/requirements.md) | 12/12 | 需求文档：证据采集单一入口（attachment-evidence-intake） |
| 📦已归档 | [`106-attachment-inline-preview`](_archive/106-attachment-inline-preview/requirements.md) | 11/11 | 需求：底稿附件就地预览与易用性（attachment-inline-preview） |
| 📦已归档 | [`107-attachment-confirmation-evidence-loop`](_archive/107-attachment-confirmation-evidence-loop/requirements.md) ⧉cycle | 12/12 | 需求：函证证据闭环（attachment-confirmation-evidence-loop） |
| 📦已归档 | [`108-attachment-archive-and-a-class-evidence`](_archive/108-attachment-archive-and-a-class-evidence/requirements.md) | 17/17 | 需求：归档与 A 类证据（attachment-archive-and-a-class-evidence） |
| 📦已归档 | [`134-attachment-contract-identity-and-domain-closure`](_archive/134-attachment-contract-identity-and-domain-closure/requirements.md) ⧉cycle | 25/25 | Spec F — attachment-contract-identity-and-domain-closure 需求 |
| 📦已归档 | [`135-attachment-voucher-evidence-binding`](_archive/135-attachment-voucher-evidence-binding/requirements.md) ⧉attachment+cycle | 12/12 | 需求：抽凭证据绑定（attachment-voucher-evidence-binding） |
| 📦已归档 | [`167-attachment-platform-cross-module-closure`](_archive/167-attachment-platform-cross-module-closure/requirements.md) | 31/31 | 需求：附件平台跨模块闭环 |
| 📦已归档 | [`29-chain-closure-phase4-deliverable-center-trio`](_archive/29-chain-closure-phase4-deliverable-center-trio/requirements.md) | 18/18 | 需求：全链条闭环 · 阶段四（交付中心三件套一键出具） |
| 📦已归档 | [`51-deliverable-trio-generation-accuracy`](_archive/51-deliverable-trio-generation-accuracy/requirements.md) | 32/32 | 交付中心三件套生成准确性（审计报告正文 / 财务报表 / 附注） |
| 📦已归档 | [`87-attachment-security-baseline`](_archive/87-attachment-security-baseline/requirements.md) | 12/12 | 需求文档：附件安全底线（attachment-security-baseline） |
| 📦已归档 | [`adjudication-export-template`](_archive/05-business-features/adjudication-export-template/requirements.md) ⧉attachment | 37/37 | Requirements Document |
| 📦已归档 | [`attachment-ocr-ai-evidence-governance-hardening`](_archive/06-engineering-governance/attachment-ocr-ai-evidence-governance-hardening/requirements.md) ⧉attachment+platform | 64/65 | Requirements Document |
| 📦已归档 | [`attachment-workpaper-linkage-convergence`](_archive/05-business-features/attachment-workpaper-linkage-convergence/requirements.md) | 23/23 | Requirements Document |
| 📦已归档 | [`audit-evidence-attachment-preview-format-expansion`](_archive/05-business-features/audit-evidence-attachment-preview-format-expansion/requirements.md) ⧉cycle | 20/20 | Requirements Document |
| 📦已归档 | [`audit-report-deliverable-center`](_archive/05-business-features/audit-report-deliverable-center/requirements.md) | 127/127 | 需求文档：审计报告交付件管理中心 |
| 📦已归档 | [`audit-report-template-integration`](_archive/05-business-features/audit-report-template-integration/requirements.md) | 187/190 | 需求文档：审计报告模板正文集成 |
| 📦已归档 | [`confirmation-attachment-ocr-linkage`](_archive/05-business-features/confirmation-attachment-ocr-linkage/requirements.md) ⧉attachment+cycle | 28/28 | Requirements Document |
| 📦已归档 | [`deliverable-lineage-and-writeback`](_archive/05-business-features/deliverable-lineage-and-writeback/requirements.md) ⧉writeback | 92/92 | 需求文档：出品物溯源与回填（deliverable-lineage-and-writeback） |
| 📦已归档 | [`deliverable-lineage-content-control`](_archive/05-business-features/deliverable-lineage-content-control/requirements.md) | 8/9 | Requirements Document |
| 📦已归档 | [`deliverable-lineage-wiring-and-writeback-closure`](_archive/05-business-features/deliverable-lineage-wiring-and-writeback-closure/requirements.md) ⧉writeback | 40/40 | Requirements Document |
| 📦已归档 | [`deliverable-writeback-and-online-edit-integrity`](_archive/55-batch-2026-10-21/deliverable-writeback-and-online-edit-integrity/requirements.md) ⧉writeback | 29/29 | 交付件回填 / 在线编辑保存 / 签发清单完整性 |
| 📦已归档 | [`j1-post-publish-semantic-and-evidence-closure`](_archive/17-2026-10-03-verified-batch/j1-post-publish-semantic-and-evidence-closure/requirements.md) ⧉cycle | 9/9 | J1 发布后语义与证据闭环 — 需求 |
| 📦已归档 | [`phase13-word-export`](_archive/01-phase-foundation/phase13-word-export/requirements.md) | 119/119 | Phase 13: 审计报告·报表·附注生成与导出 - 需求文档 |
| 📦已归档 | [`phase16-evidence-package-and-versionline`](_archive/01-phase-foundation/phase16-evidence-package-and-versionline/requirements.md) | 126/126 | Phase 16: 取证包与版本链闭环 - 需求文档 |
| 📦已归档 | [`platform-evidence-knowledge-ai-governance`](_archive/04-infra-architecture/platform-evidence-knowledge-ai-governance/requirements.md) ⧉attachment+platform | 101/101 | 需求文档：附件证据、知识库与 AI 治理闭环 |
| 📦已归档 | [`wp-evidence-collection`](_archive/05-business-features/wp-evidence-collection/requirements.md) ⧉cycle | 19/19 | 需求文档：审计证据收集体系（wp-evidence-collection） |

[↑ 返回概览](#top)

<a id="domain-ai"></a>
## 知识库 / AI / LLM / OCR（23 个）

| 状态 | Spec | 进度 | 需求标题 |
| --- | --- | --- | --- |
| 📦已归档 | [`113-ai-content-pending-target-label`](_archive/113-ai-content-pending-target-label/requirements.md) | 5/5 | 需求：AI 待确认列表的目标标签修复（ai-content-pending-target-label） |
| 📦已归档 | [`152-enterprise-embedding-rerank-closure`](_archive/152-enterprise-embedding-rerank-closure/requirements.md) | 20/20 | 企业向量 / 重排模型接入与知识库向量检索修通 — 需求 |
| 📦已归档 | [`172-llm-linkage-audit-practice-closure`](_archive/172-llm-linkage-audit-practice-closure/requirements.md) | 17/17 | 需求文档：LLM 联动与审计实务闭环 |
| 📦已归档 | [`177-chat-host-draft-overlay`](_archive/177-chat-host-draft-overlay/requirements.md) | 8/8 | 需求文档：Chat 宿主通用未保存草稿纳入（draft overlay） |
| 📦已归档 | [`21-knowledge-base-retrieval-and-authz-closure`](_archive/21-knowledge-base-retrieval-and-authz-closure/requirements.md) ⧉procedure | 58/58 | 知识库检索与授权收口（方案 A：文档正文词法检索）— 需求 |
| 📦已归档 | [`53-dsh-kb-ocr-local-first-routing`](_archive/53-dsh-kb-ocr-local-first-routing/requirements.md) | 12/12 | 需求：DSH 子进程与知识库扫描件 OCR 接入本机优先路由 |
| 📦已归档 | [`ai-chat-adopt-and-note-target-picker`](_archive/55-batch-2026-10-21/ai-chat-adopt-and-note-target-picker/requirements.md) ⧉note | 15/16 | 需求：AI 面板「采纳」「转存笔记」选择目标位置与文件 |
| 📦已归档 | [`attachment-ocr-ai-evidence-governance-hardening`](_archive/06-engineering-governance/attachment-ocr-ai-evidence-governance-hardening/requirements.md) ⧉attachment+platform | 64/65 | Requirements Document |
| 📦已归档 | [`confirmation-attachment-ocr-linkage`](_archive/05-business-features/confirmation-attachment-ocr-linkage/requirements.md) ⧉attachment+cycle | 28/28 | Requirements Document |
| 📦已归档 | [`disclosure-note-knowledge-ai-enrichment`](_archive/08-disclosure-notes/disclosure-note-knowledge-ai-enrichment/requirements.md) ⧉note | 10/11 | Requirements Document |
| 📦已归档 | [`doc-level-ai-chat`](_archive/04-infra-architecture/doc-level-ai-chat/requirements.md) | 12/12 | 需求文档：doc-level-ai-chat（文档/文件夹级 LLM 知识库对话） |
| 📦已归档 | [`dsh-agent-panel-integration`](_archive/04-infra-architecture/dsh-agent-panel-integration/requirements.md) | 35/35 | Requirements Document |
| 📦已归档 | [`knowledge-base-unification`](_archive/04-infra/knowledge-base-unification/requirements.md) ⧉platform | 67/67 | Requirements Document |
| 📦已归档 | [`knowledge-upload-robustness-and-consumer-wiring`](_archive/17-2026-10-03-verified-batch/knowledge-upload-robustness-and-consumer-wiring/requirements.md) | 27/27 | 知识库上传健壮性与下游消费方接线 — 需求 |
| 📦已归档 | [`llm-external-provider-runtime-closure`](_archive/55-batch-2026-10-21/llm-external-provider-runtime-closure/requirements.md) | 33/33 | 外部 LLM 提供商运行时闭环 — Requirements |
| 📦已归档 | [`llm-ocr-local-first-routing`](_archive/55-batch-2026-10-21/llm-ocr-local-first-routing/requirements.md) | 14/14 | LLM / OCR 本机优先路由收口 — Requirements |
| 📦已归档 | [`llm-structured-output`](_archive/04-infra-architecture/llm-structured-output/requirements.md) | 13/16 | Requirements: 本地 LLM 结构化输出（Instructor + vLLM guided decoding） |
| 📦已归档 | [`platform-evidence-knowledge-ai-governance`](_archive/04-infra-architecture/platform-evidence-knowledge-ai-governance/requirements.md) ⧉attachment+platform | 101/101 | 需求文档：附件证据、知识库与 AI 治理闭环 |
| 📦已归档 | [`retrieval-kernel-unification`](_archive/04-infra-architecture/retrieval-kernel-unification/requirements.md) ⧉platform | 12/12 | 需求文档：retrieval-kernel-unification（检索/知识层统一架构） |
| 📦已归档 | [`vllm-httpx-bugfix`](_archive/04-infra-architecture/vllm-httpx-bugfix/design.md) | 21/21 | 设计文档：vLLM / httpx 链路 3 bug 修复 |
| 📦已归档 | [`workpaper-ai-conclusion-copilot`](_archive/05-business-features/workpaper-ai-conclusion-copilot/requirements.md) ⧉cycle | 58/58 | 需求文档：底稿科目结论 AI 副驾驶 |
| 📦已归档 | [`wp-ai-review-ux-fix`](_archive/05-business-features/wp-ai-review-ux-fix/design.md) ⧉cycle | 8/8 | 设计文档：wp-ai-review-ux-fix（底稿 AI 复核弹窗 UX 缺陷修复） |
| 📦已归档 | [`wp-tsj-llm-review`](_archive/05-business-features/wp-tsj-llm-review/requirements.md) | 22/22 | 需求文档：TSJ 提示词驱动 LLM 复核（wp-tsj-llm-review） |

[↑ 返回概览](#top)

<a id="domain-acnr"></a>
## ACNR 地址坐标名称库 / 交叉引用（11 个）

| 状态 | Spec | 进度 | 需求标题 |
| --- | --- | --- | --- |
| 📦已归档 | [`102-wp-deeplink-cell-locate-closure`](_archive/102-wp-deeplink-cell-locate-closure/requirements.md) | 6/6 | 需求文档：底稿深链单元格定位收口（wp-deeplink-cell-locate-closure） |
| 📦已归档 | [`136-wp-deeplink-locate-coverage-closure`](_archive/136-wp-deeplink-locate-coverage-closure/requirements.md) | 7/7 | 需求：底稿深链定位覆盖收口（wp-deeplink-locate-coverage-closure） |
| 📦已归档 | [`137-wp-deeplink-locate-residual-closure`](_archive/137-wp-deeplink-locate-residual-closure/requirements.md) | 7/7 | 需求：底稿深链定位残项收口（wp-deeplink-locate-residual-closure） |
| 📦已归档 | [`153-acnr-foundation-defect-closure`](_archive/153-acnr-foundation-defect-closure/requirements.md) | 33/33 | 需求文档：ACNR 地址坐标名称库底座缺陷收口（acnr-foundation-defect-closure） |
| 📦已归档 | [`acnr`](_archive/04-infra-architecture/acnr/requirements.md) | 76/77 | Requirements Document |
| 📦已归档 | [`acnr-consumer-wiring`](_archive/04-infra-architecture/acnr-consumer-wiring/requirements.md) | 100/100 | Requirements Document |
| 📦已归档 | [`acnr-invalidation-overlay-hardening`](_archive/04-infra-architecture/acnr-invalidation-overlay-hardening/requirements.md) | 37/37 | Requirements Document |
| 📦已归档 | [`acnr-runtime-convergence`](_archive/04-infra-architecture/acnr-runtime-convergence/requirements.md) | 25/25 | Requirements Document |
| 📦已归档 | [`cross-workpaper-dispatch-persistence`](_archive/12-2026-06-23-batch/cross-workpaper-dispatch-persistence/requirements.md) | 34/34 | Requirements Document |
| 📦已归档 | [`h3-cross-workpaper-reconciliation`](_archive/05-business-features/h3-cross-workpaper-reconciliation/requirements.md) ⧉cycle | 9/9 | Requirements Document |
| 📦已归档 | [`wp-locate-foundation`](_archive/05-business-features/wp-locate-foundation/requirements.md) ⧉cycle | 22/27 | 需求文档：底稿定位基础设施 |

[↑ 返回概览](#top)

<a id="domain-procedure"></a>
## 程序裁剪 / 生成 / 委派 / 权限（29 个）

| 状态 | Spec | 进度 | 需求标题 |
| --- | --- | --- | --- |
| 📦已归档 | [`115-batch-project-authorization-and-lock-hardening`](_archive/115-batch-project-authorization-and-lock-hardening/requirements.md) ⧉procedure | 59/59 | 需求：批量建项授权与拓扑锁加固 |
| 📦已归档 | [`121-project-pid-path-authz-coverage`](_archive/121-project-pid-path-authz-coverage/requirements.md) | 6/6 | 需求：路径参数写成 `{pid}` 的项目接口鉴权覆盖 |
| 📦已归档 | [`123-trim-followup-residual-findings-closure`](_archive/123-trim-followup-residual-findings-closure/requirements.md) | 26/26 | 需求：裁剪生成后续优化复盘的范围外问题收口 |
| 📦已归档 | [`124-trim-generation-plan-linkage`](_archive/124-trim-generation-plan-linkage/requirements.md) | 28/28 | 需求：程序裁剪 → 生成底稿联动（生成计划） |
| 📦已归档 | [`163-trim-generation-plan-followup-optimizations`](_archive/163-trim-generation-plan-followup-optimizations/requirements.md) | 52/52 | 需求：程序裁剪 → 生成计划后续优化 |
| 📦已归档 | [`21-knowledge-base-retrieval-and-authz-closure`](_archive/21-knowledge-base-retrieval-and-authz-closure/requirements.md) ⧉procedure | 58/58 | 知识库检索与授权收口（方案 A：文档正文词法检索）— 需求 |
| 📦已归档 | [`64-partner-manager-edit-permission`](_archive/64-partner-manager-edit-permission/requirements.md) ⧉procedure | 110/110 | Requirements Document |
| 📦已归档 | [`76-procedure-trim-generation-delegation-chain`](_archive/76-procedure-trim-generation-delegation-chain/requirements.md) | 23/23 | 需求：程序裁剪 → 底稿生成 → 委派 → 可见性 链条闭环 |
| 📦已归档 | [`81-procedure-chain-followup-closure`](_archive/81-procedure-chain-followup-closure/requirements.md) | 17/17 | 程序链后续收口：用户接口 / 逐行委派 / 四个小问题 / 测试残留（procedure-chain-followup-closure） |
| 📦已归档 | [`86-procedure-chain-hardening-and-java-contracts`](_archive/86-procedure-chain-hardening-and-java-contracts/requirements.md) | 29/29 | 程序链加固与 Java 迁移契约（procedure-chain-hardening-and-java-contracts） |
| 📦已归档 | [`a-review-checklist-rbac`](_archive/12-2026-06-23-batch/a-review-checklist-rbac/requirements.md) ⧉cycle | 31/40 | Requirements Document |
| 📦已归档 | [`authorization-enforcement-baseline`](_archive/12-2026-06-23-batch/authorization-enforcement-baseline/requirements.md) | 15/15 | Requirements Document |
| 📦已归档 | [`custom-query-authorization-hardening`](_archive/12-2026-06-23-batch/custom-query-authorization-hardening/design.md) ⧉global-modules | 13/13 | Custom Query Authorization Hardening — Bugfix Design |
| 📦已归档 | [`phase2-role-experience-boost`](_archive/01-phase-foundation/phase2-role-experience-boost/requirements.md) | 32/32 | Requirements Document — Phase 2 角色体验提升 |
| 📦已归档 | [`platform-context-permission-foundation`](_archive/04-infra-architecture/platform-context-permission-foundation/requirements.md) ⧉platform | 111/111 | 需求文档：平台上下文、年度与权限基础统一 |
| 📦已归档 | [`platform-role-workbench-quality-loop`](_archive/04-infra-architecture/platform-role-workbench-quality-loop/requirements.md) ⧉platform | 111/111 | 需求文档：五类角色作业台与质量闭环 |
| 📦已归档 | [`procedure-applicability-trimming`](_archive/05-business-features/procedure-applicability-trimming/requirements.md) | 21/35 | Requirements Document — 程序适用性裁剪 UI |
| 📦已归档 | [`procedure-delegation-notification`](_archive/05-business-features/procedure-delegation-notification/requirements.md) | 17/17 | Requirements Document |
| 📦已归档 | [`procedure-delegation-visibility-isolation`](_archive/06-engineering-governance/procedure-delegation-visibility-isolation/requirements.md) | 18/18 | Requirements Document |
| 📦已归档 | [`procedure-mainline-convergence`](_archive/04-infra/procedure-mainline-convergence/requirements.md) | 42/42 | 程序裁剪与委派主链收敛 — Requirements |
| 📦已归档 | [`procedure-trim-report-line-account-resolution`](_archive/05-business-features/procedure-trim-report-line-account-resolution/requirements.md) | 16/16 | Requirements Document |
| 📦已归档 | [`procedure-trimming-and-delegation-intelligence`](_archive/05-business-features/procedure-trimming-and-delegation-intelligence/requirements.md) | 26/26 | Requirements Document |
| 📦已归档 | [`project-creation-enhancement`](_archive/05-business-features/project-creation-enhancement/requirements.md) | 33/33 | Requirements Document |
| 📦已归档 | [`role-based-view-switching`](_archive/05-business-features/role-based-view-switching/requirements.md) | 19/22 | Requirements Document — 角色视图切换 (Role-Based View Switching) |
| 📦已归档 | [`visibility-isolation-go-live-hardening`](_archive/06-engineering-governance/visibility-isolation-go-live-hardening/requirements.md) | 8/8 | Requirements Document |
| 📦已归档 | [`work-hours-auto-collect-and-edit`](_archive/05-business-features/work-hours-auto-collect-and-edit/requirements.md) | 18/18 | Requirements Document |
| 📦已归档 | [`workhour-entry-frontend`](_archive/05-business-features/workhour-entry-frontend/requirements.md) | 29/29 | Requirements Document |
| 📦已归档 | [`workhour-table-unification`](_archive/05-business-features/workhour-table-unification/requirements.md) ⧉platform | 39/39 | Requirements Document |
| 📦已归档 | [`workpaper-procedure-table-html`](_archive/07-workpaper-slimdown/workpaper-procedure-table-html/requirements.md) ⧉cycle | 27/27 | Requirements: A循环程序表 HTML 化 |

[↑ 返回概览](#top)

<a id="domain-platform"></a>
## 平台基建 / 性能 / 治理 / 发布（157 个）

| 状态 | Spec | 进度 | 需求标题 |
| --- | --- | --- | --- |
| 📦已归档 | [`109-excel-style-table-editing`](_archive/109-excel-style-table-editing/requirements.md) | 35/35 | 需求：表格按 Excel 方式呈现与编辑 |
| 📦已归档 | [`112-stash-1021-lost-changes-recovery`](_archive/112-stash-1021-lost-changes-recovery/requirements.md) | 8/8 | 需求：10 月 21 日 AI 采纳与笔记恢复 |
| 📦已归档 | [`114-backend-startup-and-request-overhead`](_archive/114-backend-startup-and-request-overhead/requirements.md) | 10/10 | 后端冷启动、热重载与每请求固定开销 — 需求 |
| 📦已归档 | [`118-lan-http-insecure-context-compat`](_archive/118-lan-http-insecure-context-compat/requirements.md) | 7/7 | 内网 HTTP 非安全上下文兼容 — 需求 |
| 📦已归档 | [`120-platform-perf-hotspots`](_archive/120-platform-perf-hotspots/requirements.md) | 13/13 | 平台响应速度热点 — 需求 |
| 📦已归档 | [`122-runtime-performance-and-reload-hardening-followup`](_archive/122-runtime-performance-and-reload-hardening-followup/requirements.md) | 32/32 | 运行时性能与热重载加固后续 — 需求 |
| 📦已归档 | [`125-workpaper-multi-window-lock-gaps`](_archive/125-workpaper-multi-window-lock-gaps/requirements.md) | 14/14 | 底稿多窗口编辑锁两处漏洞收口 — 需求 |
| 📦已归档 | [`140-formula-hub-release-blockers`](_archive/140-formula-hub-release-blockers/requirements.md) ⧉cycle+platform | 14/14 | 需求：公式管理阻断缺陷收口（formula-hub-release-blockers） |
| 📦已归档 | [`145-formula-e2e-ci-gate`](_archive/145-formula-e2e-ci-gate/requirements.md) ⧉platform | 7/7 | 需求文档：S8　公式 Playwright 规格接入真实运行的 CI |
| 📦已归档 | [`148-formula-grammar-resolver-unification`](_archive/148-formula-grammar-resolver-unification/requirements.md) ⧉platform | 11/11 | 需求文档：S1　公式语法与取数器单一来源 |
| 📦已归档 | [`151-audit-log-chain-integrity`](_archive/151-audit-log-chain-integrity/requirements.md) | 11/11 | 需求文档：S10　审计哈希链加固 |
| 📦已归档 | [`159-display-core-violations-cleanup`](_archive/159-display-core-violations-cleanup/requirements.md) | 5/5 | Requirements Document |
| 📦已归档 | [`160-frontend-prod-build-white-screen-closure`](_archive/160-frontend-prod-build-white-screen-closure/requirements.md) | 7/7 | 需求：生产构建白屏收口 |
| 📦已归档 | [`162-platform-performance-user-experience-closure`](_archive/162-platform-performance-user-experience-closure/requirements.md) | 41/41 | 平台性能与用户体验闭环 — 需求 |
| 📦已归档 | [`164-api-prefix-fix-recovery`](_archive/164-api-prefix-fix-recovery/requirements.md) | 7/7 | 需求：恢复丢失的 /api 前缀修复（residual 任务 26 / 27） |
| 📦已归档 | [`183-m-cycle-key-naming-unification`](_archive/183-m-cycle-key-naming-unification/requirements.md) ⧉platform | 14/14 | Requirements — M 循环键名统一（前端驼峰 ↔ 契约下划线） |
| 📦已归档 | [`186-platform-release-blocker-closure`](_archive/186-platform-release-blocker-closure/requirements.md) | 24/24 | 平台发布阻断项收口 — 需求 |
| 📦已归档 | [`187-platform-performance-residual-findings-closure`](_archive/187-platform-performance-residual-findings-closure/requirements.md) | 40/42 | 平台性能收口的范围外发现 — 需求 |
| 📦已归档 | [`188-platform-heavy-jobs-and-capacity-closure`](_archive/188-platform-heavy-jobs-and-capacity-closure/requirements.md) | 35/36 | 平台重任务、交互性能与容量闭环 — 需求 |
| 📦已归档 | [`38-m2-m3-m4-m7-m10-sheet-map-drift-and-collapse`](_archive/38-m2-m3-m4-m7-m10-sheet-map-drift-and-collapse/requirements.md) | 29/29 | M2 / M3 / M4 / M7 / M10 —— SHEET_MAP 错位与粒度折叠收口 · 需求 |
| 📦已归档 | [`47-multi-window-ledger-workbench`](_archive/47-multi-window-ledger-workbench/requirements.md) ⧉cycle+platform | 24/24 | 多窗口查账工作台 — 需求 |
| 📦已归档 | [`52-m7-m9-service-modules-and-lazy-import-guard`](_archive/52-m7-m9-service-modules-and-lazy-import-guard/requirements.md) | 10/10 | 需求：M7 / M9 缺失 service 补齐 + lazy import 守卫不再跳过缺失模块 |
| 📦已归档 | [`54-preexisting-test-failures-closure`](_archive/54-preexisting-test-failures-closure/requirements.md) | 12/12 | 需求：46 个预存失败用例逐一收口 |
| 📦已归档 | [`67-formula-governance-coverage-closure`](_archive/67-formula-governance-coverage-closure/requirements.md) | 36/36 | 需求文档：公式治理全覆盖收口（formula-governance-coverage-closure） |
| 📦已归档 | [`74-audit-year-calendar-fallback-ratchet`](_archive/74-audit-year-calendar-fallback-ratchet/requirements.md) ⧉cycle | 29/29 | 审计年度兜底取今年 / 写死年度 —— 棘轮与收口（audit-year-calendar-fallback-ratchet） |
| 📦已归档 | [`78-workpaper-sync-save-path-cpu-hotspots`](_archive/78-workpaper-sync-save-path-cpu-hotspots/requirements.md) ⧉platform | 9/9 | 双向回写 CPU 热点与事件循环阻塞 — Requirements |
| 📦已归档 | [`79-post-push-residual-defect-closure`](_archive/79-post-push-residual-defect-closure/requirements.md) | 32/32 | 推送后残留缺陷收口 — 需求 |
| 📦已归档 | [`a10-1-governance-communication`](_archive/13-2026-06-29-batch/a10-1-governance-communication/requirements.md) | 24/24 | Requirements Document |
| 📦已归档 | [`a9-2-deficiency-letter-governance`](_archive/13-2026-06-29-batch/a9-2-deficiency-letter-governance/requirements.md) ⧉platform | 18/18 | Requirements Document |
| 📦已归档 | [`amount-input-migration-and-column-typing`](_archive/06-engineering-governance/amount-input-migration-and-column-typing/requirements.md) | 8/10 | Requirements — 可编辑金额控件迁移与列类型判据 |
| 📦已归档 | [`applicable-standards-runtime-and-sync-guard`](_archive/08-disclosure-notes/applicable-standards-runtime-and-sync-guard/requirements.md) ⧉platform | 26/26 | Requirements Document |
| 📦已归档 | [`attachment-ocr-ai-evidence-governance-hardening`](_archive/06-engineering-governance/attachment-ocr-ai-evidence-governance-hardening/requirements.md) ⧉attachment+platform | 64/65 | Requirements Document |
| 📦已归档 | [`audit-chain-generation`](_archive/05-business-features/audit-chain-generation/requirements.md) | 101/101 | 需求文档：审计全链路一键生成与导出 |
| 📦已归档 | [`audit-sheet-editable`](_archive/07-workpaper-slimdown/audit-sheet-editable/requirements.md) ⧉cycle | 18/18 | Requirements: 审定表可编辑升级 (GtAuditSheet) |
| 📦已归档 | [`b50-risk-assessment`](_archive/13-2026-06-29-batch/b50-risk-assessment/requirements.md) ⧉platform | 41/41 | Requirements Document |
| 📦已归档 | [`c-control-test-component`](_archive/13-2026-06-29-batch/c-control-test-component/requirements.md) | 25/53 | Requirements Document |
| 📦已归档 | [`c-control-test-popup-enhance`](_archive/05-business-features/c-control-test-popup-enhance/requirements.md) | 33/33 | Requirements Document |
| 📦已归档 | [`c-control-test-refresh`](_archive/05-business-features/c-control-test-refresh/requirements.md) | 25/25 | Requirements Document |
| 📦已归档 | [`consol-note-template-header-unification`](_archive/24-consol-note-and-key-isolation/consol-note-template-header-unification/requirements.md) ⧉note+platform | 7/7 | 统一合并附注模板与单体附注模板的表头格式 |
| 📦已归档 | [`cutoff-test-architecture-convergence`](_archive/05-business-features/cutoff-test-architecture-convergence/requirements.md) ⧉platform | 16/17 | Requirements Document |
| 📦已归档 | [`cutoff-test-auto-sampling`](_archive/05-business-features/cutoff-test-auto-sampling/requirements.md) ⧉cycle+platform | 45/45 | Requirements Document: 通用截止测试自动提取组件 |
| 📦已归档 | [`d0-onlyoffice-migration`](_archive/04-infra-architecture/d0-onlyoffice-migration/requirements.md) ⧉cycle+platform | 10/10 | 需求：多 sheet 底稿非核心 Sheet 切换到 OnlyOffice 渲染 |
| 📦已归档 | [`d4-dual-mode-formula-governance`](_archive/14-d4-bidirectional-writeback/d4-dual-mode-formula-governance/requirements.md) ⧉cycle+platform | 16/16 | D4 双模式公式治理与36底稿覆盖总纲 |
| 📦已归档 | [`d6-contract-assets`](_archive/05-business-features/d6-contract-assets/requirements.md) ⧉platform | 85/85 | Requirements Document: D6 合同资产底稿专属HTML精美组件 |
| 📦已归档 | [`dev-tooling-modernization`](_archive/06-engineering-governance/dev-tooling-modernization/requirements.md) | 20/20 | Requirements: 开发工具链现代化（uv / Docling / gitleaks / SQLFluff / DSPy） |
| 📦已归档 | [`display-format-single-source`](_archive/05-business-features/display-format-single-source/requirements.md) | 12/13 | 显示格式化单一真源（金额/时间/百分比）— Requirements |
| 📦已归档 | [`endpoint-fuzz-and-tracing`](_archive/04-infra-architecture/endpoint-fuzz-and-tracing/requirements.md) | 16/17 | Requirements: 端点自动巡检 + 全链路追踪 + 检索降级增强 |
| 📦已归档 | [`environment-hygiene-deps-and-scratch-schemas`](_archive/17-2026-10-03-verified-batch/environment-hygiene-deps-and-scratch-schemas/requirements.md) | 22/22 | 环境卫生：依赖对齐、加密 fail-closed 与泄漏 scratch schema — 需求 |
| 📦已归档 | [`f4-aging-enum-unification`](_archive/05-business-features/f4-aging-enum-unification/requirements.md) ⧉platform | 23/24 | Requirements Document |
| 📦已归档 | [`formula-engine-unification`](_archive/04-infra-architecture/formula-engine-unification/requirements.md) ⧉platform | 20/20 | 需求文档：formula-engine-unification（公式引擎统一架构） |
| 📦已归档 | [`frontend-consistency-m1`](_archive/06-engineering-governance/frontend-consistency-m1/requirements.md) | 36/36 | Requirements Document |
| 📦已归档 | [`frontend-excel-io-single-entry-convergence`](_archive/06-engineering-governance/frontend-excel-io-single-entry-convergence/requirements.md) ⧉writeback | 15/15 | Requirements Document |
| 📦已归档 | [`frontend-sse-connection-consolidation`](_archive/04-infra-architecture/frontend-sse-connection-consolidation/requirements.md) ⧉platform | 24/24 | Requirements Document |
| 📦已归档 | [`frontend-test-network-isolation-and-load-dedup`](_archive/55-batch-2026-10-21/frontend-test-network-isolation-and-load-dedup/requirements.md) | 10/10 | 需求文档：前端单测网络隔离与并发加载合并 |
| 📦已归档 | [`g1-trading-financial-assets`](_archive/05-business-features/g1-trading-financial-assets/requirements.md) ⧉platform | 49/50 | Requirements Document |
| 📦已归档 | [`global-linkage-bus`](_archive/04-infra-architecture/global-linkage-bus/requirements.md) ⧉platform | 52/52 | 全局联动总线（Unified Linkage Bus）— 需求文档 |
| 📦已归档 | [`global-modules-cleanup`](_archive/04-infra-architecture/global-modules-cleanup/design.md) ⧉platform | 10/10 | 设计文档：global-modules-cleanup（全局模块多源澄清 + 死文件清理 + 联动补全） |
| 📦已归档 | [`global-modules-p2-polish`](_archive/04-infra-architecture/global-modules-p2-polish/requirements.md) ⧉platform | 11/11 | 需求文档：global-modules-p2-polish（全局模块 P2/P3 体验与性能增强） |
| 📦已归档 | [`global-platform-enhancement`](_archive/04-infra-architecture/global-platform-enhancement/requirements.md) ⧉platform | 199/206 | 需求文档：审计平台全局化增强 |
| 📦已归档 | [`global-refinement-v3`](_archive/04-infra-architecture/global-refinement-v3/requirements.md) ⧉platform | 143/147 | 全平台 V3 收官增强 — 需求文档 |
| 📦已归档 | [`global-refinement-v5-closure`](_archive/04-infra-architecture/global-refinement-v5-closure/requirements.md) ⧉platform | 53/53 | Requirements Document |
| 📦已归档 | [`grid-sheet-inline-editing`](_archive/11-confirmation-d0-module/grid-sheet-inline-editing/requirements.md) | 45/45 | Requirements Document |
| 📦已归档 | [`gtdform-test-and-shrink`](_archive/07-workpaper-slimdown/gtdform-test-and-shrink/requirements.md) | 29/29 | 需求文档：D 类渲染器补测 + 拆分 |
| 📦已归档 | [`guard-assertion-attribution-refactor`](_archive/06-engineering-governance/guard-assertion-attribution-refactor/requirements.md) | 8/8 | Requirements — 守卫判据归因化改造（全局等值型 → 归因型） |
| 📦已归档 | [`h1-fixed-assets`](_archive/05-business-features/h1-fixed-assets/requirements.md) ⧉platform | 83/83 | Requirements Document: H1 固定资产底稿专属HTML精美组件 |
| 📦已归档 | [`h10-asset-disposal-income`](_archive/05-business-features/h10-asset-disposal-income/requirements.md) ⧉platform | 30/30 | Requirements Document: H10 资产处置损益底稿专属HTML精美组件 |
| 📦已归档 | [`h5-oil-gas-assets`](_archive/05-business-features/h5-oil-gas-assets/requirements.md) ⧉platform | 40/40 | Requirements Document: H5 油气资产底稿专属HTML精美组件 |
| 📦已归档 | [`h6-asset-disposal-clearing`](_archive/05-business-features/h6-asset-disposal-clearing/requirements.md) ⧉platform | 27/27 | Requirements Document: H6 固定资产清理底稿专属HTML精美组件 |
| 📦已归档 | [`h7-biological-assets`](_archive/05-business-features/h7-biological-assets/requirements.md) ⧉platform | 44/44 | Requirements Document: H7 生产性生物资产底稿专属HTML精美组件 |
| 📦已归档 | [`h7-biological-assets-disclosure-rebuild`](_archive/08-disclosure-notes/h7-biological-assets-disclosure-rebuild/requirements.md) ⧉cycle+platform | 12/12 | Requirements Document |
| 📦已归档 | [`h8-right-of-use-assets`](_archive/05-business-features/h8-right-of-use-assets/requirements.md) ⧉platform | 38/38 | Requirements Document: H8 使用权资产底稿专属HTML精美组件 |
| 📦已归档 | [`i1-intangible-assets`](_archive/05-business-features/i1-intangible-assets/requirements.md) ⧉platform | 58/58 | Requirements Document: I1 无形资产、累计摊销及减值准备底稿专属HTML精美组件 |
| 📦已归档 | [`i5-other-noncurrent-assets`](_archive/05-business-features/i5-other-noncurrent-assets/requirements.md) ⧉platform | 32/32 | Requirements Document: I5 其他非流动资产底稿专属HTML精美组件 |
| 📦已归档 | [`k11-asset-impairment-loss`](_archive/05-business-features/k11-asset-impairment-loss/requirements.md) ⧉platform | 29/29 | Requirements Document: K11 资产减值损失底稿专属HTML精美组件 |
| 📦已归档 | [`k2-other-current-assets`](_archive/05-business-features/k2-other-current-assets/requirements.md) ⧉platform | 31/31 | Requirements Document: K2 其他流动资产底稿专属HTML精美组件 |
| 📦已归档 | [`k2-other-current-assets-disclosure-alignment`](_archive/08-disclosure-notes/k2-other-current-assets-disclosure-alignment/requirements.md) ⧉cycle+platform | 27/27 | Requirements Document |
| 📦已归档 | [`knowledge-base-unification`](_archive/04-infra/knowledge-base-unification/requirements.md) ⧉platform | 67/67 | Requirements Document |
| 📦已归档 | [`ledger-import-sign-convention-migration`](_archive/05-business-features/ledger-import-sign-convention-migration/requirements.md) ⧉cycle+platform | 64/64 | 需求文档：账表导入符号约定与历史迁移 |
| 📦已归档 | [`ledger-import-unification`](_archive/99-superseded/ledger-import-unification/requirements.md) ⧉cycle+platform | 86/138 | 账表导入统一方案 — 需求文档 |
| 📦已归档 | [`ledger-raw-extra-column-display`](_archive/05-business-features/ledger-raw-extra-column-display/requirements.md) ⧉cycle+platform | 24/24 | Requirements Document |
| 📦已归档 | [`linkage-panorama-graph`](_archive/99-superseded/linkage-panorama-graph/requirements.md) ⧉platform | 5/27 | Requirements Document — 联动全景图 (Linkage Panorama Graph) |
| 📦已归档 | [`migration-integrity-and-enum-drift-closure`](_archive/17-2026-10-03-verified-batch/migration-integrity-and-enum-drift-closure/requirements.md) | 21/21 | 迁移完整性与枚举漂移收口 — 需求 |
| 📦已归档 | [`migration-runner-resilience`](_archive/06-engineering-governance/migration-runner-resilience/requirements.md) | 0/6 | 需求文档：D6 MigrationRunner 韧性化 |
| 📦已归档 | [`multi-standard-unification`](_archive/05-business-features/multi-standard-unification/requirements.md) ⧉platform | 26/26 | 需求文档：多准则状态统一（multi-standard-unification） |
| 📦已归档 | [`multi-worker-readiness`](_archive/12-2026-06-23-batch/multi-worker-readiness/requirements.md) | 23/23 | Requirements Document |
| 📦已归档 | [`n1-deferred-tax-assets`](_archive/05-business-features/n1-deferred-tax-assets/requirements.md) ⧉platform | 34/34 | Requirements Document: N1 递延所得税资产底稿专属HTML精美组件 |
| 🟢活跃 | [`operation-log-and-last-login`](operation-log-and-last-login/requirements.md) | 8/8 | 操作日志与最后登录时间 — 需求 |
| 📦已归档 | [`partner-dashboard`](_archive/05-business-features/partner-dashboard/requirements.md) | 26/27 | Requirements Document — 合伙人仪表盘 (Partner Dashboard) |
| 📦已归档 | [`pg-pooling-and-load-test`](_archive/04-infra-architecture/pg-pooling-and-load-test/requirements.md) | 11/13 | Requirements: PG 连接池化 + 6000 并发压测（PgBouncer + Locust） |
| 📦已归档 | [`phase0-infrastructure`](_archive/01-phase-foundation/phase0-infrastructure/requirements.md) | 78/78 | 需求文档：第零阶段 — 技术基础设施 |
| 📦已归档 | [`phase1-experience-gap-fix`](_archive/01-phase-foundation/phase1-experience-gap-fix/requirements.md) | 29/29 | Requirements Document — Phase 1 体验断层修复 |
| 📦已归档 | [`phase11-system-hardening`](_archive/01-phase-foundation/phase11-system-hardening/design.md) | 131/131 | Phase 11 系统加固 — 技术设计文档 |
| 📦已归档 | [`phase12-workpaper-deep`](_archive/01-phase-foundation/phase12-workpaper-deep/requirements.md) | 172/172 | Phase 12: 底稿深度开发 - 需求文档 |
| 📦已归档 | [`phase14-gate-engine-governance`](_archive/01-phase-foundation/phase14-gate-engine-governance/requirements.md) | 134/134 | Phase 14: 统一门禁引擎与治理收敛 - 需求文档 |
| 📦已归档 | [`phase15-task-tree-and-event-orchestration`](_archive/01-phase-foundation/phase15-task-tree-and-event-orchestration/requirements.md) | 119/119 | Phase 15: 四级任务树与事件编排补偿 - 需求文档 |
| 📦已归档 | [`phase1a-core`](_archive/01-phase-foundation/phase1a-core/requirements.md) | 137/137 | 需求文档：第一阶段MVP核心 — 数据导入+科目映射+四表联动+试算表+调整分录+重要性水平 |
| 📦已归档 | [`phase1b-workpaper`](_archive/01-phase-foundation/phase1b-workpaper/requirements.md) | 110/110 | 需求文档：第一阶段MVP底稿 — ONLYOFFICE集成+底稿模板引擎+底稿质量自检 |
| 📦已归档 | [`phase1c-report`](_archive/01-phase-foundation/phase1c-report/requirements.md) | 118/118 | 需求文档：第一阶段MVP报表 — 报表生成+现金流量表+附注+PDF导出 |
| 📦已归档 | [`phase3-collaboration`](_archive/01-phase-foundation/phase3-collaboration/requirements.md) | 141/141 | 需求文档：第三阶段协作与质控 — 多用户权限+三级复核+期后事项+版本控制+项目看板+函证管理+审计档案归档 |
| 📦已归档 | [`phase3-system-enhancement`](_archive/01-phase-foundation/phase3-system-enhancement/requirements.md) | 38/40 | Requirements Document — Phase 3 系统性增强 |
| 📦已归档 | [`phase4-ai`](_archive/01-phase-foundation/phase4-ai/requirements.md) | 90/90 | 需求文档：第四阶段AI赋能 — 本地LLM+OCR单据识别+AI辅助底稿+合同分析+证据链验证+知识库对话+函证AI+自然语言操控 |
| 📦已归档 | [`phase4-long-term-governance`](_archive/01-phase-foundation/phase4-long-term-governance/requirements.md) | 33/33 | Requirements Document — Phase 4 长期治理 |
| 📦已归档 | [`phase5-extension`](_archive/01-phase-foundation/phase5-extension/requirements.md) | 214/214 | Phase 8 - 扩展能力与远期规划 需求文档 |
| 📦已归档 | [`phase5-operational-excellence`](_archive/01-phase-foundation/phase5-operational-excellence/requirements.md) | 63/63 | Requirements Document — Phase 5 运营卓越 |
| 📦已归档 | [`phase6-integration`](_archive/01-phase-foundation/phase6-integration/requirements.md) | 356/356 | Phase 9 — 前后端联动集成与功能补全 |
| 📦已归档 | [`phase6-precision-and-security`](_archive/01-phase-foundation/phase6-precision-and-security/requirements.md) | 32/51 | Requirements Document — Phase 6: 数值精度 + 权限统一 + 安全加固 |
| 📦已归档 | [`phase7-enhancement`](_archive/01-phase-foundation/phase7-enhancement/requirements.md) | 209/209 | Phase 10 — 深度增强与协作体验 |
| 📦已归档 | [`phase7-role-experience-closure`](_archive/01-phase-foundation/phase7-role-experience-closure/requirements.md) | 50/75 | Requirements Document — Phase 7: EQCR + QC + 工时体验闭环 |
| 📦已归档 | [`phase8`](_archive/01-phase-foundation/phase8/requirements.md) | 209/209 | Phase 8 — 需求文档 |
| 📦已归档 | [`platform-architecture-convergence`](_archive/06-engineering-governance/platform-architecture-convergence/requirements.md) | 22/22 | Requirements Document |
| 🟢活跃 | [`platform-capacity-acceptance-and-heavy-defect-closure`](platform-capacity-acceptance-and-heavy-defect-closure/requirements.md) | 2/13 | 平台容量验收与重任务残留缺陷收口 — 需求 |
| 📦已归档 | [`platform-context-permission-foundation`](_archive/04-infra-architecture/platform-context-permission-foundation/requirements.md) ⧉platform | 111/111 | 需求文档：平台上下文、年度与权限基础统一 |
| 📦已归档 | [`platform-evidence-knowledge-ai-governance`](_archive/04-infra-architecture/platform-evidence-knowledge-ai-governance/requirements.md) ⧉attachment+platform | 101/101 | 需求文档：附件证据、知识库与 AI 治理闭环 |
| 🟢活跃 | [`platform-global-display-settings-closure`](platform-global-display-settings-closure/requirements.md) | 26/29 | 平台全局显示设置收口：需求 |
| 📦已归档 | [`platform-global-hardening`](_archive/04-infra-architecture/platform-global-hardening/requirements.md) | 79/79 | Requirements Document |
| 📦已归档 | [`platform-linkage-contract-stale`](_archive/04-infra-architecture/platform-linkage-contract-stale/requirements.md) | 104/104 | 需求文档：平台数据联动契约、穿透与 stale 统一 |
| 📦已归档 | [`platform-maintenance-governance`](_archive/04-infra-architecture/platform-maintenance-governance/requirements.md) | 108/108 | 需求文档：平台治理、维护账本与工程卡点 |
| 📦已归档 | [`platform-role-workbench-quality-loop`](_archive/04-infra-architecture/platform-role-workbench-quality-loop/requirements.md) ⧉platform | 111/111 | 需求文档：五类角色作业台与质量闭环 |
| 📦已归档 | [`platform-ui-editing-consistency`](_archive/04-infra-architecture/platform-ui-editing-consistency/requirements.md) | 106/106 | 需求文档：平台 UI、编辑状态与全局组件一致性 |
| 📦已归档 | [`post-enhancement-bugfix`](_archive/99-superseded/post-enhancement-bugfix/requirements.md) | 134/149 | 需求文档：审计平台缺陷修复与业务优化 |
| 📦已归档 | [`production-readiness`](_archive/04-infra-architecture/production-readiness/requirements.md) | 143/144 | 需求文档：生产就绪改进（production-readiness） |
| 📦已归档 | [`proposal-remaining-18`](_archive/05-business-features/proposal-remaining-18/requirements.md) | 30/30 | 全局建议书剩余 27 项 — 需求文档 |
| 📦已归档 | [`pytest-residual-failures-cleanup`](_archive/06-engineering-governance/pytest-residual-failures-cleanup/design.md) | 50/57 | Pytest Residual Failures Cleanup — Bugfix Design |
| 📦已归档 | [`qc-python-rule-load-hardening`](_archive/12-2026-06-23-batch/qc-python-rule-load-hardening/design.md) | 11/11 | QC Python Rule Load Hardening — Bugfix Design |
| 📦已归档 | [`refinement-round1-review-closure`](_archive/03-refinement-rounds/refinement-round1-review-closure/requirements.md) | 33/45 | Refinement Round 1 — 复核闭环与合规文档一体化 |
| 📦已归档 | [`refinement-round2-project-manager`](_archive/03-refinement-rounds/refinement-round2-project-manager/requirements.md) | 24/27 | Refinement Round 2 — 项目经理视角（多项目作战 + 委派催办 + 简报） |
| 📦已归档 | [`refinement-round3-quality-control`](_archive/03-refinement-rounds/refinement-round3-quality-control/requirements.md) | 29/29 | Refinement Round 3 — 质控人员视角（规则覆盖 + 抽查手段 + 质量评级） |
| 📦已归档 | [`refinement-round4-audit-assistant`](_archive/03-refinement-rounds/refinement-round4-audit-assistant/requirements.md) | 26/26 | Refinement Round 4 — 审计助理视角（新人上手 + 单页自洽 + AI 就位） |
| 📦已归档 | [`refinement-round5-independent-review`](_archive/03-refinement-rounds/refinement-round5-independent-review/requirements.md) | 27/27 | Refinement Round 5 — 独立复核（EQCR）视角（独立取证 + 反向检查 + 报告前一锤定音） |
| 📦已归档 | [`refinement-round6-cross-role-optimization`](_archive/03-refinement-rounds/refinement-round6-cross-role-optimization/requirements.md) | 18/18 | Refinement Round 6 — 跨角色系统级优化（门面收敛 + 守门机制 + 死代码清理） |
| 📦已归档 | [`refinement-round9-global-deep-review`](_archive/03-refinement-rounds/refinement-round9-global-deep-review/requirements.md) | 83/91 | R9 全局深度复盘 — 需求文档 |
| 📦已归档 | [`repo-frontend-layout-unification`](_archive/06-engineering-governance/repo-frontend-layout-unification/requirements.md) | — | 需求文档：仓库前端路径二义性消除 |
| 📦已归档 | [`repo-git-workflow-unification`](_archive/06-engineering-governance/repo-git-workflow-unification/requirements.md) | — | 需求文档：仓库 git 工作流统一治理 |
| 📦已归档 | [`report-cache-year-isolation`](_archive/12-2026-06-23-batch/report-cache-year-isolation/design.md) | 11/11 | Report Cache Year Isolation Bugfix Design |
| 📦已归档 | [`report-view-slimdown`](_archive/07-workpaper-slimdown/report-view-slimdown/requirements.md) | 56/56 | Requirements Document |
| 📦已归档 | [`restricted-assets-note-row-scope-rollout`](_archive/08-disclosure-notes/restricted-assets-note-row-scope-rollout/requirements.md) ⧉platform | 16/16 | Requirements Document |
| 📦已归档 | [`retrieval-kernel-unification`](_archive/04-infra-architecture/retrieval-kernel-unification/requirements.md) ⧉platform | 12/12 | 需求文档：retrieval-kernel-unification（检索/知识层统一架构） |
| 📦已归档 | [`sampling-evaluation-and-governance-closure`](_archive/05-business-features/sampling-evaluation-and-governance-closure/requirements.md) ⧉cycle+platform | 19/19 | Requirements Document |
| 📦已归档 | [`schema-drift-full-sync`](_archive/05-business-features/schema-drift-full-sync/design.md) | 3/3 | Design Document — Schema Drift Full Sync |
| 📦已归档 | [`single-source-cleanup`](_archive/12-2026-06-23-batch/single-source-cleanup/requirements.md) | 7/7 | Requirements Document |
| 📦已归档 | [`stale-propagation-cleanup-doc`](_archive/05-business-features/stale-propagation-cleanup-doc/requirements.md) | 6/6 | Stale 传播死代码清理 + 分层文档 — Requirements |
| 📦已归档 | [`startup-prewarm-event-loop-unblocking`](_archive/17-2026-10-03-verified-batch/startup-prewarm-event-loop-unblocking/requirements.md) | 10/10 | 启动预热不阻塞事件循环 — 需求 |
| 📦已归档 | [`table-unification-el-table`](_archive/04-infra-architecture/table-unification-el-table/requirements.md) | 26/26 | 表格统一化 — 全部迁移到 el-table |
| 📦已归档 | [`v3-linkage-stale-propagation`](_archive/04-infra-architecture/v3-linkage-stale-propagation/requirements.md) | 23/23 | Spec A — Linkage Stale Propagation（联动 stale 推广） |
| 📦已归档 | [`v3-r10-editor-resilience`](_archive/04-infra-architecture/v3-r10-editor-resilience/requirements.md) | 48/48 | Spec C (R10) — Editor Resilience · Requirements |
| 📦已归档 | [`v3-r10-linkage-and-tokens`](_archive/04-infra-architecture/v3-r10-linkage-and-tokens/requirements.md) | 68/68 | Spec B (R10) — Linkage & Tokens · Requirements |
| 📦已归档 | [`workhour-table-unification`](_archive/05-business-features/workhour-table-unification/requirements.md) ⧉platform | 39/39 | Requirements Document |
| 📦已归档 | [`workpaper-guardrail-cleanup`](_archive/05-business-features/workpaper-guardrail-cleanup/design.md) ⧉platform | 22/22 | 设计文档：底稿模块防退化卡点治理 |
| 📦已归档 | [`workpaper-h-fixed-assets-cycle`](_archive/02-workpaper-cycles/workpaper-h-fixed-assets-cycle/requirements.md) ⧉platform | 59/59 | H 固定资产循环底稿优化 — Requirements |
| 📦已归档 | [`workpaper-i-intangible-assets-cycle`](_archive/02-workpaper-cycles/workpaper-i-intangible-assets-cycle/requirements.md) ⧉platform | 62/62 | I 无形资产循环底稿优化 — Requirements |
| 📦已归档 | [`wp-frontend-ux-polish`](_archive/05-business-features/wp-frontend-ux-polish/requirements.md) ⧉cycle | 30/32 | 需求文档：底稿前端体验优化 |
| 📦已归档 | [`wp-functional-actions`](_archive/05-business-features/wp-functional-actions/requirements.md) ⧉cycle | 33/33 | 需求文档：底稿功能行为联动（wp-functional-actions） |
| 📦已归档 | [`wp-generation-pipeline`](_archive/05-business-features/wp-generation-pipeline/requirements.md) ⧉cycle | 37/37 | 需求文档 |
| 📦已归档 | [`wp-performance-virtualization`](_archive/05-business-features/wp-performance-virtualization/requirements.md) ⧉cycle | 8/9 | 需求文档：底稿性能与虚拟滚动 |
| 📦已归档 | [`wp-template-migration`](_archive/05-business-features/wp-template-migration/requirements.md) | 19/19 | 需求文档：模板版本升级数据迁移 |
| 📦已归档 | [`xlsx-read-acceleration`](_archive/04-infra-architecture/xlsx-read-acceleration/requirements.md) | 15/15 | Requirements: xlsx 读路径 calamine 加速推广 |
| 📦已归档 | [`zero-downtime-deployment`](_archive/04-infra-architecture/zero-downtime-deployment/requirements.md) | 76/76 | 需求文档：服务器零停机滚动更新与无感版本迭代（zero-downtime-deployment） |

[↑ 返回概览](#top)

<a id="domain-global-modules"></a>
## 高级查询 / 全局 7 横切（18 个）

| 状态 | Spec | 进度 | 需求标题 |
| --- | --- | --- | --- |
| 📦已归档 | [`144-advanced-query-safety-and-consistency-closure`](_archive/144-advanced-query-safety-and-consistency-closure/requirements.md) | 8/8 | 需求文档：高级查询安全与一致性收口 |
| 📦已归档 | [`178-advanced-query-artifact-and-freshness`](_archive/178-advanced-query-artifact-and-freshness/requirements.md) | 11/12 | 需求文档：高级查询查询证据与时效（advanced-query-artifact-and-freshness） |
| 📦已归档 | [`179-advanced-query-linkage-closure`](_archive/179-advanced-query-linkage-closure/requirements.md) | 47/48 | 需求文档：高级查询联动闭环（advanced-query-linkage-closure） |
| 📦已归档 | [`advanced-query-consolidation`](_archive/05-business-features/advanced-query-consolidation/requirements.md) ⧉global-modules | 12/12 | Requirements Document |
| 📦已归档 | [`advanced-query-disclosure-integration-hardening`](_archive/04-infra/advanced-query-disclosure-integration-hardening/requirements.md) ⧉note | 36/36 | Requirements Document |
| 📦已归档 | [`advanced-query-enhancements-p1p2`](_archive/05-business-features/advanced-query-enhancements-p1p2/requirements.md) | 122/124 | Requirements Document — 高级查询模块剩余 P1-P2 增强项 |
| 📦已归档 | [`advanced-query-hardening-wiring-closure`](_archive/05-business-features/advanced-query-hardening-wiring-closure/requirements.md) | 64/83 | Requirements Document |
| 📦已归档 | [`advanced-query-module`](_archive/05-business-features/advanced-query-module/requirements.md) | 85/85 | Requirements Document |
| 📦已归档 | [`custom-query-authorization-hardening`](_archive/12-2026-06-23-batch/custom-query-authorization-hardening/design.md) ⧉global-modules | 13/13 | Custom Query Authorization Hardening — Bugfix Design |
| 📦已归档 | [`global-linkage-bus`](_archive/04-infra-architecture/global-linkage-bus/requirements.md) ⧉platform | 52/52 | 全局联动总线（Unified Linkage Bus）— 需求文档 |
| 📦已归档 | [`global-modules-cleanup`](_archive/04-infra-architecture/global-modules-cleanup/design.md) ⧉platform | 10/10 | 设计文档：global-modules-cleanup（全局模块多源澄清 + 死文件清理 + 联动补全） |
| 📦已归档 | [`global-modules-p2-polish`](_archive/04-infra-architecture/global-modules-p2-polish/requirements.md) ⧉platform | 11/11 | 需求文档：global-modules-p2-polish（全局模块 P2/P3 体验与性能增强） |
| 📦已归档 | [`global-platform-enhancement`](_archive/04-infra-architecture/global-platform-enhancement/requirements.md) ⧉platform | 199/206 | 需求文档：审计平台全局化增强 |
| 📦已归档 | [`global-refinement-v3`](_archive/04-infra-architecture/global-refinement-v3/requirements.md) ⧉platform | 143/147 | 全平台 V3 收官增强 — 需求文档 |
| 📦已归档 | [`global-refinement-v5-closure`](_archive/04-infra-architecture/global-refinement-v5-closure/requirements.md) ⧉platform | 53/53 | Requirements Document |
| 📦已归档 | [`linkage-panorama-graph`](_archive/99-superseded/linkage-panorama-graph/requirements.md) ⧉platform | 5/27 | Requirements Document — 联动全景图 (Linkage Panorama Graph) |
| 📦已归档 | [`template-library-coordination`](_archive/05-business-features/template-library-coordination/requirements.md) | 64/64 | 需求文档：全局模板库管理系统 |
| 📦已归档 | [`template-library-formula-preset-custom`](_archive/05-business-features/template-library-formula-preset-custom/requirements.md) | 16/16 | Requirements Document |

[↑ 返回概览](#top)
