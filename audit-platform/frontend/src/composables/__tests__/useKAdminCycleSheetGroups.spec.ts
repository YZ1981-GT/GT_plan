/**
 * useKAdminCycleSheetGroups.spec.ts — K-F2 Task 2.2 + k-admin-cycle-post-review-fix Task 4.5
 *
 * Validates: Requirements K-F2, 2.7, 2.8, 3.4, 3.8
 *
 * 验证 11 类分组规则对 K 循环 109 个有效 sheet 全覆盖（采样 36+ 个代表）：
 *   1. 索引（底稿目录/GT_Custom）→ defaultHidden=true
 *   2. 程序表（实质性程序表 / 函证程序表 / xxA 结尾）
 *   3. 审定表（审定表 / 情况表 / 函证结果汇总）
 *   4. 费用明细（明细表K8-2 / 明细表K9-2 / K10-2~K13-2，优先级前置）
 *   5. 明细表（其他 明细表）
 *   6. 分析程序（分析 / 对比）
 *   7. 往来款检查（K1-/K3- 含 检查/账龄/挂账/关联方/三阶段/未收回/大额/坏账）
 *   8. 检查表（检查表 / 计提 / 分配 / 截止性测试 / 测算 / 测试表 / 政策检查 / 核对表）
 *   9. 函证辅助（K0-x 函证/替代程序/回函/核实/舞弊风险/差异调节/过程控制/会计提示）
 *  10. 附注+调整（附注披露 → defaultHidden=true / 调整分录）
 *  11. 其他（fallback）
 */
import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import {
  classifyKSheet,
  K_SHEET_GROUP_RULES,
  FALLBACK_GROUP,
  useKAdminCycleSheetGroups,
} from '../useKAdminCycleSheetGroups'

// ===== K 循环代表 sheet 名（openpyxl 实测，36 sheet） =====

const K_SAMPLE_SHEETS = [
  // 索引
  '底稿目录',
  'GT_Custom',
  // 程序表
  '函证程序表K0A',
  '实质性程序表 K1A',
  '实质性程序表 K2A',
  '实质性程序表K3A',
  '实质性程序表 K5A',
  '实质性程序表K8A',
  '实质性程序表K9A',
  '实质性程序表 K11A',
  // 审定表
  '审定表K1-1',
  '审定表 K5-1',
  '审定表K8-1',
  '审定表K9-1',
  '审定表K11-1',
  '函证结果汇总表K0-1',
  // 费用明细（K8-2/K9-2）
  '明细表K8-2',
  '明细表K9-2',
  // 明细表（其他）
  '明细表K1-2',
  '明细表 K5-2', // 含空格
  '明细表K3-2',
  '明细表K10-2',
  // 分析程序
  '实质性分析K8-4',
  '实质性分析K9-4',
  '大额其他应收款情况分析表K1-5',
  '大额其他应付款情况分析表K3-4',
  // 往来款检查（K1-/K3-）
  '关联方及交易检查表K1-11',
  '坏账准备转回（收回）、核销检查表K1-9',
  '长期未收回款项检查表K1-10',
  '三阶段划分检查表K1-7',
  '其他应收款检查表K1-12',
  '长期挂账检查表K3-5',
  '关联方及交易检查表K3-6',
  // 检查表（通用）
  '截止性测试(从记账凭证至原始凭证）K8-6',
  '截止性测试（从原始凭证至记账凭证）K8-7',
  '截止性测试(从记账凭证至原始凭证）K9-6',
  '弃置费用检查表 K5-5',
  '产品质量保修检查表 K5-4',
  '未决诉讼检查表 K5-6',
  '预计负债检查表 K5-7',
  '管理费用检查表K9-8',
  '销售费用检查表K8-8',
  '合同检查表K8-5',
  '合同检查表K9-5',
  '坏账准备测算K1-8',
  '减值准备测试表（后续计量） K6-5',
  '处置组减值测试表（后续计量） K6-6',
  '初始确认检查表K6-4',
  '摊销测算表K2-5',
  '政府补助核对表K10-4',
  '坏账准备明细表K1-3', // 含"明细表"，会被 detail 命中（priority 4 在 receivable_payable_check 前）
  '信用减值损失会计政策检查K1-6',
  // 附注+调整
  '附注披露信息(上市公司)',
  '附注披露信息(国企)',
  '附注披露信息（上市公司）',
  '附注披露信息（国企）',
  '附注披露信息（国有企业）',
  '调整分录汇总K1-4',
  '调整分录汇总K8-3',
  '调整分录汇总 K5-3',
  // 其他
  '会计提示',
  '邮件传真回函可靠性验证K0-7',
  '函证差异调节表K0-4',
  '跟函函证过程控制K0-3',
  '核实被函证单位信息K0-2',
  '函证程序舞弊风险评价表K0-8',
  '应收政府补助检查表K10-5',
  '其他流动负债检查表 K4-4',
  '其他流动资产检查表表K2-6',
  '递延收益检查表K7-5',
  '其他应付款替代程序K0-6',
  '其他应收款替代程序K0-5',
  '其他收益检查表K10-6',
  '其他应付款检查表K3-7', // K3- 含 检查 → 往来款检查
  '检查表（不再满足持有待售）K6-7',
  '营业外支出检查表K13-4',
  '营业外收入检查表K12-4',
  '合同取得成本明细表K2-4',
  '应收政府补助检查表K10-5',
]

// ===== 预期分类（关键代表） =====

const EXPECTED: Record<string, string> = {
  // 索引
  '底稿目录': '索引',
  'GT_Custom': '索引',
  // 程序表
  '函证程序表K0A': '程序表',
  '实质性程序表 K1A': '程序表',
  '实质性程序表 K11A': '程序表',
  '实质性程序表K8A': '程序表',
  // 审定表
  '审定表K1-1': '审定表',
  '审定表 K5-1': '审定表',
  '审定表K8-1': '审定表',
  '函证结果汇总表K0-1': '审定表',
  // 费用明细（K8-2/K9-2/K10-2~K13-2 优先匹配，priority 3）
  '明细表K8-2': '费用明细',
  '明细表K9-2': '费用明细',
  '明细表K10-2': '费用明细',
  // 明细表（其他）
  '明细表K1-2': '明细表',
  '明细表 K5-2': '明细表', // 含空格
  '明细表K3-2': '明细表',
  // 分析程序
  '实质性分析K8-4': '分析程序',
  '实质性分析K9-4': '分析程序',
  '大额其他应收款情况分析表K1-5': '分析程序', // 含"分析"
  '大额其他应付款情况分析表K3-4': '分析程序',
  // 往来款检查（K1-/K3- 含 检查/账龄/挂账/关联方/三阶段/未收回/大额/坏账）
  '关联方及交易检查表K1-11': '往来款检查',
  '坏账准备转回（收回）、核销检查表K1-9': '往来款检查',
  '长期未收回款项检查表K1-10': '往来款检查',
  '三阶段划分检查表K1-7': '往来款检查',
  '其他应收款检查表K1-12': '往来款检查',
  '长期挂账检查表K3-5': '往来款检查',
  '关联方及交易检查表K3-6': '往来款检查',
  '其他应付款检查表K3-7': '往来款检查',
  '信用减值损失会计政策检查K1-6': '往来款检查',
  // 检查表（通用）
  '截止性测试(从记账凭证至原始凭证）K8-6': '检查表',
  '截止性测试（从原始凭证至记账凭证）K8-7': '检查表',
  '截止性测试(从记账凭证至原始凭证）K9-6': '检查表',
  '弃置费用检查表 K5-5': '检查表',
  '产品质量保修检查表 K5-4': '检查表',
  '未决诉讼检查表 K5-6': '检查表',
  '预计负债检查表 K5-7': '检查表',
  '管理费用检查表K9-8': '检查表',
  '销售费用检查表K8-8': '检查表',
  '合同检查表K8-5': '检查表',
  '合同检查表K9-5': '检查表',
  '坏账准备测算K1-8': '往来款检查',
  '减值准备测试表（后续计量） K6-5': '检查表',
  '处置组减值测试表（后续计量） K6-6': '检查表',
  '初始确认检查表K6-4': '检查表',
  '摊销测算表K2-5': '检查表',
  '政府补助核对表K10-4': '检查表',
  // 坏账准备明细表 — 含 "明细表" → priority 4 detail 命中，先于 priority 6 往来款检查
  '坏账准备明细表K1-3': '明细表',
  // 附注+调整
  '附注披露信息(上市公司)': '附注+调整',
  '附注披露信息(国企)': '附注+调整',
  '附注披露信息（上市公司）': '附注+调整',
  '附注披露信息（国企）': '附注+调整',
  '附注披露信息（国有企业）': '附注+调整',
  '调整分录汇总K1-4': '附注+调整',
  '调整分录汇总K8-3': '附注+调整',
  '调整分录汇总 K5-3': '附注+调整',
  // 检查表（杂项）
  '应收政府补助检查表K10-5': '检查表',
  '其他收益检查表K10-6': '检查表',
  '检查表（不再满足持有待售）K6-7': '检查表',
  '营业外支出检查表K13-4': '检查表',
  '营业外收入检查表K12-4': '检查表',
  '其他流动负债检查表 K4-4': '检查表',
  '其他流动资产检查表表K2-6': '检查表',
  '递延收益检查表K7-5': '检查表',
  // 合同取得成本明细表 含"明细表" → 明细表
  '合同取得成本明细表K2-4': '明细表',
  // 函证辅助（K0 函证特殊 sheet — 新增 priority 7.5 分组）
  '会计提示': '其他', // 无 K0-x 编号，不匹配 confirmation_aux
  '邮件传真回函可靠性验证K0-7': '函证辅助',
  '函证差异调节表K0-4': '函证辅助',
  '跟函函证过程控制K0-3': '函证辅助',
  '核实被函证单位信息K0-2': '函证辅助',
  '函证程序舞弊风险评价表K0-8': '函证辅助',
  '其他应付款替代程序K0-6': '函证辅助',
  '其他应收款替代程序K0-5': '函证辅助',
}

// ===== 结构性校验 =====

describe('K_SHEET_GROUP_RULES — 结构性校验', () => {
  it('规则数组共 11 条（10 显式类 + 1 fallback），按 priority 升序排列', () => {
    expect(K_SHEET_GROUP_RULES).toHaveLength(11)
    for (let i = 1; i < K_SHEET_GROUP_RULES.length; i++) {
      expect(K_SHEET_GROUP_RULES[i].priority).toBeGreaterThanOrEqual(
        K_SHEET_GROUP_RULES[i - 1].priority,
      )
    }
    expect(K_SHEET_GROUP_RULES[0].id).toBe('index')
    expect(K_SHEET_GROUP_RULES[0].priority).toBe(0)
    expect(K_SHEET_GROUP_RULES[K_SHEET_GROUP_RULES.length - 1].id).toBe('other')
    expect(K_SHEET_GROUP_RULES[K_SHEET_GROUP_RULES.length - 1].priority).toBe(9)
  })

  it('规则 id 全部唯一', () => {
    const ids = K_SHEET_GROUP_RULES.map((r) => r.id)
    expect(new Set(ids).size).toBe(ids.length)
  })

  it('每条规则均含必需字段', () => {
    for (const r of K_SHEET_GROUP_RULES) {
      expect(typeof r.id).toBe('string')
      expect(typeof r.category).toBe('string')
      expect(typeof r.icon).toBe('string')
      expect(r.color).toMatch(/^#[0-9a-fA-F]{6}$/)
      expect(typeof r.priority).toBe('number')
      expect(typeof r.match).toBe('function')
    }
  })

  it('FALLBACK_GROUP 与末项规则一致', () => {
    const last = K_SHEET_GROUP_RULES[K_SHEET_GROUP_RULES.length - 1]
    expect(FALLBACK_GROUP.category).toBe(last.category)
    expect(FALLBACK_GROUP.priority).toBe(last.priority)
  })
})

// ===== 关键代表 sheet 分类验证 =====

describe('classifyKSheet — 关键代表 sheet 命中预期类别 (K-F2)', () => {
  it('每个关键代表 sheet 与 EXPECTED 映射一致', () => {
    for (const [name, expected] of Object.entries(EXPECTED)) {
      const result = classifyKSheet(name)
      expect(result.category, `sheet="${name}"`).toBe(expected)
    }
  })

  it('索引类 defaultHidden=true', () => {
    expect(classifyKSheet('底稿目录').defaultHidden).toBe(true)
    expect(classifyKSheet('GT_Custom').defaultHidden).toBe(true)
  })

  it('附注披露类 defaultHidden=true（5 种括号变体全覆盖）', () => {
    const variants = [
      '附注披露信息(上市公司)',
      '附注披露信息(国企)',
      '附注披露信息（上市公司）',
      '附注披露信息（国企）',
      '附注披露信息（国有企业）',
    ]
    for (const name of variants) {
      const r = classifyKSheet(name)
      expect(r.category).toBe('附注+调整')
      expect(r.defaultHidden).toBe(true)
    }
  })

  it('调整分录类 defaultHidden=false（不隐藏）', () => {
    const r = classifyKSheet('调整分录汇总K1-4')
    expect(r.category).toBe('附注+调整')
    expect(r.defaultHidden).toBeFalsy()
  })

  it('K8-2/K9-2 优先匹配 费用明细（priority 3 < 明细表 priority 4）', () => {
    expect(classifyKSheet('明细表K8-2').category).toBe('费用明细')
    expect(classifyKSheet('明细表K9-2').category).toBe('费用明细')
    // K1-2/K3-2 不匹配 expense_detail，落到 detail
    expect(classifyKSheet('明细表K1-2').category).toBe('明细表')
    expect(classifyKSheet('明细表K3-2').category).toBe('明细表')
  })

  it('K5-2 sheet 名含空格仍被分类为 明细表', () => {
    expect(classifyKSheet('明细表 K5-2').category).toBe('明细表')
  })

  it('K1-/K3- 通用检查表归入 往来款检查（K-circle 业务专项）', () => {
    expect(classifyKSheet('关联方及交易检查表K1-11').category).toBe(
      '往来款检查',
    )
    expect(classifyKSheet('长期挂账检查表K3-5').category).toBe('往来款检查')
    expect(classifyKSheet('信用减值损失会计政策检查K1-6').category).toBe(
      '往来款检查',
    )
  })

  it('K1- 含"明细表"先归"明细表"，再不入"往来款检查"（优先级铁律）', () => {
    // 坏账准备明细表K1-3 含"明细表" → priority 4 detail 命中
    expect(classifyKSheet('坏账准备明细表K1-3').category).toBe('明细表')
  })

  it('截止性测试 / 测算 / 测试表 命中 检查表（非 K1/K3）', () => {
    expect(classifyKSheet('截止性测试(从记账凭证至原始凭证）K8-6').category).toBe(
      '检查表',
    )
    // 坏账准备测算K1-8 含 K1- + 坏账 → 优先 往来款检查（priority 6）
    expect(classifyKSheet('坏账准备测算K1-8').category).toBe('往来款检查')
    expect(
      classifyKSheet('减值准备测试表（后续计量） K6-5').category,
    ).toBe('检查表')
  })
})

// ===== 优先级冲突解决 =====

describe('classifyKSheet — 优先级冲突解决', () => {
  it('"实质性分析K8-4" 含"分析" → 分析程序(5)，不被审定表/明细表误命中', () => {
    expect(classifyKSheet('实质性分析K8-4').category).toBe('分析程序')
  })

  it('"大额其他应收款情况分析表K1-5" 含"分析"+"K1-" → 优先 分析程序(5)，先于往来款检查(6)', () => {
    expect(classifyKSheet('大额其他应收款情况分析表K1-5').category).toBe(
      '分析程序',
    )
  })

  it('"函证结果汇总表K0-1" 含"函证结果汇总" → 审定表(2)', () => {
    expect(classifyKSheet('函证结果汇总表K0-1').category).toBe('审定表')
  })

  it('"函证程序表K0A" 含"函证程序表" → 程序表(1)', () => {
    expect(classifyKSheet('函证程序表K0A').category).toBe('程序表')
  })

  it('"合同取得成本明细表K2-4" 含"明细表" → 明细表(4)', () => {
    expect(classifyKSheet('合同取得成本明细表K2-4').category).toBe('明细表')
  })
})

// ===== 函证辅助 + 费用明细 regex 扩展验证（k-admin-cycle-post-review-fix Task 4.5） =====

describe('classifyKSheet — 函证辅助分组 (Req 2.7)', () => {
  it('函证差异调节表K0-4 → category=函证辅助', () => {
    expect(classifyKSheet('函证差异调节表K0-4').category).toBe('函证辅助')
  })

  it('核实被函证单位信息K0-2 → category=函证辅助', () => {
    expect(classifyKSheet('核实被函证单位信息K0-2').category).toBe('函证辅助')
  })

  it('K0 函证相关 sheet 全部归入函证辅助', () => {
    const confirmationSheets = [
      '邮件传真回函可靠性验证K0-7',
      '跟函函证过程控制K0-3',
      '函证程序舞弊风险评价表K0-8',
      '其他应付款替代程序K0-6',
      '其他应收款替代程序K0-5',
    ]
    for (const name of confirmationSheets) {
      expect(classifyKSheet(name).category, `sheet="${name}"`).toBe('函证辅助')
    }
  })

  it('会计提示（无 K0-x 编号）不归入函证辅助，归其他', () => {
    expect(classifyKSheet('会计提示').category).toBe('其他')
  })
})

describe('classifyKSheet — 费用明细 regex 扩展 (Req 2.8)', () => {
  it('明细表K10-2 → category=费用明细', () => {
    expect(classifyKSheet('明细表K10-2').category).toBe('费用明细')
  })

  it('明细表K13-2 → category=费用明细', () => {
    expect(classifyKSheet('明细表K13-2').category).toBe('费用明细')
  })

  it('K8-2/K9-2 仍归费用明细（保持不变）', () => {
    expect(classifyKSheet('明细表K8-2').category).toBe('费用明细')
    expect(classifyKSheet('明细表K9-2').category).toBe('费用明细')
  })

  it('K11-2/K12-2 也归费用明细（扩展覆盖）', () => {
    expect(classifyKSheet('明细表K11-2').category).toBe('费用明细')
    expect(classifyKSheet('明细表K12-2').category).toBe('费用明细')
  })

  it('K1-2/K3-2 仍归明细表（不受扩展影响）', () => {
    expect(classifyKSheet('明细表K1-2').category).toBe('明细表')
    expect(classifyKSheet('明细表K3-2').category).toBe('明细表')
  })
})

// ===== 完备性 / fallback =====

describe('classifyKSheet — 完备性', () => {
  it('任意 sheet 名（含极端字符串）恒返回非 null 类目', () => {
    const edgeCases = ['', ' ', 'abc', '123', '!@#$%', 'A'.repeat(200), '中文']
    for (const name of edgeCases) {
      const cls = classifyKSheet(name)
      expect(cls).toBeDefined()
      expect(typeof cls.category).toBe('string')
      expect(cls.category.length).toBeGreaterThan(0)
    }
  })

  it('不匹配任何规则的 sheet 归入"其他"', () => {
    expect(classifyKSheet('随便的名字').category).toBe('其他')
    expect(classifyKSheet('').category).toBe('其他')
  })
})

// ===== composable 集成 =====

describe('useKAdminCycleSheetGroups — composable 行为', () => {
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
    const nav = useKAdminCycleSheetGroups(apiRef)
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
      '调整分录汇总K1-4',
      '审定表K8-1',
      '明细表K8-2',
    ]
    const apiRef = ref<any>(createMockUniverAPI(samples))
    const nav = useKAdminCycleSheetGroups(apiRef)
    nav.refresh()

    const names = nav.sheets.value.map((s) => s.name)
    expect(names).not.toContain('底稿目录')
    expect(names).not.toContain('GT_Custom')
    expect(names).not.toContain('附注披露信息(上市公司)')
    expect(names).not.toContain('附注披露信息（国企）')
    expect(names).toContain('调整分录汇总K1-4')
    expect(names).toContain('审定表K8-1')
    expect(names).toContain('明细表K8-2')
  })

  it('groups 按 priority 升序排列', () => {
    const apiRef = ref<any>(createMockUniverAPI(K_SAMPLE_SHEETS))
    const nav = useKAdminCycleSheetGroups(apiRef)
    nav.refresh()

    const priorities = nav.groups.value.map((g) => g.priority)
    for (let i = 1; i < priorities.length; i++) {
      expect(priorities[i]).toBeGreaterThanOrEqual(priorities[i - 1])
    }
  })
})
