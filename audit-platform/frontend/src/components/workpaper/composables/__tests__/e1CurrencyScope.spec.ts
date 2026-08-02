/**
 * e1CurrencyScope.spec.ts — E1 币种 / 受限类别 单一真源守卫
 *
 * **E 类没有账龄维度** —— 货币资金不涉及账龄。E 类与其它循环「账龄枚举」对应的
 * 枚举维度是**币种**与**受限类别**，本守卫钉死这两者的单一真源与稳定 key。
 *
 * 🔴 源码型断言必先 blankComments()：本守卫与被守卫源码的注释里都写着反例
 *    （币种名、桶中文名），不剥离会误报。每条都有反向自检。
 *
 * **Validates: Requirements 4.5, 4.6, 11.3, 11.7, 11.8, 11.9, 11.10**
 *
 * spec: e1-four-table-extraction-and-disclosure-alignment (Task 7)
 * Properties: 9, 10, 17
 */
import { describe, it, expect } from 'vitest'
import fc from 'fast-check'
import { readFileSync, existsSync } from 'fs'
import { resolve } from 'path'

import {
  E1_DEFAULT_CURRENCIES,
  E1_FX_GROUPS,
  E1_NOTE_FX_CURRENCY_LABELS,
  e1CurrencyRowKey,
  e1CustomCurrencyKey,
  e1DefaultRate,
  e1ForeignCurrencies,
  e1RmbAmount,
  e1SumCurrencyAcrossGroups,
} from '../e1CurrencyScope'
import {
  E1_MAIN_ROWS_LISTED,
  E1_MAIN_ROWS_SOE,
  e1MainColumns,
  e1SummableRows,
} from '../e1DisclosureScope'
import {
  E1_UNRESTRICTED,
  allLeavesTotal,
  customBucketKey,
  effectiveBucketOf,
  isCustomBucketKey,
  normalizeRestrictedPrefill,
  parseManualMap,
  pendingUnclassified,
  resolveBucketLabel,
  resolveRestrictedRows,
  restrictedTotals,
  serializeManualMap,
  unrestrictedLeaves,
  type E1RestrictedLeaf,
  type E1RestrictedPrefill,
} from '../e1RestrictedScope'

const WP_ROOT = resolve(__dirname, '../..')
const E1_ROOT = resolve(WP_ROOT, 'e1')
const COMPOSABLES = resolve(WP_ROOT, 'composables')

function blankComments(src: string): string {
  const blank = (m: string) => m.replace(/[^\n]/g, ' ')
  return src
    .replace(/\/\*[\s\S]*?\*\//g, blank)
    .replace(/<!--[\s\S]*?-->/g, blank)
    .replace(/(^|[^:])(\/\/[^\n]*)/gm, (_m, pre: string, cmt: string) => pre + blank(cmt))
}

// ─── 币种真源 ─────────────────────────────────────────────────────────────────

describe('币种单一真源', () => {
  it('预置币种逐字取自源 xlsx 原币表 R39~R43', () => {
    expect(E1_DEFAULT_CURRENCIES.map((c) => c.label)).toEqual([
      '人民币',
      '美元',
      '日元',
      '澳元',
      '欧元',
    ])
  })

  it('只有人民币是记账本位币，折算率恒 1', () => {
    const base = E1_DEFAULT_CURRENCIES.filter((c) => c.isBase)
    expect(base).toHaveLength(1)
    expect(base[0].label).toBe('人民币')
    expect(e1DefaultRate('cny')).toBe(1)
    expect(e1DefaultRate('usd')).toBe(0)
  })

  it('「外币性货币项目」派生表排除记账本位币', () => {
    const fx = e1ForeignCurrencies()
    expect(fx.map((c) => c.label)).toEqual(['美元', '日元', '澳元', '欧元'])
    expect(fx.every((c) => !c.isBase)).toBe(true)
  })

  it('原币表四个分组逐字取自源 xlsx R38/R44/R50/R56', () => {
    expect(E1_FX_GROUPS.map((g) => g.label)).toEqual([
      '库存现金',
      '银行存款',
      '银行存款中：财务公司存款',
      '其他货币资金',
    ])
    // 每组都带源 xlsx 单元格引用（供守卫反查）
    expect(E1_FX_GROUPS.every((g) => /!A\d+$/.test(g.sourceRef))).toBe(true)
  })

  it('附注外币章节币种口径与底稿不同（跨循环共享章节，如实记录）', () => {
    expect(E1_NOTE_FX_CURRENCY_LABELS).toEqual(['美元', '欧元', '港币'])
    const wpLabels = E1_DEFAULT_CURRENCIES.map((c) => c.label)
    expect(E1_NOTE_FX_CURRENCY_LABELS).not.toEqual(wpLabels)
    expect(wpLabels).not.toContain('港币')
  })
})

// ─── Property 9: 派生列读时推导 ───────────────────────────────────────────────

describe('Property 9: 派生列读时推导', () => {
  it('人民币金额 = 原币 × 折算率（源 xlsx D39=B39*C39）', () => {
    expect(e1RmbAmount(1000, 7.0288)).toBeCloseTo(7028.8, 6)
  })

  it('非法输入不产生 NaN', () => {
    expect(e1RmbAmount(NaN, 7)).toBe(0)
    expect(e1RmbAmount(1, Infinity)).toBe(0)
    expect(e1RmbAmount(undefined as unknown as number, 7)).toBe(0)
  })

  it('PBT: 外币性货币项目某币种 = 原币表四组同币种之和', () => {
    fc.assert(
      fc.property(
        fc.array(
          fc.record({
            currencyKey: fc.constantFrom('usd', 'jpy', 'eur'),
            groupSlot: fc.constantFrom('cash', 'bank', 'finance_co', 'other'),
            amount: fc.double({ min: -1e9, max: 1e9, noNaN: true, noDefaultInfinity: true }),
          }),
          { maxLength: 24 },
        ),
        (rows) => {
          const usd = e1SumCurrencyAcrossGroups(rows, 'usd', (r) => r.amount)
          const manual = rows
            .filter((r) => r.currencyKey === 'usd')
            .reduce((s, r) => s + r.amount, 0)
          expect(usd).toBeCloseTo(manual, 6)
        },
      ),
      { numRuns: 5 },
    )
  })
})

// ─── 稳定 key ─────────────────────────────────────────────────────────────────

describe('稳定 key（禁用 label 作 key）', () => {
  it('同分组同币种不同序号不撞键', () => {
    expect(e1CurrencyRowKey('cash', 'usd', 0)).not.toBe(e1CurrencyRowKey('cash', 'usd', 1))
  })

  it('不同分组同币种不撞键', () => {
    expect(e1CurrencyRowKey('cash', 'usd', 0)).not.toBe(e1CurrencyRowKey('bank', 'usd', 0))
  })

  it('同名自定义币种不撞键（label 作 key 会合并两行数据）', () => {
    expect(e1CustomCurrencyKey('新币种', 0)).not.toBe(e1CustomCurrencyKey('新币种', 1))
  })

  it('PBT: 任意 (group, currency, seq) 三元组唯一', () => {
    fc.assert(
      fc.property(
        fc.uniqueArray(
          fc.tuple(
            fc.constantFrom('cash', 'bank', 'finance_co', 'other'),
            fc.constantFrom('cny', 'usd', 'jpy', 'aud', 'eur'),
            fc.integer({ min: 0, max: 20 }),
          ),
          { selector: (t) => t.join('|'), maxLength: 40 },
        ),
        (triples) => {
          const keys = triples.map(([g, c, s]) => e1CurrencyRowKey(g, c, s))
          expect(new Set(keys).size).toBe(keys.length)
        },
      ),
      { numRuns: 5 },
    )
  })
})

// ─── 受限类别：前端不得抄中文标签 ─────────────────────────────────────────────

describe('受限类别中文标签只有后端一份', () => {
  const SCOPE_SRC = blankComments(
    readFileSync(resolve(COMPOSABLES, 'e1RestrictedScope.ts'), 'utf-8'),
  )

  it('反向自检：源码非空且含关键函数', () => {
    expect(SCOPE_SRC).toContain('resolveRestrictedRows')
  })

  it('前端不得内联桶中文名（后端 bucket_defs_payload 是唯一来源）', () => {
    const backendLabels = [
      '银行承兑汇票保证金',
      '信用证保证金',
      '履约保证金',
      '用于担保的定期存款或通知存款',
      '放在境外且资金汇回受到限制的款项',
      '其他受限资金',
    ]
    const leaked = backendLabels.filter((l) => SCOPE_SRC.includes(l))
    expect(leaked).toEqual([])
  })

  it('拿不到 bucketDefs 时退化显示 key（不编造中文名）', () => {
    expect(resolveBucketLabel('bank_acceptance', [])).toBe('bank_acceptance')
  })

  it('bucketDefs 存在时取后端 label', () => {
    const label = resolveBucketLabel('bank_acceptance', [
      { key: 'bank_acceptance', label: '来自后端的标签', isPlatformExtra: false },
    ])
    expect(label).toBe('来自后端的标签')
  })

  it('自定义类别的中文名由审计师输入，不算硬编码', () => {
    const key = customBucketKey('某专项监管户')
    expect(isCustomBucketKey(key)).toBe(true)
    expect(resolveBucketLabel(key, [])).toBe('某专项监管户')
  })
})

// ─── Property 17: 人工归类优先 ────────────────────────────────────────────────

function leaf(
  code: string,
  name: string,
  closing: number,
  autoBucket: string | null = null,
  opening = 0,
): E1RestrictedLeaf {
  return { code, name, opening, closing, slot: 'other', autoBucket }
}

const DEFS = [
  { key: 'bank_acceptance', label: 'BA', isPlatformExtra: false },
  { key: 'letter_of_credit', label: 'LC', isPlatformExtra: false },
  { key: 'other', label: 'OT', isPlatformExtra: true },
]

function prefill(leaves: E1RestrictedLeaf[]): E1RestrictedPrefill {
  return { leaves, bucketDefs: DEFS, source: { report_row_code: 'BS-002' } }
}

describe('Property 17: 人工归类优先且可精确重算', () => {
  it('自动分类结果按桶聚合', () => {
    const p = prefill([
      leaf('1012.01', '银行承兑汇票保证金', 100, 'bank_acceptance'),
      leaf('1012.02', '信用证保证金', 200, 'letter_of_credit'),
    ])
    const rows = resolveRestrictedRows({ prefill: p, manualMap: {} })
    expect(rows.map((r) => [r.bucketKey, r.endingAmount])).toEqual([
      ['bank_acceptance', 100],
      ['letter_of_credit', 200],
    ])
  })

  it('人工把叶子改归到别的类别 → 两侧余额都精确重算', () => {
    const p = prefill([
      leaf('1012.01', '银行承兑汇票保证金', 100, 'bank_acceptance'),
      leaf('1012.02', '信用证保证金', 200, 'letter_of_credit'),
    ])
    const rows = resolveRestrictedRows({
      prefill: p,
      manualMap: { '1012.01': 'letter_of_credit' },
    })
    const byKey = Object.fromEntries(rows.map((r) => [r.bucketKey, r.endingAmount]))
    // 原类别归零消失，新类别吸收 —— 预聚合表示做不到这点
    expect(byKey.bank_acceptance).toBeUndefined()
    expect(byKey.letter_of_credit).toBe(300)
  })

  it('人工归类把「待归类」叶子归入某类', () => {
    const p = prefill([leaf('1002.99', '某说不清的户', 500, null)])
    expect(pendingUnclassified(p, {})).toHaveLength(1)
    const rows = resolveRestrictedRows({ prefill: p, manualMap: { '1002.99': 'other' } })
    expect(rows).toHaveLength(1)
    expect(rows[0].endingAmount).toBe(500)
    expect(pendingUnclassified(p, { '1002.99': 'other' })).toHaveLength(0)
  })

  it('标记「不受限」的叶子不进任何类别行，但仍可被勾稽取到', () => {
    const p = prefill([
      leaf('1002.11', '基本户', 900, null),
      leaf('1012.01', '银行承兑汇票保证金', 100, 'bank_acceptance'),
    ])
    const map = { '1002.11': E1_UNRESTRICTED }
    const rows = resolveRestrictedRows({ prefill: p, manualMap: map })
    expect(rows).toHaveLength(1)
    expect(restrictedTotals(rows).ending).toBe(100)
    expect(unrestrictedLeaves(p, map).map((l) => l.code)).toEqual(['1002.11'])
    // 恒等式：受限 + 不受限 + 待归类 == 全部叶子
    expect(allLeavesTotal(p).ending).toBe(1000)
  })

  it('自动分类结果也能被人工改判为「不受限」', () => {
    const p = prefill([leaf('1012.01', '银行承兑汇票保证金', 100, 'bank_acceptance')])
    const map = { '1012.01': E1_UNRESTRICTED }
    expect(effectiveBucketOf(p.leaves[0], map)).toBeNull()
    expect(resolveRestrictedRows({ prefill: p, manualMap: map })).toEqual([])
  })

  it('四表新增叶子不改动已有类别行金额', () => {
    const before = prefill([leaf('1012.01', '银行承兑汇票保证金', 100, 'bank_acceptance')])
    const rowsBefore = resolveRestrictedRows({ prefill: before, manualMap: {} })
    const after = prefill([
      leaf('1012.01', '银行承兑汇票保证金', 100, 'bank_acceptance'),
      leaf('1002.77', '新开的说不清户', 700, null),
    ])
    const rowsAfter = resolveRestrictedRows({ prefill: after, manualMap: {} })
    expect(rowsAfter.find((r) => r.bucketKey === 'bank_acceptance')?.endingAmount).toBe(
      rowsBefore.find((r) => r.bucketKey === 'bank_acceptance')?.endingAmount,
    )
    expect(pendingUnclassified(after, {}).map((l) => l.code)).toEqual(['1002.77'])
  })

  it('已录入的受限原因在重新取数后保留', () => {
    const p = prefill([leaf('1012.01', '银行承兑汇票保证金', 100, 'bank_acceptance')])
    const first = resolveRestrictedRows({ prefill: p, manualMap: {} })
    first[0].reason = '开立银行承兑汇票的保证金存款'
    const second = resolveRestrictedRows({
      prefill: p,
      manualMap: {},
      existingRows: first,
    })
    expect(second[0].reason).toBe('开立银行承兑汇票的保证金存款')
  })

  it('纯手工行（不由四表叶子构成）原样保留', () => {
    const p = prefill([])
    const manual = [
      {
        id: 'restricted_custom_x_0',
        bucketKey: customBucketKey('手工类别'),
        label: '手工类别',
        openingAmount: 10,
        endingAmount: 20,
        reason: '手工',
        codes: [],
        fromFourTable: false,
      },
    ]
    const rows = resolveRestrictedRows({ prefill: p, manualMap: {}, existingRows: manual })
    expect(rows).toHaveLength(1)
    expect(rows[0].endingAmount).toBe(20)
  })

  it('行序按后端 bucketDefs 声明顺序（与源模板行序一致）', () => {
    const p = prefill([
      leaf('1012.02', '信用证保证金', 200, 'letter_of_credit'),
      leaf('1012.01', '银行承兑汇票保证金', 100, 'bank_acceptance'),
    ])
    const rows = resolveRestrictedRows({ prefill: p, manualMap: {} })
    expect(rows.map((r) => r.bucketKey)).toEqual(['bank_acceptance', 'letter_of_credit'])
  })

  it('行 id 稳定且不撞键（禁用 label 作 key）', () => {
    const p = prefill([
      leaf('1012.01', '银行承兑汇票保证金', 100, 'bank_acceptance'),
      leaf('1012.02', '信用证保证金', 200, 'letter_of_credit'),
    ])
    const ids = resolveRestrictedRows({ prefill: p, manualMap: {} }).map((r) => r.id)
    expect(new Set(ids).size).toBe(ids.length)
    expect(ids.every((i) => i.startsWith('restricted_'))).toBe(true)
  })
})

// ─── 载荷归一与持久化 ─────────────────────────────────────────────────────────

describe('载荷归一与人工归类持久化', () => {
  it('缺字段 / 脏数据不抛', () => {
    expect(normalizeRestrictedPrefill(undefined).leaves).toEqual([])
    expect(normalizeRestrictedPrefill({ leaves: 'nope' }).leaves).toEqual([])
    const p = normalizeRestrictedPrefill({
      leaves: [{ code: '1002.1', autoBucket: '' }],
      bucketDefs: [{ key: 'k' }],
    })
    expect(p.leaves[0].autoBucket).toBeNull()
    expect(p.leaves[0].closing).toBe(0)
    expect(p.bucketDefs[0].label).toBe('')
  })

  it('人工归类 map 往返无损', () => {
    const map = { '1012.01': 'other', '1002.11': E1_UNRESTRICTED }
    expect(parseManualMap(serializeManualMap(map))).toEqual(map)
  })

  it('非法持久化值返回空 map（不抛）', () => {
    expect(parseManualMap('not-json')).toEqual({})
    expect(parseManualMap('[]')).toEqual({})
    expect(parseManualMap('')).toEqual({})
    expect(parseManualMap(null)).toEqual({})
  })
})

// ─── 组件不得内联枚举字面量 ───────────────────────────────────────────────────

describe('组件字面量归零', () => {
  const DISCLOSURE = resolve(E1_ROOT, 'E1TabDisclosure.vue')

  it('反向自检：披露组件存在', () => {
    expect(existsSync(DISCLOSURE)).toBe(true)
  })

  it('反向自检：组件确实引了真源模块（否则下面的字面量断言可能只是巧合）', () => {
    const src = blankComments(readFileSync(DISCLOSURE, 'utf-8'))
    expect(src).toMatch(/from\s+'\.\.\/composables\/e1CurrencyScope'/)
  })

  it('披露组件不得内联币种字面量（应从 e1CurrencyScope 派生）', () => {
    const src = blankComments(readFileSync(DISCLOSURE, 'utf-8'))
    // 币种名一旦内联，改真源就不会同步 → 与附注外币章节口径分叉
    for (const label of ['美元', '日元', '澳元', '欧元', '人民币', '港币']) {
      expect(src, `币种字面量 ${label} 应已收敛到 e1CurrencyScope`).not.toContain(
        `'${label}'`,
      )
    }
  })

  it('披露组件不得内联主表行标签 / 外币分组字面量', () => {
    const src = blankComments(readFileSync(DISCLOSURE, 'utf-8'))
    const labels = new Set<string>([
      ...E1_FX_GROUPS.map((g) => g.label),
      ...E1_MAIN_ROWS_LISTED.map((r) => r.label),
      ...E1_MAIN_ROWS_SOE.map((r) => r.label),
    ])
    for (const label of labels) {
      expect(src, `行/分组字面量 ${label} 应已收敛到 e1DisclosureScope`).not.toContain(
        `'${label}'`,
      )
    }
  })
})

// ─── 主表行真源（源 xlsx 逐字）─────────────────────────────────────────────────

describe('披露主表行单一真源', () => {
  it('上市 8 行 / 国企 5 行，与源 xlsx R8~R15 / R8~R12 对应', () => {
    expect(E1_MAIN_ROWS_LISTED).toHaveLength(8)
    expect(E1_MAIN_ROWS_SOE).toHaveLength(5)
    expect(E1_MAIN_ROWS_LISTED.map((r) => r.sourceRef)).toEqual([
      'A8', 'A9', 'A10', 'A11', 'A12', 'A13', 'A14', 'A15',
    ])
    expect(E1_MAIN_ROWS_SOE.map((r) => r.sourceRef)).toEqual([
      'A8', 'A9', 'A10', 'A11', 'A12',
    ])
  })

  it('🔴 国企首行是「现金」，上市是「库存现金」（源模板实证差异，非笔误）', () => {
    expect(E1_MAIN_ROWS_SOE[0].label).toBe('现金')
    expect(E1_MAIN_ROWS_LISTED[0].label).toBe('库存现金')
  })

  it('🔴 境外款项行只在上市侧，且用源模板全称（改造前底稿写缩写）', () => {
    const listedOverseas = E1_MAIN_ROWS_LISTED.find((r) => r.key === 'overseas')
    expect(listedOverseas?.label).toBe('其中：存放在境外的款项总额')
    expect(listedOverseas?.isMemo).toBe(true)
    // 国企版源 xlsx R13 是括注文字，不是数据行
    expect(E1_MAIN_ROWS_SOE.some((r) => r.key === 'overseas')).toBe(false)
  })

  it('列头逐字取自源 xlsx R7（上市两空格 / 国企一空格 + 年初余额）', () => {
    expect(e1MainColumns('listed')).toEqual({
      label: '项  目',
      ending: '期末数',
      opening: '期初数',
    })
    expect(e1MainColumns('soe')).toEqual({
      label: '项 目',
      ending: '期末余额',
      opening: '年初余额',
    })
  })

  it('合计行排除自身与「其中：」备注行', () => {
    const listed = e1SummableRows('listed')
    expect(listed.map((r) => r.key)).toEqual([
      'cash', 'bank', 'finance_co', 'other_mf', 'accrued', 'digital',
    ])
    expect(e1SummableRows('soe').map((r) => r.key)).toEqual([
      'cash', 'bank', 'other_mf', 'digital',
    ])
  })

  it('🔴 跨 sheet 键必须是 `E1-adj-total-{科目码}` 形态（跨 spec 数据契约）', () => {
    // 归档 spec e1-monetary-fund-refactor：「写出 E1-adj-total-1001/1002/1012
    // = 三科目审定合计，供报表/附注引用」；wp_formula.py 亦引用。改键会断链 + 丢数据。
    const all = [...E1_MAIN_ROWS_LISTED, ...E1_MAIN_ROWS_SOE]
    const keys = all.map((r) => r.crossKey).filter(Boolean)
    expect(keys.length).toBeGreaterThan(0)
    for (const k of keys) {
      expect(k, `${k} 不符合跨 spec 契约形态`).toMatch(/^E1-adj-total-\d{4}$/)
    }
    expect(new Set(keys)).toEqual(
      new Set(['E1-adj-total-1001', 'E1-adj-total-1002', 'E1-adj-total-1012']),
    )
  })

  it('按需增设的两行无跨 sheet 键（无一级标准科目，不臆造键）', () => {
    const byKey = Object.fromEntries(E1_MAIN_ROWS_LISTED.map((r) => [r.key, r]))
    expect(byKey.finance_co.crossKey).toBe('')
    expect(byKey.digital.crossKey).toBe('')
  })

  it('行 key 在同一变体内唯一', () => {
    for (const rows of [E1_MAIN_ROWS_LISTED, E1_MAIN_ROWS_SOE]) {
      const keys = rows.map((r) => r.key)
      expect(new Set(keys).size).toBe(keys.length)
    }
  })
})
