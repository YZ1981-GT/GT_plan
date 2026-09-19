/**
 * H 类金额控件守卫（spec `h-cycle-extraction-formula-and-disclosure-completion` Task 12）
 *
 * **双向锁死**（缺任一侧都会漂移）：
 * - 正向：登记的目标文件里**金额列**必须是 `<WpAmountInput>`，不得回退 `el-input-number`
 * - 反向：**非金额列**（利率 / 比例 / 年限 / 笔数）必须**保持** `el-input-number`，
 *   套 `WpAmountInput` 会给「本期利息资本化率 5.2%」加上千分符与两位小数语义
 *
 * 🔴 为什么必须替换：element-plus **2.13.6** 的 `input-number` 编译产物里
 * **不存在 `formatter` / `parser` prop**（`es/components/input-number/**` 全文无
 * `formatter`）⇒ 平台存量 40+ 处 `el-input-number :formatter` **全是空操作，
 * 千分符从未生效**（浏览器双证：`el-input-number :formatter` 下输 1234567.5 显示
 * `1234567.50` 无千分符；换 `el-input` 后显示 `1,234,567.50`）。
 *
 * 判据真源 = `composables/hCycleAmountControlRegistry.ts`（非金额列逐条带理由），
 * 幂等脚本 = `backend/scripts/fix/fix_h_cycle_amount_controls.py --check`。
 */
import fs from 'node:fs'
import path from 'node:path'

import { describe, expect, it } from 'vitest'

import {
  H_AMOUNT_TARGET_FILES,
  H_NON_AMOUNT_NAME_HINTS,
  H_NON_AMOUNT_FIELDS,
  H_NON_AMOUNT_NAME_HINTS,
  isHNonAmountField,
} from '../composables/hCycleAmountControlRegistry'

// 本文件位于 .../components/workpaper/__tests__/ → 回仓库根需 6 级
const REPO_ROOT = path.resolve(__dirname, '../../../../../..')
const WP_DIR = path.join(REPO_ROOT, 'audit-platform/frontend/src/components/workpaper')

function readWp(rel: string): string {
  const p = path.join(WP_DIR, rel)
  if (!fs.existsSync(p)) throw new Error(`守卫路径失效（REPO_ROOT 回退级数错？）: ${p}`)
  return fs.readFileSync(p, 'utf-8')
}

/** 剥 HTML 注释 + JS 注释（注释里会写反例，不剥必误判） */
export function stripComments(src: string): string {
  return src
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:])\/\/[^\n]*/g, '$1')
}

/** 标签存在性：带名字边界，`<FooREMOVED` 不算命中 */
export function countTag(src: string, tag: string): number {
  return (src.match(new RegExp(`<${tag}(?=[\\s/>])`, 'g')) || []).length
}

/** 取某标签的完整开标签串（逐个，尊重引号，禁固定字符窗口） */
export function tagOpens(src: string, tag: string): string[] {
  const re = new RegExp(`<${tag}(?=[\\s/>])`, 'g')
  const out: string[] = []
  let m: RegExpExecArray | null
  while ((m = re.exec(src))) {
    let i = m.index + m[0].length
    let quote: string | null = null
    while (i < src.length) {
      const ch = src[i]
      if (quote) {
        if (ch === quote) quote = null
      } else if (ch === '"' || ch === "'") {
        quote = ch
      } else if (ch === '>') {
        break
      }
      i++
    }
    out.push(src.slice(m.index, i + 1))
  }
  return out
}

/** 从开标签抽绑定的字段名（`v-model="row.x"` / `:model-value="cellAmt(row,'k')"`） */
export function fieldOf(tag: string): string {
  const m = tag.match(/(?:v-model(?:\.number)?|:model-value)\s*=\s*"([^"]+)"/)
  if (!m) return ''
  const expr = m[1].trim()
  const fn = expr.match(/^([A-Za-z_$][\w$]*)\s*\(/)
  if (fn) return fn[1]
  const parts = expr.split('.')
  return parts[parts.length - 1].replace(/[^\w$]/g, '')
}

describe('H 类金额控件（Task 12 / 正向：金额列必须是 WpAmountInput）', () => {
  it('登记表自检：目标文件非空、路径真实存在（防守卫空转）', () => {
    expect(H_AMOUNT_TARGET_FILES.length).toBeGreaterThanOrEqual(9)
    for (const rel of H_AMOUNT_TARGET_FILES) {
      expect(fs.existsSync(path.join(WP_DIR, rel)), `登记的文件不存在: ${rel}`).toBe(true)
    }
    expect(Object.keys(H_NON_AMOUNT_FIELDS).length).toBeGreaterThan(0)
    expect(H_NON_AMOUNT_NAME_HINTS.length).toBeGreaterThan(5)
  })

  it.each(H_AMOUNT_TARGET_FILES)('%s 金额列全部使用 WpAmountInput', (rel) => {
    const src = stripComments(readWp(rel))
    expect(countTag(src, 'WpAmountInput'), `${rel} 未渲染 WpAmountInput`).toBeGreaterThan(0)

    const bad: string[] = []
    for (const tag of tagOpens(src, 'el-input-number')) {
      const field = fieldOf(tag)
      // 留下的 el-input-number 必须是登记过的非金额列
      if (!isHNonAmountField(rel, field)) bad.push(field || '(未识别字段)')
    }
    expect(
      bad,
      `${rel} 仍有未登记的 el-input-number（EP 2.13.6 无 formatter prop ⇒ 千分符不生效）：${bad.join(', ')}`,
    ).toEqual([])
  })

  it.each(H_AMOUNT_TARGET_FILES)('%s 已显式 import WpAmountInput', (rel) => {
    const src = stripComments(readWp(rel))
    expect(src, `${rel} 缺 WpAmountInput 的 import`).toMatch(
      /import\s+WpAmountInput\s+from\s+['"][^'"]*WpAmountInput\.vue['"]/,
    )
  })

  it.each(H_AMOUNT_TARGET_FILES)('%s 的 WpAmountInput 上无 el-input-number 专属 prop 残留', (rel) => {
    const src = stripComments(readWp(rel))
    const bad: string[] = []
    for (const tag of tagOpens(src, 'WpAmountInput')) {
      // WpAmountInput 的 defineProps 只有 modelValue/disabled/size/placeholder/ariaLabel
      for (const p of [':controls', ':precision', ':min', ':max', ':step']) {
        if (tag.includes(`${p}=`)) bad.push(`${fieldOf(tag)}${p}`)
      }
    }
    expect(bad, `${rel} 残留 el-input-number 专属 prop（会静默落到根元素）：${bad.join(', ')}`).toEqual(
      [],
    )
  })
})

describe('H 类金额控件（Task 12 / 反向：非金额列必须保持 el-input-number）', () => {
  it('登记的非金额列确实仍是 el-input-number（禁把比率套成金额）', () => {
    const missing: string[] = []
    for (const key of Object.keys(H_NON_AMOUNT_FIELDS)) {
      const [rel, field] = key.split('::')
      const src = stripComments(readWp(rel))
      const hit = tagOpens(src, 'el-input-number').some((t) => fieldOf(t) === field)
      if (!hit) missing.push(key)
    }
    expect(
      missing,
      `以下非金额列已不是 el-input-number（利率/比例套千分符+两位小数是语义错误）：${missing.join(', ')}`,
    ).toEqual([])
  })

  it('登记的非金额列不得出现在 WpAmountInput 上', () => {
    const bad: string[] = []
    for (const key of Object.keys(H_NON_AMOUNT_FIELDS)) {
      const [rel, field] = key.split('::')
      const src = stripComments(readWp(rel))
      if (tagOpens(src, 'WpAmountInput').some((t) => fieldOf(t) === field)) bad.push(key)
    }
    expect(bad, `以下非金额列被错误替换：${bad.join(', ')}`).toEqual([])
  })

  it('每条非金额登记都带非空理由（防当逃逸阀用）', () => {
    for (const [key, reason] of Object.entries(H_NON_AMOUNT_FIELDS)) {
      expect(String(reason).trim().length, `${key} 理由为空`).toBeGreaterThanOrEqual(8)
    }
  })
})

describe('反向自检（证明上面的断言不是空转）', () => {
  it('把 WpAmountInput 改名后标签断言必红（标签判据带名字边界）', () => {
    const src = readWp(H_AMOUNT_TARGET_FILES[0])
    const mutated = src.replace(/<WpAmountInput(?=[\s/>])/, '<WpAmountInputREMOVED')
    expect(countTag(mutated, 'WpAmountInput')).toBe(countTag(src, 'WpAmountInput') - 1)
    // 弱判据对照：`includes('<WpAmountInput')` 会被骗过 —— 这正是要避免的写法
    expect(mutated).toContain('<WpAmountInput')
  })

  it('未登记的 el-input-number 会被点名', () => {
    const fake = '<el-input-number v-model="row.someAmount" :controls="false" />'
    const field = fieldOf(tagOpens(fake, 'el-input-number')[0])
    expect(field).toBe('someAmount')
    expect(isHNonAmountField('h1/core/H1TabAdjudication.vue', field)).toBe(false)
  })

  it('isHNonAmountField 只认登记表，不做名称推断（判据单一真源）', () => {
    // 🔴 这是**有意设计**：判据必须是「逐条登记 + 写明理由」，
    // 否则任何新起的 `xxxRate` 字段会被静默豁免、无人复核其口径。
    // 名称启发式只作守卫侧的**第二道防线**（见下一条），不参与生产判定。
    expect(isHNonAmountField('h2/core/H2TabDisclosureListed.vue', 'interestCapRate')).toBe(true)
    expect(
      isHNonAmountField('any/unregistered.vue', 'interestCapRate'),
      '未登记文件即便字段名像比率也不得被豁免',
    ).toBe(false)
    for (const f of ['beginBalance', 'endBook', 'aje', 'transferToFA']) {
      expect(isHNonAmountField('h1/core/H1TabAdjudication.vue', f), `${f} 应判为金额`).toBe(false)
    }
    // 同前缀不同语义：只有「率」不是金额，累计额/本期额都是金额（故按完整字段名登记）
    for (const f of ['interestCapAccum', 'interestCapCurrent']) {
      expect(isHNonAmountField('h2/core/H2TabDisclosureListed.vue', f), `${f} 是金额`).toBe(false)
    }
  })

  it('名称启发式清单可用作第二道防线（比率/年限/笔数类关键词）', () => {
    const hit = (f: string) => H_NON_AMOUNT_NAME_HINTS.some((h) => f.includes(h))
    for (const f of ['interestCapRate', 'cumInputPct', 'usefulYears', 'sampleCount', 'salvageRatio']) {
      expect(hit(f), `${f} 应命中关键词`).toBe(true)
    }
    for (const f of ['beginBalance', 'endBook', 'aje', 'transferToFA', 'interestCapAccum']) {
      expect(hit(f), `${f} 不应命中关键词`).toBe(false)
    }
  })

  it('tagOpens 尊重引号：属性值里的 > 不会提前截断', () => {
    const src = '<WpAmountInput @update:model-value="(v: number) => set(v)" size="small" />'
    const opens = tagOpens(src, 'WpAmountInput')
    expect(opens).toHaveLength(1)
    expect(opens[0]).toContain('size="small"')
  })

  it('stripComments 自检：注释里的反例不参与判定', () => {
    const withComment = '<!-- 反例：<el-input-number v-model="row.x" /> -->\n<div/>'
    expect(countTag(stripComments(withComment), 'el-input-number')).toBe(0)
    expect(countTag(withComment, 'el-input-number')).toBe(1)
  })
})
