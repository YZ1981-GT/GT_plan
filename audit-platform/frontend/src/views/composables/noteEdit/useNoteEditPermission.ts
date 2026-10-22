/**
 * useNoteEditPermission — 附注编辑器可写态**唯一来源**
 *
 * 对当前项目发判定查询 GET /api/projects/{pid}/disclosure-notes/edit-permission，
 * 输出 status / decision 与派生值。编辑器和子组件的全部写开关、EQCR 开关都取自这里。
 *
 * Feature: partner-manager-edit-permission
 * Requirements: 10.1, 10.2, 10.6
 */
import { ref, computed, watch, onUnmounted, type Ref, type ComputedRef } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'
import { noteEditPermission } from '@/services/apiPaths/report'

// ── 类型 ─────────────────────────────────────────────────────────────────────

export interface NoteEditDecision {
  canEdit: boolean
  reason: string | null
  isEqcr: boolean
}

export type NoteEditStatus = 'pending' | 'ok' | 'failed'

export interface UseNoteEditPermissionOptions {
  projectId: ComputedRef<string> | Ref<string>
  /** 项目是否已归档（来自项目状态） */
  isArchived: ComputedRef<boolean> | Ref<boolean>
  /** 多窗口锁强制只读 */
  forcedReadonly: ComputedRef<boolean> | Ref<boolean>
}

export interface UseNoteEditPermissionReturn {
  status: Ref<NoteEditStatus>
  decision: Ref<NoteEditDecision | null>

  /** 能编辑附注（查询成功 ∧ canEdit ∧ 未归档） */
  canWrite: ComputedRef<boolean>
  /** 能编辑且未被多窗口锁强制只读 */
  canWriteLocked: ComputedRef<boolean>
  /** 显示「📋 只读副本」标识：查询成功且判为 EQCR */
  showReadonlyBadge: ComputedRef<boolean>
  /** 显示非 EQCR 才显示的入口：查询成功且非 EQCR */
  showNonEqcrEntries: ComputedRef<boolean>
  /** 禁用原因（只给一条当前成立的原因） */
  disabledReason: ComputedRef<string>

  /** 等到当前项目得出结论或失败 */
  ready: () => Promise<void>
  /** 写请求被拒后标记为不可写（同步生效） */
  markRejected: () => void
  /** 重新发起判定查询 */
  refresh: () => void
}

// ── 常量 ─────────────────────────────────────────────────────────────────────

const QUERY_TIMEOUT = 15_000
const MSG_PENDING = '正在确认编辑权限…'
const MSG_FAILED = '无法确认编辑权限'
const MSG_FAILED_WITH_READONLY = '无法确认编辑权限，已按只读打开'
const MSG_ARCHIVED = '项目已归档，无法编辑'
const MSG_FORCED_READONLY = '他人正在编辑，当前为只读'

// ── 判断取消（去重 / 卸载 / 换项目）─────────────────────────────────────────

function isCancellation(err: unknown): boolean {
  if (!err) return false
  // axios.isCancel
  if (typeof err === 'object' && err !== null && '__CANCEL__' in err) return true
  // AbortController signal
  if (err instanceof DOMException && err.name === 'AbortError') return true
  // axios cancel
  if (typeof err === 'object' && err !== null && 'message' in err) {
    const msg = (err as { message?: string }).message
    if (msg === 'canceled' || msg === 'note-edit-readonly') return true
  }
  return false
}

// ── composable ──────────────────────────────────────────────────────────────

export function useNoteEditPermission(
  options: UseNoteEditPermissionOptions,
): UseNoteEditPermissionReturn {
  const { projectId, isArchived, forcedReadonly } = options

  const status = ref<NoteEditStatus>('pending')
  const decision = ref<NoteEditDecision | null>(null)
  // 写请求被拒后 markRejected 置 true，refresh 清除
  const rejected = ref(false)

  // 序号，每次 refresh 递增；只采用最新序号的结论
  let seq = 0
  let abortController: AbortController | null = null

  // ready() 等待列表
  let readyResolvers: Array<() => void> = []

  function resolveReady() {
    const list = readyResolvers
    readyResolvers = []
    list.forEach((r) => r())
  }

  async function refresh() {
    // abort 上一次
    if (abortController) {
      abortController.abort()
      abortController = null
    }
    rejected.value = false

    const pid = typeof projectId === 'object' && 'value' in projectId ? projectId.value : ''
    if (!pid) {
      status.value = 'pending'
      decision.value = null
      return
    }

    seq += 1
    const mySeq = seq
    const myPid = pid

    status.value = 'pending'
    decision.value = null

    const ac = new AbortController()
    abortController = ac

    try {
      const res = await http.get(noteEditPermission.query(myPid), {
        _silent: true,
        _dedupe: false,
        timeout: QUERY_TIMEOUT,
        signal: ac.signal,
      } as any)

      // 只采用「项目 = 当前项目 且 序号 = 最新」的结论
      const currentPid = typeof projectId === 'object' && 'value' in projectId ? projectId.value : ''
      if (myPid !== currentPid || mySeq !== seq) return

      const data = res?.data ?? res
      // 校验响应
      if (
        typeof data !== 'object' ||
        data === null ||
        typeof data.can_edit !== 'boolean' ||
        typeof data.is_eqcr !== 'boolean'
      ) {
        handleFailure('响应格式不完整')
        return
      }
      if (!data.can_edit && !data.reason) {
        handleFailure('不能编辑但未返回原因')
        return
      }

      status.value = 'ok'
      decision.value = {
        canEdit: data.can_edit,
        reason: data.reason ?? null,
        isEqcr: data.is_eqcr,
      }
      resolveReady()
    } catch (err: unknown) {
      const currentPid = typeof projectId === 'object' && 'value' in projectId ? projectId.value : ''
      if (myPid !== currentPid || mySeq !== seq) return
      if (isCancellation(err)) return

      // 403: append backend reason
      let backendReason = ''
      if (typeof err === 'object' && err !== null) {
        const axErr = err as any
        if (axErr.response?.status === 403) {
          const respData = axErr.response?.data
          if (typeof respData === 'string') {
            backendReason = respData
          } else if (respData?.message) {
            backendReason = respData.message
          } else if (respData?.data && typeof respData.data === 'string') {
            backendReason = respData.data
          }
        }
      }
      handleFailure(backendReason)
    }

    function handleFailure(reason: string) {
      const currentPid = typeof projectId === 'object' && 'value' in projectId ? projectId.value : ''
      if (myPid !== currentPid || mySeq !== seq) return

      status.value = 'failed'
      decision.value = null
      const msg = reason
        ? `${MSG_FAILED_WITH_READONLY}（${reason}）`
        : MSG_FAILED_WITH_READONLY
      ElMessage.warning(msg)
      resolveReady()
    }
  }

  function markRejected() {
    rejected.value = true
  }

  function ready(): Promise<void> {
    if (status.value !== 'pending') return Promise.resolve()
    return new Promise<void>((resolve) => {
      readyResolvers.push(resolve)
    })
  }

  // ── 派生值 ──────────────────────────────────────────────────────────────

  const canWrite = computed(() => {
    if (rejected.value) return false
    return status.value === 'ok' && !!decision.value?.canEdit && !isArchived.value
  })

  const canWriteLocked = computed(() => {
    return canWrite.value && !forcedReadonly.value
  })

  const showReadonlyBadge = computed(() => {
    return status.value === 'ok' && !!decision.value?.isEqcr
  })

  const showNonEqcrEntries = computed(() => {
    return status.value === 'ok' && !decision.value?.isEqcr
  })

  const disabledReason = computed(() => {
    // 优先级：pending → failed → 判定不能编辑 → 归档 → 多窗口锁
    if (status.value === 'pending') return MSG_PENDING
    if (status.value === 'failed') return MSG_FAILED
    if (status.value === 'ok' && decision.value && !decision.value.canEdit) {
      return decision.value.reason || MSG_FAILED
    }
    if (isArchived.value) return MSG_ARCHIVED
    if (forcedReadonly.value) return MSG_FORCED_READONLY
    return ''
  })

  // ── 自动查询 ────────────────────────────────────────────────────────────

  watch(
    () => (typeof projectId === 'object' && 'value' in projectId ? projectId.value : ''),
    () => { refresh() },
    { immediate: true },
  )

  onUnmounted(() => {
    if (abortController) {
      abortController.abort()
      abortController = null
    }
    resolveReady()
  })

  return {
    status,
    decision,
    canWrite,
    canWriteLocked,
    showReadonlyBadge,
    showNonEqcrEntries,
    disabledReason,
    ready,
    markRejected,
    refresh,
  }
}
