import { describe, it, expect } from 'vitest'
import { buildH1ListedColumns } from '../h1DisclosureSyncPayload'
import { buildH8ListedColumns } from '../h8DisclosureSyncPayload'
import { buildG1SoeSyncPayloads, buildG1SyncPayload, buildG1ListedSubTableData } from '../g1DisclosureSyncPayload'
import { H1_LISTED_SUBTABLE } from '../h1NoteSectionMap'
import { H8_LISTED_SUBTABLE } from '../h8NoteSectionMap'
import { buildG7ListedColumns } from '../../g7-long-term-equity-main/disclosure/g7ListedDisclosureModel'
import { buildG7SoeColumns } from '../../g7-long-term-equity-main/disclosure/g7SoeDisclosureModel'

// disclosure-table-sync-convergence：H/G 循环披露列头锁定（防假绿）
describe('H/G 循环披露 _columns 覆盖', () => {
  it('H1 固定资产 listed 变动表列头随类别动态（项目 + 类别 + 合计）', () => {
    const cols = buildH1ListedColumns({
      categories: [{ key: 'building', label: '房屋建筑物' }, { key: 'machine', label: '机器设备' }],
    } as any)
    const mv = cols[H1_LISTED_SUBTABLE.movement]
    expect(mv[0].is_label).toBe(true)
    expect(mv.map((c) => c.label)).toEqual(['项目', '房屋建筑物', '机器设备', '合计'])
    // 附属子表源对齐
    expect(cols[H1_LISTED_SUBTABLE.idle].map((c) => c.label)).toEqual([
      '项目', '账面原值', '累计折旧', '减值准备', '账面价值', '备注',
    ])
  })

  it('H8 使用权资产 listed 变动表列头随类别动态', () => {
    const cols = buildH8ListedColumns({ categories: [{ key: 'house', label: '房屋' }] } as any)
    expect(cols[H8_LISTED_SUBTABLE.movement].map((c) => c.label)).toEqual(['项目', '房屋', '合计'])
  })

  it('G1 交易性金融资产 soe 附带源对齐列头（英文键映射）', () => {
    const [trading] = buildG1SoeSyncPayloads('wp-g1', null, {
      tradingRows: [], derivativeRows: [], fvBasisNote: '', derivativeTipNote: '', auditNote: '',
    })
    const cols = trading.columns!['交易性金融资产']
    expect(cols[0].is_label).toBe(true)
    expect(cols.map((c) => c.label)).toEqual(['项目', '期末公允价值', '期初公允价值'])
    expect(cols[1].key).toBe('end_fair_value')
  })

  it('G1 listed 分类表标签列键为「项目」（非 label）', () => {
    const payload = buildG1SyncPayload('listed', 'wp-g1', null, buildG1ListedSubTableData({
      classificationRows: [], designatedReason: '', derivativeRows: [], derivativeNote: '',
      fvRows: [], inputRows: [], l3Rows: [], amortRows: [], generalNote: '',
    } as any))
    const cls = payload!.columns!['交易性金融资产分类']
    expect(cls[0].is_label).toBe(true)
    expect(cls[0].key).toBe('项目')
    expect(cls.map((c) => c.label)).toEqual(['项目', '期末余额', '上年年末余额', '备注'])
  })

  it('G7 长期股权投资 listed/soe 列头由配置派生（每表首列为「项目」标签列）', () => {
    const listed = buildG7ListedColumns()
    const soe = buildG7SoeColumns()
    expect(Object.keys(listed).length).toBeGreaterThan(0)
    expect(Object.keys(soe).length).toBeGreaterThan(0)
    for (const defs of Object.values(listed)) {
      expect(defs[0].is_label).toBe(true)
      expect(defs[0].key).toBe('项目')
    }
    for (const defs of Object.values(soe)) {
      expect(defs[0].is_label).toBe(true)
      expect(defs[0].key).toBe('项目')
    }
    // 长期股权投资变动表列头源对齐（取自 movementColumns 配置）
    const mv = listed['长期股权投资']
    expect(mv.map((c) => c.label)).toContain('期初余额（账面价值）')
    expect(mv.map((c) => c.label)).toContain('期末余额（账面价值）')
  })
})
