/**
 * useJPayrollSheetGroups.spec.ts — J-F2 Task 2.2
 *
 * Validates: Requirements J-F2
 *
 * 验证 8 类分组规则对 J 循环 29 个有效 sheet 全覆盖：
 *   1. 索引（底稿目录/GT_Custom）→ defaultHidden=true
 *   2. 程序表（实质性程序表/xxA 结尾）
 *   3. 审定表（审定表/情况表）
 *   4. 明细表
 *   5. 分析程序（分析/对比）
 *   6. 检查表（检查表/计提情况/分配情况）
 *   7. IPO专项（IPO/首发）
 *   8. 附注+调整（附注披露/调整分录）→ 附注 defaultHidden=true
 *   9. 其他（fallback）
 */
import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import {
  classifyJSheet,
  J_SHEET_GROUP_RULES,
  FALLBACK_GROUP,
  useJPayrollSheetGroups,
} from '../useJPayrollSheetGroups'

// ===== J 循环 29 个有效 sheet 名（openpyxl 实测） =====

const J_VALID_SHEETS = [
  '应付职工薪酬实质性程序表 J1A',
  '应付职工薪酬实质性程序表 J1A-原版',
  '应付职工薪酬实质性程序表 L1A-原',
  '审定表J1-1 ',
  '附注披露信息（上市公司）',
  '附注披露信息（国有企业）',
  '明细表J1-2 ',
  '调整分录汇总表J1-3',
  '月度分析表J1-4',
  '与同行业对比分析表J1-5',
  '计提情况检查表J1-6',
  '分配情况检查表J1-7',
  '检查表J1-8',
  '非货币性福利检查表J1-9',
  '辞退福利检查表J1-10',
  'IPO企业薪酬审计提示',
  'GT_Custom',
  '长期应付职工薪酬实质性程序表 J2A',
  '长期应付职工薪酬实质性程序表 L2A',
  '审定表J2-1',
  '明细表J2-2',
  '调整分录汇总表J2-3',
  '计提情况检查表J2-4',
  '股份支付实质性程序表 J3A',
  '股份支付情况表J3-1',
  '股份支付检查表J3-2',
  'IPO企业股权激励工具关注的审计重点',
  '首发业务解答二',
  '底稿目录',
]

// ===== 预期分类映射 =====

const EXPECTED: Record<string, string> = {
  // 索引
  GT_Custom: '索引',
  底稿目录: '索引',
  // 程序表
  '应付职工薪酬实质性程序表 J1A': '程序表',
  '应付职工薪酬实质性程序表 J1A-原版': '程序表',
  '应付职工薪酬实质性程序表 L1A-原': '程序表',
  '长期应付职工薪酬实质性程序表 J2A': '程序表',
  '长期应付职工薪酬实质性程序表 L2A': '程序表',
  '股份支付实质性程序表 J3A': '程序表',
  // 审定表
  '审定表J1-1 ': '审定表',
  '审定表J2-1': '审定表',
  '股份支付情况表J3-1': '审定表',
  // 明细表
  '明细表J1-2 ': '明细表',
  '明细表J2-2': '明细表',
  // 分析程序
  '月度分析表J1-4': '分析程序',
  '与同行业对比分析表J1-5': '分析程序',
  // 检查表
  '计提情况检查表J1-6': '检查表',
  '分配情况检查表J1-7': '检查表',
  '检查表J1-8': '检查表',
  '非货币性福利检查表J1-9': '检查表',
  '辞退福利检查表J1-10': '检查表',
  '股份支付检查表J3-2': '检查表',
  '计提情况检查表J2-4': '检查表',
  // IPO专项
  'IPO企业薪酬审计提示': 'IPO专项',
  'IPO企业股权激励工具关注的审计重点': 'IPO专项',
  '首发业务解答二': 'IPO专项',
  // 附注+调整
  '附注披露信息（上市公司）': '附注+调整',
  '附注披露信息（国有企业）': '附注+调整',
  '调整分录汇总表J1-3': '附注+调整',
  '调整分录汇总表J2-3': '附注+调整',
}

// ===== 结构性校验 =====

describe('J_SHEET_GROUP_RULES — 结构性校验', () => {
  it('规则数组共 9 条（8 显式类 + 1 fallback），按 priority 升序排列', () => {
    expect(J_SHEET_GROUP_RULES).toHaveLength(9)
    for (let i = 1; i < J_SHEET_GROUP_RULES.length; i++) {
      expect(J_SHEET_GROUP_RULES[i].priority).toBeGreaterThan(
        J_SHEET_GROUP_RULES[i - 1].priority,
      )
    }
    expect(J_SHEET_GROUP_RULES[0].id).toBe('index')
    expect(J_SHEET_GROUP_RULES[0].priority).toBe(0)
    expect(J_SHEET_GROUP_RULES[J_SHEET_GROUP_RULES.length - 1].id).toBe('other')
    expect(J_SHEET_GROUP_RULES[J_SHEET_GROUP_RULES.length - 1].priority).toBe(8)
  })

  it('规则 id 全部唯一', () => {
    const ids = J_SHEET_GROUP_RULES.map((r) => r.id)
    expect(new Set(ids).size).toBe(ids.length)
  })

  it('每条规则均含必需字段', () => {
    for (const r of J_SHEET_GROUP_RULES) {
      expect(typeof r.id).toBe('string')
      expect(typeof r.category).toBe('string')
      expect(typeof r.icon).toBe('string')
      expect(r.color).toMatch(/^#[0-9a-fA-F]{6}$/)
      expect(typeof r.priority).toBe('number')
      expect(typeof r.match).toBe('function')
    }
  })

  it('FALLBACK_GROUP 与末项规则一致', () => {
    const last = J_SHEET_GROUP_RULES[J_SHEET_GROUP_RULES.length - 1]
    expect(FALLBACK_GROUP.category).toBe(last.category)
    expect(FALLBACK_GROUP.priority).toBe(last.priority)
  })
})

// ===== 8 类规则全覆盖 29 sheet =====

describe('classifyJSheet — 8 类规则全覆盖 29 个有效 sheet (J-F2)', () => {
  it('29 个有效 sheet 全部被分类且与预期一致', () => {
    expect(J_VALID_SHEETS).toHaveLength(29)
    for (const sheet of J_VALID_SHEETS) {
      const result = classifyJSheet(sheet)
      const expected = EXPECTED[sheet]
      expect(expected).toBeDefined()
      expect(result.category).toBe(expected)
    }
  })

  it('无 sheet 归入 fallback "其他"', () => {
    for (const sheet of J_VALID_SHEETS) {
      const result = classifyJSheet(sheet)
      expect(result.category).not.toBe('其他')
    }
  })

  it('索引类 defaultHidden=true', () => {
    expect(classifyJSheet('底稿目录').defaultHidden).toBe(true)
    expect(classifyJSheet('GT_Custom').defaultHidden).toBe(true)
  })

  it('附注披露类 defaultHidden=true', () => {
    expect(classifyJSheet('附注披露信息（上市公司）').defaultHidden).toBe(true)
    expect(classifyJSheet('附注披露信息（国有企业）').defaultHidden).toBe(true)
  })

  it('调整分录类 defaultHidden=false（不隐藏）', () => {
    const result = classifyJSheet('调整分录汇总表J1-3')
    expect(result.category).toBe('附注+调整')
    expect(result.defaultHidden).toBeFalsy()
  })
})

// ===== 各类代表性 sheet 命中验证 =====

describe('classifyJSheet — 各类代表性 sheet 命中', () => {
  it('类 1 索引：底稿目录 / GT_Custom', () => {
    expect(classifyJSheet('底稿目录').category).toBe('索引')
    expect(classifyJSheet('GT_Custom').category).toBe('索引')
  })

  it('类 2 程序表：实质性程序表 / xxA 结尾 / xxA- / L1A-原', () => {
    expect(classifyJSheet('应付职工薪酬实质性程序表 J1A').category).toBe('程序表')
    expect(classifyJSheet('应付职工薪酬实质性程序表 J1A-原版').category).toBe('程序表')
    expect(classifyJSheet('应付职工薪酬实质性程序表 L1A-原').category).toBe('程序表')
    expect(classifyJSheet('长期应付职工薪酬实质性程序表 J2A').category).toBe('程序表')
    expect(classifyJSheet('长期应付职工薪酬实质性程序表 L2A').category).toBe('程序表')
    expect(classifyJSheet('股份支付实质性程序表 J3A').category).toBe('程序表')
  })

  it('类 3 审定表：审定表 / 情况表', () => {
    expect(classifyJSheet('审定表J1-1 ').category).toBe('审定表')
    expect(classifyJSheet('审定表J2-1').category).toBe('审定表')
    expect(classifyJSheet('股份支付情况表J3-1').category).toBe('审定表')
  })

  it('类 4 明细表', () => {
    expect(classifyJSheet('明细表J1-2 ').category).toBe('明细表')
    expect(classifyJSheet('明细表J2-2').category).toBe('明细表')
  })

  it('类 5 分析程序：分析 / 对比', () => {
    expect(classifyJSheet('月度分析表J1-4').category).toBe('分析程序')
    expect(classifyJSheet('与同行业对比分析表J1-5').category).toBe('分析程序')
  })

  it('类 6 检查表：检查表 / 计提情况 / 分配情况', () => {
    expect(classifyJSheet('计提情况检查表J1-6').category).toBe('检查表')
    expect(classifyJSheet('分配情况检查表J1-7').category).toBe('检查表')
    expect(classifyJSheet('检查表J1-8').category).toBe('检查表')
    expect(classifyJSheet('非货币性福利检查表J1-9').category).toBe('检查表')
    expect(classifyJSheet('辞退福利检查表J1-10').category).toBe('检查表')
    expect(classifyJSheet('股份支付检查表J3-2').category).toBe('检查表')
    expect(classifyJSheet('计提情况检查表J2-4').category).toBe('检查表')
  })

  it('类 7 IPO专项：IPO / 首发', () => {
    expect(classifyJSheet('IPO企业薪酬审计提示').category).toBe('IPO专项')
    expect(classifyJSheet('IPO企业股权激励工具关注的审计重点').category).toBe('IPO专项')
    expect(classifyJSheet('首发业务解答二').category).toBe('IPO专项')
  })

  it('类 8 附注+调整：附注披露 / 调整分录', () => {
    expect(classifyJSheet('附注披露信息（上市公司）').category).toBe('附注+调整')
    expect(classifyJSheet('附注披露信息（国有企业）').category).toBe('附注+调整')
    expect(classifyJSheet('调整分录汇总表J1-3').category).toBe('附注+调整')
    expect(classifyJSheet('调整分录汇总表J2-3').category).toBe('附注+调整')
  })
})

// ===== 优先级冲突解决 =====

describe('classifyJSheet — 优先级冲突解决', () => {
  it('"计提情况检查表J1-6" 含"检查表"和"计提情况" → 归入检查表(5)', () => {
    expect(classifyJSheet('计提情况检查表J1-6').category).toBe('检查表')
  })

  it('"月度分析表J1-4" 含"分析" → 归入分析程序(4)，不被明细表(3)误匹配', () => {
    expect(classifyJSheet('月度分析表J1-4').category).toBe('分析程序')
  })

  it('"股份支付情况表J3-1" 含"情况表" → 归入审定表(2)，不被检查表(5)误匹配', () => {
    expect(classifyJSheet('股份支付情况表J3-1').category).toBe('审定表')
  })

  it('末尾带空格的 sheet 名正确分类', () => {
    expect(classifyJSheet('审定表J1-1 ').category).toBe('审定表')
    expect(classifyJSheet('明细表J1-2 ').category).toBe('明细表')
  })
})

// ===== 完备性：fallback 兜底 =====

describe('classifyJSheet — 完备性', () => {
  it('任意 sheet 名（含极端字符串）恒返回非 null 类目', () => {
    const edgeCases = ['', ' ', 'abc', '123', '!@#$%', 'A'.repeat(200), '中文']
    for (const name of edgeCases) {
      const cls = classifyJSheet(name)
      expect(cls).toBeDefined()
      expect(typeof cls.category).toBe('string')
      expect(cls.category.length).toBeGreaterThan(0)
    }
  })

  it('不匹配任何规则的 sheet 归入"其他"', () => {
    expect(classifyJSheet('随便的名字').category).toBe('其他')
    expect(classifyJSheet('').category).toBe('其他')
  })
})

// ===== composable 集成 =====

describe('useJPayrollSheetGroups — composable 行为', () => {
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
    const nav = useJPayrollSheetGroups(apiRef)
    expect(() => nav.refresh()).not.toThrow()
    expect(nav.totalCount.value).toBe(0)
    expect(nav.groups.value).toEqual([])
  })

  it('refresh 后 defaultHidden sheet 被过滤（索引+附注披露）', () => {
    const apiRef = ref<any>(createMockUniverAPI(J_VALID_SHEETS))
    const nav = useJPayrollSheetGroups(apiRef)
    nav.refresh()

    const names = nav.sheets.value.map((s) => s.name)
    // 索引类被过滤
    expect(names).not.toContain('底稿目录')
    expect(names).not.toContain('GT_Custom')
    // 附注披露类被过滤
    expect(names).not.toContain('附注披露信息（上市公司）')
    expect(names).not.toContain('附注披露信息（国有企业）')
    // 调整分录不被过滤
    expect(names).toContain('调整分录汇总表J1-3')
    expect(names).toContain('调整分录汇总表J2-3')
  })

  it('groups 按 priority 升序排列', () => {
    const apiRef = ref<any>(createMockUniverAPI(J_VALID_SHEETS))
    const nav = useJPayrollSheetGroups(apiRef)
    nav.refresh()

    const priorities = nav.groups.value.map((g) => g.priority)
    for (let i = 1; i < priorities.length; i++) {
      expect(priorities[i]).toBeGreaterThanOrEqual(priorities[i - 1])
    }
  })

  it('过滤后 totalCount = 29 - 4（2 索引 + 2 附注披露）= 25', () => {
    const apiRef = ref<any>(createMockUniverAPI(J_VALID_SHEETS))
    const nav = useJPayrollSheetGroups(apiRef)
    nav.refresh()

    // 29 total - 2 index - 2 disclosure = 25 visible
    expect(nav.totalCount.value).toBe(25)
  })
})
