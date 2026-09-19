/**
 * useF2DetailSheet — importPostPeriodOutbound 期后出库一键取数 单元测试
 *
 * 覆盖：取数填充逻辑 / 名称匹配 / 不覆盖非零 / 只读守卫 / 缺参数守卫
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref, computed } from 'vue'

const mockConfirm = vi.fn().mockResolvedValue('confirm')
const mockWarning = vi.fn()
const mockSuccess = vi.fn()
const mockError = vi.fn()
const mockInfo = vi.fn()

vi.mock('element-plus', () => ({
  ElMessageBox: {
    confirm: (...args: any[]) => mockConfirm(...args),
    prompt: vi.fn().mockResolvedValue({ value: '测试' }),
  },
  ElMessage: {
    warning: (...args: any[]) => mockWarning(...args),
    success: (...args: any[]) => mockSuccess(...args),
    error: (...args: any[]) => mockError(...args),
    info: (...args: any[]) => mockInfo(...args),
  },
}))

vi.mock('../composables/f2LedgerPostOutbound', async (importOriginal) => {
  const actual = await importOriginal() as any
  return {
    ...actual,
    pullPostPeriodOutbound: vi.fn(),
  }
})

import { useF2DetailSheet, type F2DetailRow } from '../composables/useF2DetailSheet'
import { pullPostPeriodOutbound } from '../composables/f2LedgerPostOutbound'
import type { ChecklistResponse } from '../composables/useF2FormData'

const mockPull = pullPostPeriodOutbound as unknown as ReturnType<typeof vi.fn>

function makeConfig(sheetCode = 'F2-4') {
  return computed(() => ({
    sheetCode,
    categoryLabel: '发出商品',
    hasQuantity: true,
    hasPostPeriod: true,
    accountCode: '1406',
  }))
}

function makeRow(id: string, itemName: string, postPeriodAmt = 0, postPeriodQty = 0): F2DetailRow {
  return {
    id,
    itemCode: '',
    supplier: '',
    itemName,
    spec: '',
    unit: '',
    openingQty: 100,
    openingAmt: 10000,
    increaseQty: 50,
    increaseAmt: 5000,
    decreaseQty: 30,
    decreaseAmt: 3000,
    closingQty: 0,
    closingAmt: 0,
    postPeriodQty,
    postPeriodAmt,
    postPeriodUnitPrice: '',
    openingUnitPrice: '',
    increaseUnitPrice: '',
    decreaseUnitPrice: '',
    unitPrice: '',
    aging: {},
    agingTotal: 0,
    qualityStatus: '',
    hasOpenOrder: '',
    orderNo: '',
    salesUnitPrice: '',
  }
}

function makeResponses(rows: F2DetailRow[], sheetCode = 'F2-4'): Map<string, ChecklistResponse> {
  const map = new Map<string, ChecklistResponse>()
  map.set(`${sheetCode}-rows`, {
    item_id: `${sheetCode}-rows`,
    conclusion: null,
    remark: JSON.stringify(rows),
  })
  return map
}

describe('importPostPeriodOutbound', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.spyOn(window, 'dispatchEvent').mockImplementation(() => true)
    mockConfirm.mockResolvedValue('confirm')
  })

  it('只读模式直接返回并提示', async () => {
    const detail = useF2DetailSheet({
      config: makeConfig(),
      allResponses: ref(makeResponses([makeRow('1', '钢材')])),
      isReadonly: ref(true),
      projectId: ref('proj1'),
      year: ref(2025),
    })

    await detail.importPostPeriodOutbound()
    expect(mockWarning).toHaveBeenCalledWith('只读模式，无法取数')
    expect(mockPull).not.toHaveBeenCalled()
  })

  it('缺少 projectId 时提示', async () => {
    const detail = useF2DetailSheet({
      config: makeConfig(),
      allResponses: ref(makeResponses([makeRow('1', '钢材')])),
      isReadonly: ref(false),
      projectId: ref(''),
      year: ref(2025),
    })

    await detail.importPostPeriodOutbound()
    expect(mockWarning).toHaveBeenCalledWith('缺少项目ID或审计年度，无法取期后出库')
  })

  it('缺少 year 时提示', async () => {
    const detail = useF2DetailSheet({
      config: makeConfig(),
      allResponses: ref(makeResponses([makeRow('1', '钢材')])),
      isReadonly: ref(false),
      projectId: ref('proj1'),
      year: ref(0),
    })

    await detail.importPostPeriodOutbound()
    expect(mockWarning).toHaveBeenCalledWith('缺少项目ID或审计年度，无法取期后出库')
  })

  it('pull 返回 error 时弹错误消息', async () => {
    mockPull.mockResolvedValue({ status: 'error', message: '网络异常', entries: [], byName: {}, totalAmount: 0, totalQty: 0, unmatchedCount: 0 })

    const detail = useF2DetailSheet({
      config: makeConfig(),
      allResponses: ref(makeResponses([makeRow('1', '钢材')])),
      isReadonly: ref(false),
      projectId: ref('proj1'),
      year: ref(2025),
    })

    await detail.importPostPeriodOutbound()
    expect(mockError).toHaveBeenCalledWith('网络异常')
  })

  it('pull 返回 empty 时弹 info 消息', async () => {
    mockPull.mockResolvedValue({ status: 'empty', message: '无数据', entries: [], byName: {}, totalAmount: 0, totalQty: 0, unmatchedCount: 0 })

    const detail = useF2DetailSheet({
      config: makeConfig(),
      allResponses: ref(makeResponses([makeRow('1', '钢材')])),
      isReadonly: ref(false),
      projectId: ref('proj1'),
      year: ref(2025),
    })

    await detail.importPostPeriodOutbound()
    expect(mockInfo).toHaveBeenCalledWith('无数据')
  })

  it('匹配成功后填入 postPeriodQty/Amt（名称规范化匹配）', async () => {
    // pull 返回按 normalizeInvName 归集的结果
    mockPull.mockResolvedValue({
      status: 'ok',
      entries: [],
      byName: {
        '钢材': { amount: 5000, qty: 20 },
        '铝材': { amount: 3000, qty: 15 },
      },
      totalAmount: 8000,
      totalQty: 35,
      unmatchedCount: 0,
      message: '',
    })

    const rows = [makeRow('1', '钢材'), makeRow('2', '铝材'), makeRow('3', '铜材')]
    const detail = useF2DetailSheet({
      config: makeConfig(),
      allResponses: ref(makeResponses(rows)),
      isReadonly: ref(false),
      projectId: ref('proj1'),
      year: ref(2025),
    })

    await detail.importPostPeriodOutbound()

    // 确认弹窗被调用
    expect(mockConfirm).toHaveBeenCalled()
    // 钢材和铝材被填入
    const r1 = detail.rows.value.find((r) => r.itemName === '钢材')!
    expect(r1.postPeriodAmt).toBe(5000)
    expect(r1.postPeriodQty).toBe(20)
    const r2 = detail.rows.value.find((r) => r.itemName === '铝材')!
    expect(r2.postPeriodAmt).toBe(3000)
    expect(r2.postPeriodQty).toBe(15)
    // 铜材未匹配，保持0
    const r3 = detail.rows.value.find((r) => r.itemName === '铜材')!
    expect(r3.postPeriodAmt).toBe(0)
    expect(r3.postPeriodQty).toBe(0)
    // 成功消息
    expect(mockSuccess).toHaveBeenCalledWith('已填入 2 项期后出库数据')
  })

  it('不覆盖已有非零值的行', async () => {
    mockPull.mockResolvedValue({
      status: 'ok',
      entries: [],
      byName: {
        '钢材': { amount: 9999, qty: 99 },
      },
      totalAmount: 9999,
      totalQty: 99,
      unmatchedCount: 0,
      message: '',
    })

    // 行已有非零 postPeriodAmt
    const rows = [makeRow('1', '钢材', 1000, 10)]
    const detail = useF2DetailSheet({
      config: makeConfig(),
      allResponses: ref(makeResponses(rows)),
      isReadonly: ref(false),
      projectId: ref('proj1'),
      year: ref(2025),
    })

    await detail.importPostPeriodOutbound()

    // 无可匹配行 → info 提示
    expect(mockInfo).toHaveBeenCalled()
    // 值未被覆盖
    const r = detail.rows.value[0]
    expect(r.postPeriodAmt).toBe(1000)
    expect(r.postPeriodQty).toBe(10)
  })

  it('用户取消确认弹窗时不填入', async () => {
    mockConfirm.mockRejectedValue('cancel')
    mockPull.mockResolvedValue({
      status: 'ok',
      entries: [],
      byName: { '钢材': { amount: 5000, qty: 20 } },
      totalAmount: 5000,
      totalQty: 20,
      unmatchedCount: 0,
      message: '',
    })

    const rows = [makeRow('1', '钢材')]
    const detail = useF2DetailSheet({
      config: makeConfig(),
      allResponses: ref(makeResponses(rows)),
      isReadonly: ref(false),
      projectId: ref('proj1'),
      year: ref(2025),
    })

    await detail.importPostPeriodOutbound()

    // 值未被填入
    expect(detail.rows.value[0].postPeriodAmt).toBe(0)
    expect(mockSuccess).not.toHaveBeenCalled()
  })

  it('调用 pullPostPeriodOutbound 传入正确的 accountCode', async () => {
    mockPull.mockResolvedValue({ status: 'empty', message: '', entries: [], byName: {}, totalAmount: 0, totalQty: 0, unmatchedCount: 0 })

    const detail = useF2DetailSheet({
      config: makeConfig(),
      allResponses: ref(makeResponses([makeRow('1', '钢材')])),
      isReadonly: ref(false),
      projectId: ref('proj1'),
      year: ref(2025),
    })

    await detail.importPostPeriodOutbound()
    expect(mockPull).toHaveBeenCalledWith('proj1', 2025, '1406')
  })
})
