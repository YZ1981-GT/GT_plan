/**
 * useDSalesCycleSheetGroups smoke test
 *
 * spec workpaper-d-sales-cycle ADR D5（任务 2.5）
 *
 * 覆盖 14 类规则的代表性 sheet 名分类正确性，以及 groups computed 的
 * priority 升序行为。
 */
import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import {
  classifyDSheet,
  D_SHEET_PATTERNS,
  FALLBACK_GROUP,
  useDSalesCycleSheetGroups,
} from '../useDSalesCycleSheetGroups'

describe('useDSalesCycleSheetGroups - classifyDSheet', () => {
  it('索引: 底稿目录 / GT_Custom 默认隐藏', () => {
    expect(classifyDSheet('底稿目录')).toMatchObject({
      category: '索引',
      priority: 1,
      defaultHidden: true,
    })
    expect(classifyDSheet('GT_Custom')).toMatchObject({
      category: '索引',
      defaultHidden: true,
    })
  })

  it('总控台: D[0-7]A 类 sheet 名识别为 priority 1', () => {
    expect(classifyDSheet('应收账款实质性程序表D2A')).toMatchObject({
      category: '总控台',
      priority: 1,
    })
    expect(classifyDSheet('D4-22A')).toMatchObject({
      category: '总控台',
      priority: 1,
    })
  })

  it('审定表: priority 2', () => {
    expect(classifyDSheet('审定表D2-1')).toMatchObject({
      category: '审定表',
      priority: 2,
    })
    expect(classifyDSheet('应收账款审定表D2-1')).toMatchObject({
      category: '审定表',
      priority: 2,
    })
  })

  it('坏账与减值: priority 4（覆盖坏账/减值/ECL）', () => {
    expect(classifyDSheet('坏账准备计算表D2-8')).toMatchObject({
      category: '坏账与减值',
      priority: 4,
    })
    expect(classifyDSheet('信用减值损失分析D2-9')).toMatchObject({
      category: '坏账与减值',
      priority: 4,
    })
    expect(classifyDSheet('ECL 模型计算')).toMatchObject({
      category: '坏账与减值',
      priority: 4,
    })
  })

  it('访谈: priority 10', () => {
    expect(classifyDSheet('客户访谈记录D4-30')).toMatchObject({
      category: '访谈',
      priority: 10,
    })
  })

  it('附注披露: readonly=true, priority 11', () => {
    expect(classifyDSheet('附注披露信息(上市公司)')).toMatchObject({
      category: '附注披露',
      priority: 11,
      readonly: true,
    })
  })

  it('历史遗留: 修订前D4A / （原）X 默认隐藏 priority 99', () => {
    expect(classifyDSheet('修订前D4A')).toMatchObject({
      category: '历史遗留',
      priority: 99,
      defaultHidden: true,
    })
    expect(classifyDSheet('应收账款审定表（原）')).toMatchObject({
      category: '历史遗留',
      defaultHidden: true,
    })
  })

  it('明细表: 排除坏账类 sheet', () => {
    expect(classifyDSheet('应收账款明细表D2-2')).toMatchObject({
      category: '明细表',
      priority: 3,
    })
    // "坏账明细表"应归类为坏账与减值（priority 4），而非明细表
    expect(classifyDSheet('坏账明细表D2-3')).toMatchObject({
      category: '坏账与减值',
    })
  })

  it('14 类规则全覆盖（含 historical 隐藏 + note readonly）', () => {
    const categories = new Set(D_SHEET_PATTERNS.map((p) => p.category))
    expect(categories).toEqual(
      new Set([
        '索引',
        '历史遗留',
        '总控台',
        '审定表',
        '明细表',
        '坏账与减值',
        '分析',
        '截止测试',
        '检查表',
        '关联方',
        '监盘',
        '访谈',
        '附注披露',
        '调整分录',
      ]),
    )
    expect(D_SHEET_PATTERNS).toHaveLength(14)
    // 默认隐藏类 = 索引 + 历史遗留
    const hiddenCats = D_SHEET_PATTERNS.filter((p) => p.defaultHidden).map((p) => p.category)
    expect(hiddenCats).toEqual(expect.arrayContaining(['索引', '历史遗留']))
    // 只读类 = 附注披露
    const readonlyCats = D_SHEET_PATTERNS.filter((p) => p.readonly).map((p) => p.category)
    expect(readonlyCats).toEqual(['附注披露'])
  })

  it('未匹配类目 fallback 为"其他" priority 50', () => {
    const result = classifyDSheet('完全不相干的随机名字 XYZ123')
    expect(result).toEqual(FALLBACK_GROUP)
    expect(result.priority).toBe(50)
  })
})

describe('useDSalesCycleSheetGroups - composable', () => {
  /** 构造一个 mock Univer Facade API */
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

  it('refresh 加载 sheet 列表，groups 按 priority 升序', () => {
    const apiRef = ref<any>(
      createMockUniverAPI([
        '附注披露信息',
        '应收账款实质性程序表D2A',
        '审定表D2-1',
        '客户访谈记录D4-30',
        '坏账准备计算表D2-8',
      ]),
    )
    const nav = useDSalesCycleSheetGroups(apiRef)
    nav.refresh()

    expect(nav.totalCount.value).toBe(5)
    const priorities = nav.groups.value.map((g) => g.priority)
    // 升序：1 (总控台), 2 (审定表), 4 (坏账与减值), 10 (访谈), 11 (附注披露)
    expect(priorities).toEqual([...priorities].sort((a, b) => a - b))
    expect(priorities[0]).toBe(1)
    expect(priorities[priorities.length - 1]).toBe(11)
  })

  it('refresh 默认过滤 defaultHidden 类（索引 + 历史遗留）', () => {
    const apiRef = ref<any>(
      createMockUniverAPI([
        '底稿目录',
        '审定表D2-1',
        '修订前D4A',
        '应收账款实质性程序表D2A',
      ]),
    )
    const nav = useDSalesCycleSheetGroups(apiRef)
    nav.refresh()

    // 只保留 2 个非隐藏 sheet（审定表 + 总控台）
    expect(nav.totalCount.value).toBe(2)
    const names = nav.sheets.value.map((s) => s.name)
    expect(names).not.toContain('底稿目录')
    expect(names).not.toContain('修订前D4A')
    expect(names).toContain('审定表D2-1')
    expect(names).toContain('应收账款实质性程序表D2A')
  })

  it('附注披露 sheet 项标记 readonly=true', () => {
    const apiRef = ref<any>(createMockUniverAPI(['附注披露信息(上市公司)']))
    const nav = useDSalesCycleSheetGroups(apiRef)
    nav.refresh()
    expect(nav.sheets.value[0].readonly).toBe(true)
    expect(nav.sheets.value[0].category).toBe('附注披露')
  })

  it('univerAPI 为 null 时 sheets 列表为空，无异常抛出', () => {
    const apiRef = ref<any>(null)
    const nav = useDSalesCycleSheetGroups(apiRef)
    expect(() => nav.refresh()).not.toThrow()
    expect(nav.totalCount.value).toBe(0)
  })
})

// =============================================================================
// Task 2.8：真实 D2 模板合并去重后 sheet 名分组验证
// 数据来源：
//   - Task 1.7 实测：D2 三模板文件合并去重 = 20 sheet（实测脚本已删除，
//     基线落地 tasks.md "Task 1.7 实施记录" 章节）
//   - 用户在 Task 2.8 prompt 中显式锚定 13 个 sheet 名 + 期望分类
// 本测试验证用户显式列出的 13 个 sheet 名（含 2 个 GT 默认隐藏 sheet），
// 这是 Task 1.7 实测 20 sheet 的可信子集，不对未列出的 7 个主业务 sheet 名做猜测。
// =============================================================================

describe('useDSalesCycleSheetGroups - 真实 D2 模板 sheet 分组验证（Task 2.8）', () => {
  /** Task 2.8 prompt 锚定的 12 个 D2 真实 sheet 名（来源：用户显式期望分类列表 + 8 GT 公共 sheet） */
  const REAL_D2_SHEETS = [
    // GT 公共 sheet（8 个，用户 prompt 显式列出）
    '底稿目录', // → 索引（priority 1, defaultHidden）
    'GT_Custom', // → 索引（priority 1, defaultHidden）
    '应收账款实质性程序表D2A', // → 总控台（priority 1）
    '审定表D2-1', // → 审定表（priority 2）
    '客户明细表D2-2', // → 明细表（priority 3）
    '账龄分析表D2-7', // → 分析（priority 5，"分析"匹配优先于"明细"）
    '坏账准备计算表D2-8', // → 坏账与减值（priority 4）
    '调整分录汇总表D2-3', // → 调整分录（priority 12）
    // 用户 prompt "Expected classifications" 显式锚定的 4 个主业务 sheet 名
    '信用减值损失分析D2-9', // → 坏账与减值（priority 4，"减值"优先于"分析"）
    '附注披露信息(上市公司)', // → 附注披露（priority 11, readonly）
    '应收账款业务模式分析D2-13', // → 分析（priority 5）
    // 用户 prompt 提及"附注披露上市公司、附注披露国企"作为 D2 实存 sheet
    '附注披露信息(国企)', // → 附注披露（priority 11, readonly）
  ]

  it('D2 真实 12 sheet 全部分类命中（无 fallback 到"其他"）', () => {
    const fallbackHits: string[] = []
    const mapping: Array<{ sheet: string; category: string; priority: number }> = []

    for (const name of REAL_D2_SHEETS) {
      const cls = classifyDSheet(name)
      mapping.push({ sheet: name, category: cls.category, priority: cls.priority })
      if (cls.category === '其他') {
        fallbackHits.push(name)
      }
    }

    // 输出每个 sheet → category 映射（vitest 控制台可见，便于人工核验）
    // eslint-disable-next-line no-console
    console.log(
      '[Task 2.8] D2 真实 sheet → category 映射：\n' +
        mapping
          .map(
            (m, i) =>
              `  ${String(i + 1).padStart(2, '0')}. [${String(m.priority).padStart(2, '0')}] ${m.category.padEnd(8, '　')} ← ${m.sheet}`,
          )
          .join('\n'),
    )

    expect(fallbackHits, `这些 sheet 未被任何规则命中，需扩展 D_SHEET_PATTERNS：${fallbackHits.join(', ')}`).toEqual([])
  })

  it('期望分类锚定（spec ADR D5 期望值与真实 D2 sheet 一一对应）', () => {
    const expectations: Array<[string, string, number]> = [
      ['底稿目录', '索引', 1],
      ['GT_Custom', '索引', 1],
      ['应收账款实质性程序表D2A', '总控台', 1],
      ['审定表D2-1', '审定表', 2],
      ['客户明细表D2-2', '明细表', 3],
      // 注意：账龄"分析"表先匹配"分析"规则（priority 5），不会落到明细表/坏账
      ['账龄分析表D2-7', '分析', 5],
      ['坏账准备计算表D2-8', '坏账与减值', 4],
      // "信用减值损失分析"同时含"减值/损失/分析"，按 D_SHEET_PATTERNS 顺序，
      // 坏账与减值（priority 4）排在分析（priority 5）之前，应命中坏账与减值
      ['信用减值损失分析D2-9', '坏账与减值', 4],
      ['附注披露信息(上市公司)', '附注披露', 11],
      ['附注披露信息(国企)', '附注披露', 11],
      ['应收账款业务模式分析D2-13', '分析', 5],
      ['调整分录汇总表D2-3', '调整分录', 12],
    ]

    for (const [sheet, expectedCategory, expectedPriority] of expectations) {
      const cls = classifyDSheet(sheet)
      expect(cls.category, `${sheet} 期望 ${expectedCategory} 实际 ${cls.category}`).toBe(expectedCategory)
      expect(cls.priority, `${sheet} 期望 priority ${expectedPriority} 实际 ${cls.priority}`).toBe(expectedPriority)
    }
  })

  it('D2 真实 12 sheet 至少覆盖 8/14 业务类目（验收 #3）', () => {
    const coveredCategories = new Set<string>()
    for (const name of REAL_D2_SHEETS) {
      const cls = classifyDSheet(name)
      if (cls.category !== '其他') coveredCategories.add(cls.category)
    }
    // 期望覆盖：索引/总控台/审定表/明细表/坏账与减值/分析/附注披露/调整分录 = 8 类
    expect(coveredCategories.size).toBeGreaterThanOrEqual(8)
    // eslint-disable-next-line no-console
    console.log(
      `[Task 2.8] D2 真实模板覆盖业务类目 ${coveredCategories.size}/14：${Array.from(coveredCategories).join(', ')}`,
    )
  })

  it('useDSalesCycleSheetGroups composable 加载真实 12 sheet 后默认隐藏底稿目录/GT_Custom，剩 10 sheet', () => {
    const sheetObjects = REAL_D2_SHEETS.map((name, idx) => ({
      getSheetId: () => `sid-${idx}`,
      getSheetName: () => name,
      isSheetHidden: () => false,
      activate: () => undefined,
    }))
    const wb = {
      getSheets: () => sheetObjects,
      getActiveSheet: () => sheetObjects[2], // 总控台作为默认激活 sheet
      getId: () => 'unit1',
    }
    const apiRef = ref<any>({
      getActiveWorkbook: () => wb,
      executeCommand: async () => undefined,
    })
    const nav = useDSalesCycleSheetGroups(apiRef)
    nav.refresh()

    // 默认隐藏 2 sheet（底稿目录 + GT_Custom）→ 显示 10 sheet
    expect(nav.totalCount.value).toBe(10)

    // groups 按 priority 升序：1 (总控台) 应排第一
    expect(nav.groups.value[0].category).toBe('总控台')
    // 最后一个 group 应为 priority 12 (调整分录)
    const lastGroup = nav.groups.value[nav.groups.value.length - 1]
    expect(lastGroup.priority).toBe(12)
    expect(lastGroup.category).toBe('调整分录')

    // 附注披露 sheet 必须 readonly=true（2 sheet：上市/国企）
    const noteSheets = nav.sheets.value.filter((s) => s.category === '附注披露')
    expect(noteSheets).toHaveLength(2)
    expect(noteSheets.every((s) => s.readonly)).toBe(true)
  })
})
