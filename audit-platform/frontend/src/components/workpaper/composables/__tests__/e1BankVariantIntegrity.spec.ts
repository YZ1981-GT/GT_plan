/**
 * e1BankVariantIntegrity.spec.ts — E1-3 跨层金额守恒守卫（写入侧 variant × 消费侧 variant）
 *
 * **Validates: Requirements 1.3, 4.1, 4.2, 4.5**
 *
 * spec: e1-variant-recalc-and-mutation-denominator-closure (Task 2)
 * Properties: 5, 6, 14, 15
 *
 * ## 断言半径：本守卫跨四层，单层守卫查不出被守卫的缺陷
 *
 * ```
 * ① 写入侧种子/录入        buildBankSeedRowsFromAccounts(p, variantA)
 *                          buildBankSeedRows(p)          （叶子口径兜底）
 *                          addRow + updateCell           （审计师手工录入）
 *          ↓
 * ② 序列化                 serializeRows(rows, USER_FIELDS) → allResponses
 *          ↓
 * ③ 加载归一               loadFromResponses()  ← `fxRate: parseNum(r.fxRate) || 1`
 *          ↓
 * ④ 按消费侧 variant 重算   recalcRow(row, variantB)
 * ```
 *
 * 🔴 **为什么单层不够**：归档 spec `e-cycle-…completion` 有一条守卫写着
 * 「multi 版必须下发原币列，否则 recalcRow 会把本位币金额抹成 0」——
 * **措辞已准确描述了本缺陷的机制**，却没能拦住它，因为它只断言第 ① 层的输出
 * （种子行带不带原币列），断言半径停在纯函数返回值上。缺陷发生在 ①→④ 的
 * **口径不一致**：①的 rmb 形态与叶子口径都不给原币列，而④无条件由原币列派生。
 * 29 条变异 + 568 例守卫全数放行，因为没有一条把两端串起来。
 *
 * 故本守卫的最小单位是「一次跨四层的往返」，而非任何单层函数的返回值。
 */
import { describe, it, expect, vi, afterEach } from 'vitest'
import { defineComponent, h, ref, type Ref } from 'vue'
import { mount } from '@vue/test-utils'

import {
  useE1BankDetail,
  type BankDetailRow,
  type BankDetailVariant,
} from '../useE1BankDetail'
import { buildBankSeedRowsFromAccounts, normalizeAccountPrefill } from '../e1BankAccountPrefill'
import { buildBankSeedRows, normalizePrefill } from '../e1FourTablePrefill'

const STORAGE_KEY = 'E1-bank-detail-rows'
const VARIANTS: BankDetailVariant[] = ['rmb', 'multi']

type RowJson = Record<string, unknown>
type Resp = { item_id: string; conclusion: string | null; remark: string | null }
type BankDetailApi = ReturnType<typeof useE1BankDetail>

interface Harness {
  api: BankDetailApi
  variant: Ref<BankDetailVariant>
  allResponses: Ref<Map<string, Resp>>
  unmount: () => void
}

function mountBankDetail(rows: RowJson[] | null, variant: BankDetailVariant): Harness {
  const allResponses = ref(new Map<string, Resp>())
  if (rows) {
    allResponses.value.set(STORAGE_KEY, {
      item_id: STORAGE_KEY,
      conclusion: null,
      remark: JSON.stringify(rows),
    })
  }
  const variantRef = ref(variant)
  let captured: BankDetailApi | null = null
  const wrapper = mount(
    defineComponent({
      setup() {
        captured = useE1BankDetail({
          wpId: ref('wp-test'),
          projectId: ref('proj-test'),
          allResponses,
          saveImmediate: async () => {},
          debouncedSave: async () => {},
          isReadonly: ref(false),
          variant: variantRef,
        })
        return () => h('div')
      },
    }),
  )
  if (!captured) throw new Error('composable 未被捕获')
  return { api: captured, variant: variantRef, allResponses, unmount: () => wrapper.unmount() }
}

// ─── 三个写入侧来源 ──────────────────────────────────────────────────────────

/** 来源 ①：账户级种子（`tb_aux_balance` 银行账户维度）。 */
function accountSeed(variant: BankDetailVariant): RowJson[] {
  const prefill = normalizeAccountPrefill({
    accounts: {
      bank: [
        {
          account_code: '100201',
          account_no: '023900017110777',
          bank_name: '招商银行',
          opening: 848871.86,
          debit: 120000,
          credit: 641776.66,
          closing: 327095.2,
          currency: 'CNY',
          row_count: 1,
          parsed_level: 1,
          slot: 'bank',
          source: 'tb_aux_balance:银行账户:023900017110777',
        },
      ],
      other: [],
      finance_co: [],
      unassigned: [],
    },
  })
  const rows = buildBankSeedRowsFromAccounts(prefill, variant)
  if (!rows || !rows.length) throw new Error('账户级种子为空 —— 构造数据没生效')
  return rows
}

/** 来源 ②：叶子口径兜底种子（aux 侧无账户数据时走这条）。 */
function leafSeed(): RowJson[] {
  const prefill = normalizePrefill({
    bank: [
      { code: '100201', name: '银行存款/招商银行', opening: 848871.86, increase: 120000, decrease: 641776.66 },
    ],
    other: [],
  })
  const rows = buildBankSeedRows(prefill)
  if (!rows || !rows.length) throw new Error('叶子口径种子为空 —— 构造数据没生效')
  return rows
}

/**
 * 来源 ③：审计师手工录入 —— 走 `addRow` + `updateCell` 真实调用后取**落库形态**。
 *
 * 不手搓 row 对象：`updateCell` 内部会 `recalcRow(row, variant.value)`，手搓会绕过它，
 * 而「在 rmb 版录入的行被 multi 版抹零」恰恰要经过这一步。
 * 用 fake timers 推进 `scheduleSave` 的 2 秒窗口，拿到 `serializeRows` 的真实输出。
 */
function manualEntry(variant: BankDetailVariant): RowJson[] {
  vi.useFakeTimers()
  try {
    const h = mountBankDetail(null, variant)
    h.api.addRow('principal', 'institution')
    const added = h.api.rows.value[h.api.rows.value.length - 1]
    h.api.updateCell(added.id, 'bankName', '招商银行')
    h.api.updateCell(added.id, 'accountNo', '023900017110777')
    h.api.updateCell(added.id, 'opening', 848871.86)
    h.api.updateCell(added.id, 'increase', 120000)
    h.api.updateCell(added.id, 'decrease', 641776.66)
    vi.advanceTimersByTime(2100)
    const raw = h.allResponses.value.get(STORAGE_KEY)?.remark
    if (!raw) throw new Error('手工录入未产生落库形态 —— scheduleSave 没跑到')
    const parsed = JSON.parse(raw) as RowJson[]
    h.unmount()
    return parsed
  } finally {
    vi.useRealTimers()
  }
}

const SOURCES: Array<{
  name: string
  build: (v: BankDetailVariant) => RowJson[]
  /** 写入侧在该 variant 下是否产出了可派生的原币列（决定 multi 消费能否算对）。 */
  fcComplete: (v: BankDetailVariant) => boolean
  /** 写入动作本身是否会被当前实现抹零（手工录入在 multi 版下 updateCell 当场抹零）。 */
  zeroedOnWrite: (v: BankDetailVariant) => boolean
}> = [
  {
    name: '账户级种子',
    build: accountSeed,
    // multi 版对本位币账户下发 openingFc = opening（恒等事实），故 fc 齐备
    fcComplete: (v) => v === 'multi',
    zeroedOnWrite: () => false,
  },
  {
    name: '叶子口径兜底种子',
    build: () => leafSeed(),
    // 叶子行是科目级汇总，无账户无币种 ⇒ fc 恒为 0，与写入 variant 无关
    fcComplete: () => false,
    zeroedOnWrite: () => false,
  },
  {
    name: '手工录入行',
    build: manualEntry,
    fcComplete: () => false,
    // 🔴 缺陷的第三个面：multi 版下 updateCell 内的 recalcRow 当场把本位币列抹零，
    // 落库形态里存的就是 0 —— 比「切 variant 才丢」更直接，审计师填完即失。
    zeroedOnWrite: (v) => v === 'multi',
  },
]

/**
 * 该组合在**修复前**是否应当打红 —— 判据先行阶段用它核对「该红的红、该绿的绿」。
 *
 * 不用 `vb === 'multi'` 这种粗规则：账户级 multi 写入时 fc 列齐备（本位币恒等），
 * multi 消费能算对，本就该绿。首轮就是因为标记太粗而误报了一个「假绿」。
 */
function expectedRedBeforeFix(
  source: (typeof SOURCES)[number],
  va: BankDetailVariant,
  vb: BankDetailVariant,
): boolean {
  if (source.zeroedOnWrite(va)) return true
  return vb === 'multi' && !source.fcComplete(va)
}

/** 期望金额取自**构造输入**，不取自任何被测输出（防自我一致的恒真式）。 */
const EXPECT = {
  opening: 848871.86,
  increase: 120000,
  decrease: 641776.66,
  ending: 848871.86 + 120000 - 641776.66,
}

function payloadRow(h: Harness): BankDetailRow {
  const row = h.api.rows.value.find((r) => r.accountNo === '023900017110777' || r.bankName)
  if (!row) throw new Error('rows 里找不到目标行 —— 加载链路没跑通')
  return row
}

afterEach(() => {
  vi.useRealTimers()
})

// ═══════════════════════════════════════════════════════════════════════════
// Property 5：variantA × variantB 四组合 × 三来源，金额守恒
// ═══════════════════════════════════════════════════════════════════════════

describe('跨层金额守恒：写入侧 variant × 消费侧 variant（Property 5）', () => {
  for (const source of SOURCES) {
    for (const va of VARIANTS) {
      for (const vb of VARIANTS) {
        const marker = expectedRedBeforeFix(source, va, vb) ? '🔴 ' : ''
        it(`${marker}${source.name}｜${va} 写入 → ${vb} 消费：本位币金额守恒`, () => {
          const rows = source.build(va)
          const h = mountBankDetail(rows, vb)
          const row = payloadRow(h)
          expect(row.opening).toBeCloseTo(EXPECT.opening, 2)
          expect(row.increase).toBeCloseTo(EXPECT.increase, 2)
          expect(row.decrease).toBeCloseTo(EXPECT.decrease, 2)
          expect(row.ending).toBeCloseTo(EXPECT.ending, 2)
          h.unmount()
        })
      }
    }
  }
})

// ═══════════════════════════════════════════════════════════════════════════
// Property 6：叶子口径兜底路径在 multi 版下恒零（与 variant 切换无关）
// ═══════════════════════════════════════════════════════════════════════════

describe('叶子口径兜底：multi 版金额不得恒零（Property 6）', () => {
  it('🔴 叶子口径种子直接以 multi 消费即应有金额（不需要切 variant）', () => {
    const rows = leafSeed()
    // 前置事实：叶子口径无条件下发 fxRate:1 + fc 全 0（e1FourTablePrefill.mk）
    expect(rows[0].fxRate).toBe(1)
    expect(rows[0].openingFc).toBe(0)
    expect(rows[0].opening).toBeCloseTo(EXPECT.opening, 2)

    const h = mountBankDetail(rows, 'multi')
    const row = payloadRow(h)
    expect(row.opening).toBeCloseTo(EXPECT.opening, 2)
    expect(row.ending).toBeCloseTo(EXPECT.ending, 2)
    h.unmount()
  })

  it('叶子口径种子以 rmb 消费时金额正确（零回归支点）', () => {
    const h = mountBankDetail(leafSeed(), 'rmb')
    const row = payloadRow(h)
    expect(row.opening).toBeCloseTo(EXPECT.opening, 2)
    expect(row.ending).toBeCloseTo(EXPECT.ending, 2)
    h.unmount()
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 运行时 variant 切换（缺陷的原始复现路径）
// ═══════════════════════════════════════════════════════════════════════════

describe('运行时 variant 切换不得改变金额（Property 5 的动态形态）', () => {
  for (const source of SOURCES) {
    it(`🔴 ${source.name}｜rmb 挂载 → 运行时切 multi → 再切回：金额三次一致`, async () => {
      const h = mountBankDetail(source.build('rmb'), 'rmb')
      const atRmb = payloadRow(h).opening
      expect(atRmb).toBeCloseTo(EXPECT.opening, 2)

      h.variant.value = 'multi'
      await Promise.resolve()
      const atMulti = payloadRow(h).opening

      h.variant.value = 'rmb'
      await Promise.resolve()
      const backToRmb = payloadRow(h).opening

      expect(atMulti).toBeCloseTo(atRmb, 2)
      expect(backToRmb).toBeCloseTo(atRmb, 2)
      h.unmount()
    })
  }
})

// ═══════════════════════════════════════════════════════════════════════════
// 构造数据自证：判据的前提不能悄悄空转
// ═══════════════════════════════════════════════════════════════════════════

describe('构造数据自证（防判据空转）', () => {
  it('三个来源在两个写入 variant 下都真的产出了行，且行里有 opening 字段', () => {
    // 只断言结构，不断言金额 —— 「手工录入 + multi 写入」当前会被 updateCell 当场抹零，
    // 那正是被守卫的缺陷（zeroedOnWrite），自证不该因它而红，否则分不清
    // 「构造数据没生效」与「缺陷生效了」。
    for (const source of SOURCES) {
      for (const va of VARIANTS) {
        const rows = source.build(va)
        expect(rows.length, `${source.name}/${va} 行数`).toBeGreaterThan(0)
        expect(rows.some((r) => 'opening' in r), `${source.name}/${va} 应有 opening 字段`).toBe(true)
      }
    }
  })

  it('不被写入侧抹零的来源，其构造输出金额必须正确（防构造数据空转，修复前后都应绿）', () => {
    for (const source of SOURCES) {
      for (const va of VARIANTS) {
        if (source.zeroedOnWrite(va)) continue
        const rows = source.build(va)
        const amounts = rows.map((r) => Number(r.opening ?? 0))
        expect(Math.max(...amounts), `${source.name}/${va} 期初`).toBeCloseTo(EXPECT.opening, 2)
      }
    }
  })

  it('🔴 手工录入在 multi 版下被 updateCell 当场抹零（缺陷第三面，修复后本条应转为守恒）', () => {
    const rows = manualEntry('multi')
    const target = rows.find((r) => r.accountNo === '023900017110777')
    expect(target, '落库形态里应有刚录入的行').toBeTruthy()
    // 修复后这里应等于 EXPECT.opening —— 当前实现下是 0，故本条在修复前红。
    expect(Number(target?.opening)).toBeCloseTo(EXPECT.opening, 2)
  })

  it('账户级 rmb 版确实不下发原币列、multi 版确实下发（缺陷的写入侧前提）', () => {
    const rmbRow = accountSeed('rmb')[0]
    const multiRow = accountSeed('multi')[0]
    expect('fxCurrency' in rmbRow).toBe(false)
    expect('openingFc' in rmbRow).toBe(false)
    expect('fxCurrency' in multiRow).toBe(true)
    expect(multiRow.openingFc).toBeCloseTo(EXPECT.opening, 2)
  })

  it('手工录入路径真的经过了 updateCell 的 recalcRow（落库形态含本位币列）', () => {
    const rows = manualEntry('rmb')
    expect(rows.length).toBeGreaterThan(0)
    const target = rows.find((r) => r.accountNo === '023900017110777')
    expect(target, '落库形态里应有刚录入的行').toBeTruthy()
    expect(Number(target?.opening)).toBeCloseTo(EXPECT.opening, 2)
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// Task 7 / Property 11：落库形态 —— 判据必须落在序列化输出上
// ═══════════════════════════════════════════════════════════════════════════

const CROSS_SHEET_KEYS = [
  'E1-bank-detail-principal-opening-unaudited',
  'E1-bank-detail-principal-total-unaudited',
  'E1-bank-detail-institution-opening-unaudited',
  'E1-bank-detail-institution-total-unaudited',
  'E1-bank-detail-finance-opening-unaudited',
  'E1-bank-detail-finance-total-unaudited',
  'E1-bank-detail-other-opening-unaudited',
  'E1-bank-detail-other-total-unaudited',
] as const

/** 读落库形态（serializeRows 的真实输出），而不是内存 rows。 */
function persistedRows(h: Harness): RowJson[] {
  const raw = h.allResponses.value.get(STORAGE_KEY)?.remark
  if (!raw) throw new Error('尚无落库形态 —— persistToResponses 没跑到')
  return JSON.parse(raw) as RowJson[]
}

function crossSheetSnapshot(h: Harness): Record<string, string | null> {
  const out: Record<string, string | null> = {}
  for (const k of CROSS_SHEET_KEYS) out[k] = h.allResponses.value.get(k)?.remark ?? null
  return out
}

describe('落库形态：被抹零的 0 不得覆盖录入值（Property 11 / AC 3.1、3.3、3.4）', () => {
  it('在 multi 版编辑一格后落库的本位币列仍是录入值（不是派生失败的 0）', () => {
    vi.useFakeTimers()
    try {
      const h = mountBankDetail(accountSeed('rmb'), 'multi')
      const row = payloadRow(h)
      // 触发一次真实编辑 → scheduleSave → 2 秒后 persistToResponses → serializeRows
      h.api.updateCell(row.id, 'statementBalance', 1)
      vi.advanceTimersByTime(2100)

      const persisted = persistedRows(h)
      const target = persisted.find((r) => r.accountNo === '023900017110777')
      expect(target, '落库形态里应有该账户行').toBeTruthy()
      expect(Number(target?.opening)).toBeCloseTo(EXPECT.opening, 2)
      expect(Number(target?.increase)).toBeCloseTo(EXPECT.increase, 2)
      expect(Number(target?.decrease)).toBeCloseTo(EXPECT.decrease, 2)
      h.unmount()
    } finally {
      vi.useRealTimers()
    }
  })

  it('运行时切 variant 后再编辑，落库值不被 variant 派生结果污染', () => {
    vi.useFakeTimers()
    try {
      const h = mountBankDetail(leafSeed(), 'rmb')
      h.variant.value = 'multi'
      const row = payloadRow(h)
      h.api.updateCell(row.id, 'statementBalance', 2)
      vi.advanceTimersByTime(2100)

      const target = persistedRows(h).find((r) => Number(r.opening) !== 0)
      expect(target, '落库形态里应有非 0 期初的行').toBeTruthy()
      expect(Number(target?.opening)).toBeCloseTo(EXPECT.opening, 2)
      h.unmount()
    } finally {
      vi.useRealTimers()
    }
  })

  it('形态 B（外币待录入）的落库值与写入时一致，0 是写入时就是 0 而非被算成 0（AC 3.4）', () => {
    vi.useFakeTimers()
    try {
      const foreign: RowJson = {
        id: 'bank-principal-institution-acct-usd-9',
        section: 'principal',
        group: 'institution',
        bankName: '花旗银行',
        accountNo: 'USD-9',
        opening: 0,
        increase: 0,
        decrease: 0,
        adjustment: 0,
        fxCurrency: '美元',
        fxRate: 0,
        openingFc: 0,
        increaseFc: 0,
        decreaseFc: 0,
        adjustmentFc: 0,
      }
      const h = mountBankDetail([foreign], 'multi')
      h.api.updateCell('bank-principal-institution-acct-usd-9', 'statementBalance', 3)
      vi.advanceTimersByTime(2100)

      const target = persistedRows(h).find((r) => r.accountNo === 'USD-9')
      expect(target).toBeTruthy()
      expect(Number(target?.opening)).toBe(0)
      // 关键：汇率仍是 0（待录入），没被回落成 1
      expect(Number(target?.fxRate)).toBe(0)
      h.unmount()
    } finally {
      vi.useRealTimers()
    }
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// Task 7 / Property 12：跨 sheet 聚合键不得因 variant 切换而变
// ═══════════════════════════════════════════════════════════════════════════

describe('跨 sheet 聚合键在 variant 切换前后一致（Property 12 / AC 3.2、3.5）', () => {
  for (const source of SOURCES) {
    it(`${source.name}｜切 variant 前后八个聚合键取值相同`, async () => {
      const h = mountBankDetail(source.build('rmb'), 'rmb')
      const before = crossSheetSnapshot(h)
      // 前置自证：聚合键真的被写了（watch 带 immediate: true），否则本条恒真
      expect(
        Object.values(before).some((v) => v !== null),
        '聚合键一个都没写 ⇒ 判据空转',
      ).toBe(true)

      h.variant.value = 'multi'
      await Promise.resolve()
      const after = crossSheetSnapshot(h)

      expect(after).toEqual(before)
      h.unmount()
    })
  }

  it('E1-1 审定表读取的 institution 期末聚合等于本位币期末（不因 variant 改变）', async () => {
    const h = mountBankDetail(accountSeed('rmb'), 'rmb')
    const key = 'E1-bank-detail-institution-total-unaudited'
    const atRmb = Number(h.allResponses.value.get(key)?.remark ?? NaN)
    expect(atRmb).toBeCloseTo(EXPECT.ending, 2)

    h.variant.value = 'multi'
    await Promise.resolve()
    const atMulti = Number(h.allResponses.value.get(key)?.remark ?? NaN)
    expect(atMulti).toBeCloseTo(EXPECT.ending, 2)
    h.unmount()
  })
})
