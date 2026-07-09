/**
 * useM1DividendEngine — M1 股利测算引擎
 *
 * 纯函数，无副作用、无 Vue reactivity、确定性输出。
 *
 * 对应：应付股利(利润)测算表M1-5（29×14，21 calc公式）
 * 科目：2232 应付股利（贷方/负债类）
 *
 * 本引擎覆盖：
 * - P5: 应宣告股利 = 可供分配利润 × 分配比例（xlsx: M1-5 D=B*C）
 * - 宣告差异 = 测算宣告 - 账面宣告（xlsx: M1-5 F=D-E）
 *
 * 列名映射（xlsx列名权威）：
 * | xlsx列名           | 变量名           | 列位 | 备注                |
 * |-------------------|-----------------|------|-------------------|
 * | 股东会决议分配基数   | profit          | B列  | 来自M6利润分配      |
 * | 分配比例           | ratio           | C列  | 用户输入           |
 * | 分配额            | declaredDividend | D列  | 计算值             |
 * | 实际分配额         | booked          | E列  | 用户输入/账面宣告   |
 * | 差异              | declareDiff     | F列  | 计算值             |
 *
 * M6联动：M1-5的B列"股东会决议分配基数"来源于M6利润分配方案
 * （系统实现通过EventBus订阅 'm6:profit-distributed' 事件接收）
 *
 * Spec: .kiro/specs/m1-dividends-payable/ Task 2.2
 * Requirements: 5.3-5.4, 7.3-7.4
 */

// ─── helpers ────────────────────────────────────────────────

/** 将 NaN / undefined / null 视为 0 */
function safe(v: unknown): number {
  if (v === null || v === undefined) return 0
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

// ─── P5: 应宣告股利 ─────────────────────────────────────────

/**
 * 计算应宣告股利（Property P5）
 *
 * 应宣告股利 = 可供分配利润 × 分配比例
 *
 * 来源：M1-5 应付股利(利润)测算表
 * xlsx公式：D10=B10*C10 ... D17=B17*C17
 *
 * @param profit - 股东会决议分配基数/可供分配利润（B列，来自M6）
 * @param ratio - 分配比例（C列）
 * @returns 分配额/应宣告股利（D列）
 */
export function calcDeclaredDividend(profit: number, ratio: number): number {
  return safe(profit) * safe(ratio)
}

// ─── 宣告差异 ───────────────────────────────────────────────

/**
 * 计算宣告差异
 *
 * 宣告差异 = 测算宣告(分配额) - 账面宣告(实际分配额)
 *
 * 来源：M1-5 应付股利(利润)测算表
 * xlsx公式：F10=D10-E10 ... F17=D17-E17
 *
 * 正值=应宣告大于实际宣告（少分配）
 * 负值=应宣告小于实际宣告（多分配）
 *
 * @param estimated - 测算宣告/分配额（D列，计算值）
 * @param booked - 账面宣告/实际分配额（E列，用户输入）
 * @returns 宣告差异（F列）
 */
export function calcDeclareDiff(estimated: number, booked: number): number {
  return safe(estimated) - safe(booked)
}
