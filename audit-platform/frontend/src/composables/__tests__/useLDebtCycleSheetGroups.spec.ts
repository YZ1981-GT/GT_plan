/**
 * useLDebtCycleSheetGroups.spec.ts — L-F2 Task 2.2
 *
 * Validates: Requirements L-F2
 *
 * 验证 10 类分组规则对 L 循环 79 个有效 sheet 全覆盖（采样代表）：
 *   1. 索引（底稿目录/GT_Custom/修订说明）→ defaultHidden=true
 *   2. 历史遗留（含"示例"）→ defaultHidden=true
 *   3. 总控台（实质性程序表 / xxA 结尾）
 *   4. 审定表（审定表）
 *   5. 明细表（明细表）
 *   6. 分析程序（分析程序）
 *   7. 利息测算（利息测算 / 利息计算 / 利率测算）
 *   8. 检查表（逾期 / 检查表 / 核查表 / 摊余成本）
 *   9. 附注+调整（附注披露 → defaultHidden=true + readonly=true / 调整分录）
 *  10. 其他程序（fallback）
 */
import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import {
  classifyLSheet,
  L_SHEET_GROUP_RULES,
  FALLBACK_GROUP,
  useLDebtCycleSheetGroups,
} from '../useLDebtCycleSheetGroups'

// ===== L 循环代表 sheet 名（openpyxl 实测） =====

const L_SAMPLE_SHEETS = [
  // 索引
  '底稿目录',
  'GT_Custom',
  // 历史遗留
  '函证差异检查表（示例）',
  // 总控台
  '短期借款实质性程序表L1A',
  '长期借款实质性程序表L3A',
  '应付债券实质性程序表L4A ', // 末尾空格
  '实质性程序表L8A',
  // 审定表
  '审定表L1-1',
  '审定表L3-1',
  '审定表L5-1',
  '审定表L8-1',
  // 明细表
  '明细表L1-2',
  '明细表L3-2',
  '明细表L5-2',
  '明细表L6-2',
  '明细表L8-2',
  // 分析程序
  '分析程序L1-3',
  '分析程序L3-3',
  // 利息测算
  '利息测算表L1-5',
  '利息测算表L3-5',
  // 检查表
  '逾期贷款检查表L1-6',
  '摊余成本计算表L5-3',
  // 附注+调整
  '附注披露信息(上市公司)',
  '附注披露信息(国企)',
  '附注披露信息（上市公司）',
  '附注披露信息（国企）',
  '附注披露信息（国有企业）',
  '调整分录汇总L1-4',
  '调整分录汇总L8-3',
  // 其他
  '会计提示',
]

// ===== 预期分类（关键代表） =====

const EXPECTED: Record<string, string> = {
  // 索引
  '底稿目录': '索引',
  'GT_Custom': '索引',
  // 历史遗留
  '函证差异检查表（示例）': '历史遗留',
  // 总控台
  '短期借款实质性程序表L1A': '总控台',
  '长期借款实质性程序表L3A': '总控台',
  '应付债券实质性程序表L4A ': '总控台', // 末尾空格
  '实质性程序表L8A': '总控台',
  // 审定表
  '审定表L1-1': '审定表',
  '审定表L3-1': '审定表',
  '审定表L5-1': '审定表',
  '审定表L8-1': '审定表',
  // 明细表
  '明细表L1-2': '明细表',
  '明细表L3-2': '明细表',
  '明细表L5-2': '明细表',
  '明细表L6-2': '明细表',
  '明细表L8-2': '明细表',
  // 分析程序
  '分析程序L1-3': '分析程序',
  '分析程序L3-3': '分析程序',
  // 利息测算
  '利息测算表L1-5': '利息测算',
  '利息测算表L3-5': '利息测算',
  // 检查表
  '逾期贷款检查表L1-6': '检查表',
  '摊余成本计算表L5-3': '检查表',
  // 附注+调整
  '附注披露信息(上市公司)': '附注+调整',
  '附注披露信息(国企)': '附注+调整',
  '附注披露信息（上市公司）': '附注+调整',
  '附注披露信息（国企）': '附注+调整',
  '附注披露信息（国有企业）': '附注+调整',
  '调整分录汇总L1-4': '附注+调整',
  '调整分录汇总L8-3': '附注+调整',
  // 其他
  '会计提示': '其他程序',
}

// ===== 结构性校验 =====

describe('L_SHEET_GROUP_RULES — 结构性校验', () => {
  it('规则数组共 10 条（9 显式类 + 1 fallback），按 priority 升序排列', () => {
    expect(L_SHEET_GROUP_RULES).toHaveLength(10)
    for (let i = 1; i < L_SHEET_GROUP_RULES.length; i++) {
      expect(L_SHEET_GROUP_RULES[i].priority).toBeGreaterThanOrEqual(
        L_SHEET_GROUP_RULES[i - 1].priority,
      )
    }
    expect(L_SHEET_GROUP_RULES[0].id).toBe('index')
    expect(L_SHEET_GROUP_RULES[0].priority).toBe(0)
    expect(L_SHEET_GROUP_RULES[L_SHEET_GROUP_RULES.length - 1].id).toBe('other')
    expect(L_SHEET_GROUP_RULES[L_SHEET_GROUP_RULES.length - 1].priority).toBe(9)
  })

  it('每条规则 priority 全部唯一', () => {
    const priorities = L_SHEET_GROUP_RULES.map((r) => r.priority)
    expect(new Set(priorities).size).toBe(priorities.length)
  })

  it('规则 id 全部唯一', () => {
    const ids = L_SHEET_GROUP_RULES.map((r) => r.id)
    expect(new Set(ids).size).toBe(ids.length)
  })

  it('每条规则均含必需字段', () => {
    for (const r of L_SHEET_GROUP_RULES) {
      expect(typeof r.id).toBe('string')
      expect(typeof r.category).toBe('string')
      expect(typeof r.icon).toBe('string')
      expect(r.color).toMatch(/^#[0-9a-fA-F]{6}$/)
      expect(typeof r.priority).toBe('number')
      expect(typeof r.match).toBe('function')
    }
  })

  it('FALLBACK_GROUP 与末项规则一致', () => {
    const last = L_SHEET_GROUP_RULES[L_SHEET_GROUP_RULES.length - 1]
    expect(FALLBACK_GROUP.category).toBe(last.category)
    expect(FALLBACK_GROUP.priority).toBe(last.priority)
  })
})

// ===== 关键代表 sheet 分类验证 =====

describe('classifyLSheet — 关键代表 sheet 命中预期类别 (L-F2)', () => {
  it('每个关键代表 sheet 与 EXPECTED 映射一致', () => {
    for (const [name, expected] of Object.entries(EXPECTED)) {
      const result = classifyLSheet(name)
      expect(result.category, `sheet="${name}"`).toBe(expected)
    }
  })

  it('索引类 defaultHidden=true', () => {
    expect(classifyLSheet('底稿目录').defaultHidden).toBe(true)
    expect(classifyLSheet('GT_Custom').defaultHidden).toBe(true)
  })

  it('历史遗留类 defaultHidden=true', () => {
    expect(classifyLSheet('函证差异检查表（示例）').defaultHidden).toBe(true)
  })

  it('附注披露类 defaultHidden=true + readonly=true（5 种括号变体全覆盖）', () => {
    const variants = [
      '附注披露信息(上市公司)',
      '附注披露信息(国企)',
      '附注披露信息（上市公司）',
      '附注披露信息（国企）',
      '附注披露信息（国有企业）',
    ]
    for (const name of variants) {
      const r = classifyLSheet(name)
      expect(r.category, `sheet="${name}"`).toBe('附注+调整')
      expect(r.defaultHidden, `sheet="${name}" defaultHidden`).toBe(true)
      expect(r.readonly, `sheet="${name}" readonly`).toBe(true)
    }
  })

  it('调整分录类 defaultHidden=true 但 readonly 非 true', () => {
    const r = classifyLSheet('调整分录汇总L1-4')
    expect(r.category).toBe('附注+调整')
    expect(r.defaultHidden).toBe(true)
    // 调整分录不设 readonly（用户可编辑）
    expect(r.readonly).toBeFalsy()
  })

  it('利息测算 priority=6 优先于检查表 priority=7', () => {
    const r = classifyLSheet('利息测算表L1-5')
    expect(r.category).toBe('利息测算')
    expect(r.priority).toBe(6)
  })

  it('末尾空格 sheet 仍正确分类（L4A 末尾带空格）', () => {
    const r = classifyLSheet('应付债券实质性程序表L4A ')
    expect(r.category).toBe('总控台')
  })
})

// ===== 优先级冲突解决 =====

describe('classifyLSheet — 优先级冲突解决', () => {
  it('审定表(3) < 明细表(4)：含"审定表"的 sheet 优先匹配审定表', () => {
    expect(classifyLSheet('审定表L1-1').category).toBe('审定表')
    expect(classifyLSheet('审定表L1-1').priority).toBe(3)
  })

  it('总控台(2) < 审定表(3)：含"实质性程序表"的 sheet 优先匹配总控台', () => {
    expect(classifyLSheet('实质性程序表L1A').category).toBe('总控台')
    expect(classifyLSheet('实质性程序表L1A').priority).toBe(2)
  })

  it('利息测算(6) < 检查表(7)：含"利息测算"的 sheet 不被"检查表"误命中', () => {
    expect(classifyLSheet('利息测算表L1-5').category).toBe('利息测算')
  })

  it('明细表(4) < 分析程序(5)：含"明细表"的 sheet 优先匹配明细表', () => {
    expect(classifyLSheet('明细表L1-2').category).toBe('明细表')
  })
})

// ===== defaultHidden / readonly 标志验证 =====

describe('classifyLSheet — defaultHidden/readonly 标志', () => {
  it('索引类 defaultHidden=true', () => {
    expect(classifyLSheet('底稿目录').defaultHidden).toBe(true)
    expect(classifyLSheet('GT_Custom').defaultHidden).toBe(true)
    expect(classifyLSheet('修订说明').defaultHidden).toBe(true)
  })

  it('历史遗留类 defaultHidden=true', () => {
    expect(classifyLSheet('函证差异检查表（示例）').defaultHidden).toBe(true)
    expect(classifyLSheet('测试(示例)').defaultHidden).toBe(true)
  })

  it('附注+调整类 defaultHidden=true', () => {
    expect(classifyLSheet('附注披露信息(上市公司)').defaultHidden).toBe(true)
    expect(classifyLSheet('调整分录汇总L1-4').defaultHidden).toBe(true)
  })

  it('附注披露 readonly=true vs 调整分录 readonly=false', () => {
    // 附注披露 → readonly=true
    expect(classifyLSheet('附注披露信息(上市公司)').readonly).toBe(true)
    expect(classifyLSheet('附注披露信息（国企）').readonly).toBe(true)
    // 调整分录 → readonly 不为 true
    expect(classifyLSheet('调整分录汇总L1-4').readonly).toBeFalsy()
    expect(classifyLSheet('调整分录汇总L8-3').readonly).toBeFalsy()
  })

  it('总控台/审定表/明细表/分析程序/利息测算/检查表 defaultHidden 非 true', () => {
    const normalSheets = [
      '实质性程序表L1A',
      '审定表L1-1',
      '明细表L1-2',
      '分析程序L1-3',
      '利息测算表L1-5',
      '逾期贷款检查表L1-6',
    ]
    for (const name of normalSheets) {
      const r = classifyLSheet(name)
      expect(r.defaultHidden, `sheet="${name}" should not be hidden`).toBeFalsy()
    }
  })
})

// ===== 完备性 / fallback =====

describe('classifyLSheet — 完备性', () => {
  it('任意 sheet 名（含极端字符串）恒返回非 null 类目', () => {
    const edgeCases = ['', ' ', 'abc', '123', '!@#$%', 'A'.repeat(200), '中文']
    for (const name of edgeCases) {
      const cls = classifyLSheet(name)
      expect(cls).toBeDefined()
      expect(typeof cls.category).toBe('string')
      expect(cls.category.length).toBeGreaterThan(0)
    }
  })

  it('不匹配任何规则的 sheet 归入"其他程序"', () => {
    expect(classifyLSheet('随便的名字').category).toBe('其他程序')
    expect(classifyLSheet('').category).toBe('其他程序')
  })
})

// ===== composable 集成 =====

describe('useLDebtCycleSheetGroups — composable 行为', () => {
  function createMockUniverAPI(sheetNames: string[]) {
    const sheetObjects = sheetNames.map((name, idx) => ({
      getSheetId: () => `sid-${idx}`,
      getSheetName: () => name,
      isSheetHidden: () => false,
      activate: () => undefined,
    }))
    const wb = {
      getSheets: () => sheetObjects,
      getActiveSheet: () => sheetObjects[0],
      getId: () => 'unit1',
    }
    return {
      getActiveWorkbook: () => wb,
      executeCommand: async () => undefined,
    }
  }

  it('univerAPI 为 null 时 sheets 列表为空，无异常', () => {
    const apiRef = ref<any>(null)
    const nav = useLDebtCycleSheetGroups(apiRef)
    expect(() => nav.refresh()).not.toThrow()
    expect(nav.totalCount.value).toBe(0)
    expect(nav.groups.value).toEqual([])
  })

  it('refresh 后 defaultHidden sheet 被过滤（索引+历史遗留+附注披露+调整分录）', () => {
    const samples = [
      '底稿目录',
      'GT_Custom',
      '函证差异检查表（示例）',
      '附注披露信息(上市公司)',
      '附注披露信息（国企）',
      '调整分录汇总L1-4',
      '审定表L8-1',
      '明细表L8-2',
      '利息测算表L1-5',
    ]
    const apiRef = ref<any>(createMockUniverAPI(samples))
    const nav = useLDebtCycleSheetGroups(apiRef)
    nav.refresh()

    const names = nav.sheets.value.map((s) => s.name)
    // defaultHidden 的 sheet 被过滤
    expect(names).not.toContain('底稿目录')
    expect(names).not.toContain('GT_Custom')
    expect(names).not.toContain('函证差异检查表（示例）')
    expect(names).not.toContain('附注披露信息(上市公司)')
    expect(names).not.toContain('附注披露信息（国企）')
    expect(names).not.toContain('调整分录汇总L1-4')
    // 非 defaultHidden 的 sheet 保留
    expect(names).toContain('审定表L8-1')
    expect(names).toContain('明细表L8-2')
    expect(names).toContain('利息测算表L1-5')
  })

  it('groups 按 priority 升序排列', () => {
    const apiRef = ref<any>(createMockUniverAPI(L_SAMPLE_SHEETS))
    const nav = useLDebtCycleSheetGroups(apiRef)
    nav.refresh()

    const priorities = nav.groups.value.map((g) => g.priority)
    for (let i = 1; i < priorities.length; i++) {
      expect(priorities[i]).toBeGreaterThanOrEqual(priorities[i - 1])
    }
  })

  it('totalCount 仅计算非 hidden sheet', () => {
    const samples = [
      '底稿目录', // hidden
      '审定表L1-1', // visible
      '明细表L1-2', // visible
      '附注披露信息(上市公司)', // hidden
    ]
    const apiRef = ref<any>(createMockUniverAPI(samples))
    const nav = useLDebtCycleSheetGroups(apiRef)
    nav.refresh()
    expect(nav.totalCount.value).toBe(2)
  })
})
