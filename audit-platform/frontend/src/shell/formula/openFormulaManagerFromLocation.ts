/**
 * openFormulaManagerFromLocation — single production entry that converts a
 * renderable page's runtime context into a complete CanonicalWorkpaperLocation,
 * runs it through the unified `createOpenFormulaManagerCommand` gate, and only
 * then emits the `open-formula-manager` EventBus payload.
 *
 * ADR-FMC-03 / spec formula-manager-closure Task 2.1:
 *  - Every renderable page opens the central FormulaManager through THIS helper
 *    (the `data-testid=formula-manager-open` primary outlet calls it).
 *  - The helper fails closed when the page cannot supply a complete location
 *    identity (projectId / wpId / wpCode): no nodeKey-only bypass, no silent
 *    `report` scope fallback, no `/report-config/types` or missing-year 422.
 *  - Project-level RBAC is enforced server-side. The client command gate consumes the
 *    real capability snapshot fetched by WorkpaperEditor; missing/expired/mismatched
 *    snapshots fail closed and are never replaced with a synthetic allow decision.
 *
 * The EventBus payload is DERIVED from the same validated location, so the
 * dialog's scope label / breadcrumb stay consistent with the opening page
 * (a workpaper entry never lands on `report` scope).
 */

import { GC0_CONTRACT_VERSION, type CanonicalWorkpaperLocation } from '@/shared/contracts/gc0'
import { eventBus, type OpenFormulaManagerPayload } from '@/utils/eventBus'

import type { WorkpaperCapabilitySnapshot } from './workpaperCapabilitySnapshot'
import {
  createOpenFormulaManagerCommand,
  type OpenFormulaManagerResult,
} from './openFormulaManagerCommand'

export type FormulaManagerOutletScope = NonNullable<OpenFormulaManagerPayload['scope']>

/** Raw runtime context collected by a renderable page's primary outlet. */
export interface FormulaManagerOutletContext {
  projectId?: string | null
  wpId?: string | null
  wpCode?: string | null
  /** Fiscal / preparation year. */
  year?: number | null
  /** Current real sheet code; empty string = whole-workbook view. */
  sheetName?: string | null
  /** Sheet codes the host workbook actually owns (render-config is runtime truth). */
  sheetCodes?: string[] | null
  organizationId?: string | null
  entryId?: string | null
  host?: CanonicalWorkpaperLocation['host']
  /** Scope label; a workpaper entry is always `workpaper`, never `report`. */
  scope?: FormulaManagerOutletScope
  /** Migration metadata only — never used as location identity. */
  legacyNodeKey?: string
  /** Extra payload fields (consol / note entries, e.g. templateType / noteSection). */
  extras?: Partial<OpenFormulaManagerPayload>
  ownerEpoch?: number
  contextRevision?: number
}

export type OpenFormulaManagerOutcome =
  | { ok: true; command: OpenFormulaManagerResult & { ok: true }; payload: OpenFormulaManagerPayload }
  | { ok: false; reasonCode: string; detail: string }

/**
 * Build a complete CanonicalWorkpaperLocation from page context.
 * Returns null when a required identity field (projectId/wpId/wpCode) is absent
 * — this is the fail-closed gate that forbids a nodeKey-only open.
 */
export function buildLocationFromContext(
  ctx: FormulaManagerOutletContext,
): CanonicalWorkpaperLocation | null {
  const projectId = (ctx.projectId ?? '').trim()
  const wpId = (ctx.wpId ?? '').trim()
  const wpCode = (ctx.wpCode ?? '').trim()
  if (!projectId || !wpId || !wpCode) return null

  const sheetName = (ctx.sheetName ?? '').trim()
  const anchor: CanonicalWorkpaperLocation['anchor'] = sheetName
    ? { kind: 'sheet', sheetUid: sheetName, sheetCode: sheetName }
    : { kind: 'whole_workbook' }

  return {
    contractVersion: GC0_CONTRACT_VERSION,
    organizationId: (ctx.organizationId ?? '').trim() || 'default',
    projectId,
    fiscalYear: Number.isFinite(ctx.year as number) ? (ctx.year as number) : 0,
    wpId,
    wpCode,
    entryId: ctx.entryId ?? null,
    host: ctx.host ?? 'html',
    anchor,
    display: { sheetName: sheetName || null, sectionLabel: null },
    ownerEpoch: ctx.ownerEpoch ?? 0,
    contextRevision: ctx.contextRevision ?? 0,
  }
}

/**
 * Derive the EventBus payload from the validated location — single source.
 * `scope` defaults to `workpaper` so a workpaper entry never silently becomes
 * a `report` scope (ADR-FMC-03 consequence).
 */
export function payloadFromLocation(
  location: CanonicalWorkpaperLocation,
  ctx: FormulaManagerOutletContext,
): OpenFormulaManagerPayload {
  const sheetName = location.display.sheetName ?? ''
  return {
    ...(ctx.extras ?? {}),
    wpId: location.wpId,
    projectId: location.projectId,
    wpCode: location.wpCode,
    year: location.fiscalYear || undefined,
    sheetName,
    sheetCodes: ctx.sheetCodes ?? undefined,
    scope: 'workpaper',
    ...(ctx.legacyNodeKey ? { nodeKey: ctx.legacyNodeKey } : {}),
  }
}

/**
 * Production entry point. Builds the location, runs the unified command gate,
 * and (only on ok) emits `open-formula-manager` with a complete payload.
 *
 * Returns a typed outcome so callers can surface a zh message on failure
 * instead of opening a context-less dialog.
 */
export function openFormulaManagerFromLocation(
  ctx: FormulaManagerOutletContext,
  capability: WorkpaperCapabilitySnapshot | null | undefined,
  canonicalLocation?: CanonicalWorkpaperLocation | null,
): OpenFormulaManagerOutcome {
  if (!capability) {
    return {
      ok: false,
      reasonCode: 'capability_missing',
      detail: '公式管理能力尚未就绪，请稍候刷新后重试',
    }
  }
  const location = canonicalLocation ?? buildLocationFromContext(ctx)
  if (!location) {
    return {
      ok: false,
      reasonCode: 'incomplete_location',
      detail: '当前底稿缺少完整上下文（项目/实例/编码），暂时无法打开公式管理',
    }
  }

  const result = createOpenFormulaManagerCommand({
    location,
    capability,
    legacyNodeKey: ctx.legacyNodeKey,
  })

  if (!result.ok) {
    return { ok: false, reasonCode: result.reasonCode, detail: result.detail }
  }

  const payload: OpenFormulaManagerPayload = {
    ...payloadFromLocation(location, ctx),
    contextKind: 'workpaper',
    canonicalLocation: location,
    capabilitySnapshot: capability,
    formulaSession: result.session,
    readOnly: capability.formulaEditUser.allowed !== true,
  }
  eventBus.emit('open-formula-manager', payload)
  return { ok: true, command: result, payload }
}


export type FormulaManagerProjectScope = Exclude<FormulaManagerOutletScope, 'workpaper'>

export interface FormulaManagerScopeContext extends Omit<OpenFormulaManagerPayload, 'scope'> {
  scope: FormulaManagerProjectScope
  projectId: string
  year: number
}

/** 无普通 wpId 的 report/note/tb/consolidation 入口；显式分支，禁止伪造工作底稿身份。 */
export function openFormulaManagerScope(
  ctx: FormulaManagerScopeContext,
): { ok: true; payload: OpenFormulaManagerPayload } | { ok: false; reasonCode: string; detail: string } {
  if (!ctx.projectId?.trim() || !Number.isFinite(ctx.year) || !ctx.scope) {
    return {
      ok: false,
      reasonCode: 'incomplete_scope_context',
      detail: '公式管理缺少完整的项目、年度或作用域上下文',
    }
  }
  const payload: OpenFormulaManagerPayload = {
    ...ctx,
    contextKind: 'scope',
    readOnly: false,
  }
  eventBus.emit('open-formula-manager', payload)
  return { ok: true, payload }
}
