/**
 * useNTaxCycleSheetGroups.spec.ts — N-F2 Task 2.2
 *
 * Validates: Requirements N-F2
 *
 * 验证 8 类分组规则对 N 循环 45 个有效 sheet 全覆盖（采样代表）：
 *   1. 索引 (priority=1, defaultHidden=true): 底稿目录 / GT_Custom
 *   2. 程序表 (priority=2): 含"程序表" 或 N*A 结尾
 *   3. 审定表 (priority=3): 含"审定表"
 *   4. 明细表 (priority=4): 含"明细表"
 *   5. 税费计算 (priority=5): 测算表 / 计算表 / 税费.*计算 / 应交.*税费
 *   6. 递延所得税 (priority=6): 递延所得税.*核对 / 递延.*费用
 *   7. 附注+调整 (priority=7, defaultHidden=true): 附注披露 / 调整分录
 *   8. 其他 (priority=99): fallback
 */
import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import {
  classifyNSheet,
  N_SHEET_GROUP_RULES,
  FALLBACK_GROUP,
  useNTaxCycleSheetGroups,
} from '../useNTaxCycleSheetGroups'

// ===== N 循环代表 sheet 名（openpyxl 实测） =====

const N_SAMPLE_SHEETS = [
  // 索引
  '底稿目录',
  'GT_Custom',
  // 程序表
  '递延所得税资产实质性程序表N1A',
  '应交税费实质性程序表N2A',
  '递延所得税负债实质性程序表N3A',
  '税金及附加审计程序表N4A ', // 末尾空格
  '所得税费用实质性程序表N5A',
  // 审定表
  '审定表N1-1',
  '审定表N2-1',
  '审定表N3-1',
  '审定表N4-1',
  '审定表N5-1',
  // 明细表
  '明细表N1-2',
  '明细表N2-2',
  '明细表N3-2',
  '明细表N4-2',
  '明细表N5-2',
  // 税费计算
  '应交其他税费测算表N2-8',
  '当期所得税费用计算表N5-4',
  // 递延所得税
  '递延所得税费用核对表N5-8',
  // 附注+调整
  '附注披露信息(上市公司)',
  '附注披露信息(国企)',
  '附注披露信息（上市公司）',
  '附注披露信息（国企）',
  '附注披露信息（国有企业）',
  // 其他
  '会计提示',
]

// ===== 预期分类（关键代表） =====

const EXPECTED: Record<string, string> = {
  // 索引
  底稿目录: '索引',
  GT_Custom: '索引',
  // 程序表
  递延所得税资产实质性程序表N1A: '程序表',
  应交税费实质性程序表N2A: '程序表',
  递延所得税负债实质性程序表N3A: '程序表',
  '税金及附加审计程序表N4A ': '程序表', // 末尾空格
  所得税费用实质性程序表N5A: '程序表',
  // 审定表
  '审定表N1-1': '审定表',
  '审定表N2-1': '审定表',
  '审定表N3-1': '审定表',
  '审定表N4-1': '审定表',
  '审定表N5-1': '审定表',
  // 明细表
  '明细表N1-2': '明细表',
  '明细表N2-2': '明细表',
  '明细表N3-2': '明细表',
  '明细表N4-2': '明细表',
  '明细表N5-2': '明细表',
  // 税费计算
  '应交其他税费测算表N2-8': '税费计算',
  '当期所得税费用计算表N5-4': '税费计算',
  // 递延所得税
  '递延所得税费用核对表N5-8': '递延所得税',
  // 附注+调整
  '附注披露信息(上市公司)': '附注+调整',
  '附注披露信息(国企)': '附注+调整',
  '附注披露信息（上市公司）': '附注+调整',
  '附注披露信息（国企）': '附注+调整',
  '附注披露信息（国有企业）': '附注+调整',
  // 其他
  会计提示: '其他',
}

// ===== 结构性校验 =====

describe('N_SHEET_GROUP_RULES — 结构性校验', () => {
  it('规则数组共 8 条（7 显式类 + 1 fallback），按 priority 升序排列', () => {
    expect(N_SHEET_GROUP_RULES).toHaveLength(8)
    for (let i = 1; i < N_SHEET_GROUP_RULES.length; i++) {
      expect(N_SHEET_GROUP_RULES[i].priority).toBeGreaterThanOrEqual(
        N_SHEET_GROUP_RULES[i - 1].priority,
      )
    }
    expect(N_SHEET_GROUP_RULES[0].id).toBe('index')
    expect(N_SHEET_GROUP_RULES[0].priority).toBe(1)
    expect(N_SHEET_GROUP_RULES[N_SHEET_GROUP_RULES.length - 1].id).toBe('other')
    expect(N_SHEET_GROUP_RULES[N_SHEET_GROUP_RULES.length - 1].priority).toBe(99)
  })

  it('规则 id 全部唯一', () => {
    const ids = N_SHEET_GROUP_RULES.map((r) => r.id)
    expect(new Set(ids).size).toBe(ids.length)
  })

  it('每条规则均含必需字段', () => {
    for (const r of N_SHEET_GROUP_RULES) {
      expect(typeof r.id).toBe('string')
      expect(typeof r.category).toBe('string')
      expect(typeof r.icon).toBe('string')
      expect(r.color).toMatch(/^#[0-9a-fA-F]{6}$/)
      expect(typeof r.priority).toBe('number')
      expect(typeof r.match).toBe('function')
    }
  })

  it('FALLBACK_GROUP 与末项规则一致', () => {
    const last = N_SHEET_GROUP_RULES[N_SHEET_GROUP_RULES.length - 1]
    expect(FALLBACK_GROUP.category).toBe(last.category)
    expect(FALLBACK_GROUP.priority).toBe(last.priority)
  })
})

// ===== 关键代表 sheet 分类验证 =====

describe('classifyNSheet — 关键代表 sheet 命中预期类别 (N-F2)', () => {
  it('每个关键代表 sheet 与 EXPECTED 映射一致', () => {
    for (const [name, expected] of Object.entries(EXPECTED)) {
      const result = classifyNSheet(name)
      expect(result.category, `sheet="${name}"`).toBe(expected)
    }
  })

  it('索引类 defaultHidden=true', () => {
    expect(classifyNSheet('底稿目录').defaultHidden).toBe(true)
    expect(classifyNSheet('GT_Custom').defaultHidden).toBe(true)
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
      const r = classifyNSheet(name)
      expect(r.category, `sheet="${name}"`).toBe('附注+调整')
      expect(r.defaultHidden, `sheet="${name}" defaultHidden`).toBe(true)
      expect(r.readonly, `sheet="${name}" readonly`).toBe(true)
    }
  })

  it('末尾空格 N4A sheet 仍正确分类为程序表', () => {
    expect(classifyNSheet('税金及附加审计程序表N4A ').category).toBe('程序表')
  })
})

// ===== 优先级冲突解决 =====

describe('classifyNSheet — 优先级冲突解决（首个命中即停止）', () => {
  it('程序表(2) < 审定表(3)：含"程序表"的 sheet 优先匹配程序表', () => {
    expect(classifyNSheet('应交税费实质性程序表N2A').category).toBe('程序表')
    expect(classifyNSheet('应交税费实质性程序表N2A').priority).toBe(2)
  })

  it('审定表(3) < 明细表(4)：含"审定表"的 sheet 优先匹配审定表', () => {
    expect(classifyNSheet('审定表N2-1').category).toBe('审定表')
    expect(classifyNSheet('审定表N2-1').priority).toBe(3)
  })

  it('明细表(4) < 税费计算(5)：含"明细表"的 sheet 优先匹配明细表', () => {
    expect(classifyNSheet('明细表N2-2').category).toBe('明细表')
    expect(classifyNSheet('明细表N2-2').priority).toBe(4)
  })

  it('税费计算(5) < 递延所得税(6)：含"测算表"的 sheet 优先匹配税费计算', () => {
    expect(classifyNSheet('应交其他税费测算表N2-8').category).toBe('税费计算')
    expect(classifyNSheet('应交其他税费测算表N2-8').priority).toBe(5)
  })

  it('递延所得税(6) < 附注+调整(7)：含"递延所得税.*核对"的 sheet 优先匹配递延所得税', () => {
    expect(classifyNSheet('递延所得税费用核对表N5-8').category).toBe('递延所得税')
    expect(classifyNSheet('递延所得税费用核对表N5-8').priority).toBe(6)
  })
})

// ===== defaultHidden / readonly 标志验证 =====

describe('classifyNSheet — defaultHidden/readonly 标志', () => {
  it('索引类 defaultHidden=true', () => {
    expect(classifyNSheet('底稿目录').defaultHidden).toBe(true)
    expect(classifyNSheet('GT_Custom').defaultHidden).toBe(true)
  })

  it('附注+调整类（附注披露）defaultHidden=true', () => {
    expect(classifyNSheet('附注披露信息(上市公司)').defaultHidden).toBe(true)
  })

  it('附注披露 readonly=true', () => {
    expect(classifyNSheet('附注披露信息(上市公司)').readonly).toBe(true)
    expect(classifyNSheet('附注披露信息（国企）').readonly).toBe(true)
  })

  it('程序表/审定表/明细表/税费计算/递延所得税 defaultHidden 非 true', () => {
    const normalSheets = [
      '应交税费实质性程序表N2A',
      '审定表N2-1',
      '明细表N2-2',
      '应交其他税费测算表N2-8',
      '递延所得税费用核对表N5-8',
    ]
    for (const name of normalSheets) {
      const r = classifyNSheet(name)
      expect(r.defaultHidden, `sheet="${name}" should not be hidden`).toBeFalsy()
    }
  })
})

// ===== 完备性 / fallback =====

describe('classifyNSheet — 完备性', () => {
  it('任意 sheet 名（含极端字符串）恒返回非 null 类目', () => {
    const edgeCases = ['', ' ', 'abc', '123', '!@#$%', 'A'.repeat(200), '中文']
    for (const name of edgeCases) {
      const cls = classifyNSheet(name)
      expect(cls).toBeDefined()
      expect(typeof cls.category).toBe('string')
      expect(cls.category.length).toBeGreaterThan(0)
    }
  })

  it('不匹配任何规则的 sheet 归入"其他"', () => {
    expect(classifyNSheet('随便的名字').category).toBe('其他')
    expect(classifyNSheet('').category).toBe('其他')
    expect(classifyNSheet('会计提示').category).toBe('其他')
  })

  it('每条规则至少匹配 1 个预期 sheet', () => {
    // 验证每条非 fallback 规则至少有 1 个代表 sheet 命中
    const ruleIds = N_SHEET_GROUP_RULES.filter((r) => r.id !== 'other').map(
      (r) => r.id,
    )
    const hitRuleIds = new Set<string>()
    for (const name of N_SAMPLE_SHEETS) {
      for (const rule of N_SHEET_GROUP_RULES) {
        if (rule.match(name)) {
          hitRuleIds.add(rule.id)
          break
        }
      }
    }
    for (const ruleId of ruleIds) {
      expect(hitRuleIds.has(ruleId), `rule "${ruleId}" should match at least 1 sample sheet`).toBe(
        true,
      )
    }
  })
})

// ===== composable 集成 =====

describe('useNTaxCycleSheetGroups — composable 行为', () => {
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
    const nav = useNTaxCycleSheetGroups(apiRef)
    expect(() => nav.refresh()).not.toThrow()
    expect(nav.totalCount.value).toBe(0)
    expect(nav.groups.value).toEqual([])
  })

  it('refresh 后 defaultHidden sheet 被过滤（索引+附注披露）', () => {
    const samples = [
      '底稿目录',
      'GT_Custom',
      '附注披露信息(上市公司)',
      '附注披露信息（国企）',
      '审定表N2-1',
      '明细表N2-2',
      '应交税费实质性程序表N2A',
    ]
    const apiRef = ref<any>(createMockUniverAPI(samples))
    const nav = useNTaxCycleSheetGroups(apiRef)
    nav.refresh()

    const names = nav.sheets.value.map((s) => s.name)
    // defaultHidden 的 sheet 被过滤
    expect(names).not.toContain('底稿目录')
    expect(names).not.toContain('GT_Custom')
    expect(names).not.toContain('附注披露信息(上市公司)')
    expect(names).not.toContain('附注披露信息（国企）')
    // 非 defaultHidden 的 sheet 保留
    expect(names).toContain('审定表N2-1')
    expect(names).toContain('明细表N2-2')
    expect(names).toContain('应交税费实质性程序表N2A')
  })

  it('groups 按 priority 升序排列', () => {
    const apiRef = ref<any>(createMockUniverAPI(N_SAMPLE_SHEETS))
    const nav = useNTaxCycleSheetGroups(apiRef)
    nav.refresh()

    const priorities = nav.groups.value.map((g) => g.priority)
    for (let i = 1; i < priorities.length; i++) {
      expect(priorities[i]).toBeGreaterThanOrEqual(priorities[i - 1])
    }
  })

  it('totalCount 仅计算非 hidden sheet', () => {
    const samples = [
      '底稿目录', // hidden
      '审定表N2-1', // visible
      '明细表N2-2', // visible
      '附注披露信息(上市公司)', // hidden
    ]
    const apiRef = ref<any>(createMockUniverAPI(samples))
    const nav = useNTaxCycleSheetGroups(apiRef)
    nav.refresh()
    expect(nav.totalCount.value).toBe(2)
  })

  it('switchTo 切换 activeSheetId', () => {
    const samples = ['审定表N2-1', '明细表N2-2']
    const apiRef = ref<any>(createMockUniverAPI(samples))
    const nav = useNTaxCycleSheetGroups(apiRef)
    nav.refresh()

    nav.switchTo('sid-1')
    expect(nav.activeSheetId.value).toBe('sid-1')
  })
})
