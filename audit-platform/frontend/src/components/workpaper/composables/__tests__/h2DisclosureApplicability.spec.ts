/**
 * H2 applicable_standards 附注适用性
 */
import { describe, expect, it } from 'vitest'
import {
  parseApplicableStandardsFromMap,
  resolveH2DisclosureVariantFromResponses,
  resolveH2DisclosureVariantFromStandards,
} from '../useH2ApplicableStandards'
import { isH2DisclosureApplicable } from '../h2NoteSectionMap'
import { resolveH2SheetStatus } from '../h2IndexCompletion'

function mapFrom(obj: Record<string, string>): Map<string, any> {
  const m = new Map<string, any>()
  for (const [k, v] of Object.entries(obj)) {
    m.set(k, { item_id: k, remark: v, conclusion: null })
  }
  return m
}

describe('useH2ApplicableStandards', () => {
  it('解析 JSON / 逗号分隔 applicable_standards', () => {
    const m1 = mapFrom({ 'H2-applicable-standards': '["listed_standalone"]' })
    expect(parseApplicableStandardsFromMap(m1)).toEqual(['listed_standalone'])

    const m2 = mapFrom({ applicable_standards: 'soe_standalone,listed_consolidated' })
    expect(parseApplicableStandardsFromMap(m2)).toEqual(['soe_standalone', 'listed_consolidated'])
  })

  it('单方适用时解析附注版本', () => {
    expect(resolveH2DisclosureVariantFromStandards(['listed_standalone'])).toBe('listed')
    expect(resolveH2DisclosureVariantFromStandards(['soe_standalone'])).toBe('soe')
    expect(resolveH2DisclosureVariantFromStandards(['listed_standalone', 'soe_standalone'])).toBeNull()
    expect(isH2DisclosureApplicable('listed', ['soe_standalone'])).toBe(false)
  })

  it('目录完成度：不适用附注标 N/A', () => {
    const m = mapFrom({ 'H2-applicable-standards': '["soe_standalone"]' })
    expect(resolveH2DisclosureVariantFromResponses(m)).toBe('soe')
    expect(resolveH2SheetStatus('H2-disc-L', m).status).toBe('na')
    expect(resolveH2SheetStatus('H2-disc-S', m).status).toBe('pending')
  })
})
