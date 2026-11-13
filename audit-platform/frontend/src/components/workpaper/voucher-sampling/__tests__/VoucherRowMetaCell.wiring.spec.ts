/**
 * VoucherRowMetaCell — 凭证检查表「来源」列挂他稿结论与异常处置（spec voucher-workflow-linkage-lineage-closure R6 / R7）
 *
 * 两个组件各有行为用例（VoucherConclusionTag.spec / VoucherDispositionButton.spec）；这里钉住来源列把它们挂上、
 * 传对行与项目（处置另传锁定：年审阶段锁定的预审行不出处置）。78 个凭证检查宿主都经这一列拿到这两项。
 */
import { describe, expect, it } from 'vitest'
import { shallowMount } from '@vue/test-utils'

import VoucherRowMetaCell from '../VoucherRowMetaCell.vue'

const ROW = { voucherNo: '0003', voucherDate: '2025-01-07', _gt: { vk: JSON.stringify(['2025', '001', '2025-01-07', 'FY', '0003']) } }

describe('来源列', () => {
  it('挂他稿结论：传行与项目', () => {
    const w = shallowMount(VoucherRowMetaCell, { props: { row: ROW, projectId: 'p1', locked: false, year: 2025 } })
    const tag = w.findComponent({ name: 'VoucherConclusionTag' })
    expect(tag.exists()).toBe(true)
    expect(tag.props()).toMatchObject({ row: ROW, projectId: 'p1' })
  })

  it('挂异常处置：传行、项目与锁定', () => {
    const w = shallowMount(VoucherRowMetaCell, { props: { row: ROW, projectId: 'p1', locked: true, year: 2025 } })
    const btn = w.findComponent({ name: 'VoucherDispositionButton' })
    expect(btn.exists()).toBe(true)
    expect(btn.props()).toMatchObject({ row: ROW, projectId: 'p1', locked: true })
  })
})
