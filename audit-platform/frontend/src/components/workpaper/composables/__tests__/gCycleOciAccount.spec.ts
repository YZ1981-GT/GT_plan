/**
 * gCycleOciAccount.spec.ts — G8 / G9 / G12 / G14 调整分录里的「其他综合收益」科目码
 *
 * spec: .kiro/specs/formula-fetch-followup-defect-closure/ R1.4（触类旁通）
 *
 * 2026-10-24 前这四处把 OCI 写成 4002（资本公积，G8/G9/G12）或 4104（利润分配，G14）：
 * 下拉选项、手工公允变动分录组、核对表生成的 AJE 都落到错科目，按前缀认领中央调整时
 * 把资本公积 / 利润分配的分录拉进来、真正的 OCI（4003）反而漏掉，OCI 净额也按错码汇总。
 */
import { describe, it, expect } from 'vitest'

import { OCI_ACCOUNT_CODE } from '../mCycleAccountScope'
import { G8_ADJ_ACCOUNT_OPTIONS, isG8RelatedAccount } from '../useG8Adjustment'
import { G9_ADJ_ACCOUNT_OPTIONS, isG9RelatedAccount } from '../useG9Adjustment'
import { G12_ADJ_ACCOUNT_OPTIONS, isG12RelatedAccount } from '../g12AdjStorage'
import { G14_ADJ_ACCOUNT_OPTIONS, isG14RelatedAccount } from '../g14AdjStorage'
import { summarizeG8Adjustment } from '../g8AdjStorage'
import { summarizeG9Adjustment } from '../g9AdjStorage'

const OPTION_LISTS: Array<[string, ReadonlyArray<{ code: string; name: string }>]> = [
  ['G8', G8_ADJ_ACCOUNT_OPTIONS],
  ['G9', G9_ADJ_ACCOUNT_OPTIONS],
  ['G12', G12_ADJ_ACCOUNT_OPTIONS],
  ['G14', G14_ADJ_ACCOUNT_OPTIONS],
]

describe('G 循环调整分录的 OCI 科目码', () => {
  it('OCI = 4003（其他综合收益，M9 口径）', () => {
    expect(OCI_ACCOUNT_CODE).toBe('4003')
  })

  it.each(OPTION_LISTS)('%s 科目选项：「其他综合收益」= 4003，且 4002 / 4104 不叫其他综合收益', (_wp, options) => {
    const oci = options.filter((o) => o.name === '其他综合收益')
    expect(oci.map((o) => o.code)).toEqual([OCI_ACCOUNT_CODE])
    for (const o of options) {
      if (o.code === '4002') expect(o.name).toBe('资本公积')
      if (o.code === '4104') expect(o.name).toContain('利润分配')
    }
  })

  it.each([
    ['G8', isG8RelatedAccount],
    ['G9', isG9RelatedAccount],
    ['G12', isG12RelatedAccount],
    ['G14', isG14RelatedAccount],
  ] as const)('%s 认领中央调整：认 4003 及其明细，不认 4002 资本公积 / 4104 利润分配', (_wp, isRelated) => {
    expect(isRelated('4003')).toBe(true)
    expect(isRelated('4003-01')).toBe(true)
    expect(isRelated('4002')).toBe(false)
    expect(isRelated('4104')).toBe(false)
  })

  it('G8 / G9 汇总的 OCI 净额按 4003 取', () => {
    const rows = [
      { entryType: 'AJE', accountCode: '4003', debitAmount: 0, creditAmount: 70 },
      { entryType: 'AJE', accountCode: '4002', debitAmount: 0, creditAmount: 500 },
    ]
    expect(summarizeG8Adjustment(rows as any).ociNet).toBe(-70)
    expect(summarizeG9Adjustment(rows as any).ociNet).toBe(-70)
  })
})
