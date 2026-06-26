/**
 * useCControlTestData — C 类控制测试数据加载/debounce保存/即时保存
 *
 * Spec: .kiro/specs/c-control-test-component/
 * Task: 2.1
 *
 * 职责：
 * - 从 GET /api/workpapers/:wpId/checklist-responses 加载 C{n}-* 数据
 * - debounce 2s 文本字段保存 / 选择字段变更立即保存
 * - 组件卸载时 flush 未保存数据（onScopeDispose）
 * - 保存 via PUT /api/workpapers/:wpId/checklist-responses
 */
import { ref, onScopeDispose, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface ChecklistItem {
  item_id: string
  conclusion: string | null
  remark: string | null
  wp_ref: string | null
}

export type ChecklistResponse = ChecklistItem

// ─── Composable ──────────────────────────────────────────────────────────────

export function useCControlTestData(wpId: Ref<string>, cycleNum: Ref<number>) {
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
      const prefix = `C${cycleNum.value}-`
      for (const r of responses) {
        if (r.item_id?.startsWith(prefix)) {
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

  /** 立即保存指定 items（Test_Method/Sample_Result/结论触发） */
  async function saveImmediate(items: ChecklistItem[]): Promise<void> {
    if (saveTimer) {
      clearTimeout(saveTimer)
      saveTimer = null
    }
    pendingSave = false
    await doSave(items)
  }

  /** debounce 2000ms 文本字段保存（偏差描述/凭证号/金额等字段） */
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
    allResponses,
    loading,
    saving,
    loadAll,
    saveImmediate,
    saveDebouncedText,
    flushPendingSave,
    getField,
    setFieldImmediate,
  }
}

export default useCControlTestData
