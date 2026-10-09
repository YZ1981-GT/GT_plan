/**
 * H2-GAP-2 根治守卫：`transferOut` 载入期并进 `decrease`。
 *
 * spec: `h2-h6-h10-pilot-cross-reference-lanes`
 *
 * ═══ 为什么要这条守卫 ═══
 *
 * 「其他减少」原本同时由 `decrease` 与 `transferOut` 两个字段承载
 * （`_otherDecrease = decrease + transferOut`）。双向回写时模板只有 `O 其他减少`
 * **一格**，投影只能落一个字段 ⇒ 另一个字段的金额会静默消失在两侧差额里
 * （契约里登记为 H2-GAP-2）。
 *
 * 根治办法是载入期把 `transferOut` 一次性并进 `decrease` 并置 0，使
 * `其他减少 == decrease` 成为单一口径、模板 `O` 与 `decrease` 变 1:1。
 *
 * 本文件钉住三件事：
 *   ① **历史值不丢**：`transferOut` 非零时必须被加进 `decrease`，不是被丢弃；
 *   ② **幂等**：归并后的行再过一次归一化，`decrease` 不得二次累加；
 *   ③ **口径只有一处定义**：`_otherDecrease` 不得再累加 `transferOut`。
 *
 * ═══ 🔴 变异反证的**诚实结果**（三个变异，只杀掉一个）═══
 *
 * | 变异 | 结果 | 为什么 |
 * |---|---|---|
 * | 删 `_normalizeRow` 的 `+ _getNum(raw.transferOut)` | **RED** | 行为真变了：历史值被丢弃 |
 * | 删 `row.transferOut = 0` | GREEN | **等价变异** —— `_createEmptyRow` 已把该字段初始化为 0，且归并后再没有任何地方从 raw 读它 ⇒ 删掉这行行为不变 |
 * | `_otherDecrease` 改回 `decrease + transferOut` | GREEN | **等价变异** —— 归并后该字段恒 0，加 0 不改变结果 |
 *
 * 后两个存活**不是判据弱**，是「归并本身让它们变成无行为差异的写法」。但它们仍是
 * **意图回退**：留着会让下一个人以为「累加口径还活着」。⇒ 用两条**源码级**判据补上
 * （见文件末尾 `describe('源码级：口径与清零的意图不得回退')`），它们按文本取证，
 * 因此能杀掉这两个等价变异。
 *
 * 🔴 不要把这三行改成「行为级测试」去凑红 —— 那需要人为构造一个「字段非 0 且被读取」
 * 的状态，而根治的目标恰恰是让那个状态不可达。判据形态要跟着事实走。
 */
import fs from 'node:fs'
import path from 'node:path'
import { describe, it, expect } from 'vitest'
import { normalizeH2DetailRows } from '../useH2Detail'

/** 最小行：只给归并相关字段，其余走缺省。 */
function rawRow(over: Record<string, unknown> = {}) {
  return { rowId: 'r1', name: '厂房', cipBegin: 1000, ...over }
}

describe('H2-GAP-2 根治：transferOut 载入期并进 decrease', () => {
  it('① 历史非零 transferOut 被加进 decrease，不是被丢弃', () => {
    const [row] = normalizeH2DetailRows([rawRow({ decrease: 30, transferOut: 70 })])
    expect(row.decrease).toBe(100)
    expect(row.transferOut).toBe(0)
  })

  it('① 缺 decrease 只有 transferOut 时，金额同样保住', () => {
    const [row] = normalizeH2DetailRows([rawRow({ transferOut: 55 })])
    expect(row.decrease).toBe(55)
    expect(row.transferOut).toBe(0)
  })

  it('② 幂等：归并后的行再归一化一次，decrease 不二次累加', () => {
    const [once] = normalizeH2DetailRows([rawRow({ decrease: 30, transferOut: 70 })])
    const [twice] = normalizeH2DetailRows([{ ...once }])
    expect(twice.decrease).toBe(100)
    expect(twice.transferOut).toBe(0)
  })

  it('② 旧别名（decreaseOther / decreaseDisposal）也参与同一归并', () => {
    const [row] = normalizeH2DetailRows([rawRow({ decreaseOther: 20, transferOut: 5 })])
    expect(row.decrease).toBe(25)
    expect(row.transferOut).toBe(0)
  })

  it('③ 期末余额只吃并好的 decrease，不再额外加 transferOut', () => {
    // 期初 1000，增加 0，转固 0，其他减少 = 30 + 70 = 100 ⇒ 期末 900
    const [row] = normalizeH2DetailRows([rawRow({ decrease: 30, transferOut: 70 })])
    expect(row.cipEnd).toBe(900)
    expect(row.unadjustedEnd).toBe(900)
  })

  it('③ 归并后 transferOut 恒 0，两字段之和仍等于原总额', () => {
    const [row] = normalizeH2DetailRows([rawRow({ decrease: 30, transferOut: 70 })])
    expect(row.transferOut).toBe(0)
    expect(row.decrease + row.transferOut).toBe(100)
  })
})

/**
 * 源码级判据 —— 杀掉两个「行为等价但意图回退」的变异。
 *
 * 这两条按**文本**取证而非行为：归并已让 `transferOut` 恒 0，所以「再累加一次」与
 * 「不显式清零」都不改变任何计算结果（等价变异）。但它们会把已经收口的口径重新
 * 打开，下一个人看到 `decrease + transferOut` 会以为双口径还活着，于是在双向回写
 * 里重新引入 H2-GAP-2。
 */
describe('源码级：口径与清零的意图不得回退', () => {
  const SRC = fs.readFileSync(
    path.join(__dirname, '..', 'useH2Detail.ts'),
    'utf-8',
  )

  it('_otherDecrease 的函数体不得再出现 transferOut（口径单一真源）', () => {
    const m = SRC.match(/function _otherDecrease\([\s\S]*?\n\}/)
    expect(m, '找不到 _otherDecrease —— 形态变了，判据要跟进').not.toBeNull()
    expect(m![0]).not.toContain('transferOut')
  })

  it('_normalizeRow 必须显式把 transferOut 清零（保住归并意图的可读性）', () => {
    expect(SRC).toContain('row.transferOut = 0')
  })

  it('归并只在一处发生：全文件恰有一次 `+ _getNum(raw.transferOut)`', () => {
    const hits = SRC.match(/\+\s*_getNum\(raw\.transferOut\)/g) || []
    expect(hits).toHaveLength(1)
  })

  it('不得再从 raw 读 transferOut 赋给行（那会让清零失效）', () => {
    expect(SRC).not.toMatch(/row\.transferOut\s*=\s*_getNum\(raw\.transferOut\)/)
  })
})
