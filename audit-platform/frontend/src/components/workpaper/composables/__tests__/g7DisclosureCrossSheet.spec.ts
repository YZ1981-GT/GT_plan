import { describe, expect, it } from 'vitest'
import {
  applyListedMinorityFsFromG75,
  applyListedMinoritySubsidiariesFromG74,
  applyListedMovementFromG72,
  applyListedSubsidiaryCompositionFromG74,
  applySoeClassificationFromG71,
  applySoeCommonControlFromG78,
  applySoeMinorityShareholdersFromG74,
  applySoeNonCommonControlFromG79,
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

  it('maps listed minority subsidiaries and FS from G7-4/5', () => {
    const listed = createG7ListedDisclosureState()
    const bundle = buildSourceBundleFromChecklistItems([
      {
        item_id: 'G7-4-rows',
        conclusion: JSON.stringify([
          {
            groupType: 'subsidiary',
            investeeName: '非全资子A',
            directHoldingRatio: 60,
            indirectHoldingRatio: 0,
          },
          {
            groupType: 'subsidiary',
            investeeName: '全资子B',
            directHoldingRatio: 100,
            indirectHoldingRatio: 0,
          },
        ]),
      },
      {
        item_id: 'G7-5-rows',
        conclusion: JSON.stringify({
          groups: [
            {
              investeeName: '非全资子A',
              rows: [
                { investeeName: '非全资子A', reportItem: '流动资产', priorAmount: 10, currentAmount: 12 },
                { investeeName: '非全资子A', reportItem: '非流动资产', priorAmount: 20, currentAmount: 22 },
                { investeeName: '非全资子A', reportItem: '总资产', priorAmount: 30, currentAmount: 34 },
                { investeeName: '非全资子A', reportItem: '流动负债', priorAmount: 4, currentAmount: 5 },
                { investeeName: '非全资子A', reportItem: '非流动负债', priorAmount: 6, currentAmount: 7 },
                { investeeName: '非全资子A', reportItem: '总负债', priorAmount: 10, currentAmount: 12 },
                { investeeName: '非全资子A', reportItem: '营业收入', priorAmount: 40, currentAmount: 50 },
                { investeeName: '非全资子A', reportItem: '净利润', priorAmount: 1, currentAmount: 2 },
                { investeeName: '非全资子A', reportItem: '所有者权益（净资产）', priorAmount: 18, currentAmount: 20 },
                { investeeName: '非全资子A', reportItem: '综合收益总额', priorAmount: 1.5, currentAmount: 2.5 },
                { investeeName: '非全资子A', reportItem: '经营活动现金流量', priorAmount: 3, currentAmount: 4 },
              ],
            },
          ],
        }),
      },
    ])

    expect(applyListedMinoritySubsidiariesFromG74(
      listed.tables['important-minority-subsidiaries'],
      bundle.basicInfo,
      true,
      bundle.financialInfo,
    )).toBe(true)
    expect(listed.tables['important-minority-subsidiaries'][0].label).toBe('非全资子A')
    expect(listed.tables['important-minority-subsidiaries'][0].values.holdingRatio).toBe(40)
    expect(listed.tables['important-minority-subsidiaries'][0].values.currentProfit).toBe(0.8)
    expect(listed.tables['important-minority-subsidiaries'][0].values.closingEquity).toBe(8)

    const filledFs = applyListedMinorityFsFromG75(
      {
        closing: listed.tables['minority-closing-balance'],
        opening: listed.tables['minority-opening-balance'],
        results: listed.tables['minority-results'],
      },
      bundle.financialInfo,
      bundle.basicInfo,
      true,
    )
    expect(filledFs).toEqual(expect.arrayContaining([
      'minority-closing-balance',
      'minority-opening-balance',
      'minority-results',
    ]))
    expect(listed.tables['minority-closing-balance'][0].values.currentAssets).toBe(12)
    expect(listed.tables['minority-opening-balance'][0].values.currentAssets).toBe(10)
    expect(listed.tables['minority-results'][0].values.currentRevenue).toBe(50)
    expect(listed.tables['minority-results'][0].values.priorProfit).toBe(1)

    const listedFresh = createG7ListedDisclosureState()
    const filled = refreshListedTablesFromSources(listedFresh.tables, bundle, true)
    expect(filled).toEqual(expect.arrayContaining([
      'important-minority-subsidiaries',
      'minority-closing-balance',
      'minority-opening-balance',
      'minority-results',
    ]))
  })

  it('maps G7-8/9 mergers and minority FS into SOE disclosure tables', () => {
    const soe = createG7SoeDisclosureState()
    const texts: Record<string, string> = {}
    const bundle = buildSourceBundleFromChecklistItems([
      {
        item_id: 'G7-4-rows',
        conclusion: JSON.stringify([
          {
            groupType: 'subsidiary',
            investeeName: '非全资子A',
            directHoldingRatio: 60,
            indirectHoldingRatio: 0,
          },
          {
            groupType: 'subsidiary',
            investeeName: '全资子B',
            directHoldingRatio: 100,
            indirectHoldingRatio: 0,
          },
        ]),
      },
      {
        item_id: 'G7-5-rows',
        conclusion: JSON.stringify({
          groups: [
            {
              investeeName: '非全资子A',
              rows: [
                { investeeName: '非全资子A', reportItem: '流动资产', priorAmount: 10, currentAmount: 12 },
                { investeeName: '非全资子A', reportItem: '净利润', priorAmount: 1, currentAmount: 2 },
              ],
            },
            {
              investeeName: '已处置子C',
              rows: [
                { investeeName: '已处置子C', reportItem: '流动资产', priorAmount: 5, currentAmount: 8 },
                { investeeName: '已处置子C', reportItem: '营业收入', priorAmount: 3, currentAmount: 4 },
              ],
            },
            {
              investeeName: '同控并入甲',
              rows: [
                { investeeName: '同控并入甲', reportItem: '营业收入', priorAmount: 0, currentAmount: 90 },
                { investeeName: '同控并入甲', reportItem: '净利润', priorAmount: 0, currentAmount: 15 },
                { investeeName: '同控并入甲', reportItem: '经营活动现金流量', priorAmount: 0, currentAmount: 12 },
              ],
            },
            {
              investeeName: '非同控并入乙',
              rows: [
                { investeeName: '非同控并入乙', reportItem: '营业收入', priorAmount: 0, currentAmount: 70 },
                { investeeName: '非同控并入乙', reportItem: '净利润', priorAmount: 0, currentAmount: 9 },
              ],
            },
          ],
        }),
      },
      {
        item_id: 'G7-8-rows',
        conclusion: JSON.stringify([
          {
            section: 'merger',
            investeeName: '同控并入甲',
            acquisitionDate: '2024-03-01',
            ownerEquityBookValue: 1000,
            totalConsideration: 800,
            finalController: '集团总部',
            accountingPolicyConsistent: '是',
          },
        ]),
      },
      {
        item_id: 'G7-9-rows',
        conclusion: JSON.stringify([
          {
            section: 'merger',
            investeeName: '非同控并入乙',
            acquisitionDate: '2024-06-15',
            acquisitionDateEvidenceRef: '董事会决议',
            ownershipRatio: 0.7,
            acquireeIdentifiableNetAssetsFV: 500,
            valuationReportRef: '评估报告A',
            totalConsiderationFV: 600,
            goodwill: 100,
          },
        ]),
      },
      {
        item_id: 'G7-12-rows',
        conclusion: JSON.stringify({
          rows: [
            {
              investeeName: '已处置子C',
              registeredPlace: '深圳',
              businessNature: '贸易',
              originalShareholdingRatio: 0.8,
              disposalReason: '出售',
              lossOfControlDate: '2024-09-30',
              lossOfControlBasis: '股权交割完成',
              residualFairValue: 200,
              residualBookValue: 150,
              remainingShareholdingRatio: 0.2,
              residualFairValueMethod: '市场法',
            },
          ],
        }),
      },
    ])

    expect(bundle.sourcesHit).toEqual(expect.arrayContaining(['G7-4', 'G7-5', 'G7-8', 'G7-9', 'G7-12']))
    expect(bundle.commonControlMergers?.[0]?.investeeName).toBe('同控并入甲')
    expect(bundle.nonCommonControlMergers?.[0]?.atCombinationHolding).toBe(70)

    expect(applySoeCommonControlFromG78(
      soe.tables['common-control-combination'],
      bundle.commonControlMergers!,
      true,
      bundle.financialInfo,
    )).toBe(true)
    expect(soe.tables['common-control-combination'][0].label).toBe('同控并入甲')
    expect(soe.tables['common-control-combination'][0].values.consideration).toBe(800)
    expect(soe.tables['common-control-combination'][0].values.revenue).toBe(90)
    expect(soe.tables['common-control-combination'][0].values.netProfit).toBe(15)

    expect(applySoeNonCommonControlFromG79(
      soe.tables['non-common-control-combination'],
      bundle.nonCommonControlMergers!,
      true,
      bundle.financialInfo,
    )).toBe(true)
    expect(soe.tables['non-common-control-combination'][0].values.goodwill).toBe(100)
    expect(soe.tables['non-common-control-combination'][0].values.atCombinationHolding).toBe(70)
    expect(soe.tables['non-common-control-combination'][0].values.postRevenue).toBe(70)

    expect(applySoeMinorityShareholdersFromG74(
      soe.tables['minority-shareholders'],
      bundle.basicInfo,
      true,
      bundle.financialInfo,
    )).toBe(true)
    expect(soe.tables['minority-shareholders'][0].label).toBe('非全资子A')
    expect(soe.tables['minority-shareholders'][0].values.holdingRatio).toBe(40)
    expect(soe.tables['minority-shareholders'][0].values.currentProfit).toBe(0.8)

    const soeFresh = createG7SoeDisclosureState()
    const filled = refreshSoeTablesFromSources(soeFresh.tables, bundle, true, texts)
    expect(filled).toEqual(expect.arrayContaining([
      'common-control-combination',
      'non-common-control-combination',
      'minority-shareholders',
      'minority-financials',
      'former-subsidiary-basic',
      'former-subsidiary-position',
      'former-subsidiary-results',
      'common-control-basis',
      'non-common-control-notes',
      'sale-date-method',
      'remaining-equity-remeasurement',
    ]))
    expect(soeFresh.tables['common-control-combination'][0].label).toBe('同控并入甲')
    expect(soeFresh.tables['minority-financials'].find(r => r.label === '流动资产')?.values.c1Current).toBe(12)
    expect(soeFresh.tables['former-subsidiary-position'].find(r => r.label === '流动资产')?.values.c1SaleDate).toBe(8)
    expect(texts['common-control-basis']).toContain('同控并入甲')
    expect(texts['non-common-control-notes']).toContain('非同控并入乙')
    expect(texts['sale-date-method']).toContain('股权交割完成')
    expect(texts['remaining-equity-remeasurement']).toContain('重新计量损益')
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

  it('fills policy-difference narratives from G7-6 inconsistent rows', () => {
    const bundle = buildSourceBundleFromChecklistItems([
      {
        item_id: 'G7-6-rows',
        conclusion: JSON.stringify({
          groups: [{
            investeeName: '联营丙',
            rows: [
              {
                isConsistent: '不一致',
                policyItem: '收入确认',
                adjustmentAmount: 120,
                adjustmentNote: '权责发生制差异',
              },
              { isConsistent: '一致', policyItem: '折旧', adjustmentAmount: 0 },
            ],
          }],
        }),
      },
    ])
    expect(bundle.sourcesHit).toContain('G7-6')
    expect(bundle.policyDifferences).toHaveLength(1)

    const listed = createG7ListedDisclosureState()
    const listedTexts: Record<string, string> = { ...listed.texts }
    const listedFilled = refreshListedTablesFromSources(listed.tables, bundle, true, listedTexts)
    expect(listedFilled).toContain('policy-differences')
    expect(listedTexts['policy-differences']).toContain('联营丙')
    expect(listedTexts['policy-differences']).toContain('收入确认')

    const soe = createG7SoeDisclosureState()
    const soeTexts: Record<string, string> = { ...soe.texts }
    const soeFilled = refreshSoeTablesFromSources(soe.tables, bundle, true, soeTexts)
    expect(soeFilled).toContain('policy-estimate-differences')
    expect(soeTexts['policy-estimate-differences']).toContain('G7-6')
  })

  it('fills control / impairment / ownership narratives without changing table structure', () => {
    const bundle = buildSourceBundleFromChecklistItems([
      {
        item_id: 'G7-4-rows',
        conclusion: JSON.stringify([
          {
            groupType: 'subsidiary',
            investeeName: '子控A',
            directHoldingRatio: 40,
            votingRatio: 55,
            holdingVotingDifferenceReason: '委托表决权安排',
            lessThanHalfControlReason: '董事会多数席位',
          },
          {
            groupType: 'joint_venture',
            investeeName: '合营丁',
            directHoldingRatio: 50,
            votingRatio: 50,
          },
        ]),
      },
      {
        item_id: 'G7-10-rows',
        conclusion: JSON.stringify({
          rows: [{
            section: 'nci',
            companyName: '子控A',
            costCash: 100,
            purchaseCost: 100,
            equityAdjustment: 20,
          }],
        }),
      },
      {
        item_id: 'G7-17-rows',
        conclusion: JSON.stringify([
          {
            investeeName: '合营丁',
            hasImpairmentSign: true,
            bookValue: 500,
            recoverableAmount: 420,
            impairmentAmount: 80,
            fvLessDisposalCost: 400,
            valueInUse: 420,
          },
        ]),
      },
    ])

    const listedTexts: Record<string, string> = {}
    const listed = createG7ListedDisclosureState()
    const listedFilled = refreshListedTablesFromSources(listed.tables, bundle, true, listedTexts)
    expect(listedFilled).toEqual(expect.arrayContaining([
      'subsidiary-control-judgement',
      'ownership-change-description',
      'impairment-method',
    ]))
    expect(listedTexts['subsidiary-control-judgement']).toContain('委托表决权安排')
    expect(listedTexts['ownership-change-description']).toContain('子控A')
    expect(listedTexts['impairment-method']).toContain('可收回金额 420')

    const soeTexts: Record<string, string> = {}
    const soe = createG7SoeDisclosureState()
    const soeFilled = refreshSoeTablesFromSources(soe.tables, bundle, true, soeTexts)
    expect(soeFilled).toEqual(expect.arrayContaining([
      'holding-voting-diff',
      'joint-control-basis',
      'ownership-change-description',
    ]))
    expect(soeTexts['joint-control-basis']).toContain('合营丁')
  })

  it('fills listed control judgement narrative from G7-7 overallConclusion', () => {
    const bundle = buildSourceBundleFromChecklistItems([
      {
        item_id: 'G7-7-control-judgment-data',
        conclusion: JSON.stringify({
          decision: {
            investeeName: '子甲',
            relationshipType: '控制',
            combinationType: '非同一控制下企业合并',
          },
          overallConclusion: '经审查，对子甲构成控制（来源 G7-7 测试）。',
        }),
      },
    ])
    expect(bundle.sourcesHit).toContain('G7-7')
    expect(bundle.controlJudgmentNarrative).toContain('对子甲构成控制')

    const texts: Record<string, string> = {}
    const listed = createG7ListedDisclosureState()
    const filled = refreshListedTablesFromSources(listed.tables, bundle, true, texts)
    expect(filled).toContain('subsidiary-control-judgement')
    expect(texts['subsidiary-control-judgement']).toContain('对子甲构成控制')
  })
})
