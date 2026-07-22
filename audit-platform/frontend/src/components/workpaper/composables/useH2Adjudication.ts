/**
 * useH2Adjudication — H2-1 审定表 composable
 *
 * 对齐致同源模板「在建工程及减值准备审定表」：
 *   一、原值(1604) → 二、减值准备 → 三、净值(=原值−减值)
 * 列组（xlsx 12 列）：期初{未审/账项调整/审定} | 期末{未审/账项调整/审定}
 *   | 未审比较{变动额/率} | 审定比较{变动额/率}
 *
 * 数字化增强：
 * - 审定=未审+账项调整；净值=原值−减值（身份校验）
 * - 变动率≥30% 标红（须在审计说明(1)解释）
 * - 三角勾稽在 H2-2 实施，本表展示跨 sheet 差异
 * - 从 H2-2 回写工程行；从 H2-3 回写期末账项调整
 * - TB 核对：在建工程(1604)+工程物资(1605)
 *
 * Spec: .kiro/specs/h2-construction-in-progress/
 * Task: 3.3 | Requirements: 2.1-2.12（列结构以 xlsx/冲突决议为准）
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { calcAuditedAmount, calcSubtotal, calcTriangleWithTransfer } from './useH2FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

/**
 * H2-1 审定表行（原值 / 减值共用同一 12 列结构）
 */
export interface H2AdjudicationRow {
  rowId: string
  /** 项目名称（工程名称） */
  name: string
  beginUnadjusted: number
  beginAdjustment: number
  beginAudited: number
  endUnadjusted: number
  endAdjustment: number
  endAudited: number
  unadjustedChange: number
  unadjustedChangeRate: number | null
  auditedChange: number
  auditedChangeRate: number | null
  /** 变动率绝对值 ≥ 阈值 */
  isSignificant?: boolean
  isSubtotal?: boolean
  isTotal?: boolean
  isEditable?: boolean
}

/** 净值行（按工程派生：原值−减值） */
export interface H2NetValueRow {
  rowId: string
  name: string
  beginUnadjusted: number
  beginAudited: number
  endUnadjusted: number
  endAudited: number
  unadjustedChange: number
  unadjustedChangeRate: number | null
  auditedChange: number
  auditedChangeRate: number | null
  isSignificant: boolean
  isTotal?: boolean
}

/** TB / 试算核对行 */
export interface TbCompareRow {
  label: string
  audited: number
  tbAmount: number
  difference: number
}

/** 三角勾稽校验错误（来自 H2-2） */
export interface TriangleError {
  rowId: string
  name: string
  diff: number
}

/** 源模板审计说明结构化字段 */
export interface H2QualitativeNotes {
  /** (1) 净值重大变动原因（变动率≥30%） */
  fluctuation: string
  /** (2) 本期转入固定资产情况 */
  transferToFa: string
  /** (3) 其他说明（可选） */
  other: string
}

export type H2AdjudicationBlock = 'cost' | 'impair'

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_PREFIX = 'H2-1'
const ROWS_KEY = 'H2-1-rows'
const IMPAIR_ROWS_KEY = 'H2-1-impair-rows'
const NOTE_KEY = 'H2-1-audit-note'
const CONCLUSION_KEY = 'H2-1-audit-conclusion'
const QUAL_KEY = 'H2-1-qualitative-notes'
const MATERIALS_KEY = 'H2-1-materials'

/** 净值变动率阈值（%），对齐源模板红字提示 */
export const CHANGE_RATE_THRESHOLD = 30

const EMPTY_NOTES: H2QualitativeNotes = {
  fluctuation: '',
  transferToFa: '',
  other: '',
}

const CONCLUSION_TEMPLATES: Record<'A' | 'B' | 'C', string> = {
  A: '未见异常。经审定，在建工程及相关减值准备在所有重大方面公允反映。',
  B: '除上述重大不符事项应当作为调整事项予以调整外，其余未见异常。',
  C: '由于存在以下重大未调整事项（或审计范围受到限制无法获取充分、适当证据），不可确认。',
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function _calcChangeRate(current: number, previous: number): number | null {
  if (previous === 0 && current === 0) return 0
  if (previous === 0 && current !== 0) return null
  return ((current - previous) / Math.abs(previous)) * 100
}

function _isSignificant(rate: number | null): boolean {
  return rate != null && Math.abs(rate) >= CHANGE_RATE_THRESHOLD
}

function _round2(n: number): number {
  return Math.round(n * 100) / 100
}

function _blankRow(name = ''): H2AdjudicationRow {
  return {
    rowId: `row-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`,
    name,
    beginUnadjusted: 0,
    beginAdjustment: 0,
    beginAudited: 0,
    endUnadjusted: 0,
    endAdjustment: 0,
    endAudited: 0,
    unadjustedChange: 0,
    unadjustedChangeRate: 0,
    auditedChange: 0,
    auditedChangeRate: 0,
    isSignificant: false,
    isSubtotal: false,
    isTotal: false,
    isEditable: true,
  }
}

function _applyFormulas(row: H2AdjudicationRow): void {
  row.beginAudited = calcAuditedAmount(row.beginUnadjusted, row.beginAdjustment)
  row.endAudited = calcAuditedAmount(row.endUnadjusted, row.endAdjustment)
  row.unadjustedChange = row.endUnadjusted - row.beginUnadjusted
  row.unadjustedChangeRate = _calcChangeRate(row.endUnadjusted, row.beginUnadjusted)
  row.auditedChange = row.endAudited - row.beginAudited
  row.auditedChangeRate = _calcChangeRate(row.endAudited, row.beginAudited)
  row.isSignificant = _isSignificant(row.auditedChangeRate)
}

function _normalizeRow(raw: any): H2AdjudicationRow {
  const row: H2AdjudicationRow = {
    rowId: raw.rowId ?? `row-${Math.random().toString(36).slice(2, 10)}`,
    name: raw.name ?? '',
    beginUnadjusted: Number(raw.beginUnadjusted) || 0,
    beginAdjustment: Number(raw.beginAdjustment) || 0,
    beginAudited: 0,
    endUnadjusted: Number(raw.endUnadjusted) || 0,
    endAdjustment: Number(raw.endAdjustment) || 0,
    endAudited: 0,
    unadjustedChange: 0,
    unadjustedChangeRate: null,
    auditedChange: 0,
    auditedChangeRate: null,
    isSignificant: false,
    isSubtotal: raw.isSubtotal ?? false,
    isTotal: raw.isTotal ?? false,
    isEditable: raw.isEditable ?? true,
  }
  _applyFormulas(row)
  return row
}

function _sumRow(name: string, details: H2AdjudicationRow[]): H2AdjudicationRow {
  const beginUnadj = calcSubtotal(details.map((r) => r.beginUnadjusted))
  const beginAdj = calcSubtotal(details.map((r) => r.beginAdjustment))
  const endUnadj = calcSubtotal(details.map((r) => r.endUnadjusted))
  const endAdj = calcSubtotal(details.map((r) => r.endAdjustment))
  const row: H2AdjudicationRow = {
    rowId: `row-total-${name}`,
    name: '合计',
    beginUnadjusted: beginUnadj,
    beginAdjustment: beginAdj,
    beginAudited: 0,
    endUnadjusted: endUnadj,
    endAdjustment: endAdj,
    endAudited: 0,
    unadjustedChange: 0,
    unadjustedChangeRate: null,
    auditedChange: 0,
    auditedChangeRate: null,
    isSignificant: false,
    isSubtotal: false,
    isTotal: true,
    isEditable: false,
  }
  _applyFormulas(row)
  return row
}

function _persistSlice(rows: H2AdjudicationRow[]) {
  return rows
    .filter((r) => !r.isTotal)
    .map((r) => ({
      rowId: r.rowId,
      name: r.name,
      beginUnadjusted: r.beginUnadjusted,
      beginAdjustment: r.beginAdjustment,
      beginAudited: r.beginAudited,
      endUnadjusted: r.endUnadjusted,
      endAdjustment: r.endAdjustment,
      endAudited: r.endAudited,
      isSubtotal: r.isSubtotal || undefined,
      isEditable: r.isEditable,
    }))
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH2Adjudication(options: {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  isReadonly: Ref<boolean>
  /** TB 取数（科目 1604 / 可选 1605） */
  tbData?: Ref<{
    unadjusted_amount?: number
    audited_amount?: number
    materials_unadjusted?: number
    materials_audited?: number
  }>
  /** @deprecated 优先从 allResponses 自算；保留兼容 */
  detailTotals?: ComputedRef<{
    cipEnd: number
    endAudited?: number
    increase: number
    decrease: number
    transfer: number
  }>
  /** @deprecated 优先从 allResponses 自算 */
  transferSummary?: ComputedRef<{ totalTransfer: number; items: Array<{ name: string; amount: number }> }>
  onSave?: (itemId: string, value: any) => void
  onWritebackTB?: (auditedAmount: number) => Promise<void>
  onPublishEvent?: (event: string, payload: any) => void
}) {
  const costRows = ref<H2AdjudicationRow[]>([])
  const impairRows = ref<H2AdjudicationRow[]>([])
  const auditNote = ref('')
  const auditConclusion = ref('')
  const qualitativeNotes = ref<H2QualitativeNotes>({ ...EMPTY_NOTES })
  /** 工程物资审定/TB（源模板与试算核对） */
  const materialsAudited = ref(0)
  const materialsTb = ref(0)

  function _getJson(itemId: string): any {
    const item = options.allResponses.value.get(itemId)
    if (!item) return null
    const raw = item.remark ?? item.conclusion
    if (!raw) return null
    try {
      return JSON.parse(raw)
    } catch {
      return null
    }
  }

  function _getString(itemId: string): string {
    const item = options.allResponses.value.get(itemId)
    return (item?.remark ?? item?.conclusion ?? '') as string
  }

  function _parseH22Rows(): any[] {
    const resp = options.allResponses.value.get('H2-2-rows')
    const raw = resp?.remark ?? resp?.conclusion
    if (!raw) return []
    try {
      const parsed = JSON.parse(raw)
      return Array.isArray(parsed) ? parsed : []
    } catch {
      return []
    }
  }

  function _parseH25TransferTotal(): number {
    const resp = options.allResponses.value.get('H2-5-rows')
    const raw = resp?.remark ?? resp?.conclusion
    if (!raw) return 0
    try {
      const rows = JSON.parse(raw)
      if (!Array.isArray(rows)) return 0
      return rows.reduce((s: number, r: any) => s + (Number(r.transferAmount) || 0), 0)
    } catch {
      return 0
    }
  }

  function initFromAllResponses(): void {
    const costData = _getJson(ROWS_KEY)
    costRows.value =
      Array.isArray(costData) && costData.length > 0 ? costData.map(_normalizeRow) : []

    const impairData = _getJson(IMPAIR_ROWS_KEY)
    if (Array.isArray(impairData) && impairData.length > 0) {
      impairRows.value = impairData.map(_normalizeRow)
    } else {
      // 无减值存档：按原值工程名生成空减值行（对齐源模板「二、减值准备」）
      impairRows.value = costRows.value.map((r) => {
        const blank = _blankRow(r.name)
        blank.rowId = `imp-${r.rowId}`
        return blank
      })
    }

    auditNote.value = _getString(NOTE_KEY)
    auditConclusion.value = _getString(CONCLUSION_KEY)

    const notesRaw = _getJson(QUAL_KEY)
    qualitativeNotes.value = {
      fluctuation: String(notesRaw?.fluctuation ?? ''),
      transferToFa: String(notesRaw?.transferToFa ?? ''),
      other: String(notesRaw?.other ?? ''),
    }

    const mat = _getJson(MATERIALS_KEY)
    materialsAudited.value = Number(mat?.audited) || 0
    materialsTb.value = Number(mat?.tbAmount) || 0
  }

  watch(options.allResponses, () => initFromAllResponses(), { immediate: true })

  // ─── Computed: 明细 / 合计 ─────────────────────────────────────────────────

  const costDetailRows = computed(() =>
    costRows.value.filter((r) => !r.isSubtotal && !r.isTotal),
  )
  const impairDetailRows = computed(() =>
    impairRows.value.filter((r) => !r.isSubtotal && !r.isTotal),
  )

  /** @deprecated 兼容旧调用：等同 costDetailRows */
  const detailRows = costDetailRows

  const costTotalRow = computed(() => _sumRow('cost', costDetailRows.value))
  const impairTotalRow = computed(() => _sumRow('impair', impairDetailRows.value))

  /** @deprecated 兼容旧调用：等同 costTotalRow */
  const totalRow = costTotalRow

  /** 三、净值（按工程名对齐：原值−减值） */
  const netRows = computed<H2NetValueRow[]>(() => {
    const impairByName = new Map<string, H2AdjudicationRow>()
    for (const r of impairDetailRows.value) {
      impairByName.set(r.name, r)
    }
    const names = [
      ...new Set([
        ...costDetailRows.value.map((r) => r.name),
        ...impairDetailRows.value.map((r) => r.name),
      ]),
    ].filter(Boolean)

    const details: H2NetValueRow[] = names.map((name) => {
      const c = costDetailRows.value.find((r) => r.name === name)
      const i = impairByName.get(name)
      const beginUnadj = (c?.beginUnadjusted ?? 0) - (i?.beginUnadjusted ?? 0)
      const beginAud = (c?.beginAudited ?? 0) - (i?.beginAudited ?? 0)
      const endUnadj = (c?.endUnadjusted ?? 0) - (i?.endUnadjusted ?? 0)
      const endAud = (c?.endAudited ?? 0) - (i?.endAudited ?? 0)
      const unadjChange = endUnadj - beginUnadj
      const audChange = endAud - beginAud
      const unadjRate = _calcChangeRate(endUnadj, beginUnadj)
      const audRate = _calcChangeRate(endAud, beginAud)
      return {
        rowId: `net-${name}`,
        name,
        beginUnadjusted: beginUnadj,
        beginAudited: beginAud,
        endUnadjusted: endUnadj,
        endAudited: endAud,
        unadjustedChange: unadjChange,
        unadjustedChangeRate: unadjRate,
        auditedChange: audChange,
        auditedChangeRate: audRate,
        isSignificant: _isSignificant(audRate),
        isTotal: false,
      }
    })

    const beginUnadj = calcSubtotal(details.map((r) => r.beginUnadjusted))
    const beginAud = calcSubtotal(details.map((r) => r.beginAudited))
    const endUnadj = calcSubtotal(details.map((r) => r.endUnadjusted))
    const endAud = calcSubtotal(details.map((r) => r.endAudited))
    const audRate = _calcChangeRate(endAud, beginAud)
    details.push({
      rowId: 'net-total',
      name: '合计',
      beginUnadjusted: beginUnadj,
      beginAudited: beginAud,
      endUnadjusted: endUnadj,
      endAudited: endAud,
      unadjustedChange: endUnadj - beginUnadj,
      unadjustedChangeRate: _calcChangeRate(endUnadj, beginUnadj),
      auditedChange: endAud - beginAud,
      auditedChangeRate: audRate,
      isSignificant: _isSignificant(audRate),
      isTotal: true,
    })
    return details
  })

  const netTotalRow = computed(
    () => netRows.value.find((r) => r.isTotal) ?? netRows.value[netRows.value.length - 1],
  )

  const significantNetChanges = computed(() =>
    netRows.value.filter((r) => !r.isTotal && r.isSignificant),
  )

  /** 身份校验：净值合计 = 原值合计 − 减值合计 */
  const netIdentityDiff = computed(() => {
    const expected =
      costTotalRow.value.endAudited - impairTotalRow.value.endAudited
    return _round2((netTotalRow.value?.endAudited ?? 0) - expected)
  })

  // ─── TB / 交叉验证 ─────────────────────────────────────────────────────────

  const tbRow = computed(() => {
    const tb = options.tbData?.value
    return {
      tbUnadjusted: tb?.unadjusted_amount ?? 0,
      tbAudited: tb?.audited_amount ?? 0,
      materialsTbUnadjusted: tb?.materials_unadjusted ?? 0,
      // 1605 试算列以本表可编辑 materialsTb 为准（可由 TB 种子带入）
      materialsTbAudited: materialsTb.value,
    }
  })

  /** 与试算平衡表核对（源模板：在建工程 + 工程物资） */
  const tbCompareRows = computed<TbCompareRow[]>(() => {
    const cipAudited = costTotalRow.value.endAudited
    // 1604：优先 TB 审定；若尚未回写则回退未审，便于编制期对照
    const cipTb =
      tbRow.value.tbAudited !== 0 ? tbRow.value.tbAudited : tbRow.value.tbUnadjusted
    const matAud = materialsAudited.value
    const matTb = materialsTb.value
    return [
      {
        label: '在建工程审定数(1604)',
        audited: cipAudited,
        tbAmount: cipTb,
        difference: cipAudited - cipTb,
      },
      {
        label: '工程物资审定数(1605)',
        audited: matAud,
        tbAmount: matTb,
        difference: matAud - matTb,
      },
    ]
  })

  const diffRow = computed(() => {
    const amount = costTotalRow.value.endAudited - tbRow.value.tbAudited
    return { amount, isZero: Math.abs(amount) < 0.01 }
  })

  /** 原值期末未审合计 vs TB 未审（编制早期勾稽） */
  const unadjustedVsTbDiff = computed(
    () => costTotalRow.value.endUnadjusted - tbRow.value.tbUnadjusted,
  )

  /** H2-2 聚合（优先 options，否则从 allResponses 自算） */
  const h22Totals = computed(() => {
    if (options.detailTotals?.value) {
      return {
        endAudited: options.detailTotals.value.endAudited ?? options.detailTotals.value.cipEnd,
        transfer: options.detailTotals.value.transfer,
        impairEndAudited: 0,
      }
    }
    const rows = _parseH22Rows()
    let endAudited = 0
    let transfer = 0
    let impairEndAudited = 0
    for (const row of rows) {
      endAudited += Number(row.endAudited) || Number(row.cipEnd) || 0
      transfer += Number(row.transferAmount) || 0
      impairEndAudited +=
        Number(row.impairEndAud) || Number(row.impairmentEnd) || Number(row.impairment) || 0
    }
    return { endAudited, transfer, impairEndAudited }
  })

  const detailDiff = computed(
    () => costTotalRow.value.endAudited - (h22Totals.value.endAudited || 0),
  )

  const impairDetailDiff = computed(
    () => impairTotalRow.value.endAudited - (h22Totals.value.impairEndAudited || 0),
  )

  const transferDiff = computed(() => {
    const h22 = h22Totals.value.transfer
    const h25 = options.transferSummary?.value?.totalTransfer ?? _parseH25TransferTotal()
    return h22 - h25
  })

  /** H2-2 转固合计（供说明(2)自动带数） */
  const transferFromH22 = computed(() => h22Totals.value.transfer)

  const triangleErrors = computed<TriangleError[]>(() => {
    const h2Rows = _parseH22Rows()
    const errors: TriangleError[] = []
    for (const row of h2Rows) {
      const begin = Number(row.cipBegin) || 0
      const increaseTotal =
        Number(row.increaseTotal) ||
        (Number(row.increaseMaterial) || 0) +
          (Number(row.increaseLabor) || 0) +
          (Number(row.increaseMachinery) || 0) +
          (Number(row.increaseInterest) || 0) +
          (Number(row.increaseOther) || 0)
      const decrease = (Number(row.decrease) || 0) + (Number(row.transferOut) || 0)
      const transfer = Number(row.transferAmount) || 0
      const end = Number(row.cipEnd) || 0
      const diff = calcTriangleWithTransfer(begin, increaseTotal, decrease, transfer, end)
      if (Math.abs(diff) > 0.01) {
        errors.push({
          rowId: row.rowId ?? '',
          name: row.name ?? '未命名工程',
          diff,
        })
      }
    }
    return errors
  })

  // ─── Persist ───────────────────────────────────────────────────────────────

  function _persistCost(): void {
    options.onSave?.(ROWS_KEY, _persistSlice(costRows.value))
  }
  function _persistImpair(): void {
    options.onSave?.(IMPAIR_ROWS_KEY, _persistSlice(impairRows.value))
  }
  function _persistMaterials(): void {
    options.onSave?.(MATERIALS_KEY, {
      audited: materialsAudited.value,
      tbAmount: materialsTb.value,
    })
  }

  function _recalcBlock(block: H2AdjudicationBlock): void {
    const list = block === 'cost' ? costRows.value : impairRows.value
    for (const r of list) {
      if (r.isTotal) continue
      _applyFormulas(r)
    }
  }

  // ─── Actions ───────────────────────────────────────────────────────────────

  function updateCell(
    block: H2AdjudicationBlock,
    rowId: string,
    field: string,
    value: any,
  ): void {
    if (options.isReadonly.value) return
    const list = block === 'cost' ? costRows.value : impairRows.value
    const row = list.find((r) => r.rowId === rowId)
    if (!row || row.isTotal) return

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
    if (block === 'cost') _persistCost()
    else _persistImpair()
  }

  function addProjectRow(name: string): void {
    if (options.isReadonly.value) return
    if (!name?.trim()) return
    const trimmed = name.trim()
    const cost = _blankRow(trimmed)
    const impair = _blankRow(trimmed)
    impair.rowId = `imp-${cost.rowId}`
    costRows.value.push(cost)
    impairRows.value.push(impair)
    _persistCost()
    _persistImpair()
  }

  function removeProjectRow(rowId: string): void {
    if (options.isReadonly.value) return
    const cIdx = costRows.value.findIndex((r) => r.rowId === rowId)
    if (cIdx !== -1) {
      const name = costRows.value[cIdx].name
      costRows.value.splice(cIdx, 1)
      const iIdx = impairRows.value.findIndex((r) => r.name === name || r.rowId === `imp-${rowId}`)
      if (iIdx !== -1) impairRows.value.splice(iIdx, 1)
      _persistCost()
      _persistImpair()
      return
    }
    const iIdx = impairRows.value.findIndex((r) => r.rowId === rowId)
    if (iIdx !== -1) {
      impairRows.value.splice(iIdx, 1)
      _persistImpair()
    }
  }

  /**
   * 从 H2-2 明细回写原值/减值工程行（覆盖同名工程金额，保留已有调整意图时可仅填空）
   */
  function syncFromH22(mode: 'fillEmpty' | 'overwrite' = 'overwrite'): {
    applied: boolean
    message: string
  } {
    if (options.isReadonly.value) return { applied: false, message: '只读模式' }
    const h22 = _parseH22Rows()
    if (h22.length === 0) {
      return { applied: false, message: 'H2-2 暂无明细行，请先在明细表录入工程' }
    }

    const costByName = new Map(costDetailRows.value.map((r) => [r.name, r]))
    const impairByName = new Map(impairDetailRows.value.map((r) => [r.name, r]))
    let touched = 0

    for (const src of h22) {
      const name = String(src.name || '').trim() || '未命名工程'
      const beginUnadj = Number(src.cipBegin) || 0
      const beginAud = Number(src.beginAudited) || beginUnadj
      const endUnadj = Number(src.cipEnd) || 0
      const endAud = Number(src.endAudited) || endUnadj
      const beginAdj = _round2(beginAud - beginUnadj)
      const endAdj = _round2(endAud - endUnadj)

      let cost = costByName.get(name)
      if (!cost) {
        cost = _blankRow(name)
        costRows.value.push(cost)
        costByName.set(name, cost)
      }
      const costEmpty =
        cost.beginUnadjusted === 0 &&
        cost.endUnadjusted === 0 &&
        cost.beginAdjustment === 0 &&
        cost.endAdjustment === 0
      if (mode === 'overwrite' || costEmpty) {
        cost.beginUnadjusted = beginUnadj
        cost.beginAdjustment = beginAdj
        cost.endUnadjusted = endUnadj
        cost.endAdjustment = endAdj
        _applyFormulas(cost)
        touched++
      }

      const iBeginUnadj = Number(src.impairmentBegin) || 0
      const iBeginAud = Number(src.impairBeginAud) || iBeginUnadj
      const iEndUnadj = Number(src.impairmentEnd) || 0
      const iEndAud = Number(src.impairEndAud) || iEndUnadj

      let impair = impairByName.get(name)
      if (!impair) {
        impair = _blankRow(name)
        impair.rowId = `imp-${cost.rowId}`
        impairRows.value.push(impair)
        impairByName.set(name, impair)
      }
      const impairEmpty =
        impair.beginUnadjusted === 0 &&
        impair.endUnadjusted === 0 &&
        impair.beginAdjustment === 0 &&
        impair.endAdjustment === 0
      if (mode === 'overwrite' || impairEmpty) {
        impair.beginUnadjusted = iBeginUnadj
        impair.beginAdjustment = _round2(iBeginAud - iBeginUnadj)
        impair.endUnadjusted = iEndUnadj
        impair.endAdjustment = _round2(iEndAud - iEndUnadj)
        _applyFormulas(impair)
      }
    }

    // 自动带入转固说明（仅空时）
    const transferAmt = h22Totals.value.transfer
    if (transferAmt !== 0 && !qualitativeNotes.value.transferToFa.trim()) {
      qualitativeNotes.value = {
        ...qualitativeNotes.value,
        transferToFa: `本期自在建工程转入固定资产合计 ${_round2(transferAmt).toLocaleString('zh-CN', { minimumFractionDigits: 2 })} 元（取自 H2-2，详见 H2-5）。`,
      }
      options.onSave?.(QUAL_KEY, { ...qualitativeNotes.value })
    }

    _persistCost()
    _persistImpair()
    return {
      applied: true,
      message: `已从 H2-2 同步 ${h22.length} 个工程（写入 ${touched} 处原值行）`,
    }
  }

  function syncEndAdjustmentFromH23(cipAjeNet: number): { applied: boolean; message: string } {
    if (options.isReadonly.value) return { applied: false, message: '只读模式' }
    const details = costDetailRows.value
    if (details.length === 0) {
      return { applied: false, message: 'H2-1 暂无工程项目行，请先从 H2-2 同步或新增工程' }
    }
    if (Math.abs(cipAjeNet) < 0.005) {
      for (const r of details) r.endAdjustment = 0
      _recalcBlock('cost')
      _persistCost()
      return { applied: true, message: 'H2-3 的 1604 账项净额为 0，已清空各行期末账项调整' }
    }

    if (details.length === 1) {
      details[0].endAdjustment = _round2(cipAjeNet)
    } else {
      const weights = details.map((r) => Math.abs(r.endUnadjusted))
      const weightSum = weights.reduce((s, w) => s + w, 0)
      let allocated = 0
      details.forEach((r, i) => {
        if (i === details.length - 1) {
          r.endAdjustment = _round2(cipAjeNet - allocated)
        } else {
          const share =
            weightSum > 0 ? (cipAjeNet * weights[i]) / weightSum : cipAjeNet / details.length
          const amt = _round2(share)
          r.endAdjustment = amt
          allocated += amt
        }
      })
    }
    _recalcBlock('cost')
    _persistCost()
    return {
      applied: true,
      message: `已将 H2-3 的 1604 账项净额 ${cipAjeNet.toLocaleString('zh-CN', { minimumFractionDigits: 2 })} 回写至 ${details.length} 行期末账项调整`,
    }
  }

  async function publishAdjudicated(): Promise<void> {
    const auditedTotal = costTotalRow.value.endAudited
    const impairEnd = impairTotalRow.value.endAudited
    const beginCost = costTotalRow.value.beginAudited
    const beginImpair = impairTotalRow.value.beginAudited
    if (options.onWritebackTB) await options.onWritebackTB(auditedTotal)
    if (options.onPublishEvent) {
      options.onPublishEvent('substantive:adjudicated', {
        wpCode: 'H2',
        accountCode: '1604',
        auditedAmount: auditedTotal,
        timestamp: Date.now(),
        // 兼容旧载荷
        wp_code: 'H2',
        account_codes: ['1604'],
        audited_amount: auditedTotal,
        begin_audited: beginCost,
        end_audited: auditedTotal,
        impair_audited: impairEnd,
        begin_impair_audited: beginImpair,
        net_audited: netTotalRow.value?.endAudited ?? auditedTotal - impairEnd,
        // H4 国企披露 CIP 行自动带入
        cip: {
          endBook: auditedTotal,
          endImpairment: impairEnd,
          beginBook: beginCost,
          beginImpairment: beginImpair,
        },
      })
    }
  }

  function saveNote(note: string): void {
    auditNote.value = note
    options.onSave?.(NOTE_KEY, note)
  }

  function saveConclusion(conclusion: string): void {
    auditConclusion.value = conclusion
    options.onSave?.(CONCLUSION_KEY, conclusion)
  }

  function applyConclusionTemplate(key: 'A' | 'B' | 'C'): void {
    if (options.isReadonly.value) return
    saveConclusion(CONCLUSION_TEMPLATES[key])
  }

  function saveQualitativeNotes(patch?: Partial<H2QualitativeNotes>): void {
    if (patch) qualitativeNotes.value = { ...qualitativeNotes.value, ...patch }
    options.onSave?.(QUAL_KEY, { ...qualitativeNotes.value })
  }

  function updateMaterials(field: 'audited' | 'tbAmount', value: number): void {
    if (options.isReadonly.value) return
    if (field === 'audited') materialsAudited.value = Number(value) || 0
    else materialsTb.value = Number(value) || 0
    _persistMaterials()
  }

  /**
   * 从 TB 带入工程物资审定/试算数（源模板与试算核对 1605）。
   * fillEmpty：仅空值时写入；overwrite：强制覆盖。
   */
  function seedMaterialsFromTb(mode: 'fillEmpty' | 'overwrite' = 'fillEmpty'): {
    applied: boolean
    message: string
  } {
    if (options.isReadonly.value) return { applied: false, message: '只读模式' }
    const tb = options.tbData?.value
    const matUnadj = Number(tb?.materials_unadjusted ?? 0) || 0
    const matAud = Number(tb?.materials_audited ?? tb?.materials_unadjusted ?? 0) || 0
    if (matUnadj === 0 && matAud === 0 && !tb) {
      return { applied: false, message: '暂无 TB 工程物资(1605)取数' }
    }
    const empty =
      materialsAudited.value === 0 && materialsTb.value === 0
    if (mode === 'fillEmpty' && !empty) {
      return { applied: false, message: '工程物资已有录入，未覆盖（可强制从 TB 带入）' }
    }
    materialsAudited.value = matAud || matUnadj
    materialsTb.value = matAud || matUnadj
    _persistMaterials()
    return {
      applied: true,
      message: `已从 TB 带入工程物资(1605) ${materialsAudited.value.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}`,
    }
  }

  // 首次有 TB 且物资为空时自动带入
  watch(
    () => options.tbData?.value,
    (tb) => {
      if (!tb || options.isReadonly.value) return
      if (materialsAudited.value === 0 && materialsTb.value === 0) {
        const mat = Number(tb.materials_audited ?? tb.materials_unadjusted ?? 0) || 0
        if (mat !== 0) {
          materialsAudited.value = mat
          materialsTb.value = mat
          _persistMaterials()
        }
      }
    },
    { immediate: true, deep: true },
  )

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    CHANGE_RATE_THRESHOLD,
    CONCLUSION_TEMPLATES,

    costRows,
    impairRows,
    /** @deprecated 兼容：指向 costRows */
    rows: costRows,
    auditNote,
    auditConclusion,
    qualitativeNotes,
    materialsAudited,
    materialsTb,

    costDetailRows,
    impairDetailRows,
    detailRows,
    costTotalRow,
    impairTotalRow,
    totalRow,
    netRows,
    netTotalRow,
    significantNetChanges,
    netIdentityDiff,

    tbRow,
    tbCompareRows,
    diffRow,
    unadjustedVsTbDiff,
    detailDiff,
    impairDetailDiff,
    transferDiff,
    transferFromH22,
    triangleErrors,

    updateCell,
    addProjectRow,
    removeProjectRow,
    syncFromH22,
    syncEndAdjustmentFromH23,
    publishAdjudicated,
    saveNote,
    saveConclusion,
    applyConclusionTemplate,
    saveQualitativeNotes,
    updateMaterials,
    seedMaterialsFromTb,
    initFromAllResponses,
  }
}

export default useH2Adjudication

