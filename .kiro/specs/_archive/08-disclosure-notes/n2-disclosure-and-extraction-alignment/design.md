# Design Document

## Overview

把 N2 应交税费底稿的数据链路从「手工录入 → 手工推送」升级为「四表入库 → 自动预填审定表 → 审定表/明细表数据自动带入披露表 → 自动推送附注」的完整闭环。核心是建立跨层税种名称归一映射，使三层（tb_balance 科目名 / 底稿 taxType / 附注披露 label）一一对应。

## Architecture

```
tb_balance (2221% 叶子)
    │ _classify_tax_type (修正后 → 14 输出键，含 vat 独立键)
    ▼
N2-1 审定表 (N2-1-{key}-audited / N2-1-{key}-opening)
    │ useN2Adjudication14 → N2-1-adjudication-rows (JSON array, taxType field)
    ▼
    ├─→ useN2CrossSheet.adjudicationVsCalcTables (联动校验)
    │
    └─→ useN2DisclosureTables.restoreWithPrefill()
            │ N2_TAX_LABEL_MAP (归一映射表) 
            │ 按 taxType 匹配源模板 13 固定行 → 填入对应列值
            ▼
        披露表 (checklist_responses: N2-disclosure-{variant}-taxes)
            │ buildN2SyncPayload → POST sync-from-workpaper
            ▼
        附注 §五、41 / §八、41 (sub_table_data: {应交税费: [...13行+动态+合计]})
```

## Components and Interfaces

### 1. `N2_TAX_LABEL_MAP`（新建，单一真源）

位置：`composables/n2TaxLabelMap.ts`

```typescript
/**
 * 源模板 13 固定税种的归一映射表（三层共用单一真源）。
 *
 * key = 规范名（`_normalizeTaxNameForN4` 的输出）
 * value.disclosureLabel = 源模板披露表 A 列逐字（附注模板 rows[].label 同源）
 * value.classifyKey = `_classify_tax_type` 后端预填输出键
 * value.sortOrder = 源模板 R 行序（控制默认排序）
 */
export const N2_TAX_LABEL_MAP: Record<string, {
  disclosureLabel: string
  classifyKey: string
  sortOrder: number
}> = {
  '企业所得税':         { disclosureLabel: '企业所得税',          classifyKey: 'cit',           sortOrder: 1 },
  '增值税':            { disclosureLabel: '增值税',             classifyKey: 'vat',           sortOrder: 2 },
  '消费税':            { disclosureLabel: '消费税',             classifyKey: 'consumption',   sortOrder: 3 },
  '资源税':            { disclosureLabel: '资源税',             classifyKey: 'resource',      sortOrder: 4 },
  '土地增值税':         { disclosureLabel: '土地增值税',          classifyKey: 'lvt',           sortOrder: 5 },
  '城市维护建设税':      { disclosureLabel: '城市维护建设税',       classifyKey: 'urban',         sortOrder: 6 },
  '车船牌照税':         { disclosureLabel: '车船牌照税',          classifyKey: 'vehicle',       sortOrder: 7 },
  '房产税':            { disclosureLabel: '房产税',             classifyKey: 'property',      sortOrder: 8 },
  '土地使用税':         { disclosureLabel: '土地使用税',          classifyKey: 'land-use',      sortOrder: 9 },
  '教育费附加':         { disclosureLabel: '教育费附加',          classifyKey: 'education',     sortOrder: 10 },
  '矿产资源补偿费':      { disclosureLabel: '矿产资源补偿费',       classifyKey: 'mineral',       sortOrder: 11 },
  '代扣代缴外国企业所得税': { disclosureLabel: '代扣代缴外国企业所得税',  classifyKey: 'wh-foreign-cit', sortOrder: 12 },
  '代扣代缴个人所得税':    { disclosureLabel: '代扣代缴个人所得税',     classifyKey: 'wh-iit',        sortOrder: 13 },
}

/** 变体名 → 规范名 归一（与 _normalizeTaxNameForN4 保持一致并扩展） */
export function normalizeTaxLabel(raw: string): string { ... }
```

### 2. `_classify_tax_type` 修正（后端）

修改点：
- `"增值税" in name` → 返回 `"vat"`（而非 `"urban"`）
- 新增 `"资源税"` → `"resource"`
- 新增 `"矿产资源补偿费"` / `"矿产资源"` → `"mineral"`
- 新增 `"代扣代缴外国企业所得税"` / `"代扣代缴外国"` → `"wh-foreign-cit"`（必须在 `"企业所得税"` 之前判断，因后者是前者子串）
- 新增 `"代扣代缴个人所得税"` / `"代扣代缴个人"` → `"wh-iit"`（必须在 `"个人所得税"` 之前判断）
- 既有 `"增值税" in name` → `"urban"` 的条件收窄为 `("城市维护建设" in name or "城建" in name)`（已在上方）

顺序敏感总结（从上到下按序判断）：
1. 土地增值税（含「增值税」子串）
2. 城镇土地使用税（含「土地」子串）
3. 城市维护建设税/城建税
4. **增值税**（改为 `vat`）
5. 矿产资源补偿费（含「资源」子串）→ 必须先于资源税
6. 资源税
7. 地方教育附加（含「教育」子串）
8. 教育费附加
9. 代扣代缴外国企业所得税（含「企业所得税」子串）→ 必须先于企业所得税
10. 企业所得税
11. 代扣代缴个人所得税（含「个人所得税」子串）→ 必须先于个人所得税
12. 个人所得税
13. 消费税/印花税/房产税/车船税
14. other

### 3. `useN2DisclosureTables` 扩展：`restoreWithPrefill`

新增从 N2-1/N2-2 自动带入逻辑：
- `restore()` 现有行为不变（从 checklist 恢复自己的持久化数据）
- 新增 `prefillFromAdjudication(adjRows, detailRows)` 纯函数：
  1. 按 `normalizeTaxLabel(row.taxType)` 归一
  2. 逐行匹配源模板 13 固定行
  3. 上市版：`end = _adjRowEndAudited(r)` / `prior = r.beginAudited`
  4. 国企版：从 N2-2 detail 取 `opening = audBegin` / `payable = audPayable` / `paid = audPaid` / `end = computeN2SoeEnd()`
  5. **仅填充值为 null 的格子**（手工优先原则）

### 4. 附注模板幂等脚本

`backend/scripts/fix/fix_note_n2_tax_structure.py`：
- 把 §五、41 rows 从 5 种扩充到 13 种 + 合计（label 逐字取源模板，`row_type: data`）
- 把 §八、41 rows 从 10 种扩充到 13 种 + 合计
- `--dry-run` / `--check` / `--apply`
- `_aligned_by` 更新为 `n2-disclosure-and-extraction-alignment`

## Data Models

### 源模板 13 固定税种行（两版完全一致）

| R行 | label（逐字） | classify key |
|-----|-------------|-------------|
| R8  | 企业所得税 | cit |
| R9  | 增值税 | vat |
| R10 | 消费税 | consumption |
| R11 | 资源税 | resource |
| R12 | 土地增值税 | lvt |
| R13 | 城市维护建设税 | urban |
| R14 | 车船牌照税 | vehicle |
| R15 | 房产税 | property |
| R16 | 土地使用税 | land-use |
| R17 | 教育费附加 | education |
| R18 | 矿产资源补偿费 | mineral |
| R19 | 代扣代缴外国企业所得税 | wh-foreign-cit |
| R20 | 代扣代缴个人所得税 | wh-iit |
| R21~R22 | （预留，可改名） | — |
| R23 | 合  计 | — |

### 税种名称归一规则（`normalizeTaxLabel`）

| 变体名 | 规范名（= 源模板 label） |
|--------|----------------------|
| 未交增值税 | 增值税 |
| 城建税 | 城市维护建设税 |
| 车船税 / 车船使用税 | 车船牌照税 |
| 城镇土地使用税 | 土地使用税 |
| 个人所得税 | 代扣代缴个人所得税 |
| 地方教育附加 | 教育费附加（合并列示） |
| 印花税 | （源模板无固定行，走动态增行或合并到「其他」） |

注意：源模板**没有「印花税」固定行**——它在 N2-2 明细表固定税种里有，但在披露表源模板的 13 行里没有。按源模板口径，印花税如需披露走用户手动增行（R21~R22 预留行）或合并到「其他」。

## Correctness Properties

### Property 1: classify 输出唯一性
**Validates: Requirements 1.1, 1.2, 1.3**

`_classify_tax_type` 的输出键必须与源模板 13 行 + `other` 构成满射（每个源模板行至少有一个 classify 键映射到它）。增值税独占 `vat` 键，不与城建税 `urban` 混。

### Property 2: 行骨架完整性
**Validates: Requirements 2.1, 2.2, 3.1, 3.2**

`N2_LISTED_TAX_ITEMS` / `N2_SOE_TAX_ITEMS` 逐字等于源模板 R8~R20 的 A 列值（13 项），顺序一致。附注模板 rows 逐字等于同一来源。

### Property 3: 带入不覆盖原则
**Validates: Requirements 4.5**

`prefillFromAdjudication` 只填充 `null` 值的格子；非 null 格子（含用户手工输入的 0）不被覆盖。

### Property 4: 推送完整性
**Validates: Requirements 5.1, 5.3, 5.4**

`buildN2SyncPayload` 的 `sub_table_data[应交税费]` 行数 = 源模板固定行（有值的）+ 动态增行 + 合计行。列键逐字对齐附注模板 columns（上市 label/end/prior / 国企 label/opening/payable/paid/end）。

### Property 5: 旧数据兼容
**Validates: Requirements 1.5**

已有 `N2-1-urban-audited` 键值（含混了增值税的城建税余额）不因修正而丢失。前端 `_normalizeTaxNameForN4` 的旧行为（`"增值税" → "增值税"`、`"城建税" → "城建税"`）在读取侧保持不变。写入侧分拆后，新入库数据 key 正确，旧数据按原 key 继续可读。

### Property 6: 公式预设语义一致
**Validates: Requirements 7.1, 7.2**

`prefill_formula_mapping.json` N2 审定表的 5 条公式（TB/ADJ/PREV）语义与 `_build_adjudication_prefill` + `_fetch_tb_data` 的 Python 实现逐条等价。

### Property 7: 勾稽面板覆盖
**Validates: Requirements 5.1**

`runN2ListedChecks` / `runN2SoeChecks` 在 13 行骨架下仍正确计算合计 ↔ 各行勾稽。
