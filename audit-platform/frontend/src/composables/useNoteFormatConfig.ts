/**
 * Sprint 4 Task 4.4 — 致同附注排版规范前端 composable
 *
 * Spec:   .kiro/specs/disclosure-note-full-revamp/ Sprint 4 Task 4.4 (R5.2)
 * Reqs:   v2 §5.4 / D7 / ADR-009 — 21 项排版参数从后端拉取并 inject 到 CSS 变量
 *
 * 用法
 * ----
 * ```ts
 * import { useNoteFormatConfig } from '@/composables/useNoteFormatConfig'
 *
 * const { config, cssVariables, loading, fetch, applyToRoot } = useNoteFormatConfig()
 *
 * onMounted(async () => {
 *   await fetch()
 *   applyToRoot()  // 将 21 项 CSS 变量注入 :root，附注预览组件可直接消费
 * })
 * ```
 */
import { ref, type Ref } from 'vue'

import { api } from '@/services/apiProxy'
import { disclosureNotes as P_dn } from '@/services/apiPaths'

// 21 项字段（与 backend NoteFormatConfig dataclass 一一对应）
export interface NoteFormatConfig {
  // 页面设置（4）
  margin_top_cm: number
  margin_bottom_cm: number
  margin_left_cm: number
  margin_right_cm: number
  // 页眉页脚（2）
  header_distance_cm: number
  footer_distance_cm: number
  // 字体（4）
  font_chinese: string
  font_western: string
  font_size_pt: number
  font_size_table_pt: number
  // 段落间距（4）
  heading_space_after_lines: number
  body_space_after_lines: number
  after_table_space_before_lines: number
  after_table_space_after_lines: number
  // 表格（4）
  table_top_border_pt: number
  table_bottom_border_pt: number
  header_bottom_border_pt: number
  table_row_height_cm: number
  // 标题缩进（2）
  heading1_left_indent_chars: number
  heading2_left_indent_chars: number
  // 数值格式（1）
  empty_value_placeholder: string
}

export interface NoteFormatConfigResponse {
  format_config: NoteFormatConfig
  css_variables: Record<string, string>
  field_count: number
}

export function useNoteFormatConfig() {
  const config: Ref<NoteFormatConfig | null> = ref(null)
  const cssVariables: Ref<Record<string, string>> = ref({})
  const fieldCount = ref(0)
  const loading = ref(false)
  const error = ref<unknown>(null)

  /** 从后端拉取 21 项排版规范并缓存到 ref. */
  async function fetch() {
    loading.value = true
    error.value = null
    try {
      const resp: any = await api.get(P_dn.formatConfig)
      const data = resp as NoteFormatConfigResponse
      config.value = data.format_config
      cssVariables.value = data.css_variables ?? {}
      fieldCount.value = data.field_count ?? Object.keys(data.format_config || {}).length
    } catch (e) {
      error.value = e
      throw e
    } finally {
      loading.value = false
    }
  }

  /**
   * 把 21 项 CSS 变量注入 ``:root``（document.documentElement）.
   * 调用方负责生命周期（unmount 时调 ``revertFromRoot`` 清理）。
   */
  function applyToRoot(target: HTMLElement = document.documentElement) {
    for (const [name, value] of Object.entries(cssVariables.value)) {
      target.style.setProperty(name, value)
    }
  }

  /** 从 ``:root`` 移除本 composable 注入的 CSS 变量. */
  function revertFromRoot(target: HTMLElement = document.documentElement) {
    for (const name of Object.keys(cssVariables.value)) {
      target.style.removeProperty(name)
    }
  }

  return {
    config,
    cssVariables,
    fieldCount,
    loading,
    error,
    fetch,
    applyToRoot,
    revertFromRoot,
  }
}
