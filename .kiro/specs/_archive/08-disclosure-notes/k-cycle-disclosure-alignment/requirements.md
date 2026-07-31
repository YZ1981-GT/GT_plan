# Requirements Document

K 循环（K1、K3~K13）披露表 ↔ 附注对齐

## Introduction

K2 已按 `k2-other-current-assets-disclosure-alignment` 收口，作为样例。本 spec 把同一套做法铺到 K 系其余 12 个循环。

### 全循环普查实证（2026-07-30，openpyxl 读源 xlsx + 模板 JSON 逐表核）

| 循环 | sheet 名 | 附注表数（listed/soe） | 主要缺口 |
|---|---|---|---|
| K1 其他应收款 | 🔴 listed 前半角 `附注披露信息(上市公司）` | 18 / 19 | 37 表全缺 `columns`；4 表残留 `header_label` 假行；soe 有裸名表 `续：` |
| K3 其他应付款 | ✓ 半角双侧（源 xlsx 即半角） | 7 / 6 | 13 表全缺 `columns`+`guidance`；listed 有泄漏表名 `项  目` |
| K4 其他流动负债 | ✓ | 3 / 1 | 4 表全缺；listed 表 3 名为 `债券名称`（表头首格） |
| K5 预计负债 | ✓ | 1 / 1 | 2 表全缺 |
| K6 持有待售 | ✓ | 6 / 4 | 10 表全缺；假行 4 处；泄漏名 `项  目`；占位表名 `子公司A`/`分公司B` |
| K7 递延收益 | ✓ | 1 / 2 | 3 表全缺 |
| K8 销售费用 | 🔴 双侧半角 vs xlsx 全角 | 1 / 1 | 2 表全缺；listed 子表名错位 |
| K9 管理费用 | 🔴 双侧 | 1 / 1 | 同上 |
| K10 其他收益 | 🔴 双侧 | 1 / 1 | 2 表全缺；soe 是 4 列（末列「是否为政府补助」）常量只 3 列 |
| K11 资产减值损失 | 🔴 双侧 | 1 / 1 | listed 章节号错；泄漏名 `项  目` |
| K12 营业外收入 | 🔴 双侧 | 1 / 1 | listed 章节号错；泄漏名；第 4 列不推；占位行 |
| K13 营业外支出 | 🔴 双侧 | 1 / 1 | 同 K12 |

### 三个 P0（会导致数据落空，非美化问题）

1. **K11/K12/K13 上市侧同步落不到章节**：常量写 `资产减值损失` / `营业外收入` / `营业外支出`（连 `三、` 前缀都没有），而模板 `section_number` 实为 `三、资产减值损失（损` / `三、营业外收入（注：` / `三、营业外支出（注：`。`sync_from_workpaper` 按 `(project_id, year, note_section)` 定位 → 上市侧会新建垃圾章节，附注永远看不到数据。**模板侧编号不能改** —— listed 模板 `三、` 整章 70+ 条 `section_number` 都被 md 重建截断为 10 字符（`三、重要性标准确定方` / `三、投资性房地产【不` …），这是该章的既有形态，改动会波及全章与并发 spec。
2. **K8/K9 上市侧孤儿子表**：常量表名 `销售费用` / `管理费用`，模板实为 `销售费用（按费用性质列示）` / `管理费用（按费用性质列示）`。
3. **列结构缺失导致数据丢失**：K12/K13 的「计入当期非经常性损益的金额」组件已录入但载荷不推；K10 国企第 4 列「是否为政府补助」常量未声明。

## Glossary

| 术语 | 含义 |
|---|---|
| 损益类批次 | K8~K13，附注均为单表（K10 国企 4 列），结构同构，可共用列/载荷 helper |
| 泄漏表名 | md 重建把表头首格（`项  目`）或段落文本当成 `tables[].name` |
| 占位说明行 | 模板 `rows` 里的 `可无限量添加行` / `......` / `……`，会渲染成一行空披露数据 |
| 截断章节号 | listed 模板 `三、` 章的 `section_number` 被 md 重建截断为 10 字符，是既有真源形态 |

## Requirements

### 需求 1：sheet_name 与源 xlsx tab 名逐字一致

**用户故事**：作为审计助理，我要在附注里点「打开同步底稿」能准确跳回该循环的披露 sheet。

#### 验收标准

1. WHEN 构建同步载荷 THEN `X_DISCLOSURE_SHEET_NAME` 逐字等于源 xlsx 的披露 tab 名（含括号半/全角的原样差异）。
2. WHERE 源 xlsx 本身是半角（K3） THE SYSTEM SHALL 保留半角，不得"统一"为全角。
3. WHEN 修改任一 `X_DISCLOSURE_SHEET_NAME` THEN 重跑 `gen_note_wp_sync_registry.py --write`。
4. THE SYSTEM SHALL 提供守卫，直接以 openpyxl 读 `wb.sheetnames` 与常量比对（现有 `disclosureSheetNameRegistry.spec.ts` 只比对「常量 ↔ registry」，registry 由常量生成，查不出与 xlsx 的漂移）。

### 需求 2：章节号与子表名与模板逐字一致

#### 验收标准

1. WHEN K11/K12/K13 上市侧同步 THEN `section_id` 等于模板实测 `section_number`（含截断后缀）。
2. WHEN 任一循环同步 THEN 每个子表名都能在对应章节 `tables[].name` 中找到。
3. THE SYSTEM SHALL NOT 修改 listed 模板 `三、` 章的 `section_number`（整章形态，跨 spec 风险）。
4. WHEN 模板表名是泄漏名（`项  目` / `债券名称`）或占位名（`子公司A`） THEN 由幂等脚本改为科目/业务表名，说明移入 `guidance`。

### 需求 3：列结构与行名对齐附注模版

#### 验收标准

1. WHEN 构建载荷 THEN 每张表 `columns` 的列集合与模板 `headers` 同形（列数相等、标签列 label = `headers[0]`）。
2. WHEN K12/K13 同步 THEN 推送第 4 列「计入当期非经常性损益的金额」。
3. WHEN K10 国企同步 THEN 推送第 4 列「是否为政府补助」。
4. WHEN 任一表同步 THEN 至少一列带 `flat: true`（K 系损益类源模板皆单行表头）。
5. WHERE 底稿保留审计分析列（变动额 / 变动率 / 占比 / 备注） THE SYSTEM SHALL 在同步时投影成附注形状，不把这些列推给附注。
6. WHEN 模板 `rows` 含占位说明行（`可无限量添加行` / `......` / `……`） THEN 由幂等脚本删除，语义移入 `guidance`。

### 需求 4：附注模板补 columns 与 guidance

#### 验收标准

1. WHEN 修订完成 THEN 本批各章节每张表都有 `columns`（显式 `flat`）与 `guidance`。
2. THE `guidance` SHALL 只取源模板红/蓝字、附注模版【提示：…】原文、校验预设勾稽或数据来源，不得自造。
3. THE 修订 SHALL 做成幂等脚本，支持 `--dry-run` / `--check`，写 `_aligned_by` 标记，并在写入前自校验。

### 需求 5：平台 UI 铁律落地

#### 验收标准

1. WHEN 披露表渲染可编辑金额 THEN 使用 `WpAmountInput`（`el-input-number :formatter` 在 EP 2.13.6 是空操作）。
2. WHEN 披露表渲染只读金额 THEN 走 `fmtAmount` 单一真源。
3. WHEN 披露表存在文本说明区 THEN 该区标题行右侧有 AI 辅助按钮，prompt ≥20 字且写明源模板口径与「不得虚构」。
4. WHEN 表名变更或区块关闭 THEN 载荷携 `_removed_table_keys`。

### 需求 6：守卫与实测

#### 验收标准

1. THE SYSTEM SHALL 为每批提供契约测试，经共享 helper `runDisclosureSubtableContract` 覆盖 P1~P5。
2. WHEN 新增 `build{X}ListedColumns` / `build{X}SoeColumns` THEN 在 `disclosureColumnsCoverage.spec.ts` 的 `P1_ROUTE` 登记。
3. THE SYSTEM SHALL 提供后端结构守卫测试与 CI job。
4. WHEN 每批实现完成 THEN 经浏览器实测「录入 → 自动同步 → 附注章节落库」，以 `disclosure_notes.table_data` 为准。
