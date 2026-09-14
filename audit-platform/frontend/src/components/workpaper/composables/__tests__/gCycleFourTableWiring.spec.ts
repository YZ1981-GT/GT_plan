/**
 * G 循环四表取数接线守卫（Property 7：render 输出必须有前端消费点）。
 *
 * **为什么需要**
 *
 * 「后端输出了但前端不读」是本平台反复出现的静默缺陷形态，编译与测试全绿：
 * - 2026-08-01 实测：13 个 G render 全部输出 `tb_source_codes`，但**11 个循环零消费**
 *   —— 后端算了、前端不读，「四表入库后底稿有数据」在这些循环根本不成立。
 * - 9 个宿主**没给审定表传 `:html-data`** → 连读取通路都没有（同「宿主漏传 projectId
 *   = 披露同步永久静默失败」范式）。
 * - G5 的面板传的 4 个属性**全不是面板 prop** 且没传 `source-codes` → 面板
 *   `visible` 恒 false，**从未渲染过**；G6 写 `report-row`/`hint` 而真实 prop 是
 *   `fallback-row-code`/`hints` → 静默失效。未知属性会落到根元素当 HTML 属性，
 *   Volar / vitest / Vite **全查不出**。
 *
 * 故本守卫从源码层锁死：宿主传参、面板挂载、prop 名合法、溯源字段被读取。
 *
 * spec: .kiro/specs/g-cycle-extraction-mapping-and-disclosure-alignment/
 *       Requirements 3.2, 3.6 / Property 7
 */
import fs from 'node:fs'
import path from 'node:path'

import { describe, expect, it } from 'vitest'

// 本文件位于 .../components/workpaper/composables/__tests__/ → 回 workpaper 需 2 级
const WORKPAPER_DIR = path.resolve(__dirname, '../..')
const PANEL_FILE = path.join(WORKPAPER_DIR, 'shared/WpFourTableSourcePanel.vue')

/** 循环 → [审定表相对路径, 宿主文件名] */
const CYCLES: Readonly<Record<string, [string, string]>> = {
  G1: ['g1-trading-financial-assets/core/G1TabAdjudication.vue', 'GtG1TradingFinancialAssets.vue'],
  G2: ['g2-interest-receivable/G2TabAdjudication.vue', 'GtG2InterestReceivable.vue'],
  G3: ['g3-dividend-receivable/G3TabAdjudication.vue', 'GtG3DividendReceivable.vue'],
  G4: ['g4-bond-investment-main/core/G4TabAdjudication.vue', 'GtG4BondInvestmentMain.vue'],
  G5: ['g5-long-term-receivable/core/G5TabAdjudication.vue', 'GtG5LongTermReceivable.vue'],
  G6: ['g6-other-bond-investment-main/core/G6TabAdjudication.vue', 'GtG6OtherBondMain.vue'],
  G7: ['g7-long-term-equity-main/core/G7TabAdjudication.vue', 'GtG7LongTermEquityMain.vue'],
  G8: ['g8-other-equity-instruments/core/G8TabAdjudication.vue', 'GtG8OtherEquityInstruments.vue'],
  G9: ['g9-other-noncurrent-financial/core/G9TabAdjudication.vue', 'GtG9OtherNoncurrentFinancial.vue'],
  G10: ['g10-trading-financial-liabilities/core/G10TabAdjudication.vue', 'GtG10TradingFinancialLiabilities.vue'],
  G11: ['g11-investment-income/core/G11TabAdjudication.vue', 'GtG11InvestmentIncome.vue'],
  G12: ['g12-net-hedge-gains/core/G12TabAdjudication.vue', 'GtG12NetHedgeGains.vue'],
  G13: ['g13-fair-value-changes/G13TabAdjudication.vue', 'GtG13FairValueChanges.vue'],
  G14: ['g14-credit-impairment-loss/G14TabAdjudication.vue', 'GtG14CreditImpairmentLoss.vue'],
}

const ALL = Object.keys(CYCLES)

function read(rel: string): string {
  return fs.readFileSync(path.join(WORKPAPER_DIR, rel), 'utf-8')
}

/** 剥 HTML / JS 注释（说明文字里会写反例 prop 名，不剥必误判） */
function strip(src: string): string {
  return src
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:'"\\])\/\/[^\n]*/g, '$1')
}

/** 从面板 SFC 的 defineProps 抽出合法 prop 名（kebab-case） */
function panelPropNames(): Set<string> {
  const src = strip(fs.readFileSync(PANEL_FILE, 'utf-8'))
  const m = /defineProps<\{([\s\S]*?)\}>\(\)/.exec(src)
  if (!m) return new Set()
  const names = [...m[1].matchAll(/^\s*([a-zA-Z][a-zA-Z0-9]*)\??\s*:/gm)].map((x) => x[1])
  return new Set(names.map((n) => n.replace(/[A-Z]/g, (c) => `-${c.toLowerCase()}`)))
}

describe('自检：文件与面板 prop 清单可读', () => {
  it('面板文件存在且能抽出 prop 名', () => {
    expect(fs.existsSync(PANEL_FILE)).toBe(true)
    const props = panelPropNames()
    expect(props.size, '未能从面板抽出 prop 名 → 正则失效').toBeGreaterThanOrEqual(5)
    expect(props.has('source-codes')).toBe(true)
    expect(props.has('gross-label')).toBe(true)
    expect(props.has('fallback-row-code')).toBe(true)
  })

  it('14 个循环的审定表与宿主文件都存在', () => {
    for (const cyc of ALL) {
      const [tab, host] = CYCLES[cyc]
      expect(fs.existsSync(path.join(WORKPAPER_DIR, tab)), `${cyc} 审定表缺失`).toBe(true)
      expect(fs.existsSync(path.join(WORKPAPER_DIR, host)), `${cyc} 宿主缺失`).toBe(true)
    }
  })
})

describe('Property 7：每个 G 循环审定表都消费 tb_source_codes', () => {
  it.each(ALL)('%s 审定表挂载了共享溯源面板', (cyc) => {
    const src = strip(read(CYCLES[cyc][0]))
    expect(src, `${cyc} 未挂载 WpFourTableSourcePanel`).toContain('WpFourTableSourcePanel')
  })

  it.each(ALL)('%s 审定表读取 tb_source_codes（不得是 dead output）', (cyc) => {
    const src = strip(read(CYCLES[cyc][0]))
    expect(
      /tb_source_codes|tbSourceCodes/.test(src),
      `${cyc} 审定表未读 tb_source_codes`,
    ).toBe(true)
  })

  it.each(ALL)('%s 审定表声明了 htmlData prop（面板的数据来源）', (cyc) => {
    const src = strip(read(CYCLES[cyc][0]))
    expect(/htmlData\??\s*:/.test(src), `${cyc} 审定表无 htmlData prop`).toBe(true)
  })
})

describe('🔴 宿主必须把 html_data 传给审定表（漏传 = 静默锁死）', () => {
  it.each(ALL)('%s 宿主传了 :html-data', (cyc) => {
    const [, host] = CYCLES[cyc]
    const src = strip(read(host))
    const m = new RegExp(`<${cyc}TabAdjudication\\b([\\s\\S]{0,900}?)/>`).exec(src)
    expect(m, `${cyc} 宿主里找不到 <${cyc}TabAdjudication …/>`).toBeTruthy()
    expect(
      /:html-data=/.test(m![1]),
      `${cyc} 宿主未给审定表传 :html-data → 面板与取数全部拿不到数据（不报错、不红）`,
    ).toBe(true)
  })
})

describe('🔴 面板 prop 名必须合法（错名静默失效）', () => {
  /** Vue 指令 / 事件绑定不算 prop */
  const DIRECTIVES = /^(v-|@|:key$|key$|ref$|class$|style$)/

  it.each(ALL)('%s 未给面板传不存在的 prop', (cyc) => {
    const legal = panelPropNames()
    const src = strip(read(CYCLES[cyc][0]))
    const uses = [...src.matchAll(/<WpFourTableSourcePanel([\s\S]{0,900}?)\/>/g)]
    expect(uses.length, `${cyc} 未找到面板使用点`).toBeGreaterThan(0)
    for (const u of uses) {
      const attrs = [...u[1].matchAll(/(?::)?([a-z][a-zA-Z0-9-]*)=/g)].map((x) => x[1])
      const unknown = attrs.filter((a) => !legal.has(a) && !DIRECTIVES.test(a))
      expect(
        unknown,
        `${cyc} 给面板传了不存在的 prop ${JSON.stringify(unknown)}；`
          + `合法 prop：${[...legal].join(', ')}`,
      ).toEqual([])
    }
  })

  it.each(ALL)('%s 必须传 source-codes（否则面板 visible 恒 false、从不渲染）', (cyc) => {
    const src = strip(read(CYCLES[cyc][0]))
    const uses = [...src.matchAll(/<WpFourTableSourcePanel([\s\S]{0,900}?)\/>/g)]
    for (const u of uses) {
      expect(
        /:source-codes=/.test(u[1]),
        `${cyc} 面板缺 :source-codes —— G5 曾因此从未渲染过`,
      ).toBe(true)
    }
  })

  it('反向自检：不存在的 prop 名确实会被判非法', () => {
    const legal = panelPropNames()
    expect(legal.has('report-row')).toBe(false)
    expect(legal.has('hint')).toBe(false)
    expect(legal.has('gross-standard')).toBe(false)
    expect(legal.has('resolved-from')).toBe(false)
  })

  it('反向自检：strip 确实剥掉了注释里的反例 prop 名', () => {
    const raw = read(CYCLES.G6[0])
    // 纠错说明保留在注释里
    expect(raw).toContain('report-row')
    expect(strip(raw)).not.toContain('report-row')
  })
})

describe('面板呈现语义解析的审计追溯信号', () => {
  const panel = strip(fs.readFileSync(PANEL_FILE, 'utf-8'))

  it('冲突告警（report_config 错码时以科目表为准但必须可见）', () => {
    expect(panel).toContain('tbConflictTexts')
  })

  it('旧准则科目待人工映射提示', () => {
    expect(panel).toContain('tbUnmappedTexts')
  })

  it('「本项目无此科目」提示（区别于余额为 0）', () => {
    expect(panel).toContain('tbSemanticSlots')
    expect(panel).toContain('found === false')
  })

  it('🔴 科目表不可用只在**显式 false** 时告警（旧路径不发该字段）', () => {
    expect(panel).toContain('chart_available === false')
  })
})
