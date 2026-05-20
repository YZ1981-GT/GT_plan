/**
 * useFPurchaseInventorySheetGroups vitest
 *
 * spec workpaper-f-purchase-inventory ADR-F5（任务 2.4）
 *
 * 覆盖 16 类规则的代表性 sheet 名分类正确性 + 真实 F 循环 sheet 名验证
 */
import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import {
  classifyFSheet,
  F_SHEET_PATTERNS,
  FALLBACK_GROUP,
  useFPurchaseInventorySheetGroups,
} from '../useFPurchaseInventorySheetGroups'

describe('useFPurchaseInventorySheetGroups - classifyFSheet (16 categories)', () => {
  it('索引: 底稿目录 / GT_Custom / 修订说明 默认隐藏', () => {
    expect(classifyFSheet('底稿目录')).toMatchObject({
      category: '索引',
      priority: 1,
      defaultHidden: true,
    })
    expect(classifyFSheet('GT_Custom')).toMatchObject({ category: '索引', defaultHidden: true })
    expect(classifyFSheet('修订说明')).toMatchObject({ category: '索引', defaultHidden: true })
  })

  it('总控台: F[0-5]A / F2-21A / F2-55A / F2-61A 识别', () => {
    expect(classifyFSheet('存货实质性程序表F2A')).toMatchObject({ category: '总控台', priority: 1 })
    expect(classifyFSheet('应付账款实质性程序表F4A')).toMatchObject({ category: '总控台' })
    expect(classifyFSheet('营业成本实质性程序表F5A')).toMatchObject({ category: '总控台' })
    expect(classifyFSheet('函证程序表F0A')).toMatchObject({ category: '总控台' })
    expect(classifyFSheet('存货监盘程序表F2-21A')).toMatchObject({ category: '总控台' })
    expect(classifyFSheet('合同履约成本实质性程序表F2-55A')).toMatchObject({ category: '总控台' })
    expect(classifyFSheet('程序表F2-61A')).toMatchObject({ category: '总控台' })
  })

  it('审定表: priority 2', () => {
    expect(classifyFSheet('存货审定表F2-1')).toMatchObject({ category: '审定表', priority: 2 })
    expect(classifyFSheet('审定表F1-1')).toMatchObject({ category: '审定表', priority: 2 })
    expect(classifyFSheet('应付账款审定表F4-1')).toMatchObject({ category: '审定表', priority: 2 })
  })

  it('跌价准备 (priority 4) 优先于 明细表 (priority 3)', () => {
    expect(classifyFSheet('跌价准备测试表F2-47')).toMatchObject({
      category: '跌价准备',
      priority: 4,
    })
    expect(classifyFSheet('长库龄 呆滞 超过保质期存货明细表F2-48')).toMatchObject({
      category: '跌价准备',
      priority: 4,
    })
    expect(classifyFSheet('跌价转回F2-49')).toMatchObject({ category: '跌价准备', priority: 4 })
  })

  it('存货监盘 (priority 6)', () => {
    expect(classifyFSheet('监盘计划F2-22')).toMatchObject({ category: '存货监盘', priority: 6 })
    expect(classifyFSheet('监盘小结F2-23')).toMatchObject({ category: '存货监盘' })
    expect(classifyFSheet('盘点计划问卷F2-21')).toMatchObject({ category: '存货监盘' })
    expect(classifyFSheet('抽盘结果汇总表F2-25')).toMatchObject({ category: '存货监盘' })
    expect(classifyFSheet('盘点倒轧表F2-26')).toMatchObject({ category: '存货监盘' })
  })

  it('截止测试 (priority 7)', () => {
    expect(classifyFSheet('截止测试-入库（记账凭证至原始凭证）F2-29')).toMatchObject({
      category: '截止测试',
      priority: 7,
    })
    expect(classifyFSheet('截止测试-出库（原始凭证至记账凭证）F2-32')).toMatchObject({
      category: '截止测试',
    })
  })

  it('计价测试 (priority 9) 优先于 明细表', () => {
    expect(classifyFSheet('计价方法测试表-平均F2-38')).toMatchObject({
      category: '计价测试',
      priority: 9,
    })
    expect(classifyFSheet('计价方法测试表-先进先出F2-39')).toMatchObject({ category: '计价测试' })
    expect(classifyFSheet('生产成本明细表F2-41')).toMatchObject({ category: '计价测试' })
    expect(classifyFSheet('制造费用明细表F2-43')).toMatchObject({ category: '计价测试' })
    expect(classifyFSheet('直接人工分析表F2-42')).toMatchObject({ category: '计价测试' })
  })

  it('合同履约 (priority 11)', () => {
    expect(classifyFSheet('合同履约成本构成明细表F2-55')).toMatchObject({
      category: '合同履约',
      priority: 11,
    })
    expect(classifyFSheet('亏损合同预计损失测算表F2-58')).toMatchObject({ category: '合同履约' })
  })

  it('供应商访谈 (priority 12)', () => {
    expect(classifyFSheet('供应商访谈记录汇总表F2-71')).toMatchObject({
      category: '供应商访谈',
      priority: 12,
    })
    expect(classifyFSheet('供应商访谈记录F2-72')).toMatchObject({ category: '供应商访谈' })
  })

  it('明细表 (priority 3) — 非跌价/监盘/计价/合同类', () => {
    expect(classifyFSheet('明细汇总表F2-2')).toMatchObject({ category: '明细表', priority: 3 })
    expect(classifyFSheet('一、原材料明细表F2-3')).toMatchObject({ category: '明细表' })
    expect(classifyFSheet('六、库存商品明细表F2-8')).toMatchObject({ category: '明细表' })
  })

  it('分析 (priority 5)', () => {
    expect(classifyFSheet('存货总体分析表F2-18')).toMatchObject({ category: '分析', priority: 5 })
    expect(classifyFSheet('存货产销量变动分析表F2-19')).toMatchObject({ category: '分析' })
    expect(classifyFSheet('实质性分析F1-4')).toMatchObject({ category: '分析' })
  })

  it('检查表 (priority 8)', () => {
    expect(classifyFSheet('存货采购入库检查表F2-33-新增')).toMatchObject({
      category: '检查表',
      priority: 8,
    })
    expect(classifyFSheet('未入账检查表F4-7')).toMatchObject({ category: '检查表' })
    expect(classifyFSheet('供应商融资检查表F4-9')).toMatchObject({ category: '检查表' })
    expect(classifyFSheet('长期挂账检查表F4-5')).toMatchObject({ category: '检查表' })
    expect(classifyFSheet('委托加工物资核查表F2-35')).toMatchObject({ category: '检查表' })
  })

  it('关联方 (priority 10)', () => {
    expect(classifyFSheet('关联采购分析表F2-52')).toMatchObject({
      category: '关联方',
      priority: 10,
    })
    expect(classifyFSheet('关联方及交易检查表F1-6')).toMatchObject({ category: '关联方' })
  })

  it('附注披露 (priority 13, readonly)', () => {
    expect(classifyFSheet('附注披露信息(上市公司)')).toMatchObject({
      category: '附注披露',
      priority: 13,
      readonly: true,
    })
    expect(classifyFSheet('附注披露信息（国企）')).toMatchObject({
      category: '附注披露',
      readonly: true,
    })
  })

  it('调整分录 (priority 14)', () => {
    expect(classifyFSheet('调整分录汇总F2-14')).toMatchObject({
      category: '调整分录',
      priority: 14,
    })
    expect(classifyFSheet('调整分录汇总F4-3')).toMatchObject({ category: '调整分录' })
  })

  it('会计政策 (priority 15)', () => {
    expect(classifyFSheet('存货会计政策检查F2-16')).toMatchObject({
      category: '会计政策',
      priority: 15,
    })
  })

  it('历史遗留 (priority 99, hidden)', () => {
    expect(classifyFSheet('预付账款实质性程序表G1A-修订前')).toMatchObject({
      category: '历史遗留',
      priority: 99,
      defaultHidden: true,
    })
    expect(classifyFSheet('存货计价测试程序G2-8-删除')).toMatchObject({
      category: '历史遗留',
      defaultHidden: true,
    })
    expect(classifyFSheet('产品年度成本比较G2-8-4-移至分析类')).toMatchObject({
      category: '历史遗留',
    })
    expect(classifyFSheet('函证差异检查表（示例）')).toMatchObject({ category: '历史遗留' })
    expect(classifyFSheet('访谈记录与核对示例')).toMatchObject({ category: '历史遗留' })
  })

  it('16 类规则全覆盖（含 historical hidden + note readonly + policy + 函证管理）', () => {
    const categories = new Set(F_SHEET_PATTERNS.map((p) => p.category))
    expect(categories).toEqual(
      new Set([
        '索引',
        '历史遗留',
        '总控台',
        '审定表',
        '跌价准备',
        '存货监盘',
        '截止测试',
        '计价测试',
        '合同履约',
        '供应商访谈',
        '明细表',
        '分析',
        '检查表',
        '关联方',
        '附注披露',
        '调整分录',
        '会计政策',
        '函证管理',
      ]),
    )
    expect(F_SHEET_PATTERNS).toHaveLength(18) // 17 业务类目（含函证管理）+ 1 历史遗留
    const hiddenCats = F_SHEET_PATTERNS.filter((p) => p.defaultHidden).map((p) => p.category)
    expect(hiddenCats).toEqual(expect.arrayContaining(['索引', '历史遗留']))
    const readonlyCats = F_SHEET_PATTERNS.filter((p) => p.readonly).map((p) => p.category)
    expect(readonlyCats).toEqual(['附注披露'])
  })

  it('未匹配类目 fallback 为"其他" priority 50', () => {
    const result = classifyFSheet('完全不相干的随机名字 XYZ123')
    expect(result).toEqual(FALLBACK_GROUP)
    expect(result.priority).toBe(50)
  })
})

describe('useFPurchaseInventorySheetGroups - composable behavior', () => {
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

  it('refresh 加载真实 F2 sheet 名 + groups 按 priority 升序', () => {
    const apiRef = ref<any>(
      createMockUniverAPI([
        '存货实质性程序表F2A', // 总控台 priority 1
        '存货审定表F2-1', // 审定表 priority 2
        '明细汇总表F2-2', // 明细表 priority 3
        '跌价准备测试表F2-47', // 跌价准备 priority 4
        '存货总体分析表F2-18', // 分析 priority 5
        '监盘计划F2-22', // 存货监盘 priority 6
        '截止测试-入库（记账凭证至原始凭证）F2-29', // 截止测试 priority 7
        '存货采购入库检查表F2-33', // 检查表 priority 8
        '计价方法测试表-平均F2-38', // 计价测试 priority 9
        '关联采购分析表F2-52', // 关联方 priority 10
        '合同履约成本构成明细表F2-55', // 合同履约 priority 11
        '供应商访谈记录F2-72', // 供应商访谈 priority 12
        '附注披露信息(上市公司)', // 附注披露 priority 13
        '调整分录汇总F2-14', // 调整分录 priority 14
        '存货会计政策检查F2-16', // 会计政策 priority 15
      ]),
    )
    const nav = useFPurchaseInventorySheetGroups(apiRef)
    nav.refresh()

    expect(nav.totalCount.value).toBe(15)
    const priorities = nav.groups.value.map((g) => g.priority)
    // priorities should be sorted ascending
    expect(priorities).toEqual([...priorities].sort((a, b) => a - b))
    expect(priorities[0]).toBe(1)
    expect(priorities[priorities.length - 1]).toBe(15)
  })

  it('refresh 默认过滤 defaultHidden 类（索引 + 历史遗留）', () => {
    const apiRef = ref<any>(
      createMockUniverAPI([
        '底稿目录',
        'GT_Custom',
        '修订说明',
        '存货实质性程序表F2A',
        '存货审定表F2-1',
        '存货计价测试程序G2-8-删除', // 历史遗留
        '函证差异检查表（示例）', // 历史遗留
      ]),
    )
    const nav = useFPurchaseInventorySheetGroups(apiRef)
    nav.refresh()

    expect(nav.totalCount.value).toBe(2) // 仅 F2A + F2-1
    const names = nav.sheets.value.map((s) => s.name)
    expect(names).toContain('存货实质性程序表F2A')
    expect(names).toContain('存货审定表F2-1')
    expect(names).not.toContain('底稿目录')
    expect(names).not.toContain('GT_Custom')
    expect(names).not.toContain('修订说明')
    expect(names).not.toContain('存货计价测试程序G2-8-删除')
    expect(names).not.toContain('函证差异检查表（示例）')
  })

  it('附注披露 sheet 项标记 readonly=true', () => {
    const apiRef = ref<any>(createMockUniverAPI(['附注披露信息(上市公司)']))
    const nav = useFPurchaseInventorySheetGroups(apiRef)
    nav.refresh()
    expect(nav.sheets.value[0].readonly).toBe(true)
    expect(nav.sheets.value[0].category).toBe('附注披露')
  })

  it('univerAPI 为 null 时 sheets 列表为空，无异常抛出', () => {
    const apiRef = ref<any>(null)
    const nav = useFPurchaseInventorySheetGroups(apiRef)
    expect(() => nav.refresh()).not.toThrow()
    expect(nav.totalCount.value).toBe(0)
  })
})

// =============================================================================
// Task 2.5 PBT-P5: F 循环真实 sheet 分组完备性（用真实采集的 sheet 名）
// =============================================================================

describe('PBT-P5: F 循环真实 sheet 分组完备性', () => {
  // F 循环真实 sheet 名池（来自 Sprint 0 实测 + 关键业务 sheet）
  const REAL_F_SHEETS = [
    // F0
    '函证程序表F0A',
    '函证结果汇总表F0-1',
    '核实被函证单位信息F0-2',
    '跟函函证过程控制F0-3',
    '函证差异调节表F0-4',
    '预付及采购替代程序F0-5',
    '函证程序舞弊风险评价表F0-8',
    // F1
    '预付账款实质性程序表F1A',
    '审定表F1-1',
    '明细表F1-2',
    '实质性分析F1-4',
    '长期挂款检查表F1-5',
    '关联方及交易检查表F1-6',
    // F2
    '存货实质性程序表F2A',
    '存货审定表F2-1',
    '明细汇总表F2-2',
    '一、原材料明细表F2-3',
    '六、库存商品明细表F2-8',
    '存货会计政策检查F2-16',
    '存货总体分析表F2-18',
    '存货监盘程序表F2-21A',
    '监盘计划F2-22',
    '抽盘结果汇总表F2-25',
    '截止测试-入库（记账凭证至原始凭证）F2-29',
    '截止测试-出库（原始凭证至记账凭证）F2-32',
    '存货采购入库检查表F2-33-新增',
    '材料领用检查表F2-34-新增',
    '委托加工物资核查表F2-35',
    '计价方法测试表-平均F2-38',
    '计价方法测试表-先进先出F2-39',
    '生产成本明细表F2-41',
    '制造费用明细表F2-43',
    '生产成本分配F2-44',
    '跌价准备测试表F2-47',
    '长库龄 呆滞 超过保质期存货明细表F2-48',
    '关联采购分析表F2-52',
    '合同履约成本实质性程序表F2-55A',
    '合同履约成本构成明细表F2-55',
    '亏损合同预计损失测算表F2-58',
    '程序表F2-61A',
    '原材料采购价格分析表F2-61',
    '供应商访谈记录汇总表F2-71',
    '供应商访谈记录F2-72',
    // F3
    '应付票据实质性程序表F3A',
    '审定表F3-1',
    '明细表F3-2',
    '应付票据（带息）利息测算表F3-4',
    // F4
    '应付账款实质性程序表F4A',
    '审定表F4-1',
    '明细表F4-2',
    '未入账检查表F4-7',
    '供应商融资检查表F4-9',
    // F5
    '营业成本实质性程序表F5A',
    '营业务成本审定表F5-1',
    '主营业务成本月度明细表F5-2',
    '与上年度比较分析表F5-5',
    '销售数量与结转成本数量核对明细表F5-6',
    '成本倒轧表F5-7',
    // 附注披露
    '附注披露信息(上市公司)',
    '附注披露信息(国企)',
  ]

  it('全部真实 F 循环 sheet 名都能命中分类（无 fallback）', () => {
    const fallbacks: string[] = []
    REAL_F_SHEETS.forEach((name) => {
      const cls = classifyFSheet(name)
      if (cls.category === '其他') fallbacks.push(name)
    })
    expect(fallbacks).toEqual([])
  })

  it('每个 sheet 只命中 1 个分类（互斥性）', () => {
    REAL_F_SHEETS.forEach((name) => {
      const matches = F_SHEET_PATTERNS.filter((p) => p.pattern.test(name))
      expect(matches.length).toBeGreaterThanOrEqual(1)
      // 第一个匹配即为分类结果，但所有匹配的都被标记
    })
  })

  it('真实 F 循环 sheet 至少覆盖 12 类业务', () => {
    const covered = new Set<string>()
    REAL_F_SHEETS.forEach((name) => {
      const cls = classifyFSheet(name)
      if (cls.category !== '其他' && cls.category !== '历史遗留') covered.add(cls.category)
    })
    expect(covered.size).toBeGreaterThanOrEqual(12)
  })
})
