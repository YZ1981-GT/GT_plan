/**
 * useF3FormData — F3 应付票据数据加载/debounce保存/即时保存/批量保存
 *
 * Spec: .kiro/specs/f3-notes-payable/ Task 3.1
 * 比照 useD4FormData
 */
import { ref, onScopeDispose, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'

export interface ChecklistResponse {
  item_id: string
  conclusion: string | null
  remark: string | null
}

export interface ProjectContext {
  business_category?: string
  applicable_standards?: string[]
  entity_name?: string
  audit_period_end?: string
  bs_date?: string
  [key: string]: any
}

/** 动态行 JSON：优先 remark，兼容历史 conclusion */
export function readRowJson(resp: ChecklistResponse | undefined): string | null {
  if (!resp) return null
  return resp.remark ?? resp.conclusion ?? null
}

export interface UseF3FormDataOptions {
  wpId: Ref<string>
  projectId: Ref<string>
}

export function useF3FormData(options: UseF3FormDataOptions) {
  const { wpId, projectId } = options

  const allResponses = ref<Map<string, ChecklistResponse>>(new Map())
  const isLoading = ref(false)
  const projectContext = ref<ProjectContext>({})
  const sheetCache = ref<Record<string, any>>({})
  const tbValues = ref<Record<string, number>>({})

  const _debounceTimers = new Map<string, ReturnType<typeof setTimeout>>()
  const _pendingItems = new Set<string>()

  async function loadResponses(): Promise<void> {
    if (!wpId.value) return
    try {
      const res = await api.get(`/api/workpapers/${wpId.value}/checklist-responses`)
      const responses: any[] = Array.isArray(res) ? res : (res?.data ?? [])
      const map = new Map<string, ChecklistResponse>()
      for (const r of responses) {
        if (r.item_id?.startsWith('F3-') || r.item_id?.startsWith('F3A') || r.item_id?.startsWith('F3-note-')) {
          map.set(r.item_id, {
            item_id: r.item_id,
            conclusion: r.conclusion ?? null,
            remark: r.remark ?? null,
          })
        }
      }
      allResponses.value = map
    } catch {
      ElMessage.warning('F3数据加载失败，可手动填写')
    }
  }

  async function loadProjectContext(): Promise<void> {
    if (!projectId.value) return
    try {
      const data = await api.get(`/api/projects/${projectId.value}`)
      const ctx = data || {}
      projectContext.value = {
        business_category: ctx.business_category ?? undefined,
        applicable_standards: ctx.applicable_standards ?? [],
        entity_name: ctx.entity_name ?? undefined,
        audit_period_end: ctx.audit_period_end ?? undefined,
        bs_date: ctx.bs_date ?? undefined,
        ...ctx,
      }
    } catch {
      // 项目加载失败：跳过
    }
  }

  async function selfLoad(): Promise<void> {
    if (!wpId.value) return
    try {
      const res = await api.get(
        `/api/workpapers/${wpId.value}/render-config?force_component_type=f3-notes-payable`,
        { _silent: true } as any,
      )
      const data = res?.data ?? res
      const sheets = data?.sheets ?? data?.data?.sheets ?? []
      for (const s of sheets) {
        const html = s.html_data ?? s
        sheetCache.value[s.sheet_name || s.name || 'default'] = html
        // P0-4：捕获 tb_values（可能在 sheet.html_data 或顶层）
        if (html?.tb_values && typeof html.tb_values === 'object') {
          tbValues.value = { ...tbValues.value, ...html.tb_values }
        }
      }
      const topTb = data?.tb_values ?? data?.data?.tb_values
      if (topTb && typeof topTb === 'object') {
        tbValues.value = { ...tbValues.value, ...topTb }
      }
    } catch {
      // selfLoad 失败不阻塞
    }
  }

  /** P0-4：F3-1 审定表试算核对数(2201) 预填——仅无持久化时 seed，不覆盖手工录入。 */
  function seedTrialBalance(): void {
    const v = tbValues.value['2201']
    if (v == null) return
    if (allResponses.value.has('F3-1-adj-tb-2201')) return
    allResponses.value.set('F3-1-adj-tb-2201', {
      item_id: 'F3-1-adj-tb-2201',
      conclusion: null,
      remark: String(v),
    })
  }

  async function loadAll(): Promise<void> {
    isLoading.value = true
    try {
      await Promise.all([loadResponses(), loadProjectContext(), selfLoad()])
      seedTrialBalance()
    } finally {
      isLoading.value = false
    }
  }

  function getSheet(name: string) {
    return sheetCache.value[name] ?? { rows: [] }
  }

  async function _doSave(items: ChecklistResponse[]): Promise<void> {
    if (!wpId.value || items.length === 0) return
    try {
      await api.put(`/api/workpapers/${wpId.value}/checklist-responses`, {
        project_id: projectId.value,
        items: items.map((item) => ({
          item_id: item.item_id,
          conclusion: item.conclusion || null,
          remark: item.remark || null,
        })),
      })
    } catch (err: any) {
      const msg = err?.message || ''
      if (msg !== 'canceled' && err?.code !== 'ERR_CANCELED') {
        ElMessage.error('保存失败，请稍后重试')
      }
    }
  }

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

  /** 子 composable 通过 CustomEvent 批量保存 */
  async function saveItemsFromEvent(items: ChecklistResponse[]): Promise<void> {
    if (!items.length) return
    for (const item of items) {
      allResponses.value.set(item.item_id, item)
    }
    await _doSave(items)
  }

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

  async function writebackTrialBalance(accountCode: string, auditedAmount: number): Promise<void> {
    if (!projectId.value) return
    try {
      await api.put(`/api/projects/${projectId.value}/trial-balance/writeback`, {
        account_code: accountCode,
        audited_amount: auditedAmount,
      })
    } catch {
      ElMessage.warning('审定数回写失败，请手动确认试算表数据')
    }
  }

  function _flushPending(): void {
    for (const timer of _debounceTimers.values()) clearTimeout(timer)
    _debounceTimers.clear()

    if (_pendingItems.size > 0) {
      const items: ChecklistResponse[] = []
      for (const itemId of _pendingItems) {
        const resp = allResponses.value.get(itemId)
        if (resp) items.push(resp)
      }
      _pendingItems.clear()
      if (items.length > 0) void _doSave(items)
    }
  }

  onScopeDispose(() => {
    _flushPending()
  })

  return {
    allResponses,
    isLoading,
    projectContext,
    sheetCache,
    loadAll,
    getSheet,
    saveImmediate,
    saveBatch,
    saveItemsFromEvent,
    debouncedSave,
    writebackTrialBalance,
  }
}

export default useF3FormData
