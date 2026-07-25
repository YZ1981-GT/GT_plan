/**
 * useAdjustmentCentralSync 单元测试
 *
 * spec: workpaper-adjustment-centralization
 * 验证：借贷平衡守卫（P2）、payload 映射与类型（P3）、source_ref/itemId 动态解析（P7）、
 * 空行过滤、approved 锁定错误提示、回流状态。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'

// mock element-plus 消息 + API（vi.hoisted 保证在 vi.mock 工厂前初始化）
const { msg, syncMock, statusMock } = vi.hoisted(() => ({
  msg: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
  syncMock: vi.fn(),
  statusMock: vi.fn(),
}))
vi.mock('element-plus', () => ({ ElMessage: msg }))
vi.mock('@/services/auditPlatformApi', () => ({
  syncAdjustmentFromWorkpaper: (...a: any[]) => syncMock(...a),
  getAdjustmentBySourceRef: (...a: any[]) => statusMock(...a),
}))

import { useAdjustmentCentralSync } from '@/components/workpaper/composables/useAdjustmentCentralSync'

beforeEach(() => {
  syncMock.mockReset()
  statusMock.mockReset()
  msg.success.mockReset(); msg.error.mockReset(); msg.warning.mockReset(); msg.info.mockReset()
})

function makeSync(lineItems: any[], type: 'aje' | 'rje' = 'aje', itemId: string | (() => string) = 'D4-4-rows') {
  return useAdjustmentCentralSync({
    projectId: ref('proj-1'),
    year: ref(2025),
    wpId: ref('wp-1'),
    wpCode: 'D4',
    itemId,
    buildLineItems: () => lineItems,
    buildMeta: () => ({ description: '收入调整', adjustmentType: type }),
  })
}

describe('useAdjustmentCentralSync', () => {
  it('P2 借贷不平衡不调用后端', async () => {
    const s = makeSync([
      { account_name: 'A', debit_amount: 100, credit_amount: 0 },
      { account_name: 'B', debit_amount: 0, credit_amount: 60 },
    ])
    await s.syncToCentral()
    expect(syncMock).not.toHaveBeenCalled()
    expect(msg.error).toHaveBeenCalled()
  })

  it('P3 平衡时调用后端，payload 含正确类型与来源', async () => {
    syncMock.mockResolvedValue({})
    statusMock.mockResolvedValue({ review_status: 'draft' })
    const s = makeSync([
      { account_name: '库存现金', debit_amount: 5000, credit_amount: 0 },
      { account_name: '主营业务收入', debit_amount: 0, credit_amount: 5000 },
    ], 'rje')
    await s.syncToCentral()
    expect(syncMock).toHaveBeenCalledTimes(1)
    const [pid, body] = syncMock.mock.calls[0]
    expect(pid).toBe('proj-1')
    expect(body.adjustment_type).toBe('rje')
    expect(body.wp_id).toBe('wp-1')
    expect(body.item_id).toBe('D4-4-rows')
    expect(body.source_wp_code).toBe('D4')
    expect(body.line_items).toHaveLength(2)
  })

  it('空行（借贷全 0）被过滤后无有效行则不调用后端', async () => {
    const s = makeSync([{ account_name: 'A', debit_amount: 0, credit_amount: 0 }])
    await s.syncToCentral()
    expect(syncMock).not.toHaveBeenCalled()
    expect(msg.info).toHaveBeenCalled()
  })

  it('P7 动态 itemId（getter）参与 source_ref', async () => {
    const s = makeSync([], 'aje', () => 'L1-adj-RJE')
    expect(s.sourceRef()).toBe('wp-1:L1-adj-RJE')
  })

  it('APPROVED_LOCKED 错误给出撤回提示', async () => {
    syncMock.mockRejectedValue({ response: { data: { detail: { error_code: 'APPROVED_LOCKED' } } } })
    const s = makeSync([
      { account_name: '库存现金', debit_amount: 100, credit_amount: 0 },
      { account_name: '主营业务收入', debit_amount: 0, credit_amount: 100 },
    ])
    await s.syncToCentral()
    expect(msg.warning).toHaveBeenCalled()
  })

  it('refreshStatus 拉取回流状态', async () => {
    statusMock.mockResolvedValue({ review_status: 'approved', adjustment_no: 'AJE-001' })
    const s = makeSync([])
    await s.refreshStatus()
    expect(s.centralStatus.value?.review_status).toBe('approved')
  })
})
