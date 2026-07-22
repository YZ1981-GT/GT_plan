/**
 * useH6Adjudication — H6-1 固定资产清理审定表
 *
 * 对齐致同源模板（冲突决议：列名/公式以 xlsx 为准）：
 *   项目 | 期初{未审/账项调整/审定} | 期末{未审/账项调整/审定}
 *       | 本期审定数与上期审定数的比较{变动额/变动率}
 *   数据行 ← 明细表 H6-2；合计后接审计说明(1)(2)(3)与报表核对 + 审计结论
 *
 * 公式：审定=未审+账项调整；变动额=期末审定−期初审定；
 *   变动率=IF(期初=0∧变动=0,0, 期初=0∧变动≠0→±100%, 否则 变动/|期初|)
 *
 * 数字化增强（保留原联动能力）：
 * - 过渡科目 1606 期末审定应为 0
 * - 从 H6-2 回填项目；从 H6-3 回写期末账项调整
 * - 清理净损益 ↔ H10；确认审定 → TB(1606)
 * - 兼容旧存档：category=income/expense/balance + beginBalance/unadjusted/aje/rje
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import {
  calcAuditedAmount,
  calcSubtotal,
  calcH6ChangeRate,
  calcH62EndUnadjusted,
  calcH62EndAdjustment,
} from './useH6FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

/** H6-1 审定表行（对齐 Excel 列 B–I） */
export interface H6AdjudicationRow {
  rowId: string
  /** 项目名称（通常对应 H6-2 资产名称） */
  name: string
  beginUnadjusted: number
  beginAdjustment: number
  beginAudited: number
  endUnadjusted: number
  endAdjustment: number
  endAudited: number
  /** 变动额 = 期末审定 − 期初审定 */
  auditedChange: number
  /** 变动率（%）；期初为 0 且变动≠0 时为 ±100 */
  auditedChangeRate: number | null
  isSignificant?: boolean
  isSubtotal?: boolean
  isTotal?: boolean
  /** 关联 H6-2 明细行 */
  refDetailRowId?: string
  /**
   * @deprecated 旧过程结构分类；迁移后不再写入
   */
  category?: 'income' | 'expense' | 'gainLoss' | 'balance'
  subCategory?: 'bookValue' | 'fee' | 'tax'
  beginBalance?: number
  debitAmount?: number
  creditAmount?: number
  endBalance?: number
  unadjusted?: number
  aje?: number
  rje?: number
  audited?: number
}

/** (3) 与经审计的财务报表核对 */
export interface H6FsReconcile {
  /** 固定资产净值期末审定（手填 / 自 H1 带入） */
  faNetEndAudited: number
  /** 固定资产净值期初审定 */
  faNetBeginAudited: number
  /** 报表期末数（固定资产+清理列报口径） */
  fsEndAmount: number
  /** 报表期初数 */
  fsBeginAmount: number
}

/** 结构化审计说明 */
export interface H6QualitativeNotes {
  /** (1) 期末较期初重大变动原因（变动率≥30%） */
  fluctuation: string
  /** (2) 情况说明 */
  situation: string
}

/** 过渡科目期末校验结果 */
export interface TransitCheckResult {
  isZero: boolean
  balance: number
  warning: string
}

/** H10交叉验证结果 */
export interface H10CrossCheck {
  h6GainLoss: number
  h10Amount: number
  diff: number
  isMatch: boolean
  warning: string
}

export interface H6SignificantChangeItem {
  name: string
  beginAudited: number
  endAudited: number
  auditedChange: number
  auditedChangeRate: number | null
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ROWS_KEY = 'H6-1-rows'
const NOTE_KEY = 'H6-1-audit-note'
const CONCLUSION_KEY = 'H6-1-audit-conclusion'
const QUAL_KEY = 'H6-1-qualitative-notes'
const FS_KEY = 'H6-1-fs-reconcile'
const GAIN_LOSS_KEY = 'H6-1-disposal-gain-loss'
const END_BALANCE_KEY = 'H6-1-end-balance-audited'
const BEGIN_BALANCE_KEY = 'H6-1-begin-balance-audited'
const AJE_TOTAL_KEY = 'H6-1-aje-total'
const RJE_TOTAL_KEY = 'H6-1-rje-total'
const SIGNIFICANT_KEY = 'H6-1-significant-changes'
const SIGNIFICANT_COUNT_KEY = 'H6-1-significant-change-count'

/** 变动率阈值（%），对齐源模板「比例超过30%」 */
export const CHANGE_RATE_THRESHOLD = 30

const EMPTY_NOTES: H6QualitativeNotes = { fluctuation: '', situation: '' }
const EMPTY_FS: H6FsReconcile = {
  faNetEndAudited: 0,
  faNetBeginAudited: 0,
  fsEndAmount: 0,
  fsBeginAmount: 0,
}

const CONCLUSION_TEMPLATES: Record<'A' | 'B' | 'C', string> = {
  A: '未见异常。经审定，固定资产清理在所有重大方面公允反映；过渡科目期末余额已结转完毕。',
  B: '除上述重大不符事项应当作为调整事项予以调整外，其余未见异常。',
  C: '由于存在以下重大未调整事项（或审计范围受到限制无法获取充分、适当证据），不可确认。',
}

// ─── Pure helpers ────────────────────────────────────────────────────────────

function _isSignificant(rate: number | null): boolean {
  return rate != null && Math.abs(rate) >= CHANGE_RATE_THRESHOLD
}

function _blankRow(name = ''): H6AdjudicationRow {
  return {
    rowId: `h61-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`,
    name,
    beginUnadjusted: 0,
    beginAdjustment: 0,
    beginAudited: 0,
    endUnadjusted: 0,
    endAdjustment: 0,
    endAudited: 0,
    auditedChange: 0,
    auditedChangeRate: 0,
    isSignificant: false,
    isSubtotal: false,
    isTotal: false,
  }
}

function _applyFormulas(row: H6AdjudicationRow): void {
  row.beginAudited = calcAuditedAmount(row.beginUnadjusted, row.beginAdjustment, 0)
  row.endAudited = calcAuditedAmount(row.endUnadjusted, row.endAdjustment, 0)
  row.auditedChange = row.endAudited - row.beginAudited
  row.auditedChangeRate = calcH6ChangeRate(row.auditedChange, row.beginAudited)
  row.isSignificant = _isSignificant(row.auditedChangeRate)
  // 兼容旧字段（供 extractH61Balances / 披露过渡）
  row.beginBalance = row.beginAudited
  row.endBalance = row.endAudited
  row.unadjusted = row.endUnadjusted
  row.aje = row.endAdjustment
  row.rje = 0
  row.audited = row.endAudited
}

/**
 * 兼容旧存档：
 * - 新格式：beginUnadjusted / endUnadjusted
 * - 旧过程结构：仅保留「期末余额」类 balance 行，映射为单行审定
 * - 旧字段：beginBalance / unadjusted / aje / rje
 */
export function normalizeH61Row(raw: any): H6AdjudicationRow | null {
  if (!raw || raw.isTotal || raw.isSubtotal) return null

  const cat = String(raw.category || '')
  const name = String(raw.name ?? '')

  // 旧过程结构：跳过收入/支出/净损益/期初/本期发生行
  if (cat === 'income' || cat === 'expense' || cat === 'gainLoss') return null
  if (cat === 'balance' && (name.includes('期初') || name.includes('本期'))) return null

  const hasNew = raw.beginUnadjusted != null || raw.endUnadjusted != null
  let beginUnadjusted = 0
  let beginAdjustment = 0
  let endUnadjusted = 0
  let endAdjustment = 0

  if (hasNew) {
    beginUnadjusted = Number(raw.beginUnadjusted) || 0
    beginAdjustment = Number(raw.beginAdjustment) || 0
    endUnadjusted = Number(raw.endUnadjusted) || 0
    endAdjustment = Number(raw.endAdjustment) || 0
  } else if (cat === 'balance' && name.includes('期末')) {
    // 旧「期末余额」行 → 期末未审/账项
    endUnadjusted = Number(raw.unadjusted ?? raw.endBalance) || 0
    endAdjustment = (Number(raw.aje) || 0) + (Number(raw.rje) || 0)
    beginUnadjusted = Number(raw.beginBalance) || 0
    beginAdjustment = 0
  } else if (!cat) {
    // 无 category 的旧扁平行
    beginUnadjusted = Number(raw.beginBalance) || 0
    beginAdjustment = 0
    endUnadjusted = Number(raw.unadjusted ?? raw.endBalance) || 0
    endAdjustment = (Number(raw.aje) || 0) + (Number(raw.rje) || 0)
  } else {
    return null
  }

  const row: H6AdjudicationRow = {
    rowId: raw.rowId ?? `h61-${Math.random().toString(36).slice(2, 10)}`,
    name: name.includes('期末') && cat === 'balance' ? '固定资产清理' : name || '固定资产清理',
    beginUnadjusted,
    beginAdjustment,
    beginAudited: 0,
    endUnadjusted,
    endAdjustment,
    endAudited: 0,
    auditedChange: 0,
    auditedChangeRate: null,
    isSignificant: false,
    isSubtotal: false,
    isTotal: false,
    refDetailRowId: raw.refDetailRowId,
  }
  _applyFormulas(row)
  return row
}

function _sumRow(details: H6AdjudicationRow[]): H6AdjudicationRow {
  const beginUnadj = calcSubtotal(details.map((r) => r.beginUnadjusted))
  const beginAdj = calcSubtotal(details.map((r) => r.beginAdjustment))
  const endUnadj = calcSubtotal(details.map((r) => r.endUnadjusted))
  const endAdj = calcSubtotal(details.map((r) => r.endAdjustment))
  const row: H6AdjudicationRow = {
    rowId: 'h61-total',
    name: '合计',
    beginUnadjusted: beginUnadj,
    beginAdjustment: beginAdj,
    beginAudited: 0,
    endUnadjusted: endUnadj,
    endAdjustment: endAdj,
    endAudited: 0,
    auditedChange: 0,
    auditedChangeRate: null,
    isSignificant: false,
    isSubtotal: false,
    isTotal: true,
  }
  _applyFormulas(row)
  return row
}

export function buildSignificantFluctuationNote(
  items: H6SignificantChangeItem[],
  threshold = CHANGE_RATE_THRESHOLD,
): string {
  if (!items.length) return ''
  const parts = items.map((it) => {
    const rate =
      it.auditedChangeRate == null
        ? '-'
        : `${it.auditedChangeRate.toLocaleString('zh-CN', { maximumFractionDigits: 2 })}%`
    const change = it.auditedChange.toLocaleString('zh-CN', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    })
    return `${it.name}变动额 ${change}（变动率 ${rate}）`
  })
  return `固定资产清理期末余额较期初变动率≥${threshold}% 的项目：${parts.join('；')}。请补充主要原因。`
}

function _parseJson(map: Map<string, any>, itemId: string): any {
  const item = map.get(itemId)
  if (!item) return null
  const raw = item.remark ?? item.conclusion
  if (!raw) return null
  if (typeof raw !== 'string') return raw
  try {
    return JSON.parse(raw)
  } catch {
    return raw
  }
}

function _round2(n: number): number {
  return Math.round(n * 100) / 100
}

function _allocateEndAdj(details: H6AdjudicationRow[], net: number): void {
  if (!details.length) return
  const weights = details.map((r) => Math.abs(r.endUnadjusted))
  const weightSum = calcSubtotal(weights)
  if (weightSum < 0.005) {
    // 均分
    const each = _round2(net / details.length)
    let allocated = 0
    details.forEach((r, i) => {
      if (i === details.length - 1) {
        r.endAdjustment = _round2(net - allocated)
      } else {
        r.endAdjustment = each
        allocated = _round2(allocated + each)
      }
      _applyFormulas(r)
    })
    return
  }
  let allocated = 0
  details.forEach((r, i) => {
    if (i === details.length - 1) {
      r.endAdjustment = _round2(net - allocated)
    } else {
      const share = _round2((net * Math.abs(r.endUnadjusted)) / weightSum)
      r.endAdjustment = share
      allocated = _round2(allocated + share)
    }
    _applyFormulas(r)
  })
}

/** 从 H6-2 明细推导审定表行金额（对齐 Excel：B/F/E/(F+G−H)） */
export function mapH62RowToAdjudication(raw: any): H6AdjudicationRow {
  const status = String(raw?.status || '')
  const nbv = Number(raw?.netBookValue) || 0
  const transferred = status === '已结转'
  const row = _blankRow(String(raw?.assetName || raw?.name || '').trim() || '未命名清理项')
  row.refDetailRowId = raw?.rowId

  const hasBalance =
    raw?.beginUnadjusted != null
    || raw?.periodIncrease != null
    || raw?.endUnadjusted != null
    || raw?.beginAdjustment != null
    || raw?.ajeIncrease != null
    || raw?.endAdjustment != null

  if (hasBalance) {
    const beginUnadj = Number(raw.beginUnadjusted) || 0
    const beginAdj = Number(raw.beginAdjustment) || 0
    const endUnadj =
      raw.endUnadjusted != null
        ? Number(raw.endUnadjusted) || 0
        : calcH62EndUnadjusted(
          beginUnadj,
          Number(raw.periodIncrease) || 0,
          Number(raw.periodDecrease) || 0,
        )
    const endAdj =
      raw.endAdjustment != null
        ? Number(raw.endAdjustment) || 0
        : calcH62EndAdjustment(
          beginAdj,
          Number(raw.ajeIncrease) || 0,
          Number(raw.ajeDecrease) || 0,
        )
    row.beginUnadjusted = beginUnadj
    row.beginAdjustment = beginAdj
    row.endUnadjusted = endUnadj
    row.endAdjustment = endAdj
  } else {
    // 旧明细：无余额列时回退净值/状态
    row.endUnadjusted = transferred ? 0 : nbv
    row.beginUnadjusted = Number(raw?.beginCarrying) || 0
    row.beginAdjustment = 0
    row.endAdjustment = 0
  }

  _applyFormulas(row)
  return row
}

/**
 * 从 H1-1 原值/折旧/减值行汇总固定资产净值（报表核对口径）。
 */
export function summarizeH11NetValue(parts: {
  costRows?: any[]
  depRows?: any[]
  impairRows?: any[]
}): { beginAudited: number; endAudited: number } {
  const sumField = (rows: any[] | undefined, field: 'beginBalance' | 'audited') => {
    if (!Array.isArray(rows)) return 0
    return rows.reduce((s, r) => {
      if (!r || r.isSubtotal || r.isTotal) return s
      return s + (Number(r[field]) || 0)
    }, 0)
  }
  const costBegin = sumField(parts.costRows, 'beginBalance')
  const costEnd = sumField(parts.costRows, 'audited')
  const depBegin = sumField(parts.depRows, 'beginBalance')
  const depEnd = sumField(parts.depRows, 'audited')
  const impairBegin = sumField(parts.impairRows, 'beginBalance')
  const impairEnd = sumField(parts.impairRows, 'audited')
  return {
    beginAudited: Math.round((costBegin - depBegin - impairBegin) * 100) / 100,
    endAudited: Math.round((costEnd - depEnd - impairEnd) * 100) / 100,
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH6Adjudication(params: {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  tbData?: Ref<{ unadjusted1606: number; audited1606: number }>
  h10Amount?: Ref<number>
  onSave?: (itemId: string, value: any) => void
  onWritebackTB?: (auditedAmount: number) => Promise<void>
}) {
  const { allResponses, onSave, onWritebackTB, tbData, h10Amount } = params

  const rows = ref<H6AdjudicationRow[]>([])
  const auditNote = ref('')
  const auditConclusion = ref('')
  const qualitativeNotes = ref<H6QualitativeNotes>({ ...EMPTY_NOTES })
  const fsReconcile = ref<H6FsReconcile>({ ...EMPTY_FS })

  function load(): void {
    const data = _parseJson(allResponses.value, ROWS_KEY)
    if (Array.isArray(data) && data.length > 0) {
      const mapped = data.map(normalizeH61Row).filter((r): r is H6AdjudicationRow => r != null)
      rows.value = mapped.length > 0 ? mapped : [_blankRow('固定资产清理')]
    } else {
      rows.value = [_blankRow('固定资产清理')]
    }

    auditNote.value = String(
      allResponses.value.get(NOTE_KEY)?.remark
        ?? allResponses.value.get(NOTE_KEY)?.conclusion
        ?? '',
    )
    auditConclusion.value = String(
      allResponses.value.get(CONCLUSION_KEY)?.remark
        ?? allResponses.value.get(CONCLUSION_KEY)?.conclusion
        ?? '',
    )

    const qual = _parseJson(allResponses.value, QUAL_KEY)
    qualitativeNotes.value = {
      fluctuation: String(qual?.fluctuation ?? ''),
      situation: String(qual?.situation ?? ''),
    }

    const fs = _parseJson(allResponses.value, FS_KEY)
    fsReconcile.value = {
      faNetEndAudited: Number(fs?.faNetEndAudited) || 0,
      faNetBeginAudited: Number(fs?.faNetBeginAudited) || 0,
      fsEndAmount: Number(fs?.fsEndAmount) || 0,
      fsBeginAmount: Number(fs?.fsBeginAmount) || 0,
    }
  }

  watch(allResponses, () => load(), { immediate: true })

  // ─── Computed ──────────────────────────────────────────────────────────────

  const detailRows = computed(() =>
    rows.value.filter((r) => !r.isTotal && !r.isSubtotal),
  )

  const totalRow = computed(() => _sumRow(detailRows.value))

  const displayRows = computed(() => [...detailRows.value, totalRow.value])

  const beginBalanceAudited = computed(() => totalRow.value.beginAudited)
  const endBalanceAudited = computed(() => totalRow.value.endAudited)

  const significantChangeItems = computed<H6SignificantChangeItem[]>(() =>
    detailRows.value
      .filter((r) => r.isSignificant)
      .map((r) => ({
        name: r.name,
        beginAudited: r.beginAudited,
        endAudited: r.endAudited,
        auditedChange: r.auditedChange,
        auditedChangeRate: r.auditedChangeRate,
      })),
  )

  const significantNetChanges = significantChangeItems

  const transitCheck: ComputedRef<TransitCheckResult> = computed(() => {
    const balance = endBalanceAudited.value
    // UI 层容差与 useH6CrossSheet 一致（|余额|<0.01 视为清零）
    const isZero = Math.abs(balance) < 0.01
    return {
      isZero,
      balance,
      warning: isZero
        ? ''
        : `⚠ 过渡科目期末余额应为0，当前余额：${balance.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}元，请检查是否有未完成清理项目`,
    }
  })

  /** 清理净损益：优先 H6-2 合计，其次本表持久化键 */
  const disposalGainLoss: ComputedRef<number> = computed(() => {
    const fromH62 = Number(allResponses.value.get('H6-2-subtotal-gain-loss')?.remark)
    if (Number.isFinite(fromH62)) return fromH62
    const detail = _parseJson(allResponses.value, 'H6-2-rows')
    if (Array.isArray(detail) && detail.length > 0) {
      return calcSubtotal(detail.map((r: any) => Number(r?.gainLoss) || 0))
    }
    const fromKey = Number(allResponses.value.get(GAIN_LOSS_KEY)?.remark)
    if (Number.isFinite(fromKey)) return fromKey
    return 0
  })

  const h10CrossCheck: ComputedRef<H10CrossCheck> = computed(() => {
    const h6GL = disposalGainLoss.value
    const h10Val = h10Amount?.value ?? 0
    const diff = h6GL - h10Val
    const isMatch = Math.abs(diff) < 0.01 || (h10Val === 0 && h6GL === 0)
    return {
      h6GainLoss: h6GL,
      h10Amount: h10Val,
      diff,
      isMatch,
      warning: isMatch ? '' : `净损益≠H10资产处置损益，差额：${diff > 0 ? '+' : ''}${diff}`,
    }
  })

  const ajeTotalNet = computed(() => calcSubtotal(detailRows.value.map((r) => r.endAdjustment)))
  const rjeTotalNet = computed(() => 0)

  const tbUnadjusted = computed(() => tbData?.value?.unadjusted1606 ?? 0)
  const tbAudited = computed(() => tbData?.value?.audited1606 ?? 0)
  const tbDiff = computed(() => endBalanceAudited.value - tbAudited.value)
  const isTbMatch = computed(() => Math.abs(tbDiff.value) < 0.01)

  /** (3) 报表核对展示行 */
  const fsCompareRows = computed(() => {
    const fs = fsReconcile.value
    const clearingEnd = endBalanceAudited.value
    const clearingBegin = beginBalanceAudited.value
    const combinedEnd = fs.faNetEndAudited + clearingEnd
    const combinedBegin = fs.faNetBeginAudited + clearingBegin
    return [
      {
        label: '固定资产净值审定数',
        endAudited: fs.faNetEndAudited,
        beginAudited: fs.faNetBeginAudited,
        editable: true,
        kind: 'fa' as const,
      },
      {
        label: '固定资产清理审定数',
        endAudited: clearingEnd,
        beginAudited: clearingBegin,
        editable: false,
        kind: 'clearing' as const,
      },
      {
        label: '固定资产与固定资产清理合计数',
        endAudited: combinedEnd,
        beginAudited: combinedBegin,
        editable: false,
        kind: 'combined' as const,
      },
      {
        label: '报表数',
        endAudited: fs.fsEndAmount,
        beginAudited: fs.fsBeginAmount,
        editable: true,
        kind: 'fs' as const,
      },
      {
        label: '差异',
        endAudited: combinedEnd - fs.fsEndAmount,
        beginAudited: combinedBegin - fs.fsBeginAmount,
        editable: false,
        kind: 'diff' as const,
      },
    ]
  })

  // ─── Persist ───────────────────────────────────────────────────────────────

  function _persist(): void {
    if (!onSave) return
    const toPersist = detailRows.value.map((r) => ({
      rowId: r.rowId,
      name: r.name,
      beginUnadjusted: r.beginUnadjusted,
      beginAdjustment: r.beginAdjustment,
      beginAudited: r.beginAudited,
      endUnadjusted: r.endUnadjusted,
      endAdjustment: r.endAdjustment,
      endAudited: r.endAudited,
      refDetailRowId: r.refDetailRowId,
    }))
    onSave(ROWS_KEY, toPersist)
    onSave(END_BALANCE_KEY, endBalanceAudited.value)
    onSave(BEGIN_BALANCE_KEY, beginBalanceAudited.value)
    onSave(AJE_TOTAL_KEY, ajeTotalNet.value)
    onSave(RJE_TOTAL_KEY, rjeTotalNet.value)
    onSave(GAIN_LOSS_KEY, disposalGainLoss.value)
    onSave(SIGNIFICANT_COUNT_KEY, significantChangeItems.value.length)
    onSave(SIGNIFICANT_KEY, significantChangeItems.value)
  }

  function _persistFs(): void {
    onSave?.(FS_KEY, { ...fsReconcile.value })
  }

  // ─── Actions ───────────────────────────────────────────────────────────────

  function updateCell(rowId: string, field: string, value: any): void {
    const row = rows.value.find((r) => r.rowId === rowId)
    if (!row || row.isTotal || row.isSubtotal) return
    const numVal = Number(value) || 0
    switch (field) {
      case 'name':
        row.name = String(value ?? '')
        break
      case 'beginUnadjusted':
        row.beginUnadjusted = numVal
        break
      case 'beginAdjustment':
        row.beginAdjustment = numVal
        break
      case 'endUnadjusted':
        row.endUnadjusted = numVal
        break
      case 'endAdjustment':
        row.endAdjustment = numVal
        break
      default:
        return
    }
    _applyFormulas(row)
    _persist()
  }

  function addRow(name = ''): void {
    rows.value.push(_blankRow(name.trim() || ''))
    _persist()
  }

  function deleteRow(rowId: string): void {
    const idx = rows.value.findIndex((r) => r.rowId === rowId)
    if (idx === -1) return
    if (rows.value[idx].isTotal || rows.value[idx].isSubtotal) return
    rows.value.splice(idx, 1)
    if (rows.value.length === 0) rows.value.push(_blankRow('固定资产清理'))
    _persist()
  }

  /**
   * 从 H6-2 回填项目行（对齐 Excel：H6-1!A7:I11 ← 明细表）
   */
  function syncFromH62(mode: 'overwrite' | 'fillEmpty' = 'overwrite'): {
    applied: boolean
    message: string
    count: number
  } {
    const detail = _parseJson(allResponses.value, 'H6-2-rows')
    if (!Array.isArray(detail) || detail.length === 0) {
      return { applied: false, message: 'H6-2 暂无明细数据', count: 0 }
    }

    const mapped = detail
      .filter((r: any) => r && (r.assetName || r.name))
      .map(mapH62RowToAdjudication)

    if (mode === 'overwrite') {
      // H6-2 余额列为权威；仅在明细无期初时保留审定表已填期初
      const prevByRef = new Map(
        detailRows.value.filter((r) => r.refDetailRowId).map((r) => [r.refDetailRowId!, r]),
      )
      const prevByName = new Map(detailRows.value.map((r) => [r.name, r]))
      rows.value = mapped.map((m) => {
        const raw = detail.find(
          (d: any) =>
            (m.refDetailRowId && d.rowId === m.refDetailRowId) || d.assetName === m.name || d.name === m.name,
        )
        const hasBalance =
          raw
          && (
            raw.beginUnadjusted != null
            || raw.periodIncrease != null
            || raw.endUnadjusted != null
            || raw.beginAdjustment != null
            || raw.endAdjustment != null
          )
        const prev = (m.refDetailRowId && prevByRef.get(m.refDetailRowId)) || prevByName.get(m.name)
        if (prev && !hasBalance) {
          // 旧明细无余额列：保留用户已填期初/账项
          if (prev.beginUnadjusted) m.beginUnadjusted = prev.beginUnadjusted
          if (prev.beginAdjustment) m.beginAdjustment = prev.beginAdjustment
          if (prev.endAdjustment) m.endAdjustment = prev.endAdjustment
          _applyFormulas(m)
        } else if (prev && hasBalance && prev.endAdjustment && !raw.endAdjustment && !raw.ajeIncrease && !raw.beginAdjustment) {
          // 明细有余额但无账项：保留 H6-3 回写的期末账项
          m.endAdjustment = prev.endAdjustment
          _applyFormulas(m)
        }
        return m
      })
    } else {
      for (const m of mapped) {
        const exists = detailRows.value.find(
          (r) => (m.refDetailRowId && r.refDetailRowId === m.refDetailRowId) || r.name === m.name,
        )
        if (exists) {
          if (exists.endUnadjusted === 0) exists.endUnadjusted = m.endUnadjusted
          if (!exists.refDetailRowId) exists.refDetailRowId = m.refDetailRowId
          _applyFormulas(exists)
        } else {
          rows.value.push(m)
        }
      }
    }

    _persist()
    return {
      applied: true,
      message: `已从 H6-2 回填 ${mapped.length} 个清理项目`,
      count: mapped.length,
    }
  }

  /** 接收 H6-3 调整分录：账项+报表净额写入期末账项调整（按未审权重分摊） */
  function syncAjeRjeFromAdjustment(ajeNet: number, rjeNet: number): void {
    const net = (Number(ajeNet) || 0) + (Number(rjeNet) || 0)
    const details = detailRows.value
    if (!details.length) return
    _allocateEndAdj(details, net)
    _persist()
  }

  function syncEndAdjFromH63(): { applied: boolean; message: string } {
    const adj = _parseJson(allResponses.value, 'H6-3-rows')
    // 若无原始行，退回用 cross-sheet 已算好的净额键
    let ajeNet = Number(allResponses.value.get('H6-3-clearing-aje-net')?.remark) || 0
    let rjeNet = Number(allResponses.value.get('H6-3-clearing-rje-net')?.remark) || 0
    if (Array.isArray(adj) && adj.length > 0) {
      // 留给 UI 侧传入；此处仍用已有 sync 入参路径
    }
    if (Math.abs(ajeNet) < 0.005 && Math.abs(rjeNet) < 0.005) {
      return { applied: false, message: 'H6-3 暂无 1606 调整净额' }
    }
    syncAjeRjeFromAdjustment(ajeNet, rjeNet)
    return {
      applied: true,
      message: `已从 H6-3 回写期末账项调整：AJE ${ajeNet.toLocaleString('zh-CN')} / RJE ${rjeNet.toLocaleString('zh-CN')}`,
    }
  }

  async function publishAdjudicated(): Promise<void> {
    _persist()
    if (onWritebackTB) {
      await onWritebackTB(endBalanceAudited.value)
    }
  }

  function saveNote(note: string): void {
    auditNote.value = note
    onSave?.(NOTE_KEY, note)
  }

  function saveConclusion(conclusion: string): void {
    auditConclusion.value = conclusion
    onSave?.(CONCLUSION_KEY, conclusion)
  }

  function saveQualitativeNotes(): void {
    onSave?.(QUAL_KEY, { ...qualitativeNotes.value })
  }

  function applyConclusionTemplate(key: 'A' | 'B' | 'C'): void {
    auditConclusion.value = CONCLUSION_TEMPLATES[key]
    onSave?.(CONCLUSION_KEY, auditConclusion.value)
  }

  function applySignificantFluctuationDraft(): void {
    const draft = buildSignificantFluctuationNote(significantChangeItems.value)
    if (!draft) return
    qualitativeNotes.value = {
      ...qualitativeNotes.value,
      fluctuation: qualitativeNotes.value.fluctuation?.trim()
        ? `${qualitativeNotes.value.fluctuation.trim()}\n${draft}`
        : draft,
    }
    saveQualitativeNotes()
  }

  function updateFsField(field: keyof H6FsReconcile, value: number): void {
    fsReconcile.value = { ...fsReconcile.value, [field]: Number(value) || 0 }
    _persistFs()
  }

  function seedFaNet(endAudited: number, beginAudited: number): void {
    fsReconcile.value = {
      ...fsReconcile.value,
      faNetEndAudited: Number(endAudited) || 0,
      faNetBeginAudited: Number(beginAudited) || 0,
    }
    _persistFs()
  }

  /**
   * 从 H1-1 审定行带入固定资产净值（overwrite / fillEmpty）
   */
  function seedFaNetFromH11(
    parts: { costRows?: any[]; depRows?: any[]; impairRows?: any[] },
    mode: 'overwrite' | 'fillEmpty' = 'overwrite',
  ): { applied: boolean; message: string; beginAudited: number; endAudited: number } {
    const { beginAudited, endAudited } = summarizeH11NetValue(parts)
    if (beginAudited === 0 && endAudited === 0) {
      return { applied: false, message: 'H1-1 暂无可用的固定资产审定数', beginAudited: 0, endAudited: 0 }
    }
    if (mode === 'fillEmpty') {
      const cur = fsReconcile.value
      if (cur.faNetEndAudited !== 0 || cur.faNetBeginAudited !== 0) {
        return {
          applied: false,
          message: '报表核对·固定资产净值已有值，未覆盖（可用覆盖模式）',
          beginAudited,
          endAudited,
        }
      }
    }
    seedFaNet(endAudited, beginAudited)
    return {
      applied: true,
      message: `已从 H1-1 带入固定资产净值：期末 ${endAudited.toLocaleString('zh-CN')} / 期初 ${beginAudited.toLocaleString('zh-CN')}`,
      beginAudited,
      endAudited,
    }
  }

  function save(): void {
    _persist()
  }

  return {
    CHANGE_RATE_THRESHOLD,
    // State
    rows,
    auditNote,
    auditConclusion,
    qualitativeNotes,
    fsReconcile,
    // Computed
    detailRows,
    totalRow,
    displayRows,
    beginBalanceAudited,
    endBalanceAudited,
    significantChangeItems,
    significantNetChanges,
    disposalGainLoss,
    transitCheck,
    h10CrossCheck,
    ajeTotalNet,
    rjeTotalNet,
    tbUnadjusted,
    tbAudited,
    tbDiff,
    isTbMatch,
    fsCompareRows,
    // Actions
    updateCell,
    addRow,
    deleteRow,
    syncFromH62,
    syncAjeRjeFromAdjustment,
    syncEndAdjFromH63,
    save,
    load,
    publishAdjudicated,
    saveNote,
    saveConclusion,
    saveQualitativeNotes,
    applyConclusionTemplate,
    applySignificantFluctuationDraft,
    updateFsField,
    seedFaNet,
    seedFaNetFromH11,
  }
}

export default useH6Adjudication
