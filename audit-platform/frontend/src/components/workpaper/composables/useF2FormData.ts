/**
 * useF2FormData — F2 存货核心组数据加载/debounce保存/EventBus/试算表回写
 *
 * Spec: .kiro/specs/f2-inventory-main/ Task 3.1
 * 比照 useD4FormData / useF3FormData
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

export interface UseF2FormDataOptions {
  wpId: Ref<string>
  projectId: Ref<string>
}

function isF2ItemId(itemId: string): boolean {
  return (
    itemId.startsWith('F2-')
    || itemId.startsWith('F2A')
    || itemId.startsWith('F2-note-')
  )
}

/** 动态行 JSON：优先 remark，兼容历史 conclusion */
export function readRowJson(resp: ChecklistResponse | undefined): string | null {
  if (!resp) return null
  return resp.remark ?? resp.conclusion ?? null
}

/** 把项目侧适用准则字段规整为 string[]（兼容 v2 对象 / 单字符串 / 数组） */
export function normalizeApplicableStandards(raw: unknown): string[] {
  if (raw == null || raw === '') return []
  if (Array.isArray(raw)) {
    return raw
      .flatMap((item) => {
        if (item == null) return []
        if (typeof item === 'string') return [item]
        if (typeof item === 'object') {
          const o = item as Record<string, unknown>
          const cand = o.type ?? o.code ?? o.value ?? o.id
          return cand != null && cand !== '' ? [String(cand)] : []
        }
        return [String(item)]
      })
      .map((s) => s.trim())
      .filter(Boolean)
  }
  if (typeof raw === 'string') {
    const t = raw.trim()
    if (!t) return []
    if (t.startsWith('[') || t.startsWith('{')) {
      try {
        return normalizeApplicableStandards(JSON.parse(t))
      } catch { /* fall through */ }
    }
    return t.split(/[,，;；|/]/).map((s) => s.trim()).filter(Boolean)
  }
  if (typeof raw === 'object') {
    const o = raw as Record<string, unknown>
    if (Array.isArray(o.standards)) return normalizeApplicableStandards(o.standards)
    if (Array.isArray(o.list)) return normalizeApplicableStandards(o.list)
    const type = o.type ?? o.code ?? o.value
    return type != null && type !== '' ? [String(type)] : []
  }
  return []
}

export function useF2FormData(options: UseF2FormDataOptions) {
  const { wpId, projectId } = options

  const allResponses = ref<Map<string, ChecklistResponse>>(new Map())
  const isLoading = ref(false)
  const projectContext = ref<ProjectContext>({})
  const sheetCache = ref<Record<string, any>>({})

  const _debounceTimers = new Map<string, ReturnType<typeof setTimeout>>()
  const _pendingItems = new Set<string>()

  async function loadResponses(): Promise<void> {
    if (!wpId.value) return
    try {
      const res = await api.get(`/api/workpapers/${wpId.value}/checklist-responses`)
      const responses: any[] = Array.isArray(res) ? res : (res?.data ?? [])
      const map = new Map<string, ChecklistResponse>()
      for (const r of responses) {
        if (r.item_id && isF2ItemId(r.item_id)) {
          map.set(r.item_id, {
            item_id: r.item_id,
            conclusion: r.conclusion ?? null,
            remark: r.remark ?? null,
          })
        }
      }
      allResponses.value = map
    } catch {
      ElMessage.warning('F2数据加载失败，可手动填写')
    }
  }

  async function loadProjectContext(): Promise<void> {
    if (!projectId.value) return
    try {
      const data = await api.get(`/api/projects/${projectId.value}`)
      const ctx = data || {}
      const standards = normalizeApplicableStandards(
        ctx.applicable_standards
        ?? ctx.applicable_standard_v2
        ?? ctx.applicableStandards
        ?? ctx.applicable_standard,
      )
      projectContext.value = {
        ...ctx,
        business_category: ctx.business_category ?? undefined,
        applicable_standards: standards,
        entity_name: ctx.entity_name ?? ctx.client_name ?? undefined,
        audit_period_end: ctx.audit_period_end ?? undefined,
        bs_date: ctx.bs_date ?? undefined,
      }
    } catch {
      // 项目加载失败：跳过
    }
  }

  async function selfLoad(): Promise<void> {
    if (!wpId.value) return
    try {
      const res = await api.get(
        `/api/workpapers/${wpId.value}/render-config?force_component_type=f2-inventory-main`,
        { _silent: true } as any,
      )
      const data = res?.data ?? res
      const sheets = data?.sheets ?? data?.data?.sheets ?? []
      for (const s of sheets) {
        sheetCache.value[s.sheet_name || s.name || 'default'] = s.html_data ?? s
      }
    } catch {
      // selfLoad 失败不阻塞
    }
  }

  /**
   * 关键路径：checklist + 项目上下文（结构化底稿首屏必需）。
   * render-config / sheetCache 仅 Grid/OO 回退需要，不阻塞首屏。
   */
  async function loadCritical(): Promise<void> {
    isLoading.value = true
    try {
      await Promise.all([loadResponses(), loadProjectContext()])
    } finally {
      isLoading.value = false
    }
  }

  async function loadAll(): Promise<void> {
    isLoading.value = true
    try {
      await Promise.all([loadResponses(), loadProjectContext(), selfLoad()])
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
      ElMessage.warning(`科目 ${accountCode} 审定数回写失败，请手动确认试算表`)
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
    loadCritical,
    loadAll,
    selfLoad,
    getSheet,
    saveImmediate,
    saveBatch,
    saveItemsFromEvent,
    debouncedSave,
    writebackTrialBalance,
  }
}

export default useF2FormData
