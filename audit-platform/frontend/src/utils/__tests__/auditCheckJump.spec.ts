import { describe, it, expect } from 'vitest'
import {
  PROJECT_WP_CODE,
  resolveCheckJumpTarget,
  isCheckJumpable,
  jumpDisabledTooltip,
  matchesCheckFilter,
  checkSortRank,
  sortChecksByPriority,
  deriveGraphCycles,
  resolveSelectedGraphCycle,
  GRAPH_VALID_CYCLES,
} from '../auditCheckJump'

// ─── 可跳性判定（Req6.1/6.2） ──────────────────────────────────────────────
describe('resolveCheckJumpTarget — 可跳性判定', () => {
  it('有 wp_id + sheet_hint → 跳底稿并带 sheet', () => {
    const t = resolveCheckJumpTarget({ wp_id: 'wp-1', wp_code: 'K9', sheet_hint: '审定表K9-1' })
    expect(t).toEqual({ wpId: 'wp-1', sheet: '审定表K9-1' })
  })

  it('有 wp_id 无 sheet_hint → 只跳底稿不带 sheet', () => {
    const t = resolveCheckJumpTarget({ wp_id: 'wp-1', wp_code: 'K9', sheet_hint: null })
    expect(t).toEqual({ wpId: 'wp-1' })
    expect(t?.sheet).toBeUndefined()
  })

  it('空白 sheet_hint 视为无 sheet', () => {
    const t = resolveCheckJumpTarget({ wp_id: 'wp-1', wp_code: 'K9', sheet_hint: '   ' })
    expect(t).toEqual({ wpId: 'wp-1' })
  })

  it('项目级来源（__PROJECT__）→ 不可跳', () => {
    expect(resolveCheckJumpTarget({ wp_code: PROJECT_WP_CODE, wp_id: null, sheet_hint: null })).toBeNull()
    // 即便误带 wp_id，__PROJECT__ 仍不可跳
    expect(resolveCheckJumpTarget({ wp_code: PROJECT_WP_CODE, wp_id: 'x' })).toBeNull()
  })

  it('无 wp_id 且父行也无 wp_id → 不可跳', () => {
    expect(resolveCheckJumpTarget({ wp_code: 'K9', wp_id: null }, { wp_code: 'K9', wp_id: null })).toBeNull()
    expect(resolveCheckJumpTarget({ wp_code: 'K9' }, {})).toBeNull()
  })

  it('check 无 wp_id 时回退父底稿行 wp_id', () => {
    const t = resolveCheckJumpTarget({ wp_code: 'D2', sheet_hint: '明细表D2-2' }, { wp_id: 'parent-wp', wp_code: 'D2' })
    expect(t).toEqual({ wpId: 'parent-wp', sheet: '明细表D2-2' })
  })

  it('check 自带 wp_id 优先于父行', () => {
    const t = resolveCheckJumpTarget({ wp_id: 'own', wp_code: 'D2' }, { wp_id: 'parent', wp_code: 'D2' })
    expect(t?.wpId).toBe('own')
  })
})

describe('isCheckJumpable / jumpDisabledTooltip', () => {
  it('可跳返回 true', () => {
    expect(isCheckJumpable({ wp_id: 'wp-1', wp_code: 'K9' })).toBe(true)
  })
  it('项目级提示"项目级检查，无对应底稿"', () => {
    expect(jumpDisabledTooltip({ wp_code: PROJECT_WP_CODE })).toBe('项目级检查，无对应底稿')
  })
  it('无 wp_id 提示"无法定位到底稿"', () => {
    expect(jumpDisabledTooltip({ wp_code: 'K9', wp_id: null })).toBe('无法定位到底稿')
  })
})

// ─── 筛选（Req6.3） ────────────────────────────────────────────────────────
describe('matchesCheckFilter', () => {
  const failed = { passed: false, severity: 'warning' }
  const blocking = { passed: false, severity: 'blocking' }
  const uncovered = { passed: null, severity: 'info' }
  const passed = { passed: true, severity: 'info' }

  it('all 全部通过', () => {
    for (const c of [failed, blocking, uncovered, passed]) {
      expect(matchesCheckFilter(c, 'all')).toBe(true)
    }
  })
  it('failed 仅未通过', () => {
    expect(matchesCheckFilter(failed, 'failed')).toBe(true)
    expect(matchesCheckFilter(blocking, 'failed')).toBe(true)
    expect(matchesCheckFilter(uncovered, 'failed')).toBe(false)
    expect(matchesCheckFilter(passed, 'failed')).toBe(false)
  })
  it('uncovered 仅未覆盖（null/undefined）', () => {
    expect(matchesCheckFilter(uncovered, 'uncovered')).toBe(true)
    expect(matchesCheckFilter({ severity: 'info' }, 'uncovered')).toBe(true)
    expect(matchesCheckFilter(failed, 'uncovered')).toBe(false)
    expect(matchesCheckFilter(passed, 'uncovered')).toBe(false)
  })
  it('blocking 仅阻断（blocking 且 failed）', () => {
    expect(matchesCheckFilter(blocking, 'blocking')).toBe(true)
    expect(matchesCheckFilter(failed, 'blocking')).toBe(false)
    // 阻断但已通过不算
    expect(matchesCheckFilter({ passed: true, severity: 'blocking' }, 'blocking')).toBe(false)
  })
})

// ─── 排序置顶（Req6.3） ────────────────────────────────────────────────────
describe('sortChecksByPriority — 阻断>未通过>未覆盖>通过，同级稳定', () => {
  it('优先级 rank', () => {
    expect(checkSortRank({ passed: false, severity: 'blocking' })).toBe(0)
    expect(checkSortRank({ passed: false, severity: 'warning' })).toBe(1)
    expect(checkSortRank({ passed: null })).toBe(2)
    expect(checkSortRank({ passed: true })).toBe(3)
  })

  it('置顶排序 + 同级保持原序', () => {
    const input = [
      { code: 'p1', passed: true, severity: 'info' },
      { code: 'u1', passed: null, severity: 'info' },
      { code: 'f1', passed: false, severity: 'warning' },
      { code: 'b1', passed: false, severity: 'blocking' },
      { code: 'f2', passed: false, severity: 'warning' },
      { code: 'p2', passed: true, severity: 'info' },
    ]
    const out = sortChecksByPriority(input).map(c => c.code)
    expect(out).toEqual(['b1', 'f1', 'f2', 'u1', 'p1', 'p2'])
  })

  it('不修改原数组', () => {
    const input = [{ code: 'a', passed: true }, { code: 'b', passed: false }]
    const snapshot = input.map(c => c.code)
    sortChecksByPriority(input)
    expect(input.map(c => c.code)).toEqual(snapshot)
  })
})

// ─── 依赖图循环动态生成（Req9.2） ──────────────────────────────────────────
describe('deriveGraphCycles', () => {
  it('仅保留 D~N 有效循环，按固定顺序', () => {
    expect(deriveGraphCycles(['K', 'D', 'M', 'OTHER', 'Q'])).toEqual(['D', 'K', 'M'])
  })
  it('含 M', () => {
    expect(deriveGraphCycles(['M'])).toEqual(['M'])
  })
  it('排除 OTHER/Q', () => {
    expect(deriveGraphCycles(['OTHER', 'Q'])).toEqual([...GRAPH_VALID_CYCLES])
  })
  it('无匹配时回退完整 D~N', () => {
    expect(deriveGraphCycles([])).toEqual([...GRAPH_VALID_CYCLES])
  })
})

describe('resolveSelectedGraphCycle', () => {
  it('当前值在列表内 → 保留', () => {
    expect(resolveSelectedGraphCycle('K', ['D', 'K', 'M'])).toBe('K')
  })
  it('当前值不在列表 → 回退第一个', () => {
    expect(resolveSelectedGraphCycle('E', ['D', 'K', 'M'])).toBe('D')
  })
  it('空列表 → 保留当前值', () => {
    expect(resolveSelectedGraphCycle('E', [])).toBe('E')
  })
})
