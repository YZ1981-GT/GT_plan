/**
 * useRowAttachment — 行级附件弹窗管理
 *
 * 处理 GtAProgramConsole / GtEControlTest 的 open-attachment 事件，
 * 弹出 AttachmentDropZone 绑定 wp_id + sheet + row。
 *
 * 锚定 spec workpaper-editor-slimdown Task 6.4
 * Validates: Requirements US-4（底稿证据链 → 附件模块打通）
 */

import { ref, computed } from 'vue'

export interface RowAttachmentPayload {
  wpId: string
  sheetName: string
  rowRef: string
}

export function useRowAttachment() {
  const visible = ref(false)
  const currentPayload = ref<RowAttachmentPayload | null>(null)

  const resourceType = 'workpaper_row'

  const resourceId = computed(() => {
    if (!currentPayload.value) return ''
    const { wpId, sheetName, rowRef } = currentPayload.value
    // rowRef already contains "sheetName:rowId", use wpId:rowRef
    return `${wpId}:${rowRef}`
  })

  function open(payload: RowAttachmentPayload) {
    currentPayload.value = payload
    visible.value = true
  }

  function close() {
    visible.value = false
    currentPayload.value = null
  }

  return {
    visible,
    currentPayload,
    resourceType,
    resourceId,
    open,
    close,
  }
}
