# 附注语义结构试点章节清单

> 本文档为 `disclosure-note-semantic-structure-and-presentation` spec P0-MVP 阶段的现状盘点与试点选择结果。
> 生成日期：2026-06-06

## 1. 试点章节总览

### 1.1 会计政策条款试点（2 个）

用于验证 `_policy_clauses` sidecar 条款化解析、三栏对照、批量确认等能力。

| 序号 | 模板版本 | 章节标题 | section_id | parent_section_id | 章节编号 |
|------|---------|---------|-----------|-------------------|---------|
| 1 | 国企版 (soe) | 重要会计政策、会计估计 | `chapter-04-zhong-yao-kuai-ji-zheng-ce-kuai-ji-gu-ji` | `null`（一级） | 四 |
| 2 | 上市版 (listed) | 重要会计政策及会计估计 | `chapter-03-zhong-yao-kuai-ji-zheng-ce-ji-kuai-ji-gu-ji` | `null`（一级） | 三 |

**典型子条款（以国企版为例）**：会计期间、记账本位币、记账基础和计价原则、企业合并、合并财务报表编制方法、合营安排、现金及现金等价物、外币业务、金融工具、套期会计、存货、长期股权投资、投资性房地产、固定资产、在建工程、借款费用等。

### 1.2 报表科目注释试点（3 个）

用于验证 `_tables` sidecar 四维上下文、`table_id/row_id/col_id/row_type`、单元格来源面板等能力。

| 序号 | 科目 | 国企版 section_id | 上市版 section_id | 底稿编号 | 科目编码 |
|------|------|------------------|------------------|---------|---------|
| 1 | 应收账款 | `chapter-08-cai-wu-bao-biao-zhu-yao-xiang-mu-zhu-shi-ying-shou-zhang-kuan` | `chapter-05-he-bing-cai-wu-bao-biao-xiang-mu-zhu-shi-ying-shou-zhang-kuan` | E4-1 | 1122 |
| 2 | 固定资产 | `chapter-08-cai-wu-bao-biao-zhu-yao-xiang-mu-zhu-shi-gu-ding-zi-chan` | `chapter-05-he-bing-cai-wu-bao-biao-xiang-mu-zhu-shi-gu-ding-zi-chan` | E9-1 | 1601, 1602 |
| 3 | 货币资金 | `chapter-08-cai-wu-bao-biao-zhu-yao-xiang-mu-zhu-shi-huo-bi-zi-jin` | `chapter-05-he-bing-cai-wu-bao-biao-xiang-mu-zhu-shi-huo-bi-zi-jin` | E1-1 | 1001, 1002, 1012 |

### 1.3 关联方章节试点（2 个）

用于验证关联方专项披露建模（主体/关系/交易/余额/证据/tie-out）。

| 序号 | 章节标题 | 国企版 section_id | 上市版 section_id | 章节编号 |
|------|---------|------------------|------------------|---------|
| 1 | 关联方关系及其交易 | `chapter-11-guan-lian-fang-ji-guan-lian-jiao-yi-guan-lian-jiao-yi-qing-kuang` | `chapter-11-guan-lian-fang-ji-guan-lian-jiao-yi-guan-lian-jiao-yi-qing-kuang` | 十一 |
| 2 | 关联方应收应付款项 | `chapter-11-guan-lian-fang-ji-guan-lian-jiao-yi-guan-lian-fang-ying-shou-ying-fu-kuan-xiang` | `chapter-11-guan-lian-fang-ji-guan-lian-jiao-yi-guan-lian-fang-ying-shou-ying-fu-kuan-xiang` | 十一 |

**关联方一级父章节**：`chapter-11-guan-lian-fang-ji-guan-lian-jiao-yi`（国企版/上市版相同 section_id）。

---

## 2. 模板源盘点

以下为本 spec 语义扩展所依赖的现有模板/配置源，语义 sidecar 从这些文件派生，不直接修改它们。

| 文件路径 | 角色 | 备注 |
|---------|------|------|
| `backend/data/note_template_soe.json` | 国企版单体/通用附注主模板 | 16242 行，含政策条款 + 科目注释 + 关联方 |
| `backend/data/note_template_listed.json` | 上市版单体/通用附注主模板 | 23549 行，含政策条款 + 科目注释 + 关联方 |
| `backend/data/consol_note_sections_soe.json` | 国企版合并附注章节（细粒度表结构） | 子表/行级定义，section_id 格式为 `五-N-M` |
| `backend/data/consol_note_sections_listed.json` | 上市版合并附注章节（细粒度表结构） | 同上，standard=listed |
| `backend/data/note_template_bindings.json` | 附注取数绑定注册表（自动生成版） | 定义 valid_sources/modes/semantics，覆盖账龄/余额/折旧等 |
| `backend/data/note_wp_mapping_rules.json` | 附注章节↔底稿编号映射规则 | 30 条映射，含 wp_codes 和 account_codes |
| `backend/data/note_check_preset_formulas.json` | 预置校验/公式 | 辅助披露平衡规则 |
| `backend/data/note_soe_listed_diff.json` | 国企/上市差异配置 | 辅助模板变体矩阵 |
| `backend/data/multi_standard_note_templates.json` | 多准则模板配置 | 备用参考 |

---

## 3. P0-MVP 约束声明

| 约束项 | 说明 |
|-------|------|
| **不新增数据库表** | 不创建新的 PostgreSQL 表 |
| **不改 `disclosure_notes` 表结构** | 不 ALTER/ADD COLUMN 到 disclosure_notes 表 |
| **扩展方式** | 仅通过 `table_data` JSONB sidecar 字段（`_semantic`、`_tables`、`_policy_clauses`、`_formulas` 扩展）+ 后端 DTO/Schema + 前端展示层 |
| **兼容性** | 保持 `headers[]`、`rows[].values[]`、`_cell_modes`、`_cell_meta`、`_formulas`、`_tables` 既有契约不变 |
| **sidecar 缺失时** | 按旧结构推断，不强制所有章节必须有 sidecar |
| **binding registry** | 初期使用 JSON 配置文件，不入库 |
| **离线模板** | 旧版离线包继续兼容，新版 semantic workbook 通过 `_meta` sheet 标识 |

---

## 4. 试点科目的底稿关联

数据来源于 `note_wp_mapping_rules.json`：

| 科目 | note_section（国企版编号） | 底稿编号 (wp_codes) | 科目编码 (account_codes) |
|------|--------------------------|--------------------|-----------------------|
| 货币资金 | 五、1 | E1-1 | 1001, 1002, 1012 |
| 应收账款 | 五、4 | E4-1 | 1122 |
| 固定资产 | 五、9 | E9-1 | 1601, 1602 |

---

## 5. 合并附注子表参考

`consol_note_sections_soe.json` / `consol_note_sections_listed.json` 为试点科目定义了更细粒度的子表结构：

### 应收账款（parent_seq=5，国企版）

| consol section_id | 子表标题 |
|-------------------|---------|
| 五-5-1 ~ 五-5-11 | 按账龄披露、按坏账准备计提方法分类、单项计提、组合计提、本期计提/收回/转回、实际核销、前五名、金融资产转移等 |

### 货币资金（parent_seq=1，国企版）

| consol section_id | 子表标题 |
|-------------------|---------|
| 五-1-1 | 货币资金明细 |
| 五-1-2 | 受限制的货币资金 |

### 固定资产

位于 `consol_note_sections_*` 的对应 parent_seq 位置，包含原值/折旧/减值明细表。

---

## 6. 语义 section_id 映射（四版本初步建议）

| semantic_section_id | soe_standalone | soe_consolidated | listed_standalone | listed_consolidated |
|--------------------|----------------|------------------|-------------------|---------------------|
| `accounts_receivable` | chapter-08-...-ying-shou-zhang-kuan | 同左 + consol 五-5-* | chapter-05-...-ying-shou-zhang-kuan | 同左 + consol 五-5-* |
| `fixed_assets` | chapter-08-...-gu-ding-zi-chan | 同左 | chapter-05-...-gu-ding-zi-chan | 同左 |
| `cash_and_bank` | chapter-08-...-huo-bi-zi-jin | 同左 + consol 五-1-* | chapter-05-...-huo-bi-zi-jin | 同左 + consol 五-1-* |
| `related_party_transactions` | chapter-11-...-guan-lian-jiao-yi-qing-kuang | 同左 | chapter-11-...-guan-lian-jiao-yi-qing-kuang | 同左 |
| `related_party_receivables_payables` | chapter-11-...-guan-lian-fang-ying-shou-ying-fu-kuan-xiang | 同左 | chapter-11-...-guan-lian-fang-ying-shou-ying-fu-kuan-xiang | 同左 |
| `accounting_policies` | chapter-04-zhong-yao-kuai-ji-zheng-ce-kuai-ji-gu-ji | 同左 | chapter-03-zhong-yao-kuai-ji-zheng-ce-ji-kuai-ji-gu-ji | 同左 |

> 注：`soe_standalone` 与 `soe_consolidated` 使用相同的主模板 section_id（`note_template_soe.json` 中 `scope: "both"`），但合并版可额外引用 `consol_note_sections_soe.json` 中的子表定义。

---

## 7. 选择依据

1. **会计政策**：长文本条款化审阅是本 spec 核心需求（Requirement 1），选两个主流版本的政策章节覆盖国企和上市场景。
2. **应收账款**：子表最多、账龄/坏账/核销/前五名等结构最复杂，适合验证 `table_id/row_id/col_id/row_type` 全套 sidecar。
3. **固定资产**：原值/折旧/减值变动表结构典型，适合验证多表 + 公式取数 + 披露平衡校验。
4. **货币资金**：结构相对简单（明细+受限制），作为最小复杂度基准，验证四维上下文基本流程。
5. **关联方**：不属于普通科目披露，需要跨模块取数（关联方模块/EQCR/函证），适合验证专项披露模型的独立建模。
