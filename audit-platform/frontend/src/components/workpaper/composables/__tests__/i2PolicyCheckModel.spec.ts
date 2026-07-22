/**
 * i2PolicyCheckModel — 单元测试
 */
import { describe, it, expect } from 'vitest'
import {
  normalizeCasItems,
  normalizeProcessItems,
  evaluateI2PolicyCompleteness,
  buildReasonablenessNarrative,
  emptyInterview,
  emptyCasItems,
  emptyProcessItems,
  emptyPeerRow,
  emptyReasonableness,
  I2_POLICY_DEFAULT_CONCLUSION,
} from '../i2PolicyCheckModel'

describe('i2PolicyCheckModel', () => {
  it('兼容旧 CAS 段落持久化', () => {
    const items = normalizeCasItems([
      {
        key: 'capitalization-policy',
        actualPolicy: '满足五条件资本化',
        evaluation: '符合',
        conclusion: '是',
      },
    ])
    const hit = items.find((i) => i.key === 'capitalization-policy')
    expect(hit?.actualPolicy).toBe('满足五条件资本化')
    expect(hit?.conclusion).toBe('是')
    expect(items.length).toBeGreaterThan(5)
  })

  it('流程核验项按预定义合并', () => {
    const items = normalizeProcessItems([
      { key: 'initiation', status: '是', evidence: '已阅立项书', indexRef: 'A1' },
    ])
    expect(items[0].label).toBe('立项报告')
    expect(items[0].status).toBe('是')
    expect(items[0].evidence).toBe('已阅立项书')
  })

  it('合理性叙述模板', () => {
    const text = buildReasonablenessNarrative({
      inspectedProjects: '项目甲、乙',
      policyTopic: '资本化时点',
      isReasonable: '是',
      reasons: '①有立项与可行性报告；②五条件可验证',
    })
    expect(text).toContain('项目甲、乙')
    expect(text).toContain('资本化时点')
    expect(text).toContain('是合理的')
    expect(text).toContain('①有立项')
  })

  it('完成度闸门：缺项时未达标', () => {
    const result = evaluateI2PolicyCompleteness({
      interview: emptyInterview(),
      processItems: emptyProcessItems(),
      casItems: emptyCasItems(),
      peerRows: [emptyPeerRow()],
      reasonableness: emptyReasonableness(),
      auditConclusion: '',
    })
    expect(result.ok).toBe(false)
    expect(result.progress).toBe(0)
  })

  it('完成度闸门：填齐后达标', () => {
    const cas = emptyCasItems().map((i) => ({ ...i, conclusion: '是' as const }))
    const process = emptyProcessItems().map((i, idx) => ({
      ...i,
      status: (idx < 4 ? '是' : '不适用') as const,
    }))
    const result = evaluateI2PolicyCompleteness({
      interview: emptyInterview({
        interviewee: '张总',
        rdProcessSummary: '立项后进入开发阶段',
      }),
      processItems: process,
      casItems: cas,
      peerRows: [emptyPeerRow({
        companyName: '同业A',
        capitalizationPolicy: '五条件资本化',
      })],
      reasonableness: emptyReasonableness({
        isReasonable: '是',
        reasons: '与准则及同业一致',
      }),
      auditConclusion: I2_POLICY_DEFAULT_CONCLUSION,
    })
    expect(result.ok).toBe(true)
    expect(result.progress).toBe(100)
  })
})
