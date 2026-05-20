/**
 * useRoleViewPreset.spec.ts — 角色视图预设 composable 单元测试
 *
 * spec role-based-view-switching Tasks 1.1-1.7
 *
 * 验证：
 * 1. 角色默认映射
 * 2. localStorage 读写 + 无效值回退
 * 3. 助理视图排序
 * 4. 合伙人视图排序 + 高亮
 * 5. 质控视图过滤
 * 6. 经理视图分组
 * 7. 搜索关键词保留
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { ref } from 'vue'
import { useRoleViewPreset, getDefaultPreset } from '../useRoleViewPreset'
import {
  statusPrioritySort,
  riskLevelSort,
  wpCodeNaturalSort,
  isKeyJudgmentPoint,
  partnerSummary,
  qcSummary,
  ROLE_DEFAULT_MAP,
  STATUS_PRIORITY,
  type WpItem,
  type HighlightContext,
} from '../viewPresetConfig'

// ─── Helpers ─────────────────────────────────────────────────────────────────

function makeWpItem(overrides: Partial<WpItem> = {}): WpItem {
  return {
    id: overrides.id ?? `wp-${Math.random().toString(36).slice(2, 8)}`,
    wp_code: overrides.wp_code ?? 'D2-1',
    status: overrides.status ?? 'pending',
    audit_cycle: overrides.audit_cycle ?? 'D',
    review_status: overrides.review_status ?? 'pending',
    ...overrides,
  }
}

function emptyContext(): HighlightContext {
  return {
    prerequisiteStatus: new Map(),
    consistencyGate: new Map(),
    reviewRecords: new Map(),
  }
}

// ─── Tests ───────────────────────────────────────────────────────────────────

describe('ROLE_DEFAULT_MAP — 角色默认映射', () => {
  it('assistant → assistant', () => {
    expect(getDefaultPreset('assistant')).toBe('assistant')
  })

  it('auditor → assistant', () => {
    expect(getDefaultPreset('auditor')).toBe('assistant')
  })

  it('manager → manager', () => {
    expect(getDefaultPreset('manager')).toBe('manager')
  })

  it('partner → partner', () => {
    expect(getDefaultPreset('partner')).toBe('partner')
  })

  it('qc → qc', () => {
    expect(getDefaultPreset('qc')).toBe('qc')
  })

  it('admin → partner', () => {
    expect(getDefaultPreset('admin')).toBe('partner')
  })

  it('eqcr → qc', () => {
    expect(getDefaultPreset('eqcr')).toBe('qc')
  })

  it('未知角色 → assistant (fallback)', () => {
    expect(getDefaultPreset('unknown_role')).toBe('assistant')
  })
})

describe('statusPrioritySort — 状态优先级排序', () => {
  it('pending < in_progress < completed < reviewed', () => {
    const items: WpItem[] = [
      makeWpItem({ status: 'reviewed' }),
      makeWpItem({ status: 'pending' }),
      makeWpItem({ status: 'completed' }),
      makeWpItem({ status: 'in_progress' }),
    ]
    items.sort(statusPrioritySort)
    expect(items.map(i => i.status)).toEqual(['pending', 'in_progress', 'completed', 'reviewed'])
  })

  it('未知状态排在最后', () => {
    const items: WpItem[] = [
      makeWpItem({ status: 'unknown' }),
      makeWpItem({ status: 'pending' }),
    ]
    items.sort(statusPrioritySort)
    expect(items[0].status).toBe('pending')
    expect(items[1].status).toBe('unknown')
  })
})

describe('riskLevelSort — 风险等级排序', () => {
  it('高风险(0) < 中风险(1) < 低风险(2)', () => {
    const items: WpItem[] = [
      makeWpItem({ _riskLevel: 2 }),
      makeWpItem({ _riskLevel: 0 }),
      makeWpItem({ _riskLevel: 1 }),
    ]
    items.sort(riskLevelSort)
    expect(items.map(i => i._riskLevel)).toEqual([0, 1, 2])
  })

  it('无 _riskLevel 视为低风险(2)', () => {
    const items: WpItem[] = [
      makeWpItem({ _riskLevel: undefined }),
      makeWpItem({ _riskLevel: 0 }),
    ]
    items.sort(riskLevelSort)
    expect(items[0]._riskLevel).toBe(0)
  })
})

describe('wpCodeNaturalSort — wp_code 自然排序', () => {
  it('D2-1 < D2-2 < D2-10', () => {
    const items: WpItem[] = [
      makeWpItem({ wp_code: 'D2-10' }),
      makeWpItem({ wp_code: 'D2-2' }),
      makeWpItem({ wp_code: 'D2-1' }),
    ]
    items.sort(wpCodeNaturalSort)
    expect(items.map(i => i.wp_code)).toEqual(['D2-1', 'D2-2', 'D2-10'])
  })

  it('A15 < B15 < D2-1', () => {
    const items: WpItem[] = [
      makeWpItem({ wp_code: 'D2-1' }),
      makeWpItem({ wp_code: 'A15' }),
      makeWpItem({ wp_code: 'B15' }),
    ]
    items.sort(wpCodeNaturalSort)
    expect(items.map(i => i.wp_code)).toEqual(['A15', 'B15', 'D2-1'])
  })
})

describe('isKeyJudgmentPoint — 质控过滤', () => {
  it('B15 通过', () => {
    expect(isKeyJudgmentPoint(makeWpItem({ wp_code: 'B15' }))).toBe(true)
  })

  it('A15 通过', () => {
    expect(isKeyJudgmentPoint(makeWpItem({ wp_code: 'A15' }))).toBe(true)
  })

  it('B50-4 通过', () => {
    expect(isKeyJudgmentPoint(makeWpItem({ wp_code: 'B50-4' }))).toBe(true)
  })

  it('D2-1 通过（各循环审定表）', () => {
    expect(isKeyJudgmentPoint(makeWpItem({ wp_code: 'D2-1' }))).toBe(true)
  })

  it('F2-1 通过', () => {
    expect(isKeyJudgmentPoint(makeWpItem({ wp_code: 'F2-1' }))).toBe(true)
  })

  it('H1-1 通过', () => {
    expect(isKeyJudgmentPoint(makeWpItem({ wp_code: 'H1-1' }))).toBe(true)
  })

  it('D2-2 不通过', () => {
    expect(isKeyJudgmentPoint(makeWpItem({ wp_code: 'D2-2' }))).toBe(false)
  })

  it('B23-1 通过（匹配 [A-Z]\\d+-1 模式）', () => {
    expect(isKeyJudgmentPoint(makeWpItem({ wp_code: 'B23-1' }))).toBe(true)
  })

  it('C2-3 不通过', () => {
    expect(isKeyJudgmentPoint(makeWpItem({ wp_code: 'C2-3' }))).toBe(false)
  })

  it('D2-10 不通过', () => {
    expect(isKeyJudgmentPoint(makeWpItem({ wp_code: 'D2-10' }))).toBe(false)
  })
})

describe('partnerSummary — 合伙人汇总', () => {
  it('正确统计 blocking 和 open review', () => {
    const items: WpItem[] = [
      makeWpItem({ wp_code: 'D2-1' }),
      makeWpItem({ wp_code: 'D2-2' }),
    ]
    const ctx: HighlightContext = {
      prerequisiteStatus: new Map(),
      consistencyGate: new Map([
        ['D2-1', { blocking_count: 2, warning_count: 1, info_count: 0 }],
        ['D2-2', { blocking_count: 0, warning_count: 1, info_count: 0 }],
      ]),
      reviewRecords: new Map([
        ['D2-1', [{ id: 'r1', status: 'open' }, { id: 'r2', status: 'closed' }]],
        ['D2-2', [{ id: 'r3', status: 'open' }]],
      ]),
    }
    const result = partnerSummary(items, ctx)
    expect(result.items[0].value).toBe(2) // blocking total
    expect(result.items[1].value).toBe(2) // open review total
  })

  it('空列表返回 0', () => {
    const result = partnerSummary([], emptyContext())
    expect(result.items[0].value).toBe(0)
    expect(result.items[1].value).toBe(0)
  })
})

describe('qcSummary — 质控汇总', () => {
  it('按风险排序生成路径', () => {
    const items: WpItem[] = [
      makeWpItem({ wp_code: 'B15', _riskLevel: 1 }),
      makeWpItem({ wp_code: 'A15', _riskLevel: 0 }),
      makeWpItem({ wp_code: 'D2-1', _riskLevel: 2 }),
    ]
    const result = qcSummary(items, emptyContext())
    expect(result.items[0].value).toBe('A15 → B15 → D2-1')
    expect(result.items[1].value).toBe(3)
  })

  it('空列表返回提示', () => {
    const result = qcSummary([], emptyContext())
    expect(result.items[0].value).toBe('暂无关键判断点底稿')
  })
})

describe('useRoleViewPreset — localStorage 持久化', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  afterEach(() => {
    localStorage.clear()
  })

  it('switchPreset 写入 localStorage', () => {
    const { switchPreset, activePreset } = useRoleViewPreset(
      ref('proj-1'),
      ref('user-1'),
      ref([]),
      ref(''),
      ref({}),
      { role: ref('assistant') },
    )
    switchPreset('partner')
    expect(activePreset.value).toBe('partner')
    expect(localStorage.getItem('gt_wp_view_preset_user-1')).toBe('partner')
  })

  it('初始化时从 localStorage 读取有效值', () => {
    localStorage.setItem('gt_wp_view_preset_user-2', 'qc')
    const { activePreset } = useRoleViewPreset(
      ref('proj-1'),
      ref('user-2'),
      ref([]),
      ref(''),
      ref({}),
      { role: ref('assistant') },
    )
    expect(activePreset.value).toBe('qc')
  })

  it('localStorage 无效值回退到角色默认', () => {
    localStorage.setItem('gt_wp_view_preset_user-3', 'invalid_value')
    const { activePreset } = useRoleViewPreset(
      ref('proj-1'),
      ref('user-3'),
      ref([]),
      ref(''),
      ref({}),
      { role: ref('manager') },
    )
    expect(activePreset.value).toBe('manager')
  })

  it('localStorage 为空时回退到角色默认', () => {
    const { activePreset } = useRoleViewPreset(
      ref('proj-1'),
      ref('user-4'),
      ref([]),
      ref(''),
      ref({}),
      { role: ref('partner') },
    )
    expect(activePreset.value).toBe('partner')
  })
})

describe('useRoleViewPreset — processedList', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('助理视图按状态排序', () => {
    const wpList = ref<WpItem[]>([
      makeWpItem({ id: '1', status: 'completed' }),
      makeWpItem({ id: '2', status: 'pending' }),
      makeWpItem({ id: '3', status: 'in_progress' }),
    ])
    const { processedList, switchPreset } = useRoleViewPreset(
      ref('proj-1'),
      ref('user-5'),
      wpList,
      ref(''),
      ref({}),
      { role: ref('assistant') },
    )
    switchPreset('assistant')
    expect(processedList.value.map(i => i.status)).toEqual(['pending', 'in_progress', 'completed'])
  })

  it('质控视图仅显示关键判断点', () => {
    const wpList = ref<WpItem[]>([
      makeWpItem({ id: '1', wp_code: 'B15' }),
      makeWpItem({ id: '2', wp_code: 'D2-2' }),
      makeWpItem({ id: '3', wp_code: 'A15' }),
      makeWpItem({ id: '4', wp_code: 'D2-1' }),
    ])
    const { processedList, switchPreset } = useRoleViewPreset(
      ref('proj-1'),
      ref('user-6'),
      wpList,
      ref(''),
      ref({}),
      { role: ref('qc') },
    )
    switchPreset('qc')
    const codes = processedList.value.map(i => i.wp_code)
    expect(codes).toContain('B15')
    expect(codes).toContain('A15')
    expect(codes).toContain('D2-1')
    expect(codes).not.toContain('D2-2')
  })

  it('搜索关键词过滤生效', () => {
    const wpList = ref<WpItem[]>([
      makeWpItem({ id: '1', wp_code: 'D2-1', wp_name: '销售收入审定表' }),
      makeWpItem({ id: '2', wp_code: 'F2-1', wp_name: '存货审定表' }),
    ])
    const searchKeyword = ref('销售')
    const { processedList } = useRoleViewPreset(
      ref('proj-1'),
      ref('user-7'),
      wpList,
      searchKeyword,
      ref({}),
      { role: ref('assistant') },
    )
    expect(processedList.value.length).toBe(1)
    expect(processedList.value[0].wp_code).toBe('D2-1')
  })

  it('视图切换保留搜索关键词', () => {
    const wpList = ref<WpItem[]>([
      makeWpItem({ id: '1', wp_code: 'D2-1', wp_name: '销售收入审定表' }),
      makeWpItem({ id: '2', wp_code: 'F2-1', wp_name: '存货审定表' }),
    ])
    const searchKeyword = ref('销售')
    const { processedList, switchPreset } = useRoleViewPreset(
      ref('proj-1'),
      ref('user-8'),
      wpList,
      searchKeyword,
      ref({}),
      { role: ref('assistant') },
    )
    switchPreset('partner')
    // 搜索关键词仍然生效
    expect(processedList.value.length).toBe(1)
    expect(processedList.value[0].wp_code).toBe('D2-1')
  })

  it('manualFilters 叠加生效', () => {
    const wpList = ref<WpItem[]>([
      makeWpItem({ id: '1', wp_code: 'D2-1', audit_cycle: 'D' }),
      makeWpItem({ id: '2', wp_code: 'F2-1', audit_cycle: 'F' }),
    ])
    const manualFilters = ref({ audit_cycle: 'D' })
    const { processedList } = useRoleViewPreset(
      ref('proj-1'),
      ref('user-9'),
      wpList,
      ref(''),
      manualFilters,
      { role: ref('assistant') },
    )
    expect(processedList.value.length).toBe(1)
    expect(processedList.value[0].audit_cycle).toBe('D')
  })
})

describe('useRoleViewPreset — highlightMap', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('助理视图：blocked prereq → 橙色左边框', () => {
    const wpList = ref<WpItem[]>([
      makeWpItem({ id: 'wp-1', wp_code: 'D2-1' }),
    ])
    const prereqMap = ref(new Map([
      ['D2-1', { overall: 'blocked' as const, items: [{ wp_code: 'C2' }] }],
    ]))
    const { highlightMap, switchPreset } = useRoleViewPreset(
      ref('proj-1'),
      ref('user-10'),
      wpList,
      ref(''),
      ref({}),
      {
        role: ref('assistant'),
        prerequisiteStatus: prereqMap,
        consistencyGate: ref(new Map()),
        reviewRecords: ref(new Map()),
      },
    )
    switchPreset('assistant')
    const highlight = highlightMap.value.get('wp-1')
    expect(highlight).toBeDefined()
    expect(highlight!.style.borderLeft).toBe('3px solid #e6a23c')
    expect(highlight!.tooltip).toContain('C2')
  })

  it('合伙人视图：blocking VR → 红色背景', () => {
    const wpList = ref<WpItem[]>([
      makeWpItem({ id: 'wp-2', wp_code: 'D2-1' }),
    ])
    const gateMap = ref(new Map([
      ['D2-1', { blocking_count: 1, warning_count: 0, info_count: 0 }],
    ]))
    const { highlightMap, switchPreset } = useRoleViewPreset(
      ref('proj-1'),
      ref('user-11'),
      wpList,
      ref(''),
      ref({}),
      {
        role: ref('partner'),
        prerequisiteStatus: ref(new Map()),
        consistencyGate: gateMap,
        reviewRecords: ref(new Map()),
      },
    )
    switchPreset('partner')
    const highlight = highlightMap.value.get('wp-2')
    expect(highlight).toBeDefined()
    expect(highlight!.style.backgroundColor).toBe('rgba(255,0,0,0.08)')
    expect(highlight!.style.borderLeft).toBe('3px solid #f56c6c')
  })

  it('质控视图：未复核 → 黄色背景', () => {
    const wpList = ref<WpItem[]>([
      makeWpItem({ id: 'wp-3', wp_code: 'B15', review_status: 'pending' }),
    ])
    const { highlightMap, switchPreset } = useRoleViewPreset(
      ref('proj-1'),
      ref('user-12'),
      wpList,
      ref(''),
      ref({}),
      { role: ref('qc') },
    )
    switchPreset('qc')
    const highlight = highlightMap.value.get('wp-3')
    expect(highlight).toBeDefined()
    expect(highlight!.style.backgroundColor).toBe('rgba(255,200,0,0.08)')
  })

  it('质控视图：已复核 → 无高亮', () => {
    const wpList = ref<WpItem[]>([
      makeWpItem({ id: 'wp-4', wp_code: 'B15', review_status: 'reviewed' }),
    ])
    const { highlightMap, switchPreset } = useRoleViewPreset(
      ref('proj-1'),
      ref('user-13'),
      wpList,
      ref(''),
      ref({}),
      { role: ref('qc') },
    )
    switchPreset('qc')
    const highlight = highlightMap.value.get('wp-4')
    expect(highlight).toBeUndefined()
  })
})

describe('useRoleViewPreset — badgeMap', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('合伙人视图：_openReviewCount > 0 → danger badge', () => {
    const wpList = ref<WpItem[]>([
      makeWpItem({ id: 'wp-5', _openReviewCount: 3 }),
    ])
    const { badgeMap, switchPreset } = useRoleViewPreset(
      ref('proj-1'),
      ref('user-14'),
      wpList,
      ref(''),
      ref({}),
      { role: ref('partner') },
    )
    switchPreset('partner')
    const badge = badgeMap.value.get('wp-5')
    expect(badge).toBeDefined()
    expect(badge!.value).toBe(3)
    expect(badge!.type).toBe('danger')
    expect(badge!.visible).toBe(true)
  })

  it('合伙人视图：_openReviewCount = 0 → 无 badge', () => {
    const wpList = ref<WpItem[]>([
      makeWpItem({ id: 'wp-6', _openReviewCount: 0 }),
    ])
    const { badgeMap, switchPreset } = useRoleViewPreset(
      ref('proj-1'),
      ref('user-15'),
      wpList,
      ref(''),
      ref({}),
      { role: ref('partner') },
    )
    switchPreset('partner')
    const badge = badgeMap.value.get('wp-6')
    expect(badge).toBeUndefined()
  })
})

describe('useRoleViewPreset — groupedList (经理视图)', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('经理视图按 audit_cycle 分组', () => {
    const wpList = ref<WpItem[]>([
      makeWpItem({ id: '1', wp_code: 'D2-1', audit_cycle: 'D', status: 'completed' }),
      makeWpItem({ id: '2', wp_code: 'D2-2', audit_cycle: 'D', status: 'pending' }),
      makeWpItem({ id: '3', wp_code: 'F2-1', audit_cycle: 'F', status: 'completed' }),
    ])
    const { groupedList, switchPreset } = useRoleViewPreset(
      ref('proj-1'),
      ref('user-16'),
      wpList,
      ref(''),
      ref({}),
      { role: ref('manager') },
    )
    switchPreset('manager')
    expect(groupedList.value).not.toBeNull()
    expect(groupedList.value!.length).toBe(2)

    const dGroup = groupedList.value!.find(g => g.key === 'D')
    expect(dGroup).toBeDefined()
    expect(dGroup!.items.length).toBe(2)
    expect(dGroup!.completed).toBe(1)
    expect(dGroup!.progress).toBe(50)
  })

  it('进度 100% 的分组默认折叠', () => {
    const wpList = ref<WpItem[]>([
      makeWpItem({ id: '1', audit_cycle: 'D', status: 'completed' }),
      makeWpItem({ id: '2', audit_cycle: 'D', status: 'reviewed' }),
    ])
    const { groupedList, switchPreset } = useRoleViewPreset(
      ref('proj-1'),
      ref('user-17'),
      wpList,
      ref(''),
      ref({}),
      { role: ref('manager') },
    )
    switchPreset('manager')
    const dGroup = groupedList.value!.find(g => g.key === 'D')
    expect(dGroup!.collapsed).toBe(true)
  })

  it('进度 < 100% 的分组默认展开', () => {
    const wpList = ref<WpItem[]>([
      makeWpItem({ id: '1', audit_cycle: 'F', status: 'completed' }),
      makeWpItem({ id: '2', audit_cycle: 'F', status: 'pending' }),
    ])
    const { groupedList, switchPreset } = useRoleViewPreset(
      ref('proj-1'),
      ref('user-18'),
      wpList,
      ref(''),
      ref({}),
      { role: ref('manager') },
    )
    switchPreset('manager')
    const fGroup = groupedList.value!.find(g => g.key === 'F')
    expect(fGroup!.collapsed).toBe(false)
  })

  it('非经理视图 groupedList 为 null', () => {
    const wpList = ref<WpItem[]>([
      makeWpItem({ id: '1', audit_cycle: 'D' }),
    ])
    const { groupedList, switchPreset } = useRoleViewPreset(
      ref('proj-1'),
      ref('user-19'),
      wpList,
      ref(''),
      ref({}),
      { role: ref('assistant') },
    )
    switchPreset('assistant')
    expect(groupedList.value).toBeNull()
  })
})

describe('useRoleViewPreset — summaryData', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('合伙人视图有 summaryData', () => {
    const wpList = ref<WpItem[]>([
      makeWpItem({ id: '1', wp_code: 'D2-1' }),
    ])
    const { summaryData, switchPreset } = useRoleViewPreset(
      ref('proj-1'),
      ref('user-20'),
      wpList,
      ref(''),
      ref({}),
      {
        role: ref('partner'),
        consistencyGate: ref(new Map([['D2-1', { blocking_count: 1, warning_count: 0, info_count: 0 }]])),
        reviewRecords: ref(new Map()),
        prerequisiteStatus: ref(new Map()),
      },
    )
    switchPreset('partner')
    expect(summaryData.value).not.toBeNull()
    expect(summaryData.value!.label).toBe('合伙人视图汇总')
  })

  it('助理视图无 summaryData', () => {
    const { summaryData, switchPreset } = useRoleViewPreset(
      ref('proj-1'),
      ref('user-21'),
      ref([]),
      ref(''),
      ref({}),
      { role: ref('assistant') },
    )
    switchPreset('assistant')
    expect(summaryData.value).toBeNull()
  })
})
