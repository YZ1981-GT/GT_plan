/**
 * WorkpaperCapabilitySnapshot — formula-toolbar Task 3 client gate.
 *
 * Fail-closed: uninitialized / expired / epoch mismatch / denied → block
 * provider, save, AI, review, and rail actions. Denied UI uses zhMessage only
 * (no formula / thread / guidance metadata).
 */

export const CAPABILITY_SNAPSHOT_VERSION = '1.0' as const

export type CapabilityKey =
  | 'formulaView'
  | 'formulaEditUser'
  | 'formulaHistory'
  | 'aiReviewPage'
  | 'aiReviewBatch'
  | 'aiAssistChat'
  | 'humanReviewRead'
  | 'humanReviewWrite'
  | 'guidanceRead'

export const CAPABILITY_KEYS: readonly CapabilityKey[] = [
  'formulaView',
  'formulaEditUser',
  'formulaHistory',
  'aiReviewPage',
  'aiReviewBatch',
  'aiAssistChat',
  'humanReviewRead',
  'humanReviewWrite',
  'guidanceRead',
] as const

export interface CapabilityDecision {
  allowed: boolean
  reasonCode: string | null
  owner: string | null
  nextAction: string | null
  zhMessage: string | null
}

export interface WorkpaperCapabilitySnapshot {
  snapshotVersion: string
  subjectDigest: string
  ownerEpoch: number
  expiresAt: string
  issuedAt?: string
  projectId?: string
  wpId?: string
  sheetUid?: string | null
  role?: string
  formulaView: CapabilityDecision
  formulaEditUser: CapabilityDecision
  formulaHistory: CapabilityDecision
  aiReviewPage: CapabilityDecision
  aiReviewBatch: CapabilityDecision
  aiAssistChat: CapabilityDecision
  humanReviewRead: CapabilityDecision
  humanReviewWrite: CapabilityDecision
  guidanceRead: CapabilityDecision
}

export type CapabilityGateVerdict =
  | { status: 'allowed' }
  | {
      status: 'blocked'
      reasonCode: string
      zhMessage: string
      owner: string | null
      nextAction: string | null
    }

const FALLBACK_ZH: Record<string, string> = {
  snapshot_uninitialized: '能力快照尚未就绪，请稍候。',
  snapshot_expired: '能力快照已过期，请刷新后重试。',
  epoch_mismatch: '底稿上下文已切换，旧权限已失效。',
  role_denied: '当前角色无权执行此操作。',
  unknown_capability: '未知能力项，已拒绝。',
}

function blocked(
  reasonCode: string,
  partial?: Partial<CapabilityDecision>,
): CapabilityGateVerdict {
  return {
    status: 'blocked',
    reasonCode,
    zhMessage:
      partial?.zhMessage ||
      FALLBACK_ZH[reasonCode] ||
      '当前无权执行此操作。',
    owner: partial?.owner ?? 'workpaper-capability-matrix',
    nextAction: partial?.nextAction ?? '联系项目负责人',
  }
}

export function assertCapabilityAllowed(
  snapshot: WorkpaperCapabilitySnapshot | null | undefined,
  key: CapabilityKey,
  ownerEpoch: number,
  now: Date = new Date(),
): CapabilityGateVerdict {
  if (!snapshot) return blocked('snapshot_uninitialized')
  if (snapshot.ownerEpoch !== ownerEpoch) return blocked('epoch_mismatch')
  const expires = Date.parse(snapshot.expiresAt)
  if (!Number.isFinite(expires) || now.getTime() >= expires) {
    return blocked('snapshot_expired')
  }
  const decision = snapshot[key]
  if (!decision || typeof decision.allowed !== 'boolean') {
    return blocked('unknown_capability')
  }
  if (decision.allowed === true) return { status: 'allowed' }
  return blocked(decision.reasonCode || 'role_denied', decision)
}

/** True when denial copy would leak sensitive metadata (must stay false). */
export function denialLeaksSensitiveMetadata(zhMessage: string | null | undefined): boolean {
  if (!zhMessage) return false
  const banned = [
    'formula=',
    'thread_id',
    'threadId',
    'guidance_title',
    '编制说明标题',
    '公式内容',
    '线程数',
  ]
  return banned.some((b) => zhMessage.includes(b))
}
