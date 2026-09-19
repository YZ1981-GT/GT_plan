/**
 * E1 披露主表「无科目码行」的语义槽预填（纯函数，零 Vue 依赖）。
 *
 * ## 背景：三处「注释承诺了但零实现」
 *
 * `e1DisclosureScope.E1_MAIN_ROWS_LISTED` 里三行 `crossKey === ''`：
 *
 * | 行 key        | 源 xlsx | 注释原文 |
 * |---------------|---------|----------|
 * | `finance_co`  | A10     | 准则解释 15 号「可在货币资金项目之下增设」→ 无一级标准科目 |
 * | `accrued`     | A12     | 存款应计利息 —— 无一级标准科目 |
 * | `digital`     | A13     | 准则解释 15 号「可增设二级科目」→ 无一级标准科目 |
 *
 * 三行原本「由审计师手工填**或由 render 的语义槽预填**」，而预填侧一直没有实现
 * ⇒ 附注主表这三行恒空（比明细表更直接影响交付件）。本模块补上这条链。
 *
 * ## 🔴 双算风险与扣减映射（本模块最关键的设计判断）
 *
 * 审定表 `useE1Adjudication.aggregateAuditedByCode()` 的三科目口径：
 *
 * - `1001` = `cash`
 * - `1002` = **`bank_principal` 全额**（`ROW_MATRIX` 里 `finance_co` 是它的「其中：」子项）
 * - `1012` = `other_mf` + **`digital`**
 *
 * 而附注 docx 主表把「存放财务公司款项」「数字货币」写成**与银行存款/其他货币资金
 * 平行的列示行**（8 行里只有 `overseas` 带「其中：」前缀）⇒ 若直接给这两行填上槽值，
 * 合计会**双算**（1002 里已含 finance_co、1012 里已含 digital）。
 *
 * 处置 = **扣减而非标 memo**：
 *
 * | 披露行 | 金额 | 依据 |
 * |--------|------|------|
 * | `bank` | `TB(1002) − slot(finance_co)` | 准则解释 15 号要求财务公司款项单独列示 ⇒ 银行存款行应为「银行机构存款」 |
 * | `finance_co` | `slot(finance_co)` | 单独列示行 |
 * | `other_mf` | `TB(1012) − slot(digital)` | 数字货币单独列示 ⇒ 其他货币资金行不含它 |
 * | `digital` | `slot(digital)` | 单独列示行 |
 * | `accrued` | `slot(accrued)` | **不属任何科目码** ⇒ 加它是修正（旧合计漏了应计利息）|
 *
 * 合计恒等式：`1001 + (1002−fc) + fc + (1012−dg) + dg + accrued = 1001+1002+1012+accrued`。
 *
 * 🔴 **不标 `isMemo`** —— memo 语义是「其中：」子项，而 docx 这两行不带该前缀；
 * 标了会让底稿 UI 与交付件的列示层级分叉（且要动 `e1DisclosureScope` 刚被诚实改写的断言）。
 *
 * 🔴 **零回归支点**：全库 8 项目 `finance_co` / `digital` 两槽 `found=False`（`account_chart`
 * 对「数字货币 / 数字人民币 / 财务公司」0 命中）⇒ 槽键不存在 ⇒ 扣减额为 0 ⇒
 * `bank`/`other_mf` 取值与改造前**逐字节相同**，`fc`/`dg` 显示空白。
 *
 * ## 取数来源
 *
 * 值由审定表 `syncAuditedTotals()` additive 写进 `allResponses`（与既有
 * `E1-adj-total-{code}` 完全同构的机制），本模块只定义键名与读写契约。
 *
 * 🔴 **不在本模块复现审定表的取数逻辑** —— 应计利息四子项汇总口径
 * （`accruedTotalValues`：E1-20 明细行非空则按 category 汇总、否则读手工未审数）
 * 已在 `useE1Adjudication` 里，复现一份即双真源。
 *
 * ## persist-first 与「不写 0」
 *
 * - 审定表侧：该行未审/调整/审定三值全为 0 ⇒ **不写该键**（保持空白而非 0）
 * - 披露表侧：`crossKey` 优先 → 槽键 → 都无则 `null`（**不是 0**，两态必须可区分）
 * - 期初列手工覆盖（`openingMap` 显式含该 key）优先级不变
 *
 * ## soe 无落点
 *
 * soe docx 主表只 6 行，**没有** `finance_co` 与 `accrued`（准则口径差异，见
 * `e1DisclosureScope` 文件头表格）⇒ 预填只作用于 listed 变体；soe 的 `digital`
 * 虽在行集里但 `crossKey` 亦为空，同样走槽键（该槽恒空）。soe 的 `other_mf`
 * 走同一条扣减映射（`digital` 槽为空时扣减为 0，行为不变）。
 */

/** 披露主表行 key → 审定表 `ROW_MATRIX.itemKey`（口径真源在审定表侧）。 */
export const E1_MAIN_ROW_SLOTS: Readonly<Record<string, string>> = Object.freeze({
  finance_co: 'finance_co',
  accrued: 'accrued_interest',
  digital: 'digital',
})

/** 参与槽预填的披露行 key（字典序固定，供守卫冻结）。 */
export const E1_PREFILL_ROW_KEYS: readonly string[] = Object.freeze([
  'accrued',
  'digital',
  'finance_co',
])

/**
 * 扣减映射：`披露行 key` → 需从其 `crossKey` 金额中扣除的槽行 key。
 *
 * 存在的唯一理由是避免双算（见文件头表格）。**改它必须同时核对
 * `useE1Adjudication.aggregateAuditedByCode()` 的科目归集口径**。
 */
export const E1_MAIN_ROW_DEDUCTIONS: Readonly<Record<string, readonly string[]>> =
  Object.freeze({
    bank: Object.freeze(['finance_co']),
    other_mf: Object.freeze(['digital']),
  })

/**
 * 槽键构造（唯一入口）。
 *
 * @param rowKey 披露主表行 key（`finance_co` / `accrued` / `digital`）
 * @param period `'ending'`（默认，期末审定数）或 `'opening'`（期初审定数）
 * @returns 形如 `E1-adj-slot-finance_co` / `E1-adj-slot-finance_co-opening`；
 *   非预填行返回 `''`（调用方据此跳过）
 */
export function e1MainRowSlotKey(
  rowKey: string,
  period: 'ending' | 'opening' = 'ending',
): string {
  if (!(rowKey in E1_MAIN_ROW_SLOTS)) return ''
  const base = `E1-adj-slot-${rowKey}`
  return period === 'opening' ? `${base}-opening` : base
}

function num(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

/** 审定表行的最小形状（只取本模块需要的字段）。 */
export interface E1AdjRowLike {
  itemKey: string
  openingUnaudited: number
  openingAdjustment: number
  openingAudited: number
  endingUnaudited: number
  endingAdjustment: number
  endingAudited: number
}

function isBlankPeriod(row: E1AdjRowLike, period: 'ending' | 'opening'): boolean {
  const trio =
    period === 'opening'
      ? [row.openingUnaudited, row.openingAdjustment, row.openingAudited]
      : [row.endingUnaudited, row.endingAdjustment, row.endingAudited]
  return trio.every((v) => num(v) === 0)
}

/**
 * 由审定表行产出槽键写入计划（供 `useE1Adjudication.syncAuditedTotals()` 调用）。
 *
 * 🔴 「三值全 0 ⇒ 不写该键」是 Property 35「槽 found=False 时保持空白而不写 0」的落地：
 * 语义槽 `found=False` 时审定表该行未审数取不到值 ⇒ 三值全 0 ⇒ 不写 ⇒ 披露表读不到 ⇒ 空白。
 * 若无条件写 0，「本项目无此科目」与「余额确实为 0」就不可区分。
 *
 * @returns `[{ itemId, value }]`，值为字符串（与 `E1-adj-total-*` 同款）
 */
export function buildE1MainRowSlotWrites(
  rows: readonly E1AdjRowLike[],
): Array<{ itemId: string; value: string }> {
  const byItemKey = new Map<string, E1AdjRowLike>()
  for (const r of rows) byItemKey.set(r.itemKey, r)

  const out: Array<{ itemId: string; value: string }> = []
  for (const rowKey of E1_PREFILL_ROW_KEYS) {
    const row = byItemKey.get(E1_MAIN_ROW_SLOTS[rowKey])
    if (!row) continue
    for (const period of ['ending', 'opening'] as const) {
      if (isBlankPeriod(row, period)) continue
      const value = period === 'opening' ? num(row.openingAudited) : num(row.endingAudited)
      out.push({ itemId: e1MainRowSlotKey(rowKey, period), value: String(value) })
    }
  }
  return out
}

/** 披露主表行的最小形状。 */
export interface E1MainRowKeyed {
  key: string
  crossKey: string
}

/** `allResponses.get(key)?.remark` 的读取器。 */
export type E1RemarkGetter = (key: string) => string | null | undefined

function readNumber(get: E1RemarkGetter, key: string): number | null {
  if (!key) return null
  const raw = get(key)
  if (raw === null || raw === undefined || raw === '') return null
  const n = Number(raw)
  return Number.isFinite(n) ? n : null
}

/**
 * 解析披露主表某行某期的**主**取数键（`crossKey` 优先 → 槽键 → `''`）。
 *
 * 分离出来是为了让守卫能不挂载组件就断言优先级，且让「加一个预填行」只需改
 * `E1_MAIN_ROW_SLOTS` 一处。
 */
export function e1MainRowAmountKey(
  row: E1MainRowKeyed,
  period: 'ending' | 'opening' = 'ending',
): string {
  if (row.crossKey) {
    return period === 'opening' ? `${row.crossKey}-opening` : row.crossKey
  }
  return e1MainRowSlotKey(row.key, period)
}

/** 该行本期需扣减的槽键清单（无扣减时为空数组）。 */
export function e1MainRowDeductionKeys(
  row: E1MainRowKeyed,
  period: 'ending' | 'opening' = 'ending',
): string[] {
  if (!row.crossKey) return []
  const slots = E1_MAIN_ROW_DEDUCTIONS[row.key]
  if (!slots || !slots.length) return []
  return slots.map((s) => e1MainRowSlotKey(s, period)).filter(Boolean)
}

/**
 * 读取披露主表某行某期金额（含扣减）。
 *
 * @returns 数值；**主键取不到值时返 `null`**（不是 0）——「无此科目」与「余额为 0」
 *   必须可区分。扣减槽取不到值时按 0 扣（缺该槽 ⇒ 不需要扣）
 */
export function resolveE1MainRowAmount(
  row: E1MainRowKeyed,
  get: E1RemarkGetter,
  period: 'ending' | 'opening' = 'ending',
): number | null {
  const base = readNumber(get, e1MainRowAmountKey(row, period))
  if (base === null) return null
  let deducted = base
  for (const k of e1MainRowDeductionKeys(row, period)) {
    deducted -= readNumber(get, k) ?? 0
  }
  return deducted
}

/** 该行本期是否由槽预填而来（供 UI 打「预填」标记）。 */
export function isE1MainRowSlotPrefilled(
  row: E1MainRowKeyed,
  get: E1RemarkGetter,
  period: 'ending' | 'opening' = 'ending',
): boolean {
  if (row.crossKey) return false
  return readNumber(get, e1MainRowSlotKey(row.key, period)) !== null
}

/** 该行本期金额是否被扣减过（供 UI tooltip 说明「已扣除单独列示项」）。 */
export function isE1MainRowDeducted(
  row: E1MainRowKeyed,
  get: E1RemarkGetter,
  period: 'ending' | 'opening' = 'ending',
): boolean {
  return e1MainRowDeductionKeys(row, period).some(
    (k) => readNumber(get, k) !== null,
  )
}
