/**
 * createCycleFormData — 参数化工厂：循环底稿表单数据 composable
 *
 * Feature: platform-global-hardening
 * Requirements: 6.5, 6.6
 *
 * 用于收敛 useD2FormData / useE1FormData / useF1FormData 等同构实现。
 * 每个循环底稿的 FormData composable 结构相同：
 *   - 从 checklist-responses 加载数据（按 item_id 前缀过滤）
 *   - debounce 保存 / 即时保存
 *   - 组件卸载时 flush
 *   - isDirty 追踪
 */
import { ref, computed, onScopeDispose, type Ref, type ComputedRef } from 'vue'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface CycleFormDataConfig<T extends Record<string, unknown> = Record<string, unknown>> {
  /** 底稿 wp_id */
  wpId: Ref<string>
  /** 项目 id（可选，用于取数联动） */
  projectId?: Ref<string>
  /** item_id 前缀过滤（如 'D2-', 'F1-', 'K8-'） */
  prefix: string
  /** 默认字段值映射（用于 resetData） */
  defaultValues?: T
  /** 自定义校验函数 */
  validateFn?: (data: Map<string, FormDataItem>) => string[]
  /** debounce 延迟毫秒数，默认 2000 */
  debounceMs?: number
  /** 自定义 API 基路径，默认 /api/workpapers/{wpId}/checklist-responses */
  apiBaseFn?: (wpId: string) => string
}

export interface FormDataItem {
  item_id: string
  conclusion: string | null
  remark: string | null
}

export interface CycleFormDataReturn {
  /** 全部响应 Map */
  formData: Ref<Map<string, FormDataItem>>
  /** 加载中标记 */
  loading: Ref<boolean>
  /** 保存中标记 */
  saving: Ref<boolean>
  /** 是否有未保存的更改 */
  isDirty: Ref<boolean>
  /** 校验错误列表 */
  errors: ComputedRef<string[]>
  /** 从后端加载数据 */
  loadData: () => Promise<void>
  /** 立即保存当前数据 */
  saveData: () => Promise<void>
  /** 重置为默认值 */
  resetData: () => void
  /** 设置单个字段（自动 debounce） */
  setField: (itemId: string, field: 'conclusion' | 'remark', value: string | null) => void
  /** 设置单个字段并立即保存 */
  setFieldImmediate: (itemId: string, field: 'conclusion' | 'remark', value: string | null) => void
  /** flush 所有待保存数据 */
  flush: () => Promise<void>
}

// ─── Factory ─────────────────────────────────────────────────────────────────

export function createCycleFormData<T extends Record<string, unknown> = Record<string, unknown>>(
  config: CycleFormDataConfig<T>,
): CycleFormDataReturn {
  const {
    wpId,
    prefix,
    defaultValues,
    validateFn,
    debounceMs = 2000,
    apiBaseFn,
  } = config

  const formData = ref<Map<string, FormDataItem>>(new Map()) as Ref<Map<string, FormDataItem>>
  const loading = ref(false)
  const saving = ref(false)
  const isDirty = ref(false)

  let saveTimer: ReturnType<typeof setTimeout> | null = null

  const errors = computed<string[]>(() => {
    if (!validateFn) return []
    return validateFn(formData.value)
  })

  function getApiBase(): string {
    if (apiBaseFn) return apiBaseFn(wpId.value)
    return `/api/workpapers/${wpId.value}/checklist-responses`
  }

  async function loadData(): Promise<void> {
    if (!wpId.value) return
    loading.value = true
    try {
      const response = await fetch(getApiBase(), {
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
      })
      if (!response.ok) throw new Error(`Load failed: ${response.status}`)
      const json = await response.json()
      const responses: any[] = Array.isArray(json) ? json : (json?.data ?? [])

      const map = new Map<string, FormDataItem>()
      for (const r of responses) {
        if (r.item_id?.startsWith(prefix)) {
          map.set(r.item_id, {
            item_id: r.item_id,
            conclusion: r.conclusion ?? null,
            remark: r.remark ?? null,
          })
        }
      }
      formData.value = map
      isDirty.value = false
    } catch {
      // fail-open: 不阻塞 UI
    } finally {
      loading.value = false
    }
  }

  async function saveData(): Promise<void> {
    if (!wpId.value || !isDirty.value) return
    saving.value = true
    try {
      const items = Array.from(formData.value.values())
      await fetch(getApiBase(), {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ items }),
      })
      isDirty.value = false
    } catch {
      // 静默失败：上层可通过 saving ref 感知
    } finally {
      saving.value = false
    }
  }

  function scheduleSave(): void {
    if (saveTimer) clearTimeout(saveTimer)
    saveTimer = setTimeout(() => {
      void saveData()
    }, debounceMs)
  }

  function setField(itemId: string, field: 'conclusion' | 'remark', value: string | null): void {
    const existing = formData.value.get(itemId) ?? { item_id: itemId, conclusion: null, remark: null }
    formData.value.set(itemId, { ...existing, [field]: value })
    isDirty.value = true
    scheduleSave()
  }

  function setFieldImmediate(itemId: string, field: 'conclusion' | 'remark', value: string | null): void {
    const existing = formData.value.get(itemId) ?? { item_id: itemId, conclusion: null, remark: null }
    formData.value.set(itemId, { ...existing, [field]: value })
    isDirty.value = true
    void saveData()
  }

  function resetData(): void {
    const map = new Map<string, FormDataItem>()
    if (defaultValues) {
      for (const [key, val] of Object.entries(defaultValues)) {
        map.set(`${prefix}${key}`, {
          item_id: `${prefix}${key}`,
          conclusion: typeof val === 'string' ? val : null,
          remark: null,
        })
      }
    }
    formData.value = map
    isDirty.value = true
  }

  async function flush(): Promise<void> {
    if (saveTimer) {
      clearTimeout(saveTimer)
      saveTimer = null
    }
    if (isDirty.value) await saveData()
  }

  // 组件卸载时自动 flush
  onScopeDispose(() => {
    void flush()
  })

  return {
    formData,
    loading,
    saving,
    isDirty,
    errors,
    loadData,
    saveData,
    resetData,
    setField,
    setFieldImmediate,
    flush,
  }
}
