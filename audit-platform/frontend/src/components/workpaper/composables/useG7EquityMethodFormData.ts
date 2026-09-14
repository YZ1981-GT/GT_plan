/**
 * useG7EquityMethodFormData — G7 长期股权投资(权益法组) 数据加载/保存/selfLoad
 *
 * Spec: .kiro/specs/g7-long-term-equity-method/
 *
 * 职责：
 * - selfLoad: bundle内嵌场景 htmlData 为 null 时自行获取 render-config
 * - 数据加载（loadResponses + loadRenderConfig 并行）
 * - 指数退避重试保存（3次，500ms/1000ms/2000ms）
 * - localStorage 暂存（网络全部失败时 fallback）
 * - 恢复暂存数据（加载后自动 flush）
 * - 批量保存（saveBatch）
 * - 组件卸载时 flush 未保存数据（onScopeDispose）
 *
 * 注意：本组无 writebackTB（权益法组不直接回写 trial_balance）
 *
 * Requirements: 1.4, 7.2
 */
import { ref, onScopeDispose, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import type { ChecklistResponse } from './useF1FormData'
import type { G7BasicInfoRow } from '../g7-long-term-equity-method/info/g7BasicInfoModel'
import type { G7FinancialInfoRow } from '../g7-long-term-equity-method/info/g7FinancialInfoModel'

// ─── Constants ───────────────────────────────────────────────────────────────

const DRAFT_PREFIX = 'g7-equity-method-draft'
const MAX_RETRIES = 3
const BASE_DELAY_MS = 500

function draftKey(wpId: string, itemId: string): string {
  return `${DRAFT_PREFIX}:${wpId}:${itemId}`
}

// ─── Content Types ───────────────────────────────────────────────────────────

export type BasicInfoRow = G7BasicInfoRow
export type FinancialInfoRow = G7FinancialInfoRow

export interface AccountingPolicyRow {
  id: string
  seq: number
  policyItem: string
  investeePolicy: string
  investorPolicy: string
  isConsistent: '一致' | '不一致' | '不适用'
  adjustmentAmount: number
  adjustmentNote: string
}

export interface InvestmentCostTestRow {
  id: string
  seq: number
  investeeName: string
  /** 稳定被投资单位 ID（优先取自 G7-4） */
  investeeId?: string
  investDate: string
  mergeType: '合并' | '非合并'
  consideration: number
  directCosts: number
  initialCost: number
  netAssetFairValue: number
  shareOfNetAssets: number
  difference: number
  differenceNature: '商誉' | '营业外收入'
  accountingTreatment: string
  fvAdjustmentDetail: string
  adjustedNetAssets: number
  adjustedShareOfNetAssets: number
  /** 持股比例（小数 0~1）；优先于外部 ratioMap */
  investmentRatio?: number
  auditConclusion: '无差异' | '存在差异-可接受' | '存在差异-需调整'
  indexRef: string
}

export interface EquityMethodCalcRow {
  id: string
  seq: number
  investeeName: string
  /** 稳定被投资单位 ID（可选，优先取自 G7-4） */
  investeeId?: string
  reportedNetProfit: number
  internalTransactionAdj: number
  fvDepreciationAdj: number
  accountingPolicyAdj: number
  otherAdj: number
  /**
   * 由 G7-16 写入的 otherAdj 分量；再同步时先剥离再累加，避免覆盖手工/G7-6 调整。
   */
  otherAdjFromG716?: number
  adjustedNetProfit: number
  investmentRatio: number
  equityShare: number
  confirmedIncome: number
  /** 账面确认OCI（用于与测算OCI份额比较） */
  confirmedOci: number
  ociDifference: number
  confirmedOtherEquity: number
  otherEquityDifference: number
  incomeDifference: number
  ociChange: number
  ociShare: number
  otherEquityChange: number
  otherEquityShare: number
  dividendDistributed: number
  openingBalance: number
  closingBalance: number
  /** 第2部分：长投四科目期末滚存与差额拆解 */
  costOpening: number
  costChange: number
  costClosing: number
  pnlAdjOpening: number
  pnlAdjChange: number
  pnlAdjClosing: number
  ociBalOpening: number
  ociBalChange: number
  ociBalClosing: number
  otherEqBalOpening: number
  otherEqBalChange: number
  otherEqBalClosing: number
  auditedNetAssets: number
  shareOfAuditedNetAssets: number
  lteiBookBalance: number
  netAssetShareVariance: number
  /**
   * G7-2 审定期初/期末总额（勾稽对照）。
   * 期初勾稽差异P = 四段期初合计 − g72OpeningTotal
   * 期末勾稽差异S = 长投账面余额 − g72ClosingTotal
   */
  g72OpeningTotal: number
  g72ClosingTotal: number
  openingReconVariance: number
  closingReconVariance: number
  goodwill: number
  cumulativeFvAdj: number
  impairment: number
  unexplainedVariance: number
  /**
   * 未解释差额⑮处理性质；仅选定后才可生成对应科目建议分录
   * pending=待拆解(不成账) / skip=无需调整
   */
  unexplainedNature:
    | 'pending'
    | 'skip'
    | 'investmentIncome'
    | 'impairment'
    | 'oci'
    | 'capitalReserve'
    | 'priorPeriod'
    | 'goodwill'
    | 'fvAdj'
  varianceExplanation: string
  auditConclusion: '无差异' | '差异可接受' | '差异需调整'
}

export interface InternalTransactionRow {
  id: string
  seq: number
  /** 稳定被投资单位 ID（来自 G7-4，优先用于跨表匹配） */
  investeeId?: string
  investeeName: string
  transactionType: '顺流' | '逆流'
  transactionContent: string
  transactionAmount: number
  /** 毛利率（小数 0~1）；未实现利润 = 交易金额 × 毛利率 */
  grossMargin: number
  unrealizedProfit: number
  /** true=用户手填未实现利润，金额/毛利率变更时不再自动覆盖 */
  unrealizedProfitManual?: boolean
  investmentRatio: number
  eliminationAmount: number
  priorElimination: number
  currentChange: number
  eliminationEntry: string
  isRelatedParty: boolean
  auditConclusion: '合理' | '基本合理' | '不合理'
  indexRef: string
  remark: string
}

export interface UnrecognizedLossRow {
  id: string
  seq: number
  investeeName: string
  investeeId?: string
  investmentBookValue: number
  longTermReceivable: number
  otherLongTermEquity: number
  estimatedLiability: number
  totalLongTermEquity: number
  cumulativeLoss: number
  excessLoss: number
  allocationOrder: string
  reduceInvestment: number
  reduceLongTermReceivable: number
  reduceOtherEquity: number
  recognizeEstimatedLiability: number
  unrecognizedLoss: number
  /** 上期累计未确认损失（披露 priorCumulative） */
  priorCumulative: number
  currentChange: number
  /** 手工锁定冲减分配（不再自动瀑布） */
  allocationManual?: boolean
  /** 手工覆盖本期变动 */
  currentChangeManual?: boolean
  auditConclusion: '合理' | '基本合理' | '不合理'
}

export interface ImpairmentTestRow {
  id: string
  seq: number
  investeeName: string
  /** 稳定被投资单位 ID（优先取自 G7-4） */
  investeeId?: string
  bookValue: number
  /** 自 G7-14 带入时的账面快照，用于 stale 检测 */
  sourceBookValue?: number | null
  /** 期初已计提减值准备（consol → open_impairment） */
  openingImpairment?: number
  recoverableAmount: number
  /** true = 可收回金额手工覆盖（不再跟公式） */
  recoverableManual?: boolean
  recoverableOverrideReason?: string
  hasImpairmentSign: boolean
  impairmentAmount: number
  fvLessDisposalCost: number
  valueInUse: number
  auditConclusion: '无需计提' | '需计提' | '已充分计提'
  indexRef: string
  /** 估值依据附件名 */
  attachmentName?: string
}

export interface G7EquityMethodContent {
  basicInfo: { rows: BasicInfoRow[] }
  financialInfo: { rows: FinancialInfoRow[]; groups: { investeeName: string; rows: FinancialInfoRow[] }[] }
  accountingPolicy: { rows: AccountingPolicyRow[]; conclusion: string }
  investmentCostTest: { rows: InvestmentCostTestRow[]; conclusion: string }
  equityMethodCalc: { rows: EquityMethodCalcRow[]; materialityLevel: number; conclusion: string; groups: { investeeName: string; rows: EquityMethodCalcRow[] }[] }
  internalTransaction: { rows: InternalTransactionRow[]; conclusion: string }
  unrecognizedLoss: { rows: UnrecognizedLossRow[]; conclusion: string }
  impairmentTest: { rows: ImpairmentTestRow[]; conclusion: string }
}

// ─── Options ─────────────────────────────────────────────────────────────────

export interface UseG7EquityMethodFormDataOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  onAfterSave?: () => void
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useG7EquityMethodFormData(opts: UseG7EquityMethodFormDataOptions) {
  const { wpId, projectId } = opts

  const isLoading = ref(false)
  const loadError = ref<string | null>(null)
  const sheetCache = ref<Record<string, any>>({})
  const allResponses = ref<Map<string, ChecklistResponse>>(new Map())
  const renderMeta = ref<Record<string, any>>({})
  const _debounceTimers = new Map<string, ReturnType<typeof setTimeout>>()
  const _pendingItems = new Set<string>()

  /** item_id前缀：筛选G7权益法组相关数据 */
  const ITEM_PREFIXES = ['G7-4-', 'G7-5-', 'G7-6-', 'G7-13-', 'G7-14-', 'G7-15-', 'G7-16-', 'G7-17-']

  // ─── Draft Restore ──────────────────────────────────────────────────────────

  /** 恢复 localStorage 中暂存的草稿数据并尝试重新保存 */
  function restoreDrafts(): void {
    if (!wpId.value) return
    const prefix = `${DRAFT_PREFIX}:${wpId.value}:`
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i)
      if (!key?.startsWith(prefix)) continue
      try {
        const itemId = key.slice(prefix.length)
        const stored = JSON.parse(localStorage.getItem(key) || '') as ChecklistResponse
        if (itemId && stored?.item_id) {
          allResponses.value.set(itemId, stored)
          void saveImmediate(itemId, stored, 1)
          localStorage.removeItem(key)
        }
      } catch { /* ignore corrupt draft */ }
    }
  }

  // ─── Load ────────────────────────────────────────────────────────────────────

  /** 加载 checklist-responses 数据 */
  async function loadResponses(): Promise<void> {
    if (!wpId.value) return
    try {
      const res = await api.get(`/api/workpapers/${wpId.value}/checklist-responses`)
      const responses: any[] = Array.isArray(res) ? res : (res?.data ?? [])
      const map = new Map<string, ChecklistResponse>()
      for (const r of responses) {
        if (r.item_id && ITEM_PREFIXES.some((p: string) => r.item_id.startsWith(p))) {
          map.set(r.item_id, {
            item_id: r.item_id,
            conclusion: r.conclusion ?? null,
            remark: r.remark ?? null,
          })
        }
      }
      allResponses.value = map
      restoreDrafts()
    } catch {
      ElMessage.warning('G7(权益法)数据加载失败，可手动填写')
    }
  }

  /**
   * selfLoad: 当组件在bundle内嵌场景 htmlData 为 null 时，
   * 自行调用 render-config?force_component_type=g7-long-term-equity-method 获取渲染数据
   */
  async function selfLoad(): Promise<void> {
    if (!wpId.value) return
    try {
      const res = await api.get(`/api/workpapers/${wpId.value}/render-config`, {
        params: { force_component_type: 'g7-long-term-equity-method' },
        _silent: true,
      } as any)
      const data = res?.data ?? res
      renderMeta.value = data?.html_data ?? data ?? {}
      const sheets = data?.sheets ?? data?.data?.sheets ?? []
      for (const s of sheets) {
        const key = s.sheet_name || s.sheetName || s.name || 'default'
        sheetCache.value[key] = s.html_data ?? s
      }
    } catch {
      // selfLoad 失败不阻塞：组件仍可从 checklist_responses 加载数据
    }
  }

  /** 统一加载入口（loadResponses + selfLoad 并行） */
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
   * 从 sheetCache 中解析出完整的 G7EquityMethodContent 结构
   * 用于从 render-config 返回的 html_data 中提取各 section 数据
   */
  function parseContent(): Partial<G7EquityMethodContent> {
    const result: Partial<G7EquityMethodContent> = {}

    for (const [key, value] of Object.entries(sheetCache.value)) {
      if (!value) continue
      const content = value?.content ?? value

      if (key.includes('G7-4') || key.includes('基本信息')) {
        result.basicInfo = content as G7EquityMethodContent['basicInfo']
      } else if (key.includes('G7-5') || key.includes('财务信息')) {
        result.financialInfo = content as G7EquityMethodContent['financialInfo']
      } else if (key.includes('G7-6') || key.includes('会计政策')) {
        result.accountingPolicy = content as G7EquityMethodContent['accountingPolicy']
      } else if (key.includes('G7-13') || key.includes('投资成本')) {
        result.investmentCostTest = content as G7EquityMethodContent['investmentCostTest']
      } else if (key.includes('G7-14') || key.includes('权益法测算')) {
        result.equityMethodCalc = content as G7EquityMethodContent['equityMethodCalc']
      } else if (key.includes('G7-15') || key.includes('内部交易')) {
        result.internalTransaction = content as G7EquityMethodContent['internalTransaction']
      } else if (key.includes('G7-16') || key.includes('未确认')) {
        result.unrecognizedLoss = content as G7EquityMethodContent['unrecognizedLoss']
      } else if (key.includes('G7-17') || key.includes('减值')) {
        result.impairmentTest = content as G7EquityMethodContent['impairmentTest']
      }
    }

    return result
  }

  // ─── Save (指数退避重试3次 + localStorage暂存) ────────────────────────────────

  /**
   * 立即保存指定 item（带指数退避重试）
   * 重试策略：500ms → 1000ms → 2000ms
   * 全部失败后 localStorage 暂存
   */
  async function saveImmediate(
    itemId: string,
    data: Partial<ChecklistResponse>,
    retries = MAX_RETRIES,
  ): Promise<void> {
    // 清除该 item 的 debounce timer
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
      item_id: itemId,
    }
    allResponses.value.set(itemId, updated)

    // 指数退避重试
    for (let i = 0; i < retries; i++) {
      try {
        await api.put(`/api/workpapers/${wpId.value}/checklist-responses`, {
          project_id: projectId.value,
          items: [{ item_id: itemId, conclusion: updated.conclusion, remark: updated.remark }],
        })
        // 成功 → 清除本地暂存
        try {
          localStorage.removeItem(draftKey(wpId.value, itemId))
        } catch { /* ignore */ }
        try {
          const { emitG7SourceRowsSaved } = await import('./g7DisclosureCrossSheet')
          emitG7SourceRowsSaved({
            projectId: projectId.value,
            wpId: wpId.value,
            itemIds: [itemId],
          })
        } catch { /* ignore */ }
        opts.onAfterSave?.()
        return
      } catch {
        if (i < retries - 1) {
          await new Promise((resolve) => setTimeout(resolve, BASE_DELAY_MS * 2 ** i))
        }
      }
    }

    // 全部重试失败 → localStorage 暂存
    try {
      localStorage.setItem(draftKey(wpId.value, itemId), JSON.stringify(updated))
      ElMessage.warning(`G7(权益法) 数据暂存本地（${itemId}），网络恢复后将自动同步`)
    } catch { /* ignore quota exceeded */ }
  }

  /** 批量保存多个 items（一次 PUT 提交，带重试） */
  async function saveBatch(
    items: Array<{ itemId: string; data: Partial<ChecklistResponse> }>,
    retries = MAX_RETRIES,
  ): Promise<void> {
    if (!items.length || !wpId.value) return

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
        item_id: itemId,
      }
      allResponses.value.set(itemId, updated)
      toSave.push(updated)
    }

    for (let i = 0; i < retries; i++) {
      try {
        await api.put(`/api/workpapers/${wpId.value}/checklist-responses`, {
          project_id: projectId.value,
          items: toSave.map((item) => ({
            item_id: item.item_id,
            conclusion: item.conclusion,
            remark: item.remark,
          })),
        })
        // 成功 → 清除所有相关本地暂存
        for (const item of toSave) {
          try { localStorage.removeItem(draftKey(wpId.value, item.item_id)) } catch { /* ignore */ }
        }
        try {
          const { emitG7SourceRowsSaved } = await import('./g7DisclosureCrossSheet')
          emitG7SourceRowsSaved({
            projectId: projectId.value,
            wpId: wpId.value,
            itemIds: toSave.map(item => item.item_id).filter(Boolean) as string[],
          })
        } catch { /* ignore */ }
        opts.onAfterSave?.()
        return
      } catch {
        if (i < retries - 1) {
          await new Promise((resolve) => setTimeout(resolve, BASE_DELAY_MS * 2 ** i))
        }
      }
    }

    // 全部重试失败 → localStorage 逐项暂存
    for (const item of toSave) {
      try {
        localStorage.setItem(draftKey(wpId.value, item.item_id), JSON.stringify(item))
      } catch { /* ignore */ }
    }
    ElMessage.warning('G7(权益法) 数据暂存本地，网络恢复后将自动同步')
  }

  /** debounce 2000ms 文本字段保存（per item_id 独立计时器） */
  function debouncedSave(itemId: string, data: Partial<ChecklistResponse>): void {
    const existing = allResponses.value.get(itemId) || { item_id: itemId, conclusion: null, remark: null }
    const updated: ChecklistResponse = {
      ...existing,
      ...(data.conclusion !== undefined ? { conclusion: data.conclusion } : {}),
      ...(data.remark !== undefined ? { remark: data.remark } : {}),
      item_id: itemId,
    }
    allResponses.value.set(itemId, updated)
    _pendingItems.add(itemId)

    const prevTimer = _debounceTimers.get(itemId)
    if (prevTimer) clearTimeout(prevTimer)

    const newTimer = setTimeout(() => {
      _debounceTimers.delete(itemId)
      _pendingItems.delete(itemId)
      void saveImmediate(itemId, updated)
    }, 2000)
    _debounceTimers.set(itemId, newTimer)
  }

  /**
   * 多键原子防抖保存：同一计时器批量 PUT，避免 G7-14 SECTION/ROWS 半成功分叉
   */
  function debouncedSaveBatch(
    items: Array<{ itemId: string; data: Partial<ChecklistResponse> }>,
  ): void {
    if (!items.length) return
    const batchIds = items.map((it) => it.itemId)
    const batchKey = `__batch__:${[...batchIds].sort().join('|')}`

    for (const { itemId, data } of items) {
      const existing = allResponses.value.get(itemId) || { item_id: itemId, conclusion: null, remark: null }
      const updated: ChecklistResponse = {
        ...existing,
        ...(data.conclusion !== undefined ? { conclusion: data.conclusion } : {}),
        ...(data.remark !== undefined ? { remark: data.remark } : {}),
        item_id: itemId,
      }
      allResponses.value.set(itemId, updated)
      _pendingItems.add(itemId)
      const prev = _debounceTimers.get(itemId)
      if (prev) clearTimeout(prev)
    }

    const prevBatch = _debounceTimers.get(batchKey)
    if (prevBatch) clearTimeout(prevBatch)

    const timer = setTimeout(() => {
      _debounceTimers.delete(batchKey)
      const toSave: Array<{ itemId: string; data: Partial<ChecklistResponse> }> = []
      for (const itemId of batchIds) {
        _debounceTimers.delete(itemId)
        _pendingItems.delete(itemId)
        const resp = allResponses.value.get(itemId)
        if (resp) {
          toSave.push({
            itemId,
            data: { conclusion: resp.conclusion, remark: resp.remark },
          })
        }
      }
      void saveBatch(toSave)
    }, 2000)
    _debounceTimers.set(batchKey, timer)
    for (const itemId of batchIds) {
      _debounceTimers.set(itemId, timer)
    }
  }

  /**
   * 保存完整 content JSON（POST 到 workpaper content 端点）
   * 用于保存权益法组所有 sheet 的完整结构化数据
   */
  async function saveContent(content: Partial<G7EquityMethodContent>, retries = MAX_RETRIES): Promise<void> {
    if (!wpId.value) return
    for (let i = 0; i < retries; i++) {
      try {
        await api.post(`/api/workpapers/${wpId.value}/content`, {
          project_id: projectId.value,
          content,
        })
        opts.onAfterSave?.()
        return
      } catch {
        if (i < retries - 1) {
          await new Promise((resolve) => setTimeout(resolve, BASE_DELAY_MS * 2 ** i))
        }
      }
    }
    // 全部失败 → localStorage 暂存整体 content
    try {
      localStorage.setItem(`${DRAFT_PREFIX}:${wpId.value}:__content__`, JSON.stringify(content))
      ElMessage.warning('G7(权益法) 内容暂存本地，网络恢复后将自动同步')
    } catch { /* ignore */ }
  }

  // ─── Flush（组件卸载） ───────────────────────────────────────────────────────

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
        void api.put(`/api/workpapers/${wpId.value}/checklist-responses`, {
          project_id: projectId.value,
          items: items.map((item) => ({
            item_id: item.item_id,
            conclusion: item.conclusion,
            remark: item.remark,
          })),
        }).catch(() => { /* best-effort flush */ })
      }
    }
  }

  // ─── Lifecycle ───────────────────────────────────────────────────────────────

  onScopeDispose(() => {
    _flushPending()
  })

  // ─── Return ──────────────────────────────────────────────────────────────────

  return {
    // State
    data: allResponses,
    loading: isLoading,
    error: loadError,
    sheetCache,
    renderMeta,
    // Load
    load: loadAll,
    selfLoad,
    getSheet,
    parseContent,
    loadResponses,
    // Save
    save: saveImmediate,
    saveImmediate,
    saveBatch,
    saveContent,
    debouncedSave,
    debouncedSaveBatch,
  }
}

export default useG7EquityMethodFormData
