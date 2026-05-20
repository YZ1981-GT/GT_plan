/**
 * useHFixedAssetSheetGroups vitest
 *
 * spec workpaper-h-fixed-assets-cycle ADR-H3b（Task 1.3b）
 *
 * 覆盖：
 * - MEASUREMENT_MODEL_FILTER 切换（H3 8 sheets: 4 visible / 4 hidden）
 * - 14 类分组规则代表性 sheet 名分类正确性
 * - composable 基本行为
 */
import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import {
  classifyHSheet,
  H_SHEET_PATTERNS,
  FALLBACK_GROUP,
  MEASUREMENT_MODEL_FILTER,
  isHiddenByMeasurementModel,
  useHFixedAssetSheetGroups,
} from '../useHFixedAssetSheetGroups'

// ===== MEASUREMENT_MODEL_FILTER 测试 =====

describe('MEASUREMENT_MODEL_FILTER - H3 计量模式切换', () => {
  // H3 共 8 个 sheet（4 成本模式 + 4 公允价值模式）
  const H3_SHEETS = [
    '审定表（成本模式）H3-1',
    '审定表（公允价值模式）H3-1',
    '明细表（成本模式）H3-2',
    '明细表（公允价值模式）H3-2',
    '增减检查表（成本模式）H3-5',
    '增减检查表（公允价值模式）H3-5',
    '折旧测算表（成本模式不含减值）H3-7',
    '折旧测算表（成本模式含减值）H3-7',
  ]

  it('cost 模式隐藏含"（公允价值模式）"的 sheet', () => {
    const hidden = H3_SHEETS.filter((s) => isHiddenByMeasurementModel(s, 'cost'))
    const visible = H3_SHEETS.filter((s) => !isHiddenByMeasurementModel(s, 'cost'))
    // 含完整"（公允价值模式）"的被隐藏: H3-1, H3-2, H3-5
    expect(hidden).toHaveLength(3)
    expect(visible).toHaveLength(5)
    expect(hidden).toContain('审定表（公允价值模式）H3-1')
    expect(hidden).toContain('明细表（公允价值模式）H3-2')
    expect(hidden).toContain('增减检查表（公允价值模式）H3-5')
  })

  it('fair_value 模式隐藏含"（成本模式）"的 sheet', () => {
    const hidden = H3_SHEETS.filter((s) => isHiddenByMeasurementModel(s, 'fair_value'))
    const visible = H3_SHEETS.filter((s) => !isHiddenByMeasurementModel(s, 'fair_value'))
    // "（成本模式）" 匹配: 审定表（成本模式）H3-1, 明细表（成本模式）H3-2, 增减检查表（成本模式）H3-5
    // 注意: "折旧测算表（成本模式不含减值）H3-7" 和 "折旧测算表（成本模式含减值）H3-7"
    // 也包含 "（成本模式" 子串但不包含完整 "（成本模式）" — 实际上它们包含 "成本模式" 后跟其他字符
    // 检查: "（成本模式不含减值）" 不包含 "（成本模式）" 子串（因为括号后不是直接闭合）
    // 所以只有 3 个被隐藏
    expect(hidden).toHaveLength(3)
    expect(visible).toHaveLength(5)
    expect(hidden).toContain('审定表（成本模式）H3-1')
    expect(hidden).toContain('明细表（成本模式）H3-2')
    expect(hidden).toContain('增减检查表（成本模式）H3-5')
    expect(visible).toContain('审定表（公允价值模式）H3-1')
    expect(visible).toContain('明细表（公允价值模式）H3-2')
    expect(visible).toContain('增减检查表（公允价值模式）H3-5')
  })

  it('MEASUREMENT_MODEL_FILTER 字典包含 cost 和 fair_value 两档', () => {
    expect(Object.keys(MEASUREMENT_MODEL_FILTER)).toEqual(['cost', 'fair_value'])
    expect(MEASUREMENT_MODEL_FILTER.cost.hide_patterns).toContain('（公允价值模式）')
    expect(MEASUREMENT_MODEL_FILTER.cost.hide_patterns).toContain('(公允价值模式)')
    expect(MEASUREMENT_MODEL_FILTER.fair_value.hide_patterns).toContain('（成本模式）')
    expect(MEASUREMENT_MODEL_FILTER.fair_value.hide_patterns).toContain('(成本模式)')
  })

  it('未知 measurement_model 不隐藏任何 sheet', () => {
    const hidden = H3_SHEETS.filter((s) => isHiddenByMeasurementModel(s, 'unknown'))
    expect(hidden).toHaveLength(0)
  })
})

// ===== 14 类分组规则测试 =====

describe('classifyHSheet - 14 类分组规则', () => {
  it('索引: 底稿目录 / GT_Custom / 修订说明 默认隐藏', () => {
    expect(classifyHSheet('底稿目录')).toMatchObject({ category: '索引', defaultHidden: true })
    expect(classifyHSheet('GT_Custom')).toMatchObject({ category: '索引', defaultHidden: true })
    expect(classifyHSheet('修订说明')).toMatchObject({ category: '索引', defaultHidden: true })
  })

  it('总控台: H1A / H2A 等程序表', () => {
    expect(classifyHSheet('固定资产实质性程序表H1A')).toMatchObject({ category: '总控台', priority: 2 })
    expect(classifyHSheet('在建工程实质性程序表H2A')).toMatchObject({ category: '总控台' })
  })

  it('审定表', () => {
    expect(classifyHSheet('审定表H1-1')).toMatchObject({ category: '审定表', priority: 3 })
    expect(classifyHSheet('审定表（成本模式）H3-1')).toMatchObject({ category: '审定表' })
    expect(classifyHSheet('审定表（公允价值模式）H7-1')).toMatchObject({ category: '审定表' })
  })

  it('附注披露 (readonly)', () => {
    expect(classifyHSheet('附注披露信息（上市公司）')).toMatchObject({
      category: '附注披露',
      readonly: true,
    })
    expect(classifyHSheet('附注披露信息（国有企业）')).toMatchObject({
      category: '附注披露',
      readonly: true,
    })
  })

  it('明细表', () => {
    expect(classifyHSheet('明细表H1-2')).toMatchObject({ category: '明细表', priority: 5 })
    expect(classifyHSheet('明细表（成本模式）H3-2')).toMatchObject({ category: '明细表' })
  })

  it('折旧测算', () => {
    expect(classifyHSheet('折旧测算表（不含减值）-直线法H1-12')).toMatchObject({
      category: '折旧测算',
      priority: 6,
    })
    expect(classifyHSheet('折旧测算表（含减值）H1-12')).toMatchObject({ category: '折旧测算' })
    expect(classifyHSheet('折耗测算表（不含减值）H5-12')).toMatchObject({ category: '折旧测算' })
    expect(classifyHSheet('折旧分配分析表H1-13')).toMatchObject({ category: '折旧测算' })
  })

  it('减值测试', () => {
    expect(classifyHSheet('减值测算表H1-14')).toMatchObject({ category: '减值测试', priority: 7 })
  })

  it('增减检查', () => {
    expect(classifyHSheet('增加检查表H1-7')).toMatchObject({ category: '增减检查', priority: 8 })
    expect(classifyHSheet('减少检查表H1-8')).toMatchObject({ category: '增减检查' })
    expect(classifyHSheet('增减检查表（成本模式）H3-5')).toMatchObject({ category: '增减检查' })
  })

  it('实物盘点', () => {
    expect(classifyHSheet('监盘计划H1-9')).toMatchObject({ category: '实物盘点', priority: 9 })
    expect(classifyHSheet('盘点检查表H1-10')).toMatchObject({ category: '实物盘点' })
    expect(classifyHSheet('监盘小结H1-11')).toMatchObject({ category: '实物盘点' })
  })

  it('权属检查', () => {
    expect(classifyHSheet('权属检查表H1-6')).toMatchObject({ category: '权属检查', priority: 10 })
    expect(classifyHSheet('产权核对表H2-8')).toMatchObject({ category: '权属检查' })
  })

  it('关联交易', () => {
    expect(classifyHSheet('关联方交易检查表H1-15')).toMatchObject({ category: '关联交易', priority: 11 })
  })

  it('租赁专项', () => {
    expect(classifyHSheet('使用权资产 租赁负债初始及后续计量（按月）H8-6')).toMatchObject({
      category: '租赁专项',
      priority: 12,
    })
    expect(classifyHSheet('租赁变更检查表H8-7')).toMatchObject({ category: '租赁专项' })
  })

  it('调整分录', () => {
    expect(classifyHSheet('调整分录汇总H1-16')).toMatchObject({ category: '调整分录', priority: 13 })
  })

  it('其他程序 (fallback)', () => {
    expect(classifyHSheet('利息资本化测算表H2-10')).toEqual(FALLBACK_GROUP)
    expect(classifyHSheet('完全不相干的随机名字 XYZ123')).toEqual(FALLBACK_GROUP)
  })
})

// ===== composable 行为测试 =====

describe('useHFixedAssetSheetGroups - composable behavior', () => {
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

  it('measurement_model=cost 时隐藏公允价值模式 sheet', () => {
    const apiRef = ref<any>(
      createMockUniverAPI([
        '审定表（成本模式）H3-1',
        '审定表（公允价值模式）H3-1',
        '明细表（成本模式）H3-2',
        '明细表（公允价值模式）H3-2',
      ]),
    )
    const modelRef = ref('cost')
    const nav = useHFixedAssetSheetGroups(apiRef, modelRef)
    nav.refresh()

    const names = nav.sheets.value.map((s) => s.name)
    expect(names).toContain('审定表（成本模式）H3-1')
    expect(names).toContain('明细表（成本模式）H3-2')
    expect(names).not.toContain('审定表（公允价值模式）H3-1')
    expect(names).not.toContain('明细表（公允价值模式）H3-2')
  })

  it('measurement_model=fair_value 时隐藏成本模式 sheet', () => {
    const apiRef = ref<any>(
      createMockUniverAPI([
        '审定表（成本模式）H3-1',
        '审定表（公允价值模式）H3-1',
        '明细表（成本模式）H3-2',
        '明细表（公允价值模式）H3-2',
      ]),
    )
    const modelRef = ref('fair_value')
    const nav = useHFixedAssetSheetGroups(apiRef, modelRef)
    nav.refresh()

    const names = nav.sheets.value.map((s) => s.name)
    expect(names).not.toContain('审定表（成本模式）H3-1')
    expect(names).not.toContain('明细表（成本模式）H3-2')
    expect(names).toContain('审定表（公允价值模式）H3-1')
    expect(names).toContain('明细表（公允价值模式）H3-2')
  })

  it('默认隐藏索引类 sheet（底稿目录/GT_Custom）', () => {
    const apiRef = ref<any>(
      createMockUniverAPI(['底稿目录', 'GT_Custom', '审定表H1-1']),
    )
    const nav = useHFixedAssetSheetGroups(apiRef)
    nav.refresh()

    expect(nav.totalCount.value).toBe(1)
    expect(nav.sheets.value[0].name).toBe('审定表H1-1')
  })

  it('univerAPI 为 null 时 sheets 列表为空，无异常抛出', () => {
    const apiRef = ref<any>(null)
    const nav = useHFixedAssetSheetGroups(apiRef)
    expect(() => nav.refresh()).not.toThrow()
    expect(nav.totalCount.value).toBe(0)
  })

  it('groups 按 priority 升序排列', () => {
    const apiRef = ref<any>(
      createMockUniverAPI([
        '审定表H1-1',
        '明细表H1-2',
        '折旧测算表（不含减值）-直线法H1-12',
        '监盘计划H1-9',
        '调整分录汇总H1-16',
      ]),
    )
    const nav = useHFixedAssetSheetGroups(apiRef)
    nav.refresh()

    const priorities = nav.groups.value.map((g) => g.priority)
    expect(priorities).toEqual([...priorities].sort((a, b) => a - b))
  })
})
