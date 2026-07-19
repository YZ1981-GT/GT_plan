import { describe, expect, it } from 'vitest'
import {
  applyListedMovementFromG72,
  applyListedSubsidiaryCompositionFromG74,
  applySoeClassificationFromG71,
  applySoeSubsidiaryBasicFromG74,
  buildSourceBundleFromChecklistItems,
  collectDisclosureTruncations,
  formatTruncationHint,
  parseG71Classification,
  refreshListedTablesFromSources,
  refreshSoeTablesFromSources,
} from '../g7DisclosureCrossSheet'
import { createG7ListedDisclosureState } from '../../g7-long-term-equity-main/disclosure/g7ListedDisclosureModel'
import { createG7SoeDisclosureState } from '../../g7-long-term-equity-main/disclosure/g7SoeDisclosureModel'

describe('g7DisclosureCrossSheet', () => {
  it('parses G7-1 adjudication groups into classification balances', () => {
    const classification = parseG71Classification({
      groups: [
        {
          id: 'subsidiary',
          rows: [
            { openingAdjusted: 10, debitAmount: 2, creditAmount: 1, closingAdjusted: 11 },
            { openingAdjusted: 20, debitAmount: 0, creditAmount: 0, closingAdjusted: 20 },
          ],
        },
        {
          id: 'joint_venture',
          rows: [{ openingAdjusted: 5, debitAmount: 1, creditAmount: 0, closingAdjusted: 6 }],
        },
        {
          id: 'associate',
          rows: [{ openingAdjusted: 8, debitAmount: 0, creditAmount: 2, closingAdjusted: 6 }],
        },
        {
          id: 'impairment',
          rows: [{ openingAdjusted: 1, debitAmount: 0.5, creditAmount: 0, closingAdjusted: 1.5 }],
        },
      ],
    })
    expect(classification?.subsidiary).toEqual({
      opening: 30,
      increase: 2,
      decrease: 1,
      closing: 31,
    })
    expect(classification?.jointVenture.closing).toBe(6)
    expect(classification?.associate.closing).toBe(6)
    expect(classification?.impairment.closing).toBe(1.5)
  })

  it('fills SOE classification and listed subsidiary composition from source bundle', () => {
    const soe = createG7SoeDisclosureState()
    const listed = createG7ListedDisclosureState()
    const bundle = buildSourceBundleFromChecklistItems([
      {
        item_id: 'G7-1-adjudication-data',
        remark: JSON.stringify({
          groups: [
            { id: 'subsidiary', rows: [{ openingAdjusted: 100, debitAmount: 0, creditAmount: 0, closingAdjusted: 100 }] },
            { id: 'joint_venture', rows: [{ openingAdjusted: 40, debitAmount: 0, creditAmount: 0, closingAdjusted: 40 }] },
            { id: 'associate', rows: [{ openingAdjusted: 20, debitAmount: 0, creditAmount: 0, closingAdjusted: 20 }] },
            { id: 'impairment', rows: [{ openingAdjusted: 5, debitAmount: 0, creditAmount: 0, closingAdjusted: 5 }] },
          ],
        }),
      },
      {
        item_id: 'G7-2-rows',
        conclusion: JSON.stringify([
          {
            section: 'equity',
            relationship: 'joint_venture',
            investeeName: '合营甲',
            openingAmount: 10,
            costIncrease: 1,
            profitLossAdjustment: 2,
            dividendReceived: 0,
            initialInvestmentCost: 9,
          },
          {
            section: 'equity',
            relationship: 'associate',
            investeeName: '联营乙',
            openingAmount: 30,
            profitLossAdjustment: 3,
            dividendReceived: 1,
            initialInvestmentCost: 28,
          },
        ]),
      },
      {
        item_id: 'G7-4-rows',
        conclusion: JSON.stringify([
          {
            groupType: 'subsidiary',
            investeeName: '子A',
            principalPlace: '上海',
            registeredPlace: '上海',
            businessNature: '制造',
            directHoldingRatio: 80,
            indirectHoldingRatio: 0,
            votingRatio: 80,
            investmentAmount: 1000,
            acquisitionMethod: '投资设立',
            level: '2',
            enterpriseType: '1',
            registeredCapital: 500,
          },
          {
            groupType: 'joint_venture',
            investeeName: '合营甲',
            principalPlace: '北京',
            registeredPlace: '北京',
            businessNature: '服务',
            directHoldingRatio: 50,
            accountingMethod: '权益法',
          },
        ]),
      },
    ])

    expect(bundle.sourcesHit).toEqual(['G7-1', 'G7-2', 'G7-4'])
    expect(applySoeClassificationFromG71(soe.tables['lte-classification'], bundle.classification!, true)).toBe(true)
    expect(soe.tables['lte-classification'].find(row => row.id === 'lte-sub')?.values.closing).toBe(100)
    expect(soe.tables['lte-classification'].find(row => row.id === 'lte-impairment')?.values.closing).toBe(5)

    expect(applySoeSubsidiaryBasicFromG74(
      soe.tables['subsidiary-basic'],
      bundle.basicInfo,
      bundle.detail,
      true,
    )).toBe(true)
    expect(soe.tables['subsidiary-basic'][0].label).toBe('子A')
    expect(soe.tables['subsidiary-basic'][0].values.investmentAmount).toBe(1000)

    expect(applyListedSubsidiaryCompositionFromG74(
      listed.tables['subsidiary-composition'],
      bundle.basicInfo,
      true,
    )).toBe(true)
    expect(listed.tables['subsidiary-composition'][0].label).toBe('子A')

    expect(applyListedMovementFromG72(listed.tables['investment-movement'], bundle.detail!, true)).toBe(true)
    expect(listed.tables['investment-movement'].find(row => row.id === 'joint-venture-1')?.label).toBe('合营甲')
    expect(listed.tables['investment-movement'].find(row => row.id === 'associate-1')?.values.closingBook).toBe(32)

    // Fresh state: orchestrator should fill multiple tables in one pass
    const soeFresh = createG7SoeDisclosureState()
    const listedFresh = createG7ListedDisclosureState()
    const soeFilled = refreshSoeTablesFromSources(soeFresh.tables, bundle, true)
    const listedFilled = refreshListedTablesFromSources(listedFresh.tables, bundle, true)
    expect(soeFilled).toContain('lte-classification')
    expect(soeFilled).toContain('lte-movement')
    expect(listedFilled).toContain('investment-movement')
    expect(listedFilled).toContain('subsidiary-composition')
  })

  it('does not overwrite filled cells when force=false', () => {
    const soe = createG7SoeDisclosureState()
    const sub = soe.tables['lte-classification'].find(row => row.id === 'lte-sub')!
    sub.values.closing = 999
    const classification = parseG71Classification({
      groups: [
        { id: 'subsidiary', rows: [{ openingAdjusted: 1, debitAmount: 0, creditAmount: 0, closingAdjusted: 1 }] },
        { id: 'joint_venture', rows: [] },
        { id: 'associate', rows: [] },
        { id: 'impairment', rows: [] },
      ],
    })!
    applySoeClassificationFromG71(soe.tables['lte-classification'], classification, false)
    expect(sub.values.closing).toBe(999)
    applySoeClassificationFromG71(soe.tables['lte-classification'], classification, true)
    expect(sub.values.closing).toBe(1)
  })
})

describe('g7DisclosureCrossSheet G7-5/12/16', () => {
  it('maps G7-5 financial info into listed and SOE metric tables', () => {
    const listed = createG7ListedDisclosureState()
    const soe = createG7SoeDisclosureState()
    const bundle = buildSourceBundleFromChecklistItems([
      {
        item_id: 'G7-4-rows',
        conclusion: JSON.stringify([
          { groupType: 'joint_venture', investeeName: '合营甲' },
          { groupType: 'associate', investeeName: '联营乙' },
        ]),
      },
      {
        item_id: 'G7-5-rows',
        conclusion: JSON.stringify({
          groups: [
            {
              investeeName: '合营甲',
              rows: [
                { investeeName: '合营甲', reportItem: '流动资产', priorAmount: 10, currentAmount: 12 },
                { investeeName: '合营甲', reportItem: '总资产', priorAmount: 50, currentAmount: 60 },
                { investeeName: '合营甲', reportItem: '净利润', priorAmount: 3, currentAmount: 4 },
              ],
            },
            {
              investeeName: '联营乙',
              rows: [
                { investeeName: '联营乙', reportItem: '流动资产', priorAmount: 20, currentAmount: 22 },
                { investeeName: '联营乙', reportItem: '净利润', priorAmount: 5, currentAmount: 6 },
              ],
            },
          ],
        }),
      },
    ])
    expect(bundle.sourcesHit).toContain('G7-5')
    const listedFilled = refreshListedTablesFromSources(listed.tables, bundle, true)
    expect(listedFilled).toContain('important-jv-balance')
    const jvCurrentAssets = listed.tables['important-jv-balance'].find(r => r.label === '流动资产')
    expect(jvCurrentAssets?.values.current).toBe(12)
    expect(jvCurrentAssets?.values.prior).toBe(10)
    const assetTotal = listed.tables['important-jv-balance'].find(r => r.label === '资产合计')
    expect(assetTotal?.values.current).toBe(60)
    const assocCurrent = listed.tables['important-associate-balance'].find(r => r.label === '流动资产')
    expect(assocCurrent?.values.company1Current).toBe(22)

    const soeFilled = refreshSoeTablesFromSources(soe.tables, bundle, true)
    expect(soeFilled).toContain('important-jv-fs')
    expect(soe.tables['important-jv-fs'].find(r => r.label === '流动资产')?.values.current).toBe(12)
  })

  it('fills former subsidiaries from G7-12 and unrecognized losses from G7-16', () => {
    const soe = createG7SoeDisclosureState()
    const listed = createG7ListedDisclosureState()
    const bundle = buildSourceBundleFromChecklistItems([
      {
        item_id: 'G7-4-rows',
        conclusion: JSON.stringify([
          { groupType: 'joint_venture', investeeName: '合营亏' },
          { groupType: 'associate', investeeName: '联营亏' },
        ]),
      },
      {
        item_id: 'G7-12-rows',
        conclusion: JSON.stringify([
          {
            investeeName: '原子公司A',
            registeredPlace: '深圳',
            businessNature: '贸易',
            originalShareholdingRatio: 70,
            votingRatio: 70,
            disposalReason: '股权转让',
          },
        ]),
      },
      {
        item_id: 'G7-16-rows',
        conclusion: JSON.stringify({
          rows: [
            { investeeName: '合营亏', unrecognizedLoss: 15, currentChange: 5 },
            { investeeName: '联营亏', unrecognizedLoss: 8, currentChange: 2 },
          ],
        }),
      },
    ])
    expect(bundle.sourcesHit).toEqual(expect.arrayContaining(['G7-12', 'G7-16']))
    const soeFilled = refreshSoeTablesFromSources(soe.tables, bundle, true)
    expect(soeFilled).toContain('former-subsidiary-basic')
    expect(soe.tables['former-subsidiary-basic'][0].label).toBe('原子公司A')
    expect(soe.tables['former-subsidiary-basic'][0].values.registeredPlace).toBe('深圳')
    expect(soeFilled).toContain('unrecognized-losses')
    expect(soe.tables['unrecognized-losses'].find(r => r.id === 'ul-jv-1')?.values.currentUnrecognized).toBe(5)
    expect(soe.tables['unrecognized-losses'].find(r => r.id === 'ul-jv-1')?.values.closingCumulative).toBe(15)
    expect(soe.tables['unrecognized-losses'].find(r => r.id === 'ul-jv-1')?.values.priorCumulative).toBe(10)

    const listedFilled = refreshListedTablesFromSources(listed.tables, bundle, true)
    expect(listedFilled).toContain('excess-losses')
    expect(listed.tables['excess-losses'].find(r => r.id === 'el-assoc-1')?.label).toBe('联营亏')
  })

  it('fills ownership-change-impact from G7-10 NCI / partial disposal rows', () => {
    const listed = createG7ListedDisclosureState()
    const soe = createG7SoeDisclosureState()
    const bundle = buildSourceBundleFromChecklistItems([
      {
        item_id: 'G7-10-rows',
        conclusion: JSON.stringify({
          rows: [
            {
              section: 'nci',
              companyName: '子公司甲',
              costCash: 100,
              costNonCashFV: 20,
              purchaseCost: 120,
              shareOfNetAssets: 80,
              equityAdjustment: 40,
              adjCapitalReserve: 30,
              adjSurplusReserve: 5,
              adjRetainedEarnings: 5,
            },
            {
              section: 'partialDisposal',
              companyName: '子公司乙',
              considerationCash: 50,
              consideration: 50,
              consolShare: 35,
              consolEquityAdj: 15,
              adjCapitalReserve: 15,
            },
          ],
        }),
      },
      {
        item_id: 'G7-2-rows',
        conclusion: JSON.stringify([
          {
            section: 'equity',
            relationship: 'joint_venture',
            investeeName: '合营甲',
            openingAmount: 200,
          },
          {
            section: 'equity',
            relationship: 'associate',
            investeeName: '联营乙',
            openingAmount: 90,
          },
        ]),
      },
    ])
    expect(bundle.sourcesHit).toEqual(expect.arrayContaining(['G7-10', 'G7-2']))
    expect(bundle.ownershipImpacts).toHaveLength(2)

    const listedFilled = refreshListedTablesFromSources(listed.tables, bundle, true)
    expect(listedFilled).toContain('ownership-change-impact')
    const cashRow = listed.tables['ownership-change-impact'].find(r => r.label === '现金')
    expect(cashRow?.values.company1).toBe(100)
    expect(cashRow?.values.company2).toBe(50)
    const totalRow = listed.tables['ownership-change-impact'].find(r => r.label === '购买成本/处置对价合计')
    expect(totalRow?.values.company1).toBe(120)
    expect(totalRow?.values.company2).toBe(50)
    expect(listedFilled).toContain('unimportant-aggregate')
    expect(listed.tables['unimportant-aggregate'].find(r => r.id === 'ua-jv-carrying')?.values.current).toBe(200)
    expect(listed.tables['unimportant-aggregate'].find(r => r.id === 'ua-jv-carrying')?.values.prior).toBe(200)
    expect(listed.tables['unimportant-aggregate'].find(r => r.id === 'ua-assoc-carrying')?.values.current).toBe(90)

    const soeFilled = refreshSoeTablesFromSources(soe.tables, bundle, true)
    expect(soeFilled).toContain('ownership-change-impact')
    expect(soe.tables['ownership-change-impact'].find(r => r.label === '现金')?.values.company1).toBe(100)
    expect(soeFilled).toContain('insignificant-aggregate')
    expect(soe.tables['insignificant-aggregate'].find(r => r.id === 'agg-jv-carrying')?.values.current).toBe(200)
    expect(soe.tables['insignificant-aggregate'].find(r => r.id === 'agg-jv-carrying')?.values.prior).toBe(200)
  })

  it('fills unimportant aggregate share from G7-2 and excludes important investees', () => {
    const listed = createG7ListedDisclosureState()
    const bundle = buildSourceBundleFromChecklistItems([
      {
        item_id: 'G7-4-rows',
        conclusion: JSON.stringify([
          { investeeName: '重要合营', groupType: 'joint_venture', directHoldingRatio: 50 },
          { investeeName: '次要合营', groupType: 'joint_venture', directHoldingRatio: 40 },
          { investeeName: '联营甲', groupType: 'associate', directHoldingRatio: 30 },
        ]),
      },
      {
        item_id: 'G7-2-rows',
        conclusion: JSON.stringify([
          {
            section: 'equity',
            relationship: 'joint_venture',
            investeeName: '重要合营',
            openingAmount: 1000,
            profitLossAdjustment: 100,
            otherComprehensiveIncome: 20,
          },
          {
            section: 'equity',
            relationship: 'joint_venture',
            investeeName: '次要合营',
            openingAmount: 400,
            profitLossAdjustment: 40,
            otherComprehensiveIncome: 8,
          },
          {
            section: 'equity',
            relationship: 'associate',
            investeeName: '联营甲',
            openingAmount: 200,
            profitLossAdjustment: 15,
            otherComprehensiveIncome: 3,
          },
        ]),
      },
    ])
    const filled = refreshListedTablesFromSources(listed.tables, bundle, true)
    expect(filled).toContain('unimportant-aggregate')
    expect(listed.tables['unimportant-aggregate'].find(r => r.id === 'ua-jv-carrying')?.values.current).toBe(448)
    expect(listed.tables['unimportant-aggregate'].find(r => r.id === 'ua-jv-profit')?.values.current).toBe(40)
    expect(listed.tables['unimportant-aggregate'].find(r => r.id === 'ua-jv-oci')?.values.current).toBe(8)
    expect(listed.tables['unimportant-aggregate'].find(r => r.id === 'ua-jv-comprehensive')?.values.current).toBe(48)
    expect(listed.tables['unimportant-aggregate'].find(r => r.id === 'ua-assoc-carrying')?.values.current).toBe(0)
  })

  it('fills equity-method bridge rows from G7-14', () => {
    const listed = createG7ListedDisclosureState()
    const soe = createG7SoeDisclosureState()
    const bundle = buildSourceBundleFromChecklistItems([
      {
        item_id: 'G7-4-rows',
        conclusion: JSON.stringify([
          { investeeName: '合营甲', groupType: 'joint_venture' },
          { investeeName: '联营乙', groupType: 'associate' },
        ]),
      },
      {
        item_id: 'G7-14-equity-method-calc',
        remark: JSON.stringify({
          rows: [
            {
              investeeName: '合营甲',
              shareOfAuditedNetAssets: 800,
              netAssetShareVariance: 50,
              goodwill: 40,
              impairment: 5,
              cumulativeFvAdj: 3,
              unexplainedVariance: 2,
              lteiBookBalance: 850,
            },
            {
              investeeName: '联营乙',
              shareOfAuditedNetAssets: 300,
              netAssetShareVariance: 20,
              goodwill: 15,
              lteiBookBalance: 320,
            },
          ],
          netAssetAdjustments: [
            {
              investeeName: '合营甲',
              unrealizedInternalElim: { begin: 10, increase: 0, decrease: 0 },
            },
          ],
        }),
      },
    ])
    expect(bundle.sourcesHit).toContain('G7-14')
    expect(bundle.equityBridge).toHaveLength(2)

    const listedFilled = refreshListedTablesFromSources(listed.tables, bundle, true)
    expect(listedFilled).toEqual(expect.arrayContaining(['important-jv-balance', 'important-associate-balance']))
    const jvShare = listed.tables['important-jv-balance'].find(r => r.label === '按持股比例计算的净资产份额')
    expect(jvShare?.values.current).toBe(800)
    expect(jvShare?.source).toBe('权益法测算G7-14')
    expect(listed.tables['important-jv-balance'].find(r => r.label === '其中：商誉')?.values.current).toBe(40)
    expect(listed.tables['important-jv-balance'].find(r => r.label === '其中：商誉')?.source).toBe('权益法测算G7-14')
    expect(listed.tables['important-jv-balance'].find(r => r.label === '未实现内部交易损益')?.values.current).toBe(10)
    expect(listed.tables['important-jv-balance'].find(r => r.label === '对合营企业权益投资的账面价值')?.values.current).toBe(850)
    expect(listed.tables['important-jv-balance'].find(r => r.label === '流动资产')?.source).toContain('G7-5')
    expect(
      listed.tables['important-associate-balance'].find(r => r.label === '按持股比例计算的净资产份额')?.values.company1Current,
    ).toBe(300)

    const soeFilled = refreshSoeTablesFromSources(soe.tables, bundle, true)
    expect(soeFilled).toContain('important-jv-fs')
    expect(soe.tables['important-jv-fs'].find(r => r.label === '调整事项')?.values.current).toBe(50)
    expect(soe.tables['important-jv-fs'].find(r => r.label === '调整事项')?.source).toBe('权益法测算G7-14')
    expect(soe.tables['important-jv-fs'].find(r => r.label === '对合营企业权益投资的账面价值')?.values.current).toBe(850)
    expect(soeFilled).toContain('important-associate-fs')
    expect(soe.tables['important-associate-fs'].find(r => r.label === '按持股比例计算的净资产份额')?.values.a1Current).toBe(300)
  })

  it('reports truncation when important investees exceed disclosure column capacity', () => {
    const bundle = buildSourceBundleFromChecklistItems([
      {
        item_id: 'G7-4-rows',
        conclusion: JSON.stringify([
          { investeeName: '联1', groupType: 'associate' },
          { investeeName: '联2', groupType: 'associate' },
          { investeeName: '联3', groupType: 'associate' },
          { investeeName: '联4', groupType: 'associate' },
        ]),
      },
      {
        item_id: 'G7-10-rows',
        conclusion: JSON.stringify({
          rows: Array.from({ length: 7 }, (_, i) => ({
            section: 'nci',
            companyName: `子公司${i + 1}`,
            costCash: 10,
            purchaseCost: 10,
          })),
        }),
      },
    ])
    const listed = collectDisclosureTruncations(bundle, 'listed')
    expect(listed.some(t => t.label === '重要联营企业' && t.omitted === 1)).toBe(true)
    expect(listed.some(t => t.label === '所有权变动交易' && t.omitted === 1)).toBe(true)
    expect(formatTruncationHint(listed)).toContain('超过披露列容量')

    const soe = collectDisclosureTruncations(bundle, 'soe')
    expect(soe.some(t => t.label === '重要联营企业' && t.omitted === 2)).toBe(true)
    expect(soe.some(t => t.label === '所有权变动交易' && t.omitted === 4)).toBe(true)
  })
})
