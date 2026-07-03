/**
 * useReviewDialog — 复核对话 composable
 *
 * 封装：消息 CRUD / SSE 订阅 / 多选状态 / 导出流程 / AI 生成 / 权限 / 关闭确认
 *
 * @see .kiro/specs/audit-review-dialog/design.md
 */
import { ref, computed, onUnmounted, type Ref, type ComputedRef } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'
import { eventBus, type SyncEventPayload } from '@/utils/eventBus'

// ── Types ───────────────────────────────────────────────────────────────────

export type SenderRole = '审计助理' | '现场经理' | '业务合伙人' | '质量控制复核合伙人' | 'EQCR技术复核人'
export type MessageType = 'text' | 'system' | 'quote'
export type ThreadStatus = 'open' | 'closed'

export interface ReviewMessage {
  id: string
  thread_id: string
  sender_id: string
  sender_name: string
  sender_role: SenderRole
  content: string
  message_type: MessageType
  created_at: string
  _status?: 'sending' | 'sent' | 'failed'
  _tempId?: string
}

export interface GtReviewDialogProps {
  wpId: string
  sectionId: string
  sectionLabel?: string
  currentUser: { id: string; name: string; role: SenderRole }
  relatedData?: {
    wpCode?: string
    wpTitle?: string
    auditedData?: Record<string, unknown>
    projectId?: string
    cellValue?: string | number
    cellLabel?: string
    priorValue?: string | number
    selectedText?: string
  }
}

// ── Exported Pure Utility Functions ─────────────────────────────────────────

const WRITE_ROLES: SenderRole[] = ['审计助理', '现场经理', '业务合伙人']
const READ_ONLY_ROLES: SenderRole[] = ['质量控制复核合伙人', 'EQCR技术复核人']

export function buildThreadKey(wpId: string, sectionId: string): string {
  return `${wpId}:${sectionId}`
}

export function getMessageAlignment(message: ReviewMessage, currentUserId: string): 'left' | 'right' {
  return message.sender_id === currentUserId ? 'right' : 'left'
}

export function formatExportText(messages: ReviewMessage[]): string {
  const sorted = [...messages].sort(
    (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
  )
  return sorted
    .map((m) => {
      const d = new Date(m.created_at)
      const hh = String(d.getHours()).padStart(2, '0')
      const mm = String(d.getMinutes()).padStart(2, '0')
      return `[${m.sender_role} ${hh}:${mm}] ${m.content}`
    })
    .join('\n')
}

export function generateItemId(wpCode: string, timestamp: number): string {
  return `${wpCode}-review-record-${timestamp}`
}

export function buildRemarkMetadata(
  exportedBy: string,
  threadId: string,
  messageIds: string[],
): { exported_at: string; exported_by: string; thread_id: string; message_ids: string[] } {
  return {
    exported_at: new Date().toISOString(),
    exported_by: exportedBy,
    thread_id: threadId,
    message_ids: messageIds,
  }
}

export function getRolePermissions(role: SenderRole): { canWrite: boolean; canRead: boolean } {
  if (WRITE_ROLES.includes(role)) return { canWrite: true, canRead: true }
  if (READ_ONLY_ROLES.includes(role)) return { canWrite: false, canRead: true }
  return { canWrite: false, canRead: false }
}

// ── Main Composable ─────────────────────────────────────────────────────────

export function useReviewDialog(props: GtReviewDialogProps) {
  // ─ Panel state
  const isOpen = ref(false)
  const isLoading = ref(false)
  const messages = ref<ReviewMessage[]>([])
  const threadId = ref<string | null>(null)
  const threadStatus = ref<ThreadStatus>('open')
  const dialogTitle = computed(() => props.sectionLabel ? `${props.sectionLabel} 复核对话` : '复核对话')

  // ─ Multi-select state
  const isMultiSelectMode = ref(false)
  const selectedIds = ref<Set<string>>(new Set())
  const lastClickIndex = ref<number>(-1)
  const selectedCount = computed(() => selectedIds.value.size)
  const canExport = computed(() => selectedIds.value.size > 0)

  // ─ Export edit state
  const isExportDialogOpen = ref(false)
  const exportText = ref('')
  const isAiPolishing = ref(false)

  // ─ AI generate state
  const isAiGenerating = ref(false)

  // ─ Permission
  const canWrite = computed(() => WRITE_ROLES.includes(props.currentUser.role))
  const canRead = computed(() => [...WRITE_ROLES, ...READ_ONLY_ROLES].includes(props.currentUser.role))

  // ─ Unread
  const unreadCount = ref(0)

  // ─ Close confirm
  const isCloseConfirmOpen = ref(false)

  // ════════════════════════════════════════════════════════════════════════════
  // 3.1 Message CRUD
  // ════════════════════════════════════════════════════════════════════════════

  async function openDialog(): Promise<void> {
    isLoading.value = true
    isOpen.value = true
    unreadCount.value = 0
    try {
      const { data } = await http.get('/api/review-threads', {
        params: { wp_id: props.wpId, section_id: props.sectionId },
      })
      threadId.value = data.id
      threadStatus.value = data.status as ThreadStatus
      messages.value = data.messages ?? []
    } catch {
      ElMessage.error('加载对话失败')
    } finally {
      isLoading.value = false
    }
  }

  function closeDialog(): void {
    isOpen.value = false
    exitSelectMode()
  }

  async function sendMessage(content: string): Promise<void> {
    if (!content.trim() || !threadId.value) return
    const tempId = crypto.randomUUID()
    const optimistic: ReviewMessage = {
      id: tempId,
      thread_id: threadId.value,
      sender_id: props.currentUser.id,
      sender_name: props.currentUser.name,
      sender_role: props.currentUser.role,
      content,
      message_type: 'text',
      created_at: new Date().toISOString(),
      _status: 'sending',
      _tempId: tempId,
    }
    messages.value.push(optimistic)
    try {
      const { data } = await http.post(`/api/review-threads/${threadId.value}/messages`, {
        content,
        message_type: 'text',
      })
      const idx = messages.value.findIndex((m) => m._tempId === tempId)
      if (idx !== -1) {
        messages.value[idx] = { ...data, _status: 'sent' }
      }
    } catch {
      const idx = messages.value.findIndex((m) => m._tempId === tempId)
      if (idx !== -1) messages.value[idx]._status = 'failed'
    }
  }

  async function retryMessage(tempId: string): Promise<void> {
    const msg = messages.value.find((m) => m._tempId === tempId)
    if (!msg) return
    msg._status = 'sending'
    try {
      const { data } = await http.post(`/api/review-threads/${threadId.value}/messages`, {
        content: msg.content,
        message_type: msg.message_type,
      })
      const idx = messages.value.findIndex((m) => m._tempId === tempId)
      if (idx !== -1) messages.value[idx] = { ...data, _status: 'sent' }
    } catch {
      msg._status = 'failed'
    }
  }

  // ════════════════════════════════════════════════════════════════════════════
  // 3.2 SSE Subscription
  // ════════════════════════════════════════════════════════════════════════════

  function handleSSE(payload: SyncEventPayload): void {
    if ((payload.event_type as string) !== 'review_message.created') return
    const evtThreadId = payload.extra?.thread_id ?? (payload as any).thread_id
    if (!evtThreadId) return
    // Only process matching thread
    if (evtThreadId !== threadId.value) return
    const msgData = payload.extra?.message ?? (payload as any).message
    if (!msgData) return
    // Exclude self (already optimistically added)
    if (msgData.sender_id === props.currentUser.id) return
    if (isOpen.value) {
      messages.value.push(msgData as ReviewMessage)
    } else {
      unreadCount.value++
    }
  }

  eventBus.on('sse:sync-event', handleSSE)
  onUnmounted(() => { eventBus.off('sse:sync-event', handleSSE) })

  // ════════════════════════════════════════════════════════════════════════════
  // 3.3 Multi-select State
  // ════════════════════════════════════════════════════════════════════════════

  function enterSelectMode(): void {
    isMultiSelectMode.value = true
    selectedIds.value = new Set()
    lastClickIndex.value = -1
  }

  function exitSelectMode(): void {
    isMultiSelectMode.value = false
    selectedIds.value = new Set()
    lastClickIndex.value = -1
  }

  function toggleSelect(msgId: string): void {
    const next = new Set(selectedIds.value)
    if (next.has(msgId)) {
      next.delete(msgId)
    } else {
      next.add(msgId)
    }
    selectedIds.value = next
    // Track last click index for shift-select
    const idx = messages.value.findIndex((m) => m.id === msgId)
    if (idx !== -1) lastClickIndex.value = idx
  }

  function shiftSelect(msgId: string): void {
    const currentIdx = messages.value.findIndex((m) => m.id === msgId)
    if (currentIdx === -1) return
    const anchor = lastClickIndex.value >= 0 ? lastClickIndex.value : currentIdx
    const lo = Math.min(anchor, currentIdx)
    const hi = Math.max(anchor, currentIdx)
    const next = new Set(selectedIds.value)
    for (let i = lo; i <= hi; i++) {
      next.add(messages.value[i].id)
    }
    selectedIds.value = next
    lastClickIndex.value = currentIdx
  }

  function selectAll(): void {
    selectedIds.value = new Set(messages.value.map((m) => m.id))
  }

  // ════════════════════════════════════════════════════════════════════════════
  // 3.4 Export Flow
  // ════════════════════════════════════════════════════════════════════════════

  function exportSelected(): void {
    const selected = messages.value.filter((m) => selectedIds.value.has(m.id))
    exportText.value = formatExportText(selected)
    isExportDialogOpen.value = true
  }

  async function aiPolish(): Promise<void> {
    if (isAiPolishing.value) return
    isAiPolishing.value = true
    try {
      const { data } = await http.post(`/api/workpapers/${props.wpId}/review-dialog/ai-generate`, {
        section_id: props.sectionId,
        related_data: props.relatedData ?? {},
        existing_content: exportText.value,
      })
      if (data.generated_text) {
        exportText.value = data.generated_text
      }
    } catch {
      ElMessage.warning('AI服务暂时不可用，请手动编辑')
    } finally {
      isAiPolishing.value = false
    }
  }

  async function saveToReviewRecord(): Promise<void> {
    if (!exportText.value.trim()) return
    const wpCode = props.relatedData?.wpCode ?? props.wpId
    const itemId = generateItemId(wpCode as string, Date.now())
    const remark = buildRemarkMetadata(
      props.currentUser.id,
      threadId.value ?? '',
      [...selectedIds.value],
    )
    try {
      await http.post(`/api/workpapers/${props.wpId}/checklist-responses`, {
        item_id: itemId,
        value: exportText.value,
        remark: JSON.stringify(remark),
      })
      ElMessage.success('已保存到复核记录')
      isExportDialogOpen.value = false
      exitSelectMode()
    } catch {
      ElMessage.error('保存失败，请重试')
    }
  }

  // ════════════════════════════════════════════════════════════════════════════
  // 3.5 AI Generate
  // ════════════════════════════════════════════════════════════════════════════

  async function aiGenerate(targetTextarea: Ref<string>): Promise<void> {
    if (isAiGenerating.value) return
    isAiGenerating.value = true
    try {
      const { data } = await http.post(`/api/workpapers/${props.wpId}/review-dialog/ai-generate`, {
        section_id: props.sectionId,
        related_data: props.relatedData ?? {},
        existing_content: '',
      })
      if (data.generated_text) {
        // If target already has content, the component should confirm override before calling
        targetTextarea.value = data.generated_text
      }
    } catch {
      ElMessage.warning('AI服务暂时不可用，请手动填写')
    } finally {
      isAiGenerating.value = false
    }
  }

  // ════════════════════════════════════════════════════════════════════════════
  // 3.7 Close Confirmation
  // ════════════════════════════════════════════════════════════════════════════

  function handleClose(): void {
    if (messages.value.length === 0) {
      closeDialog()
      return
    }
    isCloseConfirmOpen.value = true
  }

  function confirmClose(): void {
    isCloseConfirmOpen.value = false
    closeDialog()
  }

  function confirmContinue(): void {
    isCloseConfirmOpen.value = false
  }

  function confirmExport(): void {
    isCloseConfirmOpen.value = false
    enterSelectMode()
  }

  // ── Return ────────────────────────────────────────────────────────────────

  return {
    // Panel state
    isOpen,
    isLoading,
    dialogTitle,
    messages,
    threadId,
    threadStatus,
    // Multi-select
    isMultiSelectMode,
    selectedIds,
    selectedCount,
    canExport,
    // Export edit
    isExportDialogOpen,
    exportText,
    isAiPolishing,
    // AI
    isAiGenerating,
    // Permission (3.6)
    canWrite,
    canRead,
    // Unread
    unreadCount,
    // Close confirm
    isCloseConfirmOpen,
    // Methods (3.1)
    openDialog,
    closeDialog,
    sendMessage,
    retryMessage,
    // Methods (3.3)
    enterSelectMode,
    exitSelectMode,
    toggleSelect,
    shiftSelect,
    selectAll,
    // Methods (3.4)
    exportSelected,
    aiPolish,
    saveToReviewRecord,
    // Methods (3.5)
    aiGenerate,
    // Methods (3.7)
    handleClose,
    confirmClose,
    confirmContinue,
    confirmExport,
  }
}
