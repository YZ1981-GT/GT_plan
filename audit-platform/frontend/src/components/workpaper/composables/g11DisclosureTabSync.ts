/**
 * G11 投资收益披露 Tab 的审计说明 / 结论读取与同步载荷（底稿披露 Tab 与附注页离屏同步共用，spec note-pull-followup-closure R1）。
 *
 * 由 `G11TabDisclosureBase` 原样抽出：审计说明存 `G11-disclosure-audit-note-{variant}` 的 remark，审计结论存
 * `G11-disclosure-audit-conclusion-{variant}`（conclusion 优先、兼容旧 remark），Tab 挂载时读一次；同步 = `useG11Disclosure.getSyncSnapshot`
 * （说明 + 结论）→ `buildG11SyncPayloads`（上市 五、69 / 国企 八、70）。提示、逐条发送与保存仍在 Tab。
 */
import type { ChecklistResponse } from './useF1FormData'
import { buildG11SyncPayloads, type G11SyncFromWorkpaperPayload, type G11SyncSnapshot } from './g11DisclosureSyncPayload'
import type { G11DisclosureVariant } from './g11NoteSectionMap'

export function g11DisclosureAuditTextKeys(variant: G11DisclosureVariant): { note: string; conclusion: string } {
  return {
    note: `G11-disclosure-audit-note-${variant}`,
    conclusion: `G11-disclosure-audit-conclusion-${variant}`,
  }
}

/** Tab 挂载时读到的审计说明 / 结论（没有已存值为空串，与 Tab 初值相同） */
export function readG11DisclosureAuditTexts(
  responses: ReadonlyMap<string, Pick<ChecklistResponse, 'conclusion' | 'remark'>>,
  variant: G11DisclosureVariant,
): { note: string; conclusion: string } {
  const keys = g11DisclosureAuditTextKeys(variant)
  const n = responses.get(keys.note)
  const c = responses.get(keys.conclusion)
  return {
    note: n?.remark ? n.remark : '',
    conclusion: c?.conclusion || c?.remark ? String(c.conclusion ?? c.remark ?? '') : '',
  }
}

/** 「同步到附注」的载荷（口径不适用回空数组，Tab 据此提示） */
export function buildG11TabSyncPayloads(
  wpId: string,
  variant: G11DisclosureVariant,
  applicableStandards: readonly string[] | null | undefined,
  dis: { getSyncSnapshot: (auditNote?: string, auditConclusion?: string) => G11SyncSnapshot },
  auditNote: string,
  auditConclusion: string,
): G11SyncFromWorkpaperPayload[] {
  return buildG11SyncPayloads(wpId, variant, applicableStandards ?? [], dis.getSyncSnapshot(auditNote, auditConclusion))
}
