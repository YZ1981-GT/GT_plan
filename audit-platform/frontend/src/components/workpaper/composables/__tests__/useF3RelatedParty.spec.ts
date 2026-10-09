import { describe, expect, it } from 'vitest'
import {
  computeRelatedPartyRow,
  emptyRelatedPartyRow,
  isBlankRelatedPartyRow,
  safeParseRelatedPartyRows,
} from '../useF3RelatedParty'

describe('F3-6 关联方票据余额与风险公式', () => {
  it('期末余额 = 期初 + 贷方发生 - 借方发生', () => {
    const row = computeRelatedPartyRow({
      ...emptyRelatedPartyRow(1),
      partyName: '甲关联方',
      relationship: '控股股东',
      noteType: '银行承兑汇票',
      openingBalance: 1_000_000,
      debitMovement: 300_000,
      creditMovement: 500_000,
      pricingPolicy: '市场定价',
      transactionReason: '采购材料',
      subsequentPaymentAmount: 200_000,
    }, 2_400_000)

    expect(row.closingBalance).toBe(1_200_000)
    expect(row.concentration).toBe(50)
    expect(row.riskFlags).toContain('关联方余额集中度较高')
  })

  it('识别关系、定价、款项性质和期后付款缺失风险', () => {
    const row = computeRelatedPartyRow({
      ...emptyRelatedPartyRow(1),
      partyName: '待核实方',
      creditMovement: 100_000,
    }, 100_000)

    expect(row.riskFlags).toContain('关联关系待核实')
    expect(row.riskFlags).toContain('定价政策未说明')
    expect(row.riskFlags).toContain('款项性质未说明')
    expect(row.riskFlags).toContain('无期后付款记录')
  })

  it('空白录入行不生成风险提示', () => {
    const row = computeRelatedPartyRow(emptyRelatedPartyRow(1))
    expect(isBlankRelatedPartyRow(row)).toBe(true)
    expect(row.riskFlags).toEqual([])
  })
})

describe('F3-6 旧数据迁移与空行修剪', () => {
  it('旧面值迁移为贷方发生并保持期末金额，旧用途迁移为款项性质', () => {
    const rows = safeParseRelatedPartyRows(JSON.stringify([{
      rowId: 'old-1',
      partyName: '乙关联方',
      relationship: '联营企业',
      noteType: '商业承兑',
      faceValue: 800_000,
      purpose: '采购设备',
      fairness: '公允',
      settlementMethod: '票据结算',
      auditEvaluation: '未见异常',
    }]))

    expect(rows).toHaveLength(1)
    expect(rows[0].creditMovement).toBe(800_000)
    expect(rows[0].closingBalance).toBe(800_000)
    expect(rows[0].transactionReason).toBe('采购设备')
    expect(rows[0].pricingPolicy).toBe('公允')
    expect(rows[0].remark).toContain('票据结算')
    expect(rows[0].remark).toContain('未见异常')
  })

  it('修剪多余空行并重排序号，全部为空时保留一行', () => {
    const rows = safeParseRelatedPartyRows(JSON.stringify([
      { rowId: 'blank-1' },
      { rowId: 'filled', partyName: '丙关联方', creditMovement: 10_000 },
      { rowId: 'blank-2' },
    ]))
    expect(rows).toHaveLength(1)
    expect(rows[0].partyName).toBe('丙关联方')
    expect(rows[0].seq).toBe(1)

    expect(safeParseRelatedPartyRows(JSON.stringify([{ rowId: 'blank' }]))).toHaveLength(1)
  })
})


describe('F3-6 行身份稳定性（sync 双向的硬前置）', () => {
  // 🔴 原实现 `rowId: raw.rowId || raw.id || generateRowId()` 会为缺 id 的行铸新 UUID，
  // 而 `loadRows()` **不回写** ⇒ 下次载入再铸一个新的，行身份每次都变。
  // 危害与 BP-7 的下标派生同型：OO↔HTML roundtrip 按行身份配对，身份漂移会把 A 行的值
  // 并进 B 行。修复 = `migrateRow` 记数（stats 出参）+ `loadRows` 在 minted>0 时立即 persist。
  // spec: f3-sync-coverage-and-first-canary · Task 13
  it('缺 rowId 的行会铸新身份，且通过 stats 出参上报（供调用方回写）', () => {
    const stats = { minted: 0 }
    const rows = safeParseRelatedPartyRows(
      JSON.stringify([
        { partyName: '无身份方甲', creditMovement: 1000 },
        { partyName: '无身份方乙', creditMovement: 2000 },
      ]),
      stats,
    )
    expect(rows).toHaveLength(2)
    expect(stats.minted).toBe(2)
    for (const row of rows) {
      expect(row.rowId).toMatch(/^f3rp-/)
      expect(row.rowId.trim()).not.toBe('')
    }
    expect(rows[0].rowId).not.toBe(rows[1].rowId)
  })

  it('已有 rowId 的行原样保留，minted 不计数', () => {
    const stats = { minted: 0 }
    const rows = safeParseRelatedPartyRows(
      JSON.stringify([
        { rowId: 'f3rp-keep-1', partyName: '有身份方', creditMovement: 500 },
      ]),
      stats,
    )
    expect(rows[0].rowId).toBe('f3rp-keep-1')
    expect(stats.minted).toBe(0)
  })

  it('兼容 legacy `id` 字段（视为已有身份，不铸新）', () => {
    const stats = { minted: 0 }
    const rows = safeParseRelatedPartyRows(
      JSON.stringify([{ id: 'legacy-7', partyName: '旧键方', creditMovement: 100 }]),
      stats,
    )
    expect(rows[0].rowId).toBe('legacy-7')
    expect(stats.minted).toBe(0)
  })

  it('空白 rowId（空串/纯空格）算缺身份，须铸新并计数', () => {
    const stats = { minted: 0 }
    const rows = safeParseRelatedPartyRows(
      JSON.stringify([
        { rowId: '', partyName: '空串身份', creditMovement: 10 },
        { rowId: '   ', partyName: '空格身份', creditMovement: 20 },
      ]),
      stats,
    )
    expect(stats.minted).toBe(2)
    for (const row of rows) expect(row.rowId).toMatch(/^f3rp-/)
  })

  it('行身份不随行序变化（不是下标派生）', () => {
    const payload = JSON.stringify([
      { rowId: 'f3rp-a', partyName: '甲', creditMovement: 1 },
      { rowId: 'f3rp-b', partyName: '乙', creditMovement: 2 },
    ])
    const first = safeParseRelatedPartyRows(payload)
    // 交换顺序后各行 rowId 必须跟着自己的业务值走，而不是跟位置走
    const swapped = safeParseRelatedPartyRows(
      JSON.stringify([
        { rowId: 'f3rp-b', partyName: '乙', creditMovement: 2 },
        { rowId: 'f3rp-a', partyName: '甲', creditMovement: 1 },
      ]),
    )
    expect(first[0].rowId).toBe('f3rp-a')
    expect(swapped[0].rowId).toBe('f3rp-b')
    const byId = new Map(swapped.map((r) => [r.rowId, r.partyName]))
    expect(byId.get('f3rp-a')).toBe('甲')
    expect(byId.get('f3rp-b')).toBe('乙')
  })

  it('stats 省略时不抛（向后兼容既有调用方）', () => {
    expect(() =>
      safeParseRelatedPartyRows(JSON.stringify([{ partyName: '无 stats', creditMovement: 1 }])),
    ).not.toThrow()
  })
})
