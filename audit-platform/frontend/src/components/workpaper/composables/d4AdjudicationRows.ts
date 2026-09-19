/**
 * D4-1 审定表动态行 —— D4 营业收入的规格声明（薄壳）。
 *
 * 逻辑一律委托平台级共享件 `shared/dynamicAdjudicationRows.ts`，本文件只放
 * **D4 专属声明**：持久化前缀、历史固定行（无）、金额字段集。
 *
 * **为什么 D4-1 必须是动态行**
 *
 * 源模板 `D4-1至D4-4 营业收入 - 审定表明细表（Leap-常规程序）.xlsx` 的 D4-1
 * 主营/其他两段各为 **4 行空白可扩行**（R8:R11 / R14:R17）；9 个在册项目均存在
 * 业务板块级子科目（批发/零售/物流/物业与租赁/医疗/服务费及其他）。
 * 原「无干净 TB→审定表明细行映射」的结论已被推翻（推翻依据：实证 + 源模板可扩行）。
 *
 * D4 是**收入类**循环 —— 金额来自贷方单侧发生额（`credit`），无期初/期末余额概念。
 * `valueFields` 含 `currentUnadjusted`（本期未审数）和 `priorUnadjusted`（上期未审数），
 * 与后端 `build_d4_adjudication_prefill` 输出的 `opening_balance`/`closing_balance`
 * 分别对应上期/本期发生额。
 *
 * spec: .kiro/specs/d4-four-table-extraction-and-disclosure-alignment/ Task 4.2
 *       Requirements 3.2, 3.4, 3.5
 */
import type { DynamicRowsSpec, LegacyFixedRow } from './shared/dynamicAdjudicationRows'

/** 持久化键前缀 */
export const D4_ADJ_PREFIX = 'D4-1'

/**
 * 金额字段集 —— 用于「该历史行是否有数据」判定 + 合计口径。
 *
 * D4 是损益类：
 * - `currentUnadjusted` = 本期未审数（贷方发生额）
 * - `priorUnadjusted` = 上期未审数
 * - `currentAje` / `currentRje` = 本期账项/重分类调整
 * - `priorAje` / `priorRje` = 上期调整
 */
export const D4_ADJ_VALUE_FIELDS = [
  'currentUnadjusted',
  'priorUnadjusted',
  'currentAje',
  'currentRje',
  'priorAje',
  'priorRje',
] as const

/**
 * 历史固定行（迁移源）。
 *
 * D4 原实现使用 `D4-1-adj-rows` JSON 序列化整行（含 `sectionKey` 等），
 * 不是 per-field 独立键模式 —— 迁移时按旧 JSON 中每行的 `rowKey` 作为 `rowId` 沿用。
 *
 * 由于 D4 旧模型是按 crossSheet 动态生成行（非固定枚举），这里传空数组：
 * 有数据时走 JSON 反序列化、无数据时由四表预填建行。
 */
export const D4_LEGACY_ROWS: readonly LegacyFixedRow[] = []

/** D4-1 动态行规格（传给共享件的唯一入参） */
export const D4_ADJ_ROWS_SPEC: DynamicRowsSpec = {
  prefix: D4_ADJ_PREFIX,
  legacyRows: D4_LEGACY_ROWS,
  valueFields: [...D4_ADJ_VALUE_FIELDS],
}
