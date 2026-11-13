import { describe, expect, it } from 'vitest'
import {
  crossCheckStatusOf,
  mapBackendCrossCheck,
} from '../useReportCrossCheck'

/** S2 任务4（ADR-CCN-05）：表间审核严重度与界面「提示」。 */
describe('表间审核严重度（ADR-CCN-05）', () => {
  it('未通过且 warning / info 为「提示」，未通过且 blocking 为「未通过」，通过为「通过」', () => {
    expect(crossCheckStatusOf({ passed: false, severity: 'warning' })).toBe('hint')
    expect(crossCheckStatusOf({ passed: false, severity: 'info' })).toBe('hint')
    expect(crossCheckStatusOf({ passed: false, severity: 'blocking' })).toBe('failed')
    expect(crossCheckStatusOf({ passed: true, severity: 'blocking' })).toBe('passed')
  })

  it('后端逐条结果缺省或认不出的 severity 按 warning 处理，不冒充阻断', () => {
    const items = mapBackendCrossCheck({
      results: [
        { formula_id: 'a', description: 'A', passed: false },
        { formula_id: 'b', description: 'B', passed: false, severity: 'blocking' },
        { formula_id: 'c', description: 'C', passed: false, severity: 'fatal' },
      ],
    })
    expect(items.map((i) => i.severity)).toEqual(['warning', 'blocking', 'warning'])
    expect(items.map((i) => crossCheckStatusOf(i))).toEqual(['hint', 'failed', 'hint'])
  })

  it('issue_list 上的 severity 在逐条结果缺省时补上（逐条结果优先）', () => {
    const items = mapBackendCrossCheck({
      results: [
        { formula_id: 'a', description: 'A', passed: false },
        { formula_id: 'b', description: 'B', passed: false, severity: 'warning' },
      ],
      issue_list: [
        { formula_id: 'a', description: 'A', severity: 'blocking' },
        { formula_id: 'b', description: 'B', severity: 'blocking' },
      ],
    } as any)
    expect(items.map((i) => i.severity)).toEqual(['blocking', 'warning'])
  })
})
