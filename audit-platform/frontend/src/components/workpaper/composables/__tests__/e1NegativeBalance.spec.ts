/**
 * e1NegativeBalance.spec.ts — Property 27 守卫：负余额如实显示，不取绝对值。
 *
 * **Validates: Requirements 8.5**
 *
 * 🔴 本 Property 的判据分两层：
 *
 * 1. **纯函数层**：负值原样返回（不经 `abs()`），容差内的 −0.001 不算负；
 * 2. **源码层**：E1 金额**取值路径**不得出现 `Math.abs()`。
 *    这一层的难点是「容差/差异判定用 abs 是合法的」—— 全 E1 目录实测 42 处 `Math.abs`
 *    全部是 `Math.abs(diff) > TOLERANCE` 这类判定，不能一刀切禁掉。
 *    故判据收窄为：**被 abs 包裹的表达式不得是金额取值**（`closing`/`ending`/
 *    `accountSum`/`leafSum`/`endingAudited` 等余额字段），而 `diff`/`rate`/
 *    `overShort`/`residual` 这类差异量允许。
 *
 * spec: .kiro/specs/e-cycle-extraction-formula-and-disclosure-completion/ (Task 17)
 */
import { readFileSync, existsSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, it, expect } from 'vitest'

import {
  NEGATIVE_TOLERANCE,
  isNegativeAmount,
  pickNegativeAccounts,
  pickNegativeSlots,
  negativeBalanceHint,
} from '../e1NegativeBalance'

const WP_ROOT = resolve(__dirname, '../..')

// ─── 纯函数层 ────────────────────────────────────────────────────────────────

describe('Property 27（纯函数）：负值如实保留', () => {
  it('实测样本 a7fc75e5 的负余额原样返回，不取绝对值', () => {
    const v = -297771168.89
    expect(isNegativeAmount(v)).toBe(true)
    const rows = pickNegativeAccounts(
      [{ accountCode: '1002', accountNo: '123', closing: v }],
      [],
    )
    expect(rows).toHaveLength(1)
    // 🔴 决定性断言：返回的是负值本身，不是 |v|
    expect(rows[0].closing).toBe(v)
    expect(rows[0].closing).toBeLessThan(0)
    expect(rows[0].closing).not.toBe(Math.abs(v))
  })

  it('容差内的微小负值不算负（防浮点噪声触发告警）', () => {
    expect(isNegativeAmount(-0.001)).toBe(false)
    expect(isNegativeAmount(-NEGATIVE_TOLERANCE)).toBe(false)
    expect(isNegativeAmount(-0.01)).toBe(true)
    expect(NEGATIVE_TOLERANCE).toBeGreaterThan(0)
  })

  it('正值与零不算负', () => {
    for (const v of [0, 0.005, 1, 1e9]) expect(isNegativeAmount(v)).toBe(false)
  })

  it('非数值输入不抛且不算负', () => {
    for (const v of [undefined, null, '', 'abc', NaN]) {
      expect(isNegativeAmount(v)).toBe(false)
    }
  })

  it('unassigned 账户也纳入负余额检查（它同样进 E1-10 完整性核对）', () => {
    const rows = pickNegativeAccounts(
      [{ accountCode: '1002', accountNo: 'A', closing: 100 }],
      [{ accountCode: '1012', accountNo: 'B', closing: -50 }],
    )
    expect(rows.map(r => r.label)).toEqual(['B'])
  })

  it('账号缺失时退回科目码作标签（不产出空标签）', () => {
    const rows = pickNegativeAccounts([{ accountCode: '1002.01', closing: -1 }], [])
    expect(rows[0].label).toBe('1002.01')
  })

  it('槽判定：账户级或叶子任一为负即命中，两侧金额各自保留', () => {
    const slots = pickNegativeSlots([
      { slot: 'bank', label: '银行存款', accountSum: -297771168.89, leafSum: -297771168.89 },
      { slot: 'other', label: '其他货币资金', accountSum: 100, leafSum: 100 },
      { slot: 'finance_co', label: '存放财务公司款项', accountSum: 5, leafSum: -3 },
    ])
    expect(slots.map(s => s.slot)).toEqual(['bank', 'finance_co'])
    expect(slots[0].accountSum).toBe(-297771168.89)
    expect(slots[1].leafSum).toBe(-3)
  })

  it('提示文案中性归因（不指控数据错误）', () => {
    const hint = negativeBalanceHint()
    expect(hint).toContain('贷方性质')
    expect(hint).toContain('资金池')
    expect(hint).toContain('重分类')
    // 不得把负余额说成错误/异常数据
    expect(hint).not.toMatch(/取数错误|数据错误|取数有误/)
  })
})

// ─── 源码层：金额取值路径不得 abs ─────────────────────────────────────────────

/** 余额类字段（被 abs 包裹即违规）。 */
const BALANCE_TOKENS = [
  'closing',
  'accountSum',
  'leafSum',
  'endingAudited',
  'openingAudited',
  'account_sum',
  'leaf_sum',
]

/** 差异/比率类（被 abs 包裹是合法的容差判定）。 */
const DIFF_TOKENS = ['diff', 'rate', 'overShort', 'residual', 'Residual', 'amount']

function stripComments(src: string): string {
  return src
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:])\/\/[^\n]*/g, '$1')
}

/** 抽出所有 `Math.abs(...)` 的实参文本（圆括号配对，跳过字符串）。 */
function absArgs(src: string): string[] {
  const out: string[] = []
  const needle = 'Math.abs('
  let i = src.indexOf(needle)
  while (i >= 0) {
    let depth = 0
    let j = i + needle.length - 1
    let quote: string | null = null
    for (; j < src.length; j++) {
      const ch = src[j]
      if (quote) {
        if (ch === quote && src[j - 1] !== '\\') quote = null
        continue
      }
      if (ch === '"' || ch === "'" || ch === '`') {
        quote = ch
        continue
      }
      if (ch === '(') depth++
      else if (ch === ')') {
        depth--
        if (depth === 0) break
      }
    }
    out.push(src.slice(i + needle.length, j))
    i = src.indexOf(needle, j)
  }
  return out
}

const E1_FILES = [
  'e1/E1FourTableSourcePanel.vue',
  'e1/E1TabDisclosure.vue',
  'composables/e1NegativeBalance.ts',
  'composables/e1BankAccountPrefill.ts',
  'composables/e1DisclosureScope.ts',
  'composables/e1RestrictedScope.ts',
].filter(f => existsSync(resolve(WP_ROOT, f)))

describe('Property 27（源码）：金额取值路径不得取绝对值', () => {
  it('被守卫文件清单非空（反向自检：路径没写错）', () => {
    expect(E1_FILES.length).toBeGreaterThan(0)
  })

  it.each(E1_FILES)('%s 的 Math.abs 实参不含余额字段', (rel) => {
    const src = stripComments(readFileSync(resolve(WP_ROOT, rel), 'utf-8'))
    const bad = absArgs(src).filter(arg =>
      BALANCE_TOKENS.some(t => arg.includes(t)) && !DIFF_TOKENS.some(t => arg.includes(t)),
    )
    expect(bad).toEqual([])
  })

  it('抽取器自检：能正确取出实参并区分余额 vs 差异', () => {
    const good = 'if (Math.abs(row.diff) > 0.005) {}'
    const bad = 'const v = Math.abs(row.closing)'
    expect(absArgs(good)).toEqual(['row.diff'])
    expect(absArgs(bad)).toEqual(['row.closing'])
    // 反向自检：判据对 bad 必判违规、对 good 必放行
    const judge = (s: string) =>
      absArgs(s).filter(a =>
        BALANCE_TOKENS.some(t => a.includes(t)) && !DIFF_TOKENS.some(t => a.includes(t)),
      )
    expect(judge(bad)).toEqual(['row.closing'])
    expect(judge(good)).toEqual([])
  })

  it('抽取器能处理嵌套括号（否则会截断实参导致漏判）', () => {
    expect(absArgs('Math.abs(parseNum(row.closing) - 1)')).toEqual([
      'parseNum(row.closing) - 1',
    ])
  })

  it('纯函数真源自身不含 Math.abs（负值必须原样流出）', () => {
    const src = stripComments(
      readFileSync(resolve(WP_ROOT, 'composables/e1NegativeBalance.ts'), 'utf-8'),
    )
    expect(src).not.toContain('Math.abs')
  })
})

// ─── 接线：面板必须真的用了这份真源 ───────────────────────────────────────────

describe('接线（防真源写好却零消费方）', () => {
  const PANEL = resolve(WP_ROOT, 'e1/E1FourTableSourcePanel.vue')

  it('溯源面板 import 并调用了纯函数真源', () => {
    const src = stripComments(readFileSync(PANEL, 'utf-8'))
    expect(src).toContain('e1NegativeBalance')
    expect(src).toMatch(/pickNegativeSlots\s*\(/)
    expect(src).toMatch(/pickNegativeAccounts\s*\(/)
  })

  it('面板渲染了负余额提示块且文案取自真源', () => {
    const src = readFileSync(PANEL, 'utf-8')
    expect(src).toMatch(/negativeAccounts\.length\s*\|\|\s*negativeSlots\.length/)
    expect(src).toContain('negativeBalanceHint')
    // 不得在模板里抄一份提示文案（双真源）
    const tpl = src.slice(src.indexOf('<template>'))
    expect(tpl).not.toContain('资金池归集户、内部结算户或透支额度')
  })
})
