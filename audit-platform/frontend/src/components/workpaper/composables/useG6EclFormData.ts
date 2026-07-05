/**
 * useG6EclFormData — G6 其他债权投资(ECL组) 数据加载/保存/selfLoad
 *
 * Spec: .kiro/specs/g6-other-bond-investment-ecl/
 * Task: 4.1
 *
 * 职责：
 * - selfLoad逻辑（render-config?force_component_type=g6-other-bond-investment-ecl）
 * - 从 GET /api/workpapers/:wpId/checklist-responses 加载 G6-ecl 数据
 * - debounce 2000ms 文本字段保存（per item_id 独立计时器）
 * - 结论/状态/选择类字段立即保存（saveImmediate）
 * - 批量保存（saveBatch）
 * - 保存完整 content JSON（saveContent）
 * - 保存后触发 autoSnapshot（版本链联动）
 * - 组件卸载时 flush 未保存数据（onScopeDispose）
 *
 * Requirements: 1.4, 6.2
 */
import { ref, onScopeDispose, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'

// ─── G6EclContent 顶层数据接口 ──────────────────────────────────────────────

export interface StageClassificationRow {
  id: string
  seq: number
  investProject: string
  significantIncrease: string
  lowCreditRisk: boolean
  creditImpaired: boolean
  companyStage: 'Stage1' | 'Stage2' | 'Stage3'
  auditStage: 'Stage1' | 'Stage2' | 'Stage3'
  isConsistent: boolean
  discrepancyNote: string
  indexRef: string
}

export interface StageClassificationData {
  rows: StageClassificationRow[]
  summary: {
    stage1Count: number
    stage2Count: number
    stage3Count: number
    inconsistentCount: number
  }
  conclusion: string
}

export interface ImpairmentCalcRow {
  id: string
  seq: number
  investProject: string
  stageGroup: 'Stage1' | 'Stage2' | 'Stage3'
  amortizedCost: number
  fairValue: number
  creditLossRate: number
  impairmentProvision: number
  bookValue: number
  balanceAdjustment: number
  adjustedCreditLossRate: number
  impairmentAdjustment: number
  stage: 'Stage1' | 'Stage2' | 'Stage3'
  ociImpact: number
  indexRef: string
  adjBalance: number
  adjImpairment: number
  adjBookValue: number
  adjFairValue: number
  priorImpairment: number
  currentProvision: number
  currentReversal: number
  ociAdjustment: number
  differenceNote: string
}

export interface ImpairmentCalcData {
  rows: ImpairmentCalcRow[]
  conclusion: string
}

export interface EclCheckRow {
  id: string
  seq: number
  checkArea: string
  checkItem: string
  auditRequirement: string
  companyParam: string
  isReasonable: '合理' | '基本合理' | '不合理' | ''
  auditConclusion: string
  riskLevel: '高' | '中' | '低' | ''
  indexRef: string
  remark: string
}

export interface EclMeasurementData {
  pdSection: EclCheckRow[]
  lgdSection: EclCheckRow[]
  eadSection: EclCheckRow[]
  discountRateSection: EclCheckRow[]
  forwardLookingSection: EclCheckRow[]
  methodologyContext: string
}

export interface ReversalWriteOffRow {
  id: string
  seq: number
  investProject: string
  type: '转回' | '核销' | '收回'
  amount: number
  reason: string
  approvalProcedure: string
  reasonConclusion: '合理' | '基本合理' | '不合理'
  indexRef: string
}

export interface ReversalWriteOffData {
  rows: ReversalWriteOffRow[]
  conclusion: string
}

export interface VoucherCheckRow {
  id: string
  seq: number
  date: string
  voucherNo: string
  businessContent: string
  counterAccount: string
  detailAccount: string
  debitAmount: number
  creditAmount: number
  attachment: string | null
  supportingDoc: string
  checkOriginal: boolean
  checkAuthorized: boolean
  checkAccounting: boolean
  checkAmount: boolean
  checkClassification: boolean
  checkImpairment: boolean
  checkInterest: boolean
  indexRef: string
  isAbnormal: boolean
  abnormalNote: string
  riskLevel: '高' | '中' | '低' | ''
  suggestion: string
  remark: string
}

export interface VoucherCheckData {
  rows: VoucherCheckRow[]
  debitTotal: number
  creditTotal: number
  difference: number
  isBalanced: boolean
  conclusion: string
}

/** G6 ECL组 完整 content JSON 顶层接口 */
export interface G6EclContent {
  stageClassification: StageClassificationData   // G6-11
  impairmentCalc: ImpairmentCalcData             // G6-12
  eclMeasurement: EclMeasurementData             // G6-13
  reversalWriteOff: ReversalWriteOffData         // G6-14
  voucherCheck: VoucherCheckData                 // G6-15
}

// ─── ChecklistResponse 类型 ─────────────────────────────────────────────────

export interface ChecklistResponse {
  item_id: string
  conclusion: string | null
  remark: string | null
}

// ─── Options ─────────────────────────────────────────────────────────────────

export interface UseG6EclFormDataOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  onAfterSave?: () => void
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useG6EclFormData(opts: UseG6EclFormDataOptions) {
  const { wpId, projectId } = opts

  const allResponses = ref<Map<string, ChecklistResponse>>(new Map())
  const isLoading = ref(false)
  const loadError = ref<string | null>(null)
  const sheetCache = ref<Record<string, any>>({})

  // Per-item debounce timers
  const _debounceTimers = new Map<string, ReturnType<typeof setTimeout>>()
  const _pendingItems = new Set<string>()

  /** item_id前缀：筛选G6 ECL相关数据 */
  const ITEM_PREFIXES = ['G6-11-', 'G6-12-', 'G6-13-', 'G6-14-', 'G6-15-', 'G6-ecl-']

  // ─── Load ────────────────────────────────────────────────────────────────

  /** 加载 checklist-responses 数据 */
  async function loadResponses(): Promise<void> {
    if (!wpId.value) return
    try {
      const { data } = await http.get(`/api/workpapers/${wpId.value}/checklist-responses`)
      const responses: any[] = Array.isArray(data) ? data : (data?.data ?? [])
      const map = new Map<string, ChecklistResponse>()
      for (const r of responses) {
        if (r.item_id && ITEM_PREFIXES.some((p) => r.item_id.startsWith(p))) {
          map.set(r.item_id, {
            item_id: r.item_id,
            conclusion: r.conclusion ?? null,
            remark: r.remark ?? null,
          })
        }
      }
      allResponses.value = map
    } catch {
      ElMessage.warning('G6(ECL)数据加载失败，可手动填写')
    }
  }

  /**
   * selfLoad: 当组件在bundle内嵌场景 htmlData 为 null 时，
   * 自行调用 render-config?force_component_type=g6-other-bond-investment-ecl 获取渲染数据
   */
  async function selfLoad(): Promise<void> {
    if (!wpId.value) return
    try {
      const { data } = await http.get(`/api/workpapers/${wpId.value}/render-config`, {
        params: { force_component_type: 'g6-other-bond-investment-ecl' },
        _silent: true,
      } as any)
      const payload = data?.data ?? data
      const sheets = payload?.sheets ?? []
      for (const s of sheets) {
        const key = s.sheet_name || s.name || 'default'
        sheetCache.value[key] = s.html_data ?? s
      }
    } catch {
      // selfLoad 失败不阻塞：组件仍可从 checklist_responses 加载数据
    }
  }

  /** 统一加载入口 */
  async function loadAll(): Promise<void> {
    isLoading.value = true
    loadError.value = null
    try {
      await Promise.all([loadResponses(), selfLoad()])
    } catch (err: any) {
      loadError.value = err?.message || '加载失败'
    } finally {
      isLoading.value = false
    }
  }

  /** 获取缓存的sheet数据 */
  function getSheet(name: string) {
    return sheetCache.value[name] ?? { rows: [] }
  }

  /**
   * 从sheetCache中解析出完整的G6EclContent结构
   * 用于从render-config返回的html_data中提取各section数据
   */
  function parseContent(): Partial<G6EclContent> {
    const result: Partial<G6EclContent> = {}

    for (const [key, value] of Object.entries(sheetCache.value)) {
      if (!value) continue
      const content = value?.content ?? value

      if (key.includes('G6-11') || key.includes('三阶段')) {
        result.stageClassification = content as StageClassificationData
      } else if (key.includes('G6-12') || key.includes('减值准备测算')) {
        result.impairmentCalc = content as ImpairmentCalcData
      } else if (key.includes('G6-13') || key.includes('预期信用损失')) {
        result.eclMeasurement = content as EclMeasurementData
      } else if (key.includes('G6-14') || key.includes('转回')) {
        result.reversalWriteOff = content as ReversalWriteOffData
      } else if (key.includes('G6-15') || key.includes('凭证检查')) {
        result.voucherCheck = content as VoucherCheckData
      }
    }

    return result
  }

  // ─── Save ────────────────────────────────────────────────────────────────

  /** 内部保存到 checklist-responses 端点 */
  async function _doSave(items: ChecklistResponse[]): Promise<void> {
    if (!wpId.value || items.length === 0) return
    try {
      await http.put(`/api/workpapers/${wpId.value}/checklist-responses`, {
        project_id: projectId.value,
        items: items.map((item) => ({
          item_id: item.item_id,
          conclusion: item.conclusion || null,
          remark: item.remark || null,
        })),
      })
      opts.onAfterSave?.()
    } catch (err: any) {
      const msg = err?.message || ''
      if (msg !== 'canceled' && err?.code !== 'ERR_CANCELED') {
        ElMessage.error('保存失败，请稍后重试')
      }
    }
  }

  /** 立即保存指定 item（结论/状态/选择类字段触发） */
  async function saveImmediate(itemId: string, data: Partial<ChecklistResponse>): Promise<void> {
    const timer = _debounceTimers.get(itemId)
    if (timer) {
      clearTimeout(timer)
      _debounceTimers.delete(itemId)
    }
    _pendingItems.delete(itemId)

    const existing = allResponses.value.get(itemId) || { item_id: itemId, conclusion: null, remark: null }
    const updated: ChecklistResponse = {
      ...existing,
      ...(data.conclusion !== undefined ? { conclusion: data.conclusion } : {}),
      ...(data.remark !== undefined ? { remark: data.remark } : {}),
    }
    allResponses.value.set(itemId, updated)
    await _doSave([updated])
  }

  /** 批量保存多个 items */
  async function saveBatch(items: Array<{ itemId: string; data: Partial<ChecklistResponse> }>): Promise<void> {
    const toSave: ChecklistResponse[] = []
    for (const { itemId, data } of items) {
      const timer = _debounceTimers.get(itemId)
      if (timer) {
        clearTimeout(timer)
        _debounceTimers.delete(itemId)
      }
      _pendingItems.delete(itemId)

      const existing = allResponses.value.get(itemId) || { item_id: itemId, conclusion: null, remark: null }
      const updated: ChecklistResponse = {
        ...existing,
        ...(data.conclusion !== undefined ? { conclusion: data.conclusion } : {}),
        ...(data.remark !== undefined ? { remark: data.remark } : {}),
      }
      allResponses.value.set(itemId, updated)
      toSave.push(updated)
    }
    await _doSave(toSave)
  }

  /** 子composable通过 CustomEvent 批量保存 */
  async function saveItemsFromEvent(items: ChecklistResponse[]): Promise<void> {
    if (!items.length) return
    for (const item of items) {
      allResponses.value.set(item.item_id, item)
    }
    await _doSave(items)
  }

  /** debounce 2000ms 文本字段保存（per item_id 独立计时器） */
  function debouncedSave(itemId: string, data: Partial<ChecklistResponse>): void {
    const existing = allResponses.value.get(itemId) || { item_id: itemId, conclusion: null, remark: null }
    const updated: ChecklistResponse = {
      ...existing,
      ...(data.conclusion !== undefined ? { conclusion: data.conclusion } : {}),
      ...(data.remark !== undefined ? { remark: data.remark } : {}),
    }
    allResponses.value.set(itemId, updated)
    _pendingItems.add(itemId)

    const prevTimer = _debounceTimers.get(itemId)
    if (prevTimer) clearTimeout(prevTimer)

    const timer = setTimeout(() => {
      _debounceTimers.delete(itemId)
      _pendingItems.delete(itemId)
      void _doSave([updated])
    }, 2000)
    _debounceTimers.set(itemId, timer)
  }

  /**
   * 保存完整 content JSON（POST到workpaper content端点）
   * 用于保存G6 ECL组所有sheet的完整结构化数据
   * 保存成功后触发 onAfterSave → autoSnapshot（版本链联动）
   */
  async function saveContent(content: Partial<G6EclContent>): Promise<void> {
    if (!wpId.value) return
    try {
      await http.post(`/api/workpapers/${wpId.value}/content`, {
        project_id: projectId.value,
        content,
      })
      opts.onAfterSave?.()
    } catch (err: any) {
      const msg = err?.message || ''
      if (msg !== 'canceled' && err?.code !== 'ERR_CANCELED') {
        ElMessage.error('内容保存失败，请稍后重试')
      }
    }
  }

  // ─── Flush（组件卸载） ───────────────────────────────────────────────────

  function _flushPending(): void {
    for (const timer of _debounceTimers.values()) {
      clearTimeout(timer)
    }
    _debounceTimers.clear()

    if (_pendingItems.size > 0) {
      const items: ChecklistResponse[] = []
      for (const itemId of _pendingItems) {
        const resp = allResponses.value.get(itemId)
        if (resp) items.push(resp)
      }
      _pendingItems.clear()
      if (items.length > 0) {
        void _doSave(items)
      }
    }
  }

  // ─── Lifecycle ───────────────────────────────────────────────────────────

  onScopeDispose(() => {
    _flushPending()
  })

  return {
    // State
    allResponses,
    isLoading,
    loadError,
    sheetCache,
    // Load
    loadAll,
    selfLoad,
    getSheet,
    parseContent,
    // Save
    saveImmediate,
    saveBatch,
    saveItemsFromEvent,
    debouncedSave,
    saveContent,
  }
}

export default useG6EclFormData
