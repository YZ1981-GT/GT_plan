/**
 * useDeliverableLineage 单元测试
 *
 * Spec: deliverable-lineage-and-writeback Task 5.2/5.3
 * Requirements: 3.1, 3.5
 *
 * 测试覆盖：
 * - 锚点名 ↔ section_code 双向映射
 * - 无锚点降级
 */
import { describe, it, expect } from 'vitest'
import {
  sectionCodeFromAnchor,
  anchorNameFromSectionCode,
} from '@/composables/useDeliverableLineage'

describe('sectionCodeFromAnchor', () => {
  it('解析标准国企锚点 sec_八_1 → 八、1', () => {
    expect(sectionCodeFromAnchor('sec_八_1')).toBe('八、1')
  })

  it('解析上市公司锚点 sec_五_12 → 五、12', () => {
    expect(sectionCodeFromAnchor('sec_五_12')).toBe('五、12')
  })

  it('解析含多位数字锚点 sec_八_22 → 八、22', () => {
    expect(sectionCodeFromAnchor('sec_八_22')).toBe('八、22')
  })

  it('无 sec_ 前缀返回 null', () => {
    expect(sectionCodeFromAnchor('bookmark_1')).toBeNull()
    expect(sectionCodeFromAnchor('')).toBeNull()
  })

  it('sec_ 前缀后无内容返回 null', () => {
    expect(sectionCodeFromAnchor('sec_')).toBeNull()
  })
})

describe('anchorNameFromSectionCode', () => {
  it('标准国企 section_code → 锚点名', () => {
    expect(anchorNameFromSectionCode('八、1')).toBe('sec_八_1')
  })

  it('上市公司 section_code → 锚点名', () => {
    expect(anchorNameFromSectionCode('五、12')).toBe('sec_五_12')
  })

  it('含中间点分隔的 section_code', () => {
    expect(anchorNameFromSectionCode('八、1·2')).toBe('sec_八_1_2')
  })

  it('trim 前后空格', () => {
    expect(anchorNameFromSectionCode(' 八、1 ')).toBe('sec_八_1')
  })
})

describe('往返映射（Property 7 前端镜像）', () => {
  const testCodes = ['八、1', '五、12', '三、3', '八、22', '四、5']

  it.each(testCodes)(
    'section_code → anchor → section_code 往返一致: %s',
    (code) => {
      const anchor = anchorNameFromSectionCode(code)
      const restored = sectionCodeFromAnchor(anchor)
      expect(restored).toBe(code)
    },
  )
})
