/**
 * n1LossMigration — 纯函数：迁移旧版 N1-5 亏损行到新模型
 *
 * Spec: .kiro/specs/n1-loss-check-source-alignment/
 * Task: 2.2
 * Requirements: 6.1, 6.2, 6.3, 6.4
 *
 * 映射规则（design «迁移纯函数»）：
 * - expiryYear = lossYear + maxYears
 * - bookAmount = max(0, lossAmount - recoveredBegin - currentRecovery)
 * - auditAdjustment = 0
 * - recognizedAmount = isExpired ? 0 : min(bookAmount, futureTaxableIncome)
 * - basis = recognitionBasis
 * - taxRate = taxRate || 0.25
 * - lossYear 保留
 *
 * 不猜测字段（Property 8）：
 * - priorUnrecognized = 0
 * - sufficient = ''
 * - sourceOperating / sourceTemporaryDiff / sourceOther = false
 * - indexRef = ''
 *
 * 幂等性（Property 7）：
 * - 按 expiryYear 去重：existing 已含该年度 → skip
 */
import type { N1LossRow, N1LossSufficiency } from './useN1LossCheck'

// ─── Legacy Row Type ─────────────────────────────────────────────────────────

/**
 * 旧版亏损行结构（存储于 N1-5-loss-rows，只读不删）
 */
export interface LegacyLossRow {
  lossYear?: number | string | null
  maxYears?: number | string | null
  lossAmount?: number | string | null
  recoveredBegin?: number | string | null
  currentRecovery?: number | string | null
  futureTaxableIncome?: number | string | null
  taxRate?: number | string | null
  recognitionBasis?: string | null
  [key: string]: unknown
}

// ─── Migration Result ────────────────────────────────────────────────────────

export interface MigrationResult {
  rows: N1LossRow[]
  added: number
  skipped: number
}

// ─── Legacy Info ─────────────────────────────────────────────────────────────

export interface LegacyInfo {
  count: number
  canImport: boolean
}

// ─── ID Generator (deterministic for testing when seed provided) ─────────────

let _migrationIdSeq = 0

/**
 * Reset migration id sequence (for testing determinism)
 */
export function _resetMigrationIdSeq(start = 0): void {
  _migrationIdSeq = start
}

function _genMigrationId(): string {
  return `loss-${++_migrationIdSeq}`
}

// ─── Pure Functions ──────────────────────────────────────────────────────────

/**
 * 从旧版亏损行迁移到新模型。纯函数，可独立单测。
 *
 * - 按 expiryYear 去重保证幂等（Property 7）
 * - 未知项留空不猜测（Property 8）
 * - 旧键 N1-5-loss-rows 只读不删（Req 6.4）
 *
 * @param legacy - 旧版亏损行（readonly，不修改源数据）
 * @param auditYear - 审计年度（用于判断是否届满）
 * @param existing - 已有的新模型行（用于去重）
 */
export function migrateLegacyLossRows(
  legacy: readonly LegacyLossRow[],
  auditYear: number,
  existing: readonly N1LossRow[] = [],
): MigrationResult {
  const existingYears = new Set(existing.map((r) => r.expiryYear))
  const newRows: N1LossRow[] = [...existing] as N1LossRow[]
  let added = 0
  let skipped = 0

  for (const row of legacy) {
    const lossYear = Number(row.lossYear) || 0
    const maxYears = Number(row.maxYears) || 5
    const expiryYear = lossYear + maxYears

    // Idempotent: skip if expiryYear already in existing (Property 7)
    if (existingYears.has(expiryYear)) {
      skipped++
      continue
    }

    const lossAmount = Number(row.lossAmount) || 0
    const recoveredBegin = Number(row.recoveredBegin) || 0
    const currentRecovery = Number(row.currentRecovery) || 0
    const bookAmount = Math.max(0, lossAmount - recoveredBegin - currentRecovery)
    const isExpired = expiryYear < auditYear
    const futureTaxableIncome = Number(row.futureTaxableIncome) || 0
    const taxRate = Number(row.taxRate) || 0.25

    const newRow: N1LossRow = {
      id: _genMigrationId(),
      expiryYear,
      lossYear: lossYear || null,
      // Property 8: priorUnrecognized = 0 (不猜测)
      priorUnrecognized: 0,
      bookAmount,
      // Property 8: auditAdjustment = 0 (不猜测)
      auditAdjustment: 0,
      recognizedAmount: isExpired ? 0 : Math.min(bookAmount, futureTaxableIncome),
      taxRate,
      basis: row.recognitionBasis || '',
      // Property 8: sufficient = '' (不猜测)
      sufficient: '' as N1LossSufficiency,
      // Property 8: 来源三选 = false (不猜测)
      sourceOperating: false,
      sourceTemporaryDiff: false,
      sourceOther: false,
      // Property 8: indexRef = '' (不猜测)
      indexRef: '',
    }

    newRows.push(newRow)
    existingYears.add(expiryYear)
    added++
  }

  return { rows: newRows, added, skipped }
}

/**
 * 计算旧版数据检测信息（legacyInfo computed 的纯函数实现）。
 *
 * - 新键为空且旧键有行时 canImport = true
 * - 旧键 JSON 损坏时 canImport = false
 * - 旧键 N1-5-loss-rows 只读不删（Req 6.4）
 *
 * @param newRowCount - 新模型行数（N1-5-rows 解析后的行数）
 * @param legacyEntry - allResponses.get('N1-5-loss-rows') 的原始值
 */
export function computeLegacyInfo(newRowCount: number, legacyEntry: unknown): LegacyInfo {
  // New key has data → no import needed
  if (newRowCount > 0) return { count: 0, canImport: false }

  if (!legacyEntry) return { count: 0, canImport: false }

  // Try to parse legacy JSON
  const str = typeof legacyEntry === 'string' ? legacyEntry : (legacyEntry as any)?.conclusion
  if (!str || typeof str !== 'string') return { count: 0, canImport: false }

  try {
    const parsed = JSON.parse(str)
    if (!Array.isArray(parsed)) return { count: 0, canImport: false }
    return { count: parsed.length, canImport: parsed.length > 0 }
  } catch {
    // 旧键 JSON 损坏时 canImport = false (Error Handling: 迁移时旧键 JSON 损坏)
    return { count: 0, canImport: false }
  }
}
