/**
 * D7-7 / D6-5 表单按模板补列、D7-7 期后结转按模板改借方（spec oo-writeback-template-parity-closure R3 批 B2a）。
 *
 * D7-7 模板两区表头：客户名称 · 记账凭证（日期 / 凭证编号 / 业务内容 / 对方科目 / 对方明细科目 / 金额）·
 * 支持性文件 · 核对内容 1~5 · 索引号 · 是否异常 · 备注说明；本期区金额 = 借方 + 贷方，期后结转区只有借方
 * （模板 G34「借方金额」，合同负债期后结转是借方）。原表单只显示 1 个核对项、缺对方明细科目 / 支持性文件 /
 * 索引号 / 备注，期后结转区按贷方存。
 * D6-5 模板 J 列「发生原因（款项性质）」前端原来没有。
 */
import { describe, expect, it, vi } from 'vitest'
import { defineComponent, h, ref, nextTick } from 'vue'
import { mount } from '@vue/test-utils'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import D7VoucherCheckTable from '../d7/D7VoucherCheckTable.vue'
import { postTransferAmount, useD7VoucherCheck } from '../composables/useD7VoucherCheck'
import { createEmptyRow as createD6RpRow, useD6RelatedParty } from '../composables/useD6RelatedParty'

const SAMPLE = {
  rowId: 'r1', customerName: '', date: '', voucherNo: '', businessContent: '', counterAccount: '', counterDetail: '',
  debitAmount: 0, creditAmount: 0, supportDocs: '', checkItems: [false, false, false, false, false],
  indexRef: '', isAbnormal: false, remark: '',
}
const ColStub = defineComponent({
  props: { label: { type: String, default: '' } },
  setup(props, { slots }) {
    return () => h('div', { class: 'col', 'data-label': props.label }, slots.default?.({ row: SAMPLE, $index: 0 }))
  },
})
const TableStub = defineComponent({ setup(_p, { slots }) { return () => h('div', { class: 'tbl' }, slots.default?.()) } })

function labels(block: 'period' | 'post'): string[] {
  const w = mount(D7VoucherCheckTable, {
    props: { rows: [SAMPLE as any], block, isReadonly: false, projectId: 'p1' },
    global: {
      stubs: {
        ElTable: TableStub, ElTableColumn: ColStub, ElInput: true, ElCheckbox: true, ElButton: true,
        WpAmountInput: true, GtIndexChip: true,
      },
    },
  })
  return w.findAll('.col').map((c) => c.attributes('data-label') ?? '')
}

describe('D7-7 表单列与模板一致', () => {
  const common = ['客户名称', '日期', '凭证编号', '业务内容', '对方科目', '对方明细科目']
  const tail = ['支持性文件', '核对内容', '1', '2', '3', '4', '5', '索引号', '是否异常', '备注说明', '']
  it('本期增减变动区：借方 + 贷方两列金额', () => {
    expect(labels('period')).toEqual([...common, '借方金额', '贷方金额', ...tail])
  })
  it('期后结转区：只有借方金额（模板 G34）', () => {
    expect(labels('post')).toEqual([...common, '借方金额', ...tail])
  })
})

describe('D7-7 期后结转按借方存，旧数据迁移', () => {
  it('postTransferAmount：新行取借方，没重新保存过的旧行取 creditAmount', () => {
    expect(postTransferAmount({ debitAmount: 120, creditAmount: 9 })).toBe(120)
    expect(postTransferAmount({ debitAmount: 0, creditAmount: 9 })).toBe(0)
    expect(postTransferAmount({ creditAmount: 300 })).toBe(300)
    expect(postTransferAmount({})).toBe(0)
  })

  it('旧行载入即迁移为 debitAmount，保存时不再带 creditAmount', async () => {
    const saved: Record<string, string> = {}
    const responses = ref(new Map<string, any>([
      ['D7-7-post-rows', { remark: JSON.stringify([{ rowId: 'p1', customerName: '甲公司', creditAmount: 300 }]) }],
      ['D7-7-period-rows', { remark: JSON.stringify([{ rowId: 'q1', debitAmount: 5, creditAmount: 7 }]) }],
    ]))
    const vc = useD7VoucherCheck({
      allResponses: responses as any,
      saveImmediate: vi.fn(),
      debouncedSave: (id: string, d: any) => { saved[id] = d.remark },
      wpId: ref('wp'), projectId: ref('p'),
    })
    expect(vc.postTransferRows.value[0].debitAmount).toBe(300)
    expect(vc.postTransferRows.value[0].creditAmount).toBeUndefined()
    expect(vc.postTransferDebitTotal.value).toBe(300)
    expect(vc.periodChangeRows.value[0]).toMatchObject({ debitAmount: 5, creditAmount: 7 })
    vc.updateCell('post', 'p1', 'remark', '已核')
    await nextTick()
    const row = JSON.parse(saved['D7-7-post-rows'])[0]
    expect(row).toMatchObject({ rowId: 'p1', debitAmount: 300, remark: '已核' })
    expect('creditAmount' in row).toBe(false)
  })
})

describe('D6-5 表单按模板补「发生原因（款项性质）」', () => {
  it('行模型带 transactionReason，载入保留', () => {
    expect(createD6RpRow().transactionReason).toBe('')
    const responses = ref(new Map<string, any>([
      ['D6-5-rows', { remark: JSON.stringify([{ rowId: 'a', partyName: '乙公司', transactionReason: '货款' }]) }],
    ]))
    const rp = useD6RelatedParty({ allResponses: responses as any, saveImmediate: vi.fn(), debouncedSave: vi.fn() } as any)
    expect(rp.rows.value[0].transactionReason).toBe('货款')
  })
  it('表单有该列且可录', () => {
    const src = readFileSync(resolve(__dirname, '../d6/D6TabRelatedParty.vue'), 'utf-8')
    expect(src).toContain('label="发生原因（款项性质）"')
    expect(src).toContain("updateCell(row.rowId, 'transactionReason'")
  })
})
