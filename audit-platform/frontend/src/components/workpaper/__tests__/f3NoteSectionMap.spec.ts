/**
 * F3 附注章节映射 / sync payload / 适用性门禁测试
 */
import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import {
  F3_NOTE_SECTION,
  buildF3SyncPayload,
  orderF3ClassRows,
  resolveF3CurrentStandard,
} from '../composables/f3NoteSectionMap'
import { useF3DisclosureListed } from '../composables/useF3DisclosureListed'
import { useF3DisclosureSoe } from '../composables/useF3DisclosureSoe'
import type { ChecklistResponse } from '../composables/useF3FormData'

describe('f3NoteSectionMap', () => {
  it('listed → 五、36 / soe → 八、36', () => {
    expect(F3_NOTE_SECTION.listed).toBe('五、36')
    expect(F3_NOTE_SECTION.soe).toBe('八、36')
  })

  it('current_standard 解析 consolidated / standalone', () => {
    expect(resolveF3CurrentStandard('listed', [])).toBe('listed_standalone')
    expect(resolveF3CurrentStandard('listed', ['listed_consolidated'])).toBe('listed_consolidated')
    expect(resolveF3CurrentStandard('soe', ['soe_consolidated'])).toBe('soe_consolidated')
    expect(resolveF3CurrentStandard('soe', [])).toBe('soe_standalone')
  })

  it('分类行按附注模板行序：商业承兑 → 银行承兑', () => {
    const ordered = orderF3ClassRows([
      { label: '银行承兑汇票', endAmount: 100, priorAmount: 80 },
      { label: '商业承兑汇票', endAmount: 50, priorAmount: 40 },
    ])
    expect(ordered[0].label).toBe('商业承兑汇票')
    expect(ordered[1].label).toBe('银行承兑汇票')
  })

  it('审定表无数据时仍补齐模板固定两行（0 值）', () => {
    const ordered = orderF3ClassRows([])
    expect(ordered.map((r) => r.label)).toEqual(['商业承兑汇票', '银行承兑汇票'])
    expect(ordered.every((r) => r.endAmount === 0 && r.priorAmount === 0)).toBe(true)
  })

  it('国企 sync payload 指向 八、36 且 sheet 名分流', () => {
    const payload = buildF3SyncPayload(
      'soe',
      'wp-2',
      ['soe_standalone'],
      [{ label: '银行承兑汇票', endAmount: 300, priorAmount: 200 }],
      { label: '合计', endAmount: 300, priorAmount: 200 },
      '注：企业应说明本期已到期未支付的应付票据总金额。',
    )
    expect(payload.section_id).toBe('八、36')
    expect(payload.sheet_name).toBe('F3-note-soe')
    expect(payload.current_standard).toBe('soe_standalone')
    // 缺失的商业承兑行自动补 0，保持模板固定两行
    expect(payload.sub_table_data['应付票据'].map((r) => r.label)).toEqual([
      '商业承兑汇票', '银行承兑汇票', '合计',
    ])
  })

  it('sync payload 指向 五、36 且含合计与附注说明', () => {
    const payload = buildF3SyncPayload(
      'listed',
      'wp-1',
      ['listed_standalone'],
      [
        { label: '银行承兑汇票', endAmount: 100, priorAmount: 80 },
        { label: '商业承兑汇票', endAmount: 50, priorAmount: 40 },
      ],
      { label: '合计', endAmount: 150, priorAmount: 120 },
      '本期末已到期未支付的应付票据总额为0元。',
    )
    expect(payload.section_id).toBe('五、36')
    expect(payload.sheet_name).toBe('F3-note-listed')
    expect(payload.current_standard).toBe('listed_standalone')
    const rows = payload.sub_table_data['应付票据']
    expect(rows).toHaveLength(3)
    expect(rows[0].label).toBe('商业承兑汇票')
    expect(rows[1].label).toBe('银行承兑汇票')
    expect(rows[2]).toMatchObject({ label: '合计', end_amount: 150, prior_amount: 120, is_total: true })
    expect(payload.sub_table_data['_note_texts'][0].text).toContain('已到期未支付')
    // disclosure-table-sync-convergence: 携带源对齐 columns（种类/期末余额/上年年末余额）
    expect(payload.columns).toBeDefined()
    const cols = payload.columns!['应付票据']
    expect(cols[0]).toMatchObject({ key: 'label', label: '种类', is_label: true })
    expect(cols.find((c) => c.key === 'end_amount')?.label).toBe('期末余额')
    expect(cols.find((c) => c.key === 'prior_amount')?.label).toBe('上年年末余额')
  })
})

describe('F3 附注披露适用性门禁（与 F2 同口径）', () => {
  const allResponses = ref(new Map<string, ChecklistResponse>())
  const isReadonly = ref(false)

  it('未配置适用准则时上市/国企页均适用（不再显示不适用空态）', () => {
    const listed = useF3DisclosureListed({
      allResponses, isReadonly, applicableStandards: ref<string[]>([]),
    })
    const soe = useF3DisclosureSoe({
      allResponses, isReadonly, applicableStandards: ref<string[]>([]),
    })
    expect(listed.isApplicable.value).toBe(true)
    expect(soe.isApplicable.value).toBe(true)
  })

  it('配置准则后按 listed / soe 关键字分流', () => {
    const listedOnListed = useF3DisclosureListed({
      allResponses, isReadonly, applicableStandards: ref(['listed_standalone']),
    })
    const listedOnSoe = useF3DisclosureListed({
      allResponses, isReadonly, applicableStandards: ref(['soe_standalone']),
    })
    const soeOnSoe = useF3DisclosureSoe({
      allResponses, isReadonly, applicableStandards: ref(['soe_consolidated']),
    })
    const soeOnListed = useF3DisclosureSoe({
      allResponses, isReadonly, applicableStandards: ref(['listed_consolidated']),
    })
    expect(listedOnListed.isApplicable.value).toBe(true)
    expect(listedOnSoe.isApplicable.value).toBe(false)
    expect(soeOnSoe.isApplicable.value).toBe(true)
    expect(soeOnListed.isApplicable.value).toBe(false)
  })
})
