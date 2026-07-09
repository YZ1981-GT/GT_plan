/**
 * useH5Stocktake — H5-9/10/11 监盘三阶段 composable
 *
 * 数据流联动(计划→检查→小结)
 * H5-9 监盘计划 15列 + H5-10 盘点检查 14列 + H5-11 监盘小结 叙述式
 *
 * Spec: .kiro/specs/h5-oil-gas-assets/
 * Task: 3.4
 * Requirements: 6.1-6.4
 */
import { ref, computed, watch, type Ref } from 'vue'
import type { ChecklistItem } from './useH5FormData'

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

export interface StocktakeCheckRow {
  rowId: string
  seq: number
  item: string
  bookValue: number             // 账面数
  actualValue: number           // 实盘数
  difference: number            // 差异
  diffReason: string            // 差异原因
  status: string                // 状态(正常/异常/待核实)
  photoRef: string              // 照片引用
  gpsCoord: string              // GPS坐标
  inspector: string             // 盘点人
  inspectDate: string           // 盘点日期
  conclusion: string            // 结论
  remark: string
}

export interface StocktakeSummary {
  overview: string              // 盘点概况
  scope: string                 // 盘点范围
  diffAnalysis: string          // 差异分析
  conclusion: string            // 监盘结论
  suggestions: string           // 建议
}

// ─── Constants ───────────────────────────────────────────────────────────────

const PLAN_PREFIX = 'H5-9'
const CHECK_PREFIX = 'H5-10'
const SUMMARY_PREFIX = 'H5-11'

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
      try { checkRows.value = JSON.parse(raw) ?? [] } catch { checkRows.value = [] }
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

  /** 计划中已完成的项目→自动推送到检查表 */
  const completedPlanItems = computed(() => planRows.value.filter((r) => r.status === '已完成'))

  /** 检查表中异常项汇总→小结 */
  const abnormalCheckItems = computed(() => checkRows.value.filter((r) => r.status === '异常'))
  const totalDifference = computed(() => checkRows.value.reduce((sum, r) => sum + Math.abs(r.difference), 0))

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

  function addCheckRow(item: string): void {
    checkRows.value.push({
      rowId: `check-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      seq: checkRows.value.length + 1, item,
      bookValue: 0, actualValue: 0, difference: 0,
      diffReason: '', status: '正常', photoRef: '', gpsCoord: '',
      inspector: '', inspectDate: '', conclusion: '', remark: '',
    })
    _persistCheck()
  }

  function updateCheckCell(rowId: string, field: keyof StocktakeCheckRow, value: any): void {
    const row = checkRows.value.find((r) => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
    if (field === 'bookValue' || field === 'actualValue') {
      row.difference = row.actualValue - row.bookValue
    }
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
    addPlanRow, removePlanRow, updatePlanCell,
    addCheckRow, updateCheckCell,
    updateSummary,
  }
}
