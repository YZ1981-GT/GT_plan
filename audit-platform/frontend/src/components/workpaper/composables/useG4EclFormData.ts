/**
 * useG4EclFormData — G4 债权投资(ECL组) 数据加载/保存/selfLoad
 *
 * Spec: .kiro/specs/g4-bond-investment-ecl/
 * Task: 4.3
 *
 * 职责：
 * - selfLoad逻辑（render-config?force_component_type=g4-bond-investment-ecl）
 * - 从 GET /api/workpapers/:wpId/checklist-responses 加载 G4-ecl 数据
 * - debounce 2000ms 文本字段保存（per item_id 独立计时器）
 * - 结论/状态/选择类字段立即保存（saveImmediate）
 * - 批量保存（saveBatch）
 * - 保存完整 content JSON（saveContent）
 * - 组件卸载时 flush 未保存数据（onScopeDispose）
 *
 * Requirements: 1.6
 */
import { ref, onScopeDispose, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'

// ─── G4EclContent 顶层数据接口 ──────────────────────────────────────────────

export interface StageClassificationRow {
  id: string
  seq: number
  investProject: string
  initialRating: string
  currentRating: string
  ratingChange: string
  overdue30Days: boolean
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
  bookBalance: number
  pvFutureCashFlow: number
  creditLossRate: number
  impairmentProvision: number
  bookValue: number
  balanceAdjustment: number
  adjustedCreditLossRate: number
  impairmentAdjustment: number
  adjBookBalance: number
  adjImpairment: number
  adjBookValue: number
  priorImpairment: number
  currentProvision: number
  currentReversal: number
  differenceNote: string
}

export interface ImpairmentCalcData {
  rows: ImpairmentCalcRow[]
  conclusion: string
}

export interface MethodEvalRow {
  id: string
  checkItem: string
  checkContent: string
  companyMethod: string
  auditEvaluation: '合理' | '基本合理' | '不合理'
  note: string
}

export interface GroupBasisRow {
  id: string
  groupName: string
  basis: string
  riskCharacteristic: string
  sampleSize: number
  auditEvaluation: '合理' | '不合理'
  note: string
}

export interface ParameterEvalRow {
  id: string
  paramName: string
  dataSource: string
  calcMethod: string
  verificationResult: string
  auditEvaluation: '合理' | '基本合理' | '不合理'
  note: string
}

export interface EclMeasurementData {
  methodEvaluation: MethodEvalRow[]
  groupBasis: GroupBasisRow[]
  parameterEvaluation: ParameterEvalRow[]
  conclusion: string
}

export interface ReversalRow {
  id: string
  seq: number
  unitName: string
  reversalReason: string
  recoveryMethod: string
  originalBasis: string
  reversalAmount: number
  accumulatedProvision: number
  reasonAnalysis: string
  isReasonable: '合理' | '不合理'
  indexRef: string
}

export interface WriteOffRow {
  id: string
  seq: number
  unitName: string
  writeOffType: '到期' | '逾期' | '其他'
  writeOffAmount: number
  writeOffReason: string
  writeOffProcedure: string
  isRelatedParty: boolean
  reasonAnalysis: string
  isReasonable: '合理' | '不合理'
  indexRef: string
}

export interface ReversalWriteOffData {
  reversals: ReversalRow[]
  writeOffs: WriteOffRow[]
  conclusion: string
}

export interface VoucherCheckRow {
  id: string
  seq: number
  section: 'debit' | 'credit'
  date: string
  voucherNo: string
  businessContent: string
  counterAccount: string
  detailAccount: string
  debitAmount: number
  creditAmount: number
  attachment: string | null
  supportingDocDesc: string
  checkOriginalComplete: boolean
  checkAuthorized: boolean
  checkAccountingCorrect: boolean
  checkInitialCostCorrect: boolean
  checkInterestCorrect: boolean
  checkImpairmentCorrect: boolean
  indexRef: string
  isAbnormal: boolean
  abnormalNote: string
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

/** G4 ECL组 完整 content JSON 顶层接口 */
export interface G4EclContent {
  stageClassification: StageClassificationData   // G4-9
  impairmentCalc: ImpairmentCalcData             // G4-10
  eclMeasurement: EclMeasurementData             // G4-11
  reversalWriteOff: ReversalWriteOffData         // G4-12
  voucherCheck: VoucherCheckData                 // G4-13
}

// ─── ChecklistResponse 类型 ─────────────────────────────────────────────────

export interface ChecklistResponse {
  item_id: string
  conclusion: string | null
  remark: string | null
}

// ─── Options ─────────────────────────────────────────────────────────────────

export interface UseG4EclFormDataOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  onAfterSave?: () => void
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useG4EclFormData(opts: UseG4EclFormDataOptions) {
  const { wpId, projectId } = opts

  const allResponses = ref<Map<string, ChecklistResponse>>(new Map())
  const isLoading = ref(false)
  const loadError = ref<string | null>(null)
  const sheetCache = ref<Record<string, any>>({})

  // Per-item debounce timers
  const _debounceTimers = new Map<string, ReturnType<typeof setTimeout>>()
  const _pendingItems = new Set<string>()

  /** item_id前缀：筛选G4 ECL相关数据 */
  const ITEM_PREFIXES = ['G4-9-', 'G4-10-', 'G4-11-', 'G4-12-', 'G4-13-', 'G4-ecl-']

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
      ElMessage.warning('G4(ECL)数据加载失败，可手动填写')
    }
  }

  /**
   * selfLoad: 当组件在bundle内嵌场景 htmlData 为 null 时，
   * 自行调用 render-config?force_component_type=g4-bond-investment-ecl 获取渲染数据
   */
  async function selfLoad(): Promise<void> {
    if (!wpId.value) return
    try {
      const { data } = await http.get(`/api/workpapers/${wpId.value}/render-config`, {
        params: { force_component_type: 'g4-bond-investment-ecl' },
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
   * 从sheetCache中解析出完整的G4EclContent结构
   * 用于从render-config返回的html_data中提取各section数据
   */
  function parseContent(): Partial<G4EclContent> {
    const result: Partial<G4EclContent> = {}

    // 遍历sheetCache提取各sheet数据
    for (const [key, value] of Object.entries(sheetCache.value)) {
      if (!value) continue
      const content = value?.content ?? value

      if (key.includes('G4-9') || key.includes('三阶段')) {
        result.stageClassification = content as StageClassificationData
      } else if (key.includes('G4-10') || key.includes('减值准备测算')) {
        result.impairmentCalc = content as ImpairmentCalcData
      } else if (key.includes('G4-11') || key.includes('预期信用损失')) {
        result.eclMeasurement = content as EclMeasurementData
      } else if (key.includes('G4-12') || key.includes('转回')) {
        result.reversalWriteOff = content as ReversalWriteOffData
      } else if (key.includes('G4-13') || key.includes('凭证检查')) {
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
   * 用于保存G4 ECL组所有sheet的完整结构化数据
   */
  async function saveContent(content: Partial<G4EclContent>): Promise<void> {
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

export default useG4EclFormData
