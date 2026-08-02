/**
 * K3~K13 科目码单一真源守卫。
 *
 * Property 9：前端源码不得出现该循环的**错误**科目码作科目码/请求参数/事件载荷。
 * Property 10：每个循环的 `tb_source_codes` 至少有一个前端消费点。
 * Property 24：`buildXColumns` 零入参可调（由 disclosureColumnsCoverage 覆盖，此处只验 scope）。
 *
 * spec: .kiro/specs/k-cycle-four-table-extraction-and-disclosure-completion/
 *       Task 22 / Requirements 5.2, 4.2, 4.4
 */

import { describe, it, expect } from 'vitest'
import * as fs from 'node:fs'
import * as path from 'node:path'

const COMPOSABLES = path.resolve(__dirname, '..')
const WORKPAPER = path.resolve(COMPOSABLES, '..')

function read(relPath: string): string {
  return fs.readFileSync(path.resolve(WORKPAPER, relPath), 'utf-8')
}

function stripComments(src: string): string {
  // Strip single-line comments
  let out = src.replace(/\/\/[^\n]*/g, '')
  // Strip block comments
  out = out.replace(/\/\*[\s\S]*?\*\//g, '')
  // Strip template literals that are just documentation (backtick strings containing only text)
  return out
}

// ─── K cycle config ─────────────────────────────────────────────────────────

interface KCycleConfig {
  code: string
  fallback: string
  forbiddenCodes: string[] // codes that must NOT appear in source
  hostFile: string // relative to WORKPAPER
  tabFile: string // adjudication tab relative to WORKPAPER
  scopeFile: string // accountScope relative to COMPOSABLES
}

const CYCLES: KCycleConfig[] = [
  { code: 'K3', fallback: '2241', forbiddenCodes: ['6603'], hostFile: 'GtK3OtherPayables.vue', tabFile: 'k3/core/K3TabAdjudication.vue', scopeFile: 'k3AccountScope.ts' },
  { code: 'K4', fallback: '', forbiddenCodes: ['2245', '2301'], hostFile: 'GtK4OtherCurrentLiabilities.vue', tabFile: 'k4/core/K4TabAdjudication.vue', scopeFile: 'k4AccountScope.ts' },
  { code: 'K5', fallback: '2801', forbiddenCodes: ['2701'], hostFile: 'GtK5Provisions.vue', tabFile: 'k5/core/K5TabAdjudication.vue', scopeFile: 'k5AccountScope.ts' },
  { code: 'K6', fallback: '', forbiddenCodes: ['1481', '2605', '2331'], hostFile: 'GtK6HeldForSale.vue', tabFile: 'k6/core/K6TabAdjudication.vue', scopeFile: 'k6AccountScope.ts' },
  { code: 'K7', fallback: '2401', forbiddenCodes: ['1123'], hostFile: 'GtK7DeferredIncome.vue', tabFile: 'k7/core/K7TabAdjudication.vue', scopeFile: 'k7AccountScope.ts' },
  { code: 'K8', fallback: '6601', forbiddenCodes: [], hostFile: 'GtK8SellingExpenses.vue', tabFile: 'k8/core/K8TabAdjudication.vue', scopeFile: 'k8AccountScope.ts' },
  { code: 'K9', fallback: '6602', forbiddenCodes: [], hostFile: 'GtK9AdminExpenses.vue', tabFile: 'k9/core/K9TabAdjudication.vue', scopeFile: 'k9AccountScope.ts' },
  { code: 'K10', fallback: '6117', forbiddenCodes: ['6301'], hostFile: 'GtK10OtherIncome.vue', tabFile: 'k10/core/K10TabAdjudication.vue', scopeFile: 'k10AccountScope.ts' },
  { code: 'K11', fallback: '6701', forbiddenCodes: ['6711'], hostFile: 'GtK11AssetImpairmentLoss.vue', tabFile: 'k11/core/K11TabAdjudication.vue', scopeFile: 'k11AccountScope.ts' },
  { code: 'K12', fallback: '6301', forbiddenCodes: ['6701'], hostFile: 'GtK12NonOperatingIncome.vue', tabFile: 'k12/core/K12TabAdjudication.vue', scopeFile: 'k12AccountScope.ts' },
  { code: 'K13', fallback: '6711', forbiddenCodes: ['6702'], hostFile: 'GtK13NonOperatingExpense.vue', tabFile: 'k13/core/K13TabAdjudication.vue', scopeFile: 'k13AccountScope.ts' },
]

// ─── Tests ──────────────────────────────────────────────────────────────────

describe('K cycle account scope files exist', () => {
  it.each(CYCLES)('$code scope file exists', ({ scopeFile }) => {
    const p = path.resolve(COMPOSABLES, scopeFile)
    expect(fs.existsSync(p), `${scopeFile} 不存在`).toBe(true)
  })
})

describe('Property 9: forbidden codes not in source', () => {
  it.each(CYCLES.filter((c) => c.forbiddenCodes.length > 0))(
    '$code: host and tab source must not contain forbidden codes',
    ({ code, forbiddenCodes, hostFile, tabFile }) => {
      for (const file of [hostFile, tabFile]) {
        const fullPath = path.resolve(WORKPAPER, file)
        if (!fs.existsSync(fullPath)) continue
        const src = stripComments(fs.readFileSync(fullPath, 'utf-8'))
        for (const bad of forbiddenCodes) {
          // Match as string literal (quoted code used as account identifier)
          const patterns = [`'${bad}'`, `"${bad}"`, `\`${bad}\``]
          for (const pat of patterns) {
            expect(src).not.toContain(pat)
          }
        }
      }
    },
  )

  // Reverse self-check: our stripComments actually strips
  it('stripComments removes comments containing forbidden codes', () => {
    const sample = `// 历史写 '2701' 是错误 \n const x = '2801'`
    const stripped = stripComments(sample)
    expect(stripped).not.toContain("'2701'")
    expect(stripped).toContain("'2801'")
  })
})

describe('Property 10: tb_source_codes has consumer', () => {
  it.each(CYCLES)(
    '$code: TabAdjudication accepts tbSourceCodes prop',
    ({ tabFile }) => {
      const fullPath = path.resolve(WORKPAPER, tabFile)
      if (!fs.existsSync(fullPath)) return
      const src = fs.readFileSync(fullPath, 'utf-8')
      expect(src).toMatch(/tbSourceCodes/)
    },
  )

  it.each(CYCLES)(
    '$code: host passes :tb-source-codes to TabAdjudication',
    ({ code, hostFile }) => {
      const fullPath = path.resolve(WORKPAPER, hostFile)
      if (!fs.existsSync(fullPath)) return
      const src = fs.readFileSync(fullPath, 'utf-8')
      expect(src).toMatch(/:tb-source-codes/)
    },
  )
})

describe('K5 specific: no 2701 in writebackTB path', () => {
  it('useK5FormData does not write 2701 to trial_balance', () => {
    const src = stripComments(read('composables/useK5FormData.ts'))
    // Must not contain 2701 as a string literal used for account_code
    expect(src).not.toMatch(/account_code.*['"]2701['"]/)
    expect(src).not.toMatch(/['"]2701['"].*account/)
    // Must use k5AccountCode function
    expect(src).toMatch(/k5AccountCode/)
  })
})
