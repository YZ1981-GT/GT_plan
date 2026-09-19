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
