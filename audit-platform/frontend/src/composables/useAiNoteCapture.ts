/**
 * useAiNoteCapture — 消息选择、复制和项目笔记转存
 *
 * 职责：
 * - 单选/多选 completed assistant messages
 * - 按服务端顺序拼接选中消息文本并复制
 * - 转存为项目笔记（ElMessageBox.prompt 确认名称 + idempotency key）
 * - 失败保留选择状态与名称，可重试
 * - 重复点击复用同一 idempotency key，避免双文档
 *
 * Feature: dsh-agent-panel-integration / Task 19
 * Validates: Requirements 8.2, 8.5
 * Properties: 21
 */
import { ref, computed } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import type { ChatMessage } from '@/composables/usePlatformAiChat'
import type { AiHostRef } from '@/composables/useAiHostContext'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface NoteCaptureResult {
  success: boolean
  /** 成功时的跳转路由 */
  jumpRoute?: string
  /** 失败原因（中文） */
  errorMessage?: string
  /** 失败错误码 */
  errorCode?: string
}

export interface UseAiNoteCaptureOptions {
  /** 当前消息列表引用（按服务端顺序） */
  messages: () => ChatMessage[]
  /** 当前宿主引用 */
  host: () => AiHostRef | null
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function newIdempotencyKey(): string {
  const c = globalThis.crypto as Crypto | undefined
  if (c && typeof c.randomUUID === 'function') return c.randomUUID()
  const bytes = new Uint8Array(16)
  if (c && typeof c.getRandomValues === 'function') {
    c.getRandomValues(bytes)
  } else {
    for (let i = 0; i < 16; i++) bytes[i] = Math.floor(Math.random() * 256)
  }
  bytes[6] = (bytes[6] & 0x0f) | 0x40
  bytes[8] = (bytes[8] & 0x3f) | 0x80
  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('')
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
}

const SERVER_MESSAGE_ID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

function isServerMessageId(id: string): boolean {
  return SERVER_MESSAGE_ID_RE.test(id)
}

function getToken(): string {
  try {
    const authStore = useAuthStore()
    return authStore.token || ''
  } catch {
    return ''
  }
}

// ---------------------------------------------------------------------------
// 错误码 → 中文映射
// ---------------------------------------------------------------------------

const ERROR_MESSAGES: Record<string, string> = {
  access_denied: '没有保存笔记的权限，请联系管理员',
  host_context_mismatch: '当前页面上下文已变更，请刷新页面后重试',
  message_not_found: '选中的消息已过期或不存在，请刷新会话',
  receipt_exists: '该笔记已保存成功，无需重复操作',
  rate_limited: '操作过于频繁，请稍后再试',
  network_error: '网络异常，笔记未保存成功',
}

function humanError(code?: string, fallback?: string): string {
  if (code && ERROR_MESSAGES[code]) return ERROR_MESSAGES[code]
  return fallback || '笔记保存失败，请稍后重试'
}

// ---------------------------------------------------------------------------
// Composable
// ---------------------------------------------------------------------------

export function useAiNoteCapture(options: UseAiNoteCaptureOptions) {
  // 选中的消息 ID 集合
  const selectedIds = ref<Set<string>>(new Set())

  // 选择模式是否激活
  const selectionMode = ref(false)

  // 保存中状态
  const saving = ref(false)

  // 最近一次保存失败的错误信息（用于重试提示）
  const lastError = ref<string | null>(null)

  // 最近一次使用的笔记名称（失败后保留，重试时预填）
  const lastNoteName = ref<string | null>(null)

  // 当前批次的 idempotency key（重复点击复用同一 key）
  let currentIdempotencyKey: string | null = null

  // ---------------------------------------------------------------------------
  // 可选消息（仅 completed assistant）
  // ---------------------------------------------------------------------------

  const selectableMessages = computed<ChatMessage[]>(() => {
    return options.messages().filter(
      (m) => m.role === 'assistant' && m.status === 'completed',
    )
  })

  const hasSelectableMessages = computed(() => selectableMessages.value.length > 0)

  const selectedMessages = computed<ChatMessage[]>(() => {
    const msgs = options.messages()
    // 按原始顺序（服务端顺序）过滤选中项
    return msgs.filter((m) => selectedIds.value.has(m.id))
  })

  const selectedCount = computed(() => selectedIds.value.size)

  const hasSelection = computed(() => selectedIds.value.size > 0)

  // 是否所有选中消息都有服务端 ID（只有这些才能转存）
  const allSelectedHaveServerId = computed<boolean>(() => {
    return selectedMessages.value.every((m) => isServerMessageId(m.id))
  })

  // ---------------------------------------------------------------------------
  // Selection operations
  // ---------------------------------------------------------------------------

  function enterSelectionMode() {
    selectionMode.value = true
    lastError.value = null
  }

  function exitSelectionMode() {
    selectionMode.value = false
    selectedIds.value = new Set()
    lastError.value = null
    lastNoteName.value = null
    currentIdempotencyKey = null
  }

  function toggleMessage(messageId: string) {
    const msg = options.messages().find((m) => m.id === messageId)
    if (!msg || msg.role !== 'assistant' || msg.status !== 'completed') return

    const next = new Set(selectedIds.value)
    if (next.has(messageId)) {
      next.delete(messageId)
    } else {
      next.add(messageId)
    }
    selectedIds.value = next

    // 选择变化时重新生成 idempotency key（新的选择集 = 新的保存意图）
    currentIdempotencyKey = null
    lastError.value = null
  }

  function selectAll() {
    const ids = new Set<string>()
    for (const m of selectableMessages.value) {
      ids.add(m.id)
    }
    selectedIds.value = ids
    currentIdempotencyKey = null
    lastError.value = null
  }

  function clearSelection() {
    selectedIds.value = new Set()
    currentIdempotencyKey = null
    lastError.value = null
    lastNoteName.value = null
  }

  // ---------------------------------------------------------------------------
  // Copy（按服务端顺序拼接选中消息文本）
  // ---------------------------------------------------------------------------

  async function copySelected(): Promise<boolean> {
    const msgs = selectedMessages.value
    if (msgs.length === 0) return false

    // 按原始列表顺序拼接（messages 本身就是服务端顺序）
    const text = msgs.map((m) => m.text).join('\n\n---\n\n')

    try {
      await navigator.clipboard.writeText(text)
      ElMessage.success(`已复制 ${msgs.length} 条 AI 回复`)
      return true
    } catch {
      // fallback: textarea copy
      try {
        const textarea = document.createElement('textarea')
        textarea.value = text
        textarea.style.position = 'fixed'
        textarea.style.opacity = '0'
        document.body.appendChild(textarea)
        textarea.select()
        document.execCommand('copy')
        document.body.removeChild(textarea)
        ElMessage.success(`已复制 ${msgs.length} 条 AI 回复`)
        return true
      } catch {
        ElMessage.error('复制失败，请手动选择文本复制')
        return false
      }
    }
  }

  // ---------------------------------------------------------------------------
  // Note save（转存为项目笔记）
  // ---------------------------------------------------------------------------

  async function saveAsNote(): Promise<NoteCaptureResult> {
    const msgs = selectedMessages.value
    if (msgs.length === 0) {
      return { success: false, errorMessage: '请先选择要转存的 AI 回复' }
    }

    // 检查所有消息是否有服务端 ID
    if (!allSelectedHaveServerId.value) {
      return {
        success: false,
        errorMessage: '部分回复尚未获取服务端编号，请刷新会话后重试',
        errorCode: 'message_id_not_server_issued',
      }
    }

    const host = options.host()
    if (!host || !host.projectId) {
      return {
        success: false,
        errorMessage: '当前页面无项目上下文，无法保存项目笔记',
        errorCode: 'host_unavailable',
      }
    }

    // 弹出名称确认对话框（Req 8.2：必须确认名称，不静默生成时间戳）
    let noteName: string
    try {
      const { value } = await ElMessageBox.prompt(
        '请输入笔记名称，用于在项目知识库中标识本条记录',
        '保存为项目笔记',
        {
          confirmButtonText: '保存',
          cancelButtonText: '取消',
          inputValue: lastNoteName.value || '',
          inputPlaceholder: '例如：XX科目审计问答记录',
          inputValidator: (v: string) => {
            if (!v || !v.trim()) return '笔记名称不能为空'
            if (v.trim().length > 100) return '名称不超过 100 字'
            return true
          },
        },
      ) as any
      noteName = (value as string).trim()
    } catch {
      // 用户取消
      return { success: false, errorMessage: '已取消保存' }
    }

    // 保留名称（失败时可重用）
    lastNoteName.value = noteName

    // 复用同一 idempotency key（重复点击不生成重复文档）
    if (!currentIdempotencyKey) {
      currentIdempotencyKey = newIdempotencyKey()
    }

    saving.value = true
    lastError.value = null

    try {
      const res = await fetch('/api/ai-chat/notes', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${getToken()}`,
        },
        body: JSON.stringify({
          message_ids: msgs.map((m) => m.id),
          name: noteName,
          host: {
            type: host.type,
            id: host.id,
            project_id_assertion: host.projectId,
            year_assertion: host.year,
          },
          idempotency_key: currentIdempotencyKey,
        }),
      })

      if (res.ok) {
        const body = await res.json()
        const data = body?.data ?? body
        const jumpRoute = data?.jump_route || data?.jumpRoute || null

        // 成功：清除选择状态
        ElMessage.success('笔记保存成功')
        exitSelectionMode()

        return { success: true, jumpRoute }
      }

      // 处理失败
      let code: string | undefined
      let message: string | undefined
      try {
        const body = await res.json()
        const detail = body?.detail ?? body?.data ?? body
        code = detail?.code || detail?.error_code
        message = detail?.message
      } catch { /* non-JSON */ }

      // receipt_exists 意味着之前已经成功（幂等），视为成功
      if (code === 'receipt_exists') {
        ElMessage.success('笔记已保存（之前的操作已成功）')
        exitSelectionMode()
        return { success: true }
      }

      const errorMsg = humanError(code, message)
      lastError.value = errorMsg
      return { success: false, errorMessage: errorMsg, errorCode: code }
    } catch {
      const errorMsg = humanError('network_error')
      lastError.value = errorMsg
      return { success: false, errorMessage: errorMsg, errorCode: 'network_error' }
    } finally {
      saving.value = false
    }
  }

  /**
   * 重试保存（使用之前保留的名称和 idempotency key）
   * 如果之前没有 key（选择变了），会生成新 key
   */
  async function retrySaveAsNote(): Promise<NoteCaptureResult> {
    // 直接调用 saveAsNote — 它会用已保留的 lastNoteName 和 currentIdempotencyKey
    return saveAsNote()
  }

  // ---------------------------------------------------------------------------
  // Return
  // ---------------------------------------------------------------------------

  return {
    // State
    selectionMode,
    selectedIds,
    selectedMessages,
    selectedCount,
    hasSelection,
    hasSelectableMessages,
    allSelectedHaveServerId,
    saving,
    lastError,
    lastNoteName,

    // Actions
    enterSelectionMode,
    exitSelectionMode,
    toggleMessage,
    selectAll,
    clearSelection,
    copySelected,
    saveAsNote,
    retrySaveAsNote,
  }
}
