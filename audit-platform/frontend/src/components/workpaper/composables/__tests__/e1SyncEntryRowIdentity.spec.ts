/**
 * e1SyncEntryRowIdentity.spec.ts — E1 sync entry 的动态行身份守卫（Property 23）
 *
 * **Validates: Requirements 6.5**
 *
 * spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 5 Task 47
 * Properties: 23（动态行身份不使用下标）
 * slice: backend/data/workpaper_sync_e_cycle_manifest_slice.json
 *
 * ## 本守卫与既有 `e1BankVariantIntegrity.spec.ts` 的分工（不是重复）
 *
 * | | 既有守卫 | 本守卫 |
 * |---|---|---|
 * | 断言对象 | **金额**（本位币六列跨 variant 守恒） | **身份**（row id 跨 variant / 跨删增稳定） |
 * | 缺陷形态 | recalcRow 由原币反推导致抹零 | id 用下标 / 绑 variant / 复用已删 id / 数据串行 |
 *
 * 两者可以互相独立地红/绿：金额守恒的守卫**不会**因为 id 换成数组下标而打红
 * （下标 0/1/2 在单次往返内自洽），而身份守卫**不会**因为汇率派生错而打红。
 * Property 23 的原文是「删除/重排/再新增后旧 row_uuid 不复用，原行数据不串到新行」——
 * 那是一条纯身份判据，必须有自己的单点。
 *
 * ## 为什么判据必须是「真跑一次」
 *
 * 全部断言都调用**真实**的 `buildBankSeedRowsFromAccounts` /
 * `buildAccountListSeedRowsFromAccounts` / `useE1BankDetail`（挂真组件、走真 watch），
 * 不做字符串扫源码：`stable_field_key` 是否真的与 variant 解耦，只能由「两次真实构造
 * 的输出逐项比对」证明；改名/改实现只要行为不变就不该打红，行为一变就必须打红。
 */
import { describe, it, expect } from 'vitest'
import { defineComponent, h, ref, nextTick, type Ref } from 'vue'
import { mount } from '@vue/test-utils'

import {
  useE1BankDetail,
  type BankDetailVariant,
} from '../useE1BankDetail'
import {
  buildBankSeedRowsFromAccounts,
  buildAccountListSeedRowsFromAccounts,
  normalizeAccountPrefill,
  type E1AccountPrefill,
} from '../e1BankAccountPrefill'

const STORAGE_KEY = 'E1-bank-detail-rows'
const VARIANTS: BankDetailVariant[] = ['rmb', 'multi']

type RowJson = Record<string, unknown>
type Resp = { item_id: string; conclusion: string | null; remark: string | null }
type BankDetailApi = ReturnType<typeof useE1BankDetail>

/**
 * 三个真实形态的银行账户（取自 `tb_aux_balance` 的 `aux_type='银行账户'` 形状）：
 * 本位币、外币、以及**同账号重复出现**（aux 里同一账号可能落在多条辅助项上）。
 */
const ACCOUNTS = [
  {
    account_code: '100201',
    account_no: '023900017110777',
    bank_name: '招商银行深圳分行',
    currency: 'CNY',
    opening: 848871.86,
    debit: 120000,
    credit: 641776.66,
    closing: 327095.2,
    slot: 'bank',
    source: 'tb_aux_balance:银行账户:023900017110777',
    parsed_level: 1,
    row_count: 1,
  },
  {
    account_code: '100202',
    account_no: 'HK-7712-0099',
    bank_name: '中国银行香港分行',
    currency: 'USD',
    opening: 100000,
    debit: 0,
    credit: 25000,
    closing: 75000,
    slot: 'bank',
    source: 'tb_aux_balance:银行账户:HK-7712-0099',
    parsed_level: 1,
    row_count: 1,
  },
  {
    account_code: '101201',
    account_no: '023900017110777',
    bank_name: '招商银行深圳分行',
    currency: 'CNY',
    opening: 5000,
    debit: 1000,
    credit: 0,
    closing: 6000,
    slot: 'other',
    source: 'tb_aux_balance:银行账户:023900017110777',
    parsed_level: 3,
    row_count: 2,
  },
]

function prefill(accounts = ACCOUNTS): E1AccountPrefill {
  return normalizeAccountPrefill({
    accounts: {
      bank: accounts.filter((a) => a.slot === 'bank'),
      other: accounts.filter((a) => a.slot === 'other'),
      finance_co: accounts.filter((a) => a.slot === 'finance_co'),
      unassigned: [],
    },
    reconcile: {},
    meta: { source: 'tb_aux_balance', account_count: accounts.length, parsed_level_dist: {} },
  })
}

function bankSeed(variant: BankDetailVariant, accounts = ACCOUNTS): RowJson[] {
  const rows = buildBankSeedRowsFromAccounts(prefill(accounts), variant)
  if (!rows || !rows.length) throw new Error('账户级银行种子为空 —— 构造数据没生效')
  return rows
}

interface Harness {
  api: BankDetailApi
  variant: Ref<BankDetailVariant>
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
          wpId: ref('wp-e1-task47'),
          projectId: ref('proj-task47'),
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
  return { api: captured, variant: variantRef, unmount: () => wrapper.unmount() }
}

const idsOf = (rows: RowJson[]): string[] => rows.map((r) => String(r.id))

// ═══════════════════════════════════════════════════════════════════════════
// 构造数据自证（防判据空转）
// ═══════════════════════════════════════════════════════════════════════════

describe('构造数据自证', () => {
  it('三个账户真的产出了三行，且覆盖本位币/外币/同账号重复三种形态', () => {
    const rows = bankSeed('multi')
    expect(rows).toHaveLength(3)
    expect(new Set(ACCOUNTS.map((a) => a.currency))).toEqual(new Set(['CNY', 'USD']))
    const dupes = ACCOUNTS.filter((a) => a.account_no === '023900017110777')
    expect(dupes.length, '必须有同账号重复形态，否则去重判据空转').toBe(2)
  })

  it('两个 variant 的字段集确实不同（身份判据的前提：variant 只影响字段集）', () => {
    const rmb = Object.keys(bankSeed('rmb')[0])
    const multi = Object.keys(bankSeed('multi')[0])
    expect(multi.length).toBeGreaterThan(rmb.length)
    for (const fcField of ['fxCurrency', 'fxRate', 'openingFc', 'increaseFc', 'decreaseFc']) {
      expect(multi, `multi 版必须有 ${fcField}`).toContain(fcField)
      expect(rmb, `rmb 版按设计不下发 ${fcField}`).not.toContain(fcField)
    }
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// Property 23 ①：行身份与 variant 解耦
// ═══════════════════════════════════════════════════════════════════════════

describe('Property 23 ①：stable field key 与 variant 解耦', () => {
  it('🔴 两个 variant 的种子 id 序列逐项相等（权威模板里 identity 列 A..D 两版相同）', () => {
    expect(idsOf(bankSeed('rmb'))).toEqual(idsOf(bankSeed('multi')))
  })

  it('🔴 两个 variant 的行数相等（variant 只影响字段集，不影响条数）', () => {
    expect(bankSeed('rmb')).toHaveLength(bankSeed('multi').length)
  })

  it('id 里不出现 variant 名（身份绑 variant 会让切表后行全部错位）', () => {
    for (const variant of VARIANTS) {
      for (const id of idsOf(bankSeed(variant))) {
        expect(id).not.toContain('rmb')
        expect(id).not.toContain('multi')
      }
    }
  })

  it('🔴 id 由账号派生：每行 id 必须含自己的账号，且不等于任何下标形态', () => {
    const rows = bankSeed('multi')
    rows.forEach((row, index) => {
      const accountNo = String(row.accountNo)
      expect(accountNo, '账号不得为空，否则身份退化').not.toBe('')
      expect(String(row.id)).toContain(accountNo)
      expect(String(row.id)).not.toBe(String(index))
      expect(String(row.id)).not.toMatch(new RegExp(`(^|[^0-9])${index}$`))
    })
  })

  it('🔴 打乱账户输入顺序后，每个账户仍拿到同一个 id（身份不随位置漂移）', () => {
    const forward = bankSeed('multi')
    const reversed = bankSeed('multi', [...ACCOUNTS].reverse())
    const keyOf = (r: RowJson) => `${r.group}|${r.accountNo}|${r.opening}`
    const forwardMap = new Map(forward.map((r) => [keyOf(r), String(r.id)]))
    const reversedMap = new Map(reversed.map((r) => [keyOf(r), String(r.id)]))
    expect(reversedMap.size).toBe(forwardMap.size)
    for (const [key, id] of forwardMap) {
      expect(reversedMap.get(key), `账户 ${key} 的 id 随输入顺序改变了`).toBe(id)
    }
  })

  it('同账号重复出现时以后缀去重，不改用下标（seed 内 id 唯一）', () => {
    const ids = idsOf(bankSeed('multi'))
    expect(new Set(ids).size, 'seed 内 id 必须唯一').toBe(ids.length)
    const dupeIds = ids.filter((id) => id.includes('023900017110777'))
    expect(dupeIds.length).toBe(2)
    expect(new Set(dupeIds).size).toBe(2)
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// Property 23 ②：种子 variant × 消费 Tab variant 串联（身份 + 金额同时保住）
// ═══════════════════════════════════════════════════════════════════════════

describe('Property 23 ②：种子的 variant 与消费它的 Tab 的 variant 串联', () => {
  for (const seedVariant of VARIANTS) {
    for (const consumeVariant of VARIANTS) {
      it(`🔴 ${seedVariant} 种子 → ${consumeVariant} Tab 消费：行 id 集合逐项保留`, () => {
        const seeded = bankSeed(seedVariant)
        const h = mountBankDetail(seeded, consumeVariant)
        try {
          const loaded = h.api.rows.value.map((r) => r.id)
          expect(loaded).toEqual(idsOf(seeded))
        } finally {
          h.unmount()
        }
      })
    }
  }

  it('🔴 rmb 种子被 multi Tab 消费时，本位币账户的身份与金额同时保住（抹零回归支点）', () => {
    const seeded = bankSeed('rmb')
    const h = mountBankDetail(seeded, 'multi')
    try {
      const target = h.api.rows.value.find((r) => r.accountNo === '023900017110777' && r.group === 'institution')
      expect(target, 'rmb 种子的本位币账户行在 multi 消费下丢失了').toBeTruthy()
      expect(target!.id).toBe(String(seeded[0].id))
      expect(target!.opening).toBeCloseTo(848871.86, 2)
      expect(target!.ending).toBeCloseTo(327095.2, 2)
    } finally {
      h.unmount()
    }
  })

  it('🔴 运行时切 variant 后行 id 不变（切表不得重建身份）', async () => {
    const h = mountBankDetail(bankSeed('rmb'), 'rmb')
    try {
      const before = h.api.rows.value.map((r) => r.id)
      h.variant.value = 'multi'
      await nextTick()
      expect(h.api.rows.value.map((r) => r.id)).toEqual(before)
      h.variant.value = 'rmb'
      await nextTick()
      expect(h.api.rows.value.map((r) => r.id)).toEqual(before)
    } finally {
      h.unmount()
    }
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// Property 23 ③：删除 / 重排 / 再新增 —— 旧 id 不复用，数据不串行
// ═══════════════════════════════════════════════════════════════════════════

describe('Property 23 ③：删除后再新增不复用旧 id，原行数据不串到新行', () => {
  it('🔴 删中间一行再新增，新行 id 不等于任何已删 id', () => {
    const h = mountBankDetail(bankSeed('multi'), 'multi')
    try {
      const original = h.api.rows.value.map((r) => r.id)
      const removed = original[1]
      h.api.removeRow(removed)
      expect(h.api.rows.value.map((r) => r.id)).not.toContain(removed)
      h.api.addRow('principal', 'institution')
      const after = h.api.rows.value.map((r) => r.id)
      expect(after).not.toContain(removed)
      const fresh = after.filter((id) => !original.includes(id))
      expect(fresh, '新增应恰好产生一个新 id').toHaveLength(1)
      expect(fresh[0]).not.toBe(removed)
    } finally {
      h.unmount()
    }
  })

  it('🔴 删除+新增后，存活行的金额与账号没有串到别的行', () => {
    const h = mountBankDetail(bankSeed('multi'), 'multi')
    try {
      const snapshot = new Map(
        h.api.rows.value.map((r) => [r.id, `${r.accountNo}|${r.opening}|${r.bankName}`]),
      )
      const removed = h.api.rows.value[1].id
      h.api.removeRow(removed)
      h.api.addRow('principal', 'institution')
      for (const row of h.api.rows.value) {
        if (!snapshot.has(row.id)) continue
        expect(`${row.accountNo}|${row.opening}|${row.bankName}`).toBe(snapshot.get(row.id))
      }
    } finally {
      h.unmount()
    }
  })

  it('🔴 新增行的 id 不是「当前行数」这类下标派生值', () => {
    const h = mountBankDetail(bankSeed('multi'), 'multi')
    try {
      const countBefore = h.api.rows.value.length
      h.api.addRow('principal', 'other')
      const added = h.api.rows.value[h.api.rows.value.length - 1]
      expect(String(added.id)).not.toBe(String(countBefore))
      expect(String(added.id)).not.toMatch(/(^|[^0-9])(3|4)$/)
      expect(String(added.id).length, '身份必须足够宽以避免碰撞').toBeGreaterThan(10)
    } finally {
      h.unmount()
    }
  })

  it('🔴 updateCell 按 id 定位而非下标：删首行后改末行仍改到正确的行', () => {
    const h = mountBankDetail(bankSeed('multi'), 'multi')
    try {
      const ids = h.api.rows.value.map((r) => r.id)
      h.api.removeRow(ids[0])
      const targetId = ids[ids.length - 1]
      h.api.updateCell(targetId, 'statementBalance', 12345.67)
      const target = h.api.rows.value.find((r) => r.id === targetId)
      expect(target!.statementBalance).toBeCloseTo(12345.67, 2)
      for (const row of h.api.rows.value) {
        if (row.id === targetId) continue
        expect(row.statementBalance, `行 ${row.id} 被误改`).toBe(0)
      }
    } finally {
      h.unmount()
    }
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// Property 23 ④：E1-10 账户清单同一身份口径
// ═══════════════════════════════════════════════════════════════════════════

describe('Property 23 ④：E1-10 账户清单行身份', () => {
  it('🔴 id 由账号派生（acct-a-{账号}），不用下标', () => {
    const rows = buildAccountListSeedRowsFromAccounts(prefill())
    expect(rows).toBeTruthy()
    rows!.forEach((row, index) => {
      expect(String(row.id)).toContain(String(row.accountNo))
      expect(String(row.id)).not.toBe(String(index))
    })
  })

  it('🔴 与 E1-3 不撞键（两张表的行 id 命名空间必须分开）', () => {
    const bankIds = new Set(idsOf(bankSeed('multi')))
    const listIds = buildAccountListSeedRowsFromAccounts(prefill())!.map((r) => String(r.id))
    for (const id of listIds) {
      expect(bankIds.has(id), `E1-10 的 ${id} 与 E1-3 撞键`).toBe(false)
    }
  })

  it('同账号重复以后缀去重，且零余额账户保留（完整性核对不得丢账户）', () => {
    const zeroAccount = {
      ...ACCOUNTS[0],
      account_code: '100299',
      account_no: 'NEW-0000-0001',
      opening: 0,
      debit: 0,
      credit: 0,
      closing: 0,
    }
    const rows = buildAccountListSeedRowsFromAccounts(prefill([...ACCOUNTS, zeroAccount]))!
    const ids = rows.map((r) => String(r.id))
    expect(new Set(ids).size).toBe(ids.length)
    expect(ids.some((id) => id.includes('NEW-0000-0001')), '零余额账户被丢弃了').toBe(true)
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 反向自检：把身份换成下标，本文件的判据必须不成立
// ═══════════════════════════════════════════════════════════════════════════

describe('反向自检：下标身份必须被判据拒绝', () => {
  it('把 id 换成数组下标后，「id 含账号」与「跨 variant 逐项相等」不再同时成立', () => {
    const indexed = bankSeed('multi').map((row, index) => ({ ...row, id: String(index) }))
    const violates = indexed.some((row, index) => !String(row.id).includes(String(row.accountNo)) || String(row.id) === String(index))
    expect(violates, '反例应当违反身份判据').toBe(true)
  })

  it('把 id 绑上 variant 后，跨 variant 的 id 序列不再相等', () => {
    const withVariant = (variant: BankDetailVariant) =>
      bankSeed(variant).map((row) => ({ ...row, id: `${row.id}-${variant}` }))
    expect(idsOf(withVariant('rmb'))).not.toEqual(idsOf(withVariant('multi')))
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// BP-4 characterization：E1 的 OO sheet 名走 G1 命名空间（**实况，非期望**）
// ═══════════════════════════════════════════════════════════════════════════
//
// 🔴 读法警告：本节断言的是**当前缺陷行为**，不是想要的行为。它存在的唯一理由是给
// `workpaper_sync_e_cycle_manifest_slice.json` 的 `blocking_preconditions[BP-4]` 一个
// 可执行对侧 —— 缺陷被修好时本节会打红，那时**必须同时**把 BP-4 的
// `status` 从 `REGISTERED_NOT_FIXED` 改掉，而不是把本节删掉了事。
// 反过来，缺陷若在未登记的情况下扩大，本节也会打红。

import { resolveG1SheetLabel, extractG1SheetCode } from '../g1SheetLabels'

describe('BP-4 characterization：E1 复用 G1 sheet 解析器（修好后本节应打红并更新 slice）', () => {
  it('实况：extractG1SheetCode 把 E1-5「调整分录汇总」归一进 G1 命名空间（返回 G1-3）', () => {
    expect(
      extractG1SheetCode('调整分录汇总E1-5'),
      'BP-4 已修好？请同步更新 e_cycle_manifest_slice.json 的 blocking_preconditions[BP-4]',
    ).toBe('G1-3')
  })

  it('实况：availableSheets 传空且无 fallbackSheetName 时，E1 编码拿不到真实 sheet 名', () => {
    // 宿主 GtE1MonetaryFund.vue 把 availableSheets 传成 computed(() => [])，
    // 于是 resolveG1SheetLabel 的 availableSheets 分支整段跳过。
    expect(
      resolveG1SheetLabel('E1-3', [], undefined),
      'BP-4 已修好？请同步更新 slice',
    ).toBe('E1-3')
    expect(resolveG1SheetLabel('E1-10', [], undefined)).toBe('E1-10')
  })

  it('实况：E1 编码不在 G1 sheet label 映射里，只能靠宿主 sheetName 兜底', () => {
    const real = '银行存款及其他货币资金明细表(人民币及外币)E1-3'
    expect(resolveG1SheetLabel('E1-3', [], real)).toBe(real)
    expect(resolveG1SheetLabel('G1-1', [], undefined)).toBe('审定表G1-1')
  })

  it('实况：G1 编码能拿到 G1 的真实表名 —— 证明解析器本身没坏，坏的是被 E1 复用', () => {
    expect(resolveG1SheetLabel('G1A', [], undefined)).toBe('交易性金融资产实质性程序表G1A')
    expect(extractG1SheetCode('审定表G1-1')).toBe('G1-1')
  })
})
