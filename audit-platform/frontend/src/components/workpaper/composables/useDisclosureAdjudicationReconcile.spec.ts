/**
 * useDisclosureAdjudicationReconcile.spec — 审定↔披露差异告警纯计算测试
 * spec: d-cycle-disclosure-note-enhancement (Req1/Req2)
 * Property 1: 差异告警计算正确（no-data / warn / ok）
 * Property 4: 刷新后差异归零 → level 转 ok
 */
import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import { useDisclosureAdjudicationReconcile } from './useDisclosureAdjudicationReconcile'

describe('useDisclosureAdjudicationReconcile — Property 1 分级', () => {
  it('无审定合计（hasAudited=false）→ level=no-data，不误报差异', () => {
    const { level, message } = useDisclosureAdjudicationReconcile({
      auditedTotal: () => 0,
      disclosureTotal: () => 12345,
      hasAudited: () => false,
    })
    expect(level.value).toBe('no-data')
    expect(message.value).toContain('未取到审定表合计')
  })

  it('未提供 hasAudited 且审定合计为 0 → 视为 no-data', () => {
    const { level } = useDisclosureAdjudicationReconcile({
      auditedTotal: () => 0,
      disclosureTotal: () => 0,
    })
    expect(level.value).toBe('no-data')
  })

  it('|审定−披露| > 容差(默认1元) → warn', () => {
    const { level, diff, message } = useDisclosureAdjudicationReconcile({
      auditedTotal: () => 1000.5,
      disclosureTotal: () => 900,
    })
    expect(level.value).toBe('warn')
    expect(diff.value).toBeCloseTo(100.5, 2)
    expect(message.value).toContain('差异')
  })

  it('|审定−披露| ≤ 容差 → ok（核对一致）', () => {
    const { level, message } = useDisclosureAdjudicationReconcile({
      auditedTotal: () => 1000,
      disclosureTotal: () => 999.5,
    })
    expect(level.value).toBe('ok')
    expect(message.value).toContain('核对一致')
  })

  it('恰好等于容差边界(=1元) → ok（不 >tolerance）', () => {
    const { level } = useDisclosureAdjudicationReconcile({
      auditedTotal: () => 1001,
      disclosureTotal: () => 1000,
    })
    expect(level.value).toBe('ok')
  })

  it('自定义容差 tolerance=100', () => {
    const { level } = useDisclosureAdjudicationReconcile({
      auditedTotal: () => 1050,
      disclosureTotal: () => 1000,
      tolerance: 100,
    })
    expect(level.value).toBe('ok')
  })

  it('NaN / 非有限值兜底为 0，不抛错', () => {
    const { diff, level } = useDisclosureAdjudicationReconcile({
      auditedTotal: () => NaN,
      disclosureTotal: () => Number.POSITIVE_INFINITY,
      hasAudited: () => true,
    })
    expect(Number.isFinite(diff.value)).toBe(true)
    expect(diff.value).toBe(0)
    expect(level.value).toBe('ok')
  })
})

describe('useDisclosureAdjudicationReconcile — Property 4 刷新后归零', () => {
  it('披露合计被刷新为审定合计后 → diff→0，level 转 ok', () => {
    const disclosure = ref(800)
    const { level, diff } = useDisclosureAdjudicationReconcile({
      auditedTotal: () => 1000,
      disclosureTotal: () => disclosure.value,
    })
    expect(level.value).toBe('warn')
    expect(diff.value).toBe(200)
    // 模拟「从审定表刷新」：披露合计覆盖为审定合计
    disclosure.value = 1000
    expect(diff.value).toBe(0)
    expect(level.value).toBe('ok')
  })
})
