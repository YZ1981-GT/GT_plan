/**
 * adjudicationPrefillPlan「四表余额为 0 不写入」守卫（平台级共享件）。
 *
 * ## 缺陷来源（浏览器实测，非推演）
 *
 * I1-1 无形资产审定表 / 项目「重庆医药集团宜宾医药有限公司新健康大药房临港店_2025」(soe)：
 * 点「从四表库带入未审数」→ toast 报「补填 18 格」，但表内 210 个 input **全为空/0**。
 *
 * 抓 `GET /api/workpapers/{I1-1}/render-config` 实证根因：
 * `html_data.adjudication_prefill` 如实下发 3 段（账面原值/累计摊销/减值准备）× 6 类别 = 18 行，
 * 每行 `opening/closing/increase/decrease` **全为 0**（该项目 `tb_balance` 无 17xx 余额）。
 *
 * 对照组「和平药房_2024」同一 I1 底稿：`cost` 3 行期末合计 5,445,065.12、
 * `amortization` 3 行合计 2,870,275.43，I4 leaf 模式合计 6,382,978.23 —— 全非零。
 * ⇒ **后端取数正确，缺陷只在本模块的写入判定**。
 *
 * ## 为什么写 0 是缺陷而不是无害
 *
 * `adjudicationPrefillPlan` 模块头第 3 条早已立下口径「本项目无此科目 ≠ 该科目为 0，不写 0」
 * （E1「存放财务公司款项」实证：写 0 会把「不适用」伪装成「已核实为零」）。
 * 但该口径旧实现只堵了入口 A（槽未命中 → `absentSlots`），漏了入口 B（槽命中但金额为 0）。
 * 后果三条：
 *   1. 审计师看到「补填 18 格」以为已带入真实数据，实际把「无余额」记成了「已核实为零」；
 *   2. 白写 18 格会刷新 `updated_at`、触发附注同步链路；
 *   3. UI 上写 0 与留空都渲染「-」（`fmtAmount` 平台口径），视觉零差异 ⇒ 缺陷不可见。
 *
 * spec: .kiro/specs/i-cycle-extraction-formula-and-disclosure-closure/ Task 24（补测 2/5）
 */
import { describe, expect, it } from 'vitest'

import {
  describeAdjPrefillPlan,
  planAdjudicationPrefill,
  planHasWork,
  resolveAdjPrefillWrites,
  type AdjPrefillCell,
} from '../shared/adjudicationPrefillPlan'

function cell(rowKey: string, amount: number, label = rowKey): AdjPrefillCell {
  return { rowKey, field: 'closingUnadjusted', amount, label, periodLabel: '期末未审' }
}

describe('入口 B：四表金额为 0 且当前格为空 → zeroSkipped，不写 0', () => {
  it('全 0 载荷不产生任何写入，planHasWork 为 false', () => {
    const cells = [cell('a', 0), cell('b', 0), cell('c', 0)]
    const plan = planAdjudicationPrefill(cells, () => null)

    expect(plan.writes).toHaveLength(0)
    expect(plan.conflicts).toHaveLength(0)
    expect(plan.zeroSkipped).toHaveLength(3)
    expect(planHasWork(plan)).toBe(false)
    expect(resolveAdjPrefillWrites(plan)).toEqual([])
    // overwrite 模式同样不该把 0 塞进去（zeroSkipped 不参与任何写入路径）
    expect(resolveAdjPrefillWrites(plan, 'overwrite')).toEqual([])
  })

  it('零与非零混合时只写非零格', () => {
    const cells = [cell('a', 0), cell('b', 1234.56), cell('c', 0)]
    const plan = planAdjudicationPrefill(cells, () => null)

    expect(plan.writes.map((w) => w.rowKey)).toEqual(['b'])
    expect(plan.zeroSkipped.map((w) => w.rowKey)).toEqual(['a', 'c'])
    expect(planHasWork(plan)).toBe(true)
  })

  it('容差内的极小值按 0 处理（不把 0.001 当真实余额写进去）', () => {
    const plan = planAdjudicationPrefill([cell('a', 0.001), cell('b', -0.002)], () => null)
    expect(plan.writes).toHaveLength(0)
    expect(plan.zeroSkipped).toHaveLength(2)
  })

  it('负数余额（备抵类）不被误当 0 跳过', () => {
    const plan = planAdjudicationPrefill([cell('a', -500000)], () => null)
    expect(plan.writes.map((w) => w.rowKey)).toEqual(['a'])
    expect(plan.zeroSkipped).toHaveLength(0)
  })
})

describe('入口 B 不得侵蚀既有三条口径', () => {
  it('四表 0 但当前已有非零录入 → 仍进 conflicts（审计师须知四表口径为 0）', () => {
    const plan = planAdjudicationPrefill([cell('a', 0)], () => 999)
    expect(plan.conflicts).toHaveLength(1)
    expect(plan.conflicts[0].current).toBe(999)
    expect(plan.zeroSkipped).toHaveLength(0)
  })

  it('四表 0 且当前也是 0（调用方 readCell 如实返回 0）→ identical 幂等跳过', () => {
    const plan = planAdjudicationPrefill([cell('a', 0)], () => 0)
    expect(plan.identical).toBe(1)
    expect(plan.writes).toHaveLength(0)
    expect(plan.zeroSkipped).toHaveLength(0)
  })

  it('非数值既有内容仍优先保护进 conflicts，不因四表为 0 而被跳过', () => {
    const plan = planAdjudicationPrefill([cell('a', 0)], () => '待确认')
    expect(plan.conflicts).toHaveLength(1)
    expect(plan.zeroSkipped).toHaveLength(0)
  })

  it('非零金额 + 当前空 → 照旧进 writes（回归保护）', () => {
    const plan = planAdjudicationPrefill([cell('a', 100), cell('b', 200)], () => null)
    expect(plan.writes).toHaveLength(2)
    expect(plan.zeroSkipped).toHaveLength(0)
  })
})

describe('提示文案如实说明「未写入」', () => {
  it('全 0 时不得出现「补填」，须点明未写入与手工兜底路径', () => {
    const plan = planAdjudicationPrefill([cell('a', 0), cell('b', 0)], () => null)
    const text = describeAdjPrefillPlan(plan)

    expect(text).not.toContain('补填')
    expect(text).toContain('2 格四表余额为 0')
    expect(text).toContain('未写入')
    expect(text).toContain('手工填 0')
    // 不能谎称「一致」（四表确实下发了行，只是余额为 0）
    expect(text).not.toContain('无需带入')
  })

  it('混合场景里补填数只算真实写入格', () => {
    const cells = [cell('a', 0), cell('b', 500), cell('c', 0), cell('d', 600)]
    const text = describeAdjPrefillPlan(planAdjudicationPrefill(cells, () => null))
    expect(text).toContain('补填 2 格')
    expect(text).toContain('2 格四表余额为 0')
  })

  it('文案全中文，无英文键名泄漏', () => {
    const plan = planAdjudicationPrefill([cell('a', 0)], () => null)
    expect(describeAdjPrefillPlan(plan)).not.toMatch(/[A-Za-z]{4,}/)
  })
})

describe('实测真实形态回归：I1-1 宜宾临港店 3 段 × 6 类别全 0', () => {
  // 形态取自 GET /api/workpapers/8efd3f64-.../render-config 的
  // html_data.adjudication_prefill（mode=category，18 行全零）
  const I1_CATEGORIES = [
    'land_use_right', 'patent', 'patent_franchise',
    'software', 'trademark', 'other',
  ]
  const I1_SEGMENTS: Array<[string, string]> = [
    ['cost', '账面原值'],
    ['amortization', '累计摊销'],
    ['impairment', '减值准备'],
  ]

  const allZeroCells: AdjPrefillCell[] = I1_SEGMENTS.flatMap(([seg, segLabel]) =>
    I1_CATEGORIES.map((key) => ({
      rowKey: key,
      field: 'closingUnadjusted',
      amount: 0,
      label: key,
      periodLabel: `${segLabel}·期末未审`,
      sourceCodes: [`1701.${seg}`],
    })),
  )

  it('18 格全 0 → 0 写入（旧实现在此报「补填 18 格」）', () => {
    expect(allZeroCells).toHaveLength(18)
    const plan = planAdjudicationPrefill(allZeroCells, () => null)

    expect(plan.writes).toHaveLength(0)
    expect(plan.zeroSkipped).toHaveLength(18)
    expect(planHasWork(plan)).toBe(false)
    expect(describeAdjPrefillPlan(plan)).toContain('18 格四表余额为 0')
  })

  it('同一底稿在有余额项目（和平药房形态）下照常带入', () => {
    // cost 3 行 5,445,065.12 / amortization 3 行 2,870,275.43（实测值）
    const heping: AdjPrefillCell[] = [
      { ...cell('land_use_right', 4200000), periodLabel: '账面原值·期末未审' },
      { ...cell('software', 1000000), periodLabel: '账面原值·期末未审' },
      { ...cell('other', 245065.12), periodLabel: '账面原值·期末未审' },
    ]
    const plan = planAdjudicationPrefill(heping, () => null)
    expect(plan.writes).toHaveLength(3)
    expect(plan.zeroSkipped).toHaveLength(0)
    expect(describeAdjPrefillPlan(plan)).toContain('补填 3 格')
  })
})
