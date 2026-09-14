/**
 * useB23FormData — B23 业务流程与控制了解表 数据加载/debounce保存/即时保存/流程数据视图
 *
 * Spec: .kiro/specs/b23-process-control/
 * Task: 2.1
 *
 * 职责：
 * - 从 GET /api/workpapers/:wpId/checklist-responses 加载已有数据（B23- 前缀）
 * - debounce 2s 文本字段保存 / 选择字段变更立即保存
 * - 组件卸载时 flush 未保存数据（onScopeDispose）
 * - 保存 via PUT /api/workpapers/:wpId/checklist-responses
 * - processData(num) 按流程编号过滤数据视图
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

/** 流程编号 */
export type ProcessNumber = 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8

/** 流程数据视图（按 B23-P{n}- 前缀过滤） */
export interface ProcessDataView {
  items: Map<string, ChecklistResponse>
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useB23FormData(wpId: Ref<string>) {
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
        if (r.item_id?.startsWith('B23-')) {
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

  // ─── Save ────────────────────────────────────────────────────────────────

  async function doSave(items: ChecklistItem[]): Promise<void> {
    if (!wpId.value || items.length === 0) return
    saving.value = true
    try {
      // 注：不传 project_id（wpId≠projectId，误传 wp_id 作 project_id 会致后端项目查找 404）；
      // 后端从 wp_id 反查 project_id。
      await api.put(`/api/workpapers/${wpId.value}/checklist-responses`, {
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

  /** 立即保存指定 items（Process_Conclusion/穿行结论/适用性开关触发） */
  async function saveImmediate(items: ChecklistItem[]): Promise<void> {
    if (saveTimer) {
      clearTimeout(saveTimer)
      saveTimer = null
    }
    pendingSave = false
    await doSave(items)
  }

  /** debounce 2000ms 文本字段保存（控制目标/描述/备注/穿行记录字段） */
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

  // ─── 流程数据视图 ────────────────────────────────────────────────────────

  /** 按流程编号过滤数据视图（B23-P{num}- 前缀） */
  function processData(processNum: ProcessNumber): ComputedRef<ProcessDataView> {
    return computed(() => {
      const prefix = `B23-P${processNum}-`
      const items = new Map<string, ChecklistResponse>()
      for (const [key, val] of allResponses.value) {
        if (key.startsWith(prefix)) {
          items.set(key, val)
        }
      }
      return { items }
    })
  }

  // ─── Helper 方法 ─────────────────────────────────────────────────────────

  /** 获取单个字段 */
  function getField(itemId: string): ChecklistResponse {
    return allResponses.value.get(itemId) || { item_id: itemId, conclusion: null, remark: null, wp_ref: null }
  }

  /** 设置字段 + 立即保存（选择变更、签字操作） */
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
    saveImmediate,
    saveDebouncedText,
    flushPendingSave,
    // 流程数据视图
    processData,
    // Helper
    getField,
    setFieldImmediate,
  }
}

export default useB23FormData
