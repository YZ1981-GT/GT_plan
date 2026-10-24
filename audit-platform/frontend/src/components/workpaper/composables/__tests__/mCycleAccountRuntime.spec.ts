/**
 * mCycleAccountRuntime.spec.ts — M 循环科目码运行态行为（spec formula-fetch-followup-defect-closure R1.4）
 *
 * - M8 一般风险准备没有统一标准码：定位不到 / 定位到别的循环 / 多码时不发布、不发请求；
 *   bundle 内嵌（没有主入口 provide）时用 selfLoad 拉到的 render-config 定位结果。
 * - 自身事件过滤按本循环码（M7）或 wpCode（M8）认，不再拿错码比较（错码 = 自己的事件绕回来刷新自己）。
 * - 调整分录净影响只算本科目的分录（M8 原先把「4104 利润分配」算进来；M10 原先把「其他权益工具投资」算进来）。
 * - M3 注销冲减建议分录的科目码：盈余公积 4101 / 资本公积 4002 / 库存股 4201（原先 3101 / 3002 / 4002）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref, effectScope, nextTick } from 'vue'
import { eventBus } from '@/utils/eventBus'

import { useM3FormData } from '../useM3FormData'
import { useM3TreasuryCheck } from '../useM3TreasuryCheck'
import { useM7FormData } from '../useM7FormData'
import { useM7Adjudication } from '../useM7Adjudication'
import { useM8FormData } from '../useM8FormData'
import { useM8Adjudication } from '../useM8Adjudication'
import { useM8Adjustment, type M8AdjustmentEntry } from '../useM8Adjustment'
import { useM10FormData } from '../useM10FormData'
import { useM10Adjustment } from '../useM10Adjustment'
import type { TbSourceCodes } from '../shared/tbSourceCodes'

const { mockPost, mockPut, mockGet, confirmSpy, warningSpy } = vi.hoisted(() => ({
  mockPost: vi.fn(async () => ({ published: true })),
  mockPut: vi.fn(async () => ({})),
  mockGet: vi.fn(async (): Promise<any> => []),
  confirmSpy: vi.fn(async () => 'confirm'),
  warningSpy: vi.fn(),
}))

vi.mock('@/services/apiProxy', () => ({ api: { post: mockPost, put: mockPut, get: mockGet } }))
vi.mock('element-plus', () => ({
  ElMessageBox: { confirm: confirmSpy },
  ElMessage: { success: vi.fn(), error: vi.fn(), warning: warningSpy, info: vi.fn() },
}))

function m8Src(label: string, standard: string[], extra: Partial<TbSourceCodes> = {}): TbSourceCodes {
  return {
    row_code: 'BS-124',
    gross_standard: standard,
    chart_available: true,
    slots: { gross: { key: 'gross', label, standard_codes: standard, found: standard.length > 0 } },
    ...extra,
  }
}

function inScope<T>(fn: () => Promise<T> | T): Promise<T> {
  const scope = effectScope()
  return Promise.resolve(scope.run(fn) as Promise<T>).finally(() => scope.stop())
}

const publishCalls = () => mockPost.mock.calls.filter((c) => String(c[0]).includes('publish-to-tb'))

beforeEach(() => {
  mockPost.mockClear()
  mockPut.mockClear()
  mockGet.mockReset()
  mockGet.mockImplementation(async () => [])
  confirmSpy.mockClear()
  warningSpy.mockClear()
})

describe('M8 发布：定位不到不发布、不拿别的科目顶替', () => {
  it.each([
    ['没有溯源（未注入、未自加载）', null, '未取到'],
    ['别的循环的溯源（嵌入场景注入到宿主的 tbSourceCodes）', m8Src('其他权益工具投资', ['1503']), '未取到'],
    ['本项目没有该科目', m8Src('一般风险准备', []), '没有「一般风险准备」科目'],
    ['科目表未导入', m8Src('一般风险准备', [], { chart_available: false }), '未导入'],
    ['定位到多个标准码', m8Src('一般风险准备', ['4102', '4105']), '多个标准科目'],
  ])('%s ⇒ writebackTB 抛原因、不发请求', async (_title, src, reason) => {
    await inScope(async () => {
      const formData = useM8FormData({ wpId: ref('wp-m8'), projectId: ref('p'), tbSourceCodes: ref(src) })
      await expect(formData.writebackTB(100)).rejects.toThrow(reason)
      expect(publishCalls()).toHaveLength(0)
    })
  })

  it('publishToTb 被拦时直接提示原因：不弹确认、不发请求', async () => {
    await inScope(async () => {
      const formData = useM8FormData({ wpId: ref('wp-m8'), projectId: ref('p'), tbSourceCodes: ref(m8Src('一般风险准备', [])) })
      const adj = useM8Adjudication(formData, ref([]))
      await adj.publishToTb()
      expect(warningSpy).toHaveBeenCalledTimes(1)
      expect(String(warningSpy.mock.calls[0][0])).toContain('不能发布到试算表')
      expect(confirmSpy).not.toHaveBeenCalled()
      expect(publishCalls()).toHaveLength(0)
    })
  })

  it('定位到本科目 ⇒ 确认文案带定位到的码，发布写这个码', async () => {
    await inScope(async () => {
      const formData = useM8FormData({ wpId: ref('wp-m8'), projectId: ref('p'), tbSourceCodes: ref(m8Src('一般风险准备', ['4102'])) })
      const adj = useM8Adjudication(formData, ref([]))
      await adj.publishToTb()
      expect(String(confirmSpy.mock.calls[0][0])).toContain('科目 4102')
      expect(publishCalls()).toHaveLength(1)
      expect((publishCalls()[0][1] as any).writeback_rows[0].account_code).toBe('4102')
    })
  })

  it('bundle 内嵌（无主入口 provide）⇒ 用 selfLoad 拉到的 render-config 定位结果', async () => {
    mockGet.mockImplementation(async (url: string) => {
      if (String(url).includes('/render-config')) {
        return { sheets: [{ sheet_name: '审定表M8-1', html_data: { tb_source_codes: m8Src('一般风险准备', ['4102']) } }] }
      }
      return []
    })
    await inScope(async () => {
      const formData = useM8FormData({ wpId: ref('wp-m8'), projectId: ref('p') })
      expect(formData.accountCode.value).toBe('')
      await formData.loadData()
      expect(formData.accountCode.value).toBe('4102')
      await formData.writebackTB(100)
      expect((publishCalls()[0][1] as any).writeback_rows[0].account_code).toBe('4102')
    })
  })
})

describe('自身事件过滤', () => {
  it('M8 审定表：本底稿事件（带定位码）不回调，别的底稿（M6 利润分配 4104）回调', async () => {
    await inScope(async () => {
      const formData = useM8FormData({ wpId: ref('wp-m8'), projectId: ref('p'), tbSourceCodes: ref(m8Src('一般风险准备', ['4102'])) })
      const adj = useM8Adjudication(formData, ref([]))
      const cb = vi.fn()
      const off = adj.subscribeAdjudicated(cb)
      eventBus.emit('substantive:adjudicated', { wpCode: 'M8', accountCode: '4102', auditedAmount: 1, timestamp: 1 })
      expect(cb).not.toHaveBeenCalled()
      eventBus.emit('substantive:adjudicated', { wpCode: 'M6', accountCode: '4104', auditedAmount: 1, timestamp: 1 })
      expect(cb).toHaveBeenCalledTimes(1)
      off()
    })
  })

  it('M8 调整分录：M8-1 的事件（带定位码）要接住', async () => {
    await inScope(async () => {
      const formData = useM8FormData({ wpId: ref('wp-m8'), projectId: ref('p'), tbSourceCodes: ref(m8Src('一般风险准备', ['4102'])) })
      const adjustment = useM8Adjustment(formData)
      const cb = vi.fn()
      const off = adjustment.subscribeAdjudicated(cb)
      eventBus.emit('substantive:adjudicated', { wpCode: 'M8', accountCode: '4102', auditedAmount: 1, timestamp: 1 })
      expect(cb).toHaveBeenCalledTimes(1)
      eventBus.emit('substantive:adjudicated', { wpCode: 'M6', accountCode: '4104', auditedAmount: 1, timestamp: 1 })
      expect(cb).toHaveBeenCalledTimes(1)
      off()
    })
  })

  it('M7 审定表：本底稿 4301 事件不回调（原先比的是 4201 ⇒ 自己的事件绕回来刷新自己）', async () => {
    await inScope(async () => {
      const formData = useM7FormData({ wpId: ref('wp-m7'), projectId: ref('p') })
      const adj = useM7Adjudication(formData, ref([]))
      const cb = vi.fn()
      const off = adj.subscribeAdjudicated(cb)
      eventBus.emit('substantive:adjudicated', { wpCode: 'M7', accountCode: '4301', auditedAmount: 1, timestamp: 1 })
      expect(cb).not.toHaveBeenCalled()
      eventBus.emit('substantive:adjudicated', { wpCode: 'M3', accountCode: '4201', auditedAmount: 1, timestamp: 1 })
      expect(cb).toHaveBeenCalledTimes(1)
      off()
    })
  })
})

function m8Entry(accountName: string, credit: number): M8AdjustmentEntry {
  return {
    index: 1, description: '', category: '账项调整', reportItem: '', accountName, noteItem: '',
    type: 'AJE', debitAmount: 0, creditAmount: credit, refIndex: '', remark: '',
  }
}

describe('调整分录净影响只算本科目', () => {
  it('M8：「4104 利润分配」不算；「一般风险准备」与带定位码的写法算', async () => {
    await inScope(async () => {
      const formData = useM8FormData({ wpId: ref('wp-m8'), projectId: ref('p'), tbSourceCodes: ref(m8Src('一般风险准备', ['4102'])) })
      const adjustment = useM8Adjustment(formData)
      adjustment.entries.value = [
        m8Entry('4104 利润分配', 1000),
        m8Entry('一般风险准备', 30),
        m8Entry('4102 （客户科目）', 5),
      ]
      await nextTick()
      expect(adjustment.ajeNetAccount.value).toBe(35)
    })
  })

  it('M10：「其他权益工具投资」不算，「其他权益工具」算', async () => {
    await inScope(async () => {
      const formData = useM10FormData({ wpId: ref('wp-m10'), projectId: ref('p') })
      const adjustment = useM10Adjustment(formData)
      adjustment.entries.value = [
        { ...m8Entry('其他权益工具投资', 800) },
        { ...m8Entry('其他权益工具—永续债', 20) },
      ] as any
      await nextTick()
      expect(adjustment.ajeNet4401.value).toBe(20)
    })
  })
})

describe('M3 注销冲减建议分录的科目码', () => {
  it('差额>0 冲减盈余公积 4101 / 贷记库存股 4201；差额<0 增加资本公积 4002 / 借记库存股 4201', async () => {
    await inScope(async () => {
      const formData = useM3FormData({ wpId: ref('wp-m3'), projectId: ref('p') })
      const check = useM3TreasuryCheck(formData)
      check.cancelRows.value = [
        { batchName: 'B1', cancelShares: 0, cancelAmount: 1000, deductCapital: 300, deductReserve: 200, diff: 0, diffHandling: '' },
        { batchName: 'B2', cancelShares: 0, cancelAmount: 100, deductCapital: 80, deductReserve: 50, diff: 0, diffHandling: '' },
      ]
      await nextTick()
      const got = check.suggestedAjeEntries.value.map((e) => [e.accountName, e.accountCode])
      expect(got).toEqual([
        ['盈余公积', '4101'], ['库存股', '4201'],
        ['资本公积', '4002'], ['库存股', '4201'],
      ])
    })
  })
})
