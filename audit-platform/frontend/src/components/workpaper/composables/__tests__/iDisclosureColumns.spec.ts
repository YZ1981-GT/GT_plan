import { describe, it, expect } from 'vitest'
import { buildI4ListedSyncPayloads, buildI4SoeSyncPayloads } from '../i4DisclosureSyncPayload'
import { buildI5ListedSyncPayloads, buildI5SoeSyncPayloads } from '../i5DisclosureSyncPayload'
import { buildI6ListedSyncPayloads, buildI6SoeSyncPayloads } from '../i6DisclosureSyncPayload'
import { buildI1ListedColumns } from '../i1DisclosureSyncPayload'
import { buildI2ListedSyncPayloads, buildI2SoeSyncPayloads } from '../i2DisclosureSyncPayload'
import { buildI3ListedSyncPayloads, buildI3SoeSyncPayloads } from '../i3DisclosureSyncPayload'
import { I4_LISTED_SUBTABLE, I4_SOE_SUBTABLE } from '../i4NoteSectionMap'
import { I5_LISTED_SUBTABLE, I5_SOE_SUBTABLE } from '../i5NoteSectionMap'
import { I6_LISTED_SUBTABLE, I6_SOE_SUBTABLE } from '../i6NoteSectionMap'
import { I1_LISTED_SUBTABLE } from '../i1NoteSectionMap'
import { I2_LISTED_SUBTABLE, I2_SOE_SUBTABLE } from '../i2NoteSectionMap'
import { I3_LISTED_SUBTABLE, I3_SOE_SUBTABLE } from '../i3NoteSectionMap'

// disclosure-table-sync-convergence：I4/I5/I6 披露同步载荷携带源对齐列头
describe('I 循环披露 _columns 覆盖', () => {
  it('I4 长期待摊费用 listed/soe 附带源对齐变动表列头', () => {
    const [listed] = buildI4ListedSyncPayloads('wp-i4', null, { rows: [] })
    const lc = listed.columns![I4_LISTED_SUBTABLE.movement]
    expect(lc[0].is_label).toBe(true)
    expect(lc.map((c) => c.label)).toEqual(['项  目', '期初数', '本期增加', '本期摊销', '其他减少', '期末数'])
    expect(lc[3].group).toBe('本期减少')
    expect(lc[4].group).toBe('本期减少')

    const [soe] = buildI4SoeSyncPayloads('wp-i4', null, { rows: [] })
    const sc = soe.columns![I4_SOE_SUBTABLE.movement]
    expect(sc.map((c) => c.label)).toEqual([
      '项  目', '期初余额', '本期增加额', '本期摊销额', '其他减少额', '期末余额', '其他减少的原因',
    ])
    expect(sc.every((c) => c.flat)).toBe(true)
  })

  it('I5 其他非流动资产 listed=两级 7 列，soe=期末/年初 flat', () => {
    const [listed] = buildI5ListedSyncPayloads('wp-i5', null, { rows: [] })
    expect(listed.columns![I5_LISTED_SUBTABLE.main].map((c) => c.label)).toEqual([
      '项  目', '账面余额', '减值准备', '账面价值', '账面余额', '减值准备', '账面价值',
    ])
    expect(listed.columns![I5_LISTED_SUBTABLE.main][1].group).toBe('期末数')
    expect(listed.columns![I5_LISTED_SUBTABLE.main][4].group).toBe('上年年末数')

    const [soe] = buildI5SoeSyncPayloads('wp-i5', null, { rows: [] })
    expect(soe.columns![I5_SOE_SUBTABLE.main].map((c) => c.label)).toEqual([
      '项  目', '期末余额', '年初余额',
    ])
    expect(soe.columns![I5_SOE_SUBTABLE.main].every((c) => c.flat)).toBe(true)
  })

  it('I6 研发费用按性质表 listed/soe 同构（项目/本期发生额/上期发生额）', () => {
    const [listed] = buildI6ListedSyncPayloads('wp-i6', null, { rows: [] })
    expect(listed.columns![I6_LISTED_SUBTABLE.expenseByNature].map((c) => c.label)).toEqual([
      '项目', '本期发生额', '上期发生额',
    ])
    const [soe] = buildI6SoeSyncPayloads('wp-i6', null, { rows: [] })
    expect(soe.columns![I6_SOE_SUBTABLE.expenseByNature][0].is_label).toBe(true)
    expect(soe.columns![I6_SOE_SUBTABLE.expenseByNature].map((c) => c.label)).toEqual([
      '项目', '本期发生额', '上期发生额',
    ])
  })

  it('I1 无形资产 listed 变动表列头随类别动态（项目 + 类别 + 合计）', () => {
    const cols = buildI1ListedColumns({
      categories: [{ key: 'patent', label: '专利权' }, { key: 'software', label: '软件' }],
    } as any)
    const mv = cols[I1_LISTED_SUBTABLE.movement]
    expect(mv[0].is_label).toBe(true)
    expect(mv.map((c) => c.label)).toEqual(['项目', '专利权', '软件', '合计'])
    // 附属子表源对齐
    expect(cols['本期摊销费用归属'].map((c) => c.label)).toEqual([
      '项目', '生产成本', '制造费用', '销售费用', '管理费用', '研发费用', '其他', '合计',
    ])
  })

  it('I2 开发支出 listed/soe 变动表列头两级 group', () => {
    const [listed] = buildI2ListedSyncPayloads('wp-i2', null, {
      natureRows: [], movementRows: [], importantRows: [], impairmentRows: [],
      noteText: '', noteCap: '', noteImpairTest: '', notePurchased: '',
    })
    expect(listed.columns![I2_LISTED_SUBTABLE.nature].map((c) => c.label)).toEqual([
      '项  目', '本期费用化', '本期资本化', '上期费用化', '上期资本化',
    ])
    expect(listed.columns![I2_LISTED_SUBTABLE.nature].every((c) => c.flat)).toBe(true)

    expect(listed.columns![I2_LISTED_SUBTABLE.movement].map((c) => c.label)).toEqual([
      '项  目', '期初数', '内部开发支出', '其他增加',
      '确认为无形资产', '计入当期损益', '期末数',
      '资本化开始时点', '资本化依据', '研发进度',
    ])
    expect(listed.columns![I2_LISTED_SUBTABLE.movement][2].group).toBe('本期增加')
    expect(listed.columns![I2_LISTED_SUBTABLE.movement][4].group).toBe('本期减少')

    const [soe] = buildI2SoeSyncPayloads('wp-i2', null, { movementRows: [], noteText: '' })
    expect(soe.columns![I2_SOE_SUBTABLE.movement].map((c) => c.label)).toContain('其他减少')
    expect(soe.columns![I2_SOE_SUBTABLE.movement][2].group).toBe('本期增加')
    expect(soe.columns![I2_SOE_SUBTABLE.movement][4].group).toBe('本期减少')
  })

  it('I3 商誉 listed 两级表头（本期增加/本期减少含子列）+ soe flat 5 列', () => {
    const [listed] = buildI3ListedSyncPayloads('wp-i3', null, {
      bookValueRows: [], impairmentRows: [],
    })
    const bv = listed.columns![I3_LISTED_SUBTABLE.bookValue]
    expect(bv[0].label).toBe('被投资单位名称或形成商誉的事项')
    expect(bv.map((c) => c.label)).toEqual([
      '被投资单位名称或形成商誉的事项', '期初余额',
      '企业合并形成', '取得构成业务的共同经营的利益份额形成', '其他',
      '处置', '其他',
      '期末余额',
    ])
    expect(bv[2].group).toBe('本期增加')
    expect(bv[5].group).toBe('本期减少')

    // 减值表 7 列两级
    const imp = listed.columns![I3_LISTED_SUBTABLE.impairment]
    expect(imp.length).toBe(7)
    expect(imp[2].group).toBe('本期增加')
    expect(imp[4].group).toBe('本期减少')

    // 假设参数表（动态结构，不标 flat/group — 模板侧 headers[0] 为示例数据）
    expect(listed.columns![I3_LISTED_SUBTABLE.assumptions].map((c) => c.label)).toEqual([
      '资产组/业务', '毛利率', '增长率', '折现率',
    ])

    // SOE flat 5 列
    const [soe] = buildI3SoeSyncPayloads('wp-i3', null, { bookValueRows: [], impairmentRows: [] })
    expect(soe.columns![I3_SOE_SUBTABLE.impairment][0].label).toBe('被投资单位名称或形成商誉的事项')
    expect(soe.columns![I3_SOE_SUBTABLE.bookValue].every((c) => c.flat)).toBe(true)
    expect(soe.columns![I3_SOE_SUBTABLE.bookValue].length).toBe(5)
  })
})
