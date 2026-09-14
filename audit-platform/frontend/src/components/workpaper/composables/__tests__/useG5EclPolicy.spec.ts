import { describe, expect, it } from 'vitest'
import {
  useG5EclPolicy,
  DEFAULT_G5_POLICY_GROUPS,
  G5_8_INDUSTRY_REFS,
} from '../useG5EclPolicy'
import { extractPolicyGroupNames } from '../g5ListedDisclosureRows'

describe('useG5EclPolicy', () => {
  it('默认预置四条长期应收款组合，可供附注同步', () => {
    const policy = useG5EclPolicy()
    expect(policy.section2.value).toHaveLength(DEFAULT_G5_POLICY_GROUPS.length)
    expect(policy.groupNames()).toEqual(DEFAULT_G5_POLICY_GROUPS.map((g) => g.name))
  })

  it('serialize/loadFromRaw 保留 paragraphs 与 section2', () => {
    const a = useG5EclPolicy()
    a.setParagraph('policy', '组合按业务类型划分')
    a.setParagraph('peer', '同业对比草稿')
    a.section2.value[0].checkItem = '融资租赁组合'
    a.section2.value[0].companyPolicy = '融资租赁组合'
    a.conclusion.value = 'A结论'
    const raw = a.serialize()

    const b = useG5EclPolicy()
    b.loadFromRaw(raw)
    expect(b.paragraphs.value.policy).toBe('组合按业务类型划分')
    expect(b.paragraphs.value.peer).toBe('同业对比草稿')
    expect(b.groupNames()[0]).toBe('融资租赁组合')
    expect(b.conclusion.value).toBe('A结论')
    expect(extractPolicyGroupNames(raw)).toContain('融资租赁组合')
  })

  it('applyIndustryRef 追加同业案例到第（四）节', () => {
    const policy = useG5EclPolicy()
    const ref = G5_8_INDUSTRY_REFS[0]
    policy.applyIndustryRef(ref)
    expect(policy.paragraphs.value.peer).toContain(ref.company)
    policy.applyIndustryRef(G5_8_INDUSTRY_REFS[1])
    expect(policy.paragraphs.value.peer).toContain(G5_8_INDUSTRY_REFS[1].company)
  })

  it('兼容旧存档：无 paragraphs 时不报错', () => {
    const policy = useG5EclPolicy()
    policy.loadFromRaw(JSON.stringify({
      section1: [{ id: 'x', checkItem: '模型', requirement: '', companyPolicy: '', compliance: '合规', explanation: '' }],
      section2: [{ id: 'y', checkItem: '账龄组合', requirement: '', companyPolicy: '账龄组合', compliance: '待核实', explanation: '' }],
      section3: [],
      section4: [],
      conclusion: '旧结论',
    }))
    expect(policy.groupNames()).toEqual(['账龄组合'])
    expect(policy.paragraphs.value.policy).toBe('')
    expect(policy.conclusion.value).toBe('旧结论')
  })
})
