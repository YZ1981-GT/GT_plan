import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const dir = resolve(process.cwd(), 'src/components/workpaper/j2')
const source = (name: string) => readFileSync(resolve(dir, name), 'utf8')
const aiTabs = [
  'J2TabAdjudication.vue',
  'J2TabDetail.vue',
  'J2TabAdjustment.vue',
  'J2TabAccrualCheck.vue',
  'J2TabDisclosureListed.vue',
  'J2TabDisclosureSoe.vue',
]

describe('J2 Runtime Boundary migration', () => {
  it('delegates persistence and cross-cutting providers to the shared runtime', () => {
    const entry = source('GtJ2DefinedBenefitPlan.vue')
    expect(entry).toContain('useChecklistPersistence')
    expect(entry).toContain('persistence.saveDebounced(item_id, patch)')
    expect(entry).toContain('runtime?.version.scheduleAutoSnapshot()')
    expect(entry).toContain('watch(currentSheet')
    expect(entry).toContain('await persistence.flush()')
    expect(entry).not.toContain('useWorkpaperVersionToolbar')
    expect(entry).not.toContain('<GtWpVersionTrail')
    expect(entry).not.toContain("provide('jumpToSection'")
    expect(entry).not.toContain('http.put(')
  })

  it.each(aiTabs)('%s uses Runtime AI with string-only context', (name) => {
    const tab = source(name)
    expect(tab).toContain("inject<GenerateWorkpaperAiText>('generateAiText'")
    expect(tab).toContain('Record<string, string>')
    expect(tab).not.toContain('/ai/generate-text')
    expect(tab).not.toContain('setTimeout(')
  })

  it('uses full sheet names and bounded J2 codes for precise navigation', () => {
    const index = source('J2TabIndex.vue')
    const entry = source('GtJ2DefinedBenefitPlan.vue')
    expect(index).toContain("content: '审定表J2-1'")
    expect(index).toContain("content: '计提情况检查表J2-4'")
    expect(index).toContain("content: '附注披露信息（上市公司）'")
    expect(index).toContain("content: '附注披露信息（国有企业）'")
    expect(entry).toContain("J2-1(?!\\d)")
    expect(entry).not.toContain("sn.includes('J2-1')")
  })
})