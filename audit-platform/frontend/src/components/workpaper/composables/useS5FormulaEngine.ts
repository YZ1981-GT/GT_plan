/**
 * useS5FormulaEngine — S5 债务重组公式引擎
 *
 * 纯函数，无副作用、无 Vue reactivity、确定性输出。
 *
 * 本引擎覆盖：
 * - 债权人重组损益 calcCreditorGainLoss（源模板公式 =D8-E8+F8）
 * - 债务人重组损益 calcDebtorGainLoss（源模板公式 =C16-E16-F16-G16）
 *
 * 源模板公式：
 * - 债权人: =D8-E8+F8 → origBook - origFair + recvFair
 *   D8 = 原账面价值 (origBook)
 *   E8 = 公允价值 (origFair)
 *   F8 = 受让成本/受让资产公允价值 (recvFair)
 * - 债务人: =C16-E16-F16-G16 → debtBook - assetBook - equityFair
 *   C16 = 所清偿债务账面价值 (debtBook)
 *   E16 = 转让金融资产账面价值 \
 *   F16 = 转让非金融资产账面价值 / → 合并为 assetBook
 *   G16 = 权益工具公允价值 (equityFair)
 *
 * Spec: .kiro/specs/s-special-transaction-workpapers/ Task 3.2
 * Requirements: 3.2
 */

// ─── helpers ────────────────────────────────────────────────

/** 安全数值解析：null/undefined/NaN/空→0 */
export function parseNum(val: string | number | null | undefined): number {
  if (val === null || val === undefined || val === '') return 0
  const n = typeof val === 'number' ? val : Number(val)
  return Number.isFinite(n) ? n : 0
}

// ─── interfaces ─────────────────────────────────────────────

export interface CreditorInput {
  origBook: number   // 债权原账面价值 (原账面)
  origFair: number   // 债权原公允价值
  recvFair: number   // 收到资产(金融资产)公允价值
  otherCost: number  // 可直接归属于受让资产的其他成本
}

export interface DebtorInput {
  debtBook: number    // 所清偿债务账面价值
  assetBook: number   // 转让资产账面价值 (金融+非金融资产账面)
  equityFair: number  // 发行的权益工具公允价值
}

// ─── 1. 债权人重组损益（Property P4） ────────────────────────

/**
 * 计算债权人重组损益
 *
 * 源模板公式: =D8-E8+F8
 * 即: origBook - origFair + recvFair
 *
 * 含义：
 * - 债权原账面价值 减去 债权原公允价值 加上 受让资产公允价值
 * - 结果为正=重组收益，结果为负=重组损失
 *
 * 来源：审定表S5-1 债权人视角
 *
 * @param input - CreditorInput
 * @returns 债权人重组损益
 */
export function calcCreditorGainLoss(input: CreditorInput): number {
  const origBook = parseNum(input.origBook)
  const origFair = parseNum(input.origFair)
  const recvFair = parseNum(input.recvFair)

  return origBook - origFair + recvFair
}

// ─── 2. 债务人重组损益（Property P4） ────────────────────────

/**
 * 计算债务人重组损益
 *
 * 源模板公式: =C16-E16-F16-G16
 * 即: debtBook - assetBook - equityFair
 * （设计层面将 E16+F16 合并为 assetBook）
 *
 * 含义：
 * - 所清偿债务账面价值 减去 转让资产账面价值 减去 权益工具公允价值
 * - 结果为正=重组收益（债务人获益），结果为负=重组损失
 *
 * 来源：审定表S5-1 债务人视角
 *
 * @param input - DebtorInput
 * @returns 债务人重组损益
 */
export function calcDebtorGainLoss(input: DebtorInput): number {
  const debtBook = parseNum(input.debtBook)
  const assetBook = parseNum(input.assetBook)
  const equityFair = parseNum(input.equityFair)

  return debtBook - assetBook - equityFair
}
