/**
 * 报表「审核」响应映射（spec formula-governance-coverage-closure R1.6）。
 *
 * 早先只映射 consistent / checks 五个字段：弹窗统计恒 0、按 category 分的两个页签恒空；
 * 0 条可执行时 consistent 被当成「全部通过」。
 */
import { describe, expect, it, vi } from 'vitest'

vi.mock('@/utils/http', () => ({ default: { get: vi.fn(), post: vi.fn() } }))

import { mapReportConsistencyCheck } from '@/services/auditPlatformApi'

describe('mapReportConsistencyCheck', () => {
  it('0 条可执行：noResult 且 consistent 为 null（不是全部通过）', () => {
    const got = mapReportConsistencyCheck({ consistent: true, no_result: true, checks: [], total: 0 })
    expect(got.noResult).toBe(true)
    expect(got.consistent).toBeNull()
  })

  it('旧响应没有 no_result 字段且 checks 为空时也判 noResult', () => {
    expect(mapReportConsistencyCheck({ consistent: true, checks: [] }).noResult).toBe(true)
  })

  it('透传汇总计数与每项的分类 / 公式 / 来源', () => {
    const got = mapReportConsistencyCheck({
      consistent: false, no_result: false, total: 2,
      logic_check_count: 1, logic_check_passed: 1, reasonability_count: 1, reasonability_passed: 0,
      checks: [
        { name: '资产 = 负债 + 权益', passed: true, expected: '1', actual: '1', diff: '0',
          category: 'logic_check', category_label: '勾稽', formula: null, source: 'builtin' },
        { name: '毛利率合理', passed: false, expected: '0', actual: '无法取数（AUX 缺数）', diff: '',
          category: 'reasonability', category_label: '合理性', formula: "AUX('6001','客户')", source: 'config' },
      ],
    })
    expect(got).toMatchObject({
      consistent: false, noResult: false, total: 2,
      logic_check_count: 1, logic_check_passed: 1, reasonability_count: 1, reasonability_passed: 0,
    })
    expect(got.checks.map((c) => [c.category, c.source, c.formula])).toEqual([
      ['logic_check', 'builtin', null],
      ['reasonability', 'config', "AUX('6001','客户')"],
    ])
  })
})
