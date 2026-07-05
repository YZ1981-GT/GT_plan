/**
 * useD1SamplingVouching — D1-13 应收票据抽样凭证核对 composable
 *
 * Spec: .kiro/specs/d1-inspection-check/
 * Task: 7.1
 *
 * 职责：
 * - 管理抽样总体定义（population Ref<SamplePopulation>）
 * - 特定样本动态行 CRUD（specificSamples + addSpecificSample / removeSpecificSample）
 * - 凭证核对明细 13 列动态行 CRUD（vouchingRows + addVouchingRow / removeVouchingRow / updateVouchingRow）
 * - 核对结果统计：checkedCount（G32）/ checkedAmountTotal（H32）/ vouchingAmountTotal（G45）
 * - 例外汇总 E48-G50：三类例外（存在性/准确性/记录恰当性）笔数/金额/占比
 * - 超标判定：hasExceedingException（任一占比 > tolerableErrorRate）
 * - 可容忍误差率 tolerableErrorRate（默认 5%）
 * - 测试结论 testConclusion（el-select）
 * - 审计说明/结论（auditNote / auditConclusion）+ debounce 保存
 * - exportTemplate / exportData / importData（仅解析凭证核对明细行，跳过抽样定义和例外汇总）
 * - respect isReadonly
 *
 * Storage keys（item_id 前缀 "D1-sampling-"）：
 *   D1-sampling-population-desc / -count / -amount / -size / -drawn / -ref
 *   D1-sampling-specific-samples (JSON array)
 *   D1-sampling-vouching-rows (JSON array)
 *   D1-sampling-tolerable-rate
 *   D1-sampling-test-conclusion
 *   D1-sampling-note / D1-sampling-conclusion
 *
 * Exception logic:
 *   存在性例外: rows where existenceCheck === '未核实'
 *   准确性例外: rows where accuracyCheck === '金额不一致'
 *   记录恰当性例外: rows where appropriatenessCheck === '不恰当'
 *
 * checkedCount logic:
 *   Count rows where ANY of existenceCheck/accuracyCheck/appropriatenessCheck
 *   is non-empty and not '不适用'
 *
 * Requirements: 10.1-10.4, 11.1-11.4, 12.1-12.6, 13.1-13.5, 15.4, 15.6, 15.10
 */
import { ref, computed, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import type { ChecklistItem, ChecklistResponse } from './useD1FormData'
import {
  sumColumn,
  computeExceptionRate,
  type VouchingRow,
  type SpecificSampleRow,
  type SamplePopulation,
  type ExceptionSummaryRow,
} from './d1InspectionFormulas'
import { useD1ImportExport, type ImportResult } from './useD1ImportExport'
import http from '@/utils/http'

// ─── Types ───────────────────────────────────────────────────────────────────

export type SaveFn = (items: ChecklistItem[]) => Promise<void>
export type DebounceSaveFn = (item: ChecklistItem) => void

export interface UseD1SamplingVouchingOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  wpId: Ref<string>
  projectId: Ref<string>
  saveImmediate: SaveFn
  saveDebouncedText: DebounceSaveFn
  isReadonly: Ref<boolean>
}

// ─── Constants ───────────────────────────────────────────────────────────────

/** Population field keys */
const POP_DESC_KEY = 'D1-sampling-population-desc'
const POP_COUNT_KEY = 'D1-sampling-population-count'
const POP_AMOUNT_KEY = 'D1-sampling-population-amount'
const POP_SIZE_KEY = 'D1-sampling-population-size'
const POP_DRAWN_KEY = 'D1-sampling-population-drawn'
const POP_REF_KEY = 'D1-sampling-population-ref'

/** Data keys */
const SPECIFIC_SAMPLES_KEY = 'D1-sampling-specific-samples'
const VOUCHING_ROWS_KEY = 'D1-sampling-vouching-rows'
const TOLERABLE_RATE_KEY = 'D1-sampling-tolerable-rate'
const TEST_CONCLUSION_KEY = 'D1-sampling-test-conclusion'
const NOTE_KEY = 'D1-sampling-note'
const CONCLUSION_KEY = 'D1-sampling-conclusion'

/** VouchingRow 数值字段 */
const VOUCHING_NUMERIC_FIELDS: Array<keyof VouchingRow> = ['amount', 'seq']

/** VouchingRow 字符串字段 */
const VOUCHING_STRING_FIELDS: Array<keyof VouchingRow> = [
  'noteType',
  'noteNo',
  'drawer',
  'acceptor',
  'maturityDate',
  'existenceCheck',
  'accuracyCheck',
  'appropriatenessCheck',
  'remark',
  'indexRef',
]

/** select 类字段（立即保存） */
const SELECT_FIELDS: Array<keyof VouchingRow> = [
  'existenceCheck',
  'accuracyCheck',
  'appropriatenessCheck',
  'noteType',
]

// ─── Helpers ─────────────────────────────────────────────────────────────────

function generateRowId(): string {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return crypto.randomUUID()
  }
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function parseNum(val: any): number {
  const n = Number(val)
  return Number.isFinite(n) ? n : 0
}

/** 空凭证核对行工厂 */
export function emptyVouchingRow(seq: number): VouchingRow {
  return {
    id: generateRowId(),
    seq,
    noteType: '',
    noteNo: '',
    drawer: '',
    acceptor: '',
    amount: 0,
    maturityDate: '',
    existenceCheck: '',
    accuracyCheck: '',
    appropriatenessCheck: '',
    remark: '',
    indexRef: '',
  }
}

/** 空特定样本行工厂 */
export function emptySpecificSampleRow(): SpecificSampleRow {
  return {
    id: generateRowId(),
    description: '',
    amount: 0,
    reason: '',
  }
}

/** 默认抽样总体 */
function defaultPopulation(): SamplePopulation {
  return {
    populationDesc: '',
    totalCount: 0,
    totalAmount: 0,
    sampleSize: 0,
    actualDrawn: 0,
    sampleCalcRef: '',
  }
}

/** 反序列化凭证核对行 */
function deserializeVouchingRow(raw: any, fallbackSeq: number): VouchingRow {
  const row = emptyVouchingRow(fallbackSeq)
  if (raw && typeof raw.id === 'string' && raw.id) row.id = raw.id
  if (raw && typeof raw.seq === 'number') row.seq = raw.seq
  for (const f of VOUCHING_STRING_FIELDS) {
    if (raw && typeof raw[f] === 'string') (row as any)[f] = raw[f]
  }
  for (const f of VOUCHING_NUMERIC_FIELDS) {
    if (raw && raw[f] !== undefined) (row as any)[f] = parseNum(raw[f])
  }
  return row
}

/** 序列化凭证核对行 */
function serializeVouchingRow(row: VouchingRow): any {
  const data: any = { id: row.id, seq: row.seq }
  for (const f of VOUCHING_STRING_FIELDS) data[f] = (row as any)[f]
  for (const f of VOUCHING_NUMERIC_FIELDS) data[f] = (row as any)[f]
  return data
}

/** 反序列化特定样本行 */
function deserializeSpecificSample(raw: any): SpecificSampleRow {
  const row = emptySpecificSampleRow()
  if (raw && typeof raw.id === 'string' && raw.id) row.id = raw.id
  if (raw && typeof raw.description === 'string') row.description = raw.description
  if (raw && raw.amount !== undefined) row.amount = parseNum(raw.amount)
  if (raw && typeof raw.reason === 'string') row.reason = raw.reason
  return row
}

/** 序列化特定样本行 */
function serializeSpecificSample(row: SpecificSampleRow): any {
  return { id: row.id, description: row.description, amount: row.amount, reason: row.reason }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useD1SamplingVouching(options: UseD1SamplingVouchingOptions) {
  const { allResponses, wpId, projectId: _projectId, saveImmediate, saveDebouncedText, isReadonly } = options

  // ─── State ───────────────────────────────────────────────────────────────

  const population = ref<SamplePopulation>(defaultPopulation())
  const specificSamples = ref<SpecificSampleRow[]>([])
  const vouchingRows = ref<VouchingRow[]>([])
  const tolerableErrorRate = ref<number>(0.05)
  const testConclusion = ref<string>('')
  const auditNote = ref<string>('')
  const auditConclusion = ref<string>('')

  // ─── Deserialization (Load from allResponses) ────────────────────────────

  function loadPopulation(): SamplePopulation {
    const pop = defaultPopulation()
    pop.populationDesc = allResponses.value.get(POP_DESC_KEY)?.remark ?? ''
    pop.totalCount = parseNum(allResponses.value.get(POP_COUNT_KEY)?.remark)
    pop.totalAmount = parseNum(allResponses.value.get(POP_AMOUNT_KEY)?.remark)
    pop.sampleSize = parseNum(allResponses.value.get(POP_SIZE_KEY)?.remark)
    pop.actualDrawn = parseNum(allResponses.value.get(POP_DRAWN_KEY)?.remark)
    pop.sampleCalcRef = allResponses.value.get(POP_REF_KEY)?.remark ?? ''
    return pop
  }

  function loadSpecificSamples(): SpecificSampleRow[] {
    const raw = allResponses.value.get(SPECIFIC_SAMPLES_KEY)?.remark
    if (!raw) return []
    try {
      const parsed = JSON.parse(raw)
      if (!Array.isArray(parsed)) return []
      return parsed.map((r: any) => deserializeSpecificSample(r))
    } catch {
      return []
    }
  }

  function loadVouchingRows(): VouchingRow[] {
    const raw = allResponses.value.get(VOUCHING_ROWS_KEY)?.remark
    if (!raw) return []
    try {
      const parsed = JSON.parse(raw)
      if (!Array.isArray(parsed)) return []
      return parsed.map((r: any, idx: number) => deserializeVouchingRow(r, idx + 1))
    } catch {
      return []
    }
  }

  function loadFromResponses(): void {
    population.value = loadPopulation()
    specificSamples.value = loadSpecificSamples()
    vouchingRows.value = loadVouchingRows()
    tolerableErrorRate.value = parseNum(
      allResponses.value.get(TOLERABLE_RATE_KEY)?.remark ?? '0.05',
    ) || 0.05
    testConclusion.value = allResponses.value.get(TEST_CONCLUSION_KEY)?.remark ?? ''
    auditNote.value = allResponses.value.get(NOTE_KEY)?.remark ?? ''
    auditConclusion.value = allResponses.value.get(CONCLUSION_KEY)?.remark ?? ''
  }

  // Initial load
  loadFromResponses()

  // Watch allResponses for external changes (other tabs / OO sync)
  watch(
    () => [
      allResponses.value.get(VOUCHING_ROWS_KEY)?.remark,
      allResponses.value.get(SPECIFIC_SAMPLES_KEY)?.remark,
      allResponses.value.get(NOTE_KEY)?.remark,
      allResponses.value.get(CONCLUSION_KEY)?.remark,
      allResponses.value.get(POP_DESC_KEY)?.remark,
      allResponses.value.get(TEST_CONCLUSION_KEY)?.remark,
      allResponses.value.get(TOLERABLE_RATE_KEY)?.remark,
    ],
    ([newVouching, newSamples, newNote, newConclusion, _newPopDesc, newTestConc, newRate]) => {
      if (newVouching !== undefined && newVouching !== serializeVouchingRows()) {
        vouchingRows.value = loadVouchingRows()
      }
      if (newSamples !== undefined && newSamples !== serializeSpecificSamples()) {
        specificSamples.value = loadSpecificSamples()
      }
      if (newNote !== undefined && newNote !== auditNote.value) {
        auditNote.value = newNote ?? ''
      }
      if (newConclusion !== undefined && newConclusion !== auditConclusion.value) {
        auditConclusion.value = newConclusion ?? ''
      }
      if (newTestConc !== undefined && newTestConc !== testConclusion.value) {
        testConclusion.value = newTestConc ?? ''
      }
      if (newRate !== undefined) {
        const parsed = parseNum(newRate) || 0.05
        if (parsed !== tolerableErrorRate.value) tolerableErrorRate.value = parsed
      }
      // Reload population from individual keys
      population.value = loadPopulation()
    },
  )

  // ─── Serialization ───────────────────────────────────────────────────────

  function serializeVouchingRows(): string {
    return JSON.stringify(vouchingRows.value.map(serializeVouchingRow))
  }

  function serializeSpecificSamples(): string {
    return JSON.stringify(specificSamples.value.map(serializeSpecificSample))
  }

  // ─── Save Helpers ────────────────────────────────────────────────────────

  let vouchingSaveTimer: ReturnType<typeof setTimeout> | null = null
  let samplesSaveTimer: ReturnType<typeof setTimeout> | null = null

  function scheduleVouchingSave(): void {
    if (vouchingSaveTimer) clearTimeout(vouchingSaveTimer)
    vouchingSaveTimer = setTimeout(() => {
      vouchingSaveTimer = null
      persistVouchingRows()
    }, 2000)
  }

  function scheduleSpecificSamplesSave(): void {
    if (samplesSaveTimer) clearTimeout(samplesSaveTimer)
    samplesSaveTimer = setTimeout(() => {
      samplesSaveTimer = null
      persistSpecificSamples()
    }, 2000)
  }

  /** 持久化凭证核对行数据 */
  function persistVouchingRows(): void {
    const item: ChecklistItem = {
      item_id: VOUCHING_ROWS_KEY,
      conclusion: null,
      remark: serializeVouchingRows(),
    }
    allResponses.value.set(VOUCHING_ROWS_KEY, item)
    saveImmediate([item])
  }

  /** 立即持久化凭证核对行（select字段触发） */
  function persistVouchingRowsImmediate(): void {
    const item: ChecklistItem = {
      item_id: VOUCHING_ROWS_KEY,
      conclusion: null,
      remark: serializeVouchingRows(),
    }
    allResponses.value.set(VOUCHING_ROWS_KEY, item)
    saveImmediate([item])
  }

  /** 持久化特定样本行 */
  function persistSpecificSamples(): void {
    const item: ChecklistItem = {
      item_id: SPECIFIC_SAMPLES_KEY,
      conclusion: null,
      remark: serializeSpecificSamples(),
    }
    allResponses.value.set(SPECIFIC_SAMPLES_KEY, item)
    saveImmediate([item])
  }

  // ─── Population CRUD ─────────────────────────────────────────────────────

  /** 更新抽样总体单字段 */
  function updatePopulation(field: keyof SamplePopulation, value: any): void {
    if (isReadonly.value) return

    const pop = { ...population.value }
    const numFields: Array<keyof SamplePopulation> = ['totalCount', 'totalAmount', 'sampleSize', 'actualDrawn']
    const strFields: Array<keyof SamplePopulation> = ['populationDesc', 'sampleCalcRef']

    if (numFields.includes(field)) {
      ;(pop as any)[field] = parseNum(value)
    } else if (strFields.includes(field)) {
      ;(pop as any)[field] = String(value ?? '')
    } else {
      return
    }
    population.value = pop

    // Map field to storage key
    const keyMap: Record<keyof SamplePopulation, string> = {
      populationDesc: POP_DESC_KEY,
      totalCount: POP_COUNT_KEY,
      totalAmount: POP_AMOUNT_KEY,
      sampleSize: POP_SIZE_KEY,
      actualDrawn: POP_DRAWN_KEY,
      sampleCalcRef: POP_REF_KEY,
    }
    const itemId = keyMap[field]
    const remark = numFields.includes(field) ? String((pop as any)[field]) : ((pop as any)[field] || null)
    const item: ChecklistItem = { item_id: itemId, conclusion: null, remark }
    allResponses.value.set(itemId, item)
    saveDebouncedText(item)
  }

  // ─── Specific Samples CRUD ───────────────────────────────────────────────

  /** 添加特定样本行 */
  function addSpecificSample(): void {
    if (isReadonly.value) return
    const newRow = emptySpecificSampleRow()
    specificSamples.value = [...specificSamples.value, newRow]
    scheduleSpecificSamplesSave()
  }

  /** 删除特定样本行 */
  function removeSpecificSample(id: string): void {
    if (isReadonly.value) return
    const idx = specificSamples.value.findIndex((r) => r.id === id)
    if (idx === -1) return
    specificSamples.value = specificSamples.value.filter((r) => r.id !== id)
    scheduleSpecificSamplesSave()
  }

  /** 更新特定样本行字段 */
  function updateSpecificSample(id: string, field: keyof SpecificSampleRow, value: any): void {
    if (isReadonly.value) return
    const idx = specificSamples.value.findIndex((r) => r.id === id)
    if (idx === -1) return

    const row = { ...specificSamples.value[idx] }
    if (field === 'amount') {
      row.amount = parseNum(value)
    } else if (field === 'description' || field === 'reason') {
      ;(row as any)[field] = String(value ?? '')
    } else {
      return
    }

    const newRows = [...specificSamples.value]
    newRows[idx] = row
    specificSamples.value = newRows
    scheduleSpecificSamplesSave()
  }

  // ─── Vouching Rows CRUD ──────────────────────────────────────────────────

  /** 添加凭证核对行（自动编号） */
  function addVouchingRow(): void {
    if (isReadonly.value) return
    const nextSeq = vouchingRows.value.length + 1
    const newRow = emptyVouchingRow(nextSeq)
    vouchingRows.value = [...vouchingRows.value, newRow]
    scheduleVouchingSave()
  }

  /** 删除凭证核对行并重新编号 */
  function removeVouchingRow(id: string): void {
    if (isReadonly.value) return
    const idx = vouchingRows.value.findIndex((r) => r.id === id)
    if (idx === -1) return
    const filtered = vouchingRows.value.filter((r) => r.id !== id)
    // 重新编号 seq
    vouchingRows.value = filtered.map((r, i) => ({ ...r, seq: i + 1 }))
    scheduleVouchingSave()
  }

  /** 更新凭证核对行指定字段 */
  function updateVouchingRow(id: string, field: keyof VouchingRow, value: any): void {
    if (isReadonly.value) return
    const idx = vouchingRows.value.findIndex((r) => r.id === id)
    if (idx === -1) return

    const row = { ...vouchingRows.value[idx] }
    if (VOUCHING_NUMERIC_FIELDS.includes(field)) {
      ;(row as any)[field] = parseNum(value)
    } else if (VOUCHING_STRING_FIELDS.includes(field) || field === 'id') {
      ;(row as any)[field] = String(value ?? '')
    } else {
      return
    }

    const newRows = [...vouchingRows.value]
    newRows[idx] = row
    vouchingRows.value = newRows

    // select类字段立即保存，金额/文本字段 debounce 2s
    if (SELECT_FIELDS.includes(field)) {
      persistVouchingRowsImmediate()
    } else {
      scheduleVouchingSave()
    }
  }

  // ─── Computed: 核对结果统计 ──────────────────────────────────────────────

  /**
   * G32: 核查笔数 — COUNT rows where ANY of existenceCheck/accuracyCheck/appropriatenessCheck
   * is non-empty and not '不适用'
   */
  const checkedCount: ComputedRef<number> = computed(() => {
    return vouchingRows.value.filter((row) => {
      const checks = [row.existenceCheck, row.accuracyCheck, row.appropriatenessCheck]
      return checks.some((c) => c !== '' && c !== '不适用')
    }).length
  })

  /**
   * H32: 核查金额合计 — SUM amount of rows where at least one check field is filled
   * (same filter as checkedCount)
   */
  const checkedAmountTotal: ComputedRef<number> = computed(() => {
    const checkedRows = vouchingRows.value.filter((row) => {
      const checks = [row.existenceCheck, row.accuracyCheck, row.appropriatenessCheck]
      return checks.some((c) => c !== '' && c !== '不适用')
    })
    return sumColumn(checkedRows, 'amount')
  })

  /** G45: 凭证核对金额合计 — SUM all vouching rows amount */
  const vouchingAmountTotal: ComputedRef<number> = computed(() => {
    return sumColumn(vouchingRows.value, 'amount')
  })

  // ─── Computed: 例外汇总 E48-G50 ─────────────────────────────────────────

  /** 例外汇总：3行（存在性/准确性/记录恰当性） */
  const exceptionSummary: ComputedRef<ExceptionSummaryRow[]> = computed(() => {
    const totalChecked = checkedAmountTotal.value

    // 存在性例外: existenceCheck === '未核实'
    const existenceRows = vouchingRows.value.filter((r) => r.existenceCheck === '未核实')
    const existenceAmount = sumColumn(existenceRows, 'amount')

    // 准确性例外: accuracyCheck === '金额不一致'
    const accuracyRows = vouchingRows.value.filter((r) => r.accuracyCheck === '金额不一致')
    const accuracyAmount = sumColumn(accuracyRows, 'amount')

    // 记录恰当性例外: appropriatenessCheck === '不恰当'
    const appropriatenessRows = vouchingRows.value.filter((r) => r.appropriatenessCheck === '不恰当')
    const appropriatenessAmount = sumColumn(appropriatenessRows, 'amount')

    return [
      {
        category: '存在性',
        count: existenceRows.length,
        amount: existenceAmount,
        rate: computeExceptionRate(existenceAmount, totalChecked),
      },
      {
        category: '准确性',
        count: accuracyRows.length,
        amount: accuracyAmount,
        rate: computeExceptionRate(accuracyAmount, totalChecked),
      },
      {
        category: '记录恰当性',
        count: appropriatenessRows.length,
        amount: appropriatenessAmount,
        rate: computeExceptionRate(appropriatenessAmount, totalChecked),
      },
    ]
  })

  /** 任一例外占比 > tolerableErrorRate */
  const hasExceedingException: ComputedRef<boolean> = computed(() => {
    return exceptionSummary.value.some((row) => row.rate > tolerableErrorRate.value)
  })

  // ─── Tolerable Error Rate ────────────────────────────────────────────────

  /** 更新可容忍误差率 */
  function updateTolerableErrorRate(rate: number): void {
    if (isReadonly.value) return
    tolerableErrorRate.value = rate
    const item: ChecklistItem = {
      item_id: TOLERABLE_RATE_KEY,
      conclusion: null,
      remark: String(rate),
    }
    allResponses.value.set(TOLERABLE_RATE_KEY, item)
    saveImmediate([item])
  }

  // ─── Test Conclusion ─────────────────────────────────────────────────────

  /** 更新测试结论（select类，立即保存） */
  function updateTestConclusion(value: string): void {
    if (isReadonly.value) return
    testConclusion.value = value
    const item: ChecklistItem = {
      item_id: TEST_CONCLUSION_KEY,
      conclusion: null,
      remark: value || null,
    }
    allResponses.value.set(TEST_CONCLUSION_KEY, item)
    saveImmediate([item])
  }

  // ─── 审计说明/结论 ───────────────────────────────────────────────────────

  function saveAuditNote(text: string): void {
    if (isReadonly.value) return
    auditNote.value = text
    const item: ChecklistItem = {
      item_id: NOTE_KEY,
      conclusion: null,
      remark: text || null,
    }
    allResponses.value.set(NOTE_KEY, item)
    saveDebouncedText(item)
  }

  function saveAuditConclusion(text: string): void {
    if (isReadonly.value) return
    auditConclusion.value = text
    const item: ChecklistItem = {
      item_id: CONCLUSION_KEY,
      conclusion: null,
      remark: text || null,
    }
    allResponses.value.set(CONCLUSION_KEY, item)
    saveDebouncedText(item)
  }

  // ─── 导入导出接口（委托 useD1ImportExport 共享模块） ──────────────────────

  const {
    exportTemplate: _exportTemplate,
    exportData: _exportData,
  } = useD1ImportExport({ wpId, sheetCode: 'D1-13', sheetLabel: '凭证核对' })

  const exportTemplate = _exportTemplate
  const exportData = _exportData

  /**
   * 导入 xlsx 数据（仅解析凭证核对明细行，跳过抽样定义和例外汇总）
   */
  async function importData(file: File): Promise<ImportResult> {
    const formData = new FormData()
    formData.append('file', file)
    try {
      const res = await http.post(
        `/api/workpapers/${wpId.value}/d1/import-data`,
        formData,
        {
          params: { sheet: 'D1-13' },
          headers: { 'Content-Type': 'multipart/form-data' },
        },
      )
      const data = res.data?.data ?? res.data
      if (data?.rows && Array.isArray(data.rows)) {
        vouchingRows.value = data.rows.map((r: any, idx: number) => deserializeVouchingRow(r, idx + 1))
        persistVouchingRowsImmediate()
      }
      return {
        success: true,
        rowCount: data?.row_count ?? vouchingRows.value.length,
        fieldCount: data?.field_count ?? 0,
      }
    } catch (err: any) {
      const msg = err?.response?.data?.message || err?.message || '导入失败'
      return {
        success: false,
        rowCount: 0,
        fieldCount: 0,
        errors: [msg],
      }
    }
  }

  // ─── Cleanup ─────────────────────────────────────────────────────────────

  onBeforeUnmount(() => {
    if (vouchingSaveTimer) {
      clearTimeout(vouchingSaveTimer)
      persistVouchingRows()
    }
    if (samplesSaveTimer) {
      clearTimeout(samplesSaveTimer)
      persistSpecificSamples()
    }
  })

  // ─── Return ──────────────────────────────────────────────────────────────

  return {
    // 抽样总体
    population,
    updatePopulation,

    // 特定样本
    specificSamples,
    addSpecificSample,
    removeSpecificSample,
    updateSpecificSample,

    // 凭证核对明细
    vouchingRows,
    addVouchingRow,
    removeVouchingRow,
    updateVouchingRow,

    // 核对结果统计
    checkedCount,
    checkedAmountTotal,
    vouchingAmountTotal,

    // 例外汇总
    exceptionSummary,
    hasExceedingException,
    tolerableErrorRate,
    updateTolerableErrorRate,

    // 测试结论
    testConclusion,
    updateTestConclusion,

    // 审计说明/结论
    auditNote,
    auditConclusion,
    saveAuditNote,
    saveAuditConclusion,

    // 导入导出
    exportTemplate,
    exportData,
    importData,
  }
}

export default useD1SamplingVouching
