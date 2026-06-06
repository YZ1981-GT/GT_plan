/**
 * useEditStateMachine — 统一编辑状态机
 * [platform-ui-editing-consistency MVP-4]
 *
 * States: pristine | dirty | saving | saved | conflict | readonly | locked | archived
 * 所有编辑页面（底稿、附注、报表配置、调整分录）统一接入此状态机，
 * 替代各页面手写 dirty/saving 标志。
 */
import { ref, computed } from 'vue'

export type EditState =
  | 'pristine'
  | 'dirty'
  | 'saving'
  | 'saved'
  | 'conflict'
  | 'readonly'
  | 'locked'
  | 'archived'

export function useEditStateMachine(initial: EditState = 'pristine') {
  const state = ref<EditState>(initial)

  // --- Derived ---
  const isDirty = computed(() => state.value === 'dirty')
  const isSaving = computed(() => state.value === 'saving')
  const canEdit = computed(() =>
    !['readonly', 'locked', 'archived', 'saving'].includes(state.value),
  )

  // --- Transitions ---
  function markDirty() {
    if (canEdit.value && state.value !== 'dirty') {
      state.value = 'dirty'
    }
  }

  function startSave() {
    if (state.value === 'dirty') {
      state.value = 'saving'
    }
  }

  function saveDone() {
    if (state.value === 'saving') {
      state.value = 'saved'
    }
  }

  function saveFailed() {
    // 保存失败不清 dirty——回退到 dirty 让用户重试
    if (state.value === 'saving') {
      state.value = 'dirty'
    }
  }

  function setConflict() {
    state.value = 'conflict'
  }

  function setReadonly() {
    state.value = 'readonly'
  }

  function setLocked() {
    state.value = 'locked'
  }

  function setArchived() {
    state.value = 'archived'
  }

  function reset() {
    state.value = 'pristine'
  }

  return {
    state,
    isDirty,
    isSaving,
    canEdit,
    markDirty,
    startSave,
    saveDone,
    saveFailed,
    setConflict,
    setReadonly,
    setLocked,
    setArchived,
    reset,
  }
}
