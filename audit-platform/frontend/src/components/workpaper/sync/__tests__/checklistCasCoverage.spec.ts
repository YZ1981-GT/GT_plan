import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

const SRC = resolve(__dirname, '../../../..')

const STRICT_FORM_DATA = [
  'components/workpaper/composables/useD4FormData.ts',
  'components/workpaper/composables/useF2FormData.ts',
  'components/workpaper/composables/useF2ValuationFormData.ts',
  'components/workpaper/composables/useF2SpecialFormData.ts',
  'components/workpaper/composables/useF2StocktakeFormData.ts',
  'components/workpaper/composables/useF3FormData.ts',
  'components/workpaper/composables/useF4FormData.ts',
  'components/workpaper/composables/useF5CosSalFormData.ts',
  'components/workpaper/composables/useG2IntRecFormData.ts',
  'components/workpaper/composables/useG4BonInvFormData.ts',
  'composables/workpaper/useChecklistPersistence.ts',
] as const

function source(relative: string): string {
  return readFileSync(resolve(SRC, relative), 'utf-8')
}

describe('双向宿主 checklist strict CAS 覆盖', () => {
  it.each(STRICT_FORM_DATA)('%s 通过单一 CAS helper 保存', (relative) => {
    const text = source(relative)
    expect(text, relative).toContain('createChecklistCasClient')
    expect(text, relative).not.toMatch(
      /api\.put\(`\/api\/workpapers\/\$\{[^}]+\}\/checklist-responses/,
    )
  })

  it('helper 固定 strict 请求且版本只从回执推进', () => {
    const text = source('composables/workpaper/checklistCas.ts')
    expect(text).toContain('require_if_match: true')
    expect(text).toContain('remember(result)')
    expect(text).not.toMatch(/Date\.now\(|new Date\(|randomUUID/)
  })
})
