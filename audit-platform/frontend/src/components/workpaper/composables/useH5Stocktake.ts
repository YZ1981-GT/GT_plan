/**
 * useH5Stocktake — H5-9/10/11 监盘三阶段 composable
 *
 * 数据流联动(计划→检查→小结)
 * H5-9 监盘计划 15列 + H5-10 盘点检查（双向三数量，兼容旧 bookValue/actualValue）
 * + H5-11 监盘小结 叙述式
 *
 * Spec: .kiro/specs/h5-oil-gas-assets/
 * Task: 3.4
 * Requirements: 6.1-6.4
 */
import { ref, computed, watch, type Ref } from 'vue'
import type { ChecklistItem } from './useH5FormData'
import {
  normalizeDirection,
  deriveResultFromQty,
  calcRowDiffs,
  type StocktakeDirection,
  type StocktakeCheckRow as H1StocktakeCheckRow,
} from './h1StocktakeCheckModel'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface StocktakePlanRow {
  rowId: string
  seq: number
  item: string                  // 盘点项目
  oilField: string
  location: string              // 位置/GPS
  bookCost: number              // 账面原值
  bookNetValue: number          // 账面净值
  method: string                // 盘点方式(实地观察/确认函)
  plannedDate: string           // 盘点日期
  responsible: string           // 负责人
  sampleSize: number            // 样本量
  samplingMethod: string        // 抽样方法
  estimatedHours: number        // 预计耗时(小时)
  notes: string                 // 注意事项
  status: string                // 状态(待执行/进行中/已完成)
  remark: string
}

/** H5-10 检查行：双向三数量 + 旧字段兼容 */
export interface StocktakeCheckRow {
  rowId: string
  seq: number
  item: string
  /** 抽盘方向；旧数据缺省为 bookToFloor */
  direction: StocktakeDirection
  assetNo: string
  unit: string
  unitPrice: number
  bookQty: number
  bookAmount: number
  clientCountQty: number
  sampleQty: number
  qualityStatus: string
  result: string
  // ── 兼容旧字段（保存时双写，读时归一） ──
  bookValue: number             // → bookAmount
  actualValue: number           // → sampleQty
  difference: number            // sampleQty - bookQty（旧口径 actual−book）
  diffReason: string
  status: string                // 状态(正常/异常/待核实)
  photoRef: string
  gpsCoord: string
  inspector: string
  inspectDate: string
  conclusion: string
  remark: string
}

export interface StocktakeSummary {
  overview: string
  scope: string
  diffAnalysis: string
  conclusion: string
  suggestions: string
}

export type { StocktakeDirection }

// ─── Constants ───────────────────────────────────────────────────────────────

const PLAN_PREFIX = 'H5-9'
const CHECK_PREFIX = 'H5-10'
const SUMMARY_PREFIX = 'H5-11'

function _num(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

/** 旧行归一：bookValue→bookAmount，actualValue→sampleQty；缺 direction 归账面→实物 */
export function normalizeH5CheckRow(raw: any, idx: number): StocktakeCheckRow {
  const bookAmount = _num(raw.bookAmount ?? raw.bookValue)
  const sampleQty = _num(raw.sampleQty ?? raw.actualValue)
  const bookQty = _num(raw.bookQty)
  const clientCountQty = _num(raw.clientCountQty)
  const direction = normalizeDirection(raw.direction)
  const bookValue = _num(raw.bookValue ?? bookAmount)
  const actualValue = _num(raw.actualValue ?? sampleQty)
  // 仅当已持久化过三数量字段时按抽盘−账面；否则保留旧口径 实盘−账面，避免 bookQty=0 时虚增差异
  const hasExplicitQtyFields = raw.bookQty != null || raw.sampleQty != null || raw.clientCountQty != null
  const difference = hasExplicitQtyFields
    ? sampleQty - bookQty
    : actualValue - bookValue
  let result = String(raw.result ?? '')
  if (!result && hasExplicitQtyFields && (bookQty > 0 || sampleQty > 0)) {
    result = deriveResultFromQty(sampleQty, bookQty)
  }
  const item = String(raw.item ?? raw.name ?? '')
  return {
    rowId: raw.rowId ?? `check-${Math.random().toString(36).slice(2, 10)}`,
    seq: raw.seq ?? idx + 1,
    item,
    direction,
    assetNo: String(raw.assetNo ?? ''),
    unit: String(raw.unit ?? ''),
    unitPrice: _num(raw.unitPrice),
    bookQty,
    bookAmount,
    clientCountQty,
    sampleQty,
    qualityStatus: String(raw.qualityStatus ?? ''),
    result,
    bookValue,
    actualValue,
    difference,
    diffReason: String(raw.diffReason ?? ''),
    status: String(raw.status ?? '正常'),
    photoRef: String(raw.photoRef ?? ''),
    gpsCoord: String(raw.gpsCoord ?? ''),
    inspector: String(raw.inspector ?? ''),
    inspectDate: String(raw.inspectDate ?? ''),
    conclusion: String(raw.conclusion ?? ''),
    remark: String(raw.remark ?? ''),
  }
}

/** 数量变更后同步 result / difference / 旧字段双写 */
export function syncH5CheckQtyFields(row: StocktakeCheckRow): void {
  row.bookValue = row.bookAmount
  row.actualValue = row.sampleQty
  row.difference = row.sampleQty - row.bookQty
  if (row.bookQty > 0 || row.sampleQty > 0 || row.clientCountQty > 0) {
    row.result = deriveResultFromQty(row.sampleQty, row.bookQty)
  }
  const diffs = calcRowDiffs(row)
  if (diffs.hasVariance && row.status === '正常') {
    row.status = '异常'
  } else if (!diffs.hasVariance && row.status === '异常' && !row.diffReason) {
    row.status = '正常'
  }
}

/** 映射为 H1CheckDirectionTable 行（只读视图字段 + 可回写字段） */
export function toH1CheckRow(r: StocktakeCheckRow): H1StocktakeCheckRow {
  return {
    rowId: r.rowId,
    seq: r.seq,
    direction: r.direction,
    name: r.item,
    assetNo: r.assetNo,
    location: r.gpsCoord,
    spec: '',
    unit: r.unit,
    unitPrice: r.unitPrice,
    bookQty: r.bookQty,
    bookAmount: r.bookAmount,
    clientCountQty: r.clientCountQty,
    sampleQty: r.sampleQty,
    qualityStatus: r.qualityStatus,
    result: r.result,
    diffReason: r.diffReason,
    diffAmount: r.difference,
    suggestion: '',
    checker: r.inspector,
    remark: r.remark,
    bookCost: r.bookAmount,
    bookNetValue: 0,
    actualStatus: r.qualityStatus || '在用',
    photoUrl: r.photoRef,
    nameplateCheck: '',
    quantityCheck: Math.abs(r.sampleQty - r.bookQty) < 0.001 ? '一致' : '不一致',
    conditionAssess: '',
  }
}

export function draftH5CheckConclusion(ctx: {
  total: number
  matchCount: number
  varianceCount: number
  bookToFloorCount: number
  floorToBookCount: number
}): string {
  const lines = [
    `本次油气资产抽盘共检查 ${ctx.total} 项（账面→实物 ${ctx.bookToFloorCount}、实物→账面 ${ctx.floorToBookCount}）。`,
    `账实相符 ${ctx.matchCount} 项；存在数量差异 ${ctx.varianceCount} 项。`,
  ]
  if (ctx.total === 0) {
    lines.push('尚未录入抽盘明细，本节审计目标尚待执行后结论。')
  } else if (ctx.varianceCount > 0) {
    lines.push('存在账实差异，已在检查表记录原因；需关注企业对盘盈盘亏的处理及减值迹象，并汇入 H5-11。')
  } else {
    lines.push('双向抽盘未发现重大账实不符；油气资产存在性与完整性认定可获合理保证。详见 H5-9/H5-11。')
  }
  return lines.join('\n')
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH5Stocktake(opts: {
  allResponses: Ref<Map<string, ChecklistItem>>
  wpId: Ref<string>
  projectId: Ref<string>
  onSave?: (itemId: string, value: any) => void
}) {
  const { allResponses, onSave } = opts

  const planRows = ref<StocktakePlanRow[]>([])
  const checkRows = ref<StocktakeCheckRow[]>([])
  const summary = ref<StocktakeSummary>({
    overview: '', scope: '', diffAnalysis: '', conclusion: '', suggestions: '',
  })

  // ─── Load ──────────────────────────────────────────────────────────────────

  function _load(): void {
    _loadPlan()
    _loadCheck()
    _loadSummary()
  }

  function _loadPlan(): void {
    const raw = allResponses.value.get(`${PLAN_PREFIX}-rows`)?.remark
    if (raw) {
      try { planRows.value = JSON.parse(raw) ?? [] } catch { planRows.value = [] }
    } else { planRows.value = [] }
  }

  function _loadCheck(): void {
    const raw = allResponses.value.get(`${CHECK_PREFIX}-rows`)?.remark
    if (raw) {
      try {
        const parsed = JSON.parse(raw)
        checkRows.value = Array.isArray(parsed)
          ? parsed.map((r: any, i: number) => normalizeH5CheckRow(r, i))
          : []
      } catch { checkRows.value = [] }
    } else { checkRows.value = [] }
  }

  function _loadSummary(): void {
    const raw = allResponses.value.get(`${SUMMARY_PREFIX}-content`)?.remark
    if (raw) {
      try { summary.value = JSON.parse(raw) ?? { overview: '', scope: '', diffAnalysis: '', conclusion: '', suggestions: '' } }
      catch { /* keep defaults */ }
    }
  }

  // ─── Computed: 数据流联动 ──────────────────────────────────────────────────

  const completedPlanItems = computed(() => planRows.value.filter((r) => r.status === '已完成'))

  const abnormalCheckItems = computed(() => checkRows.value.filter((r) => r.status === '异常'))
  const totalDifference = computed(() => checkRows.value.reduce((sum, r) => sum + Math.abs(r.difference), 0))

  const bookToFloorRows = computed(() => checkRows.value.filter((r) => r.direction === 'bookToFloor'))
  const floorToBookRows = computed(() => checkRows.value.filter((r) => r.direction === 'floorToBook'))

  const planCompletionRate = computed(() => {
    if (planRows.value.length === 0) return 0
    return Math.round((completedPlanItems.value.length / planRows.value.length) * 100)
  })

  // ─── Actions: 计划 ─────────────────────────────────────────────────────────

  function addPlanRow(item: string): void {
    planRows.value.push({
      rowId: `plan-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      seq: planRows.value.length + 1, item,
      oilField: '', location: '', bookCost: 0, bookNetValue: 0,
      method: '实地观察', plannedDate: '', responsible: '',
      sampleSize: 0, samplingMethod: '', estimatedHours: 0,
      notes: '', status: '待执行', remark: '',
    })
    _persistPlan()
  }

  function removePlanRow(rowId: string): void {
    const idx = planRows.value.findIndex((r) => r.rowId === rowId)
    if (idx >= 0) { planRows.value.splice(idx, 1); _persistPlan() }
  }

  function updatePlanCell(rowId: string, field: keyof StocktakePlanRow, value: any): void {
    const row = planRows.value.find((r) => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
    _persistPlan()
  }

  // ─── Actions: 检查 ─────────────────────────────────────────────────────────

  function addCheckRow(item: string, direction: StocktakeDirection = 'bookToFloor'): void {
    const row = normalizeH5CheckRow({
      item,
      direction,
      seq: checkRows.value.length + 1,
      status: '正常',
    }, checkRows.value.length)
    checkRows.value.push(row)
    _persistCheck()
  }

  function removeCheckRow(rowId: string): void {
    const idx = checkRows.value.findIndex((r) => r.rowId === rowId)
    if (idx >= 0) {
      checkRows.value.splice(idx, 1)
      checkRows.value.forEach((r, i) => { r.seq = i + 1 })
      _persistCheck()
    }
  }

  function updateCheckCell(rowId: string, field: keyof StocktakeCheckRow, value: any): void {
    const row = checkRows.value.find((r) => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
    // 旧字段 ↔ 新字段双向同步
    if (field === 'bookValue') row.bookAmount = _num(value)
    if (field === 'actualValue') row.sampleQty = _num(value)
    if (field === 'bookAmount') row.bookValue = _num(value)
    if (field === 'sampleQty') row.actualValue = _num(value)
    if (field === 'item') { /* name alias via toH1 */ }
    if (
      field === 'bookValue' || field === 'actualValue'
      || field === 'bookAmount' || field === 'sampleQty'
      || field === 'bookQty' || field === 'clientCountQty'
    ) {
      syncH5CheckQtyFields(row)
    }
    _persistCheck()
  }

  /** H1CheckDirectionTable 回写 */
  function updateCheckFromH1(rowId: string, patch: Partial<H1StocktakeCheckRow>): void {
    const row = checkRows.value.find((r) => r.rowId === rowId)
    if (!row) return
    if (patch.name != null) row.item = patch.name
    if (patch.assetNo != null) row.assetNo = patch.assetNo
    if (patch.unit != null) row.unit = patch.unit
    if (patch.unitPrice != null) row.unitPrice = _num(patch.unitPrice)
    if (patch.bookQty != null) row.bookQty = _num(patch.bookQty)
    if (patch.bookAmount != null) row.bookAmount = _num(patch.bookAmount)
    if (patch.clientCountQty != null) row.clientCountQty = _num(patch.clientCountQty)
    if (patch.sampleQty != null) row.sampleQty = _num(patch.sampleQty)
    if (patch.qualityStatus != null) row.qualityStatus = patch.qualityStatus
    if (patch.diffReason != null) row.diffReason = patch.diffReason
    if (patch.remark != null) row.remark = patch.remark
    if (patch.checker != null) row.inspector = patch.checker
    if (patch.location != null) row.gpsCoord = patch.location
    syncH5CheckQtyFields(row)
    _persistCheck()
  }

  // ─── Actions: 小结 ─────────────────────────────────────────────────────────

  function updateSummary(field: keyof StocktakeSummary, value: string): void {
    summary.value[field] = value
    _persistSummary()
  }

  // ─── Persist ───────────────────────────────────────────────────────────────

  function _persistPlan(): void { onSave?.(`${PLAN_PREFIX}-rows`, planRows.value) }
  function _persistCheck(): void { onSave?.(`${CHECK_PREFIX}-rows`, checkRows.value) }
  function _persistSummary(): void { onSave?.(`${SUMMARY_PREFIX}-content`, summary.value) }

  watch(allResponses, () => _load(), { immediate: true })

  return {
    planRows, checkRows, summary,
    completedPlanItems, abnormalCheckItems, totalDifference, planCompletionRate,
    bookToFloorRows, floorToBookRows,
    addPlanRow, removePlanRow, updatePlanCell,
    addCheckRow, removeCheckRow, updateCheckCell, updateCheckFromH1,
    updateSummary,
  }
}
