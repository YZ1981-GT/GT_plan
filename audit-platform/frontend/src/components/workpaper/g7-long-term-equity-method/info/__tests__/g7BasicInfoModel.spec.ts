import { describe, expect, it } from 'vitest'
import {
  accountingMethodFor,
  createG7BasicInfoRow,
  needsHoldingVotingReason,
  needsLessThanHalfControlReason,
  needsMajorityNoControlReason,
  normalizeG7BasicInfoRow,
  serializeG7BasicInfoRows,
  sourcesFromConsolScope,
  sourcesFromG7DetailPayload,
  syncG7BasicInfoFromSources,
  toPercentRatio,
  validateG7BasicInfoRows,
} from '../g7BasicInfoModel'

describe('G7-4 basic info model', () => {
  it('derives accounting method from the source relationship groups', () => {
    expect(accountingMethodFor('subsidiary')).toBe('成本法')
    expect(accountingMethodFor('joint_venture')).toBe('权益法')
    expect(accountingMethodFor('associate')).toBe('权益法')
    expect(accountingMethodFor('joint_operation')).toBe('各项单独确认')
  })

  it('migrates legacy fraction ratios to percent', () => {
    const row = normalizeG7BasicInfoRow({
      id: 'legacy',
      investeeName: '测试联营企业',
      controlType: '联营',
      investmentRatio: 0.3,
      votingRatio: 0.25,
      registeredAddress: '上海',
    }, 0)

    expect(row.groupType).toBe('associate')
    expect(row.accountingMethod).toBe('权益法')
    expect(row.directHoldingRatio).toBe(30)
    expect(row.votingRatio).toBe(25)
    expect(row.registeredPlace).toBe('上海')
  })

  it('keeps modern percent ratios when ratioScale is percent', () => {
    const row = normalizeG7BasicInfoRow({
      id: 'modern',
      groupType: 'associate',
      investeeName: '现代联营',
      directHoldingRatio: 30,
      votingRatio: 0.5,
      ratioScale: 'percent',
    }, 0)

    expect(row.directHoldingRatio).toBe(30)
    expect(row.votingRatio).toBe(0.5)
  })

  it('migrates missing-stamp fraction-looking ratios on modern rows', () => {
    const row = normalizeG7BasicInfoRow({
      id: 'ambiguous',
      groupType: 'joint_venture',
      investeeName: '合营缺stamp',
      directHoldingRatio: 0.4,
      votingRatio: 0.4,
    }, 0)
    expect(row.groupType).toBe('joint_venture')
    expect(row.directHoldingRatio).toBe(40)
    expect(row.votingRatio).toBe(40)
  })

  it('maps export long labels to groupType', () => {
    expect(normalizeG7BasicInfoRow({
      groupType: '合营企业（共同控制）',
      investeeName: '甲',
      ratioScale: 'percent',
      directHoldingRatio: 50,
    }, 0).groupType).toBe('joint_venture')
    expect(normalizeG7BasicInfoRow({
      groupType: '联营企业（重大影响）',
      investeeName: '乙',
      ratioScale: 'percent',
      directHoldingRatio: 20,
    }, 0).groupType).toBe('associate')
  })

  it('converts fraction ratios only when forced', () => {
    expect(toPercentRatio(0.3, { force: true })).toBe(30)
    expect(toPercentRatio(0.3)).toBe(0.3)
    expect(toPercentRatio(1, { force: true })).toBe(100)
  })

  it('requires explanations only when control logic is exceptional', () => {
    const subsidiary = createG7BasicInfoRow('subsidiary', 1, '子公司')
    subsidiary.directHoldingRatio = 45
    subsidiary.votingRatio = 40
    expect(needsHoldingVotingReason(subsidiary)).toBe(true)
    expect(needsLessThanHalfControlReason(subsidiary)).toBe(true)

    const associate = createG7BasicInfoRow('associate', 1, '联营企业')
    associate.directHoldingRatio = 55
    associate.votingRatio = 55
    expect(needsMajorityNoControlReason(associate)).toBe(true)

    const jointOperation = createG7BasicInfoRow('joint_operation', 1, '共同经营')
    jointOperation.directHoldingRatio = 60
    jointOperation.votingRatio = 30
    expect(needsHoldingVotingReason(jointOperation)).toBe(false)
    expect(needsMajorityNoControlReason(jointOperation)).toBe(false)
  })

  it('validates completeness and ratio bounds', () => {
    const row = createG7BasicInfoRow('subsidiary', 1, '甲公司')
    row.directHoldingRatio = 40
    row.indirectHoldingRatio = 70
    row.votingRatio = 40
    row.enterpriseType = '9'

    const issues = validateG7BasicInfoRows([row])
    expect(issues.some(issue => issue.message.includes('持股合计'))).toBe(true)
    expect(issues.some(issue => issue.message.includes('企业类型'))).toBe(true)
    expect(issues.some(issue => issue.message.includes('形成控制的原因'))).toBe(true)
  })

  it('syncs investees from G7-2 detail payload without overwriting filled fields', () => {
    const existing = [createG7BasicInfoRow('associate', 1, '联营A')]
    existing[0].directHoldingRatio = 20

    const sources = sourcesFromG7DetailPayload([
      {
        section: 'cost',
        investeeName: '子公司A',
        investmentRatio: 0.8,
        closingAmount: 1000,
        investmentMethod: '投资设立',
      },
      {
        section: 'equity',
        relationship: 'associate',
        investeeName: '联营A',
        investmentRatio: 0.35,
        closingAmount: 500,
        investmentMethod: '股权受让',
      },
      {
        section: 'equity',
        relationship: 'joint_venture',
        investeeName: '合营B',
        closingRatio: 0.5,
      },
    ])

    const result = syncG7BasicInfoFromSources(existing, sources)
    expect(result.added).toBe(2)
    expect(result.rows.map(row => row.investeeName).sort()).toEqual(['合营B', '子公司A', '联营A'])

    const associate = result.rows.find(row => row.investeeName === '联营A')!
    expect(associate.directHoldingRatio).toBe(20)
    expect(associate.acquisitionMethod).toBe('股权受让')

    const subsidiary = result.rows.find(row => row.investeeName === '子公司A')!
    expect(subsidiary.groupType).toBe('subsidiary')
    expect(subsidiary.directHoldingRatio).toBe(80)
    expect(subsidiary.investmentAmount).toBe(1000)
  })

  it('serializes ratioScale to prevent remigration', () => {
    const serialized = serializeG7BasicInfoRows([createG7BasicInfoRow('subsidiary', 1, '甲')])
    expect(serialized[0].ratioScale).toBe('percent')
  })

  describe('sourcesFromConsolScope (G7-4 从合并范围带入)', () => {
    it('skips rows with is_included=false or empty name', () => {
      const sources = sourcesFromConsolScope([
        { company_name: '子公司A', ownership_ratio: 60, is_included: true },
        { company_name: '被排除B', ownership_ratio: 30, is_included: false },
        { company_name: '', ownership_ratio: 50, is_included: true },
        { company_name: '  ', ownership_ratio: 40, is_included: true },
        { company_name: '正常C', ownership_ratio: 80, is_included: true },
      ])
      expect(sources.map(s => s.investeeName)).toEqual(['子公司A', '正常C'])
    })

    it('converts ownership_ratio to percent when all values look like fractions', () => {
      const sources = sourcesFromConsolScope([
        { company_name: '甲公司', ownership_ratio: 0.6, is_included: true },
        { company_name: '乙公司', ownership_ratio: 0.3, is_included: true },
      ])
      expect(sources[0].directHoldingRatio).toBe(60)
      expect(sources[1].directHoldingRatio).toBe(30)
    })

    it('keeps ownership_ratio as-is when any value exceeds 1 (already percent)', () => {
      const sources = sourcesFromConsolScope([
        { company_name: '甲公司', ownership_ratio: 60, is_included: true },
        { company_name: '乙公司', ownership_ratio: 30, is_included: true },
      ])
      expect(sources[0].directHoldingRatio).toBe(60)
      expect(sources[1].directHoldingRatio).toBe(30)
    })

    it('maps company_type to groupType', () => {
      const sources = sourcesFromConsolScope([
        { company_name: '联营甲', company_type: '联营企业', ownership_ratio: 30, is_included: true },
        { company_name: '合营乙', company_type: '合营企业', ownership_ratio: 50, is_included: true },
        { company_name: '子公司丙', company_type: '子公司', ownership_ratio: 80, is_included: true },
        { company_name: '无类型丁', ownership_ratio: 70, is_included: true },
      ])
      expect(sources[0].groupType).toBe('associate')
      expect(sources[1].groupType).toBe('joint_venture')
      expect(sources[2].groupType).toBe('subsidiary')
      expect(sources[3].groupType).toBe('subsidiary') // default
    })

    it('does not delete existing G7-4 rows and does not overwrite filled fields (Property 13)', () => {
      const existing = [
        createG7BasicInfoRow('subsidiary', 1, '子公司A'),
        createG7BasicInfoRow('joint_operation', 2, '共同经营X'), // 合并范围没有此行
      ]
      existing[0].directHoldingRatio = 55
      existing[0].acquisitionMethod = '投资设立'

      const scopeRows = [
        { company_name: '子公司A', ownership_ratio: 60, is_included: true, inclusion_reason: '股权受让' },
        { company_name: '新增子公司B', ownership_ratio: 80, is_included: true },
      ]
      const sources = sourcesFromConsolScope(scopeRows)
      const result = syncG7BasicInfoFromSources(existing, sources)

      // 不删除 G7-4 独有单位
      expect(result.rows.map(r => r.investeeName).sort()).toEqual(['共同经营X', '子公司A', '新增子公司B'])
      // 不覆盖已有值
      const a = result.rows.find(r => r.investeeName === '子公司A')!
      expect(a.directHoldingRatio).toBe(55) // 已有值不被覆盖
      expect(a.acquisitionMethod).toBe('投资设立') // 已有值不被覆盖
      // 新增行
      const b = result.rows.find(r => r.investeeName === '新增子公司B')!
      expect(b.directHoldingRatio).toBe(80)
      expect(b.groupType).toBe('subsidiary')
      expect(result.added).toBe(1)
    })

    it('serializes with ratioScale=percent after sync', () => {
      const existing = [createG7BasicInfoRow('subsidiary', 1, '子公司A')]
      const sources = sourcesFromConsolScope([
        { company_name: '子公司A', ownership_ratio: 60, is_included: true },
      ])
      const result = syncG7BasicInfoFromSources(existing, sources)
      const serialized = serializeG7BasicInfoRows(result.rows)
      expect(serialized.every(r => r.ratioScale === 'percent')).toBe(true)
    })

    it('returns empty sources when given empty or invalid input', () => {
      expect(sourcesFromConsolScope([])).toEqual([])
      expect(sourcesFromConsolScope(null as any)).toEqual([])
      expect(sourcesFromConsolScope(undefined as any)).toEqual([])
    })
  })
})
