import { computed, onUnmounted, ref, watch, type Ref } from 'vue'
import { useAuditContext } from '@/composables/useAuditContext'
import { checkLockStatus } from '@/services/commonApi'
import { eventBus } from '@/utils/eventBus'

export function useConsolWorkspaceAccess(projectId: Ref<string>) {
  const { canEdit, isArchived } = useAuditContext()
  const locked = ref(false)
  const lockStatusKnown = ref(false)
  const lockStatusError = ref('')
  const checkingLock = ref(false)
  let requestSeq = 0

  async function refreshLockStatus(): Promise<void> {
    const pid = projectId.value
    const seq = ++requestSeq
    if (!pid) {
      locked.value = false
      lockStatusKnown.value = false
      lockStatusError.value = ''
      return
    }
    checkingLock.value = true
    lockStatusError.value = ''
    try {
      const response = await checkLockStatus(pid)
      if (seq !== requestSeq || pid !== projectId.value) return
      const payload = response?.data ?? response
      locked.value = Boolean(payload?.locked)
      lockStatusKnown.value = true
    } catch {
      if (seq === requestSeq && pid === projectId.value) {
        lockStatusKnown.value = false
        lockStatusError.value = '无法确认项目锁定状态，合并工作区暂时仅可查看'
      }
    } finally {
      if (seq === requestSeq) checkingLock.value = false
    }
  }

  const readonlyReason = computed(() => {
    if (isArchived.value) return '项目已归档，合并工作区仅可查看'
    if (lockStatusError.value) return lockStatusError.value
    if (checkingLock.value || !lockStatusKnown.value) return '正在确认项目锁定状态，合并工作区暂时仅可查看'
    if (locked.value) return '项目已锁定，合并工作区仅可查看'
    if (!canEdit.value) return '当前角色没有合并工作区编辑权限'
    return ''
  })

  watch(projectId, () => { void refreshLockStatus() }, { immediate: true })
  eventBus.on('consol-lock:detected', refreshLockStatus)
  onUnmounted(() => {
    requestSeq += 1
    eventBus.off('consol-lock:detected', refreshLockStatus)
  })

  return { locked, checkingLock, readonlyReason, canWrite: computed(() => !readonlyReason.value), refreshLockStatus }
}
