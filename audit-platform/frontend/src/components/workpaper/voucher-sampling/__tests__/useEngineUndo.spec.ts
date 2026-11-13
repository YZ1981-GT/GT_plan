/**
 * useEngineUndo — 只读不撤销（spec voucher-workflow-linkage-lineage-closure R4.1）
 *
 * 只读另取底稿运行时上下文（归档 / 编辑锁 / 复核身份 / 后台合并），可能在打开后才变：
 * 判定读 ref 的当前值，只读时既不交给宿主删行、也不调后端撤销、也不弹确认框。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref, type ComponentInternalInstance } from 'vue'

const messages = vi.hoisted(() => ({ warning: vi.fn(), success: vi.fn(), confirm: vi.fn() }))
vi.mock('element-plus', () => ({
  ElMessage: { warning: messages.warning, success: messages.success },
  ElMessageBox: { confirm: messages.confirm },
}))

import { useEngineUndo, READONLY_UNDO_MESSAGE, PRELIMINARY_BATCH_LOCKED_MESSAGE } from '../useEngineUndo'
import type { AuditPhase } from '@/composables/useProjectAuditPhase'

function setup(opts: { readonly?: boolean; hostHandles?: boolean; phase?: AuditPhase; entryPhase?: string } = {}) {
  const readonly = ref(!!opts.readonly)
  const undoLastExtraction = vi.fn(async () => true)
  const emitUndoRequest = vi.fn()
  const instance = { vnode: { props: opts.hostHandles ? { onUndoRequest: () => {} } : {} } } as unknown as ComponentInternalInstance
  const { handleUndo } = useEngineUndo({
    instance,
    historyList: ref([{ id: 'log-1', phase: opts.entryPhase ?? 'final', batchId: 'b-1' }]),
    projectPhase: ref<AuditPhase>(opts.phase ?? 'final'),
    undoLastExtraction,
    emitUndoRequest,
    readonly,
  })
  return { readonly, handleUndo, undoLastExtraction, emitUndoRequest }
}

beforeEach(() => {
  messages.warning.mockReset()
  messages.success.mockReset()
  messages.confirm.mockReset()
  messages.confirm.mockResolvedValue('confirm')
})

describe('只读时不撤销', () => {
  it('宿主接了 undo-request：只读不交给宿主，提示原因', async () => {
    const s = setup({ readonly: true, hostHandles: true })
    await s.handleUndo('log-1')
    expect(s.emitUndoRequest).not.toHaveBeenCalled()
    expect(s.undoLastExtraction).not.toHaveBeenCalled()
    expect(messages.warning).toHaveBeenCalledWith(READONLY_UNDO_MESSAGE)
  })

  it('宿主没接：只读不弹确认框、不调后端撤销', async () => {
    const s = setup({ readonly: true })
    await s.handleUndo('log-1')
    expect(messages.confirm).not.toHaveBeenCalled()
    expect(s.undoLastExtraction).not.toHaveBeenCalled()
  })

  it('打开后才变只读（运行时上下文翻转）：按当前值判定', async () => {
    const s = setup({ hostHandles: true })
    await s.handleUndo('log-1')
    expect(s.emitUndoRequest).toHaveBeenCalledTimes(1)
    s.readonly.value = true
    await s.handleUndo('log-1')
    expect(s.emitUndoRequest).toHaveBeenCalledTimes(1)
    expect(messages.warning).toHaveBeenCalledWith(READONLY_UNDO_MESSAGE)
  })
})

describe('可编辑时照旧', () => {
  it('宿主接了：交出批次号与 performUndo，确认后才撤销', async () => {
    const s = setup({ hostHandles: true })
    await s.handleUndo('log-1')
    const payload = s.emitUndoRequest.mock.calls[0][0]
    expect(payload).toMatchObject({ logId: 'log-1', batchId: 'b-1' })
    expect(s.undoLastExtraction).not.toHaveBeenCalled()
    await payload.performUndo()
    expect(s.undoLastExtraction).toHaveBeenCalledWith('log-1')
  })

  it('宿主没接：确认后撤销后端记录', async () => {
    const s = setup()
    await s.handleUndo('log-1')
    expect(messages.confirm).toHaveBeenCalledTimes(1)
    expect(s.undoLastExtraction).toHaveBeenCalledWith('log-1')
  })

  it('年审阶段不撤销预审批次', async () => {
    const s = setup({ hostHandles: true, entryPhase: 'preliminary', phase: 'final' })
    await s.handleUndo('log-1')
    expect(s.emitUndoRequest).not.toHaveBeenCalled()
    expect(messages.warning).toHaveBeenCalledWith(PRELIMINARY_BATCH_LOCKED_MESSAGE)
  })
})
