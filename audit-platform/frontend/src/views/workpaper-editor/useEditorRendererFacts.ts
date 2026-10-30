/**
 * 编辑器外壳从渲染器拿的两项事实（spec platform-perf-hotspots R4）：侧栏 decision_trace 与编制说明闸门。
 *
 * 外壳不再自带一份 render-config：侧栏 decision_trace 在 HTML 模式读 GtWpRenderer 已加载的配置，
 * Univer 模式读目录请求顺带取到的配置。
 *
 * 编制说明面板挂上即按页签上下文请求 guidance，所以等上下文就绪再挂：有 sheetName / sheetCode / sheetUid /
 * wholeWorkbook 之一即放行；否则 HTML 模式等 GtWpRenderer 加载结束、Univer 模式等目录就绪，拿不到上下文时
 * 按整册请求一次（原先先按空上下文请求一次、页签上来再请求一次）。
 */
import { computed, type Ref } from 'vue'
import type { RenderConfig, WorkpaperSheetContext } from '@/composables/useWpRenderer'

/** Univer 目录请求（render-config）里外壳要用的配置级字段；目录不可用时整体为 null。 */
export interface UniverCatalogFacts {
  wpCode: string | null
  decisionTrace: RenderConfig['decision_trace'] | null
}

/** GtWpRenderer 通过 defineExpose 暴露、外壳读取的部分。 */
interface HtmlRendererExposed {
  renderConfig?: RenderConfig | null
  loading?: boolean
}

export function useEditorRendererFacts(opts: {
  useHtmlRenderer: Readonly<Ref<boolean>>
  wpRendererRef: Readonly<Ref<HtmlRendererExposed | null>>
  univerCatalog: Readonly<Ref<UniverCatalogFacts | null>>
  univerSheetIdentityReady: Readonly<Ref<boolean>>
  activeSheetContext: Readonly<Ref<WorkpaperSheetContext>>
}) {
  const sidePanelDecisionTrace = computed(() => (opts.useHtmlRenderer.value
    ? (opts.wpRendererRef.value?.renderConfig?.decision_trace ?? null)
    : (opts.univerCatalog.value?.decisionTrace ?? null)))

  const guidanceContextReady = computed(() => {
    const ctx = opts.activeSheetContext.value
    if (ctx.sheetName || ctx.sheetCode || ctx.sheetUid || ctx.wholeWorkbook) return true
    return opts.useHtmlRenderer.value ? opts.wpRendererRef.value?.loading === false : opts.univerSheetIdentityReady.value
  })

  return { sidePanelDecisionTrace, guidanceContextReady }
}
