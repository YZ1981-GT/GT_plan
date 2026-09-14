/**
 * AI action taxonomy (formula-toolbar Task 9).
 *
 * Mutually exclusive action families — a11y names and capability keys differ.
 * AI assist MUST use DSH / PlatformAiChatPanel only.
 */

export const AI_ACTION_TAXONOMY_VERSION = '1.0' as const

export type AiActionFamily =
  | 'ai_review_page'
  | 'ai_review_batch'
  | 'ai_assist_chat'
  | 'human_review_thread'
  | 'submit_for_lifecycle_review'

export interface AiActionDescriptor {
  action: AiActionFamily
  /** Chinese accessible name for buttons / rails */
  a11yName: string
  capabilityKey:
    | 'aiReviewPage'
    | 'aiReviewBatch'
    | 'aiAssistChat'
    | 'humanReviewRead'
    | 'humanReviewWrite'
    | null
  carrier: 'ai-review-toolbar' | 'dsh-assist' | 'human-review-provider' | 'lifecycle'
  /** Must not share carrier with another family */
  exclusiveCarrier: boolean
}

export const AI_ACTION_DESCRIPTORS: readonly AiActionDescriptor[] = [
  {
    action: 'ai_review_page',
    a11yName: '本页 AI 复核',
    capabilityKey: 'aiReviewPage',
    carrier: 'ai-review-toolbar',
    exclusiveCarrier: false,
  },
  {
    action: 'ai_review_batch',
    a11yName: '批量 AI 复核',
    capabilityKey: 'aiReviewBatch',
    carrier: 'ai-review-toolbar',
    exclusiveCarrier: false,
  },
  {
    action: 'ai_assist_chat',
    a11yName: 'AI 助手对话',
    capabilityKey: 'aiAssistChat',
    carrier: 'dsh-assist',
    exclusiveCarrier: true,
  },
  {
    action: 'human_review_thread',
    a11yName: '人工复核对话',
    capabilityKey: 'humanReviewRead',
    carrier: 'human-review-provider',
    exclusiveCarrier: true,
  },
  {
    action: 'submit_for_lifecycle_review',
    a11yName: '提交生命周期复核',
    capabilityKey: null,
    carrier: 'lifecycle',
    exclusiveCarrier: true,
  },
] as const

export function descriptorFor(action: AiActionFamily): AiActionDescriptor {
  const hit = AI_ACTION_DESCRIPTORS.find((d) => d.action === action)
  if (!hit) throw new Error(`unknown AI action: ${action}`)
  return hit
}

export interface AiActionScope {
  action: AiActionFamily
  ownerEpoch: number
  contextRevision: number
  /** Ready location subject key or explicit selection id */
  subjectKey: string
  capabilityEpoch: number
}

export type AiActionDispatchResult =
  | { ok: true; scope: AiActionScope }
  | { ok: false; reasonCode: string; detail: string }

/**
 * Page/batch AI review scope must bind ready location (or selection) + capability epoch.
 */
export function assertAiReviewScope(input: {
  action: 'ai_review_page' | 'ai_review_batch'
  locationReady: boolean
  subjectKey: string | null
  ownerEpoch: number
  contextRevision: number
  capabilityEpoch: number
  capabilityAllowed: boolean
}): AiActionDispatchResult {
  if (!input.capabilityAllowed) {
    return {
      ok: false,
      reasonCode: 'capability_denied',
      detail: '当前无权发起 AI 复核',
    }
  }
  if (!input.locationReady || !input.subjectKey) {
    return {
      ok: false,
      reasonCode: 'location_not_ready',
      detail: '底稿位置未就绪，无法确定复核范围',
    }
  }
  if (input.ownerEpoch !== input.capabilityEpoch) {
    return {
      ok: false,
      reasonCode: 'epoch_mismatch',
      detail: '权限快照与底稿上下文不一致',
    }
  }
  return {
    ok: true,
    scope: {
      action: input.action,
      ownerEpoch: input.ownerEpoch,
      contextRevision: input.contextRevision,
      subjectKey: input.subjectKey,
      capabilityEpoch: input.capabilityEpoch,
    },
  }
}

/**
 * Assist must not borrow AI review permission / carrier.
 */
export function assertAiAssistCarrier(input: {
  requestedCarrier: string
  usingAiReviewPermission: boolean
}): AiActionDispatchResult {
  if (input.usingAiReviewPermission) {
    return {
      ok: false,
      reasonCode: 'assist_must_not_borrow_review',
      detail: 'AI 助手不得借用 AI 复核权限',
    }
  }
  if (input.requestedCarrier !== 'dsh-assist') {
    return {
      ok: false,
      reasonCode: 'assist_carrier_invalid',
      detail: 'AI 助手仅允许通过 DSH / PlatformAiChatPanel 承载',
    }
  }
  return {
    ok: true,
    scope: {
      action: 'ai_assist_chat',
      ownerEpoch: 0,
      contextRevision: 0,
      subjectKey: 'assist',
      capabilityEpoch: 0,
    },
  }
}

/** Families that must never share the same a11y name. */
export function assertTaxonomyA11yUnique(
  descriptors: readonly AiActionDescriptor[] = AI_ACTION_DESCRIPTORS,
): void {
  const seen = new Map<string, string>()
  for (const d of descriptors) {
    const prev = seen.get(d.a11yName)
    if (prev && prev !== d.action) {
      throw new Error(`duplicate a11y name "${d.a11yName}" for ${prev} and ${d.action}`)
    }
    seen.set(d.a11yName, d.action)
  }
}

/**
 * Business duplicate mounts that Task 9 removes from the workpaper-route
 * numerator (domain exclusions stay out of scope).
 */
export const AI_REVIEW_BUSINESS_DUPLICATE_PATTERNS = [
  {
    id: 'd2-local-ai-review-buttons',
    relativePath: 'components/workpaper/GtD2AccountsReceivable.vue',
    reason: 'local 本页/批量 AI 复核 — use GtWpAiReviewToolbar only',
  },
] as const
