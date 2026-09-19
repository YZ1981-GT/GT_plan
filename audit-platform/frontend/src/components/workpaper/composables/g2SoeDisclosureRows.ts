/**
 * G2 国企附注披露行结构 — 对齐 Excel「附注披露信息（国企）」+ note_template_soe §八、9
 * ① 应收利息分类  ② 重要逾期利息  ③ 坏账准备计提情况（ECL 三阶段）
 */
import { parseG2AdjStore, leafKeysForSection, type G2AdjRowStore } from './g2AdjudicationItems'
import { parseNum, calcAuditedAmount } from './useG2IntRecFormulaEngine'

export type G2SoeClassKind = 'data' | 'subtotal' | 'provision' | 'total'

export interface G2SoeClassRow {
  rowKey: string
  label: string
  kind: G2SoeClassKind
  endAmount: number
  priorAmount: number
  editable: boolean
  autoFilled?: boolean
}

export interface G2SoeOverdueRow {
  id: string
  borrower: string
  endAmount: number
  overdueMonths: number | ''
  overdueReason: string
  impairmentBasis: string
}

export type G2SoeEclStageKey = 'stage1' | 'stage2' | 'stage3' | 'total'

export interface G2SoeEclRow {
  rowKey: string
  label: string
  kind: 'header' | 'data' | 'indent' | 'closing'
  editable: boolean
  stage1: number
  stage2: number
  stage3: number
}

export const G2_SOE_CLASS_DEFS: ReadonlyArray<{
  rowKey: string
  label: string
  kind: G2SoeClassKind
  editable: boolean
  /** G2-2 investType 匹配关键词（小写包含） */
  typeKeywords?: readonly string[]
}> = [
  { rowKey: 'fixed-deposit', label: '定期存款', kind: 'data', editable: true, typeKeywords: ['定期存款', '定期', 'deposit'] },
  { rowKey: 'entrusted-loan', label: '委托贷款', kind: 'data', editable: true, typeKeywords: ['委托贷款', '委托', 'entrusted'] },
  { rowKey: 'bond', label: '债券投资', kind: 'data', editable: true, typeKeywords: ['债券', '债权', 'bond'] },
  { rowKey: 'other', label: '其他', kind: 'data', editable: true, typeKeywords: ['其他', 'other'] },
  { rowKey: 'subtotal', label: '小计', kind: 'subtotal', editable: false },
  { rowKey: 'provision', label: '减：坏账准备', kind: 'provision', editable: true },
  { rowKey: 'total', label: '合计', kind: 'total', editable: false },
]

export const G2_SOE_ECL_ROW_DEFS: ReadonlyArray<{
  rowKey: string
  label: string
  kind: G2SoeEclRow['kind']
  editable: boolean
}> = [
  { rowKey: 'header', label: '坏账准备', kind: 'header', editable: false },
  { rowKey: 'opening', label: '期初余额', kind: 'data', editable: true },
  { rowKey: 'opening-move', label: '期初余额在本期', kind: 'data', editable: false },
  { rowKey: 'to-stage2', label: '—转入第二阶段', kind: 'indent', editable: true },
  { rowKey: 'to-stage3', label: '—转入第三阶段', kind: 'indent', editable: true },
  { rowKey: 'back-stage2', label: '—转回第二阶段', kind: 'indent', editable: true },
  { rowKey: 'back-stage1', label: '—转回第一阶段', kind: 'indent', editable: true },
  { rowKey: 'provision', label: '本期计提', kind: 'data', editable: true },
  { rowKey: 'reversal', label: '本期转回', kind: 'data', editable: true },
  { rowKey: 'write-off-acct', label: '本期转销', kind: 'data', editable: true },
  { rowKey: 'write-off', label: '本期核销', kind: 'data', editable: true },
  { rowKey: 'other', label: '其他变动', kind: 'data', editable: true },
  { rowKey: 'closing', label: '期末余额', kind: 'closing', editable: false },
]

const DATA_CLASS_KEYS = ['fixed-deposit', 'entrusted-loan', 'bond', 'other'] as const

export function createEmptyOverdueRow(): G2SoeOverdueRow {
  return {
    id: `ov-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    borrower: '',
    endAmount: 0,
    overdueMonths: '',
    overdueReason: '',
    impairmentBasis: '',
  }
}

/** 账龄标签粗估逾期月数（供附注②展示） */
export function estimateOverdueMonthsFromAging(aging: string): number | '' {
  const a = String(aging || '').trim()
  if (!a) return ''
  if (/1年以内|一年以内|within\s*1/i.test(a)) return 6
  if (/1[-至到]2|一年以上两年以内/i.test(a)) return 18
  if (/2[-至到]3/i.test(a)) return 30
  if (/3[-至到]4|3年以上|三年以上/i.test(a)) return 42
  if (/4[-至到]5/i.test(a)) return 54
  if (/5年以上|五年以上/i.test(a)) return 66
  return ''
}

/**
 * 从 G2-6 长期未收回检查提取「重要逾期」行。
 * 优先取一年以上 / 标记无法收回 / 有未收回原因的行。
 */
export function extractOverdueFromG26(g26Raw: string | null | undefined): G2SoeOverdueRow[] {
  if (!g26Raw) return []
  try {
    const parsed = JSON.parse(g26Raw)
    if (!Array.isArray(parsed)) return []
    const out: G2SoeOverdueRow[] = []
    for (const r of parsed) {
      const borrower = String(r?.debtorName || r?.investTarget || '').trim()
      const endAmount =
        parseNum(r?.auditedBalance)
        || (parseNum(r?.openingBalance) + parseNum(r?.periodDebit) - parseNum(r?.periodCredit))
        || parseNum(r?.receivableAmount)
      const aging = String(r?.aging || '')
      const unrecoveredReason = String(r?.unrecoveredReason || r?.overdueReason || '')
      const isUncollectible = String(r?.isUncollectible || '')
      const longTerm = aging && !/^1年以内|一年以内|within\s*1/i.test(aging)
      const important =
        longTerm
        || /是|部分/.test(isUncollectible)
        || !!unrecoveredReason
        || endAmount > 0 && longTerm
      if (!borrower && !endAmount) continue
      if (!important && !longTerm) continue
      const impairment =
        isUncollectible === '是'
          ? '已发生减值（G2-6：无法收回）'
          : isUncollectible === '部分'
            ? '部分减值（G2-6）'
            : unrecoveredReason
              ? `关注可收回性：${unrecoveredReason}`
              : '待评估'
      out.push({
        id: `ov-g26-${r?.id || Date.now()}-${out.length}`,
        borrower: borrower || '（未命名债务人）',
        endAmount,
        overdueMonths: estimateOverdueMonthsFromAging(aging),
        overdueReason: unrecoveredReason || String(r?.businessDesc || '') || aging,
        impairmentBasis: impairment,
      })
    }
    return out
  } catch {
    return []
  }
}

export function buildDefaultClassRows(): G2SoeClassRow[] {
  return G2_SOE_CLASS_DEFS.map((d) => ({
    rowKey: d.rowKey,
    label: d.label,
    kind: d.kind,
    endAmount: 0,
    priorAmount: 0,
    editable: d.editable,
    autoFilled: false,
  }))
}

export function buildDefaultEclRows(): G2SoeEclRow[] {
  return G2_SOE_ECL_ROW_DEFS.map((d) => ({
    rowKey: d.rowKey,
    label: d.label,
    kind: d.kind,
    editable: d.editable,
    stage1: 0,
    stage2: 0,
    stage3: 0,
  }))
}

export function sumClassData(rows: G2SoeClassRow[]): { endAmount: number; priorAmount: number } {
  return rows
    .filter((r) => DATA_CLASS_KEYS.includes(r.rowKey as (typeof DATA_CLASS_KEYS)[number]))
    .reduce(
      (acc, r) => ({
        endAmount: acc.endAmount + (Number(r.endAmount) || 0),
        priorAmount: acc.priorAmount + (Number(r.priorAmount) || 0),
      }),
      { endAmount: 0, priorAmount: 0 },
    )
}

/** 重算小计 / 合计（合计 = 小计 − 坏账准备） */
export function recomputeClassDerived(rows: G2SoeClassRow[]): G2SoeClassRow[] {
  const sub = sumClassData(rows)
  const provision = rows.find((r) => r.rowKey === 'provision')
  const provEnd = Number(provision?.endAmount) || 0
  const provPrior = Number(provision?.priorAmount) || 0
  return rows.map((r) => {
    if (r.rowKey === 'subtotal') {
      return { ...r, endAmount: sub.endAmount, priorAmount: sub.priorAmount, editable: false }
    }
    if (r.rowKey === 'total') {
      return {
        ...r,
        endAmount: sub.endAmount - provEnd,
        priorAmount: sub.priorAmount - provPrior,
        editable: false,
      }
    }
    return r
  })
}

export function eclRowTotal(row: G2SoeEclRow): number {
  return (Number(row.stage1) || 0) + (Number(row.stage2) || 0) + (Number(row.stage3) || 0)
}

/**
 * 期末余额 = 期初 + 转入/转回净额 + 计提 − 转回 − 转销 − 核销 + 其他
 * 转入第二阶段：stage1 减少、stage2 增加（金额按录入绝对值处理）
 */
export function recomputeEclClosing(rows: G2SoeEclRow[]): G2SoeEclRow[] {
  const byKey = Object.fromEntries(rows.map((r) => [r.rowKey, r])) as Record<string, G2SoeEclRow>
  const get = (key: string, stage: 'stage1' | 'stage2' | 'stage3') =>
    Number(byKey[key]?.[stage]) || 0

  const closing = (stage: 'stage1' | 'stage2' | 'stage3') => {
    const opening = get('opening', stage)
    const to2 = get('to-stage2', stage)
    const to3 = get('to-stage3', stage)
    const back2 = get('back-stage2', stage)
    const back1 = get('back-stage1', stage)
    const provision = get('provision', stage)
    const reversal = get('reversal', stage)
    const writeOffAcct = get('write-off-acct', stage)
    const writeOff = get('write-off', stage)
    const other = get('other', stage)
    return (
      opening
      + to2
      + to3
      + back2
      + back1
      + provision
      - reversal
      - writeOffAcct
      - writeOff
      + other
    )
  }

  return rows.map((r) => {
    if (r.rowKey !== 'closing') return r
    return {
      ...r,
      stage1: closing('stage1'),
      stage2: closing('stage2'),
      stage3: closing('stage3'),
      editable: false,
    }
  })
}

export function overdueTotal(rows: G2SoeOverdueRow[]): number {
  return rows.reduce((s, r) => s + (Number(r.endAmount) || 0), 0)
}

/** 从 G2-1 审定表提取原值小计 / 坏账小计（期初/期末审定） */
export function extractAdjAmounts(storeRaw: string | null | undefined): {
  grossEnd: number
  grossPrior: number
  provisionEnd: number
  provisionPrior: number
  netEnd: number
  netPrior: number
} {
  const store: G2AdjRowStore = parseG2AdjStore(storeRaw)
  const sumSection = (section: 'gross' | 'provision') => {
    let end = 0
    let prior = 0
    for (const key of leafKeysForSection(section)) {
      const cell = store[key] || {}
      prior += calcAuditedAmount(
        parseNum(cell.openingUnadjusted),
        parseNum(cell.openingAdjustment),
        0,
      )
      end += calcAuditedAmount(
        parseNum(cell.closingUnadjusted),
        parseNum(cell.closingAdjustment),
        0,
      )
    }
    return { end, prior }
  }
  const gross = sumSection('gross')
  const provision = sumSection('provision')
  return {
    grossEnd: gross.end,
    grossPrior: gross.prior,
    provisionEnd: provision.end,
    provisionPrior: provision.prior,
    netEnd: gross.end - provision.end,
    netPrior: gross.prior - provision.prior,
  }
}

/** 按 G2-2 明细 investType 归集到分类行（期末优先 closingAudited） */
export function classifyDetailAmounts(
  detailRaw: string | null | undefined,
): Record<string, { endAmount: number; priorAmount: number }> {
  const result: Record<string, { endAmount: number; priorAmount: number }> = {
    'fixed-deposit': { endAmount: 0, priorAmount: 0 },
    'entrusted-loan': { endAmount: 0, priorAmount: 0 },
    bond: { endAmount: 0, priorAmount: 0 },
    other: { endAmount: 0, priorAmount: 0 },
  }
  if (!detailRaw) return result
  try {
    const parsed = JSON.parse(detailRaw)
    const rows = Array.isArray(parsed) ? parsed : []
    for (const row of rows) {
      const typeStr = String(row?.investType || row?.investTarget || '').toLowerCase()
      let matched: keyof typeof result = 'other'
      for (const def of G2_SOE_CLASS_DEFS) {
        if (def.kind !== 'data' || !def.typeKeywords) continue
        if (def.typeKeywords.some((k) => typeStr.includes(k.toLowerCase()))) {
          matched = def.rowKey as keyof typeof result
          break
        }
      }
      // 滚动核对审定优先；兼容旧版 netReceivable / bookValue
      const end =
        parseNum(row?.closingAudited)
        || parseNum(row?.netReceivable)
        || parseNum(row?.bookValue)
        || parseNum(row?.closingBalance)
        || 0
      const prior =
        parseNum(row?.openingAudited)
        || parseNum(row?.openingUnadjusted)
        || 0
      result[matched].endAmount += end
      result[matched].priorAmount += prior
    }
  } catch {
    /* ignore */
  }
  return result
}

export interface G2SoePersisted {
  classRows: G2SoeClassRow[]
  overdueRows: G2SoeOverdueRow[]
  eclRows: G2SoeEclRow[]
}

export function serializeSoeDisclosure(data: G2SoePersisted): string {
  return JSON.stringify({
    classRows: data.classRows,
    overdueRows: data.overdueRows,
    eclRows: data.eclRows,
  })
}

export function parseSoeDisclosure(raw: string | null | undefined): G2SoePersisted | null {
  if (!raw) return null
  try {
    const parsed = JSON.parse(raw) as Partial<G2SoePersisted>
    if (!parsed || typeof parsed !== 'object') return null
    return {
      classRows: Array.isArray(parsed.classRows) && parsed.classRows.length
        ? recomputeClassDerived(parsed.classRows.map((r) => ({ ...r })))
        : buildDefaultClassRows(),
      overdueRows: Array.isArray(parsed.overdueRows) ? parsed.overdueRows : [],
      eclRows: Array.isArray(parsed.eclRows) && parsed.eclRows.length
        ? recomputeEclClosing(parsed.eclRows.map((r) => ({ ...r })))
        : buildDefaultEclRows(),
    }
  } catch {
    return null
  }
}
