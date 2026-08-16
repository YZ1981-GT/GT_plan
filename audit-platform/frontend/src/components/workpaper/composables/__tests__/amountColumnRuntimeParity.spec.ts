/**
 * amountColumnRuntimeParity — 运行时金额列判定 & 跨真源一致性守卫（建议2 运行时兜底）
 *
 * 背景：通用列渲染器（COLUMN_CONFIG 驱动的 E1-23 收支检查 / E1-26~32 IPO 组）的
 * `:label` 是**运行时值**，静态迁移探针 audit_amount_input_columns.py 判不了列语义
 * （全部落 ambiguous.dynamic_label）。运行时改用 `wpAmountInput.isAmountColumn(col)`
 * 判金额性：金额动态列渲染 `WpAmountInput`（千分符生效），非金额数值列（月份/利率等）
 * 保留 `el-input-number`。
 *
 * 本守卫锁三件事：
 * 1. 两个通用渲染器的 `col.type==='number'` 分支确实按 isAmountColumn 拆了
 *    WpAmountInput（金额）/ el-input-number（非金额），且不再挂失效的 `:formatter`。
 * 2. **跨真源一致性**：isAmountColumn（运行时，黑名单+默认金额）与迁移探针真源
 *    amountColumnSemantics（白名单+默认非金额）**兜底方向相反是设计使然**，不能要求
 *    全一致；但凡真源**明确命中** NON_AMOUNT / AMOUNT pattern 的列，isAmountColumn
 *    必须与之一致 —— 精确锁住「日利率(/360) 被误判金额」这类漂移。
 * 3. 定向回归：`日利率(/360)` / `月份` 等非金额数值列 isAmountColumn=false。
 *
 * spec: amount-input-migration-and-column-typing（建议2）
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { isAmountColumn } from '../wpAmountInput'
import { COLUMN_CONFIG, type ColumnDef, type IpoSheetCode } from '../useE1IpoSpecial'
import {
  classifyColumnLabel,
  matchesAmount,
  matchesNonAmount,
} from '../../shared/amountColumnSemantics'

const E1_DIR = resolve(__dirname, '../../e1')

function readVue(name: string): string {
  return readFileSync(resolve(E1_DIR, name), 'utf-8')
}

/** 剥离注释，避免踩坑说明里的反例被数成真实用法 */
function stripComments(src: string): string {
  return src
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:])\/\/[^\n]*/g, '$1')
}

/** 用 isAmountColumn 语义的两个通用列渲染器 */
const GENERIC_RENDERERS = ['E1TabLargeCheck.vue', 'E1TabIpoSpecial.vue']

// 收集 COLUMN_CONFIG 全部 number 列（跨真源一致性的样本）
interface NumCol {
  sheet: string
  key: string
  label: string
}
const NUMBER_COLS: NumCol[] = []
for (const [sheet, cols] of Object.entries(COLUMN_CONFIG)) {
  for (const c of cols as ColumnDef[]) {
    if (c.type === 'number') NUMBER_COLS.push({ sheet: sheet as IpoSheetCode, key: c.key, label: c.label })
  }
}

describe('建议2：通用渲染器动态金额列运行时用 WpAmountInput', () => {
  it.each(GENERIC_RENDERERS)(
    '%s：number 分支按 isAmountColumn 拆 WpAmountInput / el-input-number',
    (name) => {
      const src = stripComments(readVue(name))
      // 金额动态列走 WpAmountInput（v-else-if 带 isAmountColumn(col)）
      expect(
        /<WpAmountInput[\s\S]{0,240}col\.type === 'number' && isAmountColumn\(col\)/.test(src),
        `${name} 金额动态列须用 WpAmountInput + isAmountColumn(col) 门控`,
      ).toBe(true)
      // 非金额数值列仍保留 el-input-number（不带 isAmountColumn 的 number 分支）
      expect(src, `${name} 非金额数值列须保留 el-input-number`).toContain(
        'v-else-if="col.type === \'number\'"',
      )
      // 已 import WpAmountInput
      expect(src, `${name} 须 import WpAmountInput`).toContain('WpAmountInput.vue')
      // 动态列不得再挂失效的 :formatter（EP 2.13.6 无该 prop = 千分符空操作）
      expect(
        src.includes(':formatter="isAmountColumn'),
        `${name} 不应再用失效的 el-input-number :formatter`,
      ).toBe(false)
    },
  )
})

describe('建议2：isAmountColumn 与迁移探针真源判定跨真源一致（明确命中项）', () => {
  it('反向自检：COLUMN_CONFIG 收集到足量 number 列', () => {
    expect(NUMBER_COLS.length).toBeGreaterThan(15)
  })

  it('反向自检：样本里确实同时存在明确金额列与明确非金额列（否则断言空转）', () => {
    const hasAmount = NUMBER_COLS.some((c) => matchesAmount(c.label) && !matchesNonAmount(c.label))
    const hasNonAmount = NUMBER_COLS.some((c) => matchesNonAmount(c.label) && !matchesAmount(c.label))
    expect(hasAmount, '样本缺明确金额列').toBe(true)
    expect(hasNonAmount, '样本缺明确非金额列（如月份/利率）').toBe(true)
  })

  it.each(NUMBER_COLS)('$sheet.$key「$label」：明确命中项两真源一致', ({ label }) => {
    const runtimeIsAmount = isAmountColumn({ label })
    const hitAmount = matchesAmount(label)
    const hitNonAmount = matchesNonAmount(label)
    // 真源明确非金额（命中 NON_AMOUNT 且未同时命中 AMOUNT）→ isAmountColumn 必 false
    if (hitNonAmount && !hitAmount) {
      expect(runtimeIsAmount, `「${label}」真源明确非金额，isAmountColumn 应为 false`).toBe(false)
    }
    // 真源明确金额（命中 AMOUNT 且未同时命中 NON_AMOUNT）→ isAmountColumn 必 true
    if (hitAmount && !hitNonAmount) {
      expect(runtimeIsAmount, `「${label}」真源明确金额，isAmountColumn 应为 true`).toBe(true)
    }
    // 兜底方向差异（都不命中 / 同时命中歧义）不作断言：真源默认非金额（迁移保守），
    // isAmountColumn 默认金额（运行时数值列积极加千分符），各自场景合理。
  })
})

describe('建议2：非金额数值列定向回归（本次修的 isAmountColumn 盲区）', () => {
  it('日利率(/360)：带后缀的利率列不再被误判金额（修 率$ 锚定盲区）', () => {
    expect(isAmountColumn({ key: 'dailyRate', label: '日利率(/360)' })).toBe(false)
    // 真源侧同判非金额
    expect(classifyColumnLabel('日利率(/360)')).toBe('non_amount')
  })

  it('月份/账户数量/张数：非金额数值列 isAmountColumn=false', () => {
    expect(isAmountColumn({ key: 'month', label: '月份' })).toBe(false)
    expect(isAmountColumn({ label: '账户数量' })).toBe(false)
    expect(isAmountColumn({ label: '持有张数' })).toBe(false)
  })

  it('金额/借方金额/收支金额：金额列 isAmountColumn=true', () => {
    expect(isAmountColumn({ key: 'amount', label: '金额' })).toBe(true)
    expect(isAmountColumn({ label: '借方金额' })).toBe(true)
    expect(isAmountColumn({ label: '收支金额' })).toBe(true)
  })
})
