/**
 * useCControlTestData — C2~C15 控制测试数据持久化 composable
 *
 * 职责：
 * - selfLoad(): GET /api/workpapers/:wpId/checklist-responses，按前缀 C{n}- 解析到结构化 state
 * - 解析新格式 C{n}-sum-{m}-* → summaryRows
 * - 解析旧/新格式 C{n}-ctrl-{m}-* → controlPages
 * - 解析新格式 C{n}-dev-{m}-* → deviationStates
 * - 解析 C{n}-cycle-conclusion
 * - persistAll(): 序列化 state → items → PUT（统一新格式 item_id）
 * - 动态行：addControlPoint(name) / removeControlPoint(index)
 * - debounceSave(): 2s debounce 文本字段
 * - saveImmediate(): 枚举/结论/决策树变更即时保存
 * - flushPendingSaves(): unmount 时确保无数据丢失
 * - readonly guard: isReadonly 时跳过所有保存
 *
 * Spec: .kiro/specs/c-control-test-refresh/
 * Task: 3.3
 * Requirements: 8.1, 8.2, 8.3, 2.3
 */
import { ref, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { type DecisionTreeState, createEmptyState } from './useDeviationDecisionTree'
import { eventBus } from '@/utils/eventBus'
import { CYCLE_CONFIG } from '@/components/workpaper/composables/useCControlTest'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 汇总表行（15 列） */
export interface SummaryRow {
  subProcess: string
  controlId: string
  controlName: string
  description: string
  affectedItems: string
  assertion: string
  attribute: string
  frequency: string
  relatedRisk: string
  testMethod: string
  sampleSize: number | null
  hasDeviation: '是' | '否' | null
  remediation: string
  defect: string
  indexRef: string
}

/** 单控制测试子页 */
export interface ControlPage {
  /** 控制属性/频率/相关风险/测试方法（从汇总复制） */
  attribute: string
  frequency: string
  relatedRisk: string
  testMethod: string
  /** 控制测试程序 */
  testProcedure: string
  /** 总体定义 */
  populationDef: string
  /** 总体来源 */
  populationSource: string
  /** 样本规模 */
  sampleSize: number | null
  /** 抽样方法 */
  samplingMethod: string
  /** 抽样过程 */
  samplingProcess: string
  /** 偏差定义 */
  deviationDef: string
  /** 逐笔样本结果 */
  samples: SampleResult[]
}

/** 单笔样本结果 */
export interface SampleResult {
  /** 样本描述 */
  description: string
  /** 结果：有效/偏差/不适用 */
  result: '有效' | '偏差' | '不适用' | null
}

/** C 控制测试完整状态 */
export interface CControlTestState {
  cycleNumber: number  // 2~15
  summaryRows: SummaryRow[]
  controlPages: ControlPage[]
  deviationStates: DecisionTreeState[]
  cycleConclusion: string
}

/** checklist-responses 单条 item */
export interface ChecklistResponseItem {
  item_id: string
  conclusion: string | null
  remark: string | null
  wp_ref?: string | null
}

/** B23 控制点引用项（一键引用生成汇总行） */
export interface B23ControlPointItem {
  controlId: string
  controlName: string
  relatedRisk: string
  description?: string
  subProcess?: string
}

// ─── Constants ───────────────────────────────────────────────────────────────

const DEBOUNCE_MS = 2000

/** 汇总表字段列表（用于序列化） */
const SUMMARY_FIELDS = [
  'subProcess', 'controlId', 'controlName', 'description', 'affectedItems',
  'assertion', 'attribute', 'frequency', 'relatedRisk', 'testMethod',
  'sampleSize', 'hasDeviation', 'remediation', 'defect', 'indexRef',
] as const

/** 汇总表枚举字段（存 conclusion） */
const SUMMARY_ENUM_FIELDS = new Set([
  'assertion', 'attribute', 'frequency', 'testMethod', 'hasDeviation',
])

/** 子页文本字段列表 */
const CTRL_PAGE_TEXT_FIELDS = [
  'testProcedure', 'populationDef', 'populationSource',
  'samplingMethod', 'samplingProcess', 'deviationDef',
] as const

/** 子页枚举字段 */
const CTRL_PAGE_ENUM_FIELDS = new Set(['attribute', 'frequency', 'relatedRisk', 'testMethod'])

// ─── Helpers ─────────────────────────────────────────────────────────────────

function createEmptySummaryRow(): SummaryRow {
  return {
    subProcess: '', controlId: '', controlName: '', description: '',
    affectedItems: '', assertion: '', attribute: '', frequency: '',
    relatedRisk: '', testMethod: '', sampleSize: null, hasDeviation: null,
    remediation: '', defect: '', indexRef: '',
  }
}

function createEmptyControlPage(): ControlPage {
  return {
    attribute: '', frequency: '', relatedRisk: '', testMethod: '',
    testProcedure: '', populationDef: '', populationSource: '',
    sampleSize: null, samplingMethod: '', samplingProcess: '',
    deviationDef: '', samples: [],
  }
}

/**
 * 从 wpCode (e.g., "C2", "C10", "C14-2") 提取循环编号
 * C14-2 → 14（偏差评价 Cx-2 底稿的主循环编号）
 */
export function extractCycleNumber(wpCode: string): number {
  const match = wpCode.match(/^C(\d+)/i)
  return match ? parseInt(match[1], 10) : 0
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useCControlTestData(
  wpId: Ref<string>,
  projectId: Ref<string>,
  wpCode: Ref<string>,
  isReadonly: Ref<boolean>,
) {
  // ─── Reactive state ────────────────────────────────────────────────────────
  const state = ref<CControlTestState>({
    cycleNumber: 0,
    summaryRows: [],
    controlPages: [],
    deviationStates: [],
    cycleConclusion: '',
  })

  const loading = ref(false)
  const saving = ref(false)

  let saveTimer: ReturnType<typeof setTimeout> | null = null
  let pendingSave = false

  // ─── selfLoad ──────────────────────────────────────────────────────────────

  async function selfLoad(): Promise<void> {
    if (!wpId.value) return
    loading.value = true

    const n = extractCycleNumber(wpCode.value)
    state.value.cycleNumber = n

    try {
      const res = await api.get(`/api/workpapers/${wpId.value}/checklist-responses`)
      const responses: ChecklistResponseItem[] = Array.isArray(res) ? res : (res?.data ?? [])
      parseResponses(responses, n)
    } catch {
      ElMessage.warning('数据加载失败，可手动填写')
    } finally {
      loading.value = false
    }
  }

  function parseResponses(responses: ChecklistResponseItem[], n: number): void {
    const prefix = `C${n}-`
    const filtered = responses.filter(r => r.item_id?.startsWith(prefix))

    // Collect summary rows: C{n}-sum-{m}-{field}
    const sumPattern = new RegExp(`^C${n}-sum-(\\d+)-(\\w+)$`)
    const sumMap = new Map<number, Partial<SummaryRow>>()
    let maxSum = 0

    // Collect ctrl pages: C{n}-ctrl-{m}-{field} or C{n}-ctrl-{m}-sample-{s}-result
    const ctrlFieldPattern = new RegExp(`^C${n}-ctrl-(\\d+)-(\\w+)$`)
    const ctrlSamplePattern = new RegExp(`^C${n}-ctrl-(\\d+)-sample-(\\d+)-(\\w+)$`)
    const ctrlMap = new Map<number, Partial<ControlPage>>()
    const sampleMap = new Map<number, Map<number, Partial<SampleResult>>>()
    let maxCtrl = 0

    // Collect deviation states: C{n}-dev-{m}-step{k} or C{n}-dev-{m}-conclusion or C{n}-dev-{m}-exceptionDesc
    const devStepPattern = new RegExp(`^C${n}-dev-(\\d+)-step(\\d+)$`)
    const devConclusionPattern = new RegExp(`^C${n}-dev-(\\d+)-conclusion$`)
    const devExceptionDescPattern = new RegExp(`^C${n}-dev-(\\d+)-exceptionDesc$`)
    const devMap = new Map<number, Partial<DecisionTreeState & { exceptionDesc?: string }>>()
    let maxDev = 0

    for (const r of filtered) {
      if (!r.item_id) continue
      const id = r.item_id

      // ─── Parse summary rows ───
      const sumMatch = id.match(sumPattern)
      if (sumMatch) {
        const m = parseInt(sumMatch[1], 10)
        const field = sumMatch[2]
        if (m > maxSum) maxSum = m
        if (!sumMap.has(m)) sumMap.set(m, {})
        const row = sumMap.get(m)!
        if (field === 'sampleSize') {
          row.sampleSize = r.conclusion ? parseInt(r.conclusion, 10) || null : null
        } else if (SUMMARY_ENUM_FIELDS.has(field)) {
          ;(row as any)[field] = r.conclusion || ''
        } else {
          ;(row as any)[field] = r.remark || r.conclusion || ''
        }
        continue
      }

      // ─── Parse ctrl sample results ───
      const sampleMatch = id.match(ctrlSamplePattern)
      if (sampleMatch) {
        const m = parseInt(sampleMatch[1], 10)
        const s = parseInt(sampleMatch[2], 10)
        const field = sampleMatch[3]
        if (m > maxCtrl) maxCtrl = m
        if (!sampleMap.has(m)) sampleMap.set(m, new Map())
        const samples = sampleMap.get(m)!
        if (!samples.has(s)) samples.set(s, {})
        const sample = samples.get(s)!
        if (field === 'result') {
          sample.result = (r.conclusion as SampleResult['result']) || null
        } else if (field === 'description') {
          sample.description = r.remark || ''
        }
        continue
      }

      // ─── Parse ctrl page fields ───
      const ctrlMatch = id.match(ctrlFieldPattern)
      if (ctrlMatch) {
        const m = parseInt(ctrlMatch[1], 10)
        const field = ctrlMatch[2]
        if (m > maxCtrl) maxCtrl = m
        if (!ctrlMap.has(m)) ctrlMap.set(m, {})
        const page = ctrlMap.get(m)!
        if (field === 'sampleSize') {
          page.sampleSize = r.conclusion ? parseInt(r.conclusion, 10) || null : null
        } else if (CTRL_PAGE_ENUM_FIELDS.has(field)) {
          ;(page as any)[field] = r.conclusion || ''
        } else {
          ;(page as any)[field] = r.remark || r.conclusion || ''
        }
        continue
      }

      // ─── Parse deviation steps ───
      const devStepMatch = id.match(devStepPattern)
      if (devStepMatch) {
        const m = parseInt(devStepMatch[1], 10)
        const k = parseInt(devStepMatch[2], 10)
        if (m > maxDev) maxDev = m
        if (!devMap.has(m)) devMap.set(m, {})
        const dev = devMap.get(m)!
        const val = r.conclusion || null
        if (k === 1) dev.step1 = val as DecisionTreeState['step1']
        else if (k === 2) dev.step2 = val as DecisionTreeState['step2']
        else if (k === 3) dev.step3 = val as DecisionTreeState['step3']
        else if (k === 4) dev.step4 = val as DecisionTreeState['step4']
        else if (k === 6) dev.step6 = val as DecisionTreeState['step6']
        continue
      }

      // ─── Parse deviation conclusion ───
      const devConcMatch = id.match(devConclusionPattern)
      if (devConcMatch) {
        const m = parseInt(devConcMatch[1], 10)
        if (m > maxDev) maxDev = m
        // conclusion stored but state is derived from steps
        continue
      }

      // ─── Parse deviation exceptionDesc ───
      const devExcMatch = id.match(devExceptionDescPattern)
      if (devExcMatch) {
        const m = parseInt(devExcMatch[1], 10)
        if (m > maxDev) maxDev = m
        if (!devMap.has(m)) devMap.set(m, {})
        const dev = devMap.get(m)!
        ;(dev as any).exceptionDesc = r.remark || ''
        continue
      }

      // ─── Parse cycle conclusion ───
      if (id === `C${n}-cycle-conclusion`) {
        state.value.cycleConclusion = r.conclusion || r.remark || ''
        continue
      }

      // ─── Legacy format: C{n}-ctrl-{i}-objective etc. (backward compat) ───
      // Old format items that don't match new patterns are parsed into ctrlMap
      // with best-effort field mapping (already handled by ctrlFieldPattern above)
    }

    // ─── Build state arrays ───
    const totalRows = Math.max(maxSum, maxCtrl, maxDev)

    const summaryRows: SummaryRow[] = []
    const controlPages: ControlPage[] = []
    const deviationStates: DecisionTreeState[] = []

    for (let i = 1; i <= totalRows; i++) {
      // Summary row
      const sumPartial = sumMap.get(i)
      summaryRows.push({ ...createEmptySummaryRow(), ...(sumPartial || {}) })

      // Control page
      const ctrlPartial = ctrlMap.get(i)
      const page: ControlPage = { ...createEmptyControlPage(), ...(ctrlPartial || {}) }

      // Build samples for this control page
      if (sampleMap.has(i)) {
        const samplesForPage = sampleMap.get(i)!
        const maxS = Math.max(...samplesForPage.keys(), 0)
        const samples: SampleResult[] = []
        for (let s = 1; s <= maxS; s++) {
          const partial = samplesForPage.get(s)
          samples.push({ description: '', result: null, ...(partial || {}) })
        }
        page.samples = samples
      }
      controlPages.push(page)

      // Deviation state
      const devPartial = devMap.get(i)
      deviationStates.push({ ...createEmptyState(), ...(devPartial || {}) })
    }

    state.value.summaryRows = summaryRows
    state.value.controlPages = controlPages
    state.value.deviationStates = deviationStates
  }

  // ─── Serialize → items ─────────────────────────────────────────────────────

  function serializeAll(): ChecklistResponseItem[] {
    const n = state.value.cycleNumber
    const items: ChecklistResponseItem[] = []

    // ─── Summary rows ───
    for (let i = 0; i < state.value.summaryRows.length; i++) {
      const row = state.value.summaryRows[i]
      const m = i + 1
      for (const field of SUMMARY_FIELDS) {
        const value = row[field]
        const itemId = `C${n}-sum-${m}-${field}`

        if (field === 'sampleSize') {
          items.push({
            item_id: itemId,
            conclusion: value != null ? String(value) : null,
            remark: null,
          })
        } else if (SUMMARY_ENUM_FIELDS.has(field)) {
          items.push({
            item_id: itemId,
            conclusion: (value as string) || null,
            remark: null,
          })
        } else {
          items.push({
            item_id: itemId,
            conclusion: null,
            remark: (value as string) || null,
          })
        }
      }
    }

    // ─── Control pages ───
    for (let i = 0; i < state.value.controlPages.length; i++) {
      const page = state.value.controlPages[i]
      const m = i + 1

      // Enum fields
      for (const field of ['attribute', 'frequency', 'relatedRisk', 'testMethod'] as const) {
        items.push({
          item_id: `C${n}-ctrl-${m}-${field}`,
          conclusion: page[field] || null,
          remark: null,
        })
      }

      // Text fields
      for (const field of CTRL_PAGE_TEXT_FIELDS) {
        items.push({
          item_id: `C${n}-ctrl-${m}-${field}`,
          conclusion: null,
          remark: page[field] || null,
        })
      }

      // Sample size
      items.push({
        item_id: `C${n}-ctrl-${m}-sampleSize`,
        conclusion: page.sampleSize != null ? String(page.sampleSize) : null,
        remark: null,
      })

      // Samples
      for (let s = 0; s < page.samples.length; s++) {
        const sample = page.samples[s]
        const sIdx = s + 1
        items.push({
          item_id: `C${n}-ctrl-${m}-sample-${sIdx}-description`,
          conclusion: null,
          remark: sample.description || null,
        })
        items.push({
          item_id: `C${n}-ctrl-${m}-sample-${sIdx}-result`,
          conclusion: sample.result || null,
          remark: null,
        })
      }
    }

    // ─── Deviation states ───
    for (let i = 0; i < state.value.deviationStates.length; i++) {
      const dev = state.value.deviationStates[i]
      const m = i + 1

      items.push({ item_id: `C${n}-dev-${m}-step1`, conclusion: dev.step1 || null, remark: null })
      items.push({ item_id: `C${n}-dev-${m}-step2`, conclusion: dev.step2 || null, remark: null })
      items.push({ item_id: `C${n}-dev-${m}-step3`, conclusion: dev.step3 || null, remark: null })
      items.push({ item_id: `C${n}-dev-${m}-step4`, conclusion: dev.step4 || null, remark: null })
      items.push({ item_id: `C${n}-dev-${m}-step6`, conclusion: dev.step6 || null, remark: null })

      // exceptionDesc (文本字段，存 remark)
      const excDesc = (dev as any).exceptionDesc || ''
      items.push({ item_id: `C${n}-dev-${m}-exceptionDesc`, conclusion: null, remark: excDesc || null })

      // Deviation conclusion (derived, but stored for quick read)
      items.push({
        item_id: `C${n}-dev-${m}-conclusion`,
        conclusion: null, // will be filled by evaluateDecisionTree at render
        remark: null,
      })
    }

    // ─── Cycle conclusion ───
    items.push({
      item_id: `C${n}-cycle-conclusion`,
      conclusion: state.value.cycleConclusion || null,
      remark: null,
    })

    return items
  }

  // ─── persistAll (PUT) ──────────────────────────────────────────────────────

  async function persistAll(): Promise<void> {
    if (isReadonly.value) return
    if (!wpId.value) return

    const items = serializeAll()
    if (items.length === 0) return

    saving.value = true
    try {
      await api.put(`/api/workpapers/${wpId.value}/checklist-responses`, {
        project_id: projectId.value,
        items,
      })
    } catch (err: any) {
      const msg = err?.message || ''
      if (msg !== 'canceled' && err?.code !== 'ERR_CANCELED') {
        ElMessage.error('保存失败，数据已保留在本地')
      }
    } finally {
      saving.value = false
    }
  }

  // ─── debounceSave (2s for text fields) ─────────────────────────────────────

  function debounceSave(): void {
    if (isReadonly.value) return
    pendingSave = true
    if (saveTimer) clearTimeout(saveTimer)
    saveTimer = setTimeout(() => {
      saveTimer = null
      pendingSave = false
      persistAll()
    }, DEBOUNCE_MS)
  }

  // ─── saveImmediate (enum/conclusion/decision tree changes) ─────────────────

  function saveImmediate(): void {
    if (isReadonly.value) return
    if (saveTimer) {
      clearTimeout(saveTimer)
      saveTimer = null
    }
    pendingSave = false
    persistAll()
  }

  // ─── flushPendingSaves (onBeforeUnmount) ───────────────────────────────────

  function flushPendingSaves(): void {
    if (saveTimer) {
      clearTimeout(saveTimer)
      saveTimer = null
    }
    if (pendingSave) {
      pendingSave = false
      persistAll()
    }
  }

  // ─── Dynamic row management ────────────────────────────────────────────────

  /**
   * 添加新控制点。name 为 ElMessageBox.prompt 确认后传入的控制名称。
   * 调用者负责弹出确认对话框，此处仅处理数据层。
   */
  function addControlPoint(name: string): void {
    if (isReadonly.value) return
    if (!name.trim()) return

    const newSummary = createEmptySummaryRow()
    newSummary.controlName = name.trim()
    state.value.summaryRows.push(newSummary)

    state.value.controlPages.push(createEmptyControlPage())
    state.value.deviationStates.push(createEmptyState())

    saveImmediate()
  }

  /**
   * 删除控制点（同时删除汇总行、子页、偏差状态）
   */
  function removeControlPoint(index: number): void {
    if (isReadonly.value) return
    if (index < 0 || index >= state.value.summaryRows.length) return

    state.value.summaryRows.splice(index, 1)
    state.value.controlPages.splice(index, 1)
    state.value.deviationStates.splice(index, 1)

    saveImmediate()
  }

  // ─── Field update helpers: Summary row ─────────────────────────────────────

  /** 更新汇总表文本字段（debounce 保存） */
  function updateSummaryText(
    rowIndex: number,
    field: 'subProcess' | 'controlId' | 'controlName' | 'description' |
           'affectedItems' | 'relatedRisk' | 'remediation' | 'defect' | 'indexRef',
    value: string,
  ): void {
    if (isReadonly.value) return
    if (rowIndex < 0 || rowIndex >= state.value.summaryRows.length) return
    state.value.summaryRows[rowIndex][field] = value
    debounceSave()
  }

  /** 更新汇总表枚举字段（即时保存） */
  function updateSummaryEnum(
    rowIndex: number,
    field: 'assertion' | 'attribute' | 'frequency' | 'testMethod' | 'hasDeviation',
    value: string,
  ): void {
    if (isReadonly.value) return
    if (rowIndex < 0 || rowIndex >= state.value.summaryRows.length) return
    ;(state.value.summaryRows[rowIndex] as any)[field] = value
    saveImmediate()
  }

  /** 更新汇总表样本规模（即时保存） */
  function updateSummarySampleSize(rowIndex: number, value: number | null): void {
    if (isReadonly.value) return
    if (rowIndex < 0 || rowIndex >= state.value.summaryRows.length) return
    state.value.summaryRows[rowIndex].sampleSize = value
    saveImmediate()
  }

  // ─── Field update helpers: Control page ────────────────────────────────────

  /** 更新子页文本字段（debounce 保存） */
  function updateCtrlPageText(
    pageIndex: number,
    field: typeof CTRL_PAGE_TEXT_FIELDS[number],
    value: string,
  ): void {
    if (isReadonly.value) return
    if (pageIndex < 0 || pageIndex >= state.value.controlPages.length) return
    ;(state.value.controlPages[pageIndex] as any)[field] = value
    debounceSave()
  }

  /** 更新子页枚举字段（即时保存） */
  function updateCtrlPageEnum(
    pageIndex: number,
    field: 'attribute' | 'frequency' | 'relatedRisk' | 'testMethod',
    value: string,
  ): void {
    if (isReadonly.value) return
    if (pageIndex < 0 || pageIndex >= state.value.controlPages.length) return
    state.value.controlPages[pageIndex][field] = value
    saveImmediate()
  }

  /** 更新子页样本规模（即时保存） */
  function updateCtrlPageSampleSize(pageIndex: number, value: number | null): void {
    if (isReadonly.value) return
    if (pageIndex < 0 || pageIndex >= state.value.controlPages.length) return
    state.value.controlPages[pageIndex].sampleSize = value
    saveImmediate()
  }

  /** 添加样本行 */
  function addSample(pageIndex: number): void {
    if (isReadonly.value) return
    if (pageIndex < 0 || pageIndex >= state.value.controlPages.length) return
    state.value.controlPages[pageIndex].samples.push({ description: '', result: null })
    saveImmediate()
  }

  /** 删除样本行 */
  function removeSample(pageIndex: number, sampleIndex: number): void {
    if (isReadonly.value) return
    if (pageIndex < 0 || pageIndex >= state.value.controlPages.length) return
    const samples = state.value.controlPages[pageIndex].samples
    if (sampleIndex < 0 || sampleIndex >= samples.length) return
    samples.splice(sampleIndex, 1)
    saveImmediate()
  }

  /** 更新样本描述（debounce 保存） */
  function updateSampleDescription(pageIndex: number, sampleIndex: number, value: string): void {
    if (isReadonly.value) return
    if (pageIndex < 0 || pageIndex >= state.value.controlPages.length) return
    const samples = state.value.controlPages[pageIndex].samples
    if (sampleIndex < 0 || sampleIndex >= samples.length) return
    samples[sampleIndex].description = value
    debounceSave()
  }

  /** 更新样本结果（即时保存） */
  function updateSampleResult(
    pageIndex: number,
    sampleIndex: number,
    value: SampleResult['result'],
  ): void {
    if (isReadonly.value) return
    if (pageIndex < 0 || pageIndex >= state.value.controlPages.length) return
    const samples = state.value.controlPages[pageIndex].samples
    if (sampleIndex < 0 || sampleIndex >= samples.length) return
    samples[sampleIndex].result = value
    saveImmediate()
  }

  // ─── Field update helpers: Deviation state ─────────────────────────────────

  /** 更新偏差决策树步骤（即时保存） */
  function updateDeviationStep(
    devIndex: number,
    step: 'step1' | 'step2' | 'step3' | 'step4' | 'step6' | 'exceptionDesc',
    value: string | null,
  ): void {
    if (isReadonly.value) return
    if (devIndex < 0 || devIndex >= state.value.deviationStates.length) return
    ;(state.value.deviationStates[devIndex] as any)[step] = value
    // exceptionDesc 使用 debounce（文本字段），其余即时保存
    if (step === 'exceptionDesc') {
      debounceSave()
    } else {
      saveImmediate()
    }
  }

  // ─── Cycle conclusion ──────────────────────────────────────────────────────

  /** 更新循环结论（即时保存） — 仅在结论实际变更时发布 EventBus */
  function updateCycleConclusion(value: string): void {
    if (isReadonly.value) return
    const oldConclusion = state.value.cycleConclusion
    if (oldConclusion === value) return  // 相同值不触发
    state.value.cycleConclusion = value
    saveImmediate()

    // EventBus publish: control:test-concluded → B50
    const n = state.value.cycleNumber
    const config = CYCLE_CONFIG[n]
    if (config) {
      const hasDefects = state.value.summaryRows.some(r => r.defect?.trim())
      eventBus.emit('control:test-concluded', {
        wpCode: wpCode.value,
        cycleName: config.name,
        conclusion: value,
        defectSummary: hasDefects ? '存在控制缺陷' : '',
      })
    }
  }

  // ─── B23 一键引用生成汇总行 (Req 11.4) ────────────────────────────────────

  /**
   * 从 B23 控制了解底稿一键引用控制点，生成对应汇总表行。
   * 对每个 B23 控制点生成一行 SummaryRow（controlId/controlName/relatedRisk 从 B23 带入）。
   * 返回新增行数量。
   */
  function importFromB23(b23Points: B23ControlPointItem[]): number {
    if (isReadonly.value) return 0
    if (!b23Points || b23Points.length === 0) return 0

    let added = 0
    for (const point of b23Points) {
      if (!point.controlId && !point.controlName) continue

      const row = createEmptySummaryRow()
      row.controlId = point.controlId || ''
      row.controlName = point.controlName || ''
      row.relatedRisk = point.relatedRisk || ''
      if (point.description) row.description = point.description
      if (point.subProcess) row.subProcess = point.subProcess

      state.value.summaryRows.push(row)
      state.value.controlPages.push(createEmptyControlPage())
      state.value.deviationStates.push(createEmptyState())
      added++
    }

    if (added > 0) {
      saveImmediate()
    }
    return added
  }

  // ─── 缺陷回填汇总表 (Req 11.3) ───────────────────────────────────────────

  /**
   * 当 Cx-2 决策树推导至缺陷时，回填汇总表「识别出的缺陷」列
   * @param devIndex - 控制点索引 (0-based)
   * @param defectSummary - 缺陷摘要（控制名称+偏差性质+结论）
   */
  function writebackDefect(devIndex: number, defectSummary: string): void {
    if (isReadonly.value) return
    if (devIndex < 0 || devIndex >= state.value.summaryRows.length) return
    state.value.summaryRows[devIndex].defect = defectSummary
    saveImmediate()
  }

  /**
   * 构造缺陷摘要字符串（供 GtIndexChip 跳 A14 时携带）
   * @param devIndex - 控制点索引 (0-based)
   * @param conclusion - 决策树结论
   */
  function buildDefectSummary(devIndex: number, conclusion: string): string {
    const row = state.value.summaryRows[devIndex]
    if (!row) return conclusion
    const name = row.controlName || `控制点${devIndex + 1}`
    return `${name} — ${conclusion}`
  }

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    // State
    state,
    loading,
    saving,
    // Load
    selfLoad,
    // Save
    debounceSave,
    saveImmediate,
    persistAll,
    flushPendingSaves,
    // Dynamic rows
    addControlPoint,
    removeControlPoint,
    // Summary helpers
    updateSummaryText,
    updateSummaryEnum,
    updateSummarySampleSize,
    // Control page helpers
    updateCtrlPageText,
    updateCtrlPageEnum,
    updateCtrlPageSampleSize,
    addSample,
    removeSample,
    updateSampleDescription,
    updateSampleResult,
    // Deviation helpers
    updateDeviationStep,
    // Cycle conclusion
    updateCycleConclusion,
    // B23 import (Req 11.4)
    importFromB23,
    // Defect writeback (Req 11.3)
    writebackDefect,
    buildDefectSummary,
    // Internals (for testing)
    serializeAll,
    parseResponses,
  }
}

export default useCControlTestData
