/**
 * e1BankDetailFxForm.spec.ts — E1-3 三形态判定与 fxRate 三态守卫
 *
 * **Validates: Requirements 1.1, 1.2, 1.6, 2.1, 2.2, 2.3**
 *
 * spec: e1-variant-recalc-and-mutation-denominator-closure (Task 1)
 * Properties: 1, 2, 3, 4, 8, 9, 10, 13
 *
 * ## 断言半径（为什么不只测纯函数）
 *
 * 被守卫的缺陷是「写入侧只给本位币列、消费侧无条件由原币列派生」——
 * `recalcRow` 单看没错，`buildBankSeedRowsFromAccounts` 单看也没错，错在**跨层口径**。
 * 归档 spec `e-cycle-…completion` 的 29 条变异 + 568 例守卫全没拦住它，正因为
 * 所有断言都停在纯函数返回值上。
 *
 * 故本守卫的观察窗口是 **`useE1BankDetail` composable 的 `rows`** —— 它是
 * 「行 JSON → `loadFromResponses` → `recalcRow(variant)`」这条真实链路的出口。
 * `recalcRow` 本身未导出，也**不应**为了测试而导出：导出它只能测到它自己，
 * 测不到 `loadFromResponses` 的字段归一（`fxRate: parseNum(r.fxRate) || 1` 那行
 * 恰恰是缺陷的一半）。
 *
 * ## 三形态（design.md §Architecture）
 *
 * | 形态 | 条件 | multi 版应有行为 |
 * |---|---|---|
 * | A 本位币恒等 | fc 列全 0 且 fxCurrency 是本位币 | 保留本位币六列；原币小计镜像本位币 |
 * | B 外币待录入 | fc 列全 0 且 fxCurrency 非本位币 | 本位币列 0；fxRate 保持 0；note 带提示 |
 * | C 原币权威 | fc 列任一非 0 | 由 原币 × fxRate 派生（现状不变） |
 */
import { describe, it, expect } from 'vitest'
import { defineComponent, h, ref, type Ref } from 'vue'
import { mount } from '@vue/test-utils'
import fc from 'fast-check'

import {
  useE1BankDetail,
  type BankDetailRow,
  type BankDetailVariant,
} from '../useE1BankDetail'
import { calcCashBalance } from '../useE1FormulaEngine'

const STORAGE_KEY = 'E1-bank-detail-rows'

type RowJson = Record<string, unknown>
type BankDetailApi = ReturnType<typeof useE1BankDetail>

interface Harness {
  api: BankDetailApi
  variant: Ref<BankDetailVariant>
  allResponses: Ref<Map<string, { item_id: string; conclusion: string | null; remark: string | null }>>
  saved: Array<Array<{ item_id: string; remark?: string | null }>>
  unmount: () => void
}

/**
 * 在真实组件上下文里挂载 composable。
 *
 * 必须走 `mount` 而不是裸调用：composable 内部有 `watch(variant, ...)` 与
 * `onBeforeUnmount`，裸调用时后者会脱离组件实例（Vue 只 warn 不抛），而
 * variant 切换的重算恰恰依赖 watch 真实触发。
 */
function mountBankDetail(rows: RowJson[] | null, variant: BankDetailVariant): Harness {
  const allResponses = ref(new Map()) as Harness['allResponses']
  if (rows) {
    allResponses.value.set(STORAGE_KEY, {
      item_id: STORAGE_KEY,
      conclusion: null,
      remark: JSON.stringify(rows),
    })
  }
  const variantRef = ref(variant)
  const saved: Harness['saved'] = []
  let captured: BankDetailApi | null = null

  const wrapper = mount(
    defineComponent({
      setup() {
        captured = useE1BankDetail({
          wpId: ref('wp-test'),
          projectId: ref('proj-test'),
          allResponses,
          saveImmediate: async (items) => {
            saved.push(items as Harness['saved'][number])
          },
          debouncedSave: async () => {},
          isReadonly: ref(false),
          variant: variantRef,
        })
        return () => h('div')
      },
    }),
  )

  if (!captured) throw new Error('composable 未被捕获 —— setup 未执行')
  return {
    api: captured,
    variant: variantRef,
    allResponses,
    saved,
    unmount: () => wrapper.unmount(),
  }
}

/** 只带本位币列的行（形态 A 的典型形态：rmb 版种子 / rmb 版手工录入）。 */
function baseOnlyRow(over: RowJson = {}): RowJson {
  return {
    id: 'bank-principal-institution-acct-023900017110777',
    section: 'principal',
    group: 'institution',
    bankName: '招商银行',
    accountNo: '023900017110777',
    opening: 848871.86,
    increase: 120000,
    decrease: 641776.66,
    adjustment: 0,
    ...over,
  }
}

/** 带真实原币列的行（形态 C）。 */
function fcAuthoritativeRow(over: RowJson = {}): RowJson {
  return {
    ...baseOnlyRow(),
    id: 'bank-principal-institution-acct-usd-001',
    fxCurrency: '美元',
    fxRate: 7.2,
    openingFc: 1000,
    increaseFc: 500,
    decreaseFc: 200,
    adjustmentFc: 0,
    ...over,
  }
}

function firstRow(h: Harness): BankDetailRow {
  const row = h.api.rows.value.find((r) => r.accountNo || r.bankName)
  if (!row) throw new Error('rows 为空 —— 加载链路没跑通')
  return row
}

// ═══════════════════════════════════════════════════════════════════════════
// Property 1 / 13：形态 A —— 本位币金额必须保留
// ═══════════════════════════════════════════════════════════════════════════

describe('形态 A 本位币恒等：multi 版不得抹掉本位币金额（Property 1）', () => {
  it('🔴 只有本位币列的行在 multi 版下六列与输入一致', () => {
    const h = mountBankDetail([baseOnlyRow()], 'multi')
    const row = firstRow(h)
    expect(row.opening).toBeCloseTo(848871.86, 2)
    expect(row.increase).toBeCloseTo(120000, 2)
    expect(row.decrease).toBeCloseTo(641776.66, 2)
    expect(row.ending).toBeCloseTo(calcCashBalance(848871.86, 120000, 641776.66), 2)
    expect(row.audited).toBeCloseTo(row.ending + row.adjustment, 2)
    h.unmount()
  })

  it('🔴 形态 A 下原币小计列镜像本位币，不出现「本位币有值而原币为 0」（Property 13）', () => {
    const h = mountBankDetail([baseOnlyRow()], 'multi')
    const row = firstRow(h)
    // 🔴 期望值必须取自**输入的原始数**，不得写成 calcCashBalance(row.opening, ...)：
    // 缺陷会把 row.opening 抹成 0，用它算期望值会让左右两边都是 0 ⇒ 恒真式（假绿）。
    // 首轮实测正是这样：该条标了预期红却 passed。
    const expectedFc = calcCashBalance(848871.86, 120000, 641776.66)
    expect(row.endingFc).toBeCloseTo(expectedFc, 2)
    expect(row.auditedFc).toBeCloseTo(expectedFc + row.adjustmentFc, 2)
    h.unmount()
  })

  it('🔴 variant 由 rmb 切到 multi 时金额不变（缺陷的原始复现路径）', async () => {
    const h = mountBankDetail([baseOnlyRow()], 'rmb')
    const before = firstRow(h)
    const openingBefore = before.opening
    const endingBefore = before.ending
    expect(openingBefore).toBeCloseTo(848871.86, 2)

    h.variant.value = 'multi'
    await Promise.resolve()

    const after = firstRow(h)
    expect(after.opening).toBeCloseTo(openingBefore, 2)
    expect(after.ending).toBeCloseTo(endingBefore, 2)
    h.unmount()
  })

  it('🔴 叶子口径兜底种子（fxRate:1 + fc 全 0）在 multi 版下金额非 0（Property 6 的单点形态）', () => {
    // e1FourTablePrefill.buildBankSeedRows 的 mk() 无条件下发这套字段
    const leafSeed = baseOnlyRow({
      fxCurrency: '人民币',
      fxRate: 1,
      openingFc: 0,
      increaseFc: 0,
      decreaseFc: 0,
      adjustmentFc: 0,
    })
    const h = mountBankDetail([leafSeed], 'multi')
    const row = firstRow(h)
    expect(row.opening).toBeGreaterThan(0)
    expect(row.ending).toBeGreaterThan(0)
    h.unmount()
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// Property 2：形态 B —— 外币待录入不得被臆造汇率
// ═══════════════════════════════════════════════════════════════════════════

describe('形态 B 外币待录入：不得臆造汇率（Property 2）', () => {
  it('🔴 显式 fxRate:0 的外币行加载后仍为 0（Property 8 / AC 2.2）', () => {
    const h = mountBankDetail(
      [baseOnlyRow({ fxCurrency: '美元', fxRate: 0, openingFc: 0, increaseFc: 0, decreaseFc: 0 })],
      'multi',
    )
    expect(firstRow(h).fxRate).toBe(0)
    h.unmount()
  })

  it('外币且汇率未录入时本位币列为 0（Property 34 不得被本次修复破坏）', () => {
    const h = mountBankDetail(
      [
        baseOnlyRow({
          fxCurrency: '美元',
          fxRate: 0,
          openingFc: 0,
          increaseFc: 0,
          decreaseFc: 0,
          adjustmentFc: 0,
        }),
      ],
      'multi',
    )
    const row = firstRow(h)
    expect(row.opening).toBe(0)
    expect(row.ending).toBe(0)
    expect(row.audited).toBe(0)
    h.unmount()
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// Property 3 / 4：零回归支点
// ═══════════════════════════════════════════════════════════════════════════

describe('零回归：形态 C 与 rmb 分支行为不变（Property 3 / 4）', () => {
  it('形态 C（fc 有值）在 multi 版下仍由 原币 × 汇率 派生', () => {
    const h = mountBankDetail([fcAuthoritativeRow()], 'multi')
    const row = firstRow(h)
    // 基线值来自修复前实测复算而非预期：1000×7.2 / 500×7.2 / 200×7.2
    expect(row.opening).toBeCloseTo(7200, 2)
    expect(row.increase).toBeCloseTo(3600, 2)
    expect(row.decrease).toBeCloseTo(1440, 2)
    expect(row.endingFc).toBeCloseTo(calcCashBalance(1000, 500, 200), 2)
    expect(row.ending).toBeCloseTo(1300 * 7.2, 2)
    h.unmount()
  })

  it('rmb 分支：本位币列即权威，与修复前逐字相同', () => {
    const h = mountBankDetail([baseOnlyRow()], 'rmb')
    const row = firstRow(h)
    expect(row.opening).toBeCloseTo(848871.86, 2)
    expect(row.ending).toBeCloseTo(327095.2, 2)
    expect(row.audited).toBeCloseTo(327095.2, 2)
    h.unmount()
  })

  it('rmb 分支不因 fc 列存在而改变本位币结果（形态判定只作用于 multi）', () => {
    const h = mountBankDetail([fcAuthoritativeRow()], 'rmb')
    const row = firstRow(h)
    // rmb 分支用 opening/increase/decrease，不看 fc
    expect(row.opening).toBeCloseTo(848871.86, 2)
    expect(row.ending).toBeCloseTo(327095.2, 2)
    h.unmount()
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// Property 8 / 9 / 10：fxRate 三态与历史数据兼容
// ═══════════════════════════════════════════════════════════════════════════

describe('fxRate 三态不得被压扁（Property 8 / 9）', () => {
  it('缺失 fxRate 字段 → 回落 1（本位币恒等的默认）', () => {
    const h = mountBankDetail([baseOnlyRow()], 'multi')
    expect(firstRow(h).fxRate).toBe(1)
    h.unmount()
  })

  it('🔴 显式 0 与缺失必须可区分（当前 `|| 1` 把两者压成同一态）', () => {
    const missing = mountBankDetail([baseOnlyRow()], 'multi')
    const explicitZero = mountBankDetail(
      [baseOnlyRow({ fxCurrency: '美元', fxRate: 0 })],
      'multi',
    )
    expect(firstRow(missing).fxRate).toBe(1)
    expect(firstRow(explicitZero).fxRate).toBe(0)
    expect(firstRow(missing).fxRate).not.toBe(firstRow(explicitZero).fxRate)
    missing.unmount()
    explicitZero.unmount()
  })

  it('真实汇率原样保留', () => {
    const h = mountBankDetail([baseOnlyRow({ fxCurrency: '美元', fxRate: 7.18 })], 'multi')
    expect(firstRow(h).fxRate).toBeCloseTo(7.18, 4)
    h.unmount()
  })

  it('🔴 历史落库数据（无 fxRate 键）在 multi 版下本位币列非 0（Property 10 / AC 2.6）', () => {
    const legacy: RowJson = {
      id: 'legacy-row-1',
      section: 'principal',
      group: 'institution',
      bankName: '中国银行',
      accountNo: '111645582188',
      opening: 500000,
      increase: 0,
      decrease: 0,
      adjustment: 0,
    }
    expect('fxRate' in legacy).toBe(false)
    const h = mountBankDetail([legacy], 'multi')
    expect(firstRow(h).opening).toBeCloseTo(500000, 2)
    h.unmount()
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// classifyFxForm：形态判定纯函数（Property 1 / 2 / 3）
// ═══════════════════════════════════════════════════════════════════════════

describe('classifyFxForm 形态判定纯函数', () => {
  /** 动态 import：函数尚不存在时只让本组红，不至于整个文件 collect error。 */
  async function loadClassify() {
    const mod = (await import('../useE1BankDetail')) as Record<string, unknown>
    const fn = mod.classifyFxForm
    expect(typeof fn).toBe('function')
    return fn as (row: Record<string, unknown>) => string
  }

  it('🔴 必须导出 classifyFxForm（形态判定的单一真源）', async () => {
    await loadClassify()
  })

  it('🔴 fc 列全 0 且本位币 → base-identity', async () => {
    const classify = await loadClassify()
    expect(
      classify({
        openingFc: 0,
        increaseFc: 0,
        decreaseFc: 0,
        adjustmentFc: 0,
        fxCurrency: '人民币',
      }),
    ).toBe('base-identity')
  })

  it('🔴 fc 列全 0 且非本位币 → foreign-pending', async () => {
    const classify = await loadClassify()
    expect(
      classify({
        openingFc: 0,
        increaseFc: 0,
        decreaseFc: 0,
        adjustmentFc: 0,
        fxCurrency: '美元',
      }),
    ).toBe('foreign-pending')
  })

  it('🔴 fc 列任一非 0 → fc-authoritative（不看币种）', async () => {
    const classify = await loadClassify()
    for (const field of ['openingFc', 'increaseFc', 'decreaseFc', 'adjustmentFc']) {
      const row: Record<string, unknown> = {
        openingFc: 0,
        increaseFc: 0,
        decreaseFc: 0,
        adjustmentFc: 0,
        fxCurrency: '人民币',
      }
      row[field] = 1
      expect(classify(row)).toBe('fc-authoritative')
    }
  })

  it('🔴 空 fxCurrency 按本位币处理（与 isBaseCurrency 单一真源一致）', async () => {
    const classify = await loadClassify()
    expect(
      classify({ openingFc: 0, increaseFc: 0, decreaseFc: 0, adjustmentFc: 0, fxCurrency: '' }),
    ).toBe('base-identity')
  })

  it('🔴 PBT：fc 列任一非 0 时恒为 fc-authoritative（不受币种影响）', async () => {
    const classify = await loadClassify()
    fc.assert(
      fc.property(
        fc.record({
          openingFc: fc.double({ min: -1e6, max: 1e6, noNaN: true }),
          increaseFc: fc.double({ min: -1e6, max: 1e6, noNaN: true }),
          decreaseFc: fc.double({ min: -1e6, max: 1e6, noNaN: true }),
          adjustmentFc: fc.double({ min: -1e6, max: 1e6, noNaN: true }),
          fxCurrency: fc.constantFrom('人民币', '美元', 'CNY', 'USD', ''),
        }),
        (row) => {
          const anyNonZero =
            row.openingFc !== 0 ||
            row.increaseFc !== 0 ||
            row.decreaseFc !== 0 ||
            row.adjustmentFc !== 0
          if (!anyNonZero) return true
          return classify(row as unknown as Record<string, unknown>) === 'fc-authoritative'
        },
      ),
      { numRuns: 200 },
    )
  })
})
