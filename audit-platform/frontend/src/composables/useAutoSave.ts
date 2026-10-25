/**
 * useAutoSave — 自动保存/草稿恢复 composable
 *
 * 提供统一的自动保存与草稿恢复能力：
 * - 定时将数据保存到 sessionStorage（关闭标签页后自动清除，防止多标签页 key 冲突）
 * - 挂载时检测草稿并提示恢复
 * - 保存成功后清除草稿
 * - 卸载时清除定时器
 *
 * 用法：
 *   const { hasDraft, clearDraft, saveDraft, restoreDraft } = useAutoSave(
 *     `disclosure_note_${projectId}_${noteSection}`,  // key 中应包含 projectId，防止多项目草稿互相覆盖
 *     () => currentNote.value,
 *     (data) => { currentNote.value = data },
 *   )
 *
 * @module composables/useAutoSave
 * @see R3.8
 */
import { ref, onMounted, onBeforeUnmount, isRef, toValue, type Ref, type MaybeRefOrGetter } from 'vue'
import { ElMessageBox } from 'element-plus'

export interface DraftContext {
  project_id: string
  year: number
  section: string
}

export interface UseAutoSaveOptions {
  /** 自动保存间隔（毫秒），默认 30000（30秒） */
  interval?: number
  /** 是否启用自动保存，默认 true；可传入 Ref<boolean> 动态控制 */
  enabled?: Ref<boolean> | boolean
  /** 动态草稿上下文；提供后会写入 envelope 并在恢复时严格校验 */
  context?: Ref<DraftContext | null | undefined> | DraftContext | null
}

/** 为附注草稿构造稳定的、不会与其他项目/年度/章节冲突的 key。 */
export function buildDisclosureDraftKey(context: DraftContext): string {
  const projectId = String(context.project_id || '').trim()
  const year = Number(context.year) || 0
  const section = String(context.section || '').trim()
  if (!projectId || !year || !section) return 'global'
  return `disclosure_${encodeURIComponent(projectId)}_${year}_${encodeURIComponent(section)}`
}

type AutoSaveKey = MaybeRefOrGetter<string>
type DraftContextSource = UseAutoSaveOptions['context']

function readContext(source: DraftContextSource): DraftContext | null {
  const value = source && isRef(source) ? source.value : source
  if (!value) return null
  const projectId = String(value.project_id || '').trim()
  const year = Number(value.year) || 0
  const section = String(value.section || '').trim()
  if (!projectId || !year || !section) return null
  return { project_id: projectId, year, section }
}

function sameContext(left: DraftContext | null, right: DraftContext | null): boolean {
  return !!left && !!right
    && left.project_id === right.project_id
    && left.year === right.year
    && left.section === right.section
}

export function useAutoSave<T = any>(
  key: AutoSaveKey,
  getData: () => T | null | undefined,
  setData: (data: T) => void,
  options?: UseAutoSaveOptions,
) {
  const interval = options?.interval ?? 30000
  const enabledRef = options?.enabled
  const contextSource = options?.context
  const hasContext = contextSource !== undefined
  const hasDraft = ref(false)
  let timer: ReturnType<typeof setInterval> | null = null

  /** 判断自动保存是否启用 */
  function isEnabled(): boolean {
    if (enabledRef == null) return true
    if (typeof enabledRef === 'boolean') return enabledRef
    return enabledRef.value
  }

  /** 读取当前 key；支持字符串、Ref 和 getter，避免定时器捕获旧上下文。 */
  function currentKey(): string {
    const resolved = toValue(key)
    return typeof resolved === 'string' ? resolved : String(resolved ?? '')
  }

  function currentContext(): DraftContext | null {
    return hasContext ? readContext(contextSource) : null
  }

  function isSameSnapshot(keySnapshot: string, contextSnapshot: DraftContext | null): boolean {
    if (keySnapshot !== currentKey()) return false
    return !hasContext || sameContext(contextSnapshot, currentContext())
  }

  /** 构建完整的 sessionStorage key */
  function storageKey(keySnapshot = currentKey()): string {
    return `autosave_${keySnapshot}`
  }

  /** 读取并校验当前草稿；动态上下文必须与 envelope 严格一致。 */
  function readDraft(keySnapshot = currentKey(), contextSnapshot = currentContext()): any | null {
    try {
      const raw = sessionStorage.getItem(storageKey(keySnapshot))
      if (!raw) return null
      const payload = JSON.parse(raw)
      if (payload?.data == null) return null
      if (hasContext) {
        const payloadContext = readContext(payload.context as DraftContext | null | undefined)
        if (!sameContext(payloadContext, contextSnapshot)) return null
      }
      return payload
    } catch {
      return null
    }
  }

  /** 手动保存草稿到 sessionStorage */
  function saveDraft(): boolean {
    try {
      const context = currentContext()
      if (hasContext && !context) return false
      const data = getData()
      if (data == null) return false
      const payload: Record<string, unknown> = {
        data,
        savedAt: Date.now(),
      }
      if (hasContext) {
        payload.context = context
        payload.version = 1
      }
      sessionStorage.setItem(storageKey(), JSON.stringify(payload))
      hasDraft.value = true
      return true
    } catch {
      return false
    }
  }

  /** 从 sessionStorage 恢复草稿 */
  function restoreDraft(keySnapshot = currentKey(), contextSnapshot = currentContext()): boolean {
    const payload = readDraft(keySnapshot, contextSnapshot)
    if (!payload) return false
    try {
      setData(payload.data)
      return true
    } catch {
      return false
    }
  }

  /** 清除草稿（保存成功后调用） */
  function clearDraft(keySnapshot = currentKey()) {
    sessionStorage.removeItem(storageKey(keySnapshot))
    hasDraft.value = false
  }

  /** 检查是否存在草稿 */
  function checkDraft(keySnapshot = currentKey(), contextSnapshot = currentContext()): boolean {
    return readDraft(keySnapshot, contextSnapshot) != null
  }

  /** 获取草稿保存时间的可读字符串 */
  function getDraftTime(keySnapshot = currentKey(), contextSnapshot = currentContext()): string {
    const payload = readDraft(keySnapshot, contextSnapshot)
    if (!payload?.savedAt) return ''
    try {
      return new Date(payload.savedAt).toLocaleString('zh-CN')
    } catch {
      return ''
    }
  }

  /** 启动定时自动保存 */
  function startTimer() {
    stopTimer()
    timer = setInterval(() => {
      if (isEnabled()) {
        saveDraft()
      }
    }, interval)
  }

  /** 停止定时器 */
  function stopTimer() {
    if (timer) {
      clearInterval(timer)
      timer = null
    }
  }

  // 挂载时：捕获草稿所在上下文；确认框等待期间切换 key/context 时不再恢复或删除旧草稿
  onMounted(async () => {
    const keySnapshot = currentKey()
    const contextSnapshot = currentContext()
    if (checkDraft(keySnapshot, contextSnapshot)) {
      hasDraft.value = true
      const draftTime = getDraftTime(keySnapshot, contextSnapshot)
      const timeHint = draftTime ? `（保存于 ${draftTime}）` : ''
      try {
        await ElMessageBox.confirm(
          `检测到未保存的草稿${timeHint}，是否恢复？`,
          '草稿恢复',
          {
            confirmButtonText: '恢复草稿',
            cancelButtonText: '放弃草稿',
            type: 'info',
          },
        )
        if (isSameSnapshot(keySnapshot, contextSnapshot)) {
          restoreDraft(keySnapshot, contextSnapshot)
        }
      } catch {
        // 用户选择放弃草稿；上下文变化时保留旧草稿，避免误删新章节或旧节点数据。
        if (isSameSnapshot(keySnapshot, contextSnapshot)) {
          clearDraft(keySnapshot)
        }
      }
    }
    startTimer()
  })

  // 卸载时：清除定时器
  onBeforeUnmount(() => {
    stopTimer()
  })

  return {
    /** 是否存在草稿 */
    hasDraft,
    /** 清除草稿（保存成功后调用） */
    clearDraft,
    /** 手动触发保存草稿 */
    saveDraft,
    /** 手动触发恢复草稿 */
    restoreDraft,
  }
}
