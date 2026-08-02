/**
 * 受限资产附注表（listed `五、32` 主表+续表 / soe `八、93`）行级合并载荷契约。
 *
 * **Validates: restricted-assets-note-row-scope-rollout Requirements 3.1~3.6, 5.2, 5.3
 * / Properties 6, 8, 9, 10, 14**
 *
 * 三向锁死：章节号 / 表名 / 列定义 逐字命中 `note_template_{listed,soe}.json`；
 * `owner_row_code` ∈ 该表段集合；载荷必须带 `_row_scope`。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

import {
  buildRestrictedAssetsColumns,
  buildRestrictedAssetsPayloads,
  isRestrictedAssetsOwnerApplicable,
  RESTRICTED_ASSETS_NOTE_SECTION,
  RESTRICTED_ASSETS_OWNERS,
  RESTRICTED_ASSETS_SOE_ONLY_OWNERS,
  RESTRICTED_ASSETS_TABLE,
  resolveRestrictedAssetsStandard,
  summarizeRestrictedRows,
  type RestrictedAssetsOwner,
  type RestrictedAssetsVariant,
} from '../restrictedAssetsNoteSectionMap'

const REPO_ROOT = resolve(__dirname, '../../../../../../..')
const TEMPLATE = {
  listed: resolve(REPO_ROOT, 'backend/data/note_template_listed.json'),
  soe: resolve(REPO_ROOT, 'backend/data/note_template_soe.json'),
} as const

const SHEETS = { listed: '附注披露信息(上市公司)', soe: '附注披露信息(国企)' }
const VARIANTS: readonly RestrictedAssetsVariant[] = ['listed', 'soe']

function loadTables(variant: RestrictedAssetsVariant) {
  const doc = JSON.parse(readFileSync(TEMPLATE[variant], 'utf-8'))
  const sec = (doc.sections || []).find(
    (s: any) => String(s.section_number || '').trim() === RESTRICTED_ASSETS_NOTE_SECTION[variant],
  )
  expect(sec, `模板缺章节 ${RESTRICTED_ASSETS_NOTE_SECTION[variant]}`).toBeTruthy()
  const out: Record<string, any> = {}
  for (const t of sec.tables || []) out[String(t.name || '').trim()] = t
  return out
}

/** 该表模板行集里的段首 `report_row_code`（保序去重）—— 与后端切段口径一致。 */
function segmentRowCodes(rows: any[]): string[] {
  const out: string[] = []
  for (const r of rows || []) {
    const code = String(r?.report_row_code || '').trim()
    if (code && !out.includes(code)) out.push(code)
  }
  return out
}

function tablesOf(variant: RestrictedAssetsVariant): string[] {
  return variant === 'soe'
    ? [RESTRICTED_ASSETS_TABLE.soe]
    : [RESTRICTED_ASSETS_TABLE.listedMain, RESTRICTED_ASSETS_TABLE.listedPrior]
}

const DETAILS = [
  { endAmount: 1200000, priorAmount: 900000, reason: '银行承兑汇票保证金' },
  { endAmount: 300000.004, priorAmount: 100000, reason: '信用证保证金' },
  { endAmount: 0, priorAmount: 0, reason: '银行承兑汇票保证金' },
]

function e1Rows() {
  return summarizeRestrictedRows(RESTRICTED_ASSETS_OWNERS['BS-002'], DETAILS)
}

describe('模板三向对齐（章节 / 表名 / 列定义）', () => {
  it.each(VARIANTS)('%s：表名逐字命中模板', (variant) => {
    const tabs = loadTables(variant)
    for (const name of tablesOf(variant)) {
      expect(tabs[name], `模板缺表「${name}」`).toBeTruthy()
    }
  })

  it('listed 续表名带主表名前缀，且裸名「续：」已不存在', () => {
    const tabs = loadTables('listed')
    expect(RESTRICTED_ASSETS_TABLE.listedPrior.startsWith(RESTRICTED_ASSETS_TABLE.listedMain))
      .toBe(true)
    expect(Object.keys(tabs)).not.toContain('续：')
  })

  it('soe 表名用「和」、listed 用「或」（源模板措辞不同，不得统一）', () => {
    expect(RESTRICTED_ASSETS_TABLE.soe).toContain('所有权和使用权')
    expect(RESTRICTED_ASSETS_TABLE.listedMain).toContain('所有权或使用权')
  })

  it.each(VARIANTS)('%s：列定义与模板 columns 逐字段相同（key/label/format/flat）', (variant) => {
    const tabs = loadTables(variant)
    const pushed = buildRestrictedAssetsColumns()
    for (const name of tablesOf(variant)) {
      const tplCols = tabs[name].columns || []
      const mine = pushed[name]
      expect(mine, `${name} 缺列定义`).toBeTruthy()
      expect(mine.map((c) => c.key)).toEqual(tplCols.map((c: any) => c.key))
      expect(mine.map((c) => c.label)).toEqual(tplCols.map((c: any) => c.label))
      expect(mine.map((c) => c.format ?? null)).toEqual(tplCols.map((c: any) => c.format ?? null))
      // Property 6：单级表头 —— 必标 flat 且不得声明 group
      expect(mine.some((c) => c.flat), `${name} 未标 flat`).toBe(true)
      expect(mine.some((c) => c.group)).toBe(false)
      expect(mine.map((c) => c.label)).toEqual(tabs[name].headers)
    }
  })

  it('buildRestrictedAssetsColumns 可零入参调用且覆盖 3 张子表', () => {
    const cols = buildRestrictedAssetsColumns()
    expect(Object.keys(cols).sort()).toEqual(
      [
        RESTRICTED_ASSETS_TABLE.listedMain,
        RESTRICTED_ASSETS_TABLE.listedPrior,
        RESTRICTED_ASSETS_TABLE.soe,
      ].sort(),
    )
  })

  it('两变体章节号必须不同', () => {
    expect(RESTRICTED_ASSETS_NOTE_SECTION.listed).not.toBe(RESTRICTED_ASSETS_NOTE_SECTION.soe)
  })
})

describe('段归属（owner 清单 ↔ 模板段集合）', () => {
  it.each(VARIANTS)('%s：owner 清单与模板段集合一致', (variant) => {
    const tabs = loadTables(variant)
    for (const name of tablesOf(variant)) {
      const codes = segmentRowCodes(tabs[name].rows || [])
      expect(codes.length, `${name} 段数`).toBeGreaterThanOrEqual(2)
      const expected = (Object.keys(RESTRICTED_ASSETS_OWNERS) as RestrictedAssetsOwner[]).filter(
        (o) => isRestrictedAssetsOwnerApplicable(variant, o),
      )
      expect(new Set(codes)).toEqual(new Set(expected))
    }
  })

  it('段标签与模板段首行 label 逐字一致', () => {
    for (const variant of VARIANTS) {
      const tabs = loadTables(variant)
      for (const name of tablesOf(variant)) {
        for (const r of tabs[name].rows || []) {
          const code = String(r?.report_row_code || '').trim()
          if (!code) continue
          expect(String(r.label).trim()).toBe(
            RESTRICTED_ASSETS_OWNERS[code as RestrictedAssetsOwner],
          )
        }
      }
    }
  })

  it('soe 专有段（BS-007 应收款项融资 / BS-029 在建工程）在 listed 侧不适用', () => {
    expect([...RESTRICTED_ASSETS_SOE_ONLY_OWNERS].sort()).toEqual(['BS-007', 'BS-029'])
    for (const owner of RESTRICTED_ASSETS_SOE_ONLY_OWNERS) {
      expect(isRestrictedAssetsOwnerApplicable('soe', owner)).toBe(true)
      expect(isRestrictedAssetsOwnerApplicable('listed', owner)).toBe(false)
    }
    expect(isRestrictedAssetsOwnerApplicable('listed', 'BS-002')).toBe(true)
  })
})

describe('summarizeRestrictedRows —— 按资产类别归纳成一行', () => {
  it('金额求和 + 原因去重拼接 + 金额取 2 位', () => {
    const [row] = e1Rows()
    expect(row.label).toBe('货币资金')
    expect(row.endAmount).toBe(1500000)
    expect(row.priorAmount).toBe(1000000)
    expect(row.reason).toBe('银行承兑汇票保证金；信用证保证金')
  })

  it('空明细 → 一行全零，且**不声明** priorAmount（由 payload 构造器判定不推）', () => {
    const [row] = summarizeRestrictedRows('货币资金', [])
    expect(row).toEqual({ label: '货币资金', endAmount: 0, reason: '' })
    expect('priorAmount' in row, '一条 detail 都没有 → 不得凭空补 0').toBe(false)
  })

  it('忽略非法金额（NaN / undefined）', () => {
    const [row] = summarizeRestrictedRows('存货', [
      { endAmount: Number.NaN, reason: '' },
      { endAmount: undefined, priorAmount: 5, reason: ' 抵押 ' },
    ])
    expect(row.endAmount).toBe(0)
    expect(row.priorAmount).toBe(5)
    expect(row.reason).toBe('抵押')
  })
})

describe('buildRestrictedAssetsPayloads', () => {
  it('Property 8：listed 产出 2 个 payload（主表期末 + 续表上年年末）', () => {
    const payloads = buildRestrictedAssetsPayloads(
      'listed',
      'wp-1',
      ['listed_standalone'],
      { ownerRowCode: 'BS-002', rows: e1Rows() },
      SHEETS,
    )
    expect(payloads.length).toBe(2)
    const [main, prior] = payloads
    expect(Object.keys(main.sub_table_data).filter((k) => !k.startsWith('_'))).toEqual([
      RESTRICTED_ASSETS_TABLE.listedMain,
    ])
    expect(Object.keys(prior.sub_table_data).filter((k) => !k.startsWith('_'))).toEqual([
      RESTRICTED_ASSETS_TABLE.listedPrior,
    ])
    // 两次都带 _row_scope，owner 相同、表名不同
    for (const p of payloads) {
      const scope = (p.sub_table_data as any)._row_scope
      const keys = Object.keys(scope)
      expect(keys.length).toBe(1)
      expect(scope[keys[0]]).toEqual({ owner_row_code: 'BS-002' })
      expect(p.section_id).toBe('五、32')
      expect(p.current_standard).toBe('listed_standalone')
      expect(p.sheet_name).toBe(SHEETS.listed)
    }
    expect((main.sub_table_data as any)[RESTRICTED_ASSETS_TABLE.listedMain]).toEqual([
      { label: '货币资金', end_amount: 1500000 },
    ])
    expect((prior.sub_table_data as any)[RESTRICTED_ASSETS_TABLE.listedPrior]).toEqual([
      { label: '货币资金', prior_amount: 1000000 },
    ])
  })

  it('Property 9：soe 含「受限原因」列，listed 不含（源模板 2 列）', () => {
    const [soe] = buildRestrictedAssetsPayloads(
      'soe',
      'wp-1',
      ['soe_standalone'],
      { ownerRowCode: 'BS-002', rows: e1Rows() },
      SHEETS,
    )
    const row = (soe.sub_table_data as any)[RESTRICTED_ASSETS_TABLE.soe][0]
    expect(row).toEqual({
      label: '货币资金',
      end_carrying: 1500000,
      reason: '银行承兑汇票保证金；信用证保证金',
    })
    const listed = buildRestrictedAssetsPayloads(
      'listed',
      'wp-1',
      [],
      { ownerRowCode: 'BS-002', rows: e1Rows() },
      SHEETS,
    )
    for (const p of listed) {
      for (const table of Object.keys(p.sub_table_data)) {
        if (table.startsWith('_')) continue
        for (const r of (p.sub_table_data as any)[table]) {
          expect(Object.keys(r)).not.toContain('reason')
        }
      }
    }
  })

  it('Property 10：无实质数据 → 返回 []（不推空段）', () => {
    for (const variant of VARIANTS) {
      expect(
        buildRestrictedAssetsPayloads(variant, 'wp-1', [], { ownerRowCode: 'BS-002', rows: [] }, SHEETS),
      ).toEqual([])
      const zero = summarizeRestrictedRows('货币资金', [])
      expect(
        buildRestrictedAssetsPayloads(
          variant,
          'wp-1',
          [],
          { ownerRowCode: 'BS-002', rows: zero },
          SHEETS,
        ),
        `${variant} 全零骨架不得推送（会把段恢复成模板骨架）`,
      ).toEqual([])
    }
  })

  it('只有原因、没有金额 → 仍视为有实质数据（受限事实本身要披露）', () => {
    const rows = summarizeRestrictedRows('货币资金', [{ endAmount: 0, reason: '账户被冻结' }])
    expect(
      buildRestrictedAssetsPayloads('soe', 'wp-1', [], { ownerRowCode: 'BS-002', rows }, SHEETS)
        .length,
    ).toBe(1)
  })

  it('该 owner 在本变体无落点 → 返回 []（如 H2 在 listed 侧）', () => {
    const rows = summarizeRestrictedRows('在建工程', [{ endAmount: 100, reason: '抵押' }])
    expect(
      buildRestrictedAssetsPayloads('listed', 'wp-1', [], { ownerRowCode: 'BS-029', rows }, SHEETS),
    ).toEqual([])
    expect(
      buildRestrictedAssetsPayloads('soe', 'wp-1', [], { ownerRowCode: 'BS-029', rows }, SHEETS)
        .length,
    ).toBe(1)
  })

  it('行对象的键 ⊆ columns 的键（单向 P1）', () => {
    const cols = buildRestrictedAssetsColumns()
    for (const variant of VARIANTS) {
      const payloads = buildRestrictedAssetsPayloads(
        variant,
        'wp-1',
        [],
        { ownerRowCode: 'BS-002', rows: e1Rows() },
        SHEETS,
      )
      for (const p of payloads) {
        for (const table of Object.keys(p.sub_table_data)) {
          if (table.startsWith('_')) continue
          const keys = new Set(cols[table].map((c) => c.key))
          keys.add('is_total')
          for (const r of (p.sub_table_data as any)[table]) {
            for (const k of Object.keys(r)) expect(keys.has(k), `孤儿字段 ${k}`).toBe(true)
          }
        }
      }
    }
  })

  it('无标签行被丢弃（防止推出空行）', () => {
    const payloads = buildRestrictedAssetsPayloads(
      'soe',
      'wp-1',
      [],
      { ownerRowCode: 'BS-002', rows: [{ label: '  ', endAmount: 100 }] },
      SHEETS,
    )
    expect(payloads).toEqual([])
  })

  it('current_standard 按变体 + 合并口径解析', () => {
    expect(resolveRestrictedAssetsStandard('listed', ['listed_consolidated'])).toBe(
      'listed_consolidated',
    )
    expect(resolveRestrictedAssetsStandard('listed', [])).toBe('listed_standalone')
    expect(resolveRestrictedAssetsStandard('soe', ['soe_consolidated'])).toBe('soe_consolidated')
    expect(resolveRestrictedAssetsStandard('soe', null)).toBe('soe_standalone')
    // 变体与准则不符时以**页变体**为准（避免一页写两种标准）
    expect(resolveRestrictedAssetsStandard('soe', ['listed_standalone'])).toBe('soe_standalone')
  })
})

describe('单期口径（只有期末数据的 owner）', () => {
  it('🔴 未声明 priorAmount → listed 只推主表，不推「（续：上年年末）」', () => {
    // D1 的「期末已质押的应收票据」表只有期末口径 → 推 0 会覆盖审计师在续表手填的值
    const rows = summarizeRestrictedRows('应收票据', [
      { endAmount: 500000, reason: '已质押（银行承兑票据）' },
    ])
    expect(rows[0].priorAmount, '未声明就不能凭空补 0').toBeUndefined()
    const payloads = buildRestrictedAssetsPayloads(
      'listed',
      'wp-d1',
      ['listed_standalone'],
      { ownerRowCode: 'BS-005', rows },
      SHEETS,
    )
    expect(payloads.length).toBe(1)
    expect(Object.keys(payloads[0].sub_table_data).filter((k) => !k.startsWith('_'))).toEqual([
      RESTRICTED_ASSETS_TABLE.listedMain,
    ])
  })

  it('声明了 priorAmount（哪怕是 0）→ 照推续表', () => {
    const rows = summarizeRestrictedRows('货币资金', [{ endAmount: 100, priorAmount: 0 }])
    expect(rows[0].priorAmount).toBe(0)
    const payloads = buildRestrictedAssetsPayloads(
      'listed',
      'wp-1',
      [],
      { ownerRowCode: 'BS-002', rows },
      SHEETS,
    )
    expect(payloads.length).toBe(2)
    expect((payloads[1].sub_table_data as any)[RESTRICTED_ASSETS_TABLE.listedPrior]).toEqual([
      { label: '货币资金', prior_amount: 0 },
    ])
  })

  it('soe 单表不受期初口径影响（源模板只有期末账面价值列）', () => {
    const rows = summarizeRestrictedRows('应收票据', [{ endAmount: 500000, reason: '已质押' }])
    const payloads = buildRestrictedAssetsPayloads(
      'soe',
      'wp-d1',
      [],
      { ownerRowCode: 'BS-005', rows },
      SHEETS,
    )
    expect(payloads.length).toBe(1)
    expect((payloads[0].sub_table_data as any)[RESTRICTED_ASSETS_TABLE.soe]).toEqual([
      { label: '应收票据', end_carrying: 500000, reason: '已质押' },
    ])
  })
})

describe('owner 接入状态登记（只许按 spec 增，不许悄悄接线）', () => {
  /**
   * 🔴 **已接入的 owner** —— 两种接线形态：
   *
   * - `direct`：披露 Tab 自己调 `buildRestrictedAssetsPayloads` + 自己发 POST
   *   （E1/D1 的受限数据是本页**内存行模型**，不在 `checklist_responses` 里）
   * - `shared`：走共享 composable `useRestrictedAssetsSync`
   *   （数据在 `checklist_responses`，采集逻辑声明在 `restrictedAssetsSources.ts`）
   *
   * 未接入的 owner 见 `NOT_WIRED_OWNERS`（只剩真的没有数据的两个）。
   */
  const WIRED: Record<
    string,
    { file: string; owner: RestrictedAssetsOwner; mode: 'direct' | 'shared' }
  > = {
    E1: { file: '../../e1/E1TabDisclosure.vue', owner: 'BS-002', mode: 'direct' },
    D1: { file: '../../d1/D1TabDisclosure.vue', owner: 'BS-005', mode: 'direct' },
    D2: { file: '../../d2/D2DisclosureNoteBody.vue', owner: 'BS-006', mode: 'shared' },
    'H1-listed': {
      file: '../../h1/core/H1TabDisclosureListed.vue',
      owner: 'BS-028',
      mode: 'shared',
    },
    'H1-soe': { file: '../../h1/core/H1TabDisclosureSoe.vue', owner: 'BS-028', mode: 'shared' },
    'H2-soe': { file: '../../h2/core/H2TabDisclosureSoe.vue', owner: 'BS-029', mode: 'shared' },
    'I1-listed': {
      file: '../../i1/core/I1TabDisclosureListed.vue',
      owner: 'BS-032',
      mode: 'shared',
    },
    'I1-soe': { file: '../../i1/core/I1TabDisclosureSoe.vue', owner: 'BS-032', mode: 'shared' },
  }

  /**
   * **未接入的 owner + 理由**（2026-08-02 逐循环普查的实测结论）。
   *
   * 🔴 判定口径（用户 2026-08-02 明确）：**「只有期末数」不是不接的理由**
   * —— 只有期末就只推期末（listed 不推「（续：上年年末）」续表）。
   * 只有**真的一条结构化受限金额都没有**才登记在此。
   */
  const NOT_WIRED_OWNERS: Partial<Record<RestrictedAssetsOwner, string>> = {
    'BS-007':
      'D5 应收款项融资：披露 Tab 与底稿均无受限资产录入位置（该段为 soe 专有），无结构化受限金额可推',
    'BS-010':
      'F2 存货：披露侧对 质押/抵押/受限/冻结/查封 零命中，底稿侧亦无受限金额字段，无数据可推',
  }

  function cleanSource(file: string): string {
    return readFileSync(resolve(__dirname, file), 'utf-8')
      .replace(/<!--[\s\S]*?-->/g, '')
      .replace(/\/\*[\s\S]*?\*\//g, '')
      .replace(/(^|[^:])\/\/[^\n]*/g, '$1')
  }

  it.each(Object.entries(WIRED))('%s：接线可扫到且不越权覆盖他段', (tag, { file, owner, mode }) => {
    const src = cleanSource(file)
    if (mode === 'direct') {
      expect(src, `${tag} 未调载荷构造器`).toContain('buildRestrictedAssetsPayloads')
      expect(src, `${tag} 未消费 fail closed 返回字段`).toContain('row_scope_unresolved')
    } else {
      expect(src, `${tag} 未接共享 composable`).toContain('useRestrictedAssetsSync')
      // 建了实例还要真的调用（否则同 E1 曾经的「只建实例不调用」假接入）
      expect(src, `${tag} 建了实例但从不调用`).toMatch(/await\s+syncRestrictedAssets\s*\(/)
    }
    expect(src, `${tag} 未声明自己的 owner`).toContain(`'${owner}'`)
    // 反向边界：不得出现他段 code（防越权覆盖）
    for (const other of Object.keys(RESTRICTED_ASSETS_OWNERS) as RestrictedAssetsOwner[]) {
      if (other === owner) continue
      expect(src, `${tag} 出现他段 code ${other}`).not.toContain(`'${other}'`)
    }
  })

  it('shared 形态的 Tab 必须传对变体（listed Tab 不许声明 soe，反之亦然）', () => {
    const cases: Array<[string, RestrictedAssetsVariant]> = [
      ['H1-listed', 'listed'],
      ['H1-soe', 'soe'],
      ['H2-soe', 'soe'],
      ['I1-listed', 'listed'],
      ['I1-soe', 'soe'],
    ]
    for (const [tag, variant] of cases) {
      const src = cleanSource(WIRED[tag].file)
      expect(src, `${tag} variant 声明错`).toMatch(
        new RegExp(`variant:\\s*\\(\\)\\s*=>\\s*'${variant}'`),
      )
    }
    // D2 是双变体同一组件（:key="variant" 挂载）→ 透传 props.variant
    expect(cleanSource(WIRED.D2.file)).toMatch(/variant:\s*\(\)\s*=>\s*props\.variant/)
  })

  it('已接入 ∪ 未接入 == 全部 8 个 owner，且两集合不相交', () => {
    const wired = new Set(Object.values(WIRED).map((w) => w.owner))
    const notWired = new Set(Object.keys(NOT_WIRED_OWNERS) as RestrictedAssetsOwner[])
    expect([...wired].filter((o) => notWired.has(o))).toEqual([])
    expect(new Set([...wired, ...notWired])).toEqual(
      new Set(Object.keys(RESTRICTED_ASSETS_OWNERS)),
    )
  })

  it('未接入登记表每条都写明理由（≥20 字），且只许缩不许扩', () => {
    for (const [owner, reason] of Object.entries(NOT_WIRED_OWNERS)) {
      expect(String(reason).length, `${owner} 理由太短`).toBeGreaterThan(20)
    }
    expect(Object.keys(NOT_WIRED_OWNERS).length, '未接入数只许变少').toBeLessThanOrEqual(2)
  })

  it('🔴 I1 两个 Tab 不得再自调度（syncToNotes 内调 scheduleAutoSync = 无限 POST）', () => {
    for (const tag of ['I1-listed', 'I1-soe']) {
      const src = cleanSource(WIRED[tag].file)
      const m = /\basync\s+function\s+syncToNotes\s*\(/.exec(src)
      expect(m, `${tag} 找不到 syncToNotes（正则失效则本用例空转）`).toBeTruthy()
      // 大括号配平截函数体
      let i = src.indexOf('{', m!.index + m![0].length)
      let depth = 0
      const start = i
      for (; i < src.length; i++) {
        if (src[i] === '{') depth++
        else if (src[i] === '}') {
          depth--
          if (depth === 0) break
        }
      }
      const body = src.slice(start, i + 1)
      expect(body.length, `${tag} 函数体截取失败`).toBeGreaterThan(50)
      expect(body, `${tag} 仍在 syncToNotes 内自调度`).not.toContain('scheduleAutoSync(')
      // 且必须真的监听了实际数据
      expect(src, `${tag} 没有数据变更触发的自动同步`).toMatch(
        /watch\(\s*\[[\s\S]{0,600}?\]\s*,\s*\(\)\s*=>\s*autoSync\.scheduleAutoSync\(/,
      )
    }
  })
})

describe('🔴 反向自检 + E1 接线', () => {
  it('去掉 _row_scope 的载荷会被判为危险（证明 Property 14 判定不空转）', () => {
    const [p] = buildRestrictedAssetsPayloads(
      'soe',
      'wp-1',
      [],
      { ownerRowCode: 'BS-002', rows: e1Rows() },
      SHEETS,
    )
    const isSafe = (sub: Record<string, unknown>) =>
      Object.values((sub._row_scope as any) || {}).some(
        (v: any) => !!v?.owner_row_code,
      )
    expect(isSafe(p.sub_table_data)).toBe(true)
    const mutated = { ...(p.sub_table_data as any) }
    delete mutated._row_scope
    expect(isSafe(mutated)).toBe(false)
  })

  it('E1TabDisclosure 已接受限资产 payload 且消费 fail closed 返回字段', () => {
    const raw = readFileSync(resolve(__dirname, '../../e1/E1TabDisclosure.vue'), 'utf-8')
    const src = raw
      .replace(/<!--[\s\S]*?-->/g, '')
      .replace(/\/\*[\s\S]*?\*\//g, '')
      .replace(/(^|[^:])\/\/[^\n]*/g, '$1')
    // 反向自检：注释确实被剥掉了
    expect(raw).toContain('跨循环共享表')
    expect(src).not.toContain('跨循环共享表')

    expect(src).toContain('buildRestrictedAssetsPayloads')
    expect(src).toMatch(/syncRestrictedAssetsToNote\s*\(/)
    expect(src).toContain('row_scope_unresolved')
    // E1 只许声明货币资金段，不得出现他段 code
    expect(src).toContain("'BS-002'")
    for (const foreign of ['BS-005', 'BS-006', 'BS-007', 'BS-010', 'BS-028', 'BS-029', 'BS-032']) {
      expect(src, `E1 出现他段 code ${foreign}`).not.toContain(`'${foreign}'`)
    }
    // 自动同步监听源必须含 restrictedRows（否则「改了受限资产不同步」）
    expect(src).toMatch(/watch\(\s*\[[^\]]*restrictedRows[^\]]*\]/)
  })
})
