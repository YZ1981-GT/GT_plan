/**
 * useH4Adjudication — H4-1 工程物资及减值准备审定表
 *
 * 对齐致同源模板（冲突决议 C1/C2/C3，以 xlsx 为准）：
 *   一、工程物资原值 → 二、减值准备 → 三、净值(=原值−减值)
 * 列组：期初{未审/账项调整/审定} | 期末{未审/账项调整/审定}
 *   | 本期审定数与上期审定数的比较{变动额/变动率}
 *
 * 公式：审定=未审+账项调整；变动额=期末审定−期初审定；
 *   变动率=IF(期初审定=0, 变动=0→0 / 变动≠0→±100%, 否则 变动/|期初|)
 *
 * 数字化增强：
 * - 默认分类：专用材料/专用设备/工器具/其他
 * - 从 H4-2 按分类回填；从 H4-3 回写期末账项调整（1605 净额按未审权重分摊）
 * - 净值变动≥30% 标红；结构化审计说明；(3)与报表核对（在建工程+工程物资）
 * - 兼容旧存档：beginBalance/unadjusted/aje/rje → 新字段
 *
 * Spec: .kiro/specs/h4-engineering-materials/
 * Requirements: 2.1-2.10（列结构以 xlsx/冲突决议为准）
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { calcAuditedAmount, calcSubtotal } from './useH4FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export type H4AdjudicationSection = 'original' | 'impairment'

/** H4-1 审定表行（原值 / 减值共用列结构） */
export interface H4AdjudicationRow {
  rowId: string
  /** 物资分类名称 */
  name: string
  section: H4AdjudicationSection
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
}

/** 净值行（按分类派生：原值−减值） */
export interface H4NetValueRow {
  rowId: string
  name: string
  beginUnadjusted: number
  beginAudited: number
  endUnadjusted: number
  endAudited: number
  auditedChange: number
  auditedChangeRate: number | null
  isSignificant: boolean
  isTotal?: boolean
}

/** (3) 与经审计的财务报表核对 */
export interface H4FsReconcile {
  /** 在建工程期末审定 */
  cipEndAudited: number
  /** 在建工程期初审定 */
  cipBeginAudited: number
  /** 报表期末数（在建工程+工程物资列报） */
  fsEndAmount: number
  /** 报表期初数 */
  fsBeginAmount: number
}

/** 结构化审计说明 */
export interface H4QualitativeNotes {
  /** (1) 净值重大变动原因（变动率≥30%） */
  fluctuation: string
  /** (2) 情况说明 */
  situation: string
}

export type H4AdjudicationBlock = 'original' | 'impairment'

// ─── Constants ───────────────────────────────────────────────────────────────

const ROWS_KEY = 'H4-1-rows'
const NOTE_KEY = 'H4-1-audit-note'
const CONCLUSION_KEY = 'H4-1-audit-conclusion'
const QUAL_KEY = 'H4-1-qualitative-notes'
const FS_KEY = 'H4-1-fs-reconcile'
const SIGNIFICANT_KEY = 'H4-1-significant-changes'
const SIGNIFICANT_COUNT_KEY = 'H4-1-significant-change-count'
const ADJUDICATED_TOTAL_KEY = 'H4-1-adjudicated-total'
const DEBIT_TOTAL_KEY = 'H4-1-debit-total'
const CREDIT_TOTAL_KEY = 'H4-1-credit-total'
const BEGIN_TOTAL_KEY = 'H4-1-begin-total'
const END_TOTAL_KEY = 'H4-1-end-total'

/** 净值变动率阈值（%），对齐源模板「比例超过30%」 */
export const CHANGE_RATE_THRESHOLD = 30

/** 致同模板默认分类（底稿目录可引用） */
export const DEFAULT_H4_CATEGORIES = ['专用材料', '专用设备', '工器具', '其他'] as const

const EMPTY_NOTES: H4QualitativeNotes = { fluctuation: '', situation: '' }
const EMPTY_FS: H4FsReconcile = {
  cipEndAudited: 0,
  cipBeginAudited: 0,
  fsEndAmount: 0,
  fsBeginAmount: 0,
}

const CONCLUSION_TEMPLATES: Record<'A' | 'B' | 'C', string> = {
  A: '未见异常。经审定，工程物资及相关减值准备在所有重大方面公允反映。',
  B: '除上述重大不符事项应当作为调整事项予以调整外，其余未见异常。',
  C: '由于存在以下重大未调整事项（或审计范围受到限制无法获取充分、适当证据），不可确认。',
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

/** 净值重大变动项（供附注键 / disclosureAutoFill 消费） */
export interface H4SignificantChangeItem {
  name: string
  beginAudited: number
  endAudited: number
  auditedChange: number
  auditedChangeRate: number | null
}

/** 在建工程审定带入来源 */
export interface H4CipSeedSource {
  endAudited: number
  beginAudited: number
  source: 'H2-1' | 'TB-1604' | 'event'
}

/**
 * 从 H2-1 原值行汇总在建工程审定（报表核对口径=原值审定，非净值）
 */
export function summarizeH21CostAudited(rows: any[]): { beginAudited: number; endAudited: number } {
  let beginAudited = 0
  let endAudited = 0
  if (!Array.isArray(rows)) return { beginAudited, endAudited }
  for (const r of rows) {
    if (!r || r.isTotal || r.isSubtotal) continue
    const b =
      Number(r.beginAudited)
      || (Number(r.beginUnadjusted) || 0) + (Number(r.beginAdjustment) || 0)
    const e =
      Number(r.endAudited)
      || (Number(r.endUnadjusted) || 0) + (Number(r.endAdjustment) || 0)
    beginAudited += b
    endAudited += e
  }
  return {
    beginAudited: Math.round(beginAudited * 100) / 100,
    endAudited: Math.round(endAudited * 100) / 100,
  }
}

/** 格式化重大变动说明草稿（附注/审计说明可直接引用） */
export function buildSignificantFluctuationNote(
  items: H4SignificantChangeItem[],
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
  return `净值变动率≥${threshold}% 的分类：${parts.join('；')}。请补充主要原因。`
}

/** 对齐 Excel：I=IF(AND(D=0,H=0),0,IF(AND(D=0,H>0),1,H/D))，输出为百分比 */
export function calcH4ChangeRate(change: number, beginAudited: number): number | null {
  if (beginAudited === 0 && change === 0) return 0
  if (beginAudited === 0) return change > 0 ? 100 : change < 0 ? -100 : 0
  return (change / Math.abs(beginAudited)) * 100
}

function _isSignificant(rate: number | null): boolean {
  return rate != null && Math.abs(rate) >= CHANGE_RATE_THRESHOLD
}

function _blankRow(name: string, section: H4AdjudicationSection): H4AdjudicationRow {
  return {
    rowId: `h41-${section}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`,
    name,
    section,
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

function _applyFormulas(row: H4AdjudicationRow): void {
  row.beginAudited = calcAuditedAmount(row.beginUnadjusted, row.beginAdjustment, 0)
  row.endAudited = calcAuditedAmount(row.endUnadjusted, row.endAdjustment, 0)
  row.auditedChange = row.endAudited - row.beginAudited
  row.auditedChangeRate = calcH4ChangeRate(row.auditedChange, row.beginAudited)
  row.isSignificant = _isSignificant(row.auditedChangeRate)
}

/**
 * 兼容旧存档：
 * beginBalance/debit/credit/endBalance/unadjusted/aje/rje
 */
function _normalizeRow(raw: any): H4AdjudicationRow {
  const section: H4AdjudicationSection =
    raw.section === 'impairment' ? 'impairment' : 'original'

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
  } else {
    // 旧：期末未审≈unadjusted；账项≈aje+rje；期初≈beginBalance
    beginUnadjusted = Number(raw.beginBalance) || 0
    beginAdjustment = 0
    endUnadjusted = Number(raw.unadjusted ?? raw.endBalance) || 0
    endAdjustment = (Number(raw.aje) || 0) + (Number(raw.rje) || 0)
  }

  const row: H4AdjudicationRow = {
    rowId: raw.rowId ?? `h41-${section}-${Math.random().toString(36).slice(2, 10)}`,
    name: String(raw.name ?? ''),
    section,
    beginUnadjusted,
    beginAdjustment,
    beginAudited: 0,
    endUnadjusted,
    endAdjustment,
    endAudited: 0,
    auditedChange: 0,
    auditedChangeRate: null,
    isSignificant: false,
    isSubtotal: raw.isSubtotal ?? false,
    isTotal: raw.isTotal ?? false,
  }
  _applyFormulas(row)
  return row
}

function _sumRow(name: string, section: H4AdjudicationSection, details: H4AdjudicationRow[]): H4AdjudicationRow {
  const beginUnadj = calcSubtotal(details.map((r) => r.beginUnadjusted))
  const beginAdj = calcSubtotal(details.map((r) => r.beginAdjustment))
  const endUnadj = calcSubtotal(details.map((r) => r.endUnadjusted))
  const endAdj = calcSubtotal(details.map((r) => r.endAdjustment))
  const row: H4AdjudicationRow = {
    rowId: `h41-${section}-total`,
    name,
    section,
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

function _seedDefaultRows(): H4AdjudicationRow[] {
  const rows: H4AdjudicationRow[] = []
  for (const cat of DEFAULT_H4_CATEGORIES) {
    rows.push(_blankRow(cat, 'original'))
    rows.push(_blankRow(cat, 'impairment'))
  }
  return rows
}

function _persistSlice(rows: H4AdjudicationRow[]) {
  return rows
    .filter((r) => !r.isTotal && !r.isSubtotal)
    .map((r) => ({
      rowId: r.rowId,
      name: r.name,
      section: r.section,
      beginUnadjusted: r.beginUnadjusted,
      beginAdjustment: r.beginAdjustment,
      beginAudited: r.beginAudited,
      endUnadjusted: r.endUnadjusted,
      endAdjustment: r.endAdjustment,
      endAudited: r.endAudited,
    }))
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

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH4Adjudication(params: {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  tbData?: Ref<{
    unadjusted1605: number
    audited1605: number
    /** TB·1604 未审（期末） */
    unadjusted1604?: number
    /** TB·1604 审定（期末） */
    audited1604?: number
    /** TB·1604 期初余额（来自 tb_balance opening） */
    opening1604?: number
  }>
  onSave?: (itemId: string, value: any) => void
  onWritebackTB?: (auditedAmount: number) => Promise<void>
}) {
  const { allResponses, onSave, onWritebackTB, tbData } = params

  const rows = ref<H4AdjudicationRow[]>([])
  const auditNote = ref('')
  const auditConclusion = ref('')
  const qualitativeNotes = ref<H4QualitativeNotes>({ ...EMPTY_NOTES })
  const fsReconcile = ref<H4FsReconcile>({ ...EMPTY_FS })

  // ─── Load ──────────────────────────────────────────────────────────────────

  function load(): void {
    const data = _parseJson(allResponses.value, ROWS_KEY)
    if (Array.isArray(data) && data.length > 0) {
      rows.value = data
        .filter((r: any) => r && !r.isTotal && !r.isSubtotal)
        .map(_normalizeRow)
    } else {
      rows.value = _seedDefaultRows()
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
      cipEndAudited: Number(fs?.cipEndAudited) || 0,
      cipBeginAudited: Number(fs?.cipBeginAudited) || 0,
      fsEndAmount: Number(fs?.fsEndAmount) || 0,
      fsBeginAmount: Number(fs?.fsBeginAmount) || 0,
    }
  }

  watch(allResponses, () => load(), { immediate: true })

  // ─── Computed: 分段明细 / 合计 ─────────────────────────────────────────────

  const originalRows = computed(() =>
    rows.value.filter((r) => r.section === 'original' && !r.isTotal && !r.isSubtotal),
  )
  const impairmentRows = computed(() =>
    rows.value.filter((r) => r.section === 'impairment' && !r.isTotal && !r.isSubtotal),
  )

  const originalTotal = computed(() => _sumRow('合计', 'original', originalRows.value))
  const impairmentTotal = computed(() => _sumRow('合计', 'impairment', impairmentRows.value))

  /** @deprecated 兼容旧名 */
  const originalSubtotal = originalTotal
  /** @deprecated 兼容旧名 */
  const impairmentSubtotal = impairmentTotal

  const netRows = computed<H4NetValueRow[]>(() => {
    const names = new Set<string>()
    for (const r of originalRows.value) if (r.name) names.add(r.name)
    for (const r of impairmentRows.value) if (r.name) names.add(r.name)

    const list: H4NetValueRow[] = []
    for (const name of names) {
      const o = originalRows.value.find((r) => r.name === name)
      const i = impairmentRows.value.find((r) => r.name === name)
      const beginUnadj = (o?.beginUnadjusted ?? 0) - (i?.beginUnadjusted ?? 0)
      const beginAud = (o?.beginAudited ?? 0) - (i?.beginAudited ?? 0)
      const endUnadj = (o?.endUnadjusted ?? 0) - (i?.endUnadjusted ?? 0)
      const endAud = (o?.endAudited ?? 0) - (i?.endAudited ?? 0)
      const change = endAud - beginAud
      const rate = calcH4ChangeRate(change, beginAud)
      list.push({
        rowId: `net-${name}`,
        name,
        beginUnadjusted: beginUnadj,
        beginAudited: beginAud,
        endUnadjusted: endUnadj,
        endAudited: endAud,
        auditedChange: change,
        auditedChangeRate: rate,
        isSignificant: _isSignificant(rate),
        isTotal: false,
      })
    }
    return list
  })

  const netTotalRow = computed<H4NetValueRow>(() => {
    const beginUnadj = originalTotal.value.beginUnadjusted - impairmentTotal.value.beginUnadjusted
    const beginAud = originalTotal.value.beginAudited - impairmentTotal.value.beginAudited
    const endUnadj = originalTotal.value.endUnadjusted - impairmentTotal.value.endUnadjusted
    const endAud = originalTotal.value.endAudited - impairmentTotal.value.endAudited
    const change = endAud - beginAud
    const rate = calcH4ChangeRate(change, beginAud)
    return {
      rowId: 'net-total',
      name: '合计',
      beginUnadjusted: beginUnadj,
      beginAudited: beginAud,
      endUnadjusted: endUnadj,
      endAudited: endAud,
      auditedChange: change,
      auditedChangeRate: rate,
      isSignificant: _isSignificant(rate),
      isTotal: true,
    }
  })

  /** 兼容旧 UI：净值合计对象（字段映射到 endAudited 等） */
  const netTotal = computed(() => ({
    beginBalance: netTotalRow.value.beginAudited,
    debitAmount: 0,
    creditAmount: 0,
    endBalance: netTotalRow.value.endAudited,
    unadjusted: netTotalRow.value.endUnadjusted,
    aje: originalTotal.value.endAdjustment - impairmentTotal.value.endAdjustment,
    rje: 0,
    audited: netTotalRow.value.endAudited,
    beginUnadjusted: netTotalRow.value.beginUnadjusted,
    beginAudited: netTotalRow.value.beginAudited,
    endUnadjusted: netTotalRow.value.endUnadjusted,
    endAudited: netTotalRow.value.endAudited,
    auditedChange: netTotalRow.value.auditedChange,
    auditedChangeRate: netTotalRow.value.auditedChangeRate,
  }))

  /** 净值身份校验：净值合计是否等于原值合计−减值合计 */
  const netIdentityDiff = computed(() => {
    const expected =
      originalTotal.value.endAudited - impairmentTotal.value.endAudited
    return Math.round((netTotalRow.value.endAudited - expected) * 100) / 100
  })

  const significantNetChanges = computed(() =>
    netRows.value.filter((r) => r.isSignificant),
  )

  const significantChangeItems = computed<H4SignificantChangeItem[]>(() =>
    significantNetChanges.value.map((r) => ({
      name: r.name,
      beginAudited: r.beginAudited,
      endAudited: r.endAudited,
      auditedChange: r.auditedChange,
      auditedChangeRate: r.auditedChangeRate,
    })),
  )

  // ─── CrossSheet 发布值 ─────────────────────────────────────────────────────

  const adjudicatedTotal: ComputedRef<number> = computed(() => netTotalRow.value.endAudited)

  /** 借/贷发生来自 H4-2 汇总（审定表本身无发生额列） */
  const debitTotal: ComputedRef<number> = computed(() => {
    const n = Number(allResponses.value.get(DEBIT_TOTAL_KEY)?.remark)
    if (Number.isFinite(n) && n !== 0) return n
    const fromDetail = Number(allResponses.value.get('H4-2-increase-total')?.remark)
    return Number.isFinite(fromDetail) ? fromDetail : 0
  })
  const creditTotal: ComputedRef<number> = computed(() => {
    const n = Number(allResponses.value.get(CREDIT_TOTAL_KEY)?.remark)
    if (Number.isFinite(n) && n !== 0) return n
    const fromDetail = Number(allResponses.value.get('H4-2-decrease-total')?.remark)
    return Number.isFinite(fromDetail) ? fromDetail : 0
  })

  // ─── TB / 报表核对 ─────────────────────────────────────────────────────────

  const tbUnadjusted = computed(() => tbData?.value?.unadjusted1605 ?? 0)
  const tbAudited = computed(() => tbData?.value?.audited1605 ?? 0)
  const tbDiff = computed(() => adjudicatedTotal.value - tbAudited.value)
  const isTbMatch = computed(() => Math.abs(tbDiff.value) < 0.01)
  const unadjustedVsTbDiff = computed(
    () => netTotalRow.value.endUnadjusted - tbUnadjusted.value,
  )

  /** (3) 与经审计的财务报表核对行 */
  const fsCompareRows = computed(() => {
    const emEnd = netTotalRow.value.endAudited
    const emBegin = netTotalRow.value.beginAudited
    const cipEnd = fsReconcile.value.cipEndAudited
    const cipBegin = fsReconcile.value.cipBeginAudited
    const sumEnd = cipEnd + emEnd
    const sumBegin = cipBegin + emBegin
    const fsEnd = fsReconcile.value.fsEndAmount
    const fsBegin = fsReconcile.value.fsBeginAmount
    return [
      { label: '在建工程审定数', endAudited: cipEnd, beginAudited: cipBegin, editable: true as const },
      { label: '工程物资审定数', endAudited: emEnd, beginAudited: emBegin, editable: false as const },
      { label: '在建工程与工程物资合计数', endAudited: sumEnd, beginAudited: sumBegin, editable: false as const },
      { label: '报表数', endAudited: fsEnd, beginAudited: fsBegin, editable: true as const },
      {
        label: '差异',
        endAudited: sumEnd - fsEnd,
        beginAudited: sumBegin - fsBegin,
        editable: false as const,
      },
    ]
  })

  // ─── H4-2 / H4-3 联动 ──────────────────────────────────────────────────────

  function _parseH42Rows(): any[] {
    const raw = _parseJson(allResponses.value, 'H4-2-rows')
    return Array.isArray(raw) ? raw : []
  }

  function _parseH43Nets(): { emAjeNet: number; impairAjeNet: number } {
    const raw = _parseJson(allResponses.value, 'H4-3-rows')
    if (!Array.isArray(raw)) return { emAjeNet: 0, impairAjeNet: 0 }
    let emAjeNet = 0
    let impairAjeNet = 0
    for (const r of raw) {
      const code = String(r.accountCode ?? '').trim()
      if (code !== '1605' && !code.startsWith('1605')) continue
      const cat = String(r.category ?? r.entryType ?? '')
      if (cat === '报表调整' || cat === 'RJE') continue
      const net = (Number(r.debitAmount ?? r.debit) || 0) - (Number(r.creditAmount ?? r.credit) || 0)
      const blob = `${r.accountName || ''}${r.description || ''}${r.reportItem || ''}`
      if (/减值/.test(blob)) {
        // 贷方补提准备：借−贷为负 → 减值段账项调整取反为正
        impairAjeNet += -net
      } else {
        emAjeNet += net
      }
    }
    return {
      emAjeNet: Math.round(emAjeNet * 100) / 100,
      impairAjeNet: Math.round(impairAjeNet * 100) / 100,
    }
  }

  function _parseH43EmAjeNet(): number {
    const n = _parseH43Nets()
    // 兼容旧展示：无减值行时合并展示净值影响（原值净额 − 减值补提）
    if (impairmentRows.value.length === 0) {
      return Math.round((n.emAjeNet - n.impairAjeNet) * 100) / 100
    }
    return n.emAjeNet
  }

  function _allocateEndAdj(details: H4AdjudicationRow[], net: number): void {
    if (details.length === 0) return
    if (Math.abs(net) < 0.005) {
      for (const r of details) {
        r.endAdjustment = 0
        _applyFormulas(r)
      }
      return
    }
    const weights = details.map((r) => Math.abs(r.endUnadjusted))
    const weightSum = calcSubtotal(weights)
    if (weightSum < 0.005) {
      const each = Math.round((net / details.length) * 100) / 100
      let allocated = 0
      details.forEach((r, i) => {
        const amt = i === details.length - 1
          ? Math.round((net - allocated) * 100) / 100
          : each
        allocated += amt
        r.endAdjustment = amt
        _applyFormulas(r)
      })
    } else {
      let allocated = 0
      details.forEach((r, i) => {
        const amt = i === details.length - 1
          ? Math.round((net - allocated) * 100) / 100
          : Math.round((net * Math.abs(r.endUnadjusted) / weightSum) * 100) / 100
        allocated += amt
        r.endAdjustment = amt
        _applyFormulas(r)
      })
    }
  }

  const h42CategoryTotals = computed(() => {
    const detailRows = _parseH42Rows().map((r) => ({
      category: String(r.category ?? '未分类'),
      beginAmount: Number(r.beginAmount) || 0,
      increaseSubtotal:
        Number(r.increaseSubtotal)
        || (Number(r.purchaseAmount) || 0) + (Number(r.otherIncrease) || 0),
      decreaseTotal:
        Number(r.decreaseTotal)
        || (Number(r.usageAmount) || 0)
          + (Number(r.returnAmount) || 0)
          + (Number(r.scrapAmount) || 0)
          + (Number(r.otherDecrease) || 0),
      endAmount: Number(r.endAmount) || 0,
      impairBegin: Number(r.impairBegin) || 0,
      impairEnd: Number(r.impairEnd) || 0,
      ajeBegin: Number(r.ajeBegin) || 0,
      ajeIncrease: Number(r.ajeIncrease) || 0,
      ajeDecrease: Number(r.ajeDecrease) || 0,
      ajeImpair: Number(r.ajeImpair) || 0,
      auditedEnd: Number(r.auditedEnd) || 0,
      auditedImpairEnd: Number(r.auditedImpairEnd) || 0,
      bookValueEnd: Number(r.bookValueEnd) || 0,
      auditedBookValue: Number(r.auditedBookValue) || 0,
      bookValueDiff: 0,
      rowCount: 1,
    }))
    // 按分类汇总（含调整）
    const map = new Map<string, {
      beginAmount: number
      endAmount: number
      ajeBegin: number
      endAdj: number
      impairBegin: number
      impairEnd: number
      ajeImpair: number
      increase: number
      decrease: number
    }>()
    for (const r of detailRows) {
      const cat = (r.category || '未分类').trim() || '未分类'
      const cur = map.get(cat) ?? {
        beginAmount: 0, endAmount: 0, ajeBegin: 0, endAdj: 0,
        impairBegin: 0, impairEnd: 0, ajeImpair: 0, increase: 0, decrease: 0,
      }
      cur.beginAmount += r.beginAmount
      cur.endAmount += r.endAmount
      cur.ajeBegin += r.ajeBegin
      // Excel F = R+T−V → ajeBegin+ajeIncrease−ajeDecrease；若已有 auditedEnd 则用差额
      const derivedEndAdj = r.auditedEnd
        ? r.auditedEnd - r.endAmount
        : r.ajeBegin + r.ajeIncrease - r.ajeDecrease
      cur.endAdj += derivedEndAdj
      cur.impairBegin += r.impairBegin
      cur.impairEnd += r.impairEnd
      cur.ajeImpair += r.ajeImpair
      cur.increase += r.increaseSubtotal
      cur.decrease += r.decreaseTotal
      map.set(cat, cur)
    }
    return map
  })

  const detailDiff = computed(() => {
    const detailNet = Number(allResponses.value.get('H4-2-detail-total')?.remark)
    if (Number.isFinite(detailNet) && detailNet !== 0) {
      return adjudicatedTotal.value - detailNet
    }
    // 回退：原值期末审定 vs H4-2 分类 endAmount 合计（未审口径时）
    let sum = 0
    for (const v of h42CategoryTotals.value.values()) sum += v.endAmount + v.endAdj
    return originalTotal.value.endAudited - sum
  })

  const h43EmAjeNet = computed(() => _parseH43EmAjeNet())
  const h43ImpairAjeNet = computed(() => _parseH43Nets().impairAjeNet)

  // ─── Persist ───────────────────────────────────────────────────────────────

  function _persist(): void {
    if (!onSave) return
    onSave(ROWS_KEY, _persistSlice(rows.value))
    onSave(ADJUDICATED_TOTAL_KEY, adjudicatedTotal.value)
    onSave(BEGIN_TOTAL_KEY, netTotalRow.value.beginAudited)
    onSave(END_TOTAL_KEY, netTotalRow.value.endAudited)

    // 重大变动列表 — 附注键直接消费
    const sig = significantChangeItems.value
    onSave(SIGNIFICANT_KEY, sig)
    onSave(SIGNIFICANT_COUNT_KEY, sig.length)

    // 借/贷：优先写 H4-2 汇总，供 CrossSheet 与检查表勾稽
    let inc = 0
    let dec = 0
    for (const v of h42CategoryTotals.value.values()) {
      inc += v.increase
      dec += v.decrease
    }
    if (inc !== 0 || dec !== 0) {
      onSave(DEBIT_TOTAL_KEY, Math.round(inc * 100) / 100)
      onSave(CREDIT_TOTAL_KEY, Math.round(dec * 100) / 100)
    }
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
      // 旧字段别名
      case 'beginBalance':
        row.beginUnadjusted = numVal
        break
      case 'unadjusted':
        row.endUnadjusted = numVal
        break
      case 'aje':
        row.endAdjustment = numVal
        break
      case 'rje':
        row.endAdjustment = (row.endAdjustment || 0) + numVal
        break
      default:
        return
    }
    _applyFormulas(row)
    _persist()
  }

  function addRow(name: string, section: H4AdjudicationSection = 'original'): void {
    if (!name?.trim()) return
    const trimmed = name.trim()
    rows.value.push(_blankRow(trimmed, section))
    // 原值新增时同步空减值行（同名）
    if (section === 'original') {
      const hasImp = rows.value.some(
        (r) => r.section === 'impairment' && r.name === trimmed && !r.isTotal,
      )
      if (!hasImp) rows.value.push(_blankRow(trimmed, 'impairment'))
    }
    _persist()
  }

  function deleteRow(rowId: string): void {
    const idx = rows.value.findIndex((r) => r.rowId === rowId)
    if (idx === -1) return
    const row = rows.value[idx]
    if (row.isTotal || row.isSubtotal) return
    const name = row.name
    const section = row.section
    rows.value.splice(idx, 1)
    // 删除原值时同步删同名减值
    if (section === 'original' && name) {
      const iIdx = rows.value.findIndex(
        (r) => r.section === 'impairment' && r.name === name && !r.isTotal,
      )
      if (iIdx !== -1) rows.value.splice(iIdx, 1)
    }
    _persist()
  }

  /**
   * 从 H4-2 按分类回填原值/减值（对齐 Excel 引用明细表分类小计）
   */
  function syncFromH42(mode: 'overwrite' | 'fillEmpty' = 'overwrite'): {
    applied: boolean
    message: string
    categories: number
  } {
    const totals = h42CategoryTotals.value
    if (totals.size === 0) {
      return { applied: false, message: 'H4-2 暂无明细数据', categories: 0 }
    }

    let touched = 0
    for (const [cat, t] of totals) {
      let orig = rows.value.find(
        (r) => r.section === 'original' && r.name === cat && !r.isTotal,
      )
      let imp = rows.value.find(
        (r) => r.section === 'impairment' && r.name === cat && !r.isTotal,
      )
      if (!orig) {
        orig = _blankRow(cat, 'original')
        rows.value.push(orig)
      }
      if (!imp) {
        imp = _blankRow(cat, 'impairment')
        rows.value.push(imp)
      }

      const fill = (row: H4AdjudicationRow, patch: Partial<H4AdjudicationRow>) => {
        for (const [k, v] of Object.entries(patch)) {
          if (mode === 'fillEmpty' && Number((row as any)[k]) !== 0) continue
          ;(row as any)[k] = v
        }
        _applyFormulas(row)
        touched++
      }

      fill(orig, {
        beginUnadjusted: Math.round(t.beginAmount * 100) / 100,
        beginAdjustment: Math.round(t.ajeBegin * 100) / 100,
        endUnadjusted: Math.round(t.endAmount * 100) / 100,
        endAdjustment: Math.round(t.endAdj * 100) / 100,
      })
      fill(imp, {
        beginUnadjusted: Math.round(t.impairBegin * 100) / 100,
        beginAdjustment: 0,
        endUnadjusted: Math.round(t.impairEnd * 100) / 100,
        endAdjustment: Math.round(t.ajeImpair * 100) / 100,
      })
    }
    _persist()
    return {
      applied: touched > 0,
      message: `已从 H4-2 回填 ${totals.size} 个分类`,
      categories: totals.size,
    }
  }

  /**
   * 将 H4-3 科目 1605 账项净额回写：
   * - 非减值行 → 原值段期末账项调整（按未审权重）
   * - 减值相关行 → 减值段期末账项调整（贷方补提为正）
   */
  function syncEndAdjFromH43(): { applied: boolean; message: string } {
    const { emAjeNet, impairAjeNet } = _parseH43Nets()
    const details = originalRows.value
    const impairDetails = impairmentRows.value
    if (details.length === 0 && impairDetails.length === 0) {
      return { applied: false, message: '审定表暂无分类行' }
    }

    if (details.length > 0) {
      // 无减值分类时，将减值净额并入原值（净值口径）
      const origNet = impairDetails.length === 0
        ? emAjeNet - impairAjeNet
        : emAjeNet
      _allocateEndAdj(details, origNet)
    }
    if (impairDetails.length > 0) {
      _allocateEndAdj(impairDetails, impairAjeNet)
    }

    _persist()
    const parts: string[] = []
    if (details.length > 0) {
      const shown = impairDetails.length === 0 ? emAjeNet - impairAjeNet : emAjeNet
      parts.push(`原值 ${shown.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}（${details.length}行）`)
    }
    if (impairDetails.length > 0) {
      parts.push(`减值 ${impairAjeNet.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}（${impairDetails.length}行）`)
    }
    return {
      applied: true,
      message: `已从 H4-3 回写期末账项调整：${parts.join('；')}`,
    }
  }

  async function publishAdjudicated(): Promise<void> {
    _persist()
    if (onWritebackTB) {
      await onWritebackTB(adjudicatedTotal.value)
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

  function updateFsField(field: keyof H4FsReconcile, value: number): void {
    fsReconcile.value = { ...fsReconcile.value, [field]: Number(value) || 0 }
    _persistFs()
  }

  /**
   * 将外部在建工程审定写入报表核对行（优先 H2-1，其次 TB·1604）
   */
  function seedCipFromExternal(
    src: H4CipSeedSource,
    mode: 'fillEmpty' | 'overwrite' = 'fillEmpty',
  ): { applied: boolean; message: string } {
    const end = Number(src.endAudited) || 0
    const begin = Number(src.beginAudited) || 0
    if (end === 0 && begin === 0) {
      return { applied: false, message: '来源金额均为 0，未写入' }
    }
    const empty =
      fsReconcile.value.cipEndAudited === 0 && fsReconcile.value.cipBeginAudited === 0
    if (mode === 'fillEmpty' && !empty) {
      return { applied: false, message: '在建工程已有录入，未覆盖（可强制带入）' }
    }
    fsReconcile.value = {
      ...fsReconcile.value,
      cipEndAudited: end,
      cipBeginAudited: begin || end,
    }
    _persistFs()
    const label = src.source === 'H2-1' ? 'H2-1' : src.source === 'event' ? 'H2审定事件' : 'TB·1604'
    return {
      applied: true,
      message: `已从 ${label} 带入在建工程：期末 ${end.toLocaleString('zh-CN', { minimumFractionDigits: 2 })} / 期初 ${(begin || end).toLocaleString('zh-CN', { minimumFractionDigits: 2 })}`,
    }
  }

  /** 从 TB·1604 带入（期末=审定优先，期初=opening 或未审） */
  function seedCipFromTb(mode: 'fillEmpty' | 'overwrite' = 'fillEmpty'): {
    applied: boolean
    message: string
  } {
    const tb = tbData?.value
    if (!tb) return { applied: false, message: '暂无 TB 取数' }
    const end =
      Number(tb.audited1604) || Number(tb.unadjusted1604) || 0
    const begin =
      Number(tb.opening1604) || Number(tb.unadjusted1604) || end
    if (!end && !begin) {
      return { applied: false, message: 'TB·1604 暂无余额' }
    }
    return seedCipFromExternal(
      { endAudited: end, beginAudited: begin, source: 'TB-1604' },
      mode,
    )
  }

  /**
   * 从 H2-1 原值行汇总带入；无数据时回退 TB·1604
   */
  function seedCipFromH21Rows(
    h21Rows: any[],
    mode: 'fillEmpty' | 'overwrite' = 'overwrite',
  ): { applied: boolean; message: string } {
    const { beginAudited, endAudited } = summarizeH21CostAudited(h21Rows)
    if (endAudited === 0 && beginAudited === 0) {
      return seedCipFromTb(mode === 'overwrite' ? 'overwrite' : 'fillEmpty')
    }
    return seedCipFromExternal(
      { endAudited, beginAudited, source: 'H2-1' },
      mode,
    )
  }

  /** 将重大变动列表写入说明(1)草稿（仅空时填入，避免覆盖人工说明） */
  function applySignificantNoteDraft(force = false): { applied: boolean; message: string } {
    const draft = buildSignificantFluctuationNote(significantChangeItems.value)
    if (!draft) {
      return { applied: false, message: '无净值重大变动项' }
    }
    if (!force && qualitativeNotes.value.fluctuation.trim()) {
      return { applied: false, message: '说明(1)已有内容，未覆盖' }
    }
    qualitativeNotes.value = { ...qualitativeNotes.value, fluctuation: draft }
    onSave?.(QUAL_KEY, { ...qualitativeNotes.value })
    return { applied: true, message: '已写入重大变动说明草稿' }
  }

  // TB·1604 首次可用且在建工程为空时自动带入
  watch(
    () => tbData?.value,
    (tb) => {
      if (!tb) return
      const hasCip = Number(tb.audited1604) || Number(tb.unadjusted1604) || Number(tb.opening1604)
      if (!hasCip) return
      if (fsReconcile.value.cipEndAudited !== 0 || fsReconcile.value.cipBeginAudited !== 0) return
      seedCipFromTb('fillEmpty')
    },
    { immediate: true },
  )

  function save(): void {
    _persist()
  }

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    rows,
    auditNote,
    auditConclusion,
    qualitativeNotes,
    fsReconcile,
    CHANGE_RATE_THRESHOLD,
    // 分段
    originalRows,
    impairmentRows,
    originalTotal,
    impairmentTotal,
    originalSubtotal,
    impairmentSubtotal,
    netRows,
    netTotalRow,
    netTotal,
    netIdentityDiff,
    significantNetChanges,
    significantChangeItems,
    // CrossSheet
    adjudicatedTotal,
    debitTotal,
    creditTotal,
    detailDiff,
    h43EmAjeNet,
    h43ImpairAjeNet,
    // TB / FS
    tbUnadjusted,
    tbAudited,
    tbDiff,
    isTbMatch,
    unadjustedVsTbDiff,
    fsCompareRows,
    // Actions
    updateCell,
    addRow,
    deleteRow,
    syncFromH42,
    syncEndAdjFromH43,
    save,
    load,
    publishAdjudicated,
    saveNote,
    saveConclusion,
    saveQualitativeNotes,
    applyConclusionTemplate,
    updateFsField,
    seedCipFromExternal,
    seedCipFromTb,
    seedCipFromH21Rows,
    applySignificantNoteDraft,
  }
}

export default useH4Adjudication
