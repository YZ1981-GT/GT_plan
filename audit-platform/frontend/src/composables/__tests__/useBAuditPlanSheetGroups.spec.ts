/**
 * useBAuditPlanSheetGroups.spec.ts
 *
 * 验证 7 类分组规则对 B 循环 49 个模板文件全覆盖（采样代表）：
 *   1. 索引 (priority=1, defaultHidden=true): 底稿目录 / GT_Custom
 *   2. 风险评估 (priority=2): 风险评估表/业务承接/独立性/项目组讨论/汇总风险
 *   3. 了解环境 (priority=3): 了解被审计单位/访谈/分析程序/重要性
 *   4. 企业层面控制 (priority=4): B22系列
 *   5. 业务层面控制 (priority=5): B23系列
 *   6. 集团审计+项目管理 (priority=6): 集团审计/工时预算
 *   7. 其他 (priority=99): fallback
 */
import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import {
  classifyBSheet,
  B_SHEET_GROUP_RULES,
  FALLBACK_GROUP,
  useBAuditPlanSheetGroups,
} from '../useBAuditPlanSheetGroups'

// ===== B 循环代表 sheet 名 =====

const B_SAMPLE_SHEETS = [
  // 索引
  '底稿目录',
  'GT_Custom',
  // 风险评估
  '风险评估汇总表B1-1',
  '业务承接B1A',
  '独立性评价B1B',
  '项目组讨论B2',
  '重大错报风险B3',
  '总体审计策略B40',
  '舞弊风险评估B50',
  '舞弊风险应对B51',
  '舞弊风险评估程序B52',
  // 了解环境
  '了解被审计单位及其环境B10',
  '访谈记录B11',
  '行业分析B12',
  '法律法规B13',
  '初步分析程序B15',
  '关联方识别B18',
  '重要性水平B19',
  // 企业层面控制
  '企业层面控制了解B22',
  '控制环境评价表',
  '管理层凌驾控制测试',
  '信息与沟通评价',
  '监督评价表',
  '控制矩阵',
  '设计有效性评价',
  'IT概要表',
  '信息系统了解',
  'IT一般控制测试',
  // 业务层面控制
  '了解业务层面控制B23',
  '信息处理控制了解',
  '职责分离评价表',
  // 集团审计+项目管理
  '集团审计指引B30',
  '工时预算表B60',
  // 其他
  '会计提示',
  '审计总结',
]

// ===== 预期分类 =====

const EXPECTED: Record<string, string> = {
  底稿目录: '索引',
  GT_Custom: '索引',
  '风险评估汇总表B1-1': '风险评估',
  业务承接B1A: '风险评估',
  独立性评价B1B: '风险评估',
  项目组讨论B2: '风险评估',
  重大错报风险B3: '风险评估',
  总体审计策略B40: '风险评估',
  舞弊风险评估B50: '风险评估',
  舞弊风险应对B51: '风险评估',
  舞弊风险评估程序B52: '风险评估',
  '了解被审计单位及其环境B10': '了解环境',
  访谈记录B11: '了解环境',
  行业分析B12: '了解环境',
  法律法规B13: '了解环境',
  初步分析程序B15: '了解环境',
  关联方识别B18: '了解环境',
  重要性水平B19: '了解环境',
  企业层面控制了解B22: '企业层面控制',
  控制环境评价表: '企业层面控制',
  管理层凌驾控制测试: '企业层面控制',
  信息与沟通评价: '企业层面控制',
  监督评价表: '企业层面控制',
  控制矩阵: '企业层面控制',
  设计有效性评价: '企业层面控制',
  IT概要表: '企业层面控制',
  信息系统了解: '企业层面控制',
  IT一般控制测试: '企业层面控制',
  了解业务层面控制B23: '业务层面控制',
  信息处理控制了解: '业务层面控制',
  职责分离评价表: '业务层面控制',
  集团审计指引B30: '集团审计+项目管理',
  工时预算表B60: '集团审计+项目管理',
  会计提示: '其他',
  审计总结: '其他',
}

// ===== 结构性校验 =====

describe('B_SHEET_GROUP_RULES — 结构性校验', () => {
  it('规则数组共 7 条（6 显式类 + 1 fallback），按 priority 升序排列', () => {
    expect(B_SHEET_GROUP_RULES).toHaveLength(7)
    for (let i = 1; i < B_SHEET_GROUP_RULES.length; i++) {
      expect(B_SHEET_GROUP_RULES[i].priority).toBeGreaterThanOrEqual(
        B_SHEET_GROUP_RULES[i - 1].priority,
      )
    }
    expect(B_SHEET_GROUP_RULES[0].id).toBe('index')
    expect(B_SHEET_GROUP_RULES[0].priority).toBe(1)
    expect(B_SHEET_GROUP_RULES[B_SHEET_GROUP_RULES.length - 1].id).toBe('other')
    expect(B_SHEET_GROUP_RULES[B_SHEET_GROUP_RULES.length - 1].priority).toBe(99)
  })

  it('规则 id 全部唯一', () => {
    const ids = B_SHEET_GROUP_RULES.map((r) => r.id)
    expect(new Set(ids).size).toBe(ids.length)
  })

  it('每条规则均含必需字段', () => {
    for (const r of B_SHEET_GROUP_RULES) {
      expect(typeof r.id).toBe('string')
      expect(typeof r.category).toBe('string')
      expect(typeof r.icon).toBe('string')
      expect(r.color).toMatch(/^#[0-9a-fA-F]{6}$/)
      expect(typeof r.priority).toBe('number')
      expect(typeof r.match).toBe('function')
    }
  })

  it('FALLBACK_GROUP 与末项规则一致', () => {
    const last = B_SHEET_GROUP_RULES[B_SHEET_GROUP_RULES.length - 1]
    expect(FALLBACK_GROUP.category).toBe(last.category)
    expect(FALLBACK_GROUP.priority).toBe(last.priority)
  })
})

// ===== 关键代表 sheet 分类验证 =====

describe('classifyBSheet — 关键代表 sheet 命中预期类别', () => {
  it('每个关键代表 sheet 与 EXPECTED 映射一致', () => {
    for (const [name, expected] of Object.entries(EXPECTED)) {
      const result = classifyBSheet(name)
      expect(result.category, `sheet="${name}"`).toBe(expected)
    }
  })

  it('索引类 defaultHidden=true', () => {
    expect(classifyBSheet('底稿目录').defaultHidden).toBe(true)
    expect(classifyBSheet('GT_Custom').defaultHidden).toBe(true)
  })

  it('非索引类 defaultHidden 非 true', () => {
    const normalSheets = [
      '风险评估汇总表B1-1',
      '了解被审计单位及其环境B10',
      '企业层面控制了解B22',
      '了解业务层面控制B23',
      '集团审计指引B30',
    ]
    for (const name of normalSheets) {
      const r = classifyBSheet(name)
      expect(r.defaultHidden, `sheet="${name}" should not be hidden`).toBeFalsy()
    }
  })
})

// ===== 优先级冲突解决 =====

describe('classifyBSheet — 优先级冲突解决（首个命中即停止）', () => {
  it('风险评估(2) < 了解环境(3)：含"B1-"的 sheet 优先匹配风险评估', () => {
    expect(classifyBSheet('风险评估汇总表B1-1').category).toBe('风险评估')
    expect(classifyBSheet('风险评估汇总表B1-1').priority).toBe(2)
  })

  it('了解环境(3) < 企业层面控制(4)：含"B10"的 sheet 优先匹配了解环境', () => {
    expect(classifyBSheet('了解被审计单位及其环境B10').category).toBe('了解环境')
    expect(classifyBSheet('了解被审计单位及其环境B10').priority).toBe(3)
  })

  it('企业层面控制(4) < 业务层面控制(5)：含"B22"的 sheet 优先匹配企业层面控制', () => {
    expect(classifyBSheet('企业层面控制了解B22').category).toBe('企业层面控制')
    expect(classifyBSheet('企业层面控制了解B22').priority).toBe(4)
  })

  it('业务层面控制(5) < 集团审计(6)：含"B23"的 sheet 优先匹配业务层面控制', () => {
    expect(classifyBSheet('了解业务层面控制B23').category).toBe('业务层面控制')
    expect(classifyBSheet('了解业务层面控制B23').priority).toBe(5)
  })
})

// ===== 完备性 / fallback =====

describe('classifyBSheet — 完备性', () => {
  it('任意 sheet 名（含极端字符串）恒返回非 null 类目', () => {
    const edgeCases = ['', ' ', 'abc', '123', '!@#$%', 'A'.repeat(200), '中文']
    for (const name of edgeCases) {
      const cls = classifyBSheet(name)
      expect(cls).toBeDefined()
      expect(typeof cls.category).toBe('string')
      expect(cls.category.length).toBeGreaterThan(0)
    }
  })

  it('不匹配任何规则的 sheet 归入"其他"', () => {
    expect(classifyBSheet('随便的名字').category).toBe('其他')
    expect(classifyBSheet('').category).toBe('其他')
    expect(classifyBSheet('会计提示').category).toBe('其他')
    expect(classifyBSheet('审计总结').category).toBe('其他')
  })

  it('每条规则至少匹配 1 个预期 sheet', () => {
    const ruleIds = B_SHEET_GROUP_RULES.filter((r) => r.id !== 'other').map(
      (r) => r.id,
    )
    const hitRuleIds = new Set<string>()
    for (const name of B_SAMPLE_SHEETS) {
      for (const rule of B_SHEET_GROUP_RULES) {
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

describe('useBAuditPlanSheetGroups — composable 行为', () => {
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
    const nav = useBAuditPlanSheetGroups(apiRef)
    expect(() => nav.refresh()).not.toThrow()
    expect(nav.totalCount.value).toBe(0)
    expect(nav.groups.value).toEqual([])
  })

  it('refresh 后 defaultHidden sheet 被过滤（索引）', () => {
    const samples = [
      '底稿目录',
      'GT_Custom',
      '风险评估汇总表B1-1',
      '了解被审计单位及其环境B10',
      '企业层面控制了解B22',
    ]
    const apiRef = ref<any>(createMockUniverAPI(samples))
    const nav = useBAuditPlanSheetGroups(apiRef)
    nav.refresh()

    const names = nav.sheets.value.map((s) => s.name)
    expect(names).not.toContain('底稿目录')
    expect(names).not.toContain('GT_Custom')
    expect(names).toContain('风险评估汇总表B1-1')
    expect(names).toContain('了解被审计单位及其环境B10')
    expect(names).toContain('企业层面控制了解B22')
  })

  it('groups 按 priority 升序排列', () => {
    const apiRef = ref<any>(createMockUniverAPI(B_SAMPLE_SHEETS))
    const nav = useBAuditPlanSheetGroups(apiRef)
    nav.refresh()

    const priorities = nav.groups.value.map((g) => g.priority)
    for (let i = 1; i < priorities.length; i++) {
      expect(priorities[i]).toBeGreaterThanOrEqual(priorities[i - 1])
    }
  })

  it('totalCount 仅计算非 hidden sheet', () => {
    const samples = [
      '底稿目录', // hidden
      'GT_Custom', // hidden
      '风险评估汇总表B1-1', // visible
      '了解被审计单位及其环境B10', // visible
    ]
    const apiRef = ref<any>(createMockUniverAPI(samples))
    const nav = useBAuditPlanSheetGroups(apiRef)
    nav.refresh()
    expect(nav.totalCount.value).toBe(2)
  })

  it('switchTo 切换 activeSheetId', () => {
    const samples = ['风险评估汇总表B1-1', '了解被审计单位及其环境B10']
    const apiRef = ref<any>(createMockUniverAPI(samples))
    const nav = useBAuditPlanSheetGroups(apiRef)
    nav.refresh()

    nav.switchTo('sid-1')
    expect(nav.activeSheetId.value).toBe('sid-1')
  })
})
