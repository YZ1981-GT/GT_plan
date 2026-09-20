/**
 * D4-17/18/19/20 截止/折扣/退货 前端接线守卫（vitest）
 *
 * spec: d4-cutoff-return-writeback-formula-io
 * 锁定：
 *  - D4-17/18 跨期判定走 useD4FormulaEngine（isCrossPeriodForward/Backward），不再内联日期比较
 *  - 四表 A13 推送必须人工 @click 触发（不在 watch/debounce/onMounted 自动回调体内）
 *  - 推送候选按人工判定过滤（isCutoff===false / isAbnormal==='是' / 人工 prompt 金额），
 *    reason/否 非空不构成异常
 *  - useD4InspectionWriteback wpCode 字面量正确（防接错底稿）
 */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const _dir = dirname(fileURLToPath(import.meta.url))
function readComp(rel: string): string {
  return readFileSync(resolve(_dir, '../d4/inspection', rel), 'utf-8')
}
function stripComments(src: string): string {
  return src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/.*$/gm, '$1')
}

const CASES = [
  { file: 'D4TabCutoffForward.vue', sheet: 'D4-17' },
  { file: 'D4TabCutoffBackward.vue', sheet: 'D4-18' },
  { file: 'D4TabDiscount.vue', sheet: 'D4-19' },
  { file: 'D4TabReturn.vue', sheet: 'D4-20' },
]

describe('D4-17~20 接 useD4InspectionWriteback（wpCode 字面量正确）', () => {
  for (const c of CASES) {
    it(`${c.file}: useD4InspectionWriteback wpCode = ${c.sheet}`, () => {
      const src = stripComments(readComp(c.file))
      expect(src).toMatch(new RegExp(`useD4InspectionWriteback\\([\\s\\S]*?wpCode:\\s*'${c.sheet}'`))
    })
  }
})

describe('D4-17~20 A13 推送必须人工触发（不在自动回调体内）', () => {
  for (const c of CASES) {
    it(`${c.file}: pushToA13/handlePushToA13 不在 watch/debounce/onMounted 回调窗口内`, () => {
      const src = stripComments(readComp(c.file))
      // 模板 @click 人工触发
      expect(src).toMatch(/@click="handlePushToA13"/)
      const autoTriggers = /\b(watch|watchEffect|onMounted|setTimeout|setInterval|debounceSave|debounceTimer)\b/g
      let m: RegExpExecArray | null
      while ((m = autoTriggers.exec(src)) !== null) {
        const win = src.slice(m.index, m.index + 600)
        expect(/\bpushToA13\s*\(/.test(win), `${c.file}: pushToA13 疑在 ${m[1]} 自动回调体内`).toBe(false)
        expect(/\bhandlePushToA13\s*\(/.test(win), `${c.file}: handlePushToA13 疑在 ${m[1]} 自动回调体内`).toBe(false)
      }
    })
  }
})

describe('D4-17/18 跨期判定走公式引擎单一真源（不内联日期比较）', () => {
  it('D4-17 用 isCrossPeriodForward，checkCutoff 不再内联 voucherDate<=cutoff', () => {
    const src = stripComments(readComp('D4TabCutoffForward.vue'))
    expect(src).toContain('isCrossPeriodForward')
    expect(src).toMatch(/import\s*\{[^}]*isCrossPeriodForward[^}]*\}\s*from\s*'[^']*useD4FormulaEngine'/)
    // checkCutoff 里不再出现内联的 `voucherDate <= cutoffDate` 手写比较
    const m = src.match(/function checkCutoff[\s\S]*?\n\}/)
    expect(m).toBeTruthy()
    expect(m![0]).toContain('isCrossPeriodForward')
    expect(m![0]).not.toMatch(/row\.voucherDate\s*<=\s*cutoffDate\.value\s*&&/)
  })

  it('D4-18 用 isCrossPeriodBackward，checkCutoff 不再内联 deliveryDate<=cutoff', () => {
    const src = stripComments(readComp('D4TabCutoffBackward.vue'))
    expect(src).toContain('isCrossPeriodBackward')
    const m = src.match(/function checkCutoff[\s\S]*?\n\}/)
    expect(m).toBeTruthy()
    expect(m![0]).toContain('isCrossPeriodBackward')
    expect(m![0]).not.toMatch(/row\.deliveryDate\s*<=\s*cutoffDate\.value\s*&&/)
  })
})

describe('D4-19 折扣比例走公式引擎单一真源（不内联 discountAmount/revenueAmount）', () => {
  it('D4-19 calcRate 用 calcDiscountRate，不再内联 discountAmount / revenueAmount', () => {
    const src = stripComments(readComp('D4TabDiscount.vue'))
    expect(src).toContain('calcDiscountRate')
    expect(src).toMatch(/import\s*\{[^}]*calcDiscountRate[^}]*\}\s*from\s*'[^']*useD4FormulaEngine'/)
    const m = src.match(/function calcRate[\s\S]*?\n\}/)
    expect(m).toBeTruthy()
    expect(m![0]).toContain('calcDiscountRate')
    // 不再手写 折扣额/收入额 内联除法
    expect(m![0]).not.toMatch(/row\.discountAmount\s*\/\s*row\.revenueAmount/)
  })
})

describe('D4-17~20 推送候选按人工判定过滤（发现≠自动错报）', () => {
  it('D4-17: 只推 isCutoff === false（跨期问题），非 remark/reason 非空', () => {
    const src = stripComments(readComp('D4TabCutoffForward.vue'))
    expect(src).toMatch(/\.filter\(\s*r\s*=>\s*r\.isCutoff\s*===\s*false\s*\)/)
  })
  it('D4-18: 只推 isCutoff === false', () => {
    const src = stripComments(readComp('D4TabCutoffBackward.vue'))
    expect(src).toMatch(/\.filter\(\s*r\s*=>\s*r\.isCutoff\s*===\s*false\s*\)/)
  })
  it('D4-19: 折扣错报金额由人工 prompt 输入（不把折扣额自动等同错报），金额 0 不推', () => {
    const src = stripComments(readComp('D4TabDiscount.vue'))
    expect(src).toMatch(/ElMessageBox\.prompt/)
    expect(src).toMatch(/if\s*\(\s*!amount\s*\)/)
  })
  it('D4-20: 只推 isAbnormal === "是"（人工标记异常），非 hasLitigation 非空', () => {
    const src = stripComments(readComp('D4TabReturn.vue'))
    expect(src).toMatch(/\.filter\(\s*r\s*=>\s*r\.isAbnormal\s*===\s*'是'\s*\)/)
  })
})

// ── Req 3.1 反向守卫：发现（诉讼/原因/否）不得被自动推断为「异常」──────────────
// 锁死人工确认门的判据来源：isAbnormal/isCutoff 只能由人工录入或公式引擎给出，
// 不得被 hasLitigation/returnReason/reason 的「非空」或 discountAmount「有值」自动置为异常/错报。
describe('D4-17~20 发现≠自动错报：判据不得由 reason/否/诉讼/折扣额 自动推断（Req 3.1）', () => {
  it('D4-20: isAbnormal 只能人工录入，不得由 hasLitigation/returnReason 自动置「是」', () => {
    const src = stripComments(readComp('D4TabReturn.vue'))
    // 不得出现把 row.isAbnormal 赋值的自动推断（真赋值 `=` 且非比较 `==`/`===`；
    // CRUD 初始化用 `isAbnormal: ''` 是对象字面量的 `:` 不是 `=`，不在此列）。
    expect(src).not.toMatch(/\.isAbnormal\s*=(?!=)/)
    // 不得以「涉及诉讼 → 异常」「有退货原因 → 异常」的形式推断
    expect(src).not.toMatch(/hasLitigation[\s\S]{0,40}\.isAbnormal\s*=(?!=)/)
    expect(src).not.toMatch(/returnReason[\s\S]{0,40}\.isAbnormal\s*=(?!=)/)
  })
  it('D4-19: 错报金额来自人工 prompt 的 amount，不得把 discountAmount 自动当错报额推送', () => {
    const src = stripComments(readComp('D4TabDiscount.vue'))
    const m = src.match(/function handlePushToA13[\s\S]*?\n\}/)
    expect(m).toBeTruthy()
    const body = m![0]
    // 推送项 amount 用人工 prompt 解析出的 amount，禁止直接用行折扣额
    expect(body).toMatch(/amount\s*=\s*parseFloat\(amountStr\)/)
    expect(body).toMatch(/amount,\s*description:/)
    expect(body).not.toMatch(/discountAmount/)
  })
  it('D4-17/18: 推送判据是公式引擎派生的 isCutoff===false，不得由 remark/reason 非空推断', () => {
    for (const f of ['D4TabCutoffForward.vue', 'D4TabCutoffBackward.vue']) {
      const src = stripComments(readComp(f))
      const m = src.match(/function handlePushToA13[\s\S]*?\n\}/)
      expect(m, `${f}: 缺 handlePushToA13`).toBeTruthy()
      const body = m![0]
      // 过滤条件只看 isCutoff===false，不得以 remark/reason 非空作为推送门
      expect(body).toMatch(/\.filter\(\s*r\s*=>\s*r\.isCutoff\s*===\s*false\s*\)/)
      expect(body, `${f}: 不得以 remark 非空作为推送门`).not.toMatch(/filter\([^)]*r\.remark/)
    }
  })
})

// ── Task 6 四态变异：公式同定义（单一真源）守卫命中 ──────────────────────────────
// Design Property 4 / Req 4.1：把「走公式引擎」翻成反模式「内联手写公式」，断言守卫正则
// 命中该 mutant 源串——即单源守卫拦得住「前端偷偷内联、与后端权威执行分叉」的回归。
describe('Task 6 mutation · 公式同定义单源守卫命中（内联反模式被拦）', () => {
  it('D4-17 checkCutoff：mutant「内联 voucherDate<=cutoff」会被守卫正则命中', () => {
    // 真实源不含内联比较（正向已由上方 guard 锁定）；此处证明守卫对反模式敏感。
    const mutantBody = `function checkCutoff(row) {\n  row.isCutoff = row.voucherDate <= cutoffDate.value && row.deliveryDate > cutoffDate.value\n}`
    // 守卫用的正则若作用在 mutant 上必须命中（否则守卫是空转的）
    expect(mutantBody).toMatch(/row\.voucherDate\s*<=\s*cutoffDate\.value\s*&&/)
    // 反证：真实源不含该内联
    const real = stripComments(readComp('D4TabCutoffForward.vue'))
    const m = real.match(/function checkCutoff[\s\S]*?\n\}/)
    expect(m![0]).not.toMatch(/row\.voucherDate\s*<=\s*cutoffDate\.value\s*&&/)
  })

  it('D4-19 calcRate：mutant「内联 discountAmount/revenueAmount」会被守卫正则命中', () => {
    const mutantBody = `function calcRate(row) {\n  row.discountRate = row.discountAmount / row.revenueAmount\n}`
    expect(mutantBody).toMatch(/row\.discountAmount\s*\/\s*row\.revenueAmount/)
    const real = stripComments(readComp('D4TabDiscount.vue'))
    const m = real.match(/function calcRate[\s\S]*?\n\}/)
    expect(m![0]).not.toMatch(/row\.discountAmount\s*\/\s*row\.revenueAmount/)
    expect(m![0]).toContain('calcDiscountRate') // 真实走单源引擎函数
  })

  it('D4-20 mutant「isAbnormal 由 hasLitigation 自动推断」会被守卫正则命中', () => {
    // 反模式：涉诉讼 → 自动置异常（Req 3.1 明令禁止）
    const mutantBody = `if (row.hasLitigation === '是') { row.isAbnormal = '是' }`
    expect(mutantBody).toMatch(/\.isAbnormal\s*=(?!=)/)
    // 真实源无此自动赋值（正向 guard 已锁）
    const real = stripComments(readComp('D4TabReturn.vue'))
    expect(real).not.toMatch(/\.isAbnormal\s*=(?!=)/)
  })
})
