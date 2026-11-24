/**
 * 逐 amount region 确认 —— buildRegionsFromDecisions 纯函数判据。
 *
 * 后端契约（custom_template_ingestion._validate_authority_manifest）：
 *   regions 非空数组；成员 stable_id 非空唯一；measure_kind 在闭集内；
 *   ratio 必须带 ratio_scale（fraction | percent_points）；非 ratio 不得带
 *   ratio_scale；amount 必须带 unit（yuan|qian|wan）+ divisor（1|1000|10000）。
 * 本文件逐条对拍 —— 前端组装器产出的 regions 必须能原样过后端校验。
 */
import { describe, expect, it } from 'vitest'
import {
  buildRegionsFromDecisions,
  REGION_ALLOWED_KINDS,
  REGION_ALLOWED_UNITS,
  type RegionDecision,
} from '@/composables/useCustomIngestionWizard'

const BASE: RegionDecision = { stableId: 'region-b-5', measureKind: 'amount', unit: 'yuan' }

describe('buildRegionsFromDecisions', () => {
  it('amount + unit 产出 snake_case 的 stable_id/measure_kind/unit/divisor', () => {
    const { regions, errors } = buildRegionsFromDecisions([
      { stableId: 'r1', measureKind: 'amount', unit: 'wan' },
    ])
    expect(errors).toEqual([])
    expect(regions).toEqual([
      { stable_id: 'r1', measure_kind: 'amount', unit: 'wan', divisor: 10000 },
    ])
  })

  it('🔴 amount 缺 unit → 报错且不产出该 region', () => {
    const { regions, errors } = buildRegionsFromDecisions([
      { stableId: 'r1', measureKind: 'amount' },
    ])
    expect(regions).toEqual([])
    expect(errors).toHaveLength(1)
    expect(errors[0]).toContain('r1')
    expect(errors[0]).toContain('单位')
  })

  it('🔴 ratio 缺 ratioScale → 报错；带了 fraction → 产出 ratio_scale', () => {
    const missing = buildRegionsFromDecisions([{ stableId: 'r2', measureKind: 'ratio' }])
    expect(missing.regions).toEqual([])
    expect(missing.errors[0]).toContain('ratio_scale')

    const ok = buildRegionsFromDecisions([
      { stableId: 'r2', measureKind: 'ratio', ratioScale: 'percent_points' },
    ])
    expect(ok.errors).toEqual([])
    expect(ok.regions).toEqual([
      { stable_id: 'r2', measure_kind: 'ratio', ratio_scale: 'percent_points' },
    ])
  })

  it('🔴 非 ratio 带 ratioScale → 报错且不产出', () => {
    const { regions, errors } = buildRegionsFromDecisions([
      { stableId: 'r3', measureKind: 'amount', unit: 'yuan', ratioScale: 'fraction' },
    ])
    expect(regions).toEqual([])
    expect(errors[0]).toContain('不得声明 ratio_scale')
  })

  it('🔴 未知 kind → 报错', () => {
    const bad = { stableId: 'r4', measureKind: 'bogus' } as unknown as RegionDecision
    const { regions, errors } = buildRegionsFromDecisions([bad])
    expect(regions).toEqual([])
    expect(errors[0]).toContain('measure_kind 无效')
  })

  it('🔴 stableId 重复 → 第二条报错', () => {
    const { regions, errors } = buildRegionsFromDecisions([BASE, { ...BASE }])
    expect(regions).toHaveLength(1)
    expect(errors[0]).toContain('重复')
  })

  it('空裁决 → 空 regions 无错误（纯文本模板合法）', () => {
    const { regions, errors } = buildRegionsFromDecisions([])
    expect(regions).toEqual([])
    expect(errors).toEqual([])
  })

  it('非 amount 的 kind（quantity/count/exchange_rate/unit_price/text）不带 unit 也可用', () => {
    const kinds = ['quantity', 'count', 'exchange_rate', 'unit_price', 'text'] as const
    for (const k of kinds) {
      const { regions, errors } = buildRegionsFromDecisions([{ stableId: 'r', measureKind: k }])
      expect(errors).toEqual([])
      expect(regions).toEqual([{ stable_id: 'r', measure_kind: k }])
    }
  })

  it('允许集合与后端口径一致（前端常量钉住）', () => {
    // 后端 allowed_kinds = {amount, quantity, count, ratio, exchange_rate, unit_price, text}
    expect([...REGION_ALLOWED_KINDS].sort()).toEqual(
      ['amount', 'count', 'exchange_rate', 'quantity', 'ratio', 'text', 'unit_price'],
    )
    // 后端 unit → divisor：yuan 1 / qian 1000 / wan 10000
    expect(REGION_ALLOWED_UNITS).toEqual({ yuan: 1, qian: 1000, wan: 10000 })
  })
})
