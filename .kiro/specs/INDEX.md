# 致同审计作业平台 — Spec 开发索引

**最后更新**：2026-07-27
**当前分支**：`work/2026-05-30-wp-specs`
**统计**：Active 2 / Archived 457 = 总计 459
**最高迁移**：**V127**（以 `migration_status` 实测为准）
**技术栈**：FastAPI + PostgreSQL + Redis / Vue 3 + Element Plus + Univer

---

## 〇、如何使用本索引

每个 spec 是一个目录，包含三件套文档：

| 文件 | 用途 | 何时读 |
|------|------|--------|
| `requirements.md` | 需求（用户故事 + 验收准则） | "要解决什么问题" |
| `design.md` | 设计（架构、数据模型、接口） | "怎么实现的" |
| `tasks.md` | 任务清单（`[x]`=完成 / `[ ]`=未做 / `[ ]*`=可选） | "做到哪了" |

**定位路径**：
- Active spec：`.kiro/specs/{name}/`
- Archived spec：`.kiro/specs/_archive/{分类}/{name}/`

---

## 一、Active Specs

新建 spec 放 `.kiro/specs/{name}/`。

| Spec | 阶段 | 说明 |
|------|------|------|
| `trial-balance-cross-comparison` | 部分完成（Task 1-4 `[x]`，Task 5 PBT 套件未做 / 6* Playwright 可选留待） | 试算表跨年度/跨项目对比（`useTbComparison` 外连接+差异高亮+导出，复用 GET /trial-balance 无新端点）；待补 PBT 套件（Property 1-7） |
| `confirmation-linkage-completion` | 起步（仅 `.config.kiro`，需求/设计未成） | 并发会话新建，函证联动完成收口方向；待补三件套 |

---

## 二、已归档 Spec（448个，15 分类）

```
_archive/
├── 01-phase-foundation/              24
├── 02-workpaper-cycles/              16
├── 03-refinement-rounds/              9
├── 04-infra/                          2
├── 04-infra-architecture/            36
├── 05-business-features/            223
├── 06-engineering-governance/        13
├── 07-workpaper-slimdown/            22
├── 08-disclosure-notes/              16
├── 09-consolidation-phases/           4
├── 10-A~S-workpaper-all-cycles-complete/ 31
├── 11-confirmation-d0-module/        10
├── 12-2026-06-23-batch/              12
├── 13-2026-06-29-batch/              33
└── 99-superseded/                     4
```

### 最近归档（2026-07-27，本轮 8 个完成 spec 归档）

**→ 08-disclosure-notes（+1）**

| Spec | 说明 |
|------|------|
| disclosure-note-quality-completion | 附注模块质量完成：markdown 残留止血（前端 renderNoteTextToHtml + 生成侧 sanitize_note_narrative + 存量脚本 live 清 216 条）/ stale_source 诚实分级暴露 / linkage 诊断端点 + BS-002 示例 seed / consol V2 落库 SourceTemplate.consolidated AttributeError 修复；test_note_content_utils_sanitize 7 + test_note_readiness_and_stale 16 + test_consol_notes_v2_persist 24 全绿；灰度默认关零回归；已 commit+push `b57d713e` |

**→ 05-business-features（+7）**

| Spec | 说明 |
|------|------|
| confirmation-alternative-structure-alignment | 替代程序结构对齐九套（K0-5/K0-6/L0-5 渲染层拆借贷双表 + L0-5 期初一致性 + G0-6 区块对齐 + F05/F06 拆子组件 + L05 adapter passthrough 修复）；函证域 750 passed；Playwright 留待 |
| confirmation-hub-workbench-tabs | 函证枢纽底稿多 sheet 可达 + 台账双向导航 + E0 重建（B 方案）+ 路由与编码治理（sheet override 编码尾码优先解析）；前端 706+后端契约 35 passed；仅 8.2* Playwright 可选留待 |
| confirmation-shared-model-extension | 四张共享表行模型 additive 补列（ConfirmationRow/EntityVerifyRow/ReliabilityRow/DiffReconcileRow）+ 列配置驱动 + Master 简表回退/FullGrid 宽表分工修正；函证域 668+22 契约 passed；6.3 Playwright 留待 |
| e0-send-list-components | E0-3~E0-6 四张发函前清单审定 E0.yaml + 生成器 `_reviewed` 防覆盖 + 候选去重纯函数；54 passed；Playwright 留待 |
| g0-investment-diff-model | G0 证券差异表补 5 列 + 非证券三维差异专属组件（confirmation-diff-nonsecurities 全链注册）+ migrateAdjust 修复；g0 域 33+confirmation 691+注册 66+后端 29 passed+live round-trip PASS |
| g7-linkage-extraction-completion | G7 长投联动取数（底稿侧合并联动 + G7-2/G7-1 四表跨册取数 + 抽凭铺开 + 过期常驻提示 + G7-4 反向补录 + 主入口白屏 P0 修复）；26/26 全绿；灰度默认关 |
| trial-balance-version-timemachine | 试算表版本时光机（V128 snapshot 表 + TbSnapshotService create/list/restore/diff + SHA-256 dedup + 版本抽屉 + best-effort 快照不阻断 recalc）；8/8 全绿 + Property 1-8 PBT |

### 上一轮归档（2026-07-27，disclosure-note-linkage-completion 完成归档）

**→ 08-disclosure-notes（+1）**

| Spec | 说明 |
|------|------|
| disclosure-note-linkage-completion | 附注模块联动链完成收口：①披露表保存后自动同步到附注（`useDisclosureAutoSync` 单一封装+全循环 24+ tab 铺开）②同步端点 URL 收敛为单一 canonical（H3/H4/H5/J1/D6 迁移+契约守卫）③合并附注 V2 落库激活穿透（`_persist_consol_sections_v2` provenance-only+灰度默认关）④stale_source 历史回填（221 行 report_fallback）⑤公式灰度按项目启用（`note_formula_gray_service`+就绪度看板暴露）；13 属性 P1-P13 全覆盖+live 端到端三流程验证 PASS |

### 最近归档（2026-07-26，13个已完成 spec 归档）

**→ 05-business-features（+11）**

| Spec | 说明 |
|------|------|
| adjustment-import-export-contract | 调整分录导入导出契约收敛（中央 overwrite by-key 幂等+示例行全等+汇总导出补类型列+7张底稿三重对齐 item_id/storage_field/field_keys+K12-3 JSON 迁移+双侧契约守卫；后端 265+前端 52 测试+live round-trip K3-3/中央三段 RESTORED_IDENTICAL）；已 commit `fb7921fc` |
| adjustment-detail-account-code | 调整分录明细行 `detail_account_code` 可空列（V127 迁移+前端 effectiveCode 优先匹配+导入保留明细码+recalc 零影响契约；后端 68+前端 16 测试+HTTP round-trip 100101 落库）；已 commit `fb7921fc` |
| h2-disclosure-linkage-and-prefill | H2 在建工程 P1 增强：披露表→附注结构化推送（buildH2SyncPayload 6/4 子表逐字对齐模板+12 vitest）+ 审定表从集中登记带入调整（1604 已接入+AdjudicationBringInDialog）+ H2-2 明细四表取数自动种子（后端 _build_h2_detail_prefill TB 叶子+Persist_First）+ H4 工程物资跨底稿勾稽（h2H4MaterialPull 纯函数）+ P0 四修（TB 叶子防双算+双模式 config 预拉+useNoteRefresh 1604+L1 JSON 键优先） |
| n1-loss-check-source-alignment | N1-5 按源模板重建（到期年度行+本期数三列+确认/不确认拆分+依据+来源三选+索引）+ 附注五、30/八、31 未确认一节数据源打通（deriveUnrecognizedLossPayload）+ IE 新列对齐 + N1-4/N1-1 跨表带入；7波全绿含 7.3* live round-trip |
| confirmation-attachment-ocr-linkage | 函证台账回函证据链（发函件/回函件上传+OCR识别比对+自动匹配+人工确认回填+状态撤回+一步退到底）；28/28 任务全绿 |
| f4-aging-enum-unification | F4 应付账款账龄接入平台枚举单一真源（3年段/5年段/自定义）：F4-2 扁平→nested keyed+F4-1段驱动+残差行+后端动态列头；23/24（仅7.3* Playwright留待） |
| h1-four-table-extraction | H1 固定资产四表取数扩展：H1-2 分类级 TB 叶子取数+明细增减↔序时账核对+折旧取数+related_parties注入+试算核对走规则映射；30/30 全绿 |
| h3-cross-workpaper-reconciliation | H3 投资性房地产跨底稿勾稽增强；9/9 全绿 |
| h4-four-table-extraction | H4 工程物资四表取数；10/10 全绿 |
| h5-disclosure-note-linkage | H5 生产性生物资产/油气资产披露↔附注联动（五、xx/八、xx）；7/8（仅8* live留待） |
| j1-disclosure-note-linkage | J1 应付职工薪酬披露表↔附注（五、40/八、40）结构化推送+正反向跳转+2211刷新+覆盖率守卫；12/12 全绿 |

**→ 08-disclosure-notes（+2）**

| Spec | 说明 |
|------|------|
| n1-disclosure-note-linkage | N1 递延所得税资产披露表↔附注（五、30/八、31）结构化推送+正反向跳转+2211 定向刷新+覆盖率守卫；N3 共用章节子表所有权方案 A（N1 独占四张表）；前端 288+后端 63 测试+live round-trip RESTORED_IDENTICAL |
| disclosure-note-formula-data-population | 附注表内公式数据补全（formula binding 119 条+合计标注 393 行+预设 995 条+附注侧 logic_check 61 条+只读诊断 linkage 缺口+契约守卫）；371 测试+真实项目 round-trip PASS；灰度默认 False |

### 上次归档（2026-07-25，活跃 spec 全部收尾归档）

**→ 05-business-features（+7）**

| Spec | 说明 |
|------|------|
| d-cycle-four-table-extraction-formulas | 四表库→D1-D7 底稿自动提取填充 + 公式管理可查可编（Tier B 复用 `_build_adjudication_prefill` / Tier A 可编辑标量；灰度默认关；160 测试绿+7 契约守卫；D6 真 seed 其余宁缺勿造） |
| d-cycle-tier-a-writeback-detail-seed | 前置 spec P0 增量：Tier A 编辑真生效（保存跳 parsed_data+返回 evaluated_value 不落库 + GET value + render transient TB核对行 seed 主机制，D1-D7 全铺）+ P0-2 明细维度归集 render transient seed（子开关 D6-2 试点）；332 测试绿+G6/G7/G8 守卫 |
| adjustment-collaboration-and-propagation | 调整分录多人协作接力（V125 两表+协作锁+复用 NotificationService）+ 明细表联动带入（Part B 无新表读时匹配，K8-2/K9-2 试点）；64 后端+18 前端测试绿 |
| deliverable-lineage-content-control | 交付 docx 章节内容控件化（Block Content Control Tag=`sec_xxx`）+ OnlyOffice 连接器真·光标跟随溯源；灰度+auto-follow 默认关；26 后端+32 前端测试绿（6* 连接器 live 验证 env-gated 留待） |
| balance-import-annual-column-semantics | 余额表导入年度优先+月度兜底（识别层区分年初/期初+本年累计 / 分类层年度=key月度=recommended / 转换层 `_first_decimal` 年度优先）；711 测试绿含 Property 1-15 PBT+三源契约守卫 |
| audit-check-review-gate-hardening | 「审计检查」升级为复核收口 gate（双通道写单一缓存 S1-S5 后端算+S6 前端上报 / 聚合运行时校验源复用口径不新造 / 通过率区分已判定vs未覆盖 / V126 签认只提示不阻断 / 零回归）；后端 475+前端 31 测试+P1-P14 全覆盖；**Playwright E2E 6 流程全绿（0ec33ac9）** |
| ledger-raw-extra-column-display | 账套导入非关键列进 `raw_extra` 后凭证/序时账/辅助明细查询作额外列显示（后端单一 helper `_attach_extra_fields`+前端动态列 el-table/v2/凭证明细）；复制 [object Object] 修复+列显隐⚙；后端 31+前端 29 测试绿+Playwright 真实数据通过 |

**→ 08-disclosure-notes（+1）**

| Spec | 说明 |
|------|------|
| disclosure-notes-selective-generation | 「生成附注」弹窗按附注实时树勾选章节+一键预设（只勾有数据科目）；唯一后端改动=树节点加 `has_data`（与 `_has_content` 收敛共享 `note_content_utils` helper）；导出零改动；后端 15+前端 8 测试绿+live 契约验证 |

### 最近归档（2026-07-24，全循环复盘收尾 + 基础设施加固）

**→ 05-business-features（+3）**

| Spec | 说明 |
|------|------|
| confirmation-coverage-single-source | 函证覆盖率口径修正（TB population 为分母+单一真源+死端点移除+孤儿组件清理） |
| workpaper-adjustment-centralization | 底稿调整→集中登记汇聚（V124+AdjustmentSyncService+全81循环接入+origin过滤防TB双计+a13死事件修复） |
| voucher-sampling-hardening | 抽凭引擎加固（DB级全量抽样框+方法学单一真源+批次状态机+服务端授权+LIKE转义，已push独立分支） |

**→ 06-engineering-governance（+1）**

| Spec | 说明 |
|------|------|
| attachment-ocr-ai-evidence-governance-hardening | 附件/OCR/AI/证据治理加固（65/66 任务；发布门 9 绿 + capacity 6000VU 待专用环境） |

**→ 08-disclosure-notes（+4）**

| Spec | 说明 |
|------|------|
| disclosure-table-sync-convergence | 披露表列头随 `_columns` 携带 + 后端单点投影（43/43 覆盖守卫 --strict 绿，全迁移 F2/F3/H9/H10/G/H/I/K/F1+GtCNoteTable） |
| d7-contract-liabilities-enhancement | D7 合同负债动态账龄全链路 + 调整分录按性质/账龄路由（13/13，复用 D3 机制零平行实现） |
| disclosure-note-formula-and-report-sync | 附注公式求值+报表→附注真同步+校验preset加载修复（20/20，灰度默认关零回归） |
| disclosure-note-validation-completion | 附注校验6 executor落地+ValidationContext数据装配（11类型全实现，Skip优于误报） |
| disclosure-note-knowledge-ai-enrichment | 附注RAG知识库接入AI正文生成（10/11，Task11前置不满足如实未做） |

### 最近归档（2026-07-19，工时模块重构）

**→ 05-business-features（+2）**

| Spec | 任务 | 说明 |
|------|------|------|
| workhour-entry-frontend | 6/6 | Phase7 细粒度工时填报前端入口（Dialog+List+ProjectView+路由） |
| workhour-table-unification | 8/8 | 两套工时表统一迁移（V117 数据迁移+审批改造+兼容层+WeeklyTimesheet 改写） |

### 上次归档（2026-07-18，26个 spec）

**→ 04-infra-architecture（+5）**

| Spec | 任务 | 说明 |
|------|------|------|
| acnr | 76/76 | ACNR 地址坐标名称库（五层模型+resolver+grammar） |
| acnr-consumer-wiring | 100/100 | ACNR 消费者接入（P1-P15全实现） |
| acnr-runtime-convergence | 25/25 | ACNR 运行时闭环修复（Phase1+2，509测试） |
| formula-runtime-convergence | 18/18 | 公式运行时真实写入/回滚/并发收敛 |
| platform-global-hardening | 79/79 | 全局工程治理（displayPrefs/GtWorkpaperShell/CI守卫） |

**→ 05-business-features（+5）**

| Spec | 任务 | 说明 |
|------|------|------|
| confirmation-alternative-factory-convergence | 13/13 | 函证 alternative 八套收敛为工厂（-47%代码） |
| d5-enhancement-polish | 15/15 | D5 应收账款底稿精美化打磨 |
| d6-enhancement-polish | 17/17 | D6 合同资产底稿增强打磨（列设置/勾稽/AI/结论模板） |
| d7-enhancement-polish | 15/15 | D7 合同负债底稿增强打磨（列设置/TB勾稽/公允判断） |
| procedure-delegation-notification | 17/17 | 程序委派通知机制 |

**→ 06-engineering-governance（+6）**

| Spec | 任务 | 说明 |
|------|------|------|
| procedure-delegation-visibility-isolation | 18/18 | 服务端 fail-closed 底稿可见性隔离（V113） |
| visibility-isolation-go-live-hardening | 8/8 | 可见性隔离上线加固（Go_Live_Gate=LIVE） |
| workpaper-maintainability-convergence | 37/37 | 底稿可维护性收敛（GtWpRenderer 465能力槽位） |
| workpaper-maintainability-convergence-followup | 36/36 | 可维护性收敛后续（FormData工厂化） |
| version-trail-full-coverage | 38/38 | 版本链全覆盖（89个D~N主入口+CI守卫） |
| ui-pattern-unification | 18/18 | UI模式统一（抽凭dialog-mode+版本链Toolbar） |

---

## 三、运维命令速查

| 需求 | 命令 |
|------|------|
| 代码规模 | `codegraph status` |
| 超标文件 | `python backend/scripts/check/check_file_size.py` |
| 最高迁移 | `ls backend/migrations/V*.sql \| sort \| tail -1` |
| 三件套完整性 | 扫描 `_archive/` 各 spec 目录是否含 requirements.md + design.md + tasks.md |

---

## 四、索引规约

1. 新建 spec 放 `.kiro/specs/{name}/`（扁平，不可嵌套）
2. 完成 spec 归档移到 `_archive/{分类}/`，同步更新本文件
3. 分类：01地基 / 02循环 / 03打磨 / 04架构 / 05业务 / 06工程 / 07底稿瘦身 / 08附注 / 09合并 / 10全循环 / 11函证 / 12 2023-06-23批 / 13 2026-06-29批 / 99取代
4. **凭印象禁令**：完成度必须实证
5. 迁移系统 = `backend/migrations/V*.sql`（MigrationRunner），新加必须 `IF NOT EXISTS` 幂等
