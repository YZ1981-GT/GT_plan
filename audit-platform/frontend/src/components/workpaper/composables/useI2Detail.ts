/**
 * useI2Detail — I2-2 开发支出明细表
 *
 * 对齐致同 Excel「开发支出明细表 I2-2」滚动勾稽：
 *   未审数(期初/增加/减少转无形·转损益/期末)
 *   → 期初调整 + 账项调整(增/减)
 *   → 审定数(公式列) → 与无形资产/存货勾稽差异 + 研发进度
 *
 * Excel 公式：
 *   G = B+C-E-F
 *   L = B+H ; M = C+I ; N = E+J ; O = F+K ; P = L+M-N-O ; R = P-Q
 *
 * 联动：
 *   - 从 I2-3 调整分录汇总同步账项调整列（按项目名匹配说明）
 *   - 兼容旧字段 capBeginAmount/capIncrease/transferToI1/capEndAmount
 *   - 附加「本期投入」「项目基础」区段供检查表引用
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import {
  calcAssetEndBalance,
  calcNetValue,
  calcSubtotal,
  calcChangeRate,
  calcVarianceFromExpected,
} from './useI2FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export const I2_INCREASE_METHODS = ['内部开发支出', '其他增加', ''] as const

export interface I2DetailRow {
  rowId: string

  // ── Excel 主表：项目 ──
  projectName: string
  projectCode: string
  /** 本期增加方式（内部开发支出/其他增加） */
  increaseMethod: string

  // ── 未审数 B~G ──
  unadjOpening: number
  unadjIncrease: number
  unadjDecToIA: number
  unadjDecToPL: number
  /** 公式 G = B+C-E-F */
  unadjEnding: number

  // ── 期初调整 H + 账项调整 I~K ──
  openingAdj: number
  ajeIncrease: number
  ajeDecToIA: number
  ajeDecToPL: number

  // ── 审定数 L~P（公式）──
  auditedOpening: number
  auditedIncrease: number
  auditedDecToIA: number
  auditedDecToPL: number
  auditedEnding: number

  // ── 核对 Q~T ──
  relatedIAAuditedEnd: number
  /** 公式 R = P-Q */
  diffVsIA: number
  rdProgress: string
  remark: string

  // ── 兼容旧字段 / 跨 sheet ──
  approvalDate: string
  phase: string
  manager: string
  startDate: string
  endDate: string
  budget: number
  progress: number
  capitalizationStart: string
  status: string
  materialCurrent: number
  materialAccum: number
  laborCurrent: number
  laborAccum: number
  depreciationCurrent: number
  depreciationAccum: number
  amortizationCurrent: number
  amortizationAccum: number
  otherCurrent: number
  otherAccum: number
  totalCurrent: number
  totalAccum: number
  investmentRemark: string
  validationFlag: string
  investmentSource: string
  capStartDate: string
  /** @deprecated alias → unadjOpening */
  capBeginAmount: number
  /** @deprecated alias → unadjIncrease */
  capIncrease: number
  /** @deprecated = unadjDecToIA + unadjDecToPL */
  capDecrease: number
  /** @deprecated alias → unadjEnding */
  capEndAmount: number
  /** @deprecated alias → auditedDecToIA / unadjDecToIA */
  transferToI1: number
  transferDate: string
  transferAssetName: string
  capAmortization: number
  capImpairment: number
  capNetValue: number
  completionRate: number
  acceptanceDate: string
  /** @deprecated alias → auditedEnding */
  auditedEnd: number
  adjustedBalance: number
  yoyChange: number | null
  expectedValue: number
  variance: number
  exceedFlag: string
  conclusion: string
  priorEnd: number
  adjReference: string
}

export interface I2AjeLinkage {
  i23AjeNet: number
  detailAjeNet: number
  diff: number
  hasWarning: boolean
  i23RowCount: number
}

export type I2DetailColType = 'text' | 'number' | 'formula' | 'date' | 'select'

export interface I2DetailColumn {
  key: string
  label: string
  width: number
  editable: boolean
  type: I2DetailColType
  tooltip?: string
  options?: readonly string[]
  group?: string
  emphasis?: boolean
}

const ITEM_ID_ROWS = 'I2-2-rows'
const I23_ROWS_KEY = 'I2-3-rows'
const LEGACY_I23_KEY = 'I2-3-entries'
const PHASE_OPTIONS = ['研究', '开发', '已资本化']
const STATUS_OPTIONS = ['进行中', '已完成', '已暂停', '已终止']
const TOL = 0.01

function _num(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function _str(v: unknown): string {
  return v == null ? '' : String(v)
}

function generateRowId(): string {
  return `i22-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`
}

function emptyRow(partial?: Partial<I2DetailRow>): I2DetailRow {
  const row: I2DetailRow = {
    rowId: generateRowId(),
    projectName: '',
    projectCode: '',
    increaseMethod: '内部开发支出',
    unadjOpening: 0,
    unadjIncrease: 0,
    unadjDecToIA: 0,
    unadjDecToPL: 0,
    unadjEnding: 0,
    openingAdj: 0,
    ajeIncrease: 0,
    ajeDecToIA: 0,
    ajeDecToPL: 0,
    auditedOpening: 0,
    auditedIncrease: 0,
    auditedDecToIA: 0,
    auditedDecToPL: 0,
    auditedEnding: 0,
    relatedIAAuditedEnd: 0,
    diffVsIA: 0,
    rdProgress: '',
    remark: '',
    approvalDate: '',
    phase: '',
    manager: '',
    startDate: '',
    endDate: '',
    budget: 0,
    progress: 0,
    capitalizationStart: '',
    status: '进行中',
    materialCurrent: 0,
    materialAccum: 0,
    laborCurrent: 0,
    laborAccum: 0,
    depreciationCurrent: 0,
    depreciationAccum: 0,
    amortizationCurrent: 0,
    amortizationAccum: 0,
    otherCurrent: 0,
    otherAccum: 0,
    totalCurrent: 0,
    totalAccum: 0,
    investmentRemark: '',
    validationFlag: '',
    investmentSource: '',
    capStartDate: '',
    capBeginAmount: 0,
    capIncrease: 0,
    capDecrease: 0,
    capEndAmount: 0,
    transferToI1: 0,
    transferDate: '',
    transferAssetName: '',
    capAmortization: 0,
    capImpairment: 0,
    capNetValue: 0,
    completionRate: 0,
    acceptanceDate: '',
    auditedEnd: 0,
    adjustedBalance: 0,
    yoyChange: null,
    expectedValue: 0,
    variance: 0,
    exceedFlag: '',
    conclusion: '',
    priorEnd: 0,
    adjReference: '',
  }
  Object.assign(row, partial)
  return row
}

/** 导出纯函数供单测 */
export function recalcI2DetailRow(row: I2DetailRow): void {
  // 兼容：若只改了旧字段，回填 Excel 未审列
  if (!row.unadjOpening && row.capBeginAmount) row.unadjOpening = row.capBeginAmount
  if (!row.unadjIncrease && row.capIncrease) row.unadjIncrease = row.capIncrease
  if (!row.unadjDecToIA && row.transferToI1) row.unadjDecToIA = row.transferToI1
  if (!row.unadjDecToPL && row.capDecrease && !row.unadjDecToIA) {
    // 旧版只有合计数：全部视为转损益以外的减少，优先保留 transfer
    row.unadjDecToPL = Math.max(0, row.capDecrease - row.unadjDecToIA)
  }

  row.unadjEnding = calcAssetEndBalance(
    row.unadjOpening,
    row.unadjIncrease,
    row.unadjDecToIA + row.unadjDecToPL,
  )

  row.auditedOpening = row.unadjOpening + row.openingAdj
  row.auditedIncrease = row.unadjIncrease + row.ajeIncrease
  row.auditedDecToIA = row.unadjDecToIA + row.ajeDecToIA
  row.auditedDecToPL = row.unadjDecToPL + row.ajeDecToPL
  row.auditedEnding = calcAssetEndBalance(
    row.auditedOpening,
    row.auditedIncrease,
    row.auditedDecToIA + row.auditedDecToPL,
  )
  row.diffVsIA = row.auditedEnding - row.relatedIAAuditedEnd

  // 回写别名供 I2-6/I2-7/跨 sheet（唯一写回点；新代码请读写 unadj*/audited*）
  syncLegacyAliases(row)

  row.totalCurrent = calcSubtotal([
    row.materialCurrent, row.laborCurrent, row.depreciationCurrent,
    row.amortizationCurrent, row.otherCurrent,
  ])
  row.totalAccum = calcSubtotal([
    row.materialAccum, row.laborAccum, row.depreciationAccum,
    row.amortizationAccum, row.otherAccum,
  ])
  row.capNetValue = calcNetValue(row.capEndAmount, row.capAmortization + row.capImpairment)
  row.yoyChange = calcChangeRate(row.auditedEnd, row.priorEnd)
  row.variance = calcVarianceFromExpected(row.auditedEnd, row.expectedValue)
}

/** 将规范字段同步到遗留别名，避免双轨手工维护 */
export function syncLegacyAliases(row: I2DetailRow): void {
  row.capBeginAmount = row.unadjOpening
  row.capIncrease = row.unadjIncrease
  row.capDecrease = row.unadjDecToIA + row.unadjDecToPL
  row.capEndAmount = row.unadjEnding
  row.transferToI1 = row.auditedDecToIA
  row.auditedEnd = row.auditedEnding
  row.adjustedBalance = row.auditedEnding
  row.progress = row.progress || 0
  if (row.rdProgress && !row.completionRate) {
    const m = String(row.rdProgress).match(/(\d+(?:\.\d+)?)\s*%?/)
    if (m) row.completionRate = Number(m[1])
  }
}

export function normalizeI2DetailRow(raw: any): I2DetailRow {
  const row = emptyRow({
    rowId: _str(raw.rowId) || generateRowId(),
    projectName: _str(raw.projectName),
    projectCode: _str(raw.projectCode || raw.projectNo),
    increaseMethod: _str(raw.increaseMethod) || '内部开发支出',
    unadjOpening: _num(raw.unadjOpening ?? raw.capBeginAmount ?? raw.capitalizedBegin),
    unadjIncrease: _num(raw.unadjIncrease ?? raw.capIncrease ?? raw.capitalizedIncrease),
    unadjDecToIA: _num(raw.unadjDecToIA ?? raw.transferToI1 ?? raw.transferToIntangible),
    unadjDecToPL: _num(raw.unadjDecToPL),
    openingAdj: _num(raw.openingAdj),
    ajeIncrease: _num(raw.ajeIncrease),
    ajeDecToIA: _num(raw.ajeDecToIA),
    ajeDecToPL: _num(raw.ajeDecToPL),
    relatedIAAuditedEnd: _num(raw.relatedIAAuditedEnd),
    rdProgress: _str(raw.rdProgress),
    remark: _str(raw.remark),
    approvalDate: _str(raw.approvalDate),
    phase: _str(raw.phase),
    manager: _str(raw.manager),
    startDate: _str(raw.startDate),
    endDate: _str(raw.endDate),
    budget: _num(raw.budget),
    progress: _num(raw.progress),
    capitalizationStart: _str(raw.capitalizationStart || raw.capStartDate),
    status: _str(raw.status) || '进行中',
    materialCurrent: _num(raw.materialCurrent ?? raw.materialInput),
    materialAccum: _num(raw.materialAccum),
    laborCurrent: _num(raw.laborCurrent ?? raw.laborInput),
    laborAccum: _num(raw.laborAccum),
    depreciationCurrent: _num(raw.depreciationCurrent ?? raw.depreciationInput),
    depreciationAccum: _num(raw.depreciationAccum),
    amortizationCurrent: _num(raw.amortizationCurrent),
    amortizationAccum: _num(raw.amortizationAccum),
    otherCurrent: _num(raw.otherCurrent ?? raw.otherInput),
    otherAccum: _num(raw.otherAccum),
    investmentRemark: _str(raw.investmentRemark),
    validationFlag: _str(raw.validationFlag),
    investmentSource: _str(raw.investmentSource),
    capStartDate: _str(raw.capStartDate || raw.capitalizationStart),
    capBeginAmount: _num(raw.capBeginAmount),
    capIncrease: _num(raw.capIncrease),
    capDecrease: _num(raw.capDecrease ?? raw.capitalizedDecrease),
    transferToI1: _num(raw.transferToI1 ?? raw.transferToIntangible),
    transferDate: _str(raw.transferDate),
    transferAssetName: _str(raw.transferAssetName),
    capAmortization: _num(raw.capAmortization),
    capImpairment: _num(raw.capImpairment),
    completionRate: _num(raw.completionRate),
    acceptanceDate: _str(raw.acceptanceDate),
    expectedValue: _num(raw.expectedValue),
    exceedFlag: _str(raw.exceedFlag),
    conclusion: _str(raw.conclusion),
    priorEnd: _num(raw.priorEnd),
    adjReference: _str(raw.adjReference),
  })
  // 旧数据仅有 capDecrease：拆到转无形后剩余进转损益
  if (!raw.unadjDecToPL && raw.capDecrease != null) {
    const dec = _num(raw.capDecrease)
    if (dec > row.unadjDecToIA) row.unadjDecToPL = dec - row.unadjDecToIA
  }
  recalcI2DetailRow(row)
  return row
}

/** 行级账项调整净额（对 1717：增 - 减） */
export function rowAjeNet(row: I2DetailRow): number {
  return row.ajeIncrease - row.ajeDecToIA - row.ajeDecToPL
}

export function useI2Detail(params: {
  allResponses: Ref<Map<string, any>>
  saveResponses: (sheetCode: string, data: Record<string, any>) => Promise<void>
  adjEndSubtotal?: Ref<number>
}) {
  const { allResponses, saveResponses } = params

  const rows = ref<I2DetailRow[]>([])
  const activeSegment = ref(0)
  const activeRowIndex = ref(-1)

  function _getJson(key: string): any {
    const item = allResponses.value.get(key)
    if (!item) return null
    const raw = item.remark ?? item.conclusion ?? item
    if (raw == null) return null
    if (typeof raw === 'object') return raw
    try { return JSON.parse(raw as string) } catch { return null }
  }

  function _loadRows(): void {
    const parsed = _getJson(ITEM_ID_ROWS)
    if (Array.isArray(parsed) && parsed.length > 0) {
      rows.value = parsed.map(normalizeI2DetailRow)
    } else {
      rows.value = []
    }
  }

  function recalcAll(): void {
    for (const row of rows.value) recalcI2DetailRow(row)
  }

  watch(allResponses, () => _loadRows(), { immediate: true })

  const totalRow: ComputedRef<I2DetailRow> = computed(() => {
    const r = rows.value
    const t = emptyRow({
      rowId: '__total__',
      projectName: '合计',
      unadjOpening: calcSubtotal(r.map((x) => x.unadjOpening)),
      unadjIncrease: calcSubtotal(r.map((x) => x.unadjIncrease)),
      unadjDecToIA: calcSubtotal(r.map((x) => x.unadjDecToIA)),
      unadjDecToPL: calcSubtotal(r.map((x) => x.unadjDecToPL)),
      openingAdj: calcSubtotal(r.map((x) => x.openingAdj)),
      ajeIncrease: calcSubtotal(r.map((x) => x.ajeIncrease)),
      ajeDecToIA: calcSubtotal(r.map((x) => x.ajeDecToIA)),
      ajeDecToPL: calcSubtotal(r.map((x) => x.ajeDecToPL)),
      relatedIAAuditedEnd: calcSubtotal(r.map((x) => x.relatedIAAuditedEnd)),
      budget: calcSubtotal(r.map((x) => x.budget)),
      materialCurrent: calcSubtotal(r.map((x) => x.materialCurrent)),
      materialAccum: calcSubtotal(r.map((x) => x.materialAccum)),
      laborCurrent: calcSubtotal(r.map((x) => x.laborCurrent)),
      laborAccum: calcSubtotal(r.map((x) => x.laborAccum)),
      depreciationCurrent: calcSubtotal(r.map((x) => x.depreciationCurrent)),
      depreciationAccum: calcSubtotal(r.map((x) => x.depreciationAccum)),
      amortizationCurrent: calcSubtotal(r.map((x) => x.amortizationCurrent)),
      amortizationAccum: calcSubtotal(r.map((x) => x.amortizationAccum)),
      otherCurrent: calcSubtotal(r.map((x) => x.otherCurrent)),
      otherAccum: calcSubtotal(r.map((x) => x.otherAccum)),
      transferToI1: calcSubtotal(r.map((x) => x.transferToI1)),
      priorEnd: calcSubtotal(r.map((x) => x.priorEnd)),
      expectedValue: calcSubtotal(r.map((x) => x.expectedValue)),
    })
    recalcI2DetailRow(t)
    return t
  })

  const crossValidation = computed(() => {
    const adjEnd = params.adjEndSubtotal?.value ?? 0
    const detailEnd = totalRow.value.auditedEnding
    const diff = detailEnd - adjEnd
    return {
      detailEndTotal: detailEnd,
      adjEndTotal: adjEnd,
      difference: diff,
      hasWarning: adjEnd !== 0 && Math.abs(diff) > TOL,
    }
  })

  /** I2-3 1717 账项净额 vs 明细账项调整合计 */
  const ajeLinkage: ComputedRef<I2AjeLinkage> = computed(() => {
    const i23 = _getJson(I23_ROWS_KEY) || _getJson(LEGACY_I23_KEY)
    let i23AjeNet = 0
    let i23RowCount = 0
    if (Array.isArray(i23)) {
      for (const line of i23) {
        const code = _str(line.accountCode || line.account || '')
        const name = _str(line.accountName || line.account || '')
        const isDev = code.startsWith('1717') || name.includes('开发支出')
        if (!isDev) continue
        const cat = _str(line.category || line.entryType || '')
        if (cat.includes('报表') || cat.toUpperCase() === 'RJE') continue
        i23AjeNet += _num(line.debitAmount ?? line.debit) - _num(line.creditAmount ?? line.credit)
        i23RowCount++
      }
    }
    const detailAjeNet = calcSubtotal(rows.value.map(rowAjeNet))
    const diff = detailAjeNet - i23AjeNet
    return {
      i23AjeNet,
      detailAjeNet,
      diff,
      hasWarning: i23RowCount > 0 && Math.abs(diff) > TOL,
      i23RowCount,
    }
  })

  function switchSegment(segIndex: number): void {
    if (segIndex >= 0 && segIndex <= 3) activeSegment.value = segIndex
  }

  function setActiveRow(index: number): void {
    activeRowIndex.value = index
  }

  function updateField(rowIndex: number, field: string, value: any): void {
    const row = rows.value[rowIndex]
    if (!row) return
    ;(row as any)[field] = value
    // 旧字段编辑时同步 Excel 列
    if (field === 'capBeginAmount') row.unadjOpening = _num(value)
    if (field === 'capIncrease') row.unadjIncrease = _num(value)
    if (field === 'transferToI1') row.unadjDecToIA = _num(value)
    recalcI2DetailRow(row)
  }

  function addRow(projectName: string): void {
    if (!projectName?.trim()) return
    const newRow = emptyRow({ projectName: projectName.trim() })
    recalcI2DetailRow(newRow)
    rows.value.push(newRow)
    activeRowIndex.value = rows.value.length - 1
  }

  function removeRow(index: number): void {
    if (index < 0 || index >= rows.value.length) return
    rows.value.splice(index, 1)
    if (activeRowIndex.value >= rows.value.length) {
      activeRowIndex.value = rows.value.length - 1
    }
  }

  function importRows(importedRows: Partial<I2DetailRow>[]): void {
    rows.value = importedRows.map((raw) => normalizeI2DetailRow(raw))
    activeRowIndex.value = rows.value.length > 0 ? 0 : -1
  }

  function exportRows(): I2DetailRow[] {
    return [...rows.value]
  }

  async function save(): Promise<void> {
    await saveResponses('I2-2', { [ITEM_ID_ROWS]: JSON.stringify(rows.value) })
  }

  /**
   * 从 I2-3 同步账项调整：按「调整事项说明」包含项目名匹配；
   * 借方→本期增加调整；贷方含「无形/存货」→转无形调整；否则→转损益调整。
   * 未匹配行计入选中行（若有）或第一条项目行。
   */
  function syncAjeFromI23(): { applied: number; unmatched: number; message: string } {
    const i23 = _getJson(I23_ROWS_KEY) || _getJson(LEGACY_I23_KEY)
    if (!Array.isArray(i23) || i23.length === 0) {
      return { applied: 0, unmatched: 0, message: 'I2-3 无调整分录可同步' }
    }
    if (!rows.value.length) {
      return { applied: 0, unmatched: 0, message: '请先新增明细项目' }
    }

    // 清空现有 AJE，再重算
    for (const r of rows.value) {
      r.ajeIncrease = 0
      r.ajeDecToIA = 0
      r.ajeDecToPL = 0
    }

    let applied = 0
    let unmatched = 0
    const fallbackIdx = activeRowIndex.value >= 0 ? activeRowIndex.value : 0

    for (const line of i23) {
      const code = _str(line.accountCode || line.account || '')
      const name = _str(line.accountName || line.account || '')
      const isDev = code.startsWith('1717') || name.includes('开发支出')
      if (!isDev) continue
      const cat = _str(line.category || line.entryType || '')
      if (cat.includes('报表') || cat.toUpperCase() === 'RJE') continue

      const debit = _num(line.debitAmount ?? line.debit)
      const credit = _num(line.creditAmount ?? line.credit)
      if (Math.abs(debit) < 0.005 && Math.abs(credit) < 0.005) continue

      const desc = _str(line.description || line.summary || '')
      let idx = rows.value.findIndex(
        (r) => r.projectName && desc.includes(r.projectName),
      )
      if (idx < 0) {
        unmatched++
        idx = fallbackIdx
      }

      const target = rows.value[idx]
      if (debit > 0) {
        target.ajeIncrease += debit
        applied++
      }
      if (credit > 0) {
        if (/无形|存货/.test(desc + _str(line.remark) + _str(line.noteItem))) {
          target.ajeDecToIA += credit
        } else {
          target.ajeDecToPL += credit
        }
        applied++
      }
    }

    recalcAll()
    return {
      applied,
      unmatched,
      message: applied
        ? `已从 I2-3 同步 ${applied} 笔账项至明细${unmatched ? `（其中 ${unmatched} 笔未匹配项目名，已归入当前/首行）` : ''}`
        : 'I2-3 中无 1717 开发支出账项调整行',
    }
  }

  // ─── 列配置：0 审计过程(Excel) / 1 本期投入 / 2 项目基础 / 3 其他核对 ───

  const segmentProcessColumns: I2DetailColumn[] = [
    { key: 'projectName', label: '研究开发项目名称', width: 160, editable: true, type: 'text', group: '项目' },
    { key: 'unadjOpening', label: '期初数', width: 110, editable: true, type: 'number', group: '未审数' },
    { key: 'unadjIncrease', label: '本期增加-金额', width: 110, editable: true, type: 'number', group: '未审数', emphasis: true },
    { key: 'increaseMethod', label: '增加方式', width: 120, editable: true, type: 'select', options: I2_INCREASE_METHODS, group: '未审数', emphasis: true },
    { key: 'unadjDecToIA', label: '减少-转无形/存货', width: 120, editable: true, type: 'number', group: '未审数', emphasis: true },
    { key: 'unadjDecToPL', label: '减少-转当期损益', width: 120, editable: true, type: 'number', group: '未审数' },
    { key: 'unadjEnding', label: '期末数', width: 110, editable: false, type: 'formula', tooltip: '期初+增加-转无形-转损益', group: '未审数' },
    { key: 'openingAdj', label: '期初调整', width: 100, editable: true, type: 'number', group: '调整' },
    { key: 'ajeIncrease', label: '账项-本期增加', width: 110, editable: true, type: 'number', group: '账项调整' },
    { key: 'ajeDecToIA', label: '账项-转无形/存货', width: 120, editable: true, type: 'number', group: '账项调整', emphasis: true },
    { key: 'ajeDecToPL', label: '账项-转损益', width: 110, editable: true, type: 'number', group: '账项调整' },
    { key: 'auditedOpening', label: '审定-期初', width: 110, editable: false, type: 'formula', tooltip: '未审期初+期初调整', group: '审定数' },
    { key: 'auditedIncrease', label: '审定-本期增加', width: 110, editable: false, type: 'formula', tooltip: '未审增加+账项增加', group: '审定数' },
    { key: 'auditedDecToIA', label: '审定-转无形/存货', width: 120, editable: false, type: 'formula', tooltip: '未审+账项', group: '审定数', emphasis: true },
    { key: 'auditedDecToPL', label: '审定-转损益', width: 110, editable: false, type: 'formula', group: '审定数' },
    { key: 'auditedEnding', label: '审定-期末', width: 110, editable: false, type: 'formula', tooltip: '审定期初+增加-转无形-转损益', group: '审定数' },
    { key: 'relatedIAAuditedEnd', label: '无形/存货期末审定', width: 130, editable: true, type: 'number', group: '核对', emphasis: true },
    { key: 'diffVsIA', label: '差异', width: 100, editable: false, type: 'formula', tooltip: '开发支出审定期末−无形/存货审定', group: '核对' },
    { key: 'rdProgress', label: '截至期末研发进度', width: 120, editable: true, type: 'text', group: '核对' },
    { key: 'remark', label: '备注', width: 120, editable: true, type: 'text', group: '核对' },
  ]

  const segmentInvestmentColumns: I2DetailColumn[] = [
    { key: 'projectName', label: '项目名称', width: 160, editable: false, type: 'text' },
    { key: 'materialCurrent', label: '材料-本期', width: 110, editable: true, type: 'number' },
    { key: 'materialAccum', label: '材料-累计', width: 110, editable: true, type: 'number' },
    { key: 'laborCurrent', label: '人工-本期', width: 110, editable: true, type: 'number' },
    { key: 'laborAccum', label: '人工-累计', width: 110, editable: true, type: 'number' },
    { key: 'depreciationCurrent', label: '折旧-本期', width: 110, editable: true, type: 'number' },
    { key: 'depreciationAccum', label: '折旧-累计', width: 110, editable: true, type: 'number' },
    { key: 'amortizationCurrent', label: '摊销-本期', width: 110, editable: true, type: 'number' },
    { key: 'amortizationAccum', label: '摊销-累计', width: 110, editable: true, type: 'number' },
    { key: 'otherCurrent', label: '其他-本期', width: 110, editable: true, type: 'number' },
    { key: 'otherAccum', label: '其他-累计', width: 110, editable: true, type: 'number' },
    { key: 'totalCurrent', label: '合计-本期', width: 120, editable: false, type: 'formula', tooltip: '材料+人工+折旧+摊销+其他' },
    { key: 'totalAccum', label: '合计-累计', width: 120, editable: false, type: 'formula' },
    { key: 'investmentRemark', label: '投入说明', width: 140, editable: true, type: 'text' },
  ]

  const segmentBasicColumns: I2DetailColumn[] = [
    { key: 'projectName', label: '项目名称', width: 160, editable: true, type: 'text' },
    { key: 'projectCode', label: '项目编号', width: 110, editable: true, type: 'text' },
    { key: 'approvalDate', label: '立项日期', width: 120, editable: true, type: 'date' },
    { key: 'phase', label: '阶段', width: 100, editable: true, type: 'select', options: PHASE_OPTIONS },
    { key: 'manager', label: '负责人', width: 100, editable: true, type: 'text' },
    { key: 'startDate', label: '起始日期', width: 120, editable: true, type: 'date' },
    { key: 'endDate', label: '终止日期', width: 120, editable: true, type: 'date' },
    { key: 'budget', label: '预算', width: 120, editable: true, type: 'number' },
    { key: 'capitalizationStart', label: '资本化起点', width: 120, editable: true, type: 'date' },
    { key: 'capStartDate', label: '资本化起点(联动)', width: 120, editable: true, type: 'date' },
    { key: 'transferDate', label: '转入无形日期', width: 120, editable: true, type: 'date' },
    { key: 'transferAssetName', label: '转入资产名称', width: 130, editable: true, type: 'text' },
    { key: 'status', label: '状态', width: 100, editable: true, type: 'select', options: STATUS_OPTIONS },
  ]

  const segmentSummaryColumns: I2DetailColumn[] = [
    { key: 'projectName', label: '项目名称', width: 160, editable: false, type: 'text' },
    { key: 'auditedEnding', label: '审定期末', width: 120, editable: false, type: 'formula' },
    { key: 'priorEnd', label: '上期期末', width: 120, editable: true, type: 'number' },
    { key: 'yoyChange', label: '同比变动', width: 100, editable: false, type: 'formula', tooltip: '(审定期末-上期)/上期' },
    { key: 'expectedValue', label: '预期值', width: 120, editable: true, type: 'number' },
    { key: 'variance', label: 'vs预期差异', width: 110, editable: false, type: 'formula' },
    { key: 'conclusion', label: '结论', width: 140, editable: true, type: 'text' },
    { key: 'adjReference', label: '索引', width: 100, editable: true, type: 'text' },
    { key: 'remark', label: '备注', width: 140, editable: true, type: 'text' },
  ]

  const segments = [
    { index: 0, key: 'process', label: '审计过程(Excel)', columns: segmentProcessColumns },
    { index: 1, key: 'investment', label: '本期投入', columns: segmentInvestmentColumns },
    { index: 2, key: 'basic', label: '项目基础', columns: segmentBasicColumns },
    { index: 3, key: 'summary', label: '分析结论', columns: segmentSummaryColumns },
  ]

  const activeColumns = computed(() => segments[activeSegment.value]?.columns ?? segmentProcessColumns)

  return {
    rows,
    activeSegment,
    activeRowIndex,
    totalRow,
    crossValidation,
    ajeLinkage,
    activeColumns,
    segments,
    segmentProcessColumns,
    segmentBasicColumns,
    segmentInvestmentColumns,
    segmentCapitalizationColumns: segmentProcessColumns,
    segmentSummaryColumns,
    switchSegment,
    setActiveRow,
    updateField,
    recalcAll,
    addRow,
    removeRow,
    importRows,
    exportRows,
    save,
    syncAjeFromI23,
  }
}

export default useI2Detail
