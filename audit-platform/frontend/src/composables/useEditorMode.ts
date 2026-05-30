/**
 * useEditorMode - HTML/Univer dual-mode dispatch [V3 Req 12.1.3]
 *
 * Migrates the component_type routing logic out of WorkpaperEditor.vue.
 *
 * Routing priority (consumed in the host onMounted):
 *  1. HTML class (A/B/C/D/E/H/skip 1346 sheets) -> GtWpRenderer
 *  2. Univer class (F/G 558 sheets) -> default Univer editor
 *
 * Notes:
 *  - This composable owns componentType state, the HTML allowlist,
 *    useWpClassification wiring, and the fetchComponentType async fetch.
 *
 * @example
 * const { useHtmlRenderer, componentType, fetchComponentType } = useEditorMode({
 *   wpId, projectId, wpDetail,
 * })
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { api as httpApi } from '@/services/apiProxy'
import { workpapers as P_wp } from '@/services/apiPaths'
import { useWpClassification } from '@/composables/useWpClassification'
import { HTML_RENDERER_ROUTE_SET } from '@/components/workpaper/htmlRendererRegistry'

/**
 * HTML class componentType allowlist (matches GtWpRenderer dispatch).
 *
 * 重构 2026-05-28：从硬编码 Set 改为从 htmlRendererRegistry 单一来源派生。
 * 新增 HTML 渲染器类型只需改 htmlRendererRegistry.ts，本 Set 自动同步。
 * 包含 skip placeholder（GtWpRenderer 内部 fallback 渲染 SkippedSheetPlaceholder）。
 */
export const HTML_COMPONENT_TYPES: ReadonlySet<string> = HTML_RENDERER_ROUTE_SET

export interface EditorModeContext {
  /** Workpaper id (route param) */
  wpId: Ref<string>
  /** Project id (route param) */
  projectId: Ref<string>
  /** Workpaper detail held by the host; this composable writes into it via fetchComponentType */
  wpDetail: Ref<any>
}

export interface EditorModeReturn {
  /** Current componentType (default 'univer', overwritten after fetch). */
  componentType: Ref<string>
  /** Resolved HTML componentType when whitelisted, otherwise empty string. */
  htmlComponentType: ComputedRef<string>
  /** Whether to render via GtWpRenderer. */
  useHtmlRenderer: ComputedRef<boolean>
  /** Underlying useWpClassification instance (exposed for host reuse). */
  wpClassification: ReturnType<typeof useWpClassification>
  /** Fetch component_type from backend; falls back to 'univer' on error. */
  fetchComponentType: () => Promise<void>
  /** HTML componentType allowlist (read-only). */
  HTML_COMPONENT_TYPES: ReadonlySet<string>
}

/**
 * Behaviour parity (must match WorkpaperEditor.vue pre-extraction):
 *  - componentType.value defaults to 'univer'
 *  - fetchComponentType prefers detail.component_type, then template_metadata.component_type, else 'univer'
 *  - fetchComponentType swallows errors and resets componentType to 'univer'
 *  - useHtmlRenderer is true iff classification loaded + classifications non-empty + ct in allowlist
 *  - wp_code / projectId changes (including first run) trigger wpClassification.load()
 */
export function useEditorMode(ctx: EditorModeContext): EditorModeReturn {
  const componentType = ref<string>('univer')

  // Derive wp_code from the host wpDetail; empty string skips load.
  const wpCodeRef = computed<string>(() => ctx.wpDetail.value?.wp_code || '')

  const wpClassification = useWpClassification(wpCodeRef, ctx.projectId)

  const htmlComponentType = computed<string>(() => {
    if (!wpClassification.classification.value) return ''
    if (!wpClassification.classification.value.classifications?.length) return ''
    const ct = wpClassification.componentType.value
    return HTML_COMPONENT_TYPES.has(ct as string) ? (ct as string) : ''
  })

  const useHtmlRenderer = computed<boolean>(() => !!htmlComponentType.value)

  // Auto-load classification once wp_code / projectId are ready.
  watch(
    () => [wpCodeRef.value, ctx.projectId.value] as const,
    ([code, pid]) => {
      if (code && pid) {
        wpClassification.load().catch(() => {
          /* swallow: classification failure falls back to Univer path */
        })
      }
    },
    { immediate: true },
  )

  async function fetchComponentType(): Promise<void> {
    try {
      const detail = await httpApi.get(P_wp.detail(ctx.projectId.value, ctx.wpId.value))
      const ct = detail?.component_type || detail?.template_metadata?.component_type || 'univer'
      componentType.value = ct
      if (detail) ctx.wpDetail.value = detail
    } catch {
      componentType.value = 'univer'
    }
  }

  return {
    componentType,
    htmlComponentType,
    useHtmlRenderer,
    wpClassification,
    fetchComponentType,
    HTML_COMPONENT_TYPES,
  }
}
