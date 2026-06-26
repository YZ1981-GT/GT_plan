/**
 * useB22BFormData — B22B 内部控制缺陷评价表 数据加载/debounce保存/即时保存/B15重要性水平读取
 *
 * Spec: .kiro/specs/b22b-deficiency-evaluation/
 * Task: 2.1
 *
 * 职责：
 * - 从 GET /api/workpapers/:wpId/checklist-responses 加载已有数据（B22B- 前缀）
 * - 从 B15 checklist_responses 读取 B15-materiality-level 重要性水平金额
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

/** 单个 checklist response 数据 */
export type ChecklistResponse = ChecklistItem

// ─── Composable ──────────────────────────────────────────────────────────────

export function useB22BFormData(wpId: Ref<string>, projectId: Ref<string>) {
  const allResponses = ref<Map<string, ChecklistResponse>>(new Map())
  const loading = ref(false)
  const saving = ref(false)
  const materialityLevel = ref<number | null>(null)

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
        if (r.item_id?.startsWith('B22B-')) {
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

  // ─── Load Materiality Level from B15 ─────────────────────────────────────

  async function loadMaterialityLevel(): Promise<void> {
    if (!projectId.value) return
    try {
      // Find the B15 workpaper for this project and load its materiality level
      const res = await api.get(`/api/projects/${projectId.value}/workpapers`, {
        params: { wp_code: 'B15' },
      })
      const workpapers: any[] = Array.isArray(res) ? res : (res?.data ?? [])
      if (workpapers.length === 0) return

      const b15WpId = workpapers[0].id || workpapers[0].wp_id
      if (!b15WpId) return

      const b15Res = await api.get(`/api/workpapers/${b15WpId}/checklist-responses`)
      const b15Responses: any[] = Array.isArray(b15Res) ? b15Res : (b15Res?.data ?? [])

      for (const r of b15Responses) {
        if (r.item_id === 'B15-materiality-level' && r.remark) {
          const parsed = parseFloat(r.remark)
          if (!isNaN(parsed) && parsed > 0) {
            materialityLevel.value = parsed
            return
          }
        }
      }
    } catch {
      // B15 不可用时静默失败，允许手动输入
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

  /** 立即保存指定 items（选择字段变更、签字操作用） */
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
    materialityLevel,
    // 方法
    loadAll,
    loadMaterialityLevel,
    saveImmediate,
    saveDebouncedText,
    flushPendingSave,
    // Helper
    getField,
    setFieldImmediate,
  }
}

export default useB22BFormData
