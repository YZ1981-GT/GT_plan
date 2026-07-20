/**
 * useG7SubFormData — G7 长期股权投资(子公司组) 数据加载/保存/selfLoad
 *
 * Spec: .kiro/specs/g7-long-term-equity-subsidiary/
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
 * 注意：本组无 writebackTB（子公司组不直接回写 trial_balance）
 *
 * Requirements: 1.4, 7.6
 */
import { ref, onScopeDispose, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import type { ChecklistResponse } from './useF1FormData'
import type { G7SameControlStoredRow } from '../g7-long-term-equity-subsidiary/initial/g7SameControlModel'
import type { G7DisposalPackageRow } from '../g7-long-term-equity-subsidiary/disposal/g7DisposalPackageModel'

// ─── Constants ───────────────────────────────────────────────────────────────

const DRAFT_PREFIX = 'g7-sub-draft'
const MAX_RETRIES = 3
const BASE_DELAY_MS = 500

function draftKey(wpId: string, itemId: string): string {
  return `${DRAFT_PREFIX}:${wpId}:${itemId}`
}

// ─── Content Types ───────────────────────────────────────────────────────────

export interface G7ControlRow {
  id: string
  seq: number
  dimension: string
  criterion: string
  investeeName: string
  /** 是 / 否 / 不适用（与 UI 下拉一致） */
  judgmentResult: '是' | '否' | '不适用' | ''
  judgmentBasis: string
  riskFlag: '高' | '中' | '低' | '无' | ''
  auditConclusion: string
  indexRef: string
}

export interface G7ControlSection {
  id: string
  sectionNo: string
  title: string
  rows: G7ControlRow[]
}

export interface G7ControlJudgmentData {
  sections: G7ControlSection[]
  overallConclusion: string
  decision?: import('./g7ControlJudgmentModel').G7ControlDecision
  additionalDecisions?: import('./g7ControlJudgmentModel').G7ControlDecision[]
}

export type G7SameControlRow = G7SameControlStoredRow

/** @deprecated 旧版扁平行；新实现见 g7NotSameControlModel.G7NotSameControlStoredRow */
export interface G7NotSameControlRow {
  id: string
  seq: number
  investeeName: string
  acquisitionDate: string
  mergerType?: string
  consideration?: number
  directFees?: number
  initialCost?: number
  acquireeNetAssetsFV?: number
  shareholdingRatio?: number
  shareOfFV?: number
  goodwill?: number
  auditConclusion: string
  /** 新三类业务区段标记 */
  section?: 'merger' | 'step' | 'reverse'
  [key: string]: unknown
}

export interface G7SubsequentRow {
  id: string
  seq: number
  investeeName: string
  openingBalance: number
  addition: number
  impairment: number
  declaredDividend: number
  shareholdingRatio: number
  investmentIncome: number
  closingBalance: number
  companyClosing: number
  difference: number
  auditConclusion: string
}

export interface G7DisposalSingleRow {
  id: string
  seq: number
  investeeName: string
  disposalDate: string
  disposalRatio: number
  disposalPrice: number
  bookValue: number
  receivableDividend: number
  priorOCI: number
  recyclableOCI: number
  individualGain: number
  consolidatedAdjustment: number
  consolidatedNetAssetShare: number
  consolidatedGain: number
  auditConclusion: string
  indexRef: string
}

export interface G7VoucherRow {
  id: string
  seq: number
  date: string
  voucherNo: string
  businessContent: string
  counterAccount: string
  debitAmount: number
  creditAmount: number
  attachment: string
  supportingDoc: string
  check1: boolean
  check2: boolean
  check3: boolean
  check4: boolean
  check5: boolean
  check6: boolean
  indexRef: string
  isAbnormal: boolean
  abnormalNote: string
  riskLevel: 'high' | 'medium' | 'low' | 'none'
  remark: string
}

export interface G7SubsidiaryContent {
  controlJudgment: G7ControlJudgmentData
  sameControl: { rows: G7SameControlRow[]; conclusion: string }
  notSameControl: { rows: G7NotSameControlRow[]; conclusion: string }
  subsequent: { rows: G7SubsequentRow[]; conclusion: string }
  disposalSingle: { rows: G7DisposalSingleRow[]; conclusion: string }
  disposalPackage: { rows: G7DisposalPackageRow[]; conclusion: string }
  voucher: { rows: G7VoucherRow[]; debitTotal: number; creditTotal: number; balanced: boolean }
}

// ─── Options ─────────────────────────────────────────────────────────────────

export interface UseG7SubFormDataOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  onAfterSave?: () => void
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useG7SubFormData(opts: UseG7SubFormDataOptions) {
  const { wpId, projectId } = opts

  const isLoading = ref(false)
  const loadError = ref<string | null>(null)
  const sheetCache = ref<Record<string, any>>({})
  const allResponses = ref<Map<string, ChecklistResponse>>(new Map())
  const renderMeta = ref<Record<string, any>>({})
  /** idle | pending | saving | saved | error — 供底稿保存状态指示 */
  const savePhase = ref<'idle' | 'pending' | 'saving' | 'saved' | 'error'>('idle')
  const _debounceTimers = new Map<string, ReturnType<typeof setTimeout>>()
  const _pendingItems = new Set<string>()

  /** item_id前缀：筛选G7子公司组相关数据 */
  const ITEM_PREFIXES = ['G7-7-', 'G7-8-', 'G7-9-', 'G7-10-', 'G7-11-', 'G7-12-', 'G7-18-']

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
      ElMessage.warning('G7(子公司)数据加载失败，可手动填写')
    }
  }

  /**
   * selfLoad: 当组件在bundle内嵌场景 htmlData 为 null 时，
   * 自行调用 render-config?force_component_type=g7-long-term-equity-subsidiary 获取渲染数据
   */
  async function selfLoad(): Promise<void> {
    if (!wpId.value) return
    try {
      const res = await api.get(`/api/workpapers/${wpId.value}/render-config`, {
        params: { force_component_type: 'g7-long-term-equity-subsidiary' },
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
   * 从 sheetCache 中解析出完整的 G7SubsidiaryContent 结构
   * 用于从 render-config 返回的 html_data 中提取各 section 数据
   */
  function parseContent(): Partial<G7SubsidiaryContent> {
    const result: Partial<G7SubsidiaryContent> = {}

    for (const [key, value] of Object.entries(sheetCache.value)) {
      if (!value) continue
      const content = value?.content ?? value

      if (key.includes('G7-7') || key.includes('初始判断')) {
        result.controlJudgment = content as G7SubsidiaryContent['controlJudgment']
      } else if (key.includes('G7-8') || key.includes('同控')) {
        result.sameControl = content as G7SubsidiaryContent['sameControl']
      } else if (key.includes('G7-9') || key.includes('非同控')) {
        result.notSameControl = content as G7SubsidiaryContent['notSameControl']
      } else if (key.includes('G7-10') || key.includes('后续计量')) {
        result.subsequent = content as G7SubsidiaryContent['subsequent']
      } else if (key.includes('G7-11') || key.includes('非一揽子')) {
        result.disposalSingle = content as G7SubsidiaryContent['disposalSingle']
      } else if (key.includes('G7-12') || key.includes('一揽子')) {
        result.disposalPackage = content as G7SubsidiaryContent['disposalPackage']
      } else if (key.includes('G7-18') || key.includes('凭证检查')) {
        result.voucher = content as G7SubsidiaryContent['voucher']
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
    savePhase.value = 'saving'

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
        savePhase.value = 'saved'
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
    savePhase.value = 'error'
    try {
      localStorage.setItem(draftKey(wpId.value, itemId), JSON.stringify(updated))
      ElMessage.warning(`G7(子公司) 数据暂存本地（${itemId}），网络恢复后将自动同步`)
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
    ElMessage.warning('G7(子公司) 数据暂存本地，网络恢复后将自动同步')
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
    savePhase.value = 'pending'

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
   * 保存完整 content JSON（POST 到 workpaper content 端点）
   * 用于保存子公司组所有 sheet 的完整结构化数据
   */
  async function saveContent(content: Partial<G7SubsidiaryContent>, retries = MAX_RETRIES): Promise<void> {
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
      ElMessage.warning('G7(子公司) 内容暂存本地，网络恢复后将自动同步')
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
    savePhase,
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
  }
}

export default useG7SubFormData
