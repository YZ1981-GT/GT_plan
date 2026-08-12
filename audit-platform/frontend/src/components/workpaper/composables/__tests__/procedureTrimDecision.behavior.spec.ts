/**
 * 裁剪决策内核行为覆盖（Task 7 自己的覆盖面）。
 *
 * spec: procedure-trimming-and-delegation-intelligence — Task 7
 * 被测: `composables/procedureTrimDecision.ts`
 *
 * ## 与 `procedureTrimDecision.spec.ts` 的分工
 *
 * 那个文件是 **Task 5 的打红基线**（类 A 独立口径判据 + 类 B 结构契约 + Property
 * 1/2/3/4/5/33），其既有断言**一条都不动**。本文件只做 Task 7 的行为覆盖：
 * 9 档逐条命中、短路性、风险未知、驳回、底稿已录入、不信赖控制提示、既有保留判据
 * 行为保持，以及两条 PBT。
 *
 * ## 为什么断言 `evidence.decidedBy` 而不只断言 `verdict`
 *
 * 9 档里有 8 档的 `verdict` 都是 `keep` —— 只断言 `verdict` 无法区分「命中了正确的
 * 那一档」与「碰巧被后面某一档兜住」。`decidedBy` 是决策内核对「本次走了哪一档」的
 * 自陈，断言它才能钉死决策顺序；否则把档 1 的风险保护整段删掉，测试依然全绿
 * （风险高的科目会被档 9 默认保留兜住，verdict 仍是 keep）。
 */
import { describe, it, expect } from 'vitest'
import fc from 'fast-check'

import {
  decideTrim,
  BALANCE_DRIVEN_CYCLES,
  type TrimDecisionInput,
} from '../procedureTrimDecision'

// ══════════════════════════════════════════════════════════════════════════
// 输入构造器
//
// 形态与守卫文件的 `baseInput()` 保持一致（同一份接口的事实来源），默认走
// 「档 9 默认保留」：D 循环 / 非强制 / 待执行 / 无录入 / 未驳回 / 有数据 /
// 金额 100 万 ≥ 实际执行重要性 50 万 / 中风险 / 完整性不敏感。
// ══════════════════════════════════════════════════════════════════════════
function baseInput(over: Record<string, any> = {}): TrimDecisionInput {
  // 🔴 `procedure` / `risk` 是嵌套对象，必须在 `...over` **之后**再做深合并。
  // 若靠 `...over` 顺带覆盖，传入 `procedure: { executionStatus: 'pending' }`
  // 会把整个 procedure 换成只有一个键的对象 —— `cycle` 丢失后决策会走到
  // 「非科目余额驱动循环」档，于是「底稿已录入必须保留」这类用例会因为
  // 走错档而**假绿**（verdict 恰好也是 keep）。本轮首跑即因此暴露两条。
  const base = {
    procedure: {
      wpCode: 'D2-1',
      cycle: 'D',
      isMandatory: false,
      executionStatus: 'pending',
      hasManualReason: false,
      suggestionRejected: false,
      hasWorkpaperEntry: false,
    },
    accountAmount: 1_000_000,
    subjectDataState: 'with_data',
    cycleHasData: true,
    materiality: { performanceMateriality: 500_000, trivialThreshold: 25_000 },
    risk: {
      maxRisk: 'M',
      hasSpecial: false,
      completenessRmm: null,
      completenessSpecial: false,
      approach: 'combined',
      reliance: '是',
    },
    riskDimensionAvailable: true,
    completenessSensitiveCycle: false,
    completenessSource: 'cycle_default',
  }
  const merged: Record<string, any> = { ...base, ...over }
  merged.procedure = { ...base.procedure, ...(over.procedure ?? {}) }
  // `risk: null` 是「B50 无该科目」这一态，必须能显式传入（不是"未提供"）
  merged.risk = over.risk === null ? null : { ...base.risk, ...(over.risk ?? {}) }
  return merged as TrimDecisionInput
}

/** 取 `(verdict, reasonCode, decidedBy)` 三元组，作为「命中哪一档」的判据。 */
function triple(input: TrimDecisionInput): [string, string | null, string] {
  const d = decideTrim(input)
  return [d.verdict, d.reasonCode, d.evidence.decidedBy]
}

// ══════════════════════════════════════════════════════════════════════════
// 构造器自检（防「默认输入本就不落在档 9」导致后续用例全在测别的档）
// ══════════════════════════════════════════════════════════════════════════
describe('构造器自检', () => {
  it('默认输入落在档 9 默认保留（后续各档均由此逐项 override 触发）', () => {
    expect(triple(baseInput())).toEqual(['keep', null, 'default_keep'])
  })

  it('BALANCE_DRIVEN_CYCLES 恰为 D~N 十一个循环，且不含 A/B/C/S', () => {
    expect(Array.from(BALANCE_DRIVEN_CYCLES).slice().sort()).toEqual(
      ['D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N'].slice().sort(),
    )
    for (const c of ['A', 'B', 'C', 'S']) {
      expect(BALANCE_DRIVEN_CYCLES.has(c), `不应含 ${c}`).toBe(false)
    }
  })
})

// ══════════════════════════════════════════════════════════════════════════
// 9 档逐条命中
// ══════════════════════════════════════════════════════════════════════════
describe('9 档决策顺序逐条命中', () => {
  it('档 1 风险保护：hasSpecial ⟹ keep / risk_protection', () => {
    expect(triple(baseInput({ risk: { hasSpecial: true } }))).toEqual([
      'keep',
      null,
      'risk_protection',
    ])
  })

  it('档 1 风险保护：maxRisk=H ⟹ keep / risk_protection', () => {
    expect(triple(baseInput({ risk: { maxRisk: 'H' } }))).toEqual([
      'keep',
      null,
      'risk_protection',
    ])
  })

  it('档 2 强制保留：isMandatory', () => {
    expect(triple(baseInput({ procedure: { isMandatory: true } }))).toEqual([
      'keep',
      null,
      'mandatory',
    ])
  })

  it('档 2 强制保留：A / S 循环恒保留（既有行为）', () => {
    for (const cycle of ['A', 'S']) {
      expect(triple(baseInput({ procedure: { cycle } })), `循环 ${cycle}`).toEqual([
        'keep',
        null,
        'non_data_driven_cycle_mandatory',
      ])
    }
  })

  it('档 2 强制保留：executionStatus 已投入工作的三态', () => {
    for (const status of ['in_progress', 'completed', 'reviewed']) {
      expect(
        triple(baseInput({ procedure: { executionStatus: status } })),
        `状态 ${status}`,
      ).toEqual(['keep', null, 'execution_progress'])
    }
  })

  it('档 2 强制保留：hasManualReason', () => {
    expect(triple(baseInput({ procedure: { hasManualReason: true } }))).toEqual([
      'keep',
      null,
      'manual_reason',
    ])
  })

  it('档 2 强制保留：hasWorkpaperEntry', () => {
    expect(triple(baseInput({ procedure: { hasWorkpaperEntry: true } }))).toEqual([
      'keep',
      null,
      'workpaper_entry',
    ])
  })

  it('档 2 强制保留：suggestionRejected', () => {
    expect(triple(baseInput({ procedure: { suggestionRejected: true } }))).toEqual([
      'keep',
      null,
      'suggestion_rejected',
    ])
  })

  it('档 3 非科目余额驱动循环（B 计划 / C 控制测试）', () => {
    for (const cycle of ['B', 'C']) {
      expect(triple(baseInput({ procedure: { cycle } })), `循环 ${cycle}`).toEqual([
        'keep',
        null,
        'non_balance_driven_cycle',
      ])
    }
  })

  it('档 4 数据存在性：科目底稿级 no_data ⟹ auto_trim / no_data', () => {
    expect(triple(baseInput({ subjectDataState: 'no_data' }))).toEqual([
      'auto_trim',
      'no_data',
      'no_data',
    ])
  })

  it('档 4 数据存在性：科目级 unknown + 循环级无数据 ⟹ auto_trim / no_data', () => {
    expect(
      triple(baseInput({ subjectDataState: 'unknown', cycleHasData: false })),
    ).toEqual(['auto_trim', 'no_data', 'no_data'])
  })

  it('档 5 完整性豁免（认定级）：completenessRmm=H ⟹ keep，不进重要性判据', () => {
    // 金额远低于明显微小错报临界值，若无豁免必产 below_trivial
    const [verdict, reason, tier] = triple(
      baseInput({ accountAmount: 100, risk: { completenessRmm: 'H' } }),
    )
    expect([verdict, reason]).toEqual(['keep', null])
    expect(tier).toBe('completeness_exemption')
  })

  it('档 5 完整性豁免（认定级）：completenessSpecial ⟹ keep', () => {
    expect(
      triple(baseInput({ accountAmount: 100, risk: { completenessSpecial: true } })),
    ).toEqual(['keep', null, 'completeness_exemption'])
  })

  it('档 5 完整性豁免（循环级）：completenessSensitiveCycle=true ⟹ keep', () => {
    expect(
      triple(
        baseInput({
          procedure: { cycle: 'L' },
          accountAmount: 100,
          completenessSensitiveCycle: true,
        }),
      ),
    ).toEqual(['keep', null, 'completeness_exemption'])
  })

  it('档 6 重要性维度不可用：materiality=null ⟹ keep（不推算、不猜）', () => {
    expect(triple(baseInput({ accountAmount: 1, materiality: null }))).toEqual([
      'keep',
      null,
      'materiality_unavailable',
    ])
  })

  it('档 7 低于明显微小错报临界值 ⟹ suggest_trim / below_trivial', () => {
    expect(triple(baseInput({ accountAmount: 24_999 }))).toEqual([
      'suggest_trim',
      'below_trivial',
      'below_trivial',
    ])
  })

  it('档 8 低于实际执行重要性 ⟹ suggest_trim / below_materiality', () => {
    expect(triple(baseInput({ accountAmount: 499_999 }))).toEqual([
      'suggest_trim',
      'below_materiality',
      'below_materiality',
    ])
  })

  it('档 7/8 边界：恰好等于阈值时归下一档（< 而非 <=）', () => {
    // 恰等于 trivialThreshold ⇒ 不属档 7，落档 8
    expect(triple(baseInput({ accountAmount: 25_000 }))).toEqual([
      'suggest_trim',
      'below_materiality',
      'below_materiality',
    ])
    // 恰等于 performanceMateriality ⇒ 不属档 8，落档 9
    expect(triple(baseInput({ accountAmount: 500_000 }))).toEqual([
      'keep',
      null,
      'default_keep',
    ])
  })

  it('档 9 默认保留：金额不低于实际执行重要性', () => {
    expect(triple(baseInput({ accountAmount: 500_001 }))).toEqual([
      'keep',
      null,
      'default_keep',
    ])
  })
})

// ══════════════════════════════════════════════════════════════════════════
// 短路性：命中靠前判据时，靠后判据取值变化不改变结论
// ══════════════════════════════════════════════════════════════════════════
describe('决策顺序短路性', () => {
  /** 逐项施加 override，断言三元组恒定。 */
  function assertStable(
    label: string,
    fixed: Record<string, any>,
    variants: Record<string, any>[],
  ): void {
    const results = variants.map((v) => JSON.stringify(triple(baseInput({ ...fixed, ...v }))))
    expect(new Set(results).size, `${label} 未短路：${results.join(' | ')}`).toBe(1)
  }

  it('档 1 命中时，金额 / 重要性 / 数据存在性 / 完整性 均不改变结论', () => {
    assertStable('档 1', { risk: { maxRisk: 'H' } }, [
      {},
      { accountAmount: 0 },
      { accountAmount: null },
      { materiality: null },
      { materiality: { performanceMateriality: 1, trivialThreshold: 1 } },
      { subjectDataState: 'no_data' },
      { subjectDataState: 'unknown', cycleHasData: false },
      { completenessSensitiveCycle: true },
    ])
  })

  it('档 2 命中时，数据存在性与重要性均不改变结论', () => {
    assertStable('档 2 isMandatory', { procedure: { isMandatory: true } }, [
      {},
      { subjectDataState: 'no_data' },
      { accountAmount: 1 },
      { materiality: null },
    ])
    assertStable(
      '档 2 hasWorkpaperEntry',
      { procedure: { hasWorkpaperEntry: true } },
      [{}, { subjectDataState: 'no_data' }, { accountAmount: 1 }, { materiality: null }],
    )
  })

  it('档 4 命中时，重要性与完整性取值变化不改变结论', () => {
    assertStable('档 4', { subjectDataState: 'no_data' }, [
      {},
      { materiality: null },
      { materiality: { performanceMateriality: 1, trivialThreshold: 1 } },
      { accountAmount: 1 },
      { accountAmount: null },
      { completenessSensitiveCycle: true },
    ])
  })

  it('档 5 命中时，重要性取值变化不改变结论', () => {
    assertStable(
      '档 5',
      { procedure: { cycle: 'L' }, completenessSensitiveCycle: true, accountAmount: 100 },
      [
        {},
        { materiality: null },
        { materiality: { performanceMateriality: 1, trivialThreshold: 1 } },
        { accountAmount: 1 },
        { accountAmount: 10_000_000 },
      ],
    )
  })
})

// ══════════════════════════════════════════════════════════════════════════
// 风险未知（B50 无该科目）
// ══════════════════════════════════════════════════════════════════════════
describe('风险未知：既不保护也不因风险被裁（Property 13）', () => {
  it('risk=null 且 riskDimensionAvailable=true ⟹ 不享受档 1 保护', () => {
    // 金额低于明显微小错报临界值 ⇒ 若走档 1 会 keep，实际应产生建议
    const d = decideTrim(baseInput({ risk: null, accountAmount: 100 }))
    expect(d.evidence.decidedBy, '风险未知不应命中风险保护档').not.toBe('risk_protection')
    expect(d.verdict).toBe('suggest_trim')
    expect(d.reasonCode).toBe('below_trivial')
  })

  it('risk=null ⟹ 也不因「风险低」而被自动裁剪', () => {
    const d = decideTrim(baseInput({ risk: null }))
    expect(d.verdict, '风险未知不得导致自动裁剪').toBe('keep')
    expect(d.reasonCode).toBeNull()
  })

  it('risk=null ⟹ evidence.risk_unknown 为真，且风险等级留空不伪装成低风险', () => {
    const d = decideTrim(baseInput({ risk: null }))
    expect(d.evidence.risk_unknown, 'risk_unknown 标记缺失').toBe(true)
    expect(d.evidence.maxRisk, '未评估不得被填成具体等级').toBeNull()
    expect(d.evidence.hasSpecial).toBe(false)
    expect(d.evidence.riskDimensionAvailable).toBe(true)
  })

  it('risk 非 null ⟹ risk_unknown 为假（反向自检，防该标记恒真）', () => {
    expect(decideTrim(baseInput()).evidence.risk_unknown).toBe(false)
    expect(decideTrim(baseInput({ risk: { maxRisk: 'H' } })).evidence.risk_unknown).toBe(false)
  })

  it('风险维度整体不可用（riskDimensionAvailable=false）如实留痕', () => {
    const d = decideTrim(baseInput({ risk: null, riskDimensionAvailable: false }))
    expect(d.evidence.riskDimensionAvailable).toBe(false)
    expect(d.evidence.risk_unknown).toBe(true)
  })
})

// ══════════════════════════════════════════════════════════════════════════
// 既有保留判据行为保持（Property 32）
// ══════════════════════════════════════════════════════════════════════════
describe('既有五类保留判据行为保持（Property 32）', () => {
  const cases: { label: string; over: Record<string, any>; tier: string }[] = [
    { label: '已裁剪/已驳回建议', over: { procedure: { suggestionRejected: true } }, tier: 'suggestion_rejected' },
    { label: 'is_mandatory', over: { procedure: { isMandatory: true } }, tier: 'mandatory' },
    { label: 'A 循环', over: { procedure: { cycle: 'A' } }, tier: 'non_data_driven_cycle_mandatory' },
    { label: 'S 循环', over: { procedure: { cycle: 'S' } }, tier: 'non_data_driven_cycle_mandatory' },
    { label: '有执行进度', over: { procedure: { executionStatus: 'completed' } }, tier: 'execution_progress' },
    { label: '已手动填理由', over: { procedure: { hasManualReason: true } }, tier: 'manual_reason' },
    { label: '非 D~N 循环', over: { procedure: { cycle: 'B' } }, tier: 'non_balance_driven_cycle' },
  ]

  for (const { label, over, tier } of cases) {
    it(`${label} ⟹ 恒 keep（即便金额与数据都指向裁剪）`, () => {
      // 同时叠加「无数据 + 金额极小 + 重要性极小」三个指向裁剪的条件
      const d = decideTrim(
        baseInput({
          ...over,
          subjectDataState: 'no_data',
          accountAmount: 0,
          materiality: { performanceMateriality: 1, trivialThreshold: 1 },
        }),
      )
      expect(d.verdict, `${label} 未能保留`).toBe('keep')
      expect(d.reasonCode).toBeNull()
      expect(d.evidence.decidedBy).toBe(tier)
    })
  }

  it('「待执行 + 底稿已录入」这一组合必须保留（Property 15）', () => {
    const d = decideTrim(
      baseInput({
        procedure: { executionStatus: 'pending', hasWorkpaperEntry: true },
        subjectDataState: 'no_data',
        accountAmount: 0,
      }),
    )
    expect(d.verdict, '程序状态待执行但底稿已录入，裁剪会让已做的工作消失').toBe('keep')
    expect(d.evidence.decidedBy).toBe('workpaper_entry')
  })

  it('反向自检：仅「待执行 + 无录入 + 无数据」时确实会自动裁剪', () => {
    // 证明上一条不是恒真 —— 只有 hasWorkpaperEntry 才拦住它
    const d = decideTrim(
      baseInput({
        procedure: { executionStatus: 'pending', hasWorkpaperEntry: false },
        subjectDataState: 'no_data',
      }),
    )
    expect(d.verdict).toBe('auto_trim')
    expect(d.reasonCode).toBe('no_data')
  })
})

// ══════════════════════════════════════════════════════════════════════════
// 不信赖控制提示（Property 40）
// ══════════════════════════════════════════════════════════════════════════
describe('不信赖内部控制：保留 + 提示，不改变 verdict（Property 40）', () => {
  const NOT_RELIED = ['否', '不信赖', '不拟信赖内部控制', '不予信赖', 'no']

  for (const reliance of NOT_RELIED) {
    it(`approach=substantive 且 reliance='${reliance}' ⟹ keep 且 hints 非空`, () => {
      const d = decideTrim(baseInput({ risk: { approach: 'substantive', reliance } }))
      expect(d.verdict, '提示不得改变 verdict').toBe('keep')
      expect(d.reasonCode).toBeNull()
      expect(d.hints.length, 'hints 应含实质性程序需加强的提示').toBeGreaterThan(0)
      expect(d.hints.join('')).toContain('实质性程序')
    })
  }

  it('信赖控制类取值不发提示（是 / 部分信赖 / 信赖）', () => {
    for (const reliance of ['是', '部分信赖', '信赖']) {
      const d = decideTrim(baseInput({ risk: { approach: 'substantive', reliance } }))
      expect(d.hints, `reliance='${reliance}' 不应发提示`).toEqual([])
    }
  })

  it('「不适用 / 未评估」既非信赖也非不信赖，不发提示', () => {
    for (const reliance of ['不适用', '未评估', 'N/A', null]) {
      const d = decideTrim(baseInput({ risk: { approach: 'substantive', reliance } }))
      expect(d.hints, `reliance=${String(reliance)} 不应发提示`).toEqual([])
    }
  })

  it('approach 非实质性方案时不发提示（两条件须同时满足）', () => {
    const d = decideTrim(baseInput({ risk: { approach: 'combined', reliance: '否' } }))
    expect(d.hints).toEqual([])
  })

  it('hints 恒为数组（各档都不得返回 undefined）', () => {
    const inputs = [
      baseInput(),
      baseInput({ risk: { maxRisk: 'H' } }),
      baseInput({ procedure: { isMandatory: true } }),
      baseInput({ procedure: { cycle: 'B' } }),
      baseInput({ subjectDataState: 'no_data' }),
      baseInput({ accountAmount: 100, risk: { completenessRmm: 'H' } }),
      baseInput({ materiality: null }),
      baseInput({ accountAmount: 24_999 }),
      baseInput({ accountAmount: 499_999 }),
      baseInput({ risk: null }),
    ]
    for (const input of inputs) {
      expect(Array.isArray(decideTrim(input).hints)).toBe(true)
    }
  })
})

// ══════════════════════════════════════════════════════════════════════════
// narrative 与 evidence 的审计可追溯性
// ══════════════════════════════════════════════════════════════════════════
describe('narrative 含判据数值，evidence 记录实际口径', () => {
  it('below_trivial 的 narrative 同时含科目余额与临界值', () => {
    const d = decideTrim(baseInput({ accountAmount: 24_999 }))
    expect(d.narrative).toContain('24,999.00')
    expect(d.narrative).toContain('25,000.00')
  })

  it('below_materiality 的 narrative 同时含科目余额与实际执行重要性', () => {
    const d = decideTrim(baseInput({ accountAmount: 499_999 }))
    expect(d.narrative).toContain('499,999.00')
    expect(d.narrative).toContain('500,000.00')
  })

  it('evidence 记录所用重要性口径标识与金额', () => {
    const trivial = decideTrim(baseInput({ accountAmount: 24_999 })).evidence
    expect(trivial.materialityBasis).toBe('trivial_threshold')
    expect(trivial.materialityAmount).toBe(25_000)

    const pmCase = decideTrim(baseInput({ accountAmount: 499_999 })).evidence
    expect(pmCase.materialityBasis).toBe('performance_materiality')
    expect(pmCase.materialityAmount).toBe(500_000)
  })

  it('重要性不可用时 evidence 如实标注，不填造出来的阈值', () => {
    const e = decideTrim(baseInput({ materiality: null })).evidence
    expect(e.materialityAvailable).toBe(false)
    expect(e.materialityBasis).toBeNull()
    expect(e.materialityAmount).toBeNull()
    expect(e.performanceMateriality).toBeNull()
    expect(e.trivialThreshold).toBeNull()
  })

  it('evidence 记录科目余额、数据存在性、风险等级与完整性判据层级', () => {
    const e = decideTrim(
      baseInput({ procedure: { cycle: 'L' }, completenessSensitiveCycle: true, accountAmount: 100 }),
    ).evidence
    expect(e.wpCode).toBe('D2-1')
    expect(e.cycle).toBe('L')
    expect(e.accountAmount).toBe(100)
    expect(e.subjectDataState).toBe('with_data')
    expect(e.cycleHasData).toBe(true)
    expect(e.maxRisk).toBe('M')
    expect(e.completenessExempt).toBe(true)
    expect(e.completenessSource).toBe('cycle_default')
    expect(e.completenessUsingPlatformDefault).toBe(true)
  })

  it('认定级豁免时 completenessSource=assertion 且不标平台默认', () => {
    const e = decideTrim(baseInput({ accountAmount: 100, risk: { completenessRmm: 'H' } })).evidence
    expect(e.completenessSource).toBe('assertion')
    expect(e.completenessUsingPlatformDefault, '认定级结论不是平台默认').toBe(false)
    expect(e.completenessExempt).toBe(true)
  })

  it('accountAmount=null 时 narrative 如实说明未在试算表出现，不显示 0 元', () => {
    const d = decideTrim(baseInput({ accountAmount: null }))
    expect(d.narrative).toContain('未在试算平衡表中出现')
    expect(d.evidence.accountAmount).toBeNull()
  })
})

// ══════════════════════════════════════════════════════════════════════════
// accountAmount === null 不得参与数值比较
// ══════════════════════════════════════════════════════════════════════════
describe('accountAmount=null 不参与档 7/8 数值比较', () => {
  it('null 且科目有数据时不产生重要性类建议（Math.abs(null)===0 的陷阱）', () => {
    const d = decideTrim(baseInput({ accountAmount: null }))
    expect(d.verdict, 'null 被当 0 比较会误判成低于阈值').toBe('keep')
    expect(d.reasonCode).toBeNull()
    expect(d.evidence.decidedBy).toBe('default_keep')
  })

  it('null 且科目无数据时由档 4 处理', () => {
    expect(triple(baseInput({ accountAmount: null, subjectDataState: 'no_data' }))).toEqual([
      'auto_trim',
      'no_data',
      'no_data',
    ])
  })

  it('金额确为 0（科目存在且余额为零）仍走重要性判据 —— 与 null 语义不同', () => {
    const d = decideTrim(baseInput({ accountAmount: 0 }))
    expect(d.verdict).toBe('suggest_trim')
    expect(d.reasonCode).toBe('below_trivial')
  })
})

// ══════════════════════════════════════════════════════════════════════════
// PBT（numRuns: 20）
// ══════════════════════════════════════════════════════════════════════════
describe('PBT: 决策不变式', () => {
  const amountArb = fc.oneof(
    fc.constant(null),
    fc.integer({ min: -10_000_000, max: 10_000_000 }),
  )

  it('①特别风险 / 高风险恒 keep，且不产生任何 reasonCode', () => {
    fc.assert(
      fc.property(
        fc.record({
          hasSpecial: fc.boolean(),
          highRisk: fc.boolean(),
          amount: amountArb,
          dataState: fc.constantFrom('with_data', 'no_data', 'unknown'),
          cycleHasData: fc.boolean(),
          cycle: fc.constantFrom('D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N'),
          hasMateriality: fc.boolean(),
          sensitive: fc.boolean(),
        }),
        (g) => {
          // 至少有一项风险保护成立
          const risk = {
            maxRisk: g.highRisk ? 'H' : 'L',
            hasSpecial: g.hasSpecial || !g.highRisk,
          }
          const d = decideTrim(
            baseInput({
              procedure: { cycle: g.cycle },
              risk,
              accountAmount: g.amount,
              subjectDataState: g.dataState,
              cycleHasData: g.cycleHasData,
              completenessSensitiveCycle: g.sensitive,
              materiality: g.hasMateriality
                ? { performanceMateriality: 500_000, trivialThreshold: 25_000 }
                : null,
            }),
          )
          expect(d.verdict).toBe('keep')
          expect(d.reasonCode).toBeNull()
          expect(d.evidence.decidedBy).toBe('risk_protection')
        },
      ),
      { numRuns: 20 },
    )
  })

  it('②重要性类理由码恒为 suggest_trim（永不自动裁）', () => {
    fc.assert(
      fc.property(
        fc.record({
          amount: fc.integer({ min: -10_000_000, max: 10_000_000 }),
          performanceMateriality: fc.integer({ min: 2, max: 5_000_000 }),
          trivialRatio: fc.integer({ min: 1, max: 99 }),
          cycle: fc.constantFrom('D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N'),
          maxRisk: fc.constantFrom('M', 'L'),
        }),
        (g) => {
          const trivialThreshold = Math.max(
            1,
            Math.floor((g.performanceMateriality * g.trivialRatio) / 100),
          )
          const d = decideTrim(
            baseInput({
              procedure: { cycle: g.cycle },
              risk: { maxRisk: g.maxRisk, hasSpecial: false },
              accountAmount: g.amount,
              materiality: {
                performanceMateriality: g.performanceMateriality,
                trivialThreshold,
              },
            }),
          )
          if (d.reasonCode === 'below_trivial' || d.reasonCode === 'below_materiality') {
            expect(d.verdict, '重要性类判据只允许产生建议').toBe('suggest_trim')
          }
          // 反向：auto_trim 只允许 no_data 一种成因
          if (d.verdict === 'auto_trim') {
            expect(d.reasonCode).toBe('no_data')
          }
          // 结构恒定
          expect(Array.isArray(d.hints)).toBe(true)
          expect(d.narrative.length).toBeGreaterThan(0)
          expect(d.verdict === 'keep' ? d.reasonCode === null : d.reasonCode !== null).toBe(true)
        },
      ),
      { numRuns: 20 },
    )
  })
})
