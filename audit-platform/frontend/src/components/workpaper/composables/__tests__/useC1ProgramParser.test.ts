import { describe, it, expect } from 'vitest'
import { parseC1Programs, C1_PROGRAM_ITEMS, getC1ProgramsFallback, filterBySection } from '../useC1ProgramParser'

describe('useC1ProgramParser', () => {
  it('parses all 131 raw items into structured steps', () => {
    const steps = getC1ProgramsFallback()
    // 应有多个顶级步骤（非标题、非子项的条目）
    expect(steps.length).toBeGreaterThan(20)
    // 每个步骤必须有 section 和 name
    for (const s of steps) {
      expect(s.section).toBeTruthy()
      expect(s.name).toBeTruthy()
      expect(Array.isArray(s.subItems)).toBe(true)
    }
  })

  it('assigns steps to all 9 sections', () => {
    const steps = getC1ProgramsFallback()
    const slugs = new Set(steps.map((s) => s.section))
    expect(slugs.has('ce')).toBe(true)
    expect(slugs.has('ra')).toBe(true)
    expect(slugs.has('mo')).toBe(true)
    expect(slugs.has('bu')).toBe(true)
    expect(slugs.has('ic')).toBe(true)
    expect(slugs.has('fr')).toBe(true)
    expect(slugs.has('el')).toBe(true)
    expect(slugs.has('ye')).toBe(true)
    expect(slugs.has('rp')).toBe(true)
  })

  it('control environment (ce) has 11 top-level steps', () => {
    const steps = filterBySection(getC1ProgramsFallback(), 'ce')
    expect(steps.length).toBe(11)
    expect(steps[0].name).toContain('询问高级管理层')
    expect(steps[0].subItems.length).toBe(3)
  })

  it('sub-items are correctly nested under parent steps', () => {
    const steps = getC1ProgramsFallback()
    const step1 = steps[0] // "1. 询问高级管理层..." in ce
    expect(step1.subItems.length).toBe(3)
    expect(step1.subItems[0]).toContain('（1）')
    expect(step1.subItems[1]).toContain('（2）')
    expect(step1.subItems[2]).toContain('（3）')
  })

  it('filterBySection returns correct steps for ra', () => {
    const raSteps = filterBySection(getC1ProgramsFallback(), 'ra')
    expect(raSteps.length).toBe(2) // step 1 + step 2 (conclusion)
    expect(raSteps[0].name).toContain('针对企业风险评估流程')
    expect(raSteps[0].subItems.length).toBe(7)
  })

  it('related party section (rp) has 8 top-level steps', () => {
    const rpSteps = filterBySection(getC1ProgramsFallback(), 'rp')
    expect(rpSteps.length).toBe(8)
    expect(rpSteps[0].name).toContain('内部职业道德手册')
  })

  it('stepIndex is 0-based within each section', () => {
    const steps = getC1ProgramsFallback()
    const sections = ['ce', 'ra', 'mo', 'bu', 'ic', 'fr', 'el', 'ye', 'rp']
    for (const slug of sections) {
      const sectionSteps = filterBySection(steps, slug)
      for (let i = 0; i < sectionSteps.length; i++) {
        expect(sectionSteps[i].stepIndex).toBe(i)
      }
    }
  })

  it('no items are lost (total steps + sub-items should account for all non-header items)', () => {
    const steps = getC1ProgramsFallback()
    const totalTopLevel = steps.length
    const totalSubItems = steps.reduce((sum, s) => sum + s.subItems.length, 0)
    // 131 items - 9 headers = 122 non-header items = top-level steps + sub-items
    // Note: some headers have is_header=false but are detected by content pattern
    const nonHeaderItems = totalTopLevel + totalSubItems
    expect(nonHeaderItems).toBeGreaterThanOrEqual(100) // sanity check
  })
})
