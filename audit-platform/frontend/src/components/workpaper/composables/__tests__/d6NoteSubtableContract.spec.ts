/**
 * D6 合同资产披露子表 ↔ 附注模板契约 + 两级表头结构
 *
 * 守 4 类回归（旧实现全部踩中，详见 spec）：
 * 1. 两级表头被拍平成「期末账面余额」式组合列名 → 附注丢期间父表头
 * 2. 减值准备计提情况只有期末 4 列（缺账面价值 + 整个上年年末段）
 * 3. 载荷表名与模板不一致 → 孤儿子表
 * 4. 组件 snapshot 字段名与载荷接口不符（endBalance vs balance）→ 静默推 0
 *
 * spec: .kiro/specs/d-cycle-remaining-disclosure-alignment/ Task 6.8
 */
import { describe, expect, it } from 'vitest'
import { runDisclosureSubtableContract } from './_disclosureSubtableContract.helper'
import {
  buildD6SyncPayload,
  buildD6ListedColumns,
  buildD6SimpleMainRows,
  buildD6SoeColumns,
  d6MainColumns,
  D6_NOTE_SECTION,
  D6_LISTED_SUBTABLE,
  D6_SOE_SUBTABLE,
  D6_OBSOLETE_TABLE_NAMES,
  D6_NOTE_TOTAL_LABEL,
  type D6DisclosureSnapshot,
} from '../d6NoteSectionMap'

runDisclosureSubtableContract({
  cycle: 'D6',
  variants: [
    {
      variant: 'listed',
      section: D6_NOTE_SECTION.listed,
      subtables: D6_LISTED_SUBTABLE,
      columns: buildD6ListedColumns(),
    },
    {
      variant: 'soe',
      section: D6_NOTE_SECTION.soe,
      subtables: D6_SOE_SUBTABLE,
      columns: buildD6SoeColumns(),
    },
  ],
})

const cols = (list: ReadonlyArray<{ label?: string; group?: string }>) =>
  list.map((c) => [c.label, c.group ?? ''])

describe('D6 两级表头（Property：两期同构 + 不得拍平）', () => {
  it('上市主表 = 项  目 + 期末余额{3} + 上年年末余额{3}', () => {
    expect(cols(d6MainColumns('listed'))).toEqual([
      ['项  目', ''],
      ['账面余额', '期末余额'], ['减值准备', '期末余额'], ['账面价值', '期末余额'],
      ['账面余额', '上年年末余额'], ['减值准备', '上年年末余额'], ['账面价值', '上年年末余额'],
    ])
  })

  it('国企主表分组名为 期末数 / 期初数', () => {
    expect(cols(d6MainColumns('soe'))).toEqual([
      ['项  目', ''],
      ['账面余额', '期末数'], ['减值准备', '期末数'], ['账面价值', '期末数'],
      ['账面余额', '期初数'], ['减值准备', '期初数'], ['账面价值', '期初数'],
    ])
  })

  it('🔴 列头不得是拍平后的组合名（旧实现「期末账面余额」）', () => {
    const all = [
      ...Object.values(buildD6ListedColumns()),
      ...Object.values(buildD6SoeColumns()),
    ].flat()
    for (const c of all) {
      expect(String(c.label)).not.toMatch(/^(期末|上年|期初)(账面余额|减值准备|账面价值)$/)
    }
  })

  it('减值准备计提情况：源模板 6 列（两级 + 账面价值独立列），期末/续表同构', () => {
    const listed = buildD6ListedColumns()
    const want = [
      ['类别', ''],
      ['金额', '账面余额'], ['比例(%)', '账面余额'],
      ['金额', '减值准备'], ['预期信用损失率(%)', '减值准备'],
      ['账面价值', ''],
    ]
    expect(cols(listed[D6_LISTED_SUBTABLE.impairmentEnd])).toEqual(want)
    expect(cols(listed[D6_LISTED_SUBTABLE.impairmentPrior])).toEqual(want)
  })

  it('国企减值准备变动：本期变动金额 3 列一组，期初/期末/原因独立', () => {
    expect(cols(buildD6SoeColumns()[D6_SOE_SUBTABLE.impairment])).toEqual([
      ['项  目', ''],
      ['期初数', ''],
      ['计提', '本期变动金额'], ['转回', '本期变动金额'], ['转销/核销', '本期变动金额'],
      ['期末数', ''],
      ['原因', ''],
    ])
  })

  it('group 值不得含 /（前端 activeTableColumns 只认扁平分组）', () => {
    const all = [
      ...Object.values(buildD6ListedColumns()),
      ...Object.values(buildD6SoeColumns()),
    ].flat()
    for (const c of all) expect(String(c.group ?? '')).not.toContain('/')
  })
})

// ─── 载荷行为 ────────────────────────────────────────────────────────────────

const SNAPSHOT: D6DisclosureSnapshot = {
  classRows: [
    {
      label: '单项计提坏账准备',
      endBookBalance: 1000, endImpairment: 100, endBookValue: 900,
      priorBookBalance: 800, priorImpairment: 80, priorBookValue: 720,
    },
  ],
  majorChangeRows: [{ label: '新增合同', amount: 200, reason: '中标' }],
  impairmentProvisionRows: [
    { label: '按单项计提坏账准备', balance: 1000, ratio: 100, provision: 100, lossRate: 10 },
  ],
  impairmentProvisionPriorRows: [
    { label: '按单项计提坏账准备', balance: 800, ratio: 100, provision: 80, lossRate: 10 },
  ],
  singleItems: [{ label: '甲公司', balance: 1000, provision: 100, lossRate: 10, reason: '诉讼' }],
  singleItemsPrior: [{ label: '甲公司', balance: 800, provision: 80, lossRate: 10, reason: '诉讼' }],
  groups: [
    {
      groupName: '工程施工',
      rows: [
        {
          label: '1年以内', balance: 600, provision: 30, lossRate: 5,
          priorBalance: 500, priorProvision: 25, priorLossRate: 5,
        },
      ],
    },
  ],
  changeRows: [{ label: '合同资产', provision: 20, reversal: 5, writeOff: 0, reason: '账龄延长' }],
  notes: { 'D6-note-listed-text-1': '主要为工程施工合同资产。' },
}

describe('D6 载荷', () => {
  const p = buildD6SyncPayload('listed', 'wp-1', ['listed_standalone'], SNAPSHOT)
  const names = Object.keys(p.sub_table_data).filter((k) => !k.startsWith('_'))

  it('上市推 7 张固定表 + 逐组组合表', () => {
    expect(names).toEqual([
      D6_LISTED_SUBTABLE.main,
      D6_LISTED_SUBTABLE.majorChange,
      D6_LISTED_SUBTABLE.impairmentEnd,
      D6_LISTED_SUBTABLE.impairmentPrior,
      D6_LISTED_SUBTABLE.singleEnd,
      D6_LISTED_SUBTABLE.singlePrior,
      '组合计提项目：工程施工',
      D6_LISTED_SUBTABLE.change,
    ])
    for (const n of names) expect(p.columns[n], `${n} 缺 columns`).toBeDefined()
  })

  it('上年年末段真的带数据（旧实现整段缺失）', () => {
    const prior = p.sub_table_data[D6_LISTED_SUBTABLE.impairmentPrior] as any[]
    expect(prior[0]).toMatchObject({ balance_amount: 800, provision_amount: 80 })
    const singlePrior = p.sub_table_data[D6_LISTED_SUBTABLE.singlePrior] as any[]
    expect(singlePrior[0]).toMatchObject({ balance: 800, provision: 80 })
    const group = p.sub_table_data['组合计提项目：工程施工'] as any[]
    expect(group[0]).toMatchObject({
      end_balance: 600, end_provision: 30, prior_balance: 500, prior_provision: 25,
    })
  })

  it('账面价值缺省按 账面余额 − 减值准备 推导', () => {
    const end = p.sub_table_data[D6_LISTED_SUBTABLE.impairmentEnd] as any[]
    expect(end[0].book_value).toBe(900)
  })

  it('合计行字面取源模板（减值表 A54「合 计」，其余「合  计」）', () => {
    const end = p.sub_table_data[D6_LISTED_SUBTABLE.impairmentEnd] as any[]
    expect(end[end.length - 1]).toMatchObject({
      label: D6_NOTE_TOTAL_LABEL.impairment, is_total: true,
    })
    expect(D6_NOTE_TOTAL_LABEL.impairment).toBe('合 计')
    const change = p.sub_table_data[D6_LISTED_SUBTABLE.change] as any[]
    expect(change[change.length - 1]).toMatchObject({ label: D6_NOTE_TOTAL_LABEL.other })
  })

  it('「其中：」结构标签行不参与合计', () => {
    const withStructural = buildD6SyncPayload('listed', 'wp', null, {
      ...SNAPSHOT,
      impairmentProvisionRows: [
        { label: '按单项计提坏账准备', balance: 1000, ratio: 100, provision: 100, lossRate: 10 },
        { label: '其中：', balance: 1000, ratio: 100, provision: 100, lossRate: 10 },
      ],
    })
    const rows = withStructural.sub_table_data[D6_LISTED_SUBTABLE.impairmentEnd] as any[]
    expect(rows[rows.length - 1].balance_amount).toBe(1000)
  })

  it('改版前旧表名进 _removed_table_keys（含按当前组名推导的旧组合名）', () => {
    const removed = p.sub_table_data._removed_table_keys as string[]
    expect(removed).toContain('合同资产减值准备计提情况')
    expect(removed).toContain('按单项计提坏账准备的合同资产')
    expect(removed).toContain('续：')
    expect(removed).toContain('按组合计提坏账准备的合同资产：工程施工')
    // 不得把本次推送的表也删掉
    for (const n of names) expect(removed).not.toContain(n)
  })

  it('废弃表名与当前表名无交集', () => {
    const current = new Set(Object.values(D6_LISTED_SUBTABLE))
    for (const n of D6_OBSOLETE_TABLE_NAMES.listed) expect(current.has(n)).toBe(false)
  })

  it('国企推 3 表，sheet_name / section_id 正确', () => {
    const soe = buildD6SyncPayload('soe', 'wp-2', ['soe_standalone'], {
      classRows: SNAPSHOT.classRows,
      majorChangeRows: SNAPSHOT.majorChangeRows,
      soeImpairmentRows: [
        {
          label: '合同资产', priorBalance: 80, provision: 30,
          reversal: 5, writeOff: 5, endBalance: 100, reason: '账龄',
        },
      ],
      notes: {},
    })
    expect(Object.keys(soe.sub_table_data).filter((k) => !k.startsWith('_'))).toEqual([
      D6_SOE_SUBTABLE.main, D6_SOE_SUBTABLE.majorChange, D6_SOE_SUBTABLE.impairment,
    ])
    expect(soe.section_id).toBe('八、11')
    expect(soe.sheet_name).toBe('附注披露信息（国企）')
    const imp = soe.sub_table_data[D6_SOE_SUBTABLE.impairment] as any[]
    expect(imp[imp.length - 1]).toMatchObject({
      prior_balance: 80, provision: 30, reversal: 5, write_off: 5, end_balance: 100,
    })
  })
})

// ─── 主表二选一披露格式（源模板 A20「或：披露格式如下」）────────────────────

describe('D6 主表二选一披露格式', () => {
  const CLS = [
    {
      label: '单项计提坏账准备',
      endBookBalance: 1000, endImpairment: 100, endBookValue: 900,
      priorBookBalance: 800, priorImpairment: 80, priorBookValue: 720,
    },
    {
      label: '按组合计提坏账准备',
      endBookBalance: 500, endImpairment: 50, endBookValue: 450,
      priorBookBalance: 400, priorImpairment: 40, priorBookValue: 360,
    },
    // 派生行不得被二次汇总（🔴 判定先去空白：源模板写「小  计」）
    {
      label: '小  计',
      endBookBalance: 1500, endImpairment: 150, endBookValue: 1350,
      priorBookBalance: 1200, priorImpairment: 120, priorBookValue: 1080,
    },
    {
      label: '减：列示于其他非流动资产的合同资产',
      endBookBalance: 0, endImpairment: 0, endBookValue: 200,
      priorBookBalance: 0, priorImpairment: 0, priorBookValue: 100,
    },
  ]

  it('简化式行集与金额按源模板 A22-A26 派生', () => {
    expect(buildD6SimpleMainRows(CLS)).toEqual([
      { label: '合同资产', end_amount: 1500, prior_amount: 1200 },
      { label: '减：合同资产减值准备', end_amount: 150, prior_amount: 120 },
      { label: '小  计', end_amount: 1350, prior_amount: 1080, is_total: true },
      { label: '减：列示于其他非流动资产的合同资产', end_amount: 200, prior_amount: 100 },
      { label: '合  计', end_amount: 1150, prior_amount: 980, is_total: true },
    ])
  })

  it('切到简化式后主表列变单级 3 列且显式 flat（同名同表，无需 removed keys）', () => {
    const p = buildD6SyncPayload('listed', 'wp', null, { ...SNAPSHOT, mainFormat: 'simple' })
    const cols = p.columns[D6_LISTED_SUBTABLE.main]
    expect(cols.map((c) => c.label)).toEqual(['项  目', '期末余额', '上年年末余额'])
    expect(cols.some((c) => c.flat)).toBe(true)
    expect(cols.some((c) => c.group)).toBe(false)
    const removed = (p.sub_table_data._removed_table_keys as string[]) || []
    expect(removed).not.toContain(D6_LISTED_SUBTABLE.main)
  })

  it('缺省与显式 detailed 都走两级表头（7 列）', () => {
    for (const snap of [SNAPSHOT, { ...SNAPSHOT, mainFormat: 'detailed' as const }]) {
      const p = buildD6SyncPayload('listed', 'wp', null, snap)
      expect(p.columns[D6_LISTED_SUBTABLE.main]).toHaveLength(7)
      expect(p.columns[D6_LISTED_SUBTABLE.main].some((c) => c.group)).toBe(true)
    }
  })

  it('国企侧不受 mainFormat 影响（源模板无「或：」格式）', () => {
    const soe = buildD6SyncPayload('soe', 'wp', null, {
      classRows: SNAPSHOT.classRows,
      mainFormat: 'simple',
      notes: {},
    })
    expect(soe.columns[D6_SOE_SUBTABLE.main]).toHaveLength(7)
  })
})
