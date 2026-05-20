/**
 * useMEquityCycleSheetGroups.spec.ts — M-F2 Task 2.2
 *
 * Validates: Requirements M-F2
 *
 * 验证 8 类分组规则对 M 循环 65 个有效 sheet 全覆盖（采样代表）：
 *   1. 索引 (defaultHidden=true): 底稿目录 / GT_Custom
 *   2. 程序表: 实质性程序表 / M*A 结尾
 *   3. 审定表: 审定表M*-1 pattern
 *   4. 明细表: 明细表 pattern（含上市/非上市变体）
 *   5. 变动分析: 变动 / 增减 / 权益变动
 *   6. 检查表: 检查 / 核查 / 测试
 *   7. 附注+调整 (defaultHidden=true): 附注 / 披露 / 调整
 *   8. 其他: fallback
 */
import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import {
  classifyMSheet,
  M_SHEET_GROUP_RULES,
  FALLBACK_GROUP,
  useMEquityCycleSheetGroups,
} from '../useMEquityCycleSheetGroups'

// ===== M 循环代表 sheet 名（openpyxl 实测） =====

const M_SAMPLE_SHEETS = [
  // 索引
  '底稿目录',
  'GT_Custom',
  // 程序表
  '实收资本实质性程序表M2A',
  '资本公积实质性程序表M4A',
  '盈余公积实质性程序表M5A',
  '未分配利润实质性程序表 M6A ', // 末尾空格
  '专项储备实质性程序表 M7A ',
  '一般风险准备实质性程序表 M8A ',
  '其他综合收益实质性程序表M9A',
  '其他权益工具实质性程序表M10A',
  // 审定表
  '审定表M2-1',
  '审定表M4-1',
  '审定表M5-1',
  '审定表M6-1',
  '审定表M9-1',
  '审定表M10-1',
  // 明细表
  '明细表（非上市公司）M2-2',
  '明细表（上市公司）M2-2',
  '明细表M4-2',
  '明细表M5-2',
  '明细表M6-2',
  '明细表M9-2',
  '明细表M10-2',
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
  '底稿目录': '索引',
  'GT_Custom': '索引',
  // 程序表
  '实收资本实质性程序表M2A': '程序表',
  '资本公积实质性程序表M4A': '程序表',
  '盈余公积实质性程序表M5A': '程序表',
  '未分配利润实质性程序表 M6A ': '程序表',
  '专项储备实质性程序表 M7A ': '程序表',
  '一般风险准备实质性程序表 M8A ': '程序表',
  '其他综合收益实质性程序表M9A': '程序表',
  '其他权益工具实质性程序表M10A': '程序表',
  // 审定表
  '审定表M2-1': '审定表',
  '审定表M4-1': '审定表',
  '审定表M5-1': '审定表',
  '审定表M6-1': '审定表',
  '审定表M9-1': '审定表',
  '审定表M10-1': '审定表',
  // 明细表
  '明细表（非上市公司）M2-2': '明细表',
  '明细表（上市公司）M2-2': '明细表',
  '明细表M4-2': '明细表',
  '明细表M5-2': '明细表',
  '明细表M6-2': '明细表',
  '明细表M9-2': '明细表',
  '明细表M10-2': '明细表',
  // 附注+调整
  '附注披露信息(上市公司)': '附注+调整',
  '附注披露信息(国企)': '附注+调整',
  '附注披露信息（上市公司）': '附注+调整',
  '附注披露信息（国企）': '附注+调整',
  '附注披露信息（国有企业）': '附注+调整',
  // 其他
  '会计提示': '其他',
}

// ===== 结构性校验 =====

describe('M_SHEET_GROUP_RULES — 结构性校验', () => {
  it('规则数组共 8 条（7 显式类 + 1 fallback），按 priority 升序排列', () => {
    expect(M_SHEET_GROUP_RULES).toHaveLength(8)
    for (let i = 1; i < M_SHEET_GROUP_RULES.length; i++) {
      expect(M_SHEET_GROUP_RULES[i].priority).toBeGreaterThanOrEqual(
        M_SHEET_GROUP_RULES[i - 1].priority,
      )
    }
    expect(M_SHEET_GROUP_RULES[0].id).toBe('index')
    expect(M_SHEET_GROUP_RULES[0].priority).toBe(0)
    expect(M_SHEET_GROUP_RULES[M_SHEET_GROUP_RULES.length - 1].id).toBe('other')
    expect(M_SHEET_GROUP_RULES[M_SHEET_GROUP_RULES.length - 1].priority).toBe(7)
  })

  it('每条规则 priority 全部唯一', () => {
    const priorities = M_SHEET_GROUP_RULES.map((r) => r.priority)
    expect(new Set(priorities).size).toBe(priorities.length)
  })

  it('规则 id 全部唯一', () => {
    const ids = M_SHEET_GROUP_RULES.map((r) => r.id)
    expect(new Set(ids).size).toBe(ids.length)
  })

  it('每条规则均含必需字段', () => {
    for (const r of M_SHEET_GROUP_RULES) {
      expect(typeof r.id).toBe('string')
      expect(typeof r.category).toBe('string')
      expect(typeof r.icon).toBe('string')
      expect(r.color).toMatch(/^#[0-9a-fA-F]{6}$/)
      expect(typeof r.priority).toBe('number')
      expect(typeof r.match).toBe('function')
    }
  })

  it('FALLBACK_GROUP 与末项规则一致', () => {
    const last = M_SHEET_GROUP_RULES[M_SHEET_GROUP_RULES.length - 1]
    expect(FALLBACK_GROUP.category).toBe(last.category)
    expect(FALLBACK_GROUP.priority).toBe(last.priority)
  })
})

// ===== 关键代表 sheet 分类验证 =====

describe('classifyMSheet — 关键代表 sheet 命中预期类别 (M-F2)', () => {
  it('每个关键代表 sheet 与 EXPECTED 映射一致', () => {
    for (const [name, expected] of Object.entries(EXPECTED)) {
      const result = classifyMSheet(name)
      expect(result.category, `sheet="${name}"`).toBe(expected)
    }
  })

  it('索引类 defaultHidden=true', () => {
    expect(classifyMSheet('底稿目录').defaultHidden).toBe(true)
    expect(classifyMSheet('GT_Custom').defaultHidden).toBe(true)
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
      const r = classifyMSheet(name)
      expect(r.category, `sheet="${name}"`).toBe('附注+调整')
      expect(r.defaultHidden, `sheet="${name}" defaultHidden`).toBe(true)
      expect(r.readonly, `sheet="${name}" readonly`).toBe(true)
    }
  })

  it('末尾空格 sheet 仍正确分类（M6A/M7A/M8A 末尾带空格）', () => {
    expect(classifyMSheet('未分配利润实质性程序表 M6A ').category).toBe('程序表')
    expect(classifyMSheet('专项储备实质性程序表 M7A ').category).toBe('程序表')
    expect(classifyMSheet('一般风险准备实质性程序表 M8A ').category).toBe('程序表')
  })
})

// ===== 优先级冲突解决 =====

describe('classifyMSheet — 优先级冲突解决（首个命中即停止）', () => {
  it('程序表(1) < 审定表(2)：含"实质性程序表"的 sheet 优先匹配程序表', () => {
    expect(classifyMSheet('实收资本实质性程序表M2A').category).toBe('程序表')
    expect(classifyMSheet('实收资本实质性程序表M2A').priority).toBe(1)
  })

  it('审定表(2) < 明细表(3)：含"审定表"的 sheet 优先匹配审定表', () => {
    expect(classifyMSheet('审定表M2-1').category).toBe('审定表')
    expect(classifyMSheet('审定表M2-1').priority).toBe(2)
  })

  it('明细表(3) < 变动分析(4)：含"明细表"的 sheet 优先匹配明细表', () => {
    expect(classifyMSheet('明细表M6-2').category).toBe('明细表')
    expect(classifyMSheet('明细表M6-2').priority).toBe(3)
  })

  it('变动分析(4) < 检查表(5)：含"变动"的 sheet 优先匹配变动分析', () => {
    // 假设有 sheet 名含"变动"
    expect(classifyMSheet('权益变动表').category).toBe('变动分析')
    expect(classifyMSheet('权益变动表').priority).toBe(4)
  })

  it('检查表(5) < 附注+调整(6)：含"检查"的 sheet 优先匹配检查表', () => {
    expect(classifyMSheet('检查表M2-3').category).toBe('检查表')
    expect(classifyMSheet('检查表M2-3').priority).toBe(5)
  })
})

// ===== defaultHidden / readonly 标志验证 =====

describe('classifyMSheet — defaultHidden/readonly 标志', () => {
  it('索引类 defaultHidden=true', () => {
    expect(classifyMSheet('底稿目录').defaultHidden).toBe(true)
    expect(classifyMSheet('GT_Custom').defaultHidden).toBe(true)
  })

  it('附注+调整类 defaultHidden=true', () => {
    expect(classifyMSheet('附注披露信息(上市公司)').defaultHidden).toBe(true)
  })

  it('附注披露 readonly=true vs 其他附注+调整 readonly 非 true', () => {
    // 附注披露 → readonly=true
    expect(classifyMSheet('附注披露信息(上市公司)').readonly).toBe(true)
    expect(classifyMSheet('附注披露信息（国企）').readonly).toBe(true)
  })

  it('程序表/审定表/明细表/变动分析/检查表 defaultHidden 非 true', () => {
    const normalSheets = [
      '实收资本实质性程序表M2A',
      '审定表M2-1',
      '明细表M6-2',
      '权益变动表',
      '检查表M2-3',
    ]
    for (const name of normalSheets) {
      const r = classifyMSheet(name)
      expect(r.defaultHidden, `sheet="${name}" should not be hidden`).toBeFalsy()
    }
  })
})

// ===== 完备性 / fallback =====

describe('classifyMSheet — 完备性', () => {
  it('任意 sheet 名（含极端字符串）恒返回非 null 类目', () => {
    const edgeCases = ['', ' ', 'abc', '123', '!@#$%', 'A'.repeat(200), '中文']
    for (const name of edgeCases) {
      const cls = classifyMSheet(name)
      expect(cls).toBeDefined()
      expect(typeof cls.category).toBe('string')
      expect(cls.category.length).toBeGreaterThan(0)
    }
  })

  it('不匹配任何规则的 sheet 归入"其他"', () => {
    expect(classifyMSheet('随便的名字').category).toBe('其他')
    expect(classifyMSheet('').category).toBe('其他')
    expect(classifyMSheet('会计提示').category).toBe('其他')
  })
})

// ===== composable 集成 =====

describe('useMEquityCycleSheetGroups — composable 行为', () => {
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
    const nav = useMEquityCycleSheetGroups(apiRef)
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
      '审定表M2-1',
      '明细表M6-2',
      '实收资本实质性程序表M2A',
    ]
    const apiRef = ref<any>(createMockUniverAPI(samples))
    const nav = useMEquityCycleSheetGroups(apiRef)
    nav.refresh()

    const names = nav.sheets.value.map((s) => s.name)
    // defaultHidden 的 sheet 被过滤
    expect(names).not.toContain('底稿目录')
    expect(names).not.toContain('GT_Custom')
    expect(names).not.toContain('附注披露信息(上市公司)')
    expect(names).not.toContain('附注披露信息（国企）')
    // 非 defaultHidden 的 sheet 保留
    expect(names).toContain('审定表M2-1')
    expect(names).toContain('明细表M6-2')
    expect(names).toContain('实收资本实质性程序表M2A')
  })

  it('groups 按 priority 升序排列', () => {
    const apiRef = ref<any>(createMockUniverAPI(M_SAMPLE_SHEETS))
    const nav = useMEquityCycleSheetGroups(apiRef)
    nav.refresh()

    const priorities = nav.groups.value.map((g) => g.priority)
    for (let i = 1; i < priorities.length; i++) {
      expect(priorities[i]).toBeGreaterThanOrEqual(priorities[i - 1])
    }
  })

  it('totalCount 仅计算非 hidden sheet', () => {
    const samples = [
      '底稿目录', // hidden
      '审定表M2-1', // visible
      '明细表M6-2', // visible
      '附注披露信息(上市公司)', // hidden
    ]
    const apiRef = ref<any>(createMockUniverAPI(samples))
    const nav = useMEquityCycleSheetGroups(apiRef)
    nav.refresh()
    expect(nav.totalCount.value).toBe(2)
  })

  it('switchTo 切换 activeSheetId', () => {
    const samples = ['审定表M2-1', '明细表M6-2']
    const apiRef = ref<any>(createMockUniverAPI(samples))
    const nav = useMEquityCycleSheetGroups(apiRef)
    nav.refresh()

    nav.switchTo('sid-1')
    expect(nav.activeSheetId.value).toBe('sid-1')
  })
})
