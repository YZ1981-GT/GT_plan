# 致同审计作业平台 — Spec 开发索引

**最后更新**：2026-08-07
**当前分支**：`work/2026-05-30-wp-specs`
**统计**：Active **12**（2026-08-07 行首锚定正则实扫）/ Archived **531**
**最高迁移**：**V143**（`word_export_task_versions.drift_report`；以 `migration_status` 实测为准）
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

| spec | 进度 | 一句话 |
|------|------|--------|
| `f0-confirmation-linkage-and-structural-enhancement` | 139/144（1 个 `[-]` + 2 个 `[~]` + 2 个 `[ ]`，**全是浏览器实测且用户 2026-08-03 已中止该轮 → 编排器不得接管**） | F0 存货循环函证联动增强：矩阵自动聚合 + F0-5/F0-6 供应商自动带入 + B50/A13 推送 + F0-7 可靠性结构化。**复盘退回 3 项 + Wave 7 返工 9 项**（矩阵三个入参仍传 `undefined` → 4 个百分比行恒 `-`；5 个新模块 4 个零消费方）—— **并发会话在推进，勿碰** |
| `sampling-compliance-closure` | 24/25（只剩 Task 24 浏览器实测） | 抽样/抽凭合规闭环：dataset 版本绑定 + 推断错报持久化 + A13 `projected` 通路 + 删 legacy 抽样引擎 + 准则记录表接入 + 42 宿主 methodology 收口。canonical 抽凭链路不重构，只做加法 + 删 legacy |
| `k0-confirmation-source-alignment` | 7/18（三件套已立） | **K0 管理循环函证源模板对齐**。逐格精读 11 张 sheet（10 visible + `GT_Custom` hidden）后实证 5 类缺口：**K0-1 下区四块完全缺失**（2 品种×8 指标矩阵 / 样本选择 6 项 / 审计说明 5 项 / 审计结论），`isK0` 在 `GtConfirmationSummary.vue` 零命中；**`send_memo` 是伪列**（把源 `C5:F5` 合并的分组表头当成了一个自由文本列），`row_conclusion` 段归属错（G0/H0 已用 `row_summary` 并在注释指明 K0/L0 待修正），源模板无联系人/联系电话/币种三列而 `CYCLE_EXCLUDED_COLUMNS.K0` 为空，源 `G6 函证方式` 实为渠道而未启用已有的 `send_channel`；**列标签 13 处与源模板分叉**（`account_type` 标「科目」而源为「账户/交易」，它是矩阵 SUMIF 的品种维度）；**公式预设整块贴错标签**（`sheet='审定表K0-1'` 源 xlsx 无此 tab + 审定表口径 cell_ref + 漏 `2241`）；**三处源模板索引号笔误 + 底稿目录序号跳号**（`K1-12`→K0-4 / `K0-6`→K0-7 / `K1-11`→K0-3；序号 `[1..5,7..10]` 缺 6）。矩阵按 H0 已确立范式新建（复用 `safeRatio`/`sumByCategory`，**不重构三份矩阵**）。Wave 3 须等 F0 spec 收口 |
| `report-config-account-code-integrity` | **10/12**（Wave 1~3 + CI 完成；剩 Task 10 BS-014 待用户拍板 + Task 12 收口） | **`report_config` 科目码完整性**。全表对账（132 条 `TB()` 引用 / 102 行）扫出 **13 行错码**，远超此前手工发现的 6 处 —— **权益段 BS-081~BS-090 是一整块错位**（BS-082 其他权益工具取到其他综合收益 / BS-084 库存股取到零命中码 / BS-085 / BS-086 专项储备取到本年利润 / BS-090 少数股东权益取到库存股），另 BS-033 开发支出取到无形资产减值准备、BS-053 与 BS-067 同认领 `2901` **跨行双算**、IMP-008 取到旧准则科目、IMP-017 把商誉原值当备抵。并查出 **`V136` 是失效迁移**（前提错、`WHERE` 从不命中）。**V138 已应用真实库**（连库守卫 29 passed）。**Task 7 挖出立项完全没看到的风险：`report_config.formula` 有第二条写入路径** —— `ReportFormulaService.fill_all_formulas()` 按**行名**索引且 `if cfg.formula: skip` 只填 NULL 行，恰好正是 V138 置 NULL 的那批 ⇒ 不修等于 V138 白做（已按镜像改码 + 策略前置拦截 + 名表删除三层收口，8 个变异全部打红）。核心交付是**平台级一致性守卫**（这张表此前零校验，错码可静默存在数年）+ CI job（117→118）。BS-014 与 V138 范围（12 行 vs 并入 BS-052/BS-066 = 14 行）待用户裁决 |
| `l0-confirmation-source-alignment` | 0/20（三件套刚立，**并发会话新建 08-05 17:41**） | L0 循环函证源模板对齐（沿用 K0/G0/H0 范式） |
| `sampling-evaluation-and-governance-closure` | 0/19（三件套刚立，**并发会话新建 08-05 18:12**） | 抽样评价与治理闭环（`sampling-compliance-closure` 的后继） |

> 🔴 `f0-*` / `l0-*` / `sampling-evaluation-*` 由**并发会话**推进，本会话未触碰。
> 跨会话协作时不要并行推进同一 spec（memory 已实证并发会话会互相回退同一文件，
> 本会话又实测到一次：`report_formula_service.py` 的「存货的减少」在十分钟内被改成单码，
> 由新上线的守卫打红后按实证恢复）。

**2026-08-05 空壳目录清理（2 个，Active 区不再有非 spec 目录）**：

`procedure-delegation-visibility-isolation` / `visibility-isolation-go-live-hardening` 两个目录只剩
`evidence/artifacts/`（无三件套、**未被 git 跟踪**），其 spec 文档早已完整归档在
`_archive/06-engineering-governance/`（86 个 tracked 文件）。逐文件哈希比对确认这批 evidence 是
**更早且已被取代的测量轮次**（canonical 是 6000 请求 / 64 并发，空壳里是 1500 / 48，项目 UUID 亦不同），
其中 6 个文件与两份归档副本都不同 ⇒ **不删除**，整体移入
`_archive/06-engineering-governance/{spec}/evidence/artifacts-superseded-run/`（零覆盖、移动前后哈希逐一相等）。
Archived 计数不变（未新增 spec，只是归位证据产物）。
> 🟡 `_archive/99-superseded/` 下另有这两个 spec 的**同名 evidence-only 目录**（24 个 tracked 文件，
> 其中 `visibility-isolation-go-live-hardening` 还嵌套了一层同名目录）—— 是更早一次未完成的归档搬移残留。
> 清理它需要删除 tracked 文件，留待确认。

**2026-08-05 归档（1 个，→ `05-business-features`）**：

`deliverable-lineage-wiring-and-writeback-closure`(25/25 + 40 个复选框全 `[x]`) —— 交付件溯源接线与回填闭环。
立项时的实证基线：`write_section_anchors` / `snapshot_on_confirm` / `_classify_change` 三者**生产零调用方**
⇒ 溯源/stale/刷新/回填整条链空转（前序 spec 22/22 全绿是**假绿**，测试自己合成带锚点的 docx）。
四波交付：**Wave 1** 锚点写入 + 章节状态落库 + 回填 rowcount 五桶 + 就地刷新 + 能力矩阵单一真源（真实链路验收 **12/12**，
真实项目写入 141 个锚点、`/section-states` 从全库 0 行变 141 行）· **Wave 2** 快照继承 + `doc_key` 去时间戳 +
真实编辑人（V142）+ 护栏接线（**实证席位从来没真正释放过**：占用用 `current_user.id`、释放用 `created_by`
且版本号取的是 OO 内部号，全靠 1h TTL 自愈）· **Wave 3** 报告正文段落级回填（真实链路验收 **18/18**，
发现 Word 模板模式下 `report_body_json` 只有 6 个元数据键、段落文字只在 docx 里 ⇒ 补 additive `sections`）·
**Wave 4** xlsx 差异告警（V143）+ 溯源可视化（版本链 `is_stale` 三态 + 三件套三列对照 + 列表行级溯源抽屉）。
**收尾修正推翻了自己上一轮的归因**：真实库那 22 处「Cell_Mapping 配置错位」实为**检测器自身缺陷** ——
资产负债表拆「主表 + 续表」而 JSON 两侧共用 `balance_sheet` 键且坐标重叠，按 `sheet_aliases` 取第一个匹配
sheet 会让续表 49 个 row_code 去主表取值；改为与 exporter 同源（逐 sheet 扫内联 `{{row:}}` 占位符 +
按真实 sheet 名取值）后 22→5 处（逐格核对确认真差异），另一真实报表变 `checked=452 / diffs=0` 完全一致。
真实库跑 detect 还揪出 naive/aware datetime 裸比较抛 `TypeError` 被 fail-open 吞成「无数据」的真 bug。
**遗留**：浏览器层肉眼实测（后端真实链路验收已 12/12 + 18/18 通过）· 尚未 commit。

**2026-08-04 归档（3 个，→ `11-confirmation-d0-module`）**：

`g0-confirmation-source-alignment`(23/23) —— G0 投资循环函证源模板对齐。逐格精读 10 张 sheet（全 visible）后
补齐 G0-1 下区四块（8 品种×8 指标矩阵「有就显示没有隐藏」+ 防死锁开关 / 样本选择 6 项 / 审计说明 5 段 / 审计结论）、
按循环解析跨表导航（删写死 `D0-*`）、G0A 补回 12 条 `program_category`（备选与 IPO 专项不再默认勾选）、
公式预设从「审定表口径 + `TB_SUM('1101~1511')`」改为 8 条 PLACEHOLDER、G0-6 三区块按源模板重排（删自造记账凭证列、
`support_doc` 拆成支持性文件 1/2 各三列）、9 条源模板缺陷显式登记并在 UI 逐条可追溯。
**顺带修掉两个真实数字/口径错误**：证券差异表三列方向全反（源 `M=J−G` 与表头 `③=①−②` 矛盾，平台照抄了缺陷方向 →
统一为账面 − 回函，两张差异表此前互相矛盾）· 该表组表头字面遗留 `差异（②−①)` 与派生方向自相矛盾（Task 23 浏览器实测抓出）。
**Task 23 实测 8 项 7 通过**，1 项受阻于平台级孤儿组件（`CrossWorkpaperNav.vue` 全仓零渲染宿主 →
Task 11 的修复正确但用户不可达；Property 13 只断言了链条上游有消费方，整条链仍是死的）。
遗留两条平台级议题已登记该 spec §Notes：孤儿导航组件接线（建议与 `e1-orphan-components-wiring` 合并）·
替代程序区块 `CheckBlock.vue` 可编辑金额列用 `el-input type="number"` 致千分符结构上不可能出现（七枢纽同款）。

`h0-confirmation-source-fidelity-and-linkage`(24/24) —— H0 固定资产循环函证源模板保真度与联动补齐。
逐格精读 9 张 sheet（**全 visible**）后修掉三个 P0（「账户/交易」下拉三处互不一致且无 H 类科目 /
H0-1 下区四块完全缺失 / H0-5 四段编号与源模板全部错位），并在真实库直跑与浏览器实测中挖出
**6 个额外缺陷**（其中 2 个是活的错数：H3 裸通名兜底把固定资产累计折旧扣进投资性房地产致账面金额为负；
H0 聚合忽略 `closing_direction` 把 contra 子科目加成正数）。

**2026-08-03 归档（4 个，→ `08-disclosure-notes`）**：
`h-cycle-four-table-extraction-and-account-mapping`(25/25) ·
`d4-four-table-extraction-and-disclosure-alignment`(33/33) ·
`n-cycle-note-template-and-disclosure-completion`(13/13) ·
**`semantic-account-resolver-full-rollout`(31/31)** —— 结论是「应立即迁移的策略 = 0 个」，
交付物是**三道守卫**而非批量迁移：定向裁决交叉锁死（未迁移清单 ⊆ 已登记裁决理由，
33 条逐条带实证）· 旧制编码数据触发守卫（旧制码一带非零余额即打红，把「该迁移了」
交给数据判断）· F2 展示元数据错码纠正。

新建 spec 放 `.kiro/specs/{name}/`（扁平，不可嵌套）。

---

## 二、已归档 Spec（531 个，15 分类）

```
_archive/
├── 01-phase-foundation/              24
├── 02-workpaper-cycles/              16
├── 03-refinement-rounds/              7
├── 04-infra/                          3
├── 04-infra-architecture/            37
├── 05-business-features/            235
├── 06-engineering-governance/        13
├── 07-workpaper-slimdown/            22
├── 08-disclosure-notes/              75
├── 09-consolidation-phases/           5
├── 10-A~S-workpaper-all-cycles-complete/  31
├── 11-confirmation-d0-module/        15
├── 12-2026-06-23-batch/              12
├── 13-2026-06-29-batch/              33
└── 99-superseded/                     3
```

### 最近归档（2026-08-07）

**→ 04-infra-architecture（+1）**

| Spec | 说明 |
|------|------|
| formula-management-runtime-closure | 公式管理运行层闭环（18/18 + 归档前双轮复核）。修六类实证缺陷：**48 格数字错**（`COLUMN_ALIASES` 缺 4 个发生额列名，两条求值路径静默回退期末余额 → 现 8→14 键 + 三态 helper `_resolve_tb_column`，未注册列名格数 48→**0**）· 用户公式与 Tier A **两套存储收敛**进 `wp_formula`（0 行 = 零迁移压力，GET 保留读兼容分支且守卫钉死）· `logic_check` 结果落库 `cross_check_results` · 删 **4 个同族孤儿**（`useFormulaStatus.ts` / `FormulaTooltip.vue` / `FormulaSourceDrawer.vue` / `FormulaDependencyGraph.vue`，均 0 消费方 + 调后端零命中端点）· 底稿公式面板补 issue/hint/计算时间/中文类型标签 · 27 处硬编码 URL 收敛进 `apiPaths/formula.ts` + **平台级「前端公式 URL ⊆ 后端真实路由」守卫**。另修 3 处 spec 未记缺陷（`SUM_TB` 丢弃列名 / `_COLUMN_MAP` 把发生额映到无该列的 `TrialBalance` 静默返 0，24 个消费方 / TB 正则缺词边界误匹配 `SUM_TB` 后半段）。归档复核再修 2 处：**`test_wp_formula_layer_contract.py` 恒红零信号**（列清单只到 V100 而 V104 又加 3 列 → 判据改为扫全部 `V*.sql` 抽取，自动跟随迁移）· `draftRefresh` 漏进 `apiPaths` barrel（+ barrel 完整性守卫）。后端守卫 133 passed / 前端 60 passed / 变异 6/6 RED。与同分类 `formula-engine-unification`、`formula-runtime-convergence` 同族 |

### 最近归档（2026-08-05）

**→ 05-business-features（+1）**

| Spec | 说明 |
|------|------|
| deliverable-lineage-wiring-and-writeback-closure | 交付件溯源接线与回填闭环（25/25，四波全收口 + 两次真实链路验收 12/12、18/18）。与同分类的 `deliverable-lineage-and-writeback`（被它修的前序 spec）、`deliverable-lineage-content-control`、`audit-report-deliverable-center` 同域 |

### 最近归档（2026-08-03）

**→ 08-disclosure-notes（+3）**

| Spec | 说明 |
|------|------|
| h-cycle-four-table-extraction-and-account-mapping | H1~H10 语义科目定位收口（25/25 + 复盘 5 项 + 浏览器实测）：修 3 个「取错整个科目族」P0（H3 `1503/1504`→`1521/1525/1526/1527`、H8 `1901` 待处理财产损溢→`1641/1642/1643`、H9 `2205` 合同负债→`2601/2602`）；实测挖出 `parent_check` 揭示的 `trial_balance` 父子双算平台级缺陷 |
| d4-four-table-extraction-and-disclosure-alignment | D4 营业收入四表取数与披露/附注对齐（33/33） |
| n-cycle-note-template-and-disclosure-completion | N 循环附注模板与披露收口（13/13） |

### 最近归档（2026-08-01，第四批）

**→ 08-disclosure-notes（+14）**

| Spec | 说明 |
|------|------|
| f1-four-table-extraction-and-disclosure-alignment | F1 预付款项四表库取数链路根治+披露/附注收尾（28/28 全完成+实测） |
| f1-extraction-chain-and-disclosure-source-fidelity | F1 取数链路数据源忠实度（16/17，仅缺浏览器活测；实现已完成） |
| h3-investment-property-disclosure-alignment | H3 投资性房地产披露对齐（11/11 全完成+实测） |
| h5-oil-gas-disclosure-alignment | H5 油气资产披露对齐（8/8 全完成+实测） |
| h7-biological-assets-disclosure-rebuild | H7 生产性生物资产披露重建（12/12 全完成+浏览器实测） |
| h8-right-of-use-disclosure-alignment | H8 使用权资产披露对齐（7/7 全完成+实测） |
| h9-h10-remaining-disclosure-alignment | H9 租赁负债 + H10 资产处置损益披露对齐（9/9 全完成+实测） |
| k1-extraction-chain-and-note-alignment | K1 其他应收款取数级联第二轮收口（28/28 全完成+实测） |
| k1-four-table-extraction-and-disclosure-alignment | K1 四表库取数口径根治+披露/附注结构对齐（27/27 全完成+实测） |
| k2-four-table-extraction-and-dynamic-rows | K2 其他流动资产四表取数+动态行（13/13 全完成+实测） |
| n1-four-table-extraction-and-disclosure-alignment | N1 递延所得税资产四表取数+披露对齐（24/24 全完成+实测） |
| n2-disclosure-and-extraction-alignment | N2 应交税费披露与取数对齐（19/19 全完成+实测） |
| n2-vat-calc-source-alignment | N2 增值税计算源模板对齐（19/19 全完成+实测） |
| n345-four-table-extraction-alignment | N3/N4/N5 四表取数对齐（26/26 全完成+实测） |

**→ 99-superseded（+1）**

| Spec | 说明 |
|------|------|
| n2-source-alignment | 被 `n2-disclosure-and-extraction-alignment` 取代（仅含未落盘的 implementation-checklist） |

**清理空壳（2个）**

| Spec | 说明 |
|------|------|
| procedure-delegation-visibility-isolation | 早已归档（2026-07-18），残余 evidence 目录清除 |
| visibility-isolation-go-live-hardening | 残余 evidence 目录清除 |

### 2026-07-31 归档

**→ 08-disclosure-notes（+19，含并发会话完成的 spec）**

| Spec | 说明 |
|------|------|
| h2-construction-in-progress-disclosure-alignment | H2 在建工程披露结构对齐（7/7 全完成+实测）：两级表头重建 + 「项  目」→「工程物资」改名 + 10 表 columns/guidance + 契约守卫 + CI job + 浏览器实测通过 |
| d2-ar-disclosure-template-alignment | D2 应收账款上市披露三层对齐（31/31 全完成+实测+已提交） |
| d2-ar-disclosure-soe-alignment | D2 应收账款国企披露结构对齐（25/25 全完成） |
| f2-inventory-disclosure-template-alignment | F2 存货披露对齐（Sprint 1~8 全完成+已提交） |
| f1-prepayment-disclosure-template-alignment | F1 预付款项披露对齐（全完成+实测+待 commit） |
| disclosure-columns-coverage-rollout | 披露表 columns 覆盖推广（Task 1~16 全完成+已提交） |
| j1-disclosure-template-alignment | J1 应付职工薪酬披露对齐（61/61 全完成+待 commit） |
| k2-other-current-assets-disclosure-alignment | K2 其他流动资产披露对齐（22/22 全完成+实测） |
| n1-deferred-tax-disclosure-template-alignment | N1 递延所得税资产披露对齐（57/61 实现+实测完成） |
| n-cycle-tax-disclosure-alignment | N 循环税务类披露对齐（N2/N4/N5 全完成+实测） |
| d-cycle-remaining-disclosure-alignment | D3/D5/D6/D7 披露结构对齐（Task 1~9 全完成+实测） |
| k-cycle-disclosure-alignment | K1~K13 三批披露对齐（全完成+实测） |
| d1-notes-receivable-disclosure-alignment | D1 应收票据披露对齐（四阶段全完成+实测） |
| f-cycle-disclosure-parity | F 类披露复盘对齐（R1~R9 全完成） |
| applicable-standards-frontend-wiring | 准则前端全链接通（全完成+实测） |
| applicable-standards-runtime-and-sync-guard | 准则运行时守卫（全完成+实测） |

**→ 05-business-features（+2）**

| Spec | 说明 |
|------|------|
| f1-prepayment | F1 预付款项（含四表库自动取数补齐） |
| k2-other-current-assets | K2 其他流动资产 |

**→ 06-engineering-governance（+1，清理空壳）**

| Spec | 说明 |
|------|------|
| procedure-delegation-visibility-isolation | 服务端底稿可见性隔离（18/18，2026-07-18 已归档，空壳清理） |

### 2026-07-29 归档（12 个，详见 git log）

**→ 05-business-features（+9）**

| Spec | 说明 |
|------|------|
| advanced-query-consolidation | 高级查询模块合并收敛（12/12） |
| attachment-workpaper-linkage-convergence | 附件↔底稿联动收敛（23/23） |
| f2-adjudication-import-export | F2 审定表导入导出（9/9） |
| f2-detail-ledger-pull | F2 明细表序时账取数（11/11） |
| f2-four-table-extraction-refresh | F2 四表取数刷新（22/22） |
| hi-cycle-four-table-extraction | H/I 循环四表取数（14/14） |
| lmn-four-table-extraction | L/M/N 循环四表取数（12/12） |
| template-library-formula-preset-custom | 模板库公式预设（16/16） |
| work-hours-auto-collect-and-edit | 工时自动采集与编辑（18/18） |

**→ 08-disclosure-notes（+1）**

| Spec | 说明 |
|------|------|
| d-cycle-disclosure-note-enhancement | D3-D7 审定↔披露差异告警（13/13） |

**→ 09-consolidation-phases（+1）**

| Spec | 说明 |
|------|------|
| consol-disclosure-note-persistence | 合并附注 V2 按项目灰度（9/9） |

**→ 11-confirmation-d0-module（+4）**

| Spec | 说明 |
|------|------|
| confirmation-linkage-completion | 函证两价值孤儿正式做完（19/19） |
| h0-confirmation-source-fidelity-and-linkage | H0 固定资产循环函证源模板保真度与联动（24/24） |
| g0-confirmation-source-alignment | G0 投资循环函证源模板对齐与联动补齐（23/23） |
| confirmation-orphan-and-amount-format-closure | 函证域孤儿件与金额格式收口（13/13）：删 3 个 G0 零消费方 composable · `CrossWorkpaperNav.vue` 挂上首个渲染宿主（改造前全仓零宿主 = 用户不可达）· `BlockColumnDef.render:'amount'` + 七枢纽 76 个金额列标注 + 17 个非金额列登记 · 新增平台守卫「渲染宿主存在性」（组件基线 2 / 模块基线 23，只许缩短） |

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
