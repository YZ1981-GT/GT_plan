/**
 * amountColumnSemantics 守卫 — 列类型判定单一真源自测
 *
 * Spec: `.kiro/specs/amount-input-migration-and-column-typing/` Task 1
 * 覆盖 Property 1（19 类关键词）/ 2（歧义不静默二选一）/ 3（override evidence 非空）
 * / 19（边界声明存在）。
 */
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'
import { describe, it, expect } from 'vitest'
import {
  NON_AMOUNT_LABEL_PATTERNS,
  AMOUNT_LABEL_PATTERNS,
  EXPLICIT_OVERRIDES,
  matchesNonAmount,
  matchesAmount,
  nonAmountCategoryOf,
  classifyColumnLabelRaw,
  classifyColumnLabel,
  overrideKey,
  GLOBAL_LABEL_OVERRIDES,
} from '../amountColumnSemantics'

/** R1.2 明确列举的 19 类非金额语义关键词（代表词）。 */
const R1_2_KEYWORDS = [
  '比率', '利率', '汇率', '占比', '比例',
  '年限', '期限', '月份', '月数', '天数',
  '笔数', '数量', '股数', '份数', '年度',
  '折现率', '增长率', '毛利率', '税率',
] as const

describe('Property 1: 非金额语义关键词全覆盖（R1.2）', () => {
  it('R1.2 列举的 19 类关键词全部判为非金额', () => {
    for (const kw of R1_2_KEYWORDS) {
      expect(matchesNonAmount(kw), `关键词「${kw}」应命中非金额模式`).toBe(true)
      expect(classifyColumnLabelRaw(kw), `关键词「${kw}」应分类为 non_amount`).toBe('non_amount')
    }
  })

  it('至少声明 19 类非金额模式', () => {
    expect(NON_AMOUNT_LABEL_PATTERNS.length).toBeGreaterThanOrEqual(19)
  })

  it('每类的 sample 都能被自身 pattern 命中（自洽）', () => {
    for (const c of NON_AMOUNT_LABEL_PATTERNS) {
      expect(c.pattern.test(c.sample), `类别「${c.category}」的 sample「${c.sample}」应被自身 pattern 命中`).toBe(true)
      expect(c.category.length).toBeGreaterThan(0)
    }
  })

  it('真实非金额列 label 判为非金额', () => {
    expect(classifyColumnLabelRaw('使用期限(年)')).toBe('non_amount')
    expect(classifyColumnLabelRaw('本期利息资本化率%')).not.toBe('amount') // 含率不应判金额
    expect(classifyColumnLabelRaw('持股比例')).toBe('non_amount')
    expect(classifyColumnLabelRaw('剩余年限')).toBe('non_amount')
  })
})

describe('金额语义模式', () => {
  it('明确金额 label 判为金额', () => {
    for (const label of [
      '原值', '残值', '期末余额', '账面价值', '减值准备', '本期发生额', '摊销金额',
      // 通用审计金额列（label 不含「金额」但均为金额）—— 锁住这些词，
      // 防 probe 解析漏抽（曾因注释里的 `/` 污染 findall 而漏抽，classify 误判非金额）
      '期末数', '期初数', '本期增加', '本期减少', '账项调整', '坏账准备', '期初原币',
    ]) {
      expect(matchesAmount(label), `「${label}」应命中金额模式`).toBe(true)
      expect(classifyColumnLabelRaw(label), `「${label}」应分类为 amount`).toBe('amount')
    }
  })

  it('金额模式非空', () => {
    expect(AMOUNT_LABEL_PATTERNS.length).toBeGreaterThan(0)
  })
})

describe('Property 2: 歧义 label 不静默二选一（R1.3）', () => {
  // 同时命中金额词与非金额词的 label 必须返回 ambiguous，不得偏向任一
  const ambiguousSamples = ['摊销期限', '折旧年限', '减值比例']
  it.each(ambiguousSamples)('「%s」同时命中两类 → ambiguous', (label) => {
    expect(matchesAmount(label), `「${label}」应命中金额词`).toBe(true)
    expect(matchesNonAmount(label), `「${label}」应命中非金额词`).toBe(true)
    expect(classifyColumnLabelRaw(label)).toBe('ambiguous')
  })
})

describe('Property 3: EXPLICIT_OVERRIDES 每条带非空 evidence（R1.4）', () => {
  const entries = Object.entries(EXPLICIT_OVERRIDES)

  it('override 清单非空（扫描面非空自检）', () => {
    expect(entries.length).toBeGreaterThan(0)
  })

  it.each(entries)('%s 的 evidence 非空且 classification 合法', (_key, entry) => {
    expect(entry.evidence.trim().length).toBeGreaterThan(10)
    expect(['amount', 'non_amount']).toContain(entry.classification)
  })

  it('override 键形如 {file}::{label}', () => {
    for (const key of Object.keys(EXPLICIT_OVERRIDES)) {
      expect(key).toMatch(/^.+\.vue::.+$/)
    }
  })

  it('override 真正改变判定：摊销期限(月) raw=ambiguous，override 后=non_amount', () => {
    const file = 'i1/amortization/I1TabAmortizationNoImpair.vue'
    const label = '摊销期限(月)'
    expect(classifyColumnLabelRaw(label)).toBe('ambiguous')
    expect(classifyColumnLabel(label, file)).toBe('non_amount')
    // 无 file 时不应用 override，仍是 raw 结果
    expect(classifyColumnLabel(label)).toBe('ambiguous')
    expect(overrideKey(file, label)).toBe(`${file}::${label}`)
  })
})

describe('classifyColumnLabel — I1-10 定向（相对 Task18 的能力增量）', () => {
  const file = 'i1/amortization/I1TabAmortizationNoImpair.vue'

  it('I1-10 可编辑金额列判为金额', () => {
    for (const label of ['原值', '累计摊销期初', '账面累计摊销期末', '账面本期摊销', '残值']) {
      expect(classifyColumnLabel(label, file), `「${label}」应为金额列`).toBe('amount')
    }
  })

  it('I1-10「使用期限(年)」判为非金额（反向边界锚点）', () => {
    expect(classifyColumnLabel('使用期限(年)', file)).toBe('non_amount')
  })
})

describe('Property 11: nonAmountCategoryOf 返回命中类别（反向失败消息用）', () => {
  it('命中列返回类别名', () => {
    expect(nonAmountCategoryOf('使用期限(年)')).toBe('期限')
    expect(nonAmountCategoryOf('本期利率')).toBe('利率')
    expect(nonAmountCategoryOf('持股比例')).toBe('比例')
  })

  it('金额列返回 null', () => {
    expect(nonAmountCategoryOf('原值')).toBeNull()
    expect(nonAmountCategoryOf('期末余额')).toBeNull()
  })
})

describe('Property 19 / R1.5: 模块 doc 显式声明只读展示边界', () => {
  const here = dirname(fileURLToPath(import.meta.url))
  const moduleSrc = readFileSync(resolve(here, '../amountColumnSemantics.ts'), 'utf-8')

  it('doc 声明只读展示归 displayPrefs.fmtAmount() 口径', () => {
    expect(moduleSrc).toContain('只读展示')
    expect(moduleSrc).toContain('fmtAmount')
  })

  it('doc 声明本模块只服务可编辑控件、运行时不消费', () => {
    expect(moduleSrc).toContain('可编辑控件')
    expect(moduleSrc).toContain('运行时')
  })
})

describe('GLOBAL_LABEL_OVERRIDES 全局歧义裁决（Task9 收敛 label_hit_both）', () => {
  const entries = Object.entries(GLOBAL_LABEL_OVERRIDES)

  it('非空且每条 evidence 非空、classification 合法', () => {
    expect(entries.length).toBeGreaterThan(0)
    for (const [label, e] of entries) {
      expect(e.evidence.trim().length, `${label} evidence 非空`).toBeGreaterThan(5)
      expect(['amount', 'non_amount']).toContain(e.classification)
    }
  })

  it('数量/比例/年限/期限类裁决为 non_amount', () => {
    for (const l of ['账面数量', '计提比例', '计提比例(%)', '审定数量', '未审数量', '折旧年限', '剩余摊销期限(月)']) {
      expect(classifyColumnLabel(l), `「${l}」应裁决为非金额`).toBe('non_amount')
    }
  })

  it('建议3：「年度」收窄后本/上年度前缀直接判 amount（raw，无需 override）', () => {
    // 收窄「年度」pattern（lookbehind 排除本/上前缀）后，这些不再是假歧义，
    // raw 判定直接为 amount，故已从 GLOBAL_LABEL_OVERRIDES 移除。
    for (const l of ['本年度审定数', '上年度审定数', '本年度销售金额', '本年度审定数（C列）', '上年度追溯调整后审定数（D列）']) {
      expect(classifyColumnLabelRaw(l), `「${l}」raw 应直接为金额`).toBe('amount')
    }
    // 独立「年度」/「会计年度」/「决算年度」（前缀非本/上）仍命中非金额（R1.2 不变）
    expect(matchesNonAmount('年度')).toBe(true)
    expect(matchesNonAmount('会计年度')).toBe(true)
    expect(matchesNonAmount('决算年度')).toBe(true)
  })

  it('这些 label 的 raw 判定确是 ambiguous（证明全局 override 针对的是真歧义）', () => {
    for (const l of ['账面数量', '减值比例', '折旧年限', '计提比例']) {
      expect(classifyColumnLabelRaw(l), `「${l}」raw 应为 ambiguous`).toBe('ambiguous')
    }
  })
})
