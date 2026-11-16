/**
 * 编辑器外壳从渲染器拿的两项事实（spec platform-perf-hotspots R4）：侧栏 decision_trace 与编制说明闸门。
 *
 * 外壳不再自带一份 render-config：侧栏 decision_trace 在 HTML 模式读 GtWpRenderer 已加载的配置，
 * Univer 模式读目录请求顺带取到的配置。
 *
 * 编制说明面板挂上即按页签上下文请求 guidance，所以等上下文就绪再挂：有 sheetName / sheetCode / sheetUid /
 * wholeWorkbook 之一即放行；否则 HTML 模式等 GtWpRenderer 加载结束、Univer 模式等目录就绪，拿不到上下文时
 * 按整册请求一次（原先先按空上下文请求一次、页签上来再请求一次）。
 *
 * 另：**HTML 路径的未保存草稿访问器**也在这里登记（spec chat-host-draft-overlay Task 4）。
 * 放在本模块而不是外壳里，是因为外壳有一道 1341 行的行数棘轮（`__tests__/line-budget.spec.ts`），
 * 而本模块已经在收「外壳需要知道的渲染器 / 详情事实」—— 草稿能不能取，正是由
 * 「当前走 HTML 还是 Univer」+「详情里的业务版本」这两项事实决定的。Univer 路径的访问器由
 * `UniverEditorCore` 自己登记，故这里按 `useHtmlRenderer` 开关，同一 wpId 不会出现两个源。
 */
import { computed, type Ref } from 'vue'
import type { RenderConfig, WorkpaperSheetContext } from '@/composables/useWpRenderer'
import { useHtmlWorkpaperDraftAccessor } from './useHtmlWorkpaperDraftAccessor'

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
  /** 当前底稿 ID（HTML 草稿访问器按它登记）。 */
  wpId: () => string
  /** 底稿详情里的业务版本（`updated_at`）；访问器把它冻结成「打开编辑器时」的基线。 */
  currentBusinessVersion: () => unknown
}) {
  const sidePanelDecisionTrace = computed(() => (opts.useHtmlRenderer.value
    ? (opts.wpRendererRef.value?.renderConfig?.decision_trace ?? null)
    : (opts.univerCatalog.value?.decisionTrace ?? null)))

  const guidanceContextReady = computed(() => {
    const ctx = opts.activeSheetContext.value
    if (ctx.sheetName || ctx.sheetCode || ctx.sheetUid || ctx.wholeWorkbook) return true
    return opts.useHtmlRenderer.value ? opts.wpRendererRef.value?.loading === false : opts.univerSheetIdentityReady.value
  })

  useHtmlWorkpaperDraftAccessor({
    wpId: opts.wpId,
    currentBusinessVersion: opts.currentBusinessVersion,
    enabled: () => opts.useHtmlRenderer.value,
  })

  return { sidePanelDecisionTrace, guidanceContextReady }
}
