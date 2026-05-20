/**
 * useGInvestmentCycleSheetGroups vitest
 *
 * spec workpaper-g-investment-cycle ADR-G2（Task 1.2）
 *
 * Validates: Requirements G-F3.1 ~ G-F3.6
 *
 * 4 case 覆盖：
 *   1. equity_method  → 显示权益法相关 G7 sheet，隐藏成本法/公允价值法
 *   2. cost_method    → 显示成本法相关 G7 sheet，隐藏权益法/公允价值法
 *   3. fair_value_method → 显示公允价值法相关 G7 sheet，隐藏权益法/成本法
 *   4. undefined fallback（无 g7_accounting_methods 字段）→ 不过滤，全部 G7 sheet 显示
 */
import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import {
  filterByG7AccountingMethod,
  isG7Sheet,
  isG7MethodSpecificSheet,
  resolveG7AccountingMethod,
  useGInvestmentCycleSheetGroups,
  classifyGSheet,
  G_SHEET_GROUP_RULES,
  FALLBACK_GROUP,
  type GParsedData,
  type G7AccountingMethod,
} from '../useGInvestmentCycleSheetGroups'

// ===== fixture：G7 三种方式典型 sheet 名 =====

/**
 * G7 sheet 池（覆盖三种方式 + 通用 sheet + 非 G7 sheet）
 *
 * 设计要点：
 *   - "减值测试" 在权益法和成本法均出现 —— 核算方式切换时不应被误隐
 *   - "审定表G7-1" 不含方式关键词 —— 应始终显示（G7 通用 sheet）
 *   - "G7A 总控台" 同上
 *   - "审定表G1-1" 不属于 G7 —— 应始终显示（其他循环不受 G7 方式影响）
 */
const G7_SHEETS = [
  // 权益法相关
  '权益法投资收益确认表G7-3',
  '权益变动分析表G7-4',
  '权益法对账表G7-5',
  // 成本法相关
  '成本法分红确认表G7-6',
  // 公允价值法相关
  '公允价值法变动损益表G7-7',
  '公允价值测试表G7-8',
  // 共享：减值测试（权益法 + 成本法均涉及）
  '减值测试表G7-9',
  // G7 通用 sheet（不含方式关键词，应始终显示）
  'G7A 长期股权投资程序总控台',
  '审定表G7-1',
  '明细表G7-2',
  // 非 G7 sheet（其他循环，不受 G7 方式影响）
  '审定表G1-1',
]

// ===== 4 case：核心验收（G-F3.2 / G-F3.3 / G-F3.4 / G-F3.5）=====

describe('useGInvestmentCycleSheetGroups - G7 三种核算方式切换 (G-F3)', () => {
  it('case 1: equity_method → 显示权益法相关 G7 sheet，隐藏成本法/公允价值法专属 sheet', () => {
    const items = G7_SHEETS.map((name) => ({ name }))
    const result = filterByG7AccountingMethod(items, 'equity_method')
    const names = result.map((s) => s.name)

    // 权益法相关 sheet 应保留
    expect(names).toContain('权益法投资收益确认表G7-3')
    expect(names).toContain('权益变动分析表G7-4')
    expect(names).toContain('权益法对账表G7-5')
    // 减值测试（共享）应保留
    expect(names).toContain('减值测试表G7-9')
    // G7 通用 sheet 应保留
    expect(names).toContain('G7A 长期股权投资程序总控台')
    expect(names).toContain('审定表G7-1')
    expect(names).toContain('明细表G7-2')
    // 非 G7 sheet 应保留
    expect(names).toContain('审定表G1-1')

    // 成本法专属（分红确认）应被隐藏
    expect(names).not.toContain('成本法分红确认表G7-6')
    // 公允价值法专属应被隐藏
    expect(names).not.toContain('公允价值法变动损益表G7-7')
    expect(names).not.toContain('公允价值测试表G7-8')
  })

  it('case 2: cost_method → 显示成本法相关 G7 sheet，隐藏权益法/公允价值法专属 sheet', () => {
    const items = G7_SHEETS.map((name) => ({ name }))
    const result = filterByG7AccountingMethod(items, 'cost_method')
    const names = result.map((s) => s.name)

    // 成本法相关 sheet 应保留
    expect(names).toContain('成本法分红确认表G7-6')
    // 减值测试（共享）应保留
    expect(names).toContain('减值测试表G7-9')
    // G7 通用 sheet 应保留
    expect(names).toContain('G7A 长期股权投资程序总控台')
    expect(names).toContain('审定表G7-1')
    expect(names).toContain('明细表G7-2')
    // 非 G7 sheet 应保留
    expect(names).toContain('审定表G1-1')

    // 权益法专属应被隐藏
    expect(names).not.toContain('权益法投资收益确认表G7-3')
    expect(names).not.toContain('权益变动分析表G7-4')
    expect(names).not.toContain('权益法对账表G7-5')
    // 公允价值法专属应被隐藏
    expect(names).not.toContain('公允价值法变动损益表G7-7')
    expect(names).not.toContain('公允价值测试表G7-8')
  })

  it('case 3: fair_value_method → 显示公允价值法相关 G7 sheet，隐藏权益法/成本法专属 sheet', () => {
    const items = G7_SHEETS.map((name) => ({ name }))
    const result = filterByG7AccountingMethod(items, 'fair_value_method')
    const names = result.map((s) => s.name)

    // 公允价值法相关 sheet 应保留
    expect(names).toContain('公允价值法变动损益表G7-7')
    expect(names).toContain('公允价值测试表G7-8')
    // G7 通用 sheet 应保留
    expect(names).toContain('G7A 长期股权投资程序总控台')
    expect(names).toContain('审定表G7-1')
    expect(names).toContain('明细表G7-2')
    // 非 G7 sheet 应保留
    expect(names).toContain('审定表G1-1')

    // 权益法专属应被隐藏
    expect(names).not.toContain('权益法投资收益确认表G7-3')
    expect(names).not.toContain('权益变动分析表G7-4')
    expect(names).not.toContain('权益法对账表G7-5')
    // 成本法专属（分红确认）应被隐藏
    expect(names).not.toContain('成本法分红确认表G7-6')
    // 减值测试不属于公允价值法关键词（fair_value 投资以公允价值计量，不做减值测试）
    // → 应被隐藏
    expect(names).not.toContain('减值测试表G7-9')
  })

  it('case 4: undefined fallback（无 g7_accounting_methods 字段）→ 不过滤，全部 sheet 保留 (G-F3.5)', () => {
    const items = G7_SHEETS.map((name) => ({ name }))

    // 4.a undefined method → 全显
    const result1 = filterByG7AccountingMethod(items, undefined)
    expect(result1).toHaveLength(G7_SHEETS.length)
    expect(result1.map((s) => s.name)).toEqual(G7_SHEETS)

    // 4.b null method（与 undefined 行为一致）
    const result2 = filterByG7AccountingMethod(items, null)
    expect(result2).toHaveLength(G7_SHEETS.length)

    // 4.c parsed_data 缺字段 → resolveG7AccountingMethod 返回 null
    const parsedNoField: GParsedData = {}
    expect(resolveG7AccountingMethod(parsedNoField, '联营公司A')).toBeNull()

    // 4.d parsed_data 为 null → 返回 null
    expect(resolveG7AccountingMethod(null, '联营公司A')).toBeNull()
    expect(resolveG7AccountingMethod(undefined, '联营公司A')).toBeNull()

    // 4.e 空数组 → 返回 null
    const parsedEmpty: GParsedData = { g7_accounting_methods: [] }
    expect(resolveG7AccountingMethod(parsedEmpty, '联营公司A')).toBeNull()

    // 4.f 找不到 investee_name → 返回 null（继续走 fallback 全显）
    const parsedConfigured: GParsedData = {
      g7_accounting_methods: [
        { investee_name: '联营公司A', method: 'equity_method' },
      ],
    }
    expect(resolveG7AccountingMethod(parsedConfigured, '不存在的公司')).toBeNull()
    expect(resolveG7AccountingMethod(parsedConfigured, null)).toBeNull()
    expect(resolveG7AccountingMethod(parsedConfigured, undefined)).toBeNull()
  })
})

// ===== 辅助：G-F3.1（三种方式枚举） + G-F3.6（per-investment 持久化结构） =====

describe('resolveG7AccountingMethod - per-investment 配置解析 (G-F3.1, G-F3.6)', () => {
  it('G-F3.1: 支持三种核算方式枚举', () => {
    const validMethods: G7AccountingMethod[] = [
      'equity_method',
      'cost_method',
      'fair_value_method',
    ]
    for (const m of validMethods) {
      const parsed: GParsedData = {
        g7_accounting_methods: [{ investee_name: 'X', method: m }],
      }
      expect(resolveG7AccountingMethod(parsed, 'X')).toBe(m)
    }
  })

  it('G-F3.6: 多笔投资各自配置不同方式 — 按 investee_name 路由', () => {
    const parsed: GParsedData = {
      g7_accounting_methods: [
        { investee_name: '联营公司A', method: 'equity_method' },
        { investee_name: '子公司B', method: 'cost_method' },
        { investee_name: '少数股权C', method: 'fair_value_method' },
      ],
    }
    expect(resolveG7AccountingMethod(parsed, '联营公司A')).toBe('equity_method')
    expect(resolveG7AccountingMethod(parsed, '子公司B')).toBe('cost_method')
    expect(resolveG7AccountingMethod(parsed, '少数股权C')).toBe('fair_value_method')
  })
})

// ===== 辅助函数测试 =====

describe('isG7Sheet / isG7MethodSpecificSheet', () => {
  it('isG7Sheet 识别 G7 sheet', () => {
    expect(isG7Sheet('审定表G7-1')).toBe(true)
    expect(isG7Sheet('G7A 总控台')).toBe(true)
    expect(isG7Sheet('权益法投资收益确认表G7-3')).toBe(true)
    expect(isG7Sheet('审定表G1-1')).toBe(false)
    expect(isG7Sheet('审定表G6-1')).toBe(false)
  })

  it('isG7MethodSpecificSheet 识别方式专属 sheet', () => {
    // 方式专属
    expect(isG7MethodSpecificSheet('权益法投资收益确认表G7-3')).toBe(true)
    expect(isG7MethodSpecificSheet('成本法分红确认表G7-6')).toBe(true)
    expect(isG7MethodSpecificSheet('公允价值测试表G7-8')).toBe(true)
    // G7 通用（不含方式关键词）
    expect(isG7MethodSpecificSheet('审定表G7-1')).toBe(false)
    expect(isG7MethodSpecificSheet('G7A 总控台')).toBe(false)
    expect(isG7MethodSpecificSheet('明细表G7-2')).toBe(false)
  })
})

// ===== composable 集成（Univer mock + 响应式 method 切换） =====

describe('useGInvestmentCycleSheetGroups - composable 行为', () => {
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

  it('parsed_data 为 null/undefined 时 fallback 全显（不报错）', () => {
    const apiRef = ref<any>(createMockUniverAPI(G7_SHEETS))
    const parsedRef = ref<GParsedData | null>(null)
    const investeeRef = ref<string | null>(null)
    const nav = useGInvestmentCycleSheetGroups(apiRef, parsedRef, investeeRef)
    expect(() => nav.refresh()).not.toThrow()
    expect(nav.totalCount.value).toBe(G7_SHEETS.length)
    expect(nav.currentMethod.value).toBeNull()
  })

  it('选中 equity_method 投资 → sheet 列表过滤为权益法子集', () => {
    const apiRef = ref<any>(createMockUniverAPI(G7_SHEETS))
    const parsedRef = ref<GParsedData | null>({
      g7_accounting_methods: [
        { investee_name: '联营公司A', method: 'equity_method' },
      ],
    })
    const investeeRef = ref<string | null>('联营公司A')
    const nav = useGInvestmentCycleSheetGroups(apiRef, parsedRef, investeeRef)
    nav.refresh()

    expect(nav.currentMethod.value).toBe('equity_method')
    const names = nav.sheets.value.map((s) => s.name)
    expect(names).toContain('权益法投资收益确认表G7-3')
    expect(names).not.toContain('成本法分红确认表G7-6')
    expect(names).not.toContain('公允价值法变动损益表G7-7')
  })

  it('univerAPI 为 null 时 sheets 列表为空，无异常抛出', () => {
    const apiRef = ref<any>(null)
    const nav = useGInvestmentCycleSheetGroups(apiRef)
    expect(() => nav.refresh()).not.toThrow()
    expect(nav.totalCount.value).toBe(0)
    expect(nav.groups.value).toEqual([])
  })
})

// ===== Task 2.3: G_SHEET_GROUP_RULES 12 类规则全覆盖 =====
//
// Validates: Requirements G-F2.1, G-F2.2, G-F2.3
//
// 设计要点（参考 design.md ADR-G6 + Sprint 0 实测）：
//   - 12 个显式类目（id=index/historical/procedure/audit_table/disclosure/
//     detail/fair_value/impairment/income_calc/classification/confirmation/
//     adjustment）+ 1 个 fallback 类目（id=other）= 13 条规则
//   - priority 升序匹配，首个命中即停止 → 任意 sheet 名恰好命中 1 类
//   - 索引 + 历史遗留 defaultHidden=true；附注披露 readonly=true
//   - 关键冲突解决：'函证程序表G0A' 同时命中 procedure(2) 和 confirmation(10)
//     → priority 升序优先，归入"总控台"

describe('G_SHEET_GROUP_RULES — 12 类规则全覆盖 (Task 2.3, G-F2)', () => {
  // ---------- 结构性校验 ----------

  it('规则数组共 13 条（12 显式类 + 1 fallback），按 priority 升序排列', () => {
    expect(G_SHEET_GROUP_RULES).toHaveLength(13)
    // priority 严格升序（无并列）
    for (let i = 1; i < G_SHEET_GROUP_RULES.length; i++) {
      expect(G_SHEET_GROUP_RULES[i].priority).toBeGreaterThan(
        G_SHEET_GROUP_RULES[i - 1].priority,
      )
    }
    // 首尾边界
    expect(G_SHEET_GROUP_RULES[0].id).toBe('index')
    expect(G_SHEET_GROUP_RULES[0].priority).toBe(0)
    expect(G_SHEET_GROUP_RULES[G_SHEET_GROUP_RULES.length - 1].id).toBe('other')
    expect(G_SHEET_GROUP_RULES[G_SHEET_GROUP_RULES.length - 1].priority).toBe(12)
  })

  it('规则 id 全部唯一', () => {
    const ids = G_SHEET_GROUP_RULES.map((r) => r.id)
    expect(new Set(ids).size).toBe(ids.length)
  })

  it('每条规则均含必需字段（id / category / icon / color / priority / match）', () => {
    for (const r of G_SHEET_GROUP_RULES) {
      expect(typeof r.id).toBe('string')
      expect(typeof r.category).toBe('string')
      expect(typeof r.icon).toBe('string')
      expect(r.color).toMatch(/^#[0-9a-fA-F]{6}$/)
      expect(typeof r.priority).toBe('number')
      expect(typeof r.match).toBe('function')
    }
  })

  it('FALLBACK_GROUP 与末项规则一致（id=other，priority=12）', () => {
    const last = G_SHEET_GROUP_RULES[G_SHEET_GROUP_RULES.length - 1]
    expect(FALLBACK_GROUP.category).toBe(last.category)
    expect(FALLBACK_GROUP.priority).toBe(last.priority)
    expect(FALLBACK_GROUP.icon).toBe(last.icon)
    expect(FALLBACK_GROUP.color).toBe(last.color)
  })

  // ---------- 12 类各自命中代表性 sheet（来自 design.md ADR-G6 verbatim） ----------

  it('类 1 索引：底稿目录 / GT_Custom 命中（defaultHidden=true）', () => {
    expect(classifyGSheet('底稿目录').category).toBe('索引')
    expect(classifyGSheet('GT_Custom').category).toBe('索引')
    expect(classifyGSheet('底稿目录').defaultHidden).toBe(true)
    expect(classifyGSheet('GT_Custom').defaultHidden).toBe(true)
    expect(classifyGSheet('底稿目录').priority).toBe(0)
  })

  it('类 2 历史遗留：投资收益实质性程序表G11A-修订前 / G11-1（原）/ 含示例 命中（defaultHidden=true）', () => {
    expect(classifyGSheet('投资收益实质性程序表G11A-修订前').category).toBe(
      '历史遗留',
    )
    expect(classifyGSheet('审定表G11-1（原）').category).toBe('历史遗留')
    expect(classifyGSheet('明细表G11-2(原)').category).toBe('历史遗留')
    expect(classifyGSheet('某sheet（示例）').category).toBe('历史遗留')
    expect(classifyGSheet('投资收益实质性程序表G11A-修订前').defaultHidden).toBe(
      true,
    )
    expect(classifyGSheet('投资收益实质性程序表G11A-修订前').priority).toBe(1)
  })

  it('类 3 总控台：G1A / G7A / G11A / 实质性程序表X 命中（regex /[A-Z]\\d*A$/ 或 /实质性程序/）', () => {
    // 程序表以"xxA"结尾（裸 wp_code 形式）
    expect(classifyGSheet('G1A').category).toBe('总控台')
    expect(classifyGSheet('G7A').category).toBe('总控台')
    expect(classifyGSheet('G11A').category).toBe('总控台')
    expect(classifyGSheet('G0A').category).toBe('总控台')
    // 含"实质性程序"
    expect(classifyGSheet('实质性程序表X').category).toBe('总控台')
    expect(classifyGSheet('投资收益实质性程序表G11A').category).toBe('总控台')
    // 同时命中两个条件
    expect(classifyGSheet('G1A').priority).toBe(2)
  })

  it('类 4 审定表：审定表G1-1 / 审定表G7-1 命中', () => {
    expect(classifyGSheet('审定表G1-1').category).toBe('审定表')
    expect(classifyGSheet('审定表G7-1').category).toBe('审定表')
    expect(classifyGSheet('审定表G11-1').category).toBe('审定表')
    expect(classifyGSheet('审定表G1-1').priority).toBe(3)
  })

  it('类 5 附注披露：附注披露(上市公司) / 附注披露(国企) 命中（readonly=true）', () => {
    expect(classifyGSheet('附注披露信息(上市公司)').category).toBe('附注披露')
    expect(classifyGSheet('附注披露信息(国企)').category).toBe('附注披露')
    expect(classifyGSheet('附注披露信息(上市公司)').readonly).toBe(true)
    expect(classifyGSheet('附注披露信息(国企)').readonly).toBe(true)
    expect(classifyGSheet('附注披露信息(上市公司)').priority).toBe(4)
  })

  it('类 6 明细表：明细表G1-2 / 明细表G7-2 / 结存表G1-4 命中', () => {
    expect(classifyGSheet('明细表G1-2').category).toBe('明细表')
    expect(classifyGSheet('明细表G7-2').category).toBe('明细表')
    expect(classifyGSheet('结存表G1-4').category).toBe('明细表')
    // 注意：'明细分析表G11-2' 不含子串 '明细表'，归入 fallback 其他程序（regex 限制）
    expect(classifyGSheet('明细分析表G11-2').category).toBe('其他程序')
    expect(classifyGSheet('明细表G1-2').priority).toBe(5)
  })

  it('类 7 公允价值测试：公允价值测试表G1-6 / 第三层次公允价值计量的调节表G1-7 命中', () => {
    expect(classifyGSheet('公允价值测试表G1-6').category).toBe('公允价值测试')
    expect(classifyGSheet('第三层次公允价值计量的调节表G1-7').category).toBe(
      '公允价值测试',
    )
    expect(classifyGSheet('公允价值测试表G7-8').category).toBe('公允价值测试')
    expect(classifyGSheet('公允价值测试表G1-6').priority).toBe(6)
  })

  it('类 8 减值测试：减值测试表G7-9 / 信用减值损失审计程序表 / ECL 测试 命中', () => {
    expect(classifyGSheet('减值测试表G7-9').category).toBe('减值测试')
    expect(classifyGSheet('信用减值损失审计程序表').category).toBe('减值测试')
    expect(classifyGSheet('ECL 三阶段测试').category).toBe('减值测试')
    expect(classifyGSheet('减值测试表G7-9').priority).toBe(7)
  })

  it('类 9 收益测算：收益测算表G1-5 / 投资收益确认表 / 利息收入测算 命中', () => {
    expect(classifyGSheet('收益测算表G1-5').category).toBe('收益测算')
    expect(classifyGSheet('投资收益确认表').category).toBe('收益测算')
    expect(classifyGSheet('利息收入测算G4-3').category).toBe('收益测算')
    expect(classifyGSheet('收益测算表G1-5').priority).toBe(8)
  })

  it('类 10 分类检查：业务模式分析G1-8 / 合同现金流量特征分析G1-10 / SPPI 测试 命中', () => {
    expect(classifyGSheet('业务模式分析G1-8').category).toBe('分类检查')
    expect(classifyGSheet('合同现金流量特征分析G1-10').category).toBe('分类检查')
    expect(classifyGSheet('SPPI测试').category).toBe('分类检查')
    expect(classifyGSheet('金融资产分类适当性分析').category).toBe('分类检查')
    expect(classifyGSheet('业务模式分析G1-8').priority).toBe(9)
  })

  it('类 11 函证：函证结果汇总表G0-1 / 核实被函证单位信息G0-2 / 跟函记录 命中', () => {
    expect(classifyGSheet('函证结果汇总表G0-1').category).toBe('函证')
    expect(classifyGSheet('核实被函证单位信息G0-2').category).toBe('函证')
    expect(classifyGSheet('跟函记录表').category).toBe('函证')
    expect(classifyGSheet('替代程序记录').category).toBe('函证')
    expect(classifyGSheet('函证结果汇总表G0-1').priority).toBe(10)
  })

  it('类 12 调整分录：调整分录汇总表G1-12 / 调整分录汇总G11-3 命中', () => {
    expect(classifyGSheet('调整分录汇总表G1-12').category).toBe('调整分录')
    expect(classifyGSheet('调整分录汇总G11-3').category).toBe('调整分录')
    expect(classifyGSheet('调整分录汇总表G1-12').priority).toBe(11)
  })

  it('Fallback 其他程序：有价证券监盘表G1-11 / 衍生金融工具核查表G1-14 命中', () => {
    expect(classifyGSheet('有价证券监盘表G1-11').category).toBe('其他程序')
    expect(classifyGSheet('衍生金融工具核查表G1-14').category).toBe('其他程序')
    expect(classifyGSheet('随便的一个名字').category).toBe('其他程序')
    expect(classifyGSheet('').category).toBe('其他程序')
    expect(classifyGSheet('有价证券监盘表G1-11').priority).toBe(12)
  })

  // ---------- 优先级冲突解决（design.md ADR-G6 关键冲突解决段落） ----------

  describe('优先级冲突解决（priority 升序优先）', () => {
    it('"函证程序表G0A" 同时命中 procedure(2) 和 confirmation(10) → 总控台胜出', () => {
      // 既匹配 [A-Z]\d*A$（procedure），也匹配 /函证/（confirmation）
      const result = classifyGSheet('函证程序表G0A')
      expect(result.category).toBe('总控台')
      expect(result.priority).toBe(2)
    })

    it('"投资收益实质性程序表G11A-修订前" 同时命中 historical(1) 和 procedure(2) → 历史遗留胜出', () => {
      // 历史遗留 priority=1 < 总控台 priority=2
      const result = classifyGSheet('投资收益实质性程序表G11A-修订前')
      expect(result.category).toBe('历史遗留')
      expect(result.priority).toBe(1)
    })

    it('"审定表G11-1（原）" 同时命中 historical(1) 和 audit_table(3) → 历史遗留胜出', () => {
      const result = classifyGSheet('审定表G11-1（原）')
      expect(result.category).toBe('历史遗留')
    })

    it('"明细表G1-6 公允价值测试" 同时命中 detail(5) 和 fair_value(6) → 明细表胜出', () => {
      // 明细表 priority=5 < 公允价值测试 priority=6
      const result = classifyGSheet('明细表G1-6 公允价值测试')
      expect(result.category).toBe('明细表')
      expect(result.priority).toBe(5)
    })

    it('"投资收益减值测试表" 同时命中 impairment(7) 和 income_calc(8) → 减值测试胜出', () => {
      // 减值 priority=7 < 收益测算 priority=8
      const result = classifyGSheet('投资收益减值测试表')
      expect(result.category).toBe('减值测试')
      expect(result.priority).toBe(7)
    })

    it('"调整分录函证记录" 同时命中 confirmation(10) 和 adjustment(11) → 函证胜出', () => {
      // 函证 priority=10 < 调整分录 priority=11
      const result = classifyGSheet('调整分录函证记录')
      expect(result.category).toBe('函证')
      expect(result.priority).toBe(10)
    })
  })

  // ---------- 完备性：任意 sheet 名恰好命中 1 类（CP-5 示例验证） ----------

  describe('完备性：12 类规则覆盖任意 sheet 名（CP-5 示例验证）', () => {
    it('15 个 G 循环代表性 sheet 名各自归类正确', () => {
      const samples: Array<[string, string]> = [
        ['底稿目录', '索引'],
        ['投资收益实质性程序表G11A-修订前', '历史遗留'],
        ['G1A', '总控台'],
        ['投资收益实质性程序表G11A', '总控台'],
        ['审定表G7-1', '审定表'],
        ['附注披露信息(上市公司)', '附注披露'],
        ['明细表G7-2', '明细表'],
        ['公允价值测试表G1-6', '公允价值测试'],
        ['减值测试表G7-9', '减值测试'],
        ['投资收益确认表', '收益测算'],
        ['业务模式分析G1-8', '分类检查'],
        ['函证结果汇总表G0-1', '函证'],
        ['调整分录汇总表G1-12', '调整分录'],
        ['有价证券监盘表G1-11', '其他程序'],
        ['衍生金融工具核查表G1-14', '其他程序'],
      ]
      for (const [name, expectedCategory] of samples) {
        expect(classifyGSheet(name).category).toBe(expectedCategory)
      }
    })

    it('任意 sheet 名（含极端字符串）恒返回非 null 类目（fallback 兜底）', () => {
      const edgeCases = [
        '',
        ' ',
        '  ',
        'abc',
        '123',
        'NULL',
        '!@#$%^&*()',
        'A'.repeat(200),
        '中文内容',
        'mixed 中英 123',
      ]
      for (const name of edgeCases) {
        const cls = classifyGSheet(name)
        expect(cls).toBeDefined()
        expect(typeof cls.category).toBe('string')
        expect(cls.category.length).toBeGreaterThan(0)
      }
    })

    it('只有"索引"和"历史遗留"两类 defaultHidden=true，其余 11 类显示', () => {
      const hiddenCategories = G_SHEET_GROUP_RULES.filter(
        (r) => r.defaultHidden === true,
      ).map((r) => r.id)
      expect(hiddenCategories.sort()).toEqual(['historical', 'index'])
    })

    it('只有"附注披露"一类 readonly=true，其余 12 类可编辑', () => {
      const readonlyCategories = G_SHEET_GROUP_RULES.filter(
        (r) => r.readonly === true,
      ).map((r) => r.id)
      expect(readonlyCategories).toEqual(['disclosure'])
    })
  })
})
