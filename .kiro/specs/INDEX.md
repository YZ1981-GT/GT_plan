# 致同审计作业平台 — Spec 开发索引

**最后更新**：2026-08-02
**当前分支**：`work/2026-05-30-wp-specs`
**统计**：Active **7**（`.kiro/specs/` 实测目录数）/ Archived 512 = 总计 519
**最高迁移**：**V134**（以 `migration_status` 实测为准）
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
| `e1-four-table-extraction-and-disclosure-alignment` | **20/20 完成，待 commit** | E1 货币资金四表取数 + 披露/附注对齐。实测修掉 2 个平台级 P0（`semantic_account_resolver` 多槽被报表公式兜底污染 → 货币资金合计虚增一倍）+ 2 个前端缺陷。外币章节按选项 A 收口，推送移交下一条 |
| `disclosure-note-row-level-merge` | **15/15 完成 + 真实 DB & 浏览器实测，待 commit** | 平台级**行级合并**：载荷声明 `sub_table_data._row_scope` 即只替换自己那一段，段外行原样保留、fail closed 不退化整表覆盖。段边界读模板**已有**的 `rows[].report_row_code`，不新造标识。全库 **29 张**多段共享表（listed 23 / soe 6），首个消费者 = E1 外币章节。另修 `_note_texts` 整替换 + 段可写区排除表级合计行 |
| `restricted-assets-note-row-scope-rollout` | **16/16 完成 + 真实 DB & 浏览器实测，待 commit** | 受限资产附注表（listed `五、32` 主表+续表 / soe `八、93`）行级合并接入 —— 29 张共享表里**受益面最大**的一张（8 段横跨 E1/D1/D2/D5/F2/H1/H2/I1，改造前**零 pusher**）。**8 段接了 6 段**（只有 D5/F2 真的零数据）；平台补强 `row_type: "unowned"`；修 soe 两处 `report_row_code` 错码/缺码；新增声明式来源表 + 一行接线 composable + 勾稽与段级溯源；顺带修掉 I1 两 Tab 的自调度无限 POST |
| `e1-orphan-components-wiring` | 0/14（三件套已立） | E1 有 **8 个组件已按源模板写好却从未渲染**（~225 KB）：`E1-19` 指向了 E1-18 的组件、IPO/舞弊组 E1-26/29/30/31/32 全走通用扁平表、两个 OCR 弹窗无父级。接线（props 签名已一致 + legacy 键回退已内建）+ 顺手收口金额控件/AI/披露门控/预设 + **新增平台级孤儿组件守卫** |
| `e0-confirmation-completion` | 2/18（三件套已按逐 sheet 精读**重写**，2026-08-02 复盘 + **裁决门 A 已关闭 = A-否**） | E0 货币资金函证精细打磨。逐格读源 xlsx（20 tab）后**三次推翻自己的前提**：①`reliabilityCode: null` 的注释错（`邮件传真回函核对记录F1-12` 就是可靠性表，只是 hidden）②sheet 名真实为 `银行函证其他信息核对表E0-5`（无「询证」）③**`sheet_state` 实证只有 10 张 visible** = `底稿目录` 索引的 9 张 + 目录。**用户裁决 A-否（三张 hidden 底稿不实现）** → R1（13 要项表）/ R7.1·R7.5 / R8.6 与 **Wave 6（Task 7/8/9，~39 KB）已删除**，口径存档在 R1 与 design §1。交付范围：**E0-1 下区四块**（一、函证情况 6×6 矩阵 / 二、样本选择 3 段固定说明 + 未函证理由录入 / 三、审计说明 3 条小标题 / 四、审计结论 + 提示 4 条，第二版只写了矩阵是因首轮 dump 漏了 O/V 列；两处「一句话拆两格」须合并渲染）、E0-1 缺 4 列多 8 列、`GtConfirmationSummary` 写死 `D0-5/D0-6/D0-7`、`handleJumpB50` 是 stub、E0-3/E0-6 受限标记→E1 ②表联动、备忘录改银行口径（工号+公示制度核对）、**可靠性按渠道补 12 列照做**（共享件增强，实测改在 D0-7 上做）、**新增 Task 19 钉死「hidden ⇒ `skip`」不变式**（特别是核对表的全名 `skip` 条目不得删 —— componentType 解析是尾码优先，删了会渲染出列集不符的多余页签）。已完成 2 项：Task 12.5 E0-6 专属组件 `confirmation-wealth-list` 全链、Task 11 `importE0ListsToSummary` 口径纠偏（124→357 行，原 `[ ]` 是假红）；新拆 Task 11b（取数链路两处硬前置，不解则 Task 11 全是 dead code） |
| `e0-send-list-dedicated-components` | 0/18（三件套已立，2026-08-02 复盘扩写 + 同步 A-否） | E0 发函清单专属组件。范围由四张收窄为**三张**（E0-3/E0-4/E0-5 → `confirmation-send-list-e03/e04/e05`）—— E0-6 已由 `e0-confirmation-completion` 落地 `confirmation-wealth-list`，原 `confirmation-send-list-e06` **撤回**，改为符合度核查（Task 17，8 项）；「三 + 一」命名不统一是**有意接受**并写进两份 Glossary。解 grid 兜底污染（`extract_grid(data_only=True)` 把公式缓存值 `XX银行`/`0` 当数据渲染）、E1-3 段语义取数（两版行号完全不同故禁硬编码行号）、K 列金额口径三态可切换；**R16 E0-3 函证范围完整性红线**（准则明文「包括零余额账户和在本期内注销的账户」，三处依据 = `E0A` 程序 1 + `E0-1!O28/O29` + `回函情况汇编` 编制说明 2/3，数据齐备但平台零校验）。**随 A-否 关闭两个待裁决**：R15 由「翻转 override 查表顺序」改为**只钉死全名 `skip` 不变式**（实证 skip 判定 L709 全名优先、componentType 判定 L749 尾码优先，两者顺序相反使当前配置已正确）→ Task 14 降级、不再阻塞 Task 5；R17 资金归集勾稽**永久留遗留**（对侧表不实现） |
| `e0-send-list-dedicated-components` | 0/18（三件套已立，2026-08-02 复盘扩写） | E0 发函清单专属组件。范围由四张收窄为**三张**（E0-3/E0-4/E0-5 → `confirmation-send-list-e03/e04/e05`）—— E0-6 已由 `e0-confirmation-completion` 落地 `confirmation-wealth-list`，原 `confirmation-send-list-e06` **撤回**，改为符合度核查（Task 17，8 项）；「三 + 一」命名不统一是**有意接受**并写进两份 Glossary。解 grid 兜底污染（`extract_grid(data_only=True)` 把公式缓存值 `XX银行`/`0` 当数据渲染）、E1-3 段语义取数（两版行号完全不同故禁硬编码行号）、K 列金额口径三态可切换；新增 **R16 E0-3 函证范围完整性红线**（准则明文「包括零余额账户和在本期内注销的账户」，双依据 = `E0A` 程序 1 + `E0-1!O28`，数据齐备但平台零校验）+ **R17 资金归集链路登记** |
| `g-cycle-extraction-mapping-and-disclosure-alignment` | 7/30 | G 循环四表映射与披露对齐（含 `report_config` 4 处错码修复）—— **并发会话在推进** |
| `d4-four-table-extraction-and-disclosure-alignment` | **33/33** | D4 营业收入四表取数与披露/附注对齐 |
| `h-cycle-four-table-extraction-and-account-mapping` | 0/25 | H 类四表取数与科目映射收口 —— **并发会话** |
| `f-cycle-four-table-extraction-and-disclosure-completion` | 0/16 | F 类四表取数与披露/附注收口 —— **并发会话** |

> 🔴 最后 4 条是**并发会话**的活跃 spec，本会话未触碰。跨会话协作时不要并行推进同一 spec
> （memory 已实证并发会话会互相回退同一文件）。

2026-08-01 收尾归档：`g6-four-table-extraction`(10/10) · `g5-four-table-extraction`(20/20) ·
`disclosure-note-follow-actual-content`(13/13) → `08-disclosure-notes`；
`procedure-mainline-convergence`(42/42) → `04-infra`；2 个空壳 → `99-superseded`。

新建 spec 放 `.kiro/specs/{name}/`（扁平，不可嵌套）。

---

## 二、已归档 Spec（512个，15 分类）

```
_archive/
├── 01-phase-foundation/              24
├── 02-workpaper-cycles/              16
├── 03-refinement-rounds/              9
├── 04-infra/                          2
├── 04-infra-architecture/            36
├── 05-business-features/            234
├── 06-engineering-governance/        13
├── 07-workpaper-slimdown/            22
├── 08-disclosure-notes/              53
├── 09-consolidation-phases/           5
├── 10-A~S-workpaper-all-cycles-complete/ 31
├── 11-confirmation-d0-module/        11
├── 12-2026-06-23-batch/              12
├── 13-2026-06-29-batch/              33
└── 99-superseded/                     5
```

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

**→ 11-confirmation-d0-module（+1）**

| Spec | 说明 |
|------|------|
| confirmation-linkage-completion | 函证两价值孤儿正式做完（19/19） |

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
