/**
 * I2-8 材料投入 / I2-11 委外研发 / I2-9 研发人员认定 / I2-10 研发人员工时检查接入共享回填函数
 * （spec voucher-identity-writeback-and-audit-phase 任务 12）
 *
 * 通用五条用例见 voucherFillHostHarness（一个样本一行）。另验：回填即保存（原实现只改内存，不点「保存」就丢，抽凭登记里却记着
 * 本底稿抽了这些凭证）、同一凭证抽两次不重复（原实现每次插一行）、金额取样本自己那一栏且红字带符号照记、I2-11 受托方取
 * 辅助核算往来单位（原实现把对方科目编码写进受托方）。I2-9 / I2-10 的行是人员 / 项目月份，表里没有凭证号列（凭证号记在
 * 备注 / 附件索引），旧行认不出是哪笔分录（`noLegacy`）。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ref, type Ref } from 'vue'

vi.mock('@/utils/http', () => ({ default: { get: vi.fn(), put: vi.fn(), post: vi.fn() } }))
vi.mock('element-plus', () => ({
  ElMessage: { info: vi.fn(), success: vi.fn(), error: vi.fn(), warning: vi.fn() },
  ElMessageBox: { confirm: vi.fn(), prompt: vi.fn() },
}))

import { useI2MaterialCheck } from '../useI2MaterialCheck'
import { useI2OutsourceCheck } from '../useI2OutsourceCheck'
import { useI2StaffRowsFill, useI2WorkHourRowsFill } from '../i2SheetRowsFill'
import type { I2MaterialCheckRow } from '../i2MaterialCheckModel'
import type { I2OutsourceCheckRow } from '../i2OutsourceCheckModel'
import type { I2StaffCheckRow } from '../i2StaffCheckModel'
import type { I2WorkHourCheckRow } from '../i2WorkHourModel'
import { resetVoucherFillMocks, sample, voucherFillHostCases, type HostInstance } from './voucherFillHostHarness'

type Inst<R> = HostInstance<R> & { api: any; saves: () => number }

const asItem = (k: string, v: unknown) => ({ item_id: k, conclusion: null, remark: typeof v === 'string' ? v : JSON.stringify(v) })

/**
 * 整页 saveResponse(sheet, { 各项 }) 的宿主（I2 父组件契约）：父组件先改 allResponses 再请求后端（与
 * GtI2DevelopmentExpenditure.saveResponse 相同），组合式函数的 watch 随之重读
 */
function pageHost<R>(code: string, use: (ar: Ref<Map<string, any>>, opts: any) => any) {
  const rowsKey = `${code}-rows`
  return function make(seed?: unknown[]): Inst<R> {
    const responses = ref(new Map<string, any>()) as Ref<Map<string, any>>
    if (seed) responses.value.set(rowsKey, asItem(rowsKey, seed))
    let last: unknown[] = seed ? JSON.parse(JSON.stringify(seed)) : []
    const saveResponse = vi.fn(async (_sheet: string, data: Record<string, unknown>) => {
      for (const [k, v] of Object.entries(data)) responses.value.set(k, asItem(k, v))
      if (rowsKey in data) last = JSON.parse(String(data[rowsKey]))
    })
    const api = use(responses, { saveResponse, projectId: 'proj-1', isReadonly: false })
    return {
      api,
      rows: () => api.rows.value,
      stored: () => last as any[],
      rowSaves: () => saveResponse.mock.calls.filter(c => rowsKey in c[1]).length,
      saves: () => saveResponse.mock.calls.length,
    }
  }
}

/** I2-9 / I2-10：行读写在 i2SheetRowsFill（组件只传上下文），读入由组件的 watch 调 load */
function rowsHost<R>(code: string, use: typeof useI2StaffRowsFill | typeof useI2WorkHourRowsFill) {
  const rowsKey = `${code}-rows`
  return function make(seed?: unknown[]): Inst<R> {
    let last: unknown[] = seed ? JSON.parse(JSON.stringify(seed)) : []
    const saveResponse = vi.fn(async (_sheet: string, data: Record<string, unknown>) => {
      if (rowsKey in data) last = JSON.parse(String(data[rowsKey]))
    })
    const fill = (use as typeof useI2StaffRowsFill)({ projectId: 'proj-1', readonly: false, saveResponse })
    fill.load(seed ? asItem(rowsKey, seed) : undefined)
    // 通用用例按宿主接口名调（voucherFillReady / voucherRowClass）；泛型 R 与具体行类型的处理函数签名不可比，api 用 any
    const api: any = { ...fill, voucherFillReady: fill.ready, voucherRowClass: fill.rowClass }
    return {
      api,
      rows: () => fill.rows.value as unknown as R[],
      stored: () => last as any[],
      rowSaves: () => saveResponse.mock.calls.length,
      saves: () => saveResponse.mock.calls.length,
    }
  }
}

const makeMaterial = pageHost<I2MaterialCheckRow>('I2-8', useI2MaterialCheck)
const makeOutsource = pageHost<I2OutsourceCheckRow>('I2-11', useI2OutsourceCheck)
const makeStaff = rowsHost<I2StaffCheckRow>('I2-9', useI2StaffRowsFill)
const makeWorkHour = rowsHost<I2WorkHourCheckRow>('I2-10', useI2WorkHourRowsFill)

/** 凭证号记在说明里（「凭证 0012 / …」）的行：取出凭证号 */
const noIn = (text: unknown) => /凭证 (\S+)/.exec(String(text ?? ''))?.[1]
const removeById = (inst: HostInstance<any>, id: string) => {
  const api = (inst as Inst<any>).api
  api.removeAt(api.rows.value.findIndex((r: { rowId: string }) => r.rowId === id))
}

beforeEach(resetVoucherFillMocks)

describe('I2-8 研发材料投入检查：抽凭 / 挂凭回填走共享函数', () => {
  voucherFillHostCases<I2MaterialCheckRow>({
    make: makeMaterial,
    idKey: 'rowId',
    view: r => [r.voucherNo, r.counterpartAccount, r.counterpartDetail, r.debitAmount],
    expected: [['0012', '1002/6111', '银行存款/投资收益', 300], ['0014', '多科目', '', 1000]],
    edit: (inst, id) => (inst as Inst<I2MaterialCheckRow>).api.removeRow(id),
    editKey: 'recipient',
    manualRow: { rowId: 'm1', voucherNo: '手-1', projectName: '手工项' },
    oldRow: { voucherNo: '0012', debitAmount: 1000, recipient: '张三' },
    oldRowKept: { recipient: '张三' },
  })

  it('回填即保存（原实现只改内存），借方红字带符号照记，业务内容取摘要', async () => {
    const inst = makeMaterial()
    await inst.api.onEngineFilled({ samples: [sample('fp-r', { debitAmount: '-800.00', summary: '冲销领料' })], phase: 'final', batchId: 'b-1' })
    expect(inst.saves()).toBe(1)
    expect(inst.stored().map(r => [r.voucherNo, r.businessDesc, r.debitAmount])).toEqual([['0012', '冲销领料', -800]])
  })
})

describe('I2-11 委外研发检查：抽凭 / 挂凭回填走共享函数', () => {
  voucherFillHostCases<I2OutsourceCheckRow>({
    make: makeOutsource,
    idKey: 'rowId',
    view: r => [r.voucherNo, r.amount],
    expected: [['0012', 300], ['0014', 1000]],
    edit: (inst, id) => (inst as Inst<I2OutsourceCheckRow>).api.removeRow(id),
    editKey: 'contractNo',
    manualRow: { rowId: 'm1', voucherNo: '手-1', projectName: '手工项' },
    oldRow: { voucherNo: '0012', voucherDate: '2025-03-04', amount: 1000, acceptanceResult: '已验收' },
    oldRowKept: { acceptanceResult: '已验收' },
  })

  it('受托方取辅助核算往来单位（唯一命中才填），不再写对方科目编码；回填即保存', async () => {
    const inst = makeOutsource()
    await inst.api.onEngineFilled({
      samples: [
        sample('fp-1', { partyName: '甲研究院', partyAuxType: '客户' }),
        sample('fp-2', { voucherNo: '0013', partyName: null, partyAmbiguous: true }),
      ],
      phase: 'final', batchId: 'b-1',
    })
    expect(inst.saves()).toBe(1)
    expect(inst.stored().map(r => [r.voucherNo, r.entrustedParty])).toEqual([['0012', '甲研究院'], ['0013', '']])
  })
})

describe('I2-9 研发人员认定检查：抽凭 / 挂凭回填走共享函数', () => {
  voucherFillHostCases<I2StaffCheckRow>({
    make: makeStaff,
    idKey: 'rowId',
    noOf: r => noIn(r.remark),
    view: r => [noIn(r.remark), r.staffName],
    expected: [['0012', '抽凭样本'], ['0014', '抽凭样本']],
    edit: removeById,
    editKey: 'department',
    manualRow: { rowId: 'm1', staffName: '手工人员', remark: '凭证 手-1' },
    oldRow: { staffName: '张三', remark: '凭证 0012 / 2025-03-04', department: '研发一部' },
    oldRowKept: { department: '研发一部' },
    noLegacy: true,
  })

  it('同一凭证抽两次不重复（原实现每次插一行）、回填即保存，备注记凭证号 / 日期 / 摘要', async () => {
    const inst = makeStaff()
    await inst.api.onEngineFilled({ samples: [sample('fp-1', { summary: '研发人员工资' })], phase: 'final', batchId: 'b-1' })
    await inst.api.onEngineFilled({ samples: [sample('fp-1', { summary: '研发人员工资' })], phase: 'final', batchId: 'b-2' })
    expect(inst.saves()).toBeGreaterThanOrEqual(1)
    expect(inst.stored().map(r => [r.staffName, r.remark])).toEqual([['研发人员工资', '凭证 0012 / 2025-03-04 / 研发人员工资']])
  })
})

describe('I2-10 研发人员工时检查：抽凭 / 挂凭回填走共享函数', () => {
  voucherFillHostCases<I2WorkHourCheckRow>({
    make: makeWorkHour,
    idKey: 'rowId',
    noOf: r => noIn(r.attachmentIndex),
    view: r => [noIn(r.attachmentIndex), r.salaryAccrual],
    expected: [['0012', 300], ['0014', 1000]],
    edit: removeById,
    editKey: 'remark',
    manualRow: { rowId: 'm1', staffName: '手工人员', attachmentIndex: '凭证 手-1' },
    oldRow: { staffName: '张三', projectName: '项目A', attachmentIndex: '凭证 0012', allocationBasis: '工时表' },
    oldRowKept: { allocationBasis: '工时表' },
    noLegacy: true,
  })

  it('薪酬计提取样本自己那一栏、红字带符号照记，项目取样本科目名，附件索引记凭证号与日期；回填即保存', async () => {
    const inst = makeWorkHour()
    await inst.api.onEngineFilled({
      samples: [sample('fp-r', { debitAmount: '-120.00', accountName: '开发支出-甲项目' })], phase: 'final', batchId: 'b-1',
    })
    expect(inst.stored().map(r => [r.projectName, r.salaryAccrual, r.attachmentIndex]))
      .toEqual([['开发支出-甲项目', -120, '凭证 0012 / 2025-03-04']])
  })
})
