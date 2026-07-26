/**
 * h1FourTablePrefill — H1 四表取数载荷 → H1-2 明细行映射（纯函数，便于单测）
 *
 * 后端 `html_data.h1_four_table_prefill`（灰度 H1_FOUR_TABLE_EXTRACTION_ENABLED）：
 *   detail          — tb_balance 叶子科目按**分类**聚合（原值/累计折旧/减值三段期初·借·贷·期末）
 *   ledger_movement — tb_ledger 1601 借/贷方合计（本期增加/减少），available=false 表示取不到
 *   counterpart     — 折旧对方科目可用性探测（宁缺勿造：不可用时只给中文原因）
 *
 * 铁律（Req1.5 / Req8.1）：
 *   四表库**无资产卡片维度**（tb_aux_balance 实证无该维度），故资产编号/取得日期/使用年限/
 *   残值率/存放地点等 Card_Level 字段一律留空，由客户台账导入或手工补录，**绝不编造**。
 *
 * Spec: .kiro/specs/h1-four-table-extraction/
 */
import { createEmptyDetailRow, recalcDetailRow, type DetailRow } from './useH1Detail'

// ─── Types（与后端载荷逐字对应）────────────────────────────────────────────────

export interface H1PrefillAmount {
  begin: number
  debit: number
  credit: number
  end: number
}

export interface H1PrefillDetailRow {
  category: string
  source_codes: string[]
  cost: H1PrefillAmount
  dep: H1PrefillAmount
  impair: H1PrefillAmount
  needs_review?: boolean
  formula?: string
}

export interface H1PrefillDetail {
  rows: H1PrefillDetailRow[]
  totals: { cost: number; dep: number; impair: number }
  source?: string
}

export interface H1LedgerMovement {
  available: boolean
  lines?: number
  debit_total: number
  credit_total: number
}

export interface H1CounterpartProbe {
  available: boolean
  fill_rate: number
  total_lines?: number
  reason: string
}

export interface H1FourTablePrefill {
  enabled?: boolean
  detail?: H1PrefillDetail
  ledger_movement?: H1LedgerMovement
  counterpart?: H1CounterpartProbe
}

/** 取数行 remark 前缀（用于识别"取数行"以便重新取数时覆盖、保留手工新增行） */
export const H1_FOUR_TABLE_REMARK_PREFIX = '四表取数(tb_balance)'

function _num(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function _amt(a: H1PrefillAmount | undefined): H1PrefillAmount {
  return {
    begin: _num(a?.begin),
    debit: _num(a?.debit),
    credit: _num(a?.credit),
    end: _num(a?.end),
  }
}

/** 该行是否由四表取数生成（非审计师手工新增） */
export function isFourTableSeededRow(row: Pick<DetailRow, 'remark'> | null | undefined): boolean {
  return typeof row?.remark === 'string' && row.remark.startsWith(H1_FOUR_TABLE_REMARK_PREFIX)
}

/**
 * 四表取数载荷 → H1-2 明细行（分类级）
 *
 * 映射口径：
 *   原值（资产类）：期初=begin / 本期增加=借方 / 本期减少=贷方
 *   累计折旧、减值（备抵类）：期初=|begin| / 本期计提=贷方 / 本期处置=借方
 *   期末与审定列一律交给 `recalcDetailRow` 派生（不直接写 end，保证公式列自洽）
 */
export function buildDetailSeedRows(prefill: H1FourTablePrefill | null | undefined): DetailRow[] {
  const rows = prefill?.detail?.rows
  if (!Array.isArray(rows) || rows.length === 0) return []

  const out: DetailRow[] = []
  rows.forEach((src, idx) => {
    const category = String(src?.category ?? '').trim()
    if (!category) return
    const cost = _amt(src?.cost)
    const dep = _amt(src?.dep)
    const impair = _amt(src?.impair)

    const row = createEmptyDetailRow(category, category)
    row.rowId = `h1ft-${idx}-${category}`

    // 原值
    row.costBeginUnadj = cost.begin
    row.costIncUnadj = cost.debit
    row.costDecUnadj = cost.credit

    // 累计折旧（备抵：贷方=计提增加 / 借方=处置减少）
    row.depBeginUnadj = dep.begin
    row.depProvUnadj = dep.credit
    row.depDispUnadj = dep.debit

    // 减值准备（备抵，结构同折旧）
    row.impairBeginUnadj = impair.begin
    row.impairProvUnadj = impair.credit
    row.impairDispUnadj = impair.debit

    const codes = Array.isArray(src?.source_codes) ? src.source_codes.filter(Boolean) : []
    const reviewFlag = src?.needs_review ? '，分类待复核' : ''
    row.remark = `${H1_FOUR_TABLE_REMARK_PREFIX}：${codes.join('/') || '—'}${reviewFlag}`

    recalcDetailRow(row)
    out.push(row)
  })
  return out
}

/**
 * Persist_First 判定（Req1.3 / Req6.2）：仅当 H1-2 明细缺失或为空数组时才允许种子填充。
 * 解析失败一律视为"有数据"——宁可不 seed 也不覆盖审计师已录内容。
 */
export function shouldSeedDetailRows(rawRemark: unknown): boolean {
  if (rawRemark == null || rawRemark === '') return true
  try {
    const arr = JSON.parse(String(rawRemark))
    return Array.isArray(arr) && arr.length === 0
  } catch {
    return false
  }
}

/** 「重新取数」：覆盖取数行、保留手工新增行（Req7.3） */
export function mergeSeedRows<T extends { remark?: string }>(seeds: T[], rawRemark: unknown): T[] {
  let manual: T[] = []
  try {
    const arr = rawRemark ? JSON.parse(String(rawRemark)) : []
    if (Array.isArray(arr)) manual = arr.filter((r: any) => !isFourTableSeededRow(r))
  } catch {
    manual = []
  }
  return [...seeds, ...manual]
}

// ─── 增减核对（Req2）─────────────────────────────────────────────────────────

export interface H1MovementReconcile {
  /** 序时账是否可用（false 时前端显示"未取到序时账发生额"而非 0/一致） */
  available: boolean
  detailIncrease: number
  detailDecrease: number
  ledgerIncrease: number
  ledgerDecrease: number
  diffIncrease: number
  diffDecrease: number
  /** 任一方向差异绝对值 > 1 元 */
  hasDiff: boolean
  message: string
}

const _DIFF_TOLERANCE = 1

/**
 * H1-2 原值本期增减 vs 序时账 1601 借/贷方合计（只读核对，不自动改数 Req2.4）
 *
 * @param detailRows H1-2 当前明细行（含手工新增行，按未审增减合计）
 */
export function buildMovementReconcile(
  detailRows: Pick<DetailRow, 'costIncUnadj' | 'costDecUnadj'>[] | null | undefined,
  ledger: H1LedgerMovement | null | undefined,
): H1MovementReconcile {
  const list = Array.isArray(detailRows) ? detailRows : []
  const detailIncrease = list.reduce((s, r) => s + _num(r?.costIncUnadj), 0)
  const detailDecrease = list.reduce((s, r) => s + _num(r?.costDecUnadj), 0)

  if (!ledger?.available) {
    return {
      available: false,
      detailIncrease,
      detailDecrease,
      ledgerIncrease: 0,
      ledgerDecrease: 0,
      diffIncrease: 0,
      diffDecrease: 0,
      hasDiff: false,
      message: '未取到序时账发生额（本期无 1601 分录或序时账未导入），无法自动核对本期增减。',
    }
  }

  const ledgerIncrease = _num(ledger.debit_total)
  const ledgerDecrease = _num(ledger.credit_total)
  const diffIncrease = detailIncrease - ledgerIncrease
  const diffDecrease = detailDecrease - ledgerDecrease
  const hasDiff =
    Math.abs(diffIncrease) > _DIFF_TOLERANCE || Math.abs(diffDecrease) > _DIFF_TOLERANCE

  return {
    available: true,
    detailIncrease,
    detailDecrease,
    ledgerIncrease,
    ledgerDecrease,
    diffIncrease,
    diffDecrease,
    hasDiff,
    message: hasDiff
      ? `明细本期增减与序时账 1601 发生额存在差异（增加差异 ${diffIncrease.toFixed(2)}，减少差异 ${diffDecrease.toFixed(2)}），请核对是否漏记或跨科目结转。`
      : '明细本期增减与序时账 1601 发生额一致。',
  }
}
