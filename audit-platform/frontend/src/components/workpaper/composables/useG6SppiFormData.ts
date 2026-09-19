/**
 * useG6SppiFormData — G6 其他债权投资(SPPI组) 数据加载/保存/selfLoad
 *
 * Spec: .kiro/specs/g6-other-bond-investment-sppi/
 * Task: 1.8
 *
 * 职责：
 * - selfLoad逻辑（render-config?force_component_type=g6-other-bond-investment-sppi）
 * - 从 GET /api/workpapers/:wpId/checklist-responses 加载 G6-sppi 数据
 * - debounce 2000ms 文本字段保存（per item_id 独立计时器）
 * - 结论/状态/选择类字段立即保存（saveImmediate）
 * - 批量保存（saveBatch）
 * - 保存完整 content JSON（saveContent）
 * - 组件卸载时 flush 未保存数据（onScopeDispose）
 *
 * Requirements: 1.4, 3.3, 7.3
 */
import { ref, onScopeDispose, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'

// ─── G6SppiContent 顶层数据接口 ──────────────────────────────────────────────

export interface G6SppiContent {
  fairValue: Record<string, any>
  interest: Record<string, any>
  businessModel: Record<string, any>
  sppiTest: Record<string, any>
  inventory: Record<string, any>
  reconciliation: Record<string, any>
}

// ─── ChecklistResponse 类型 ─────────────────────────────────────────────────

export interface ChecklistResponse {
  item_id: string
  conclusion: string | null
  remark: string | null
}

// ─── Options ─────────────────────────────────────────────────────────────────

export interface UseG6SppiFormDataOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  onAfterSave?: () => void
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useG6SppiFormData(opts: UseG6SppiFormDataOptions) {
  const { wpId, projectId } = opts

  const allResponses = ref<Map<string, ChecklistResponse>>(new Map())
  const isLoading = ref(false)
  const loadError = ref<string | null>(null)
  const sheetCache = ref<Record<string, any>>({})

  // Per-item debounce timers
  const _debounceTimers = new Map<string, ReturnType<typeof setTimeout>>()
  const _pendingItems = new Set<string>()

  /** item_id前缀：筛选G6 SPPI相关数据 */
  const ITEM_PREFIXES = ['G6-5-', 'G6-6-', 'G6-7-', 'G6-8-', 'G6-9-', 'G6-10-', 'G6-sppi-']

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
      ElMessage.warning('G6(SPPI)数据加载失败，可手动填写')
    }
  }

  /**
   * selfLoad: 当组件在bundle内嵌场景 htmlData 为 null 时，
   * 自行调用 render-config?force_component_type=g6-other-bond-investment-sppi 获取渲染数据
   */
  async function selfLoad(): Promise<void> {
    if (!wpId.value) return
    try {
      const { data } = await http.get(`/api/workpapers/${wpId.value}/render-config`, {
        params: { force_component_type: 'g6-other-bond-investment-sppi' },
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
   * 从sheetCache中解析出完整的G6SppiContent结构
   * 用于从render-config返回的html_data中提取各section数据
   */
  function parseContent(): Partial<G6SppiContent> {
    const result: Partial<G6SppiContent> = {}

    for (const [key, value] of Object.entries(sheetCache.value)) {
      if (!value) continue
      const content = value?.content ?? value

      if (key.includes('G6-5') || key.includes('公允价值')) {
        result.fairValue = content
      } else if (key.includes('G6-6') || key.includes('利息')) {
        result.interest = content
      } else if (key.includes('G6-7') || key.includes('业务模式')) {
        result.businessModel = content
      } else if (key.includes('G6-8') || key.includes('SPPI') || key.includes('现金流量')) {
        result.sppiTest = content
      } else if (key.includes('G6-10') || key.includes('倒轧')) {
        // 须先于「盘点」判断：「盘点倒轧表G6-10」同时含「盘点」与「倒轧」
        result.reconciliation = content
      } else if (key.includes('G6-9') || key.includes('盘点')) {
        result.inventory = content
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
    // 🔴 同一批次不得重复提交相同 item_id：后端会**整批拒绝** → 该批全部数据丢失
    //    （联动回写常见：先写整表 JSON、再写其中某个汇总字段）。
    //    同 itemId 多次传入时后写覆盖先写，与「用户最后一次输入」语义一致。
    const deduped = [...new Map(items.map((it) => [it.itemId, it])).values()]
    const toSave: ChecklistResponse[] = []
    for (const { itemId, data } of deduped) {
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
   * 多键原子防抖保存：同一计时器批量 PUT，避免 G6-6-interest-data / G6-6-rows 半成功
   */
  function debouncedSaveBatch(items: Array<{ itemId: string; data: Partial<ChecklistResponse> }>): void {
    if (!items.length) return
    const batchIds = items.map((it) => it.itemId)
    const batchKey = `__batch__:${batchIds.sort().join('|')}`

    for (const { itemId, data } of items) {
      const existing = allResponses.value.get(itemId) || { item_id: itemId, conclusion: null, remark: null }
      const updated: ChecklistResponse = {
        ...existing,
        ...(data.conclusion !== undefined ? { conclusion: data.conclusion } : {}),
        ...(data.remark !== undefined ? { remark: data.remark } : {}),
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
      const toSave: ChecklistResponse[] = []
      for (const itemId of batchIds) {
        _debounceTimers.delete(itemId)
        _pendingItems.delete(itemId)
        const resp = allResponses.value.get(itemId)
        if (resp) toSave.push(resp)
      }
      void _doSave(toSave)
    }, 2000)
    _debounceTimers.set(batchKey, timer)
    for (const itemId of batchIds) {
      _debounceTimers.set(itemId, timer)
    }
  }

  /**
   * 保存完整 content JSON（POST到workpaper content端点）
   * 用于保存G6 SPPI组所有sheet的完整结构化数据
   */
  async function saveContent(content: Partial<G6SppiContent>): Promise<void> {
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
    debouncedSaveBatch,
    saveContent,
    flushPending: _flushPending,
  }
}

export default useG6SppiFormData
