/**
 * useWordTemplateStructured — Word 模板结构化视图 composable
 *
 * Spec: .kiro/specs/word-template-dual-mode/
 * Task: 4.1
 *
 * 职责：
 * - 从 render-config 加载模板结构 (template_structure)
 * - 字段读写 (fieldValues reactive map)
 * - 2s debounce save → PUT /api/workpapers/{wpId}/checklist-responses
 * - flush pending saves
 * - export docx (prefilled-download with include_responses=true)
 * - AI fill stub (disabled)
 */
import { ref, computed, type Ref, type ComputedRef } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface PlaceholderDef {
  field_id: string
  label: string
  data_type: string // "text" | "date" | "textarea" | "number"
  default_value: string
  position: Record<string, number>
  pattern: string
  current_value: string
}

export interface ParagraphDef {
  index: number
  text: string
  style: string
  heading_level: number
  placeholder_ids: string[]
}

export interface TableDef {
  index: number
  rows: string[][]
  placeholder_ids: string[]
}

export interface TemplateStructure {
  placeholders: PlaceholderDef[]
  paragraphs: ParagraphDef[]
  tables: TableDef[]
  metadata: {
    template_name: string
    wp_code: string
    last_parsed_at: string
  }
}

export interface UseWordTemplateStructuredOptions {
  wpId: Ref<string>
  wpCode: Ref<string>
  projectId: Ref<string>
}

export interface UseWordTemplateStructuredReturn {
  templateStructure: Ref<TemplateStructure | null>
  fieldValues: Ref<Record<string, string>>
  loading: Ref<boolean>
  saveStatus: Ref<'saved' | 'saving' | 'unsaved'>
  hasPlaceholders: ComputedRef<boolean>
  // Methods
  loadStructure(): Promise<void>
  updateField(fieldId: string, value: string): void
  flushPendingSaves(): Promise<void>
  exportDocx(): Promise<void>
  exportTemplate(): Promise<void>
  triggerAiFill(fieldId: string): Promise<void>
}

// ─── Helper ──────────────────────────────────────────────────────────────────

/** Build item_id for word-template structured fields */
export function buildWtItemId(wpCode: string, fieldId: string): string {
  return `wt-${wpCode}-${fieldId}`
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useWordTemplateStructured(
  opts: UseWordTemplateStructuredOptions,
): UseWordTemplateStructuredReturn {
  const { wpId, wpCode, projectId } = opts

  const templateStructure = ref<TemplateStructure | null>(null)
  const fieldValues = ref<Record<string, string>>({})
  const loading = ref(false)
  const saveStatus = ref<'saved' | 'saving' | 'unsaved'>('saved')

  const hasPlaceholders = computed(() => {
    return (templateStructure.value?.placeholders?.length ?? 0) > 0
  })

  // ─── Pending saves ───
  const pendingItems = new Map<string, { item_id: string; conclusion: string | null; remark: string | null }>()
  let saveTimer: ReturnType<typeof setTimeout> | null = null

  // ─── Load Structure ───
  async function loadStructure(): Promise<void> {
    loading.value = true
    try {
      const res = await api.get<any>(
        `/api/workpapers/${wpId.value}/render-config?force_component_type=word-template`,
        { _silent: true } as any,
      )
      // render-config 返回 {sheets: [{html_data: {template_structure, filled_responses}}]}
      const htmlData = res?.sheets?.[0]?.html_data
      if (htmlData?.template_structure) {
        templateStructure.value = htmlData.template_structure as TemplateStructure
        // Hydrate fieldValues from filled_responses or placeholder current_values
        const values: Record<string, string> = {}
        if (htmlData.filled_responses && typeof htmlData.filled_responses === 'object') {
          Object.assign(values, htmlData.filled_responses)
        }
        // Also pick up current_value from placeholders for any not in filled_responses
        if (templateStructure.value?.placeholders) {
          for (const p of templateStructure.value.placeholders) {
            if (p.current_value && !values[p.field_id]) {
              values[p.field_id] = p.current_value
            }
          }
        }
        fieldValues.value = values
      } else {
        templateStructure.value = null
        fieldValues.value = {}
      }
    } catch {
      templateStructure.value = null
      fieldValues.value = {}
    } finally {
      loading.value = false
    }
  }

  // ─── Update Field ───
  function updateField(fieldId: string, value: string): void {
    fieldValues.value[fieldId] = value
    const itemId = buildWtItemId(wpCode.value, fieldId)
    // Determine if short text (conclusion) or long text (remark) based on placeholder data_type
    const placeholder = templateStructure.value?.placeholders?.find(p => p.field_id === fieldId)
    const isLongText = placeholder?.data_type === 'textarea'
    pendingItems.set(itemId, {
      item_id: itemId,
      conclusion: isLongText ? null : (value || null),
      remark: isLongText ? (value || null) : null,
    })
    scheduleSave()
  }

  // ─── Debounce Save ───
  function scheduleSave(): void {
    saveStatus.value = 'unsaved'
    if (saveTimer) clearTimeout(saveTimer)
    saveTimer = setTimeout(() => { saveTimer = null; doSave() }, 2000)
  }

  async function doSave(retryCount = 0): Promise<void> {
    if (pendingItems.size === 0) return
    const items = [...pendingItems.values()]
    pendingItems.clear()
    saveStatus.value = 'saving'

    try {
      await api.put(`/api/workpapers/${wpId.value}/checklist-responses`, { items })
      saveStatus.value = 'saved'
    } catch {
      if (retryCount < 3) {
        for (const item of items) pendingItems.set(item.item_id, item)
        setTimeout(() => doSave(retryCount + 1), 1000 * (retryCount + 1))
        return
      }
      saveStatus.value = 'unsaved'
      ElMessage.warning('保存失败，请检查网络后重试')
    }
  }

  // ─── Flush ───
  async function flushPendingSaves(): Promise<void> {
    if (saveTimer) {
      clearTimeout(saveTimer)
      saveTimer = null
    }
    await doSave()
  }

  // ─── Export Docx (with responses merged) ───
  async function exportDocx(): Promise<void> {
    await flushPendingSaves()
    try {
      const url = `/api/projects/${projectId.value}/wp-templates/${wpCode.value}/prefilled-download?include_responses=true`
      const token = sessionStorage.getItem('token') || localStorage.getItem('token') || ''
      const r = await fetch(url, { headers: { Authorization: `Bearer ${token}` } })
      if (!r.ok) throw new Error('导出失败')
      const blob = await r.blob()
      const obj = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = obj
      a.download = `${wpCode.value}_完成稿.docx`
      a.click()
      URL.revokeObjectURL(obj)
    } catch {
      ElMessage.error('导出失败，请重试')
    }
  }

  // ─── Export Template (with guidance) ───
  async function exportTemplate(): Promise<void> {
    try {
      const url = `/api/projects/${projectId.value}/wp-templates/${wpCode.value}/prefilled-download?include_guidance=true`
      const token = sessionStorage.getItem('token') || localStorage.getItem('token') || ''
      const r = await fetch(url, { headers: { Authorization: `Bearer ${token}` } })
      if (!r.ok) throw new Error('导出模板失败')
      const blob = await r.blob()
      const obj = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = obj
      a.download = `${wpCode.value}_模板_带说明.docx`
      a.click()
      URL.revokeObjectURL(obj)
    } catch {
      ElMessage.error('导出模板失败，请重试')
    }
  }

  // ─── AI Fill Stub ───
  async function triggerAiFill(_fieldId: string): Promise<void> {
    ElMessage.info('AI 填充功能即将上线')
  }

  return {
    templateStructure,
    fieldValues,
    loading,
    saveStatus,
    hasPlaceholders,
    loadStructure,
    updateField,
    flushPendingSaves,
    exportDocx,
    exportTemplate,
    triggerAiFill,
  }
}
