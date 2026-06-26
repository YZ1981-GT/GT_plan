/**
 * useB22AFormData — B22A 内部控制了解程序表 数据加载/debounce保存/即时保存/tab数据视图/续审加载
 *
 * Spec: .kiro/specs/b22a-control-matrix/
 * Task: 2.1
 *
 * 职责：
 * - 从 GET /api/workpapers/:wpId/checklist-responses 加载已有数据（B22A- 前缀）
 * - debounce 2s 文本字段保存 / Conclusion/Element_Score 变更立即保存
 * - 组件卸载时 flush 未保存数据（onScopeDispose）
 * - 保存 via PUT /api/workpapers/:wpId/checklist-responses
 * - 按 item_id 前缀分发到 6 个 tab 计算属性
 * - 续审加载：从上年 wp_id 加载历史 B22A-* 数据作为初始值
 */
import { ref, computed, onScopeDispose, type Ref, type ComputedRef } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface ChecklistItem {
  item_id: string
  conclusion: string | null
  remark: string | null
  wp_ref: string | null
}

/** 单个 checklist response 数据 */
export type ChecklistResponse = ChecklistItem

/** Tab 数据视图（通用） */
export interface TabState {
  items: Map<string, ChecklistResponse>
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useB22AFormData(wpId: Ref<string>) {
  const allResponses = ref<Map<string, ChecklistResponse>>(new Map())
  const loading = ref(false)
  const saving = ref(false)

  let saveTimer: ReturnType<typeof setTimeout> | null = null
  let pendingSave = false

  // ─── Load ────────────────────────────────────────────────────────────────

  async function loadAll(): Promise<void> {
    if (!wpId.value) return
    loading.value = true
    try {
      const res = await api.get(`/api/workpapers/${wpId.value}/checklist-responses`)
      const responses: any[] = Array.isArray(res) ? res : (res?.data ?? [])
      const map = new Map<string, ChecklistResponse>()
      for (const r of responses) {
        if (r.item_id?.startsWith('B22A-')) {
          map.set(r.item_id, {
            item_id: r.item_id,
            conclusion: r.conclusion ?? null,
            remark: r.remark ?? null,
            wp_ref: r.wp_ref ?? null,
          })
        }
      }
      allResponses.value = map
    } catch {
      ElMessage.warning('数据加载失败，可手动填写')
    } finally {
      loading.value = false
    }
  }

  // ─── Prior Year Load ─────────────────────────────────────────────────────

  async function loadPriorYear(priorWpId: string): Promise<void> {
    if (!priorWpId) return
    try {
      const res = await api.get(`/api/workpapers/${priorWpId}/checklist-responses`)
      const responses: any[] = Array.isArray(res) ? res : (res?.data ?? [])
      for (const r of responses) {
        if (r.item_id?.startsWith('B22A-')) {
          // Only fill empty items — do not overwrite existing edits
          if (!allResponses.value.has(r.item_id)) {
            allResponses.value.set(r.item_id, {
              item_id: r.item_id,
              conclusion: r.conclusion ?? null,
              remark: r.remark ?? null,
              wp_ref: r.wp_ref ?? null,
            })
          }
        }
      }
    } catch {
      ElMessage.warning('上年数据加载失败，不影响当前底稿使用')
    }
  }

  // ─── Save ────────────────────────────────────────────────────────────────

  async function doSave(items: ChecklistItem[]): Promise<void> {
    if (!wpId.value || items.length === 0) return
    saving.value = true
    try {
      await api.put(`/api/workpapers/${wpId.value}/checklist-responses`, {
        project_id: wpId.value,
        items: items.map((item) => ({
          item_id: item.item_id,
          conclusion: item.conclusion || null,
          remark: item.remark || null,
          wp_ref: item.wp_ref || null,
        })),
      })
    } catch (err: any) {
      const msg = err?.message || ''
      if (msg !== 'canceled' && err?.code !== 'ERR_CANCELED') {
        ElMessage.error('保存失败')
      }
    } finally {
      saving.value = false
    }
  }

  /** 立即保存指定 items（Conclusion/Element_Score 变更、签字操作用） */
  async function saveImmediate(items: ChecklistItem[]): Promise<void> {
    if (saveTimer) {
      clearTimeout(saveTimer)
      saveTimer = null
    }
    pendingSave = false
    await doSave(items)
  }

  /** debounce 2000ms 文本字段保存 */
  function saveDebouncedText(item: ChecklistItem): void {
    allResponses.value.set(item.item_id, { ...item })
    pendingSave = true

    if (saveTimer) clearTimeout(saveTimer)
    saveTimer = setTimeout(() => {
      saveTimer = null
      pendingSave = false
      const items = Array.from(allResponses.value.values())
      doSave(items)
    }, 2000)
  }

  /** flush 未保存数据（组件卸载时调用） */
  function flushPendingSave(): void {
    if (saveTimer) {
      clearTimeout(saveTimer)
      saveTimer = null
    }
    if (pendingSave) {
      pendingSave = false
      const items = Array.from(allResponses.value.values())
      doSave(items)
    }
  }

  // ─── Tab 数据视图 ────────────────────────────────────────────────────────

  const tab1Data: ComputedRef<TabState> = computed(() => {
    const items = new Map<string, ChecklistResponse>()
    for (const [key, val] of allResponses.value) {
      if (key.startsWith('B22A-T1-')) {
        items.set(key, val)
      }
    }
    return { items }
  })

  const tab2Data: ComputedRef<TabState> = computed(() => {
    const items = new Map<string, ChecklistResponse>()
    for (const [key, val] of allResponses.value) {
      if (key.startsWith('B22A-T2-')) {
        items.set(key, val)
      }
    }
    return { items }
  })

  const tab3Data: ComputedRef<TabState> = computed(() => {
    const items = new Map<string, ChecklistResponse>()
    for (const [key, val] of allResponses.value) {
      if (key.startsWith('B22A-T3-')) {
        items.set(key, val)
      }
    }
    return { items }
  })

  const tab4Data: ComputedRef<TabState> = computed(() => {
    const items = new Map<string, ChecklistResponse>()
    for (const [key, val] of allResponses.value) {
      if (key.startsWith('B22A-T4-')) {
        items.set(key, val)
      }
    }
    return { items }
  })

  const tab5Data: ComputedRef<TabState> = computed(() => {
    const items = new Map<string, ChecklistResponse>()
    for (const [key, val] of allResponses.value) {
      if (key.startsWith('B22A-T5-')) {
        items.set(key, val)
      }
    }
    return { items }
  })

  const summaryData: ComputedRef<TabState> = computed(() => {
    const items = new Map<string, ChecklistResponse>()
    for (const [key, val] of allResponses.value) {
      if (
        key.startsWith('B22A-SUM-') ||
        key.startsWith('B22A-review-') ||
        key.startsWith('B22A-amend-')
      ) {
        items.set(key, val)
      }
    }
    return { items }
  })

  // ─── Helper 方法 ─────────────────────────────────────────────────────────

  /** 获取单个字段 */
  function getField(itemId: string): ChecklistResponse {
    return allResponses.value.get(itemId) || { item_id: itemId, conclusion: null, remark: null, wp_ref: null }
  }

  /** 设置字段 + 立即保存（Conclusion/Element_Score 变更、签字操作） */
  function setFieldImmediate(itemId: string, data: Partial<Omit<ChecklistResponse, 'item_id'>>): void {
    const existing = allResponses.value.get(itemId) || { item_id: itemId, conclusion: null, remark: null, wp_ref: null }
    const updated: ChecklistResponse = {
      ...existing,
      ...(data.conclusion !== undefined ? { conclusion: data.conclusion } : {}),
      ...(data.remark !== undefined ? { remark: data.remark } : {}),
      ...(data.wp_ref !== undefined ? { wp_ref: data.wp_ref } : {}),
    }
    allResponses.value.set(itemId, updated)
    saveImmediate([updated])
  }

  // ─── Lifecycle ───────────────────────────────────────────────────────────

  onScopeDispose(() => {
    flushPendingSave()
  })

  return {
    // 响应式数据
    allResponses,
    loading,
    saving,
    // 方法
    loadAll,
    loadPriorYear,
    saveImmediate,
    saveDebouncedText,
    flushPendingSave,
    // Tab 数据视图
    tab1Data,
    tab2Data,
    tab3Data,
    tab4Data,
    tab5Data,
    summaryData,
    // Helper
    getField,
    setFieldImmediate,
  }
}

export default useB22AFormData
