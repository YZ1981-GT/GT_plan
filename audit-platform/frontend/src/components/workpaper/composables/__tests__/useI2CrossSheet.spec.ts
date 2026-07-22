import { describe, it, expect } from 'vitest'
import { ref, nextTick, effectScope } from 'vue'
import { useI2CrossSheet } from '../useI2CrossSheet'

describe('useI2CrossSheet', () => {
  it('未收到 I6 事件时 ready=false 且 isBalanced=false（防假平衡）', () => {
    const scope = effectScope()
    scope.run(() => {
      const map = ref(new Map())
      const { i6LinkageStatus } = useI2CrossSheet(map)
      expect(i6LinkageStatus.value.ready).toBe(false)
      expect(i6LinkageStatus.value.isBalanced).toBe(false)
    })
    scope.stop()
  })

  it('收到 I6 事件后按 VR-I6-01 判定平衡', async () => {
    const scope = effectScope()
    await scope.run(async () => {
      const map = ref(new Map([
        ['I2-1-rows', { remark: JSON.stringify([{ audited: 40, decreaseTransfer: 0 }]) }],
      ]))
      const { i6LinkageStatus } = useI2CrossSheet(map)
      window.dispatchEvent(new CustomEvent('research:expense-updated', {
        detail: { expense: 60, total: 100 },
      }))
      await nextTick()
      expect(i6LinkageStatus.value.ready).toBe(true)
      expect(i6LinkageStatus.value.isBalanced).toBe(true)
    })
    scope.stop()
  })

  it('I2→I1 转入：审定表为 0 时兜底 I2-2 明细', () => {
    const scope = effectScope()
    scope.run(() => {
      const map = ref(new Map([
        ['I2-1-rows', { remark: JSON.stringify([{ decreaseTransfer: 0 }]) }],
        ['I2-2-rows', { remark: JSON.stringify([{ transferToI1: 1234, projectName: 'P1' }]) }],
      ]))
      const { i1TransferAmount, detailTotals } = useI2CrossSheet(map)
      expect(detailTotals.value.transferred).toBe(1234)
      expect(i1TransferAmount.value).toBe(1234)
    })
    scope.stop()
  })
})
