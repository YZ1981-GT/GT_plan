/**
 * useEditStateMachine — 统一编辑状态机
 * [platform-ui-editing-consistency P0-5]
 *
 * States: pristine | dirty | saving | saved | conflict | readonly | locked | archived
 *
 * 所有编辑页面（底稿、附注、报表配置、调整分录）统一接入此状态机，
 * 替代各页面手写 dirty/saving 标志。
 *
 * 核心保证：
 * - dirty 页面在保存成功前不得显示 saved
 * - 保存失败不清除 dirty（回退到 dirty 让用户重试）
 * - readonly/locked/archived 状态下 markDirty 无效
 * - 提供 shouldBlockLeave() 用于离开拦截
 */
import { ref, computed, onBeforeUnmount } from 'vue'
import type { Ref } from 'vue'

export type EditState =
  | 'pristine'
  | 'dirty'
  | 'saving'
  | 'saved'
  | 'conflict'
  | 'readonly'
  | 'locked'
  | 'archived'

export interface EditStateMachineOptions {
  /** 保存成功后自动回归 pristine 的延迟毫秒（0=不自动回归） */
  savedResetDelay?: number
  /** 离开拦截提示文案 */
  leaveMessage?: string
}

export function useEditStateMachine(
  initial: EditState = 'pristine',
  options: EditStateMachineOptions = {},
) {
  const {
    savedResetDelay = 2000,
    leaveMessage = '页面有未保存的修改，确定离开吗？',
  } = options

  const state = ref<EditState>(initial)
  let savedTimer: ReturnType<typeof setTimeout> | null = null

  // --- Derived ---
  const isDirty = computed(() => state.value === 'dirty')
  const isSaving = computed(() => state.value === 'saving')
  const isSaved = computed(() => state.value === 'saved')
  const isConflict = computed(() => state.value === 'conflict')
  const isReadonly = computed(() =>
    ['readonly', 'locked', 'archived'].includes(state.value),
  )
  const canEdit = computed(() =>
    !['readonly', 'locked', 'archived', 'saving'].includes(state.value),
  )

  /**
   * 状态中文文案（用于 UI 状态栏显示）
   */
  const statusText = computed<string>(() => {
    switch (state.value) {
      case 'pristine': return ''
      case 'dirty': return '有未保存的修改'
      case 'saving': return '保存中…'
      case 'saved': return '已保存'
      case 'conflict': return '数据冲突，请刷新'
      case 'readonly': return '只读'
      case 'locked': return '已锁定'
      case 'archived': return '已归档'
      default: return ''
    }
  })

  // --- Transitions ---
  function markDirty() {
    if (canEdit.value && state.value !== 'dirty') {
      clearSavedTimer()
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
      // 自动回归 pristine（延迟 N 秒后）
      if (savedResetDelay > 0) {
        clearSavedTimer()
        savedTimer = setTimeout(() => {
          if (state.value === 'saved') {
            state.value = 'pristine'
          }
        }, savedResetDelay)
      }
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
    clearSavedTimer()
    state.value = 'pristine'
  }

  // --- 离开拦截 ---

  /**
   * 是否应阻止离开页面（dirty 或 saving 状态）
   */
  function shouldBlockLeave(): boolean {
    return state.value === 'dirty' || state.value === 'saving'
  }

  /**
   * 获取离开拦截消息
   */
  function getLeaveMessage(): string {
    return leaveMessage
  }

  // --- 内部工具 ---
  function clearSavedTimer() {
    if (savedTimer !== null) {
      clearTimeout(savedTimer)
      savedTimer = null
    }
  }

  // 组件卸载时清理 timer
  onBeforeUnmount(() => {
    clearSavedTimer()
  })

  return {
    state,
    isDirty,
    isSaving,
    isSaved,
    isConflict,
    isReadonly,
    canEdit,
    statusText,
    markDirty,
    startSave,
    saveDone,
    saveFailed,
    setConflict,
    setReadonly,
    setLocked,
    setArchived,
    reset,
    shouldBlockLeave,
    getLeaveMessage,
  }
}
