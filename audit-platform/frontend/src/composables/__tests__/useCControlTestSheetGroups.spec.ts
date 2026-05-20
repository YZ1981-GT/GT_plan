/**
 * useCControlTestSheetGroups.spec.ts
 *
 * 验证 5 类分组规则对 C 循环 36 个模板文件全覆盖（采样代表）：
 *   1. 索引 (priority=1, defaultHidden=true): 底稿目录 / GT_Custom
 *   2. 企业层面控制测试 (priority=2): C1/C21~C26
 *   3. 业务循环控制测试 (priority=3): C2~C15 各循环控制测试
 *   4. 偏差评价 (priority=4): 各循环评价控制偏差（C*-2 系列）
 *   5. 其他 (priority=99): fallback
 */
import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import {
  classifyCSheet,
  C_SHEET_GROUP_RULES,
  FALLBACK_GROUP,
  useCControlTestSheetGroups,
} from '../useCControlTestSheetGroups'

// ===== C 循环代表 sheet 名 =====

const C_SAMPLE_SHEETS = [
  // 索引
  '底稿目录',
  'GT_Custom',
  // 企业层面控制测试
  '企业层面控制测试C1',
  'IT一般控制测试',
  '会计分录测试',
  '内审评价',
  '信息处理控制测试',
  // 业务循环控制测试
  '销售循环控制测试C2',
  '货币资金循环控制测试C3',
  '采购循环控制测试C4',
  '投资循环控制测试C5',
  '固定资产循环控制测试C6',
  '在建工程循环控制测试C7',
  '无形资产循环控制测试C8',
  '研发循环控制测试C9',
  '薪酬循环控制测试C10',
  '管理循环控制测试C11',
  '税金循环控制测试C12',
  '债务循环控制测试C13',
  '租赁循环控制测试C14',
  '关联方循环控制测试C15',
  // 偏差评价
  '控制偏差评价C2-2',
  '控制偏差评价C3-2',
  '控制偏差评价C4-2',
  '控制偏差评价C10-2',
  '控制偏差评价C15-2',
  // 其他
  '会计提示',
  '审计总结',
]

// ===== 预期分类 =====

const EXPECTED: Record<string, string> = {
  底稿目录: '索引',
  GT_Custom: '索引',
  企业层面控制测试C1: '企业层面控制测试',
  IT一般控制测试: '企业层面控制测试',
  会计分录测试: '企业层面控制测试',
  内审评价: '企业层面控制测试',
  信息处理控制测试: '企业层面控制测试',
  销售循环控制测试C2: '业务循环控制测试',
  货币资金循环控制测试C3: '业务循环控制测试',
  采购循环控制测试C4: '业务循环控制测试',
  投资循环控制测试C5: '业务循环控制测试',
  固定资产循环控制测试C6: '业务循环控制测试',
  在建工程循环控制测试C7: '业务循环控制测试',
  无形资产循环控制测试C8: '业务循环控制测试',
  研发循环控制测试C9: '业务循环控制测试',
  薪酬循环控制测试C10: '业务循环控制测试',
  管理循环控制测试C11: '业务循环控制测试',
  税金循环控制测试C12: '业务循环控制测试',
  债务循环控制测试C13: '业务循环控制测试',
  租赁循环控制测试C14: '业务循环控制测试',
  关联方循环控制测试C15: '业务循环控制测试',
  '控制偏差评价C2-2': '偏差评价',
  '控制偏差评价C3-2': '偏差评价',
  '控制偏差评价C4-2': '偏差评价',
  '控制偏差评价C10-2': '偏差评价',
  '控制偏差评价C15-2': '偏差评价',
  会计提示: '其他',
  审计总结: '其他',
}

// ===== 结构性校验 =====

describe('C_SHEET_GROUP_RULES — 结构性校验', () => {
  it('规则数组共 5 条（4 显式类 + 1 fallback），按 priority 升序排列', () => {
    expect(C_SHEET_GROUP_RULES).toHaveLength(5)
    for (let i = 1; i < C_SHEET_GROUP_RULES.length; i++) {
      expect(C_SHEET_GROUP_RULES[i].priority).toBeGreaterThanOrEqual(
        C_SHEET_GROUP_RULES[i - 1].priority,
      )
    }
    expect(C_SHEET_GROUP_RULES[0].id).toBe('index')
    expect(C_SHEET_GROUP_RULES[0].priority).toBe(1)
    expect(C_SHEET_GROUP_RULES[C_SHEET_GROUP_RULES.length - 1].id).toBe('other')
    expect(C_SHEET_GROUP_RULES[C_SHEET_GROUP_RULES.length - 1].priority).toBe(99)
  })

  it('规则 id 全部唯一', () => {
    const ids = C_SHEET_GROUP_RULES.map((r) => r.id)
    expect(new Set(ids).size).toBe(ids.length)
  })

  it('每条规则均含必需字段', () => {
    for (const r of C_SHEET_GROUP_RULES) {
      expect(typeof r.id).toBe('string')
      expect(typeof r.category).toBe('string')
      expect(typeof r.icon).toBe('string')
      expect(r.color).toMatch(/^#[0-9a-fA-F]{6}$/)
      expect(typeof r.priority).toBe('number')
      expect(typeof r.match).toBe('function')
    }
  })

  it('FALLBACK_GROUP 与末项规则一致', () => {
    const last = C_SHEET_GROUP_RULES[C_SHEET_GROUP_RULES.length - 1]
    expect(FALLBACK_GROUP.category).toBe(last.category)
    expect(FALLBACK_GROUP.priority).toBe(last.priority)
  })
})

// ===== 关键代表 sheet 分类验证 =====

describe('classifyCSheet — 关键代表 sheet 命中预期类别', () => {
  it('每个关键代表 sheet 与 EXPECTED 映射一致', () => {
    for (const [name, expected] of Object.entries(EXPECTED)) {
      const result = classifyCSheet(name)
      expect(result.category, `sheet="${name}"`).toBe(expected)
    }
  })

  it('索引类 defaultHidden=true', () => {
    expect(classifyCSheet('底稿目录').defaultHidden).toBe(true)
    expect(classifyCSheet('GT_Custom').defaultHidden).toBe(true)
  })

  it('非索引类 defaultHidden 非 true', () => {
    const normalSheets = [
      '企业层面控制测试C1',
      '销售循环控制测试C2',
      '控制偏差评价C2-2',
    ]
    for (const name of normalSheets) {
      const r = classifyCSheet(name)
      expect(r.defaultHidden, `sheet="${name}" should not be hidden`).toBeFalsy()
    }
  })
})

// ===== 优先级冲突解决 =====

describe('classifyCSheet — 优先级冲突解决（首个命中即停止）', () => {
  it('企业层面控制测试(2) < 业务循环控制测试(3)：含"C1\\b"的 sheet 优先匹配企业层面', () => {
    expect(classifyCSheet('企业层面控制测试C1').category).toBe('企业层面控制测试')
    expect(classifyCSheet('企业层面控制测试C1').priority).toBe(2)
  })

  it('业务循环控制测试(3) < 偏差评价(4)：含"C2\\b"的 sheet 优先匹配业务循环', () => {
    expect(classifyCSheet('销售循环控制测试C2').category).toBe('业务循环控制测试')
    expect(classifyCSheet('销售循环控制测试C2').priority).toBe(3)
  })

  it('偏差评价(4)：含"C\\d+-2"的 sheet 匹配偏差评价', () => {
    expect(classifyCSheet('控制偏差评价C2-2').category).toBe('偏差评价')
    expect(classifyCSheet('控制偏差评价C2-2').priority).toBe(4)
  })

  it('C10~C15 匹配业务循环控制测试', () => {
    expect(classifyCSheet('薪酬循环控制测试C10').category).toBe('业务循环控制测试')
    expect(classifyCSheet('关联方循环控制测试C15').category).toBe('业务循环控制测试')
  })

  it('C10-2/C15-2 匹配偏差评价', () => {
    expect(classifyCSheet('控制偏差评价C10-2').category).toBe('偏差评价')
    expect(classifyCSheet('控制偏差评价C15-2').category).toBe('偏差评价')
  })
})

// ===== 完备性 / fallback =====

describe('classifyCSheet — 完备性', () => {
  it('任意 sheet 名（含极端字符串）恒返回非 null 类目', () => {
    const edgeCases = ['', ' ', 'abc', '123', '!@#$%', 'A'.repeat(200), '中文']
    for (const name of edgeCases) {
      const cls = classifyCSheet(name)
      expect(cls).toBeDefined()
      expect(typeof cls.category).toBe('string')
      expect(cls.category.length).toBeGreaterThan(0)
    }
  })

  it('不匹配任何规则的 sheet 归入"其他"', () => {
    expect(classifyCSheet('随便的名字').category).toBe('其他')
    expect(classifyCSheet('').category).toBe('其他')
    expect(classifyCSheet('会计提示').category).toBe('其他')
    expect(classifyCSheet('审计总结').category).toBe('其他')
  })

  it('每条规则至少匹配 1 个预期 sheet', () => {
    const ruleIds = C_SHEET_GROUP_RULES.filter((r) => r.id !== 'other').map(
      (r) => r.id,
    )
    const hitRuleIds = new Set<string>()
    for (const name of C_SAMPLE_SHEETS) {
      for (const rule of C_SHEET_GROUP_RULES) {
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

describe('useCControlTestSheetGroups — composable 行为', () => {
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
    const nav = useCControlTestSheetGroups(apiRef)
    expect(() => nav.refresh()).not.toThrow()
    expect(nav.totalCount.value).toBe(0)
    expect(nav.groups.value).toEqual([])
  })

  it('refresh 后 defaultHidden sheet 被过滤（索引）', () => {
    const samples = [
      '底稿目录',
      'GT_Custom',
      '企业层面控制测试C1',
      '销售循环控制测试C2',
      '控制偏差评价C2-2',
    ]
    const apiRef = ref<any>(createMockUniverAPI(samples))
    const nav = useCControlTestSheetGroups(apiRef)
    nav.refresh()

    const names = nav.sheets.value.map((s) => s.name)
    expect(names).not.toContain('底稿目录')
    expect(names).not.toContain('GT_Custom')
    expect(names).toContain('企业层面控制测试C1')
    expect(names).toContain('销售循环控制测试C2')
    expect(names).toContain('控制偏差评价C2-2')
  })

  it('groups 按 priority 升序排列', () => {
    const apiRef = ref<any>(createMockUniverAPI(C_SAMPLE_SHEETS))
    const nav = useCControlTestSheetGroups(apiRef)
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
      '企业层面控制测试C1', // visible
      '销售循环控制测试C2', // visible
      '控制偏差评价C2-2', // visible
    ]
    const apiRef = ref<any>(createMockUniverAPI(samples))
    const nav = useCControlTestSheetGroups(apiRef)
    nav.refresh()
    expect(nav.totalCount.value).toBe(3)
  })

  it('switchTo 切换 activeSheetId', () => {
    const samples = ['企业层面控制测试C1', '销售循环控制测试C2']
    const apiRef = ref<any>(createMockUniverAPI(samples))
    const nav = useCControlTestSheetGroups(apiRef)
    nav.refresh()

    nav.switchTo('sid-1')
    expect(nav.activeSheetId.value).toBe('sid-1')
  })
})
