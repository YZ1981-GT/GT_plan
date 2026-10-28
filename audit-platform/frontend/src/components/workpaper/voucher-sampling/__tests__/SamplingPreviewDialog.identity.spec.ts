/**
 * SamplingPreviewDialog —— 凭证号不唯一时的勾选与人工增补（spec voucher-identity-writeback-and-audit-phase 任务 9）
 *
 * 凭证号单独不唯一：同号别日、同日别凭证字是别的凭证（四川物流 FY-0003 / ZZ-0003），同一凭证同科目也可能有两笔分录。
 * - 勾选按行本身认：勾一笔不把同号的别的行一起勾上（以前按凭证号）；
 * - 人工增补：凭证号相同且（填了的）日期 / 金额也相同才算列表里已有的那笔；同号多笔请补日期或金额；
 * - 回填模式只有「追加 / 替换本阶段抽凭行」，没有年审禁用。
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import ElementPlus, { ElMessage } from 'element-plus'

import SamplingPreviewDialog from '../SamplingPreviewDialog.vue'
import type { SampledVoucher } from '../../composables/useSamplingAlgorithms'

const LIVE: VueWrapper[] = []
afterEach(() => {
  while (LIVE.length) LIVE.pop()!.unmount()
  vi.restoreAllMocks()
})

function v(over: Partial<SampledVoucher>): SampledVoucher {
  return {
    voucherNo: '0003', voucherDate: '2025-01-07', summary: null, debitAmount: '100.00', creditAmount: null,
    accountCode: '1002', accountName: '银行存款', counterpartAccount: null, counterpartAccountName: null,
    isMultiAccount: false, voucherEntries: [], voucherType: 'FY', accountingPeriod: 1, checkResult: '',
    abnormal: false, remark: '', selected: false, phase: 'final', editTrail: [], ...over,
  }
}

async function mountDialog(vouchers: SampledVoucher[]) {
  const w = mount(SamplingPreviewDialog, {
    props: { visible: true, vouchers, coverageStats: null, fillMode: 'merge', selectedCount: 0, selectedDebitTotal: 0, selectedCreditTotal: 0, phase: 'final' },
    global: { plugins: [ElementPlus] },
    attachTo: document.body,
  })
  LIVE.push(w)
  await flushPromises() // el-dialog 内容在下一拍才渲染
  return w
}

describe('勾选按行本身认', () => {
  it('勾一笔不把同号别凭证字 / 同凭证另一笔一起勾上', async () => {
    const fy = v({ voucherType: 'FY' })
    const zz = v({ voucherType: 'ZZ', debitAmount: '200.00' })
    const fy2 = v({ voucherType: 'FY', lineFp: 'second' })
    const w = await mountDialog([fy, zz, fy2])
    w.findComponent({ name: 'ElTable' }).vm.$emit('selection-change', [fy])
    expect([fy.selected, zz.selected, fy2.selected]).toEqual([true, false, false])
  })
})

describe('打开时表格勾选框跟样本 selected 一致', () => {
  it('默认勾选的行打开时就是勾上的（以前勾选框全空、统计却是全选），同步不回写 selected', async () => {
    const on = v({ selected: true })
    const off = v({ voucherDate: '2025-02-07', selected: false })
    const w = await mountDialog([on, off])
    const table = w.findComponent({ name: 'ElTable' })
    const rows = (table.vm as unknown as { getSelectionRows: () => SampledVoucher[] }).getSelectionRows()
    expect(rows.map(r => r.voucherDate)).toEqual(['2025-01-07'])
    expect([on.selected, off.selected]).toEqual([true, false])
  })
})

describe('人工增补', () => {
  function append(w: VueWrapper, form: Record<string, string>) {
    const vm = w.vm as unknown as { appendForm: Record<string, string>; handleAppendSearch: () => void }
    vm.appendForm = { voucherNo: '', voucherDate: '', debitAmount: '', creditAmount: '', summary: '', ...form }
    vm.handleAppendSearch()
  }

  it('凭证号 + 日期 + 金额相同：只勾选已有那笔，不重复添加', async () => {
    const fy = v({})
    const list = [fy, v({ voucherDate: '2025-02-07' })]
    const w = await mountDialog(list)
    append(w, { voucherNo: '0003', voucherDate: '2025-01-07', debitAmount: '100' })
    expect(list).toHaveLength(2)
    expect(fy.selected).toBe(true)
  })

  it('同号别日：是别的凭证，新增一行（以前按凭证号只勾选已有行）', async () => {
    const list = [v({})]
    const w = await mountDialog(list)
    append(w, { voucherNo: '0003', voucherDate: '2025-03-01', debitAmount: '100' })
    expect(list).toHaveLength(2)
    expect(list[1]).toMatchObject({ voucherNo: '0003', voucherDate: '2025-03-01', selected: true, phase: 'final' })
  })

  it('只给凭证号且列表里同号有多笔：提示补日期或金额，不猜', async () => {
    const warn = vi.spyOn(ElMessage, 'warning')
    const list = [v({}), v({ voucherDate: '2025-02-07' })]
    const w = await mountDialog(list)
    append(w, { voucherNo: '0003' })
    expect(list).toHaveLength(2)
    expect(list.every(x => !x.selected)).toBe(true)
    expect(warn).toHaveBeenCalledWith(expect.stringContaining('请补填日期或金额区分'))
  })
})

describe('回填模式', () => {
  it('只有「追加」与「替换本阶段抽凭行」，旧「合并」显示为追加，不因年审禁用替换', async () => {
    const w = await mountDialog([v({})])
    const radios = w.findAllComponents({ name: 'ElRadio' })
    expect(radios.map(r => r.text())).toEqual(['追加', '替换本阶段抽凭行'])
    expect(radios.every(r => !r.props('disabled'))).toBe(true)
    const group = w.findAllComponents({ name: 'ElRadioGroup' }).find(g => g.text().includes('替换本阶段抽凭行'))
    expect(group?.props('modelValue')).toBe('append')
  })
})
