/**
 * e1BankAccountPrefill 守卫（Task 7）
 *
 * spec: .kiro/specs/e-cycle-extraction-formula-and-disclosure-completion/
 * Requirements 1.7, 1.9, 1.10, 2.3, 2.4, 11.3 / Property 6, 7, 34
 *
 * 判据分三层：
 * - **契约层**：归一不抛 / 缺字段按空 / 键集与后端 `as_dict()` 逐字一致
 * - **不撞键层**（Property 7）：账户级 id 前缀与叶子口径 `-ft-` 集合无交集
 * - **口径层**：原币不反推（Property 34）/ E1-10 保留零余额（Property 6）/
 *   variant 分流只改字段集不改条数 / `finance_co → finance` 组
 *
 * 🔴 两条反向自检对应本模块落地时实测到的真实风险：
 * - `multi` 版若不下发原币列，`useE1BankDetail.recalcRow` 会把本位币金额
 *   由「原币 × 汇率」派生成 0（复现该行为时必须打红）
 * - 字段集必须是 `USER_FIELDS` 的子集（多给的键在序列化时被丢弃 = 静默失效）
 */

import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

import {
  ACCOUNT_SLOT_ORDER,
  ACCOUNT_SLOT_TO_GROUP,
  FOREIGN_FC_HINT,
  assignedAccounts,
  buildAccountListSeedRowsFromAccounts,
  buildBankSeedRowsFromAccounts,
  buildDigitalSeedRows,
  currencyLabelOf,
  hasAccountData,
  isBaseCurrency,
  normalizeAccountPrefill,
  type E1AccountRow,
} from '../e1BankAccountPrefill'
import {
  buildAccountListSeedRows,
  buildBankSeedRows,
  normalizePrefill,
} from '../e1FourTablePrefill'

// ─────────────────────────── 仓库根定位（双哨兵）────────────────────────────

function repoRoot(): string {
  let dir = __dirname
  for (let i = 0; i < 12; i += 1) {
    const a = resolve(dir, 'backend/app/services/four_table/e1_bank_accounts.py')
    const b = resolve(dir, 'audit-platform/frontend/package.json')
    try {
      readFileSync(a)
      readFileSync(b)
      return dir
    } catch {
      dir = resolve(dir, '..')
    }
  }
  throw new Error('定位不到仓库根（双哨兵均未命中）')
}

const ROOT = repoRoot()

function readSrc(rel: string): string {
  return readFileSync(resolve(ROOT, rel), 'utf-8').replace(/\r\n/g, '\n')
}

/** 从 `useE1BankDetail.ts` 抽 `USER_FIELDS` 数组（跨模块交叉锁死，不抄第二份）。 */
function bankUserFields(): string[] {
  const src = readSrc(
    'audit-platform/frontend/src/components/workpaper/composables/useE1BankDetail.ts',
  )
  const i = src.indexOf('const USER_FIELDS')
  expect(i, 'useE1BankDetail 里找不到 USER_FIELDS').toBeGreaterThan(0)
  const lo = src.indexOf('[', i)
  const hi = src.indexOf(']', lo)
  expect(hi).toBeGreaterThan(lo)
  return [...src.slice(lo, hi).matchAll(/'([^']+)'/g)].map(m => m[1])
}

/** 从 `E1TabDigitalCurrency.vue` 抽 `USER_FIELDS` 与 `STORAGE_KEY`。 */
function digitalContract(): { fields: string[]; storageKey: string } {
  const src = readSrc(
    'audit-platform/frontend/src/components/workpaper/e1/E1TabDigitalCurrency.vue',
  )
  const i = src.indexOf('const USER_FIELDS')
  expect(i, 'E1TabDigitalCurrency 里找不到 USER_FIELDS').toBeGreaterThan(0)
  const lo = src.indexOf('[', i)
  const hi = src.indexOf(']', lo)
  const fields = [...src.slice(lo, hi).matchAll(/'([^']+)'/g)].map(m => m[1])
  const km = src.match(/const STORAGE_KEY\s*=\s*'([^']+)'/)
  expect(km, 'E1TabDigitalCurrency 里找不到 STORAGE_KEY').toBeTruthy()
  return { fields, storageKey: km![1] }
}

// ─────────────────────────── 样本 ────────────────────────────────────────────

function acct(over: Partial<E1AccountRow> = {}): E1AccountRow {
  return {
    account_code: '1002',
    account_no: '1207014210004455',
    bank_name: '上海浦东发展银行',
    currency: 'CNY',
    opening: 1000,
    debit: 300,
    credit: 200,
    closing: 1100,
    slot: 'bank',
    source: 'tb_aux_balance',
    parsed_level: 1,
    row_count: 1,
    ...over,
  }
}

function prefill(over: Record<string, unknown> = {}) {
  return normalizeAccountPrefill({
    accounts: {
      bank: [acct()],
      other: [acct({ account_code: '1012', account_no: 'ALIPAY-01', slot: 'other' })],
      finance_co: [
        acct({ account_code: '1002.99', account_no: 'FIN-01', slot: 'finance_co' }),
      ],
      unassigned: [],
    },
    reconcile: { bank: { account_sum: 1100, leaf_sum: 1100, diff: 0, ok: true } },
    meta: { source: 'tb_aux_balance', account_count: 3, parsed_level_dist: { '1': 3 } },
    ...over,
  })
}

// ═══════════════════════ 契约层 ═════════════════════════════════════════════

describe('normalizeAccountPrefill 契约（Requirements 1.7）', () => {
  it('缺字段一律按空处理且不抛', () => {
    for (const raw of [undefined, null, {}, 42, 'x', [], { accounts: null }]) {
      const p = normalizeAccountPrefill(raw)
      expect(p.accounts.bank).toEqual([])
      expect(p.accounts.other).toEqual([])
      expect(p.accounts.finance_co).toEqual([])
      expect(p.accounts.unassigned).toEqual([])
      expect(p.reconcile).toEqual({})
      expect(p.meta.account_count).toBe(0)
      expect(hasAccountData(p)).toBe(false)
    }
  })

  it('行键集与后端 BankAccountRow.as_dict() 逐字一致（跨前后端交叉锁死）', () => {
    const py = readSrc('backend/app/services/four_table/e1_bank_accounts.py')
    const i = py.indexOf('def as_dict')
    expect(i).toBeGreaterThan(0)
    const body = py.slice(i, py.indexOf('\n\ndef ', i))
    const backendKeys = [...body.matchAll(/"([a-z_]+)":/g)].map(m => m[1])
    expect(backendKeys.length, 'as_dict 抽不出键（正则失效）').toBeGreaterThan(8)
    const feKeys = Object.keys(acct())
    expect([...feKeys].sort()).toEqual([...backendKeys].sort())
  })

  it('非法数值归一为 0、slot 缺失为 null、parsed_level 缺失回落 3', () => {
    const p = normalizeAccountPrefill({
      accounts: { bank: [{ opening: 'abc', closing: null }] },
    })
    const r = p.accounts.bank[0]
    expect(r.opening).toBe(0)
    expect(r.closing).toBe(0)
    expect(r.slot).toBeNull()
    expect(r.parsed_level).toBe(3)
    expect(r.row_count).toBe(1)
  })

  it('reconcile 的 ok 只认布尔 true（防真值化把 "false" 当通过）', () => {
    const p = normalizeAccountPrefill({
      reconcile: { bank: { diff: 5, ok: 'false' }, other: { diff: 0, ok: true } },
    })
    expect(p.reconcile.bank.ok).toBe(false)
    expect(p.reconcile.bank.diff).toBe(5)
    expect(p.reconcile.other.ok).toBe(true)
  })

  it('assignedAccounts 不含 unassigned，且按 ACCOUNT_SLOT_ORDER 展开', () => {
    const p = prefill({
      accounts: {
        bank: [acct()],
        other: [acct({ account_no: 'O1' })],
        finance_co: [acct({ account_no: 'F1' })],
        unassigned: [acct({ account_no: 'U1' })],
      },
    })
    const got = assignedAccounts(p)
    expect(got.map(x => x.slot)).toEqual(['bank', 'other', 'finance_co'])
    expect(got.some(x => x.row.account_no === 'U1')).toBe(false)
    // unassigned 单独存在时仍算「有账户级数据」（要暴露给溯源面板）
    const onlyUnassigned = normalizeAccountPrefill({
      accounts: { unassigned: [acct()] },
    })
    expect(hasAccountData(onlyUnassigned)).toBe(true)
  })

  it('币种判定：空串/CNY/RMB/人民币 都是本位币', () => {
    for (const c of ['', 'CNY', 'cny', 'RMB', '人民币', '  ']) {
      expect(isBaseCurrency(c), c).toBe(true)
      expect(currencyLabelOf(c)).toBe('人民币')
    }
    for (const c of ['USD', 'HKD', 'EUR']) {
      expect(isBaseCurrency(c), c).toBe(false)
      expect(currencyLabelOf(c)).toBe(c)
    }
  })
})

// ═══════════════════════ 不撞键层（Property 7）═══════════════════════════════

describe('行 id 与叶子口径不撞键（Property 7）', () => {
  const leafPrefill = normalizePrefill({
    bank: [{ code: '1002', name: '银行存款', opening: 1, increase: 0, decrease: 0, ending: 1 }],
    other: [{ code: '1012', name: '其他货币资金', opening: 0, increase: 0, decrease: 0, ending: 0 }],
    account_list: [{ code: '1002', name: '银行存款', ending: 1 }],
  })

  it('E1-3：账户级 id 与叶子口径 id 集合无交集', () => {
    const leafIds = new Set((buildBankSeedRows(leafPrefill) || []).map(r => String(r.id)))
    const acctIds = (buildBankSeedRowsFromAccounts(prefill()) || []).map(r => String(r.id))
    expect(leafIds.size).toBeGreaterThan(0)
    expect(acctIds.length).toBeGreaterThan(0)
    for (const id of acctIds) expect(leafIds.has(id), id).toBe(false)
    for (const id of acctIds) expect(id).toContain('-acct-')
    for (const id of leafIds) expect(id).toContain('-ft-')
  })

  it('E1-10：账户级 id 与叶子口径 id 集合无交集', () => {
    const leafIds = new Set(
      (buildAccountListSeedRows(leafPrefill) || []).map(r => String(r.id)),
    )
    const acctIds = (buildAccountListSeedRowsFromAccounts(prefill()) || []).map(r =>
      String(r.id),
    )
    for (const id of acctIds) expect(leafIds.has(id), id).toBe(false)
    for (const id of acctIds) expect(id.startsWith('acct-a-')).toBe(true)
  })

  it('同账号在多个槽重复出现时 id 仍唯一（补序号去重）', () => {
    const dup = normalizeAccountPrefill({
      accounts: {
        bank: [acct({ account_no: 'SAME' })],
        other: [acct({ account_no: 'SAME' })],
        finance_co: [],
        unassigned: [],
      },
    })
    const ids = (buildBankSeedRowsFromAccounts(dup) || []).map(r => String(r.id))
    expect(ids.length).toBe(2)
    expect(new Set(ids).size).toBe(2)
    // 不同槽 → 不同 group → 天然不撞；同槽内重复也要唯一
    const sameSlot = normalizeAccountPrefill({
      accounts: { bank: [acct({ account_no: 'X' }), acct({ account_no: 'X' })] },
    })
    const ids2 = (buildBankSeedRowsFromAccounts(sameSlot) || []).map(r => String(r.id))
    expect(new Set(ids2).size).toBe(2)
  })

  it('账号为空时用科目码兜底（不产出 id 尾部空串）', () => {
    const noNo = normalizeAccountPrefill({
      accounts: { bank: [acct({ account_no: '', account_code: '1002.007' })] },
    })
    const id = String((buildBankSeedRowsFromAccounts(noNo) || [])[0].id)
    expect(id).toBe('bank-principal-institution-acct-1002.007')
  })
})

// ═══════════════════════ 口径层 ═════════════════════════════════════════════

describe('E1-3 种子（Requirements 1.9, 2.3, 2.4）', () => {
  it('槽 → group 映射：bank→institution / finance_co→finance / other→other', () => {
    expect(ACCOUNT_SLOT_TO_GROUP).toEqual({
      bank: 'institution',
      finance_co: 'finance',
      other: 'other',
    })
    const rows = buildBankSeedRowsFromAccounts(prefill()) || []
    const byNo = new Map(rows.map(r => [String(r.accountNo), r]))
    expect(byNo.get('1207014210004455')!.group).toBe('institution')
    expect(byNo.get('ALIPAY-01')!.group).toBe('other')
    // R2.3：财务公司自动归组，不要求审计师手工重分类
    expect(byNo.get('FIN-01')!.group).toBe('finance')
  })

  it('group 取值必须落在 useE1BankDetail.GROUPS 取值域内', () => {
    const src = readSrc(
      'audit-platform/frontend/src/components/workpaper/composables/useE1BankDetail.ts',
    )
    const m = src.match(/const GROUPS[^=]*=\s*\[([^\]]*)\]/)
    expect(m, '抽不到 GROUPS（正则失效）').toBeTruthy()
    const groups = [...m![1].matchAll(/'([^']+)'/g)].map(x => x[1])
    expect(groups.length).toBeGreaterThan(1)
    for (const g of Object.values(ACCOUNT_SLOT_TO_GROUP)) {
      expect(groups, `group ${g} 不在 GROUPS 取值域`).toContain(g)
    }
  })

  it('账户为空返 null（宿主据此退回叶子口径）', () => {
    expect(buildBankSeedRowsFromAccounts(normalizeAccountPrefill({}))).toBeNull()
    expect(buildAccountListSeedRowsFromAccounts(normalizeAccountPrefill({}))).toBeNull()
    // 只有 unassigned 时：E1-3 不产出（未归属账户无法定 group），E1-10 要产出
    const onlyU = normalizeAccountPrefill({ accounts: { unassigned: [acct()] } })
    expect(buildBankSeedRowsFromAccounts(onlyU)).toBeNull()
    expect(buildAccountListSeedRowsFromAccounts(onlyU)).toHaveLength(1)
  })

  it('字段集必须是 useE1BankDetail.USER_FIELDS 的子集（多给的键会被静默丢弃）', () => {
    const allowed = new Set(bankUserFields())
    expect(allowed.size).toBeGreaterThan(20)
    for (const variant of ['rmb', 'multi'] as const) {
      for (const row of buildBankSeedRowsFromAccounts(prefill(), variant) || []) {
        for (const k of Object.keys(row)) {
          expect(allowed.has(k), `${variant} 版多给了字段 ${k}`).toBe(true)
        }
      }
    }
  })

  it('本位币金额来自 aux 的 opening/debit/credit（不改口径）', () => {
    const row = (buildBankSeedRowsFromAccounts(prefill(), 'rmb') || [])[0]
    expect(row.opening).toBe(1000)
    expect(row.increase).toBe(300)
    expect(row.decrease).toBe(200)
    expect(row.section).toBe('principal')
    expect(row.bankName).toBe('上海浦东发展银行')
  })

  it('两 variant 账户条数相同、字段集不同（AC 1.9）', () => {
    const p = prefill({
      accounts: {
        bank: [acct(), acct({ account_no: 'USD-1', currency: 'USD' })],
        other: [],
        finance_co: [],
        unassigned: [],
      },
    })
    const rmb = buildBankSeedRowsFromAccounts(p, 'rmb') || []
    const multi = buildBankSeedRowsFromAccounts(p, 'multi') || []
    // 条数相同：外币账户在 rmb 版不丢弃
    expect(rmb).toHaveLength(2)
    expect(multi).toHaveLength(2)
    expect(rmb.map(r => r.id)).toEqual(multi.map(r => r.id))
    // 字段集不同：rmb 版不下发 fxCurrency 与任何原币列
    for (const r of rmb) {
      for (const k of ['fxCurrency', 'fxRate', 'openingFc', 'increaseFc', 'decreaseFc', 'adjustmentFc']) {
        expect(k in r, `rmb 版不应下发 ${k}`).toBe(false)
      }
    }
    for (const r of multi) expect('fxCurrency' in r).toBe(true)
  })

  it('🔴 multi 版必须下发原币列，否则 recalcRow 会把本位币金额抹成 0', () => {
    // 复现 useE1BankDetail.recalcRow 的 multi 分支
    const recalcMulti = (r: Record<string, unknown>) => {
      const n = (v: unknown) => (Number.isFinite(Number(v)) ? Number(v) : 0)
      const rate = n(r.fxRate)
      return {
        opening: n(r.openingFc) * rate,
        increase: n(r.increaseFc) * rate,
        decrease: n(r.decreaseFc) * rate,
      }
    }
    const cny = (buildBankSeedRowsFromAccounts(prefill(), 'multi') || [])[0]
    const after = recalcMulti(cny)
    expect(after.opening, '本位币账户在 multi 版经 recalc 后金额不得变 0').toBe(1000)
    expect(after.increase).toBe(300)
    expect(after.decrease).toBe(200)

    // 反向自检：若原币列留 0（旧设想），recalc 后必然被抹成 0
    const naive = { ...cny, openingFc: 0, increaseFc: 0, decreaseFc: 0, fxRate: 1 }
    expect(recalcMulti(naive).opening).toBe(0)
  })

  it('🔴 非本位币账户原币与汇率一律留 0 且 note 有提示（Property 34）', () => {
    const p = normalizeAccountPrefill({
      accounts: { bank: [acct({ currency: 'USD', account_no: 'USD-1' })] },
    })
    const row = (buildBankSeedRowsFromAccounts(p, 'multi') || [])[0]
    expect(row.fxCurrency).toBe('USD')
    expect(row.fxRate).toBe(0)
    expect(row.openingFc).toBe(0)
    expect(row.increaseFc).toBe(0)
    expect(row.decreaseFc).toBe(0)
    expect(String(row.note)).toContain(FOREIGN_FC_HINT)
    // 本位币账户不带该提示（否则提示泛滥失去意义）
    const cny = (buildBankSeedRowsFromAccounts(prefill(), 'multi') || [])[0]
    expect(String(cny.note)).not.toContain(FOREIGN_FC_HINT)
  })

  it('源码级：不得由本位币金额反推非本位币的原币/汇率（Property 34）', () => {
    const src = readSrc(
      'audit-platform/frontend/src/components/workpaper/composables/e1BankAccountPrefill.ts',
    )
    // 剥注释后再判（说明文字里会引用被禁形态）
    const code = src
      .replace(/\/\*[\s\S]*?\*\//g, '')
      .split('\n')
      .filter(l => !l.trim().startsWith('//'))
      .join('\n')
    expect(code).not.toMatch(/openingFc\s*[:=]\s*row\.opening\s*\/\s*/)
    expect(code).not.toMatch(/fxRate\s*[:=]\s*[^0-9\s]*\s*row\.opening/)
    // 反向自检：剥注释确实生效（原文含被禁字样的说明）
    expect(src).toContain('不得由本位币反推')
    expect(code).not.toContain('不得由本位币反推')
  })

  it('note 如实标注多笔合并与 level 3 降级（数据质量可追溯）', () => {
    const p = normalizeAccountPrefill({
      accounts: {
        bank: [
          acct({ row_count: 2, account_no: 'M1' }),
          acct({ parsed_level: 3, bank_name: '', account_no: 'L3' }),
        ],
      },
    })
    const rows = buildBankSeedRowsFromAccounts(p, 'rmb') || []
    expect(String(rows[0].note)).toContain('同账号 2 笔已合并')
    expect(String(rows[1].note)).toContain('账号取自辅助项名称')
    // level 1 不带降级提示
    const clean = (buildBankSeedRowsFromAccounts(prefill(), 'rmb') || [])[0]
    expect(String(clean.note)).not.toContain('账号取自辅助项名称')
  })
})

describe('E1-10 种子（Property 6）', () => {
  it('保留零余额账户（完整性核对红线）', () => {
    const p = normalizeAccountPrefill({
      accounts: {
        bank: [
          acct({ account_no: 'ZERO', opening: 0, debit: 0, credit: 0, closing: 0 }),
          acct({ account_no: 'HAS' }),
        ],
      },
    })
    const rows = buildAccountListSeedRowsFromAccounts(p) || []
    expect(rows).toHaveLength(2)
    expect(rows.map(r => r.accountNo)).toContain('ZERO')
  })

  it('unassigned 账户也进清单（暴露科目定位未覆盖的账户）', () => {
    const p = normalizeAccountPrefill({
      accounts: { bank: [acct()], unassigned: [acct({ account_no: 'U1' })] },
    })
    const rows = buildAccountListSeedRowsFromAccounts(p) || []
    expect(rows.map(r => r.accountNo)).toEqual(
      expect.arrayContaining(['1207014210004455', 'U1']),
    )
  })

  it('字段集与叶子口径 buildAccountListSeedRows 完全一致（同一 composable 契约）', () => {
    const leaf = (buildAccountListSeedRows(
      normalizePrefill({ account_list: [{ code: '1002', name: 'X', ending: 1 }] }),
    ) || [])[0]
    const a = (buildAccountListSeedRowsFromAccounts(prefill()) || [])[0]
    expect(Object.keys(a).sort()).toEqual(Object.keys(leaf).sort())
  })
})

describe('E1-4 数字货币种子（Requirements 1.10）', () => {
  const digital = [
    { code: '1012.11', name: '数字人民币钱包', currency: 'CNY', opening: 100, increase: 50, decrease: 20, ending: 130 },
  ]

  it('🔴 持久化键是 E1-digital-rows（不是 E1-digital-detail-rows）', () => {
    const { storageKey } = digitalContract()
    expect(storageKey).toBe('E1-digital-rows')
    // 反向锁死：spec 里写过的错名在全前端零消费方
    expect(storageKey).not.toBe('E1-digital-detail-rows')
  })

  it('字段集必须是该 Tab 的 USER_FIELDS 子集', () => {
    const { fields } = digitalContract()
    const allowed = new Set(fields)
    expect(allowed.size).toBe(14)
    for (const row of buildDigitalSeedRows(digital) || []) {
      for (const k of Object.keys(row)) {
        expect(allowed.has(k), `多给了字段 ${k}`).toBe(true)
      }
    }
  })

  it('空输入返 null；seq 从 1 起；本位币汇率 1', () => {
    expect(buildDigitalSeedRows(null)).toBeNull()
    expect(buildDigitalSeedRows([])).toBeNull()
    const rows = buildDigitalSeedRows([...digital, { ...digital[0], code: '1012.12' }]) || []
    expect(rows.map(r => r.seq)).toEqual([1, 2])
    expect(rows[0].fxRate).toBe(1)
    expect(rows[0].currency).toBe('人民币')
    expect(rows[0].id).toBe('digi-ft-1012.11')
  })

  it('非本位币不臆造汇率 1，且 note 提示手工录入', () => {
    const row = (buildDigitalSeedRows([{ ...digital[0], currency: 'USD' }]) || [])[0]
    expect(row.fxRate).toBe(0)
    expect(row.currency).toBe('USD')
    expect(String(row.note)).toContain(FOREIGN_FC_HINT)
  })

  it('id 与该 Tab 自生成 id 前缀不撞（digi-ft- vs digi-{ts}-）', () => {
    const row = (buildDigitalSeedRows(digital) || [])[0]
    expect(String(row.id).startsWith('digi-ft-')).toBe(true)
    expect(String(row.id)).not.toMatch(/^digi-\d+-/)
  })
})

describe('normalizePrefill additive 扩展零回归（Property 9）', () => {
  it('新增 finance_co / digital 两键，缺省为空数组', () => {
    const p = normalizePrefill({})
    expect(p.finance_co).toEqual([])
    expect(p.digital).toEqual([])
  })

  it('🔴 新键必须真的透传数据（不能只是占位空数组）', () => {
    // 变异检验 M7 抓出的缺口：只断言「缺省为空」时，把 `arr(p.finance_co)` 改成
    // `[]` 不会打红 —— 而那正是「后端发了数据前端读不到」的 dead output 形态。
    const p = normalizePrefill({
      finance_co: [
        { code: '1002.99', name: '财务公司', opening: 8, increase: 1, decrease: 2, ending: 7 },
      ],
      digital: [
        { code: '1012.11', name: '数币', opening: 9, increase: 3, decrease: 1, ending: 11 },
        { code: '1012.12', name: '数币2', opening: 0, increase: 0, decrease: 0, ending: 0 },
      ],
    })
    expect(p.finance_co).toHaveLength(1)
    expect(p.finance_co[0].code).toBe('1002.99')
    expect(p.finance_co[0].ending).toBe(7)
    expect(p.digital).toHaveLength(2)
    expect(p.digital.map(r => r.code)).toEqual(['1012.11', '1012.12'])
    // digital 透传后必须能直接喂给 buildDigitalSeedRows（端到端链路可达）
    const seeds = buildDigitalSeedRows(p.digital) || []
    expect(seeds).toHaveLength(2)
    expect(seeds[0].opening).toBe(9)
  })

  it('非数组的新键归一为空数组（不抛）', () => {
    for (const bad of [null, 0, 'x', {}, true]) {
      const p = normalizePrefill({ finance_co: bad, digital: bad })
      expect(p.finance_co).toEqual([])
      expect(p.digital).toEqual([])
    }
  })

  it('既有五键行为逐字不变，且既有 build 函数不读新键', () => {
    const raw = {
      cash: [{ code: '1001', name: '现金', opening: 1, increase: 0, decrease: 0, ending: 1 }],
      bank: [{ code: '1002', name: '银行', opening: 2, increase: 0, decrease: 0, ending: 2 }],
      other: [],
      account_list: [{ code: '1002', name: '银行', ending: 2 }],
      meta: { as_of: '2025-12-31' },
      digital: [{ code: '1012.11', name: '数币', opening: 9, increase: 0, decrease: 0, ending: 9 }],
      finance_co: [{ code: '1002.99', name: '财务公司', opening: 8, increase: 0, decrease: 0, ending: 8 }],
    }
    const p = normalizePrefill(raw)
    expect(p.cash).toHaveLength(1)
    expect(p.bank).toHaveLength(1)
    expect(p.account_list).toHaveLength(1)
    expect(p.meta).toEqual({ as_of: '2025-12-31' })
    // 既有 E1-3 叶子种子只用 bank+other ⇒ 新键不影响条数
    expect(buildBankSeedRows(p)).toHaveLength(1)
    // 既有 E1-10 叶子种子只用 account_list
    expect(buildAccountListSeedRows(p)).toHaveLength(1)
  })
})
