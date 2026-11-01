/**
 * 同一文档的保存协调器。
 *
 * 编辑代际单调递增；同一文档只允许一个保存循环。保存期间出现新编辑时，
 * 当前请求只确认它覆盖的代际，并立即串行补存最新代际。
 */
export type SaveOnceResult = boolean | void

export interface SaveAttempt<DocumentKey> {
  documentKey: DocumentKey
  revision: number
  /** 请求完成时仍是本次捕获的文档代际。 */
  isCurrent: () => boolean
}

interface DocumentSaveState {
  editRevision: number
  savedRevision: number
  generation: number
  inFlight: Promise<boolean> | null
}

export function createSaveCoordinator<DocumentKey = string>() {
  const states = new Map<DocumentKey, DocumentSaveState>()

  function stateOf(documentKey: DocumentKey): DocumentSaveState {
    let state = states.get(documentKey)
    if (!state) {
      state = { editRevision: 0, savedRevision: 0, generation: 0, inFlight: null }
      states.set(documentKey, state)
    }
    return state
  }

  function markEdited(documentKey: DocumentKey): number {
    const state = stateOf(documentKey)
    state.editRevision += 1
    return state.editRevision
  }

  /** 用户明确放弃本地修改时，使在途旧回执失效并把当前代际记为已处理。 */
  function discard(documentKey: DocumentKey): void {
    const state = stateOf(documentKey)
    state.generation += 1
    state.savedRevision = state.editRevision
  }

  function run(
    documentKey: DocumentKey,
    saveOnce: (attempt: SaveAttempt<DocumentKey>) => Promise<SaveOnceResult>,
  ): Promise<boolean> {
    const state = stateOf(documentKey)
    if (state.inFlight) return state.inFlight

    const generation = state.generation
    const operation = (async () => {
      let firstAttempt = true
      while (firstAttempt || state.savedRevision < state.editRevision) {
        firstAttempt = false
        const revision = state.editRevision
        const result = await saveOnce({
          documentKey,
          revision,
          isCurrent: () => state.generation === generation && state.editRevision === revision,
        })
        if (state.generation !== generation || result === false) return false
        state.savedRevision = Math.max(state.savedRevision, revision)
      }
      return true
    })()

    let tracked!: Promise<boolean>
    tracked = operation.finally(() => {
      if (state.inFlight === tracked) state.inFlight = null
    })
    state.inFlight = tracked
    return tracked
  }

  return {
    markEdited,
    discard,
    run,
    isDirty: (documentKey: DocumentKey) => {
      const state = stateOf(documentKey)
      return state.editRevision > state.savedRevision
    },
    isSaving: (documentKey: DocumentKey) => stateOf(documentKey).inFlight !== null,
    editRevision: (documentKey: DocumentKey) => stateOf(documentKey).editRevision,
    savedRevision: (documentKey: DocumentKey) => stateOf(documentKey).savedRevision,
  }
}

export type SaveCoordinator<DocumentKey = string> = ReturnType<typeof createSaveCoordinator<DocumentKey>>
