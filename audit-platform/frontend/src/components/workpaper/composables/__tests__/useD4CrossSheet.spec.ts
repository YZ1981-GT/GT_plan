import { describe, expect, it } from 'vitest'
import { ref } from 'vue'
import { useD4CrossSheet } from '../useD4CrossSheet'
import type { ChecklistResponse, ProjectContext } from '../useD4FormData'

function getIpoGroupVisible(businessCategory?: string): boolean {
  const allResponses = ref<Map<string, ChecklistResponse>>(new Map())
  const projectContext = ref<ProjectContext>({ business_category: businessCategory })
  return useD4CrossSheet({ allResponses, projectContext }).ipoGroupVisible.value
}

describe('useD4CrossSheet IPO/舞弊组可见性', () => {
  it('通过 allowedCats 保留 fraud_risk', () => {
    expect(getIpoGroupVisible('fraud_risk_high')).toBe(true)
  })

  it('普通项目和空分类不可见', () => {
    expect(getIpoGroupVisible('normal')).toBe(false)
    expect(getIpoGroupVisible()).toBe(false)
  })

  it('保留核心 refinancing 基础行为', () => {
    expect(getIpoGroupVisible('refinancing')).toBe(true)
  })
})
