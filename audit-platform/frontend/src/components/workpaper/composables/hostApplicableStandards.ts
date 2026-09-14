/**
 * 宿主组件（`Gt{Cycle}*.vue`）取「适用准则」的单一入口。
 *
 * 背景（applicable-standards-frontend-wiring → -runtime-and-sync-guard）：
 * 20+ 个宿主各写一份取值链，形态不一（有的只认数组、有的先读当时并不存在的
 * `runtime.applicableStandards`），任一环节形状不对就静默返回 `[]` → 披露 Tab 门控恒空：
 * - D3 两版对**所有**项目显示「当前项目不适用…」→ 用户不可达
 * - 其余循环门控恒开 → 可在国企项目编辑上市 Tab，服务端此前又不按 `current_standard`
 *   定位 → 数据写进错误章节
 *
 * 现在数据供给有两条：
 * 1. 逐 sheet 的 `html_data.project_context.applicable_standards`（render-config Step 9.5）
 * 2. `WorkpaperRuntimeContext.applicableStandards`（scaffold 从 render-config 响应顶层
 *    注入；`GtWorkpaperShell` 套壳路径也走这条）
 */
import { computed, inject, type ComputedRef } from 'vue'
import { normalizeApplicableStandards } from './applicableStandards'
import { WorkpaperRuntimeContextKey } from './useWorkpaperScaffold'

/** 取值优先级：project_context > projectContext > 顶层 snake > 顶层 camel > 显式回退。 */
export function resolveHostApplicableStandards(
  htmlData: Record<string, any> | null | undefined,
  fallback?: unknown,
): string[] {
  const hd = htmlData ?? undefined
  const raw =
    hd?.project_context?.applicable_standards
    ?? hd?.projectContext?.applicable_standards
    ?? hd?.applicable_standards
    ?? hd?.applicableStandards
    ?? fallback
  return normalizeApplicableStandards(raw)
}

export interface HostApplicableStandardsSources {
  /** 显式来源：`props.applicableStandards`，或宿主自有的 `formData.projectContext`。 */
  explicit?: () => unknown
  /** 该 sheet 的 `props.htmlData`。 */
  htmlData?: () => Record<string, any> | null | undefined
}

/**
 * 宿主适用准则（响应式）。
 *
 * 优先级：`explicit`（非空）> `htmlData`（非空）> runtime context（非空）> `[]`。
 * 每层都经 `normalizeApplicableStandards`，故 v2 对象 / 逗号串 / JSON 串均可。
 *
 * 🔴 必须在 setup 作用域调用（内部 `inject`）。写进事件处理函数体里会拿不到上下文。
 */
export function useHostApplicableStandards(
  sources: HostApplicableStandardsSources = {},
): ComputedRef<string[]> {
  const runtime = inject(WorkpaperRuntimeContextKey, null)
  return computed<string[]>(() => {
    const explicit = normalizeApplicableStandards(sources.explicit?.())
    if (explicit.length) return explicit
    const fromHtml = resolveHostApplicableStandards(sources.htmlData?.())
    if (fromHtml.length) return fromHtml
    return runtime?.applicableStandards.value ?? []
  })
}

export default resolveHostApplicableStandards
