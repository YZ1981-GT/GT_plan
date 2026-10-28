/**
 * 抽凭引擎的撤销流程（spec voucher-identity-writeback-and-audit-phase 任务 9，ADR-VK-08，需求 4.6 / 6.3）
 *
 * - 年审阶段不撤销预审批次（预审行只读、不可删；后端同样以 409 拒绝）；
 * - 宿主接了 `undo-request`（接入共享回填函数）：把 {logId, batchId, performUndo} 交给宿主，宿主确认、删行，
 *   确认后调 performUndo 才真正撤销；
 * - 宿主没接：先确认，再只撤销后端记录，提示语如实说明底稿行没有自动删除。
 */
import type { ComponentInternalInstance, Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { AuditPhase } from '@/composables/useProjectAuditPhase'
import type { UndoRequestPayload } from '../composables/shared/voucherCheckFill'

interface HistoryEntryLike {
  id: string
  phase?: string | null
  batchId?: string | null
}

export const PRELIMINARY_BATCH_LOCKED_MESSAGE =
  '该批次是预审抽凭，年审阶段预审行只读，不能撤销；确需撤销请先由项目经理把审计阶段改回预审'

export function useEngineUndo(opts: {
  instance: ComponentInternalInstance | null
  historyList: Readonly<Ref<readonly HistoryEntryLike[]>>
  projectPhase: Readonly<Ref<AuditPhase>>
  undoLastExtraction: (logId: string) => Promise<boolean>
  emitUndoRequest: (payload: UndoRequestPayload) => void
}) {
  /** 宿主是否接了 undo-request（模板里 @undo-request 编译成 vnode prop onUndoRequest） */
  function hostHandlesUndo(): boolean {
    const p = opts.instance?.vnode.props as Record<string, unknown> | null | undefined
    return !!p && (p.onUndoRequest != null || p['onUndo-request'] != null)
  }

  async function handleUndo(logId: string): Promise<void> {
    const entry = opts.historyList.value.find(e => e.id === logId)
    if (entry?.phase === 'preliminary' && opts.projectPhase.value === 'final') {
      ElMessage.warning(PRELIMINARY_BATCH_LOCKED_MESSAGE)
      return
    }
    const performUndo = () => opts.undoLastExtraction(logId)
    if (hostHandlesUndo()) {
      opts.emitUndoRequest({ logId, batchId: entry?.batchId ?? null, performUndo })
      return
    }
    try {
      await ElMessageBox.confirm(
        '撤销会把这次抽凭记录标为已撤销，已抽排除与抽样登记随之撤销。本底稿还没有接入按批次删行，底稿里这次填入的行需要手工删除。确定撤销吗？',
        '撤销抽凭',
        { type: 'warning', confirmButtonText: '确定撤销', cancelButtonText: '取消' },
      )
    } catch {
      return
    }
    if (await performUndo()) ElMessage.success('已撤销抽凭记录；底稿里这次填入的行没有自动删除，请手工删除')
  }

  return { handleUndo, hostHandlesUndo }
}
