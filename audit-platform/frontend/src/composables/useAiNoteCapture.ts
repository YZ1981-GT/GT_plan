/**
 * useAiNoteCapture — 消息选择、复制和项目笔记转存
 *
 * 职责：
 * - 单选/多选 completed assistant messages
 * - 按服务端顺序拼接选中消息文本并复制
 * - 转存为笔记：名称与保存位置由 `ChatNoteSaveDialog` 让用户确认后传入（不静默生成名称）
 * - 失败保留选择状态、名称与位置，可重试
 * - 同一「消息集合 + 名称 + 位置」复用同一 idempotency key，避免双文档；任一变化换新键
 *
 * 2026-10-20 修复（spec ai-chat-adopt-and-note-target-picker）：旧请求体是嵌套
 * `host:{type,id,project_id_assertion,year_assertion}` 且不带 `session_id`，而后端
 * `NoteSaveRequestBody`（extra=forbid）要扁平的 `host_type/host_id/project_id/year` ⇒
 * 转存在任何页面都恒 422；无项目页面则在前端直接拦截。现在请求体与后端模型逐字段对齐
 * （前端 vitest 解析 `doc_ai_chat.py` 对账），会话由服务端按消息反查。
 *
 * Feature: dsh-agent-panel-integration / Task 19
 * Validates: Requirements 8.2, 8.5
 * Properties: 21
 */
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import type { ChatMessage } from '@/composables/usePlatformAiChat'
import type { AiHostRef } from '@/composables/useAiHostContext'
import { readAiChatErrorResponse } from '@/composables/aiChatWireError'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** 笔记名称上限（与对话框输入框 maxlength 同源）。 */
export const NOTE_NAME_MAX_LENGTH = 100

/**
 * 笔记保存位置（镜像后端 `NoteSaveRequestBody.target_project_id / target_folder_id`）。
 *
 * - `host_project`：当前宿主项目的「AI 对话笔记」文件夹（宿主必须绑定项目）
 * - `project`：用户选定项目的「AI 对话笔记」文件夹（首次保存自动创建）
 * - `folder`：用户选定、且有新建权限的知识库文件夹（文档继承文件夹权限）
 */
export type NoteSaveTarget =
  | { kind: 'host_project' }
  | { kind: 'project'; projectId: string }
  | { kind: 'folder'; folderId: string }

export interface NoteSaveRequest {
  /** 用户在对话框里确认的笔记名称 */
  name: string
  target: NoteSaveTarget
}

export interface NoteCaptureResult {
  success: boolean
  /** 成功时的跳转路由 */
  jumpRoute?: string
  /** 成功时服务端回传的实际保存位置（知识库文件夹路径） */
  location?: string
  /** 成功时实际保存的笔记名称 */
  name?: string
  /** 命中既有成功收据（重复提交未产生第二篇） */
  replayed?: boolean
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

  // 最近一次提交的名称 + 位置（失败后保留，重试 / 重开对话框时预填）
  const lastRequest = ref<NoteSaveRequest | null>(null)

  // 当前批次的 idempotency key（同一指纹复用同一 key）
  let currentIdempotencyKey: string | null = null
  // key 对应的保存意图指纹：消息集合 + 名称 + 位置
  let currentFingerprint: string | null = null

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
    lastRequest.value = null
    currentIdempotencyKey = null
    currentFingerprint = null
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
    currentFingerprint = null
    lastError.value = null
    lastNoteName.value = null
    lastRequest.value = null
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

  function fail(errorMessage: string, errorCode?: string): NoteCaptureResult {
    return { success: false, errorMessage, errorCode }
  }

  /**
   * 转存为笔记。名称与位置由调用方（`ChatNoteSaveDialog`）让用户确认后传入 ——
   * Req 8.2：不静默生成时间戳名称；位置不确定时不猜（无项目页面必须显式选择）。
   */
  async function saveAsNote(request?: NoteSaveRequest): Promise<NoteCaptureResult> {
    const req = request ?? lastRequest.value
    if (!req) return fail('请先填写笔记名称并选择保存位置', 'no_target')

    const msgs = selectedMessages.value
    if (msgs.length === 0) return fail('请先选择要转存的 AI 回复')

    // 检查所有消息是否有服务端 ID
    if (!allSelectedHaveServerId.value) {
      return fail('部分回复尚未获取服务端编号，请刷新会话后重试', 'message_id_not_server_issued')
    }

    const host = options.host()
    if (!host || !host.id) {
      return fail('当前页面无法解析 AI 对话上下文，无法保存笔记', 'host_unavailable')
    }

    const name = (req.name ?? '').trim()
    if (!name) return fail('请填写笔记名称', 'empty_name')
    if (name.length > NOTE_NAME_MAX_LENGTH) {
      return fail(`笔记名称不超过 ${NOTE_NAME_MAX_LENGTH} 字`, 'empty_name')
    }

    const target = req.target
    let targetKey = 'host'
    if (target.kind === 'host_project') {
      if (!host.projectId) return fail('当前页面未绑定项目，请选择笔记保存位置', 'no_target')
    } else if (target.kind === 'project') {
      if (!target.projectId) return fail('请选择要保存到的项目', 'no_target')
      targetKey = `project:${target.projectId}`
    } else {
      if (!target.folderId) return fail('请选择要保存到的知识库文件夹', 'no_target')
      targetKey = `folder:${target.folderId}`
    }

    // 保留名称与位置（失败时可重用）
    lastNoteName.value = name
    lastRequest.value = { name, target }

    // 同一保存意图复用同一 idempotency key（重复点击不生成重复文档）；意图变化换新键
    const ids = msgs.map((m) => m.id)
    const fingerprint = `${ids.join(',')}|${name}|${targetKey}`
    if (!currentIdempotencyKey || fingerprint !== currentFingerprint) {
      currentIdempotencyKey = newIdempotencyKey()
      currentFingerprint = fingerprint
    }

    // 请求体与后端 NoteSaveRequestBody 逐字段对齐（extra=forbid；session_id 由服务端反查）
    const payload: Record<string, unknown> = {
      message_ids: ids,
      name,
      host_type: host.type,
      host_id: host.id,
      project_id: host.projectId,
      year: host.year,
      idempotency_key: currentIdempotencyKey,
    }
    if (target.kind === 'project') payload.target_project_id = target.projectId
    if (target.kind === 'folder') payload.target_folder_id = target.folderId

    saving.value = true
    lastError.value = null

    try {
      const res = await fetch('/api/ai-chat/notes', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${getToken()}`,
        },
        body: JSON.stringify(payload),
      })

      if (res.ok) {
        let data: any = {}
        try {
          const body = await res.json()
          data = body?.data ?? body ?? {}
        } catch { /* 2xx 但无 JSON：仍视为成功，只是没有跳转信息 */ }

        // 成功：清除选择状态（提示由调用方按实际位置展示）
        exitSelectionMode()
        return {
          success: true,
          jumpRoute: data?.jump_route || data?.jumpRoute || undefined,
          location: data?.location || undefined,
          name: data?.name || name,
          replayed: Boolean(data?.replayed),
        }
      }

      const { code, message } = await readAiChatErrorResponse(res)

      // receipt_exists 意味着之前已经成功（幂等），视为成功
      if (code === 'receipt_exists') {
        exitSelectionMode()
        return { success: true, name, replayed: true }
      }

      const errorMsg = humanError(code, message)
      lastError.value = errorMsg
      return fail(errorMsg, code)
    } catch {
      const errorMsg = humanError('network_error')
      lastError.value = errorMsg
      return fail(errorMsg, 'network_error')
    } finally {
      saving.value = false
    }
  }

  /**
   * 重试保存：沿用上次的名称与位置；选择集未变时复用同一 idempotency key。
   */
  async function retrySaveAsNote(): Promise<NoteCaptureResult> {
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
    lastRequest,

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
