import {
  computed,
  inject,
  provide,
  reactive,
  ref,
  type ComputedRef,
  type InjectionKey,
} from 'vue'

export type ConsolTransitionDecision = 'save' | 'discard' | 'cancel'

export interface ConsolWorkspaceDraft {
  id: string
  label: () => string
  contextKey: () => string
  isDirty: () => boolean
  isSaving: () => boolean
  save: () => Promise<boolean>
  discard: () => Promise<void> | void
}

export interface ConsolWorkspaceDecisionState {
  visible: boolean
  processing: boolean
  reason: string
  labels: string[]
}

export interface ConsolWorkspaceGuard {
  state: ConsolWorkspaceDecisionState
  hasDirty: ComputedRef<boolean>
  hasPendingSave: ComputedRef<boolean>
  register: (draft: ConsolWorkspaceDraft) => () => void
  notifyStateChange: () => void
  confirmTransition: (reason: string, participantIds?: string[]) => Promise<boolean>
  runTransition: (
    reason: string,
    action: () => void | Promise<void>,
    participantIds?: string[],
  ) => Promise<boolean>
  decide: (decision: ConsolTransitionDecision) => void
  cancelPending: () => void
}

const CONSOL_WORKSPACE_GUARD: InjectionKey<ConsolWorkspaceGuard> = Symbol('consol-workspace-guard')

export function createConsolWorkspaceGuard(): ConsolWorkspaceGuard {
  const drafts = new Map<string, ConsolWorkspaceDraft>()
  const revision = ref(0)
  const state = reactive<ConsolWorkspaceDecisionState>({
    visible: false,
    processing: false,
    reason: '',
    labels: [],
  })
  let pendingDecision: Promise<ConsolTransitionDecision> | null = null
  let resolveDecision: ((decision: ConsolTransitionDecision) => void) | null = null

  function notifyStateChange(): void {
    revision.value += 1
  }

  function selected(ids?: string[]): ConsolWorkspaceDraft[] {
    const allowed = ids ? new Set(ids) : null
    return [...drafts.values()].filter((draft) => !allowed || allowed.has(draft.id))
  }

  const hasDirty = computed(() => {
    revision.value
    return selected().some((draft) => draft.isDirty())
  })
  const hasPendingSave = computed(() => {
    revision.value
    return selected().some((draft) => draft.isSaving())
  })

  function register(draft: ConsolWorkspaceDraft): () => void {
    drafts.set(draft.id, draft)
    notifyStateChange()
    return () => {
      if (drafts.get(draft.id) === draft) drafts.delete(draft.id)
      notifyStateChange()
    }
  }

  function ask(reason: string, targets: ConsolWorkspaceDraft[]): Promise<ConsolTransitionDecision> {
    if (pendingDecision) return pendingDecision
    state.reason = reason
    state.labels = targets.map((draft) => draft.label()).filter(Boolean)
    state.visible = true
    pendingDecision = new Promise((resolve) => { resolveDecision = resolve })
    return pendingDecision
  }

  function decide(decision: ConsolTransitionDecision): void {
    if (!resolveDecision || state.processing) return
    const resolve = resolveDecision
    resolveDecision = null
    pendingDecision = null
    state.visible = false
    resolve(decision)
  }

  function cancelPending(): void {
    decide('cancel')
  }

  async function saveUntilStable(targets: ConsolWorkspaceDraft[]): Promise<boolean> {
    for (let pass = 0; pass < 8; pass += 1) {
      const pending = targets.filter((draft) => draft.isDirty() || draft.isSaving())
      if (!pending.length) return true
      for (const draft of pending) {
        if (!(await draft.save())) return false
      }
      notifyStateChange()
    }
    return !targets.some((draft) => draft.isDirty() || draft.isSaving())
  }

  async function confirmTransition(reason: string, participantIds?: string[]): Promise<boolean> {
    const targets = selected(participantIds)
    const blockers = targets.filter((draft) => draft.isDirty() || draft.isSaving())
    if (!blockers.length) return true
    const decision = await ask(reason, blockers)
    if (decision === 'cancel') return false
    state.processing = true
    try {
      if (decision === 'discard') {
        for (const draft of blockers) await draft.discard()
        notifyStateChange()
        return true
      }
      return await saveUntilStable(blockers)
    } finally {
      state.processing = false
    }
  }

  async function runTransition(
    reason: string,
    action: () => void | Promise<void>,
    participantIds?: string[],
  ): Promise<boolean> {
    if (!(await confirmTransition(reason, participantIds))) return false
    await action()
    return true
  }

  return {
    state,
    hasDirty,
    hasPendingSave,
    register,
    notifyStateChange,
    confirmTransition,
    runTransition,
    decide,
    cancelPending,
  }
}

export function provideConsolWorkspaceGuard(): ConsolWorkspaceGuard {
  const guard = createConsolWorkspaceGuard()
  provide(CONSOL_WORKSPACE_GUARD, guard)
  return guard
}

export function useConsolWorkspaceGuard(): ConsolWorkspaceGuard | null {
  return inject(CONSOL_WORKSPACE_GUARD, null)
}
