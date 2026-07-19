import { useWorkpaperAuditYear } from './workpaperAuditYear'
/**
 * useG7FormData — G7 长期股权投资(main组) 数据加载/保存/selfLoad/writebackTB
 *
 * Spec: .kiro/specs/g7-long-term-equity-main/
 *
 * 职责：
 * - selfLoad: bundle内嵌场景 htmlData 为 null 时自行获取 render-config
 * - 数据加载（loadResponses + loadRenderConfig 并行）
 * - 指数退避重试保存（3次，500ms/1000ms/2000ms）
 * - localStorage 暂存（网络全部失败时 fallback）
 * - 恢复暂存数据（加载后自动 flush）
 * - 批量保存（saveBatch）
 * - writebackTB: 保存后回写 trial_balance 审定数(科目1511)
 * - 组件卸载时 flush 未保存数据（onScopeDispose）
 *
 * Requirements: 1.4, 3.3
 */
import { ref, onScopeDispose, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import type { ChecklistResponse } from './useF1FormData'

// ─── Constants ───────────────────────────────────────────────────────────────

const G7_ACCOUNT_CODE = '1511'
const DRAFT_PREFIX = 'g7-main-draft'
const MAX_RETRIES = 3
const BASE_DELAY_MS = 500

function draftKey(wpId: string, itemId: string): string {
  return `${DRAFT_PREFIX}:${wpId}:${itemId}`
}

// ─── Content Types ───────────────────────────────────────────────────────────

export interface G7AdjudicationRow {
  id: string
  item: string
  controlType: 'subsidiary' | 'joint_venture' | 'associate'
  openingUnadjusted: number
  openingAJE: number
  openingRJE: number
  openingAdjusted: number
  closingUnadjusted: number
  closingAJE: number
  closingRJE: number
  closingAdjusted: number
  changeAmount: number
  changeRate: number | null
}

export interface G7AdjudicationGroup {
  id: string
  groupType: 'subsidiary' | 'joint_venture' | 'associate' | 'total' | 'impairment'
  title: string
  collapsed: boolean
  rows: G7AdjudicationRow[]
  subtotal: { openingAdjusted: number; closingAdjusted: number; changeAmount: number; changeRate: number | null }
}

export interface G7DetailRow {
  id: string
  seq: number
  investeeName: string
  controlType: 'subsidiary' | 'joint_venture' | 'associate'
  [key: string]: any
}

export interface G7AdjustmentEntry {
  id: string
  seq: number
  description?: string
  category?: '账项调整' | '报表调整' | '其他'
  reportItem?: string
  noteItem?: string
  indexRef?: string
  sourceGroupId?: string
  /** 以下字段保留用于兼容旧版 G7-3 数据 */
  entryType: 'AJE' | 'RJE'
  date: string
  summary: string
  accountCode: string
  accountName: string
  debitAmount: number
  creditAmount: number
  preparedBy: string
  remark: string
}

export interface G7DisclosureSection {
  id: string
  title: string
  rows?: Array<{ id: string; label: string; value: string | number; editable: boolean }>
  textContent?: string
}

export interface G7MainContent {
  adjudication: { groups: G7AdjudicationGroup[]; netValue: any }
  detail: { rows: G7DetailRow[] }
  adjustment: { entries: G7AdjustmentEntry[] }
  disclosureListed: { sections: G7DisclosureSection[] }
  disclosureSOE: { sections: G7DisclosureSection[] }
}

// ─── Options ─────────────────────────────────────────────────────────────────

export interface UseG7FormDataOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  onAfterSave?: () => void
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useG7FormData(opts: UseG7FormDataOptions) {
  const _auditYearRef = useWorkpaperAuditYear()

  const { wpId, projectId } = opts

  const isLoading = ref(false)
  const loadError = ref<string | null>(null)
  const sheetCache = ref<Record<string, any>>({})
  const allResponses = ref<Map<string, ChecklistResponse>>(new Map())
  const renderMeta = ref<Record<string, any>>({})
  const _debounceTimers = new Map<string, ReturnType<typeof setTimeout>>()
  const _pendingItems = new Set<string>()

  /** item_id前缀：筛选G7 main相关数据 */
  const ITEM_PREFIXES = ['G7A-', 'G7-1-', 'G7-2-', 'G7-3-', 'G7-main-']

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
      ElMessage.warning('G7(main)数据加载失败，可手动填写')
    }
  }

  /**
   * selfLoad: 当组件在bundle内嵌场景 htmlData 为 null 时，
   * 自行调用 render-config?force_component_type=g7-long-term-equity-main 获取渲染数据
   */
  async function selfLoad(): Promise<void> {
    if (!wpId.value) return
    try {
      const res = await api.get(`/api/workpapers/${wpId.value}/render-config`, {
        params: { force_component_type: 'g7-long-term-equity-main' },
        _silent: true,
      } as any)
      const data = res?.data ?? res
      renderMeta.value = data?.html_data ?? data ?? {}
      const sheets = data?.sheets ?? data?.data?.sheets ?? []
      for (const s of sheets) {
        const key = s.sheet_name || s.name || 'default'
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
   * 从 sheetCache 中解析出完整的 G7MainContent 结构
   * 用于从 render-config 返回的 html_data 中提取各 section 数据
   */
  function parseContent(): Partial<G7MainContent> {
    const result: Partial<G7MainContent> = {}

    for (const [key, value] of Object.entries(sheetCache.value)) {
      if (!value) continue
      const content = value?.content ?? value

      if (key.includes('G7-1') || key.includes('审定')) {
        result.adjudication = content as G7MainContent['adjudication']
      } else if (key.includes('G7-2') || key.includes('明细')) {
        result.detail = content as G7MainContent['detail']
      } else if (key.includes('G7-3') || key.includes('调整分录')) {
        result.adjustment = content as G7MainContent['adjustment']
      } else if (key.includes('上市')) {
        result.disclosureListed = content as G7MainContent['disclosureListed']
      } else if (key.includes('国企')) {
        result.disclosureSOE = content as G7MainContent['disclosureSOE']
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
      ElMessage.warning(`G7 数据暂存本地（${itemId}），网络恢复后将自动同步`)
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
    ElMessage.warning('G7 数据暂存本地，网络恢复后将自动同步')
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
   * 保存完整 content JSON（POST 到 workpaper content 端点）
   * 用于保存 G7 main 组所有 sheet 的完整结构化数据
   */
  async function saveContent(content: Partial<G7MainContent>, retries = MAX_RETRIES): Promise<void> {
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
      ElMessage.warning('G7 内容暂存本地，网络恢复后将自动同步')
    } catch { /* ignore */ }
  }

  // ─── writebackTB ────────────────────────────────────────────────────────────

  /**
   * writebackTB: 保存审定数后回写 trial_balance
   * 默认科目1511（投资原值/合计）；可传 accountCode 回写1512减值等。
   * 注意：1511 应回写投资合计（原值），不是净值。
   */
  async function writebackTB(
    adjudicatedAmount: number,
    accountCode: string = G7_ACCOUNT_CODE,
  ): Promise<void> {
    if (!projectId.value) return
    try {
      await api.put(`/api/projects/${projectId.value}/trial-balance/writeback`, {
        account_code: accountCode,
        audited_amount: adjudicatedAmount,
      })
      if (accountCode === G7_ACCOUNT_CODE) {
        await saveImmediate('G7-1-adjudicated-amount', { conclusion: String(adjudicatedAmount) })
      }
      await saveImmediate(
        accountCode === G7_ACCOUNT_CODE ? 'G7-main-tb-writeback' : `G7-main-tb-writeback-${accountCode}`,
        {
          remark: JSON.stringify({ accountCode, auditedAmount: adjudicatedAmount }),
        },
      )
    } catch (err: any) {
      const msg = err?.message || ''
      if (msg !== 'canceled' && err?.code !== 'ERR_CANCELED') {
        ElMessage.warning(`审定数回写失败（${accountCode}），请手动确认试算表数据`)
      }
    }
  }

  /**
   * 从 render 策略或 trial_balance API 获取 TB 取数（科目1511）
   * 优先使用 render 策略 seed 的值（持久化），fallback 到直接查询
   */
  async function fetchTrialBalanceAmount(): Promise<number | null> {
    const _year = _auditYearRef.value
    if (_year == null) return null
    // 优先从 render 策略 seed 的值取
    const seeded = renderMeta.value?.tb_values?.current_amount
    if (seeded != null && seeded !== '') return Number(seeded)

    if (!projectId.value) return null
    try {
      const res = await api.get(`/api/projects/${projectId.value}/trial-balance`, {
        params: { year: _year, account_prefix: G7_ACCOUNT_CODE  },
        _silent: true,
      } as any)
      const list = Array.isArray(res?.data ?? res) ? (res?.data ?? res) : (res?.data?.items ?? [])
      const hit = list.find((r: any) =>
        String(r.standard_account_code ?? r.account_code ?? '').startsWith(G7_ACCOUNT_CODE),
      )
      if (!hit) return null
      // 借方/资产类科目：期末 = 期初 + 借 - 贷 → 取 unadjusted_amount 或计算余额
      return Number(hit.unadjusted_amount ?? hit.audited_amount ?? 0)
    } catch {
      return null
    }
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
    fetchTrialBalanceAmount,
    // Save
    save: saveImmediate,
    saveImmediate,
    saveBatch,
    saveContent,
    debouncedSave,
    // Writeback
    writebackTB,
    writebackTrialBalance: writebackTB,
    accountCode: G7_ACCOUNT_CODE,
  }
}

export default useG7FormData
