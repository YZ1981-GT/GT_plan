import { describe, expect, it } from 'vitest'
import {
  buildAdjustmentRouteHref,
  buildAdjustmentRouteTarget,
  parseAdjustmentRouteTarget,
} from '../adjustmentRouteTarget'

describe('adjustmentRouteTarget', () => {
  it.each([
    [{ kind: 'focus', entryGroupId: 'g-1' } as const, { focus: 'g-1', year: '2025' }],
    [{ kind: 'account', accountCode: '6001' } as const, { account: '6001', year: '2025' }],
    [{ kind: 'impact', entryGroupId: 'g-2' } as const, { impact: 'g-2', year: '2025' }],
    [{ kind: 'collaboration', entryGroupId: 'g-3' } as const, { group: 'g-3', year: '2025' }],
  ])('按目标类型只写规范 query：%o', (target, query) => {
    expect(buildAdjustmentRouteTarget('p1', target, { year: 2025 })).toEqual({
      name: 'Adjustments', params: { projectId: 'p1' }, query,
    })
  })

  it('分录组只进入 focus，不会误塞进 account', () => {
    const route = buildAdjustmentRouteTarget('p1', { kind: 'focus', entryGroupId: 'group-uuid' })
    expect(route.query).toEqual({ focus: 'group-uuid' })
    expect(route.query).not.toHaveProperty('account')
  })

  it('focus 可带状态；其他目标不会携带无意义状态', () => {
    expect(buildAdjustmentRouteTarget('p1', { kind: 'focus', entryGroupId: 'g1' }, { status: 'rejected' }).query)
      .toEqual({ focus: 'g1', status: 'rejected' })
    expect(buildAdjustmentRouteTarget('p1', { kind: 'account', accountCode: '1001' }, { status: 'rejected' }).query)
      .toEqual({ account: '1001' })
  })

  it('兼容旧 id 和 highlight，规范 focus 优先', () => {
    expect(parseAdjustmentRouteTarget({ id: 'old-id' })).toMatchObject({ focus: 'old-id', legacyFocus: 'id' })
    expect(parseAdjustmentRouteTarget({ highlight: 'old-highlight' })).toMatchObject({ focus: 'old-highlight', legacyFocus: 'highlight' })
    expect(parseAdjustmentRouteTarget({ focus: 'new', id: 'old', highlight: 'older' })).toMatchObject({ focus: 'new', legacyFocus: null })
  })

  it('解析四类目标、数组 query 和有效年度', () => {
    expect(parseAdjustmentRouteTarget({
      focus: ['', 'g1'], account: '6001', impact: 'g2', group: 'g3', status: 'approved', year: '2025',
    })).toEqual({
      focus: 'g1', account: '6001', impact: 'g2', group: 'g3', status: 'approved', year: 2025, legacyFocus: null,
    })
    expect(parseAdjustmentRouteTarget({ year: 'null' }).year).toBeNull()
  })

  it('字符串地址与命名路由使用同一参数顺序和编码', () => {
    expect(buildAdjustmentRouteHref('p 1', { kind: 'focus', entryGroupId: '组 1' }, { year: 2025, status: 'pending_review' }))
      .toBe('/projects/p%201/adjustments?focus=%E7%BB%84+1&year=2025&status=pending_review')
  })
})
