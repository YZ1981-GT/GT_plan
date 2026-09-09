/**
 * Route eligibility + Bundle_Budget decision (pure functions).
 * Spec: audit-evidence-attachment-preview-format-expansion Task 2
 */
export type RouteId = 'A' | 'B'

export interface BundleBudget {
  /** 解析依赖进入首屏可达 chunk */
  entryParserBytes: number
  /** 首屏 gzip 增量上限 */
  entryGzipDelta: number
  archiveChunk: number
  emailChunk: number
  drawingChunk: number
  onDemandTotal: number
}

export const DEFAULT_BUNDLE_BUDGET: BundleBudget = {
  entryParserBytes: 0,
  entryGzipDelta: 8 * 1024,
  archiveChunk: 96 * 1024,
  emailChunk: 700 * 1024,
  drawingChunk: 400 * 1024,
  onDemandTotal: Math.floor(1.2 * 1024 * 1024),
}

export interface RouteCapability {
  archiveLimits: boolean
  emailIsolation: boolean
  dxf: boolean
  disposable: boolean
  license: boolean
}

export interface RouteMeasurement {
  route: RouteId
  capability: RouteCapability
  entryGzip: number
  /** 相对同口径 baseline 的首屏 gzip 增量；probe-only 可为 null */
  entryGzipDelta: number | null
  chunks: Partial<Record<'archive' | 'email' | 'drawing', number>>
  moduleIdsPresent: string[]
  notes?: string[]
}

export type RouteDecisionKind =
  | 'selected'
  | 'ineligible'
  | 'entry_over_budget'
  | 'drawing_drop'
  | 'subset_required'

export interface RouteDecision {
  kind: RouteDecisionKind
  selected: RouteId | null
  drawingInScope: boolean
  reason: string
  eligibleRoutes: RouteId[]
}

export function isCapabilityEligible(cap: RouteCapability): boolean {
  return (
    cap.archiveLimits &&
    cap.emailIsolation &&
    cap.dxf &&
    cap.disposable &&
    cap.license
  )
}

/**
 * 资格门先于体积门。没有实施任务的 A 不得被单纯体积结果选中。
 */
export function decideRoute(
  measurements: RouteMeasurement[],
  budget: BundleBudget = DEFAULT_BUNDLE_BUDGET,
): RouteDecision {
  const byRoute = new Map(measurements.map((m) => [m.route, m]))
  const eligible = measurements.filter((m) => isCapabilityEligible(m.capability))
  const eligibleIds = eligible.map((m) => m.route)

  if (eligible.length === 0) {
    return {
      kind: 'ineligible',
      selected: null,
      drawingInScope: false,
      reason: 'no_route_passed_capability_gate',
      eligibleRoutes: [],
    }
  }

  // 合资格路线间：优先体积更小的；若仅 B 有实施任务且 A 因资格被剔除，走 B
  const preferOrder: RouteId[] = ['B', 'A']
  let chosen = preferOrder.map((id) => byRoute.get(id)).find((m) => m && isCapabilityEligible(m.capability))

  // 若 A eligible 但首屏超门 → B（Req 7.4）
  const a = byRoute.get('A')
  const b = byRoute.get('B')
  if (a && isCapabilityEligible(a.capability) && a.entryGzipDelta != null && a.entryGzipDelta > budget.entryGzipDelta) {
    if (b && isCapabilityEligible(b.capability)) {
      chosen = b
      if (b.entryGzipDelta != null && b.entryGzipDelta > budget.entryGzipDelta) {
        return {
          kind: 'entry_over_budget',
          selected: null,
          drawingInScope: false,
          reason: 'all_eligible_routes_exceed_entry_budget',
          eligibleRoutes: eligibleIds,
        }
      }
      return {
        kind: 'selected',
        selected: 'B',
        drawingInScope: drawingFits(b, budget),
        reason: 'A_entry_over_budget_fallback_B',
        eligibleRoutes: eligibleIds,
      }
    }
  }

  if (!chosen) {
    return {
      kind: 'ineligible',
      selected: null,
      drawingInScope: false,
      reason: 'no_implementable_eligible_route',
      eligibleRoutes: eligibleIds,
    }
  }

  if (chosen.entryGzipDelta != null && chosen.entryGzipDelta > budget.entryGzipDelta) {
    return {
      kind: 'entry_over_budget',
      selected: null,
      drawingInScope: false,
      reason: 'eligible_route_exceeds_entry_budget',
      eligibleRoutes: eligibleIds,
    }
  }

  const drawingOk = drawingFits(chosen, budget)
  if (!drawingOk) {
    return {
      kind: 'drawing_drop',
      selected: chosen.route,
      drawingInScope: false,
      reason: 'drawing_chunk_over_budget_must_drop_and_rebuild',
      eligibleRoutes: eligibleIds,
    }
  }

  const onDemand =
    (chosen.chunks.archive ?? 0) + (chosen.chunks.email ?? 0) + (chosen.chunks.drawing ?? 0)
  if (onDemand > budget.onDemandTotal) {
    return {
      kind: 'subset_required',
      selected: chosen.route,
      drawingInScope: drawingOk,
      reason: 'on_demand_total_over_budget',
      eligibleRoutes: eligibleIds,
    }
  }

  return {
    kind: 'selected',
    selected: chosen.route,
    drawingInScope: true,
    reason: 'capability_then_budget_ok',
    eligibleRoutes: eligibleIds,
  }
}

function drawingFits(m: RouteMeasurement, budget: BundleBudget): boolean {
  const size = m.chunks.drawing
  if (size == null) return false
  return size <= budget.drawingChunk
}
