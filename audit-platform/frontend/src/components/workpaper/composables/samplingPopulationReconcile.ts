/**
 * 总体完整性核对 — 纯函数模块
 *
 * spec: voucher-sampling-reconcile-balance-source
 * Task 4
 *
 * 消费后端 `voucher-extract` 响应中的核对字段，提供：
 * - `parseReconcileInfo`：响应 → PopulationReconcileInfo（含逐方向金额 + 向后兼容旧响应）
 * - `resolvePopulationReconcile`：手工优先 → 自动逐方向 → null
 * - `describeReconcileIssue`：门控原因文案
 * - `reconcilePresetsFor`：预置理由（仅未执行核对时提供）
 * - `formatMovementPair`：「借 x / 贷 y 元」展示
 */

import Decimal from 'decimal.js'

// ─── 类型 ─────────────────────────────────────────────────────────────────────

/** 后端响应解析后的核对信息。 */
export interface PopulationReconcileInfo {
  available: boolean
  /** |借| + |贷|（向后兼容旧前端的单值核对入口） */
  bookAmount: string | null
  basis: string | null
  /** 不可用时的中文原因 */
  unavailableReason: string | null
  // 逐方向字段（新后端才有；旧后端为 null）
  ledgerDebit: string | null
  ledgerCredit: string | null
  bookDebit: string | null
  bookCredit: string | null
  /** 是否使用了科目映射反查企业原始编码（新后端才有；旧后端默认 false） */
  mappingUsed: boolean
}

/** 单方向核对结果。 */
export interface DirectionResult {
  label: string
  ledger: string
  book: string
  diff: string
  withinThreshold: boolean
}

/** 总体核对结果。 */
export interface PopulationReconcileResult {
  /** 是否全部方向都在阈值内 */
  withinThreshold: boolean
  /** 逐方向明细（有逐方向数据时 2 条；回落单值时 1 条） */
  directions: DirectionResult[]
  /** 核对模式：'directional'（逐方向）| 'single'（旧响应回落）| 'manual'（手工录入） */
  mode: 'directional' | 'single' | 'manual'
}

// ─── 内部工具 ──────────────────────────────────────────────────────────────────

function toD(v: string | number | null | undefined): Decimal {
  try {
    const d = new Decimal(v ?? 0)
    return d.isFinite() ? d : new Decimal(0)
  } catch {
    return new Decimal(0)
  }
}

function fmt2(d: Decimal): string {
  return d.toFixed(2, Decimal.ROUND_HALF_EVEN)
}

/**
 * 手工录入金额归一：去千分位（半角/全角逗号）、空白、末尾「元」后解析。
 *
 * 🔴 不归一时 `1,912,193,756.05` 会被 Decimal 拒绝、按 0 参与比对 ⇒ 恒判「不符」。
 * 无法识别返回 null（调用方据此提示用户，而不是当 0 用）。
 */
export function parseAmountInput(raw: string | null | undefined): string | null {
  if (raw == null) return null
  const cleaned = String(raw).replace(/[,，\s]/g, '').replace(/元$/, '')
  if (!cleaned) return null
  if (!/^[+-]?(\d+(\.\d*)?|\.\d+)$/.test(cleaned)) return null
  try {
    const d = new Decimal(cleaned)
    return d.isFinite() ? d.toString() : null
  } catch {
    return null
  }
}

function fmtAmount(v: string | null): string {
  if (v == null) return '-'
  const n = toD(v)
  return n.toNumber().toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

/** 单方向判定：|序时账 − 账面| ≤ |账面| × 阈值比例。 */
function checkDirection(
  label: string,
  ledger: string | null,
  book: string | null,
  thresholdPct: number,
): DirectionResult {
  const l = toD(ledger)
  const b = toD(book)
  const diff = l.minus(b).abs()
  const threshold = b.abs().times(toD(thresholdPct))
  return {
    label,
    ledger: fmt2(l),
    book: fmt2(b),
    diff: fmt2(diff),
    withinThreshold: diff.lte(threshold),
  }
}

// ─── parseReconcileInfo ──────────────────────────────────────────────────────

/**
 * 从后端 `stats` 对象解析核对信息。
 *
 * 向后兼容：旧后端无逐方向字段时，逐方向值为 null，`resolvePopulationReconcile` 会回落单值。
 */
export function parseReconcileInfo(stats: Record<string, any> | null): PopulationReconcileInfo | null {
  if (!stats) return null
  return {
    available: stats.reconcile_available === true,
    bookAmount: stats.book_amount != null ? String(stats.book_amount) : null,
    basis: stats.reconcile_basis ?? null,
    unavailableReason: stats.reconcile_unavailable_reason ?? null,
    ledgerDebit: stats.reconcile_ledger_debit != null ? String(stats.reconcile_ledger_debit) : null,
    ledgerCredit: stats.reconcile_ledger_credit != null ? String(stats.reconcile_ledger_credit) : null,
    bookDebit: stats.reconcile_book_debit != null ? String(stats.reconcile_book_debit) : null,
    bookCredit: stats.reconcile_book_credit != null ? String(stats.reconcile_book_credit) : null,
    mappingUsed: stats.reconcile_mapping_used === true,
  }
}

// ─── resolvePopulationReconcile ──────────────────────────────────────────────

export interface ReconcileResolveOpts {
  info: PopulationReconcileInfo | null
  /** 审计师手工录入的账面金额（借+贷合计口径） */
  manualBook: string | null
  /** 抽样总体金额（GREATEST 合计，用于手工录入回落） */
  populationAmount: string
  thresholdPct: number
}

/**
 * 解析核对结果。优先级：手工录入 → 自动逐方向 → 自动单值回落 → null（未执行核对）。
 */
export function resolvePopulationReconcile(opts: ReconcileResolveOpts): PopulationReconcileResult | null {
  const { info, manualBook, populationAmount, thresholdPct } = opts

  // 1. 手工录入优先（与序时账借+贷发生额合计比对）；格式无法识别时不参与比对（由界面提示）
  const manual = parseAmountInput(manualBook)
  if (manual != null) {
    // 序时账侧用逐方向之和（如有），否则用总体金额
    let ledgerTotal: string
    if (info?.ledgerDebit != null && info?.ledgerCredit != null) {
      ledgerTotal = fmt2(toD(info.ledgerDebit).abs().plus(toD(info.ledgerCredit).abs()))
    } else {
      ledgerTotal = populationAmount
    }
    const dir = checkDirection('借+贷发生额合计', ledgerTotal, manual, thresholdPct)
    return {
      withinThreshold: dir.withinThreshold,
      directions: [dir],
      mode: 'manual',
    }
  }

  // 2. 自动核对 — 逐方向（新后端）
  if (info?.available && info.ledgerDebit != null && info.ledgerCredit != null
    && info.bookDebit != null && info.bookCredit != null) {
    const debitDir = checkDirection('借方发生额', info.ledgerDebit, info.bookDebit, thresholdPct)
    const creditDir = checkDirection('贷方发生额', info.ledgerCredit, info.bookCredit, thresholdPct)
    return {
      withinThreshold: debitDir.withinThreshold && creditDir.withinThreshold,
      directions: [debitDir, creditDir],
      mode: 'directional',
    }
  }

  // 3. 自动核对 — 旧后端回落（只有 bookAmount）
  if (info?.available && info.bookAmount != null) {
    const dir = checkDirection('账面金额', populationAmount, info.bookAmount, thresholdPct)
    return {
      withinThreshold: dir.withinThreshold,
      directions: [dir],
      mode: 'single',
    }
  }

  // 4. 未执行核对
  return null
}

// ─── describeReconcileIssue ─────────────────────────────────────────────────

/**
 * 生成 R5 门控原因文案。
 *
 * - 未执行核对：带不可用原因
 * - 不符：带逐方向差异
 * - 一致：返回 null
 */
export function describeReconcileIssue(
  result: PopulationReconcileResult | null,
  info: PopulationReconcileInfo | null,
  thresholdPct: number,
): string | null {
  if (result == null) {
    // 未执行核对
    const reason = info?.unavailableReason || '无独立账面来源且未手工录入账面金额'
    return `未执行总体完整性核对：${reason}，无法确认样本取自完整总体`
  }

  if (result.withinThreshold) return null

  // 不符 — 列出每个不符的方向
  const pctLabel = `${(thresholdPct * 100).toFixed(0)}%`
  const failedDirs = result.directions.filter(d => !d.withinThreshold)
  const details = failedDirs.map(d =>
    `${d.label}：序时账 ${fmtAmount(d.ledger)} 元 vs 账面 ${fmtAmount(d.book)} 元，差异 ${fmtAmount(d.diff)} 元`,
  ).join('；')
  return `总体完整性核对不符（超出可容忍差异 ${pctLabel}）：${details}`
}

// ─── reconcilePresetsFor ─────────────────────────────────────────────────────

// 与改造前引擎内的 RECONCILE_PRESETS 逐字一致（三条，顺序不变）
const _PRESETS_UNAVAILABLE: readonly string[] = [
  '该科目无独立明细表，已与总账另行核对一致，确认抽样总体完整',
  '已与科目余额表核对一致，序时账总体金额与账面无差异',
  '本科目审定表已独立编制，抽样总体取自同一数据源，不再重复核对',
]

/**
 * 预置放行理由。
 *
 * - 未执行核对（result === null）：给预置理由（减少输入摩擦）
 * - 不符（result.withinThreshold === false）：不给「已与XXX核对一致」（与系统证据矛盾）
 * - 一致：不需要理由
 */
export function reconcilePresetsFor(result: PopulationReconcileResult | null): string[] {
  if (result == null) return [..._PRESETS_UNAVAILABLE]
  if (!result.withinThreshold) return []  // 不符时不给一致类预置理由
  return []  // 一致时无需放行
}

// ─── formatMovementPair ─────────────────────────────────────────────────────

/** 「借 x / 贷 y 元」展示。 */
export function formatMovementPair(debit: string | null, credit: string | null): string {
  return `借 ${fmtAmount(debit)} / 贷 ${fmtAmount(credit)} 元`
}

/** 账面来源中文标签。 */
export function reconcileBasisLabel(basis: string | null): string {
  if (basis === 'tb_balance_movement') return '科目余额表发生额'
  if (basis?.startsWith('trial_balance_audited')) return '试算表审定发生额'
  if (basis) return basis
  return '独立来源'
}
