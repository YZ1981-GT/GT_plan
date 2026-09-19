/**
 * useA111FormData — A1-11 签发流转控制表 数据加载/自动填充/debounce保存
 *
 * Spec: .kiro/specs/a1-11-signing-control-form/
 * Task: 2.1
 *
 * 职责：
 * - 从 GET /api/workpapers/:wpId/checklist-responses 加载已有数据（A1-11- 前缀）
 * - 从 GET /api/projects/:pid 获取 project context 用于自动填充
 * - 自动填充映射（仅无已有记录时填充）
 * - debounce 2s 文本字段保存 / 签字立即保存
 * - 组件卸载时 flush 未保存数据
 * - 保存 via PUT /api/workpapers/:wpId/checklist-responses
 */
import { ref, onMounted, onBeforeUnmount, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface ChecklistResponseItem {
  item_id: string
  conclusion: string | null
  remark: string | null
  wp_ref: string | null
}

export interface ProjectContext {
  entity_name?: string
  entity_type?: string
  industry?: string
  engagement_letter_no?: string
  business_category?: string
  audit_period_end?: string
  [key: string]: any
}

export interface A111FormState {
  /** 所有 A1-11- 前缀字段的响应式 map：item_id → { conclusion, remark, wp_ref } */
  [itemId: string]: ChecklistResponseItem
}

// ─── Auto-fill 映射 ──────────────────────────────────────────────────────────

const AUTO_FILL_MAP: Record<string, (p: ProjectContext) => { conclusion?: string | null; remark?: string | null; wp_ref?: string | null }> = {
  'A1-11-entity-name': (p) => ({ remark: p.entity_name || null }),
  'A1-11-entity-type': (p) => ({ remark: p.entity_type || null }),
  'A1-11-industry': (p) => ({ remark: p.industry || null }),
  'A1-11-engagement-no': (p) => ({ remark: p.engagement_letter_no || null }),
  'A1-11-biz-category': (p) => ({ conclusion: p.business_category || null }),
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useA111FormData(wpId: Ref<string>, projectId: Ref<string>) {
  const formData = ref<Record<string, ChecklistResponseItem>>({})
  const loading = ref(false)
  const error = ref<string | null>(null)
  const projectContext = ref<ProjectContext>({})

  /** 已从后端加载到的 item_id 集合（用于判断自动填充） */
  const existingItemIds = new Set<string>()

  let saveTimer: ReturnType<typeof setTimeout> | null = null
  let pendingSave = false

  // ─── Load ────────────────────────────────────────────────────────────────

  async function loadResponses(): Promise<void> {
    if (!wpId.value) return
    try {
      const res = await api.get(`/api/workpapers/${wpId.value}/checklist-responses`)
      const responses: any[] = Array.isArray(res) ? res : (res?.data ?? [])
      for (const r of responses) {
        if (r.item_id?.startsWith('A1-11-')) {
          existingItemIds.add(r.item_id)
          formData.value[r.item_id] = {
            item_id: r.item_id,
            conclusion: r.conclusion ?? null,
            remark: r.remark ?? null,
            wp_ref: r.wp_ref ?? null,
          }
        }
      }
    } catch {
      // 加载失败：表单保持空白可编辑
      ElMessage.warning('加载表单数据失败，可手动填写')
    }
  }

  async function loadProjectContext(): Promise<void> {
    if (!projectId.value) return
    try {
      const data = await api.get(`/api/projects/${projectId.value}`)
      projectContext.value = data || {}
    } catch {
      // 项目加载失败：跳过自动填充
    }
  }

  /** 自动填充：仅在 checklist_responses 中无对应记录时填充 */
  function applyAutoFill(): void {
    const ctx = projectContext.value
    if (!ctx || Object.keys(ctx).length === 0) return

    for (const [itemId, extractor] of Object.entries(AUTO_FILL_MAP)) {
      // 仅无已有记录时填充
      if (existingItemIds.has(itemId)) continue

      const fillValues = extractor(ctx)
      // 如果提取的值全为空，不填充
      if (!fillValues.conclusion && !fillValues.remark && !fillValues.wp_ref) continue

      formData.value[itemId] = {
        item_id: itemId,
        conclusion: fillValues.conclusion ?? null,
        remark: fillValues.remark ?? null,
        wp_ref: fillValues.wp_ref ?? null,
      }
    }
  }

  async function loadAll(): Promise<void> {
    loading.value = true
    error.value = null
    try {
      await Promise.all([loadResponses(), loadProjectContext()])
      applyAutoFill()
    } catch (e: any) {
      error.value = e?.message || '数据加载失败'
    } finally {
      loading.value = false
    }
  }

  // ─── Save ────────────────────────────────────────────────────────────────

  async function doSave(): Promise<void> {
    if (!wpId.value || !projectId.value) return
    pendingSave = false

    const items: ChecklistResponseItem[] = Object.values(formData.value).map((item) => ({
      item_id: item.item_id,
      conclusion: item.conclusion || null,
      remark: item.remark || null,
      wp_ref: item.wp_ref || null,
    }))

    if (items.length === 0) return

    try {
      await api.put(`/api/workpapers/${wpId.value}/checklist-responses`, {
        project_id: projectId.value,
        items,
      })
      error.value = null
    } catch (err: any) {
      const msg = err?.message || ''
      if (msg !== 'canceled' && err?.code !== 'ERR_CANCELED') {
        error.value = '保存失败'
        ElMessage.error('保存失败')
      }
    }
  }

  /** debounce 2s 文本字段保存 */
  function scheduleSave(): void {
    pendingSave = true
    if (saveTimer) clearTimeout(saveTimer)
    saveTimer = setTimeout(() => {
      saveTimer = null
      doSave()
    }, 2000)
  }

  /** 立即保存（签字操作用） */
  async function saveImmediate(): Promise<void> {
    if (saveTimer) {
      clearTimeout(saveTimer)
      saveTimer = null
    }
    pendingSave = false
    await doSave()
  }

  /** flush 未保存数据（组件卸载时调用） */
  function flushPendingSave(): void {
    if (saveTimer) {
      clearTimeout(saveTimer)
      saveTimer = null
    }
    if (pendingSave) {
      doSave()
    }
  }

  // ─── Field 更新方法 ──────────────────────────────────────────────────────

  /** 更新某字段的值（触发 debounce 保存） */
  function updateField(itemId: string, field: 'conclusion' | 'remark' | 'wp_ref', value: string | null): void {
    if (!formData.value[itemId]) {
      formData.value[itemId] = { item_id: itemId, conclusion: null, remark: null, wp_ref: null }
    }
    formData.value[itemId][field] = value
    scheduleSave()
  }

  /** 批量设置某字段全部值（签字操作，立即保存） */
  function setFieldImmediate(itemId: string, values: Partial<Omit<ChecklistResponseItem, 'item_id'>>): void {
    if (!formData.value[itemId]) {
      formData.value[itemId] = { item_id: itemId, conclusion: null, remark: null, wp_ref: null }
    }
    if (values.conclusion !== undefined) formData.value[itemId].conclusion = values.conclusion
    if (values.remark !== undefined) formData.value[itemId].remark = values.remark
    if (values.wp_ref !== undefined) formData.value[itemId].wp_ref = values.wp_ref
    saveImmediate()
  }

  /** 获取某字段值 */
  function getField(itemId: string): ChecklistResponseItem {
    return formData.value[itemId] || { item_id: itemId, conclusion: null, remark: null, wp_ref: null }
  }

  // ─── Lifecycle ───────────────────────────────────────────────────────────

  onMounted(() => {
    loadAll()
  })

  onBeforeUnmount(() => {
    flushPendingSave()
  })

  return {
    formData,
    loading,
    error,
    projectContext,
    loadAll,
    updateField,
    setFieldImmediate,
    getField,
    scheduleSave,
    saveImmediate,
    flushPendingSave,
    doSave,
  }
}

export default useA111FormData
