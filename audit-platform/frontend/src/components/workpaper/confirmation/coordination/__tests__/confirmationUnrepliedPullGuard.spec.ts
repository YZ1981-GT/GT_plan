/**
 * confirmationUnrepliedPullGuard.spec.ts — Unreplied_Pull 无桩残留守卫（Property 11）
 * + 复用共用能力守卫（Property 17）
 *
 * grep 式断言：
 * - D0-6 / F0-5 / F0-6 / K0-5 四个 Alternative_Sheet 组件不再含「待接入后启用」类桩文案
 * - 它们经 coordination/importFromSummary 或 composable importFromSummary 接入（不新造第二套）
 */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'

const __dirname = dirname(fileURLToPath(import.meta.url))
// coordination/__tests__ → confirmation 根
const CONFIRMATION_ROOT = resolve(__dirname, '..', '..')

const STUB_PATTERNS = [
  '待跨底稿引用',
  '待接入后启用',
  '待 dispatch persistence 接入',
]

const ALTERNATIVE_COMPONENTS: Array<{ file: string; label: string }> = [
  { file: 'alternativeF05/GtConfirmationAlternativeF05.vue', label: 'F0-5' },
  { file: 'alternativeF06/GtConfirmationAlternativeF06.vue', label: 'F0-6' },
  { file: 'alternativeD06/GtConfirmationAlternativeD06.vue', label: 'D0-6' },
  { file: 'alternativeK05/GtConfirmationAlternativeK05.vue', label: 'K0-5' },
]

function readComponent(rel: string): string {
  return readFileSync(resolve(CONFIRMATION_ROOT, rel), 'utf-8')
}

describe('Unreplied_Pull 守卫 (Property 11 / 17)', () => {
  for (const { file, label } of ALTERNATIVE_COMPONENTS) {
    it(`${label} 组件不含桩文案`, () => {
      const src = readComponent(file)
      for (const stub of STUB_PATTERNS) {
        expect(src, `${label} 仍含桩文案「${stub}」`).not.toContain(stub)
      }
    })
  }

  it('F0-5 / F0-6 / D0-6 经 coordination/importFromSummary 接入（Property 17）', () => {
    for (const { file } of ALTERNATIVE_COMPONENTS.filter((c) => c.label !== 'K0-5')) {
      const src = readComponent(file)
      expect(src, `${file} 未复用 importUnrepliedAsCompanies`).toContain('importUnrepliedAsCompanies')
    }
  })

  it('K0-5 经 composable importFromSummary 接入（Property 17）', () => {
    const src = readComponent('alternativeK05/GtConfirmationAlternativeK05.vue')
    expect(src).toContain('data.importFromSummary')
  })
})
