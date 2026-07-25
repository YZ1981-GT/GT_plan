/**
 * useAdjustmentCollaboration — 调整分录协作接力（共享 composable）
 *
 * spec: adjustment-collaboration-and-propagation
 *
 * 分录组级协作：转派→知晓→补充明细行→确认→回写推送。
 * 供集中调整页（Adjustments.vue）与被指派人视角复用。
 */
import { ref, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  assignAdjustmentCollaboration,
  getGroupCollaboration,
  getCollaborationInbox,
  acknowledgeCollaboration,
  contributeCollaboration,
  confirmCollaboration,
  rejectCollaboration,
  type AdjCollabLineItem,
} from '@/services/auditPlatformApi'

/** 协作状态中文标签 */
export const COLLAB_STATUS_LABELS: Record<string, string> = {
  pending: '待知晓',
  acknowledged: '已知晓',
  contributed: '已补充',
  confirmed: '已确认',
  rejected: '已退回',
  closed: '已关闭',
}

/** 协作状态 → el-tag type */
export const COLLAB_STATUS_TAG: Record<string, string> = {
  pending: 'info',
  acknowledged: 'warning',
  contributed: 'primary',
  confirmed: 'success',
  rejected: 'danger',
  closed: 'info',
}

export interface CollabInboxItem {
  id: string; entry_group_id: string; status: string; round: number
  initiator_id: string; note?: string | null; updated_at: string | null
}

function unwrap<T>(v: Ref<T> | (() => T) | T): T {
  if (typeof v === 'function') return (v as () => T)()
  if (v && typeof v === 'object' && 'value' in (v as any)) return (v as Ref<T>).value
  return v as T
}

function handleCollabError(e: any, fallback: string): void {
  const detail = e?.response?.data?.detail
  const code = detail?.error_code
  const msgMap: Record<string, string> = {
    APPROVED_LOCKED: '该分录组已复核通过，不可发起协作',
    COLLABORATION_LOCKED: '该分录组存在进行中的协作',
    UNBALANCED: detail?.message || '借贷不平衡，无法提交',
    UNRESOLVED_ACCOUNTS: detail?.message || '存在无法解析的科目，请补全科目编码',
    INVALID_TRANSITION: detail?.message || '当前状态不允许该操作',
    NOT_ASSIGNEE: '只有被指派人可执行该操作',
    NOT_PARTICIPANT: '只有发起人或被指派人可退回',
    NOT_PROJECT_MEMBER: '转派对象必须为项目成员',
  }
  ElMessage.error(code && msgMap[code] ? msgMap[code] : fallback)
}

export interface UseAdjustmentCollaborationOptions {
  projectId: Ref<string> | (() => string) | string
  year: Ref<number> | (() => number) | number
}

export function useAdjustmentCollaboration(opts: UseAdjustmentCollaborationOptions) {
  const inbox = ref<CollabInboxItem[]>([])
  const busy = ref(false)

  const pid = () => unwrap(opts.projectId)

  async function assign(entryGroupId: string, assigneeId: string, note?: string): Promise<boolean> {
    busy.value = true
    try {
      await assignAdjustmentCollaboration(pid(), entryGroupId, {
        assignee_id: assigneeId, year: unwrap(opts.year), note,
      })
      ElMessage.success('已转派给协作者')
      return true
    } catch (e) { handleCollabError(e, '转派失败'); return false } finally { busy.value = false }
  }

  async function acknowledge(cid: string): Promise<boolean> {
    busy.value = true
    try {
      await acknowledgeCollaboration(pid(), cid)
      ElMessage.success('已知晓')
      return true
    } catch (e) { handleCollabError(e, '操作失败'); return false } finally { busy.value = false }
  }

  async function contribute(cid: string, lineItems: AdjCollabLineItem[], note?: string): Promise<boolean> {
    busy.value = true
    try {
      await contributeCollaboration(pid(), cid, { line_items: lineItems, note })
      ElMessage.success('补充已提交')
      return true
    } catch (e) { handleCollabError(e, '补充提交失败'); return false } finally { busy.value = false }
  }

  async function confirm(cid: string): Promise<boolean> {
    busy.value = true
    try {
      await confirmCollaboration(pid(), cid)
      ElMessage.success('已确认')
      return true
    } catch (e) { handleCollabError(e, '确认失败'); return false } finally { busy.value = false }
  }

  async function reject(cid: string, reason: string): Promise<boolean> {
    busy.value = true
    try {
      await rejectCollaboration(pid(), cid, reason)
      ElMessage.success('已退回')
      return true
    } catch (e) { handleCollabError(e, '退回失败'); return false } finally { busy.value = false }
  }

  async function getGroup(entryGroupId: string) {
    try {
      return await getGroupCollaboration(pid(), entryGroupId)
    } catch {
      return { collaboration: null, timeline: [] as any[] }
    }
  }

  async function refreshInbox(): Promise<void> {
    try {
      inbox.value = await getCollaborationInbox(pid())
    } catch {
      inbox.value = []
    }
  }

  return {
    inbox, busy,
    assign, acknowledge, contribute, confirm, reject,
    getGroupCollaboration: getGroup, refreshInbox,
  }
}

export default useAdjustmentCollaboration
