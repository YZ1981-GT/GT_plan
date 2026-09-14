/**
 * useC22BundleState.spec.ts — C22 ITGC Bundle 状态 composable 单元测试（Tasks 3.1 / 3.2）
 *
 * Spec: .kiro/specs/c22-itgc-bundle/  Requirements: 4.1, 5.1, 5.2, 7.1, 7.2, 7.4
 *
 * 覆盖：
 * - sheetTabs 分组（Phase0 §3 TabDef 表：matrix + SA10/PE8/PM6/NS9 + C21 + C21-1）
 * - 31 控制点 vs 33 子页 vs aux 续页（PE-5.1 / PE-8.1 不计入）
 * - completionMap 推导（设计/执行有效性结论）
 * - defects 收集（是否异常=是）
 * - progressSummary 一致性
 * - PM-4c #REF! 兜底标记 / matrix 排序按控制编号
 */
import { describe, it, expect } from 'vitest'
import {
  C22_BUNDLE_TABS,
  ITGC_GROUPS,
  ITGC_CONTROL_SHEETS,
  ITGC_ALL_SHEETS,
  FS_ASSERTIONS,
  C21_CARRYOVER_ITEM_ID,
  itgcItemId,
  c21SummaryItemId,
  extractControlPointFields,
  deriveItgcStatus,
  collectControlPointDefect,
  computeProgressSummary,
  statusToDisplay,
  type TabDef,
  type ChecklistResponse,
  type ControlPointFields,
} from '../useC22BundleState'

// ─── helpers ───

function emptyFields(overrides: Partial<ControlPointFields> = {}): ControlPointFields {
  return {
    designConclusion: null,
    execConclusion: null,
    abnormal: null,
    defectDesc: null,
    defectNo: null,
    appSystem: null,
    itCategory: null,
    ...overrides,
  }
}

function findTab(id: string): TabDef {
  const t = C22_BUNDLE_TABS.find(t => t.id === id)
  if (!t) throw new Error(`tab ${id} not found`)
  return t
}

// ═══════════════════════════════════════════════════════════════════════════════
// TabDef 分组结构（Task 3.1）
// ═══════════════════════════════════════════════════════════════════════════════

describe('C22_BUNDLE_TABS 分组结构（Phase0 §3）', () => {
  it('共 36 个 Tab（matrix + 33 子页 + C21 + C21-1）', () => {
    expect(C22_BUNDLE_TABS.length).toBe(36)
  })

  it('首个 Tab 为 matrix 总览', () => {
    expect(C22_BUNDLE_TABS[0].id).toBe('matrix')
    expect(C22_BUNDLE_TABS[0].kind).toBe('matrix')
  })

  it('4 大类子页计数：SA=10 / PE=8 / PM=6 / NS=9', () => {
    const countGroup = (g: string) =>
      C22_BUNDLE_TABS.filter(t => t.group === g && (t.kind === 'itgc-sheet' || t.kind === 'itgc-aux')).length
    expect(countGroup('信息安全')).toBe(10)
    expect(countGroup('运行维护')).toBe(8)
    expect(countGroup('程序变更')).toBe(6)
    expect(countGroup('新系统')).toBe(9)
  })

  it('C22 工作簿子页合计 33（含 2 aux 续页）', () => {
    expect(ITGC_ALL_SHEETS.length).toBe(33)
  })

  it('真正控制点为 31（排除 2 aux 续页）', () => {
    expect(ITGC_CONTROL_SHEETS.length).toBe(31)
    expect(C22_BUNDLE_TABS.filter(t => t.kind === 'itgc-sheet').length).toBe(31)
  })

  it('PE-5.1 / PE-8.1 为 aux 续页，归 PE 组但不计入控制点', () => {
    const aux = C22_BUNDLE_TABS.filter(t => t.kind === 'itgc-aux')
    expect(aux.map(t => t.id).sort()).toEqual(['PE-5.1', 'PE-8.1'])
    for (const t of aux) {
      expect(t.group).toBe('运行维护')
      expect(ITGC_CONTROL_SHEETS).not.toContain(t.sheet)
    }
  })

  it('每个 itgc-sheet 子页唯一归入 4 大类之一（Property 2）', () => {
    for (const t of C22_BUNDLE_TABS) {
      if (t.kind === 'itgc-sheet' || t.kind === 'itgc-aux') {
        expect(ITGC_GROUPS).toContain(t.group)
      }
    }
  })

  it('matrix / C21 / C21-1 不计入 4 大类控制域分组', () => {
    expect(findTab('matrix').group).toBe('matrix')
    expect(findTab('C21').group).toBe('IT团队')
    expect(findTab('C21-1').group).toBe('发现汇总')
  })

  it('C21 / C21-1 为独立底稿（有 wpCode 无 sheet）', () => {
    expect(findTab('C21').kind).toBe('c21')
    expect(findTab('C21').wpCode).toBe('C21')
    expect(findTab('C21-1').kind).toBe('c21-1')
    expect(findTab('C21-1').wpCode).toBe('C21-1')
  })

  it('PM-4c 标记源模板公式损坏（#REF! 兜底）', () => {
    const pm4c = findTab('PM-4c')
    expect(pm4c.refBroken).toBe(true)
    expect(pm4c.matrixRow).toBe(32)
  })

  it('多控制子页记录额外控制描述行（PE-3d/PE-6/PE-8）', () => {
    expect(findTab('PE-3d').extraDescRows).toEqual([22])
    expect(findTab('PE-6').extraDescRows).toEqual([25, 26, 27])
    expect(findTab('PE-8').extraDescRows).toEqual([30])
  })

  it('matrix 排序按控制编号（matrixRow 单调递增）', () => {
    const rows = C22_BUNDLE_TABS
      .filter(t => t.kind === 'itgc-sheet')
      .map(t => t.matrixRow as number)
    const sorted = [...rows].sort((a, b) => a - b)
    expect(rows).toEqual(sorted)
  })

  it('所有 Tab id 唯一', () => {
    const ids = C22_BUNDLE_TABS.map(t => t.id)
    expect(new Set(ids).size).toBe(ids.length)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// item_id 编码 + 字段抽取
// ═══════════════════════════════════════════════════════════════════════════════

describe('itgcItemId / extractControlPointFields', () => {
  it('item_id 规则 C22.{controlId}.{field}', () => {
    expect(itgcItemId('SA-3', 'design-conclusion')).toBe('C22.SA-3.design-conclusion')
    expect(itgcItemId('PE-6', 'abnormal')).toBe('C22.PE-6.abnormal')
  })

  it('从 responses Map 抽取控制点字段', () => {
    const map = new Map<string, ChecklistResponse>([
      [itgcItemId('SA-7', 'design-conclusion'), { item_id: itgcItemId('SA-7', 'design-conclusion'), conclusion: '有效' }],
      [itgcItemId('SA-7', 'exec-conclusion'), { item_id: itgcItemId('SA-7', 'exec-conclusion'), conclusion: '无效' }],
      [itgcItemId('SA-7', 'abnormal'), { item_id: itgcItemId('SA-7', 'abnormal'), conclusion: '是' }],
      [itgcItemId('SA-7', 'defect-desc'), { item_id: itgcItemId('SA-7', 'defect-desc'), remark: '权限未及时回收' }],
      [itgcItemId('SA-7', 'defect-no'), { item_id: itgcItemId('SA-7', 'defect-no'), remark: 'ITGC#1' }],
      [itgcItemId('SA-7', 'app-system'), { item_id: itgcItemId('SA-7', 'app-system'), remark: 'A系统' }],
    ])
    const f = extractControlPointFields(map, 'SA-7')
    expect(f).toEqual({
      designConclusion: '有效',
      execConclusion: '无效',
      abnormal: '是',
      defectDesc: '权限未及时回收',
      defectNo: 'ITGC#1',
      appSystem: 'A系统',
      itCategory: null,
    })
  })

  it('缺失字段返回 null', () => {
    const f = extractControlPointFields(new Map(), 'SA-3')
    expect(f).toEqual(emptyFields())
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// completionMap 推导（Req 7.1）
// ═══════════════════════════════════════════════════════════════════════════════

describe('deriveItgcStatus', () => {
  it('设计+执行均非空 → completed', () => {
    expect(deriveItgcStatus(emptyFields({ designConclusion: '有效', execConclusion: '有效' }))).toBe('completed')
  })
  it('仅设计非空 → in_progress', () => {
    expect(deriveItgcStatus(emptyFields({ designConclusion: '有效' }))).toBe('in_progress')
  })
  it('仅执行非空 → in_progress', () => {
    expect(deriveItgcStatus(emptyFields({ execConclusion: '部分有效' }))).toBe('in_progress')
  })
  it('均空 → not_started', () => {
    expect(deriveItgcStatus(emptyFields())).toBe('not_started')
  })
  it('空白字符串视为空', () => {
    expect(deriveItgcStatus(emptyFields({ designConclusion: '   ', execConclusion: '' }))).toBe('not_started')
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// defects 收集（Req 5.1 / 5.2）
// ═══════════════════════════════════════════════════════════════════════════════

describe('collectControlPointDefect', () => {
  const saTab = findTab('SA-7')

  it('是否异常=是 → 生成缺陷条目（含双向追溯 sheet）', () => {
    const defect = collectControlPointDefect(saTab, emptyFields({
      abnormal: '是', defectDesc: '权限未回收', defectNo: 'ITGC#1', appSystem: 'A系统',
    }))
    expect(defect).toEqual({
      controlId: 'SA-7',
      group: '信息安全',
      sheet: 'SA-7',
      description: '权限未回收',
      defectNo: 'ITGC#1',
      appSystem: 'A系统',
    })
  })

  it('是否异常=否 → 无缺陷', () => {
    expect(collectControlPointDefect(saTab, emptyFields({ abnormal: '否' }))).toBeNull()
  })

  it('是否异常未填 → 无缺陷', () => {
    expect(collectControlPointDefect(saTab, emptyFields())).toBeNull()
  })

  it('缺陷描述/编号缺失时兜底为空串/undefined', () => {
    const defect = collectControlPointDefect(saTab, emptyFields({ abnormal: '是' }))
    expect(defect).toMatchObject({ description: '', defectNo: '', appSystem: undefined })
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// progressSummary 一致性（Property 4）
// ═══════════════════════════════════════════════════════════════════════════════

describe('computeProgressSummary', () => {
  it('三态之和 == 控制点总数，defectCount == defects 长度', () => {
    const completionMap = {
      'SA-3': 'completed' as const,
      'SA-4c': 'in_progress' as const,
      'SA-5': 'not_started' as const,
      'PE-3a': 'completed' as const,
    }
    const defects = [
      { controlId: 'SA-3', group: '信息安全' as const, sheet: 'SA-3', description: 'x', defectNo: 'ITGC#1' },
    ]
    const s = computeProgressSummary(completionMap, defects)
    expect(s.completed).toBe(2)
    expect(s.inProgress).toBe(1)
    expect(s.notStarted).toBe(1)
    expect(s.completed + s.inProgress + s.notStarted).toBe(Object.keys(completionMap).length)
    expect(s.defectCount).toBe(1)
  })

  it('空 map → 全 0', () => {
    expect(computeProgressSummary({}, [])).toEqual({
      completed: 0, inProgress: 0, notStarted: 0, defectCount: 0,
    })
  })
})

describe('statusToDisplay', () => {
  it('三色映射', () => {
    expect(statusToDisplay('completed').color).toBe('#52c41a')
    expect(statusToDisplay('in_progress').color).toBe('#faad14')
    expect(statusToDisplay('not_started').color).toBe('#bfbfbf')
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// C21-1 汇总补充字段（Task 5.1）
// ═══════════════════════════════════════════════════════════════════════════════

describe('c21SummaryItemId / FS_ASSERTIONS（C21-1 汇总补充）', () => {
  it('item_id 规则 C22.C21-1.{controlId}.{field}', () => {
    expect(c21SummaryItemId('SA-7', 'impact')).toBe('C22.C21-1.SA-7.impact')
    expect(c21SummaryItemId('SA-7', 'remediation')).toBe('C22.C21-1.SA-7.remediation')
    expect(c21SummaryItemId('PE-6', 'assertions')).toBe('C22.C21-1.PE-6.assertions')
    expect(c21SummaryItemId('NS-1', 'compensating')).toBe('C22.C21-1.NS-1.compensating')
  })

  it('补充字段前缀 C22.C21-1. 不与控制点字段前缀冲突', () => {
    // 控制点字段前缀是 C22.{controlId}.（controlId ∈ 31 控制点，无 "C21-1"）
    const supplementId = c21SummaryItemId('SA-7', 'impact')
    // 不会被误判为某控制点字段（controlId 必须是真实控制点）
    const isControlPointField = ITGC_CONTROL_SHEETS.some(
      (sheet) => supplementId.startsWith(`C22.${sheet}.`),
    )
    expect(isControlPointField).toBe(false)
    expect(supplementId.startsWith('C22.C21-1.')).toBe(true)
  })

  it('财务报表认定为 9 项（Phase0 §5）', () => {
    expect(FS_ASSERTIONS.length).toBe(9)
    expect(FS_ASSERTIONS).toEqual([
      '发生', '完整性', '准确性', '截止', '分类', '存在', '权利和义务', '计价和分摊', '列报',
    ])
  })

  it('上年度整改表 item_id 常量', () => {
    expect(C21_CARRYOVER_ITEM_ID).toBe('C22.C21-1.__carryover__')
  })
})
