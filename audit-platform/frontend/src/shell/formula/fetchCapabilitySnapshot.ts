/**
 * Live WorkpaperCapabilitySnapshot fetch (formula-toolbar Task 12).
 */

import { api as httpApi } from '@/services/apiProxy'
import {
  CAPABILITY_SNAPSHOT_VERSION,
  type CapabilityDecision,
  type WorkpaperCapabilitySnapshot,
} from './workpaperCapabilitySnapshot'

export const CAPABILITY_SNAPSHOT_PATH = {
  get: (wpId: string) => `/api/workpapers/${wpId}/capability-snapshot`,
} as const

function asDecision(raw: unknown): CapabilityDecision {
  const o = (raw && typeof raw === 'object' ? raw : {}) as Record<string, unknown>
  return {
    allowed: o.allowed === true,
    reasonCode: typeof o.reasonCode === 'string' ? o.reasonCode : null,
    owner: typeof o.owner === 'string' ? o.owner : null,
    nextAction: typeof o.nextAction === 'string' ? o.nextAction : null,
    zhMessage: typeof o.zhMessage === 'string' ? o.zhMessage : null,
  }
}

export function parseCapabilitySnapshotPayload(
  payload: unknown,
  fallbackOwnerEpoch: number,
): WorkpaperCapabilitySnapshot | null {
  if (!payload || typeof payload !== 'object') return null
  const o = payload as Record<string, unknown>
  const version = String(o.snapshotVersion ?? o.snapshot_version ?? '')
  if (version && version !== CAPABILITY_SNAPSHOT_VERSION) {
    // Unknown major → fail-closed null (caller keeps prior or blocks).
    const major = version.split('.')[0]
    if (major !== '1') return null
  }
  return {
    snapshotVersion: CAPABILITY_SNAPSHOT_VERSION,
    subjectDigest: String(o.subjectDigest ?? o.subject_digest ?? ''),
    ownerEpoch: Number(o.ownerEpoch ?? o.owner_epoch ?? fallbackOwnerEpoch),
    expiresAt: String(o.expiresAt ?? o.expires_at ?? ''),
    issuedAt: typeof o.issuedAt === 'string' ? o.issuedAt : undefined,
    projectId: typeof o.projectId === 'string' ? o.projectId : undefined,
    wpId: typeof o.wpId === 'string' ? o.wpId : undefined,
    sheetUid: (o.sheetUid as string | null | undefined) ?? null,
    role: typeof o.role === 'string' ? o.role : undefined,
    formulaView: asDecision(o.formulaView),
    formulaEditUser: asDecision(o.formulaEditUser),
    formulaHistory: asDecision(o.formulaHistory),
    aiReviewPage: asDecision(o.aiReviewPage),
    aiReviewBatch: asDecision(o.aiReviewBatch),
    aiAssistChat: asDecision(o.aiAssistChat),
    humanReviewRead: asDecision(o.humanReviewRead),
    humanReviewWrite: asDecision(o.humanReviewWrite),
    guidanceRead: asDecision(o.guidanceRead),
  }
}

export async function fetchWorkpaperCapabilitySnapshot(input: {
  wpId: string
  projectId: string
  ownerEpoch: number
  sheetUid?: string | null
}): Promise<WorkpaperCapabilitySnapshot | null> {
  const params = new URLSearchParams({
    project_id: input.projectId,
    ownerEpoch: String(input.ownerEpoch),
  })
  if (input.sheetUid) params.set('sheetUid', input.sheetUid)
  const url = `${CAPABILITY_SNAPSHOT_PATH.get(input.wpId)}?${params.toString()}`
  const raw = await httpApi.get(url)
  return parseCapabilitySnapshotPayload(raw, input.ownerEpoch)
}
