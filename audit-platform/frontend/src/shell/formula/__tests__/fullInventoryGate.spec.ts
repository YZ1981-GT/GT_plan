/**
 * Formula-toolbar Task 15 — full inventory gate + F-SHELL archive evidence.
 * Validates: Requirements 13.6, 1.5, 12.5 / Property 22
 */

import { mkdirSync, writeFileSync, readFileSync, existsSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

import {
  buildT15EvidencePayload,
  runFullInventoryGate,
  DENOMINATOR_HOSTS,
} from '@/shell/formula/fullInventoryGate'
import { DOMAIN_OWNED_FORMULA_EXCLUSIONS } from '@/shell/formula'

const SPEC = join(
  __dirname,
  '../../../../../../.kiro/specs/workpaper-page-formula-toolbar-closure',
)
const BASIS = join(SPEC, 'basis')
const EVIDENCE = join(SPEC, 'evidence/F-SHELL')

describe('Task 15: full inventory gate', () => {
  it('adjudicates five hosts, zero forbidden duplicates, pins inventoryDigest', () => {
    const gate = runFullInventoryGate({
      now: new Date('2026-09-09T00:30:00.000Z'),
      runId: 't15-full-inventory-2026-09-09',
    })

    expect(gate.hostAdjudications).toHaveLength(5)
    expect(gate.hostAdjudications.map((h) => h.host)).toEqual([...DENOMINATOR_HOSTS])
    for (const h of gate.hostAdjudications) {
      expect(['reachable', 'exempted']).toContain(h.status)
    }
    expect(gate.duplicates.forbidden, JSON.stringify(gate.duplicates.forbidden)).toEqual([])
    expect(gate.legacy.findings, JSON.stringify(gate.legacy.findings)).toEqual([])
    expect(gate.staleEvidence).toEqual([])
    expect(gate.spellingGuards.workoberKeyTypos).toEqual([])
    expect(gate.browserImportGuards.cryptoStaticImports).toEqual([])
    expect(gate.inventoryDigest).toMatch(/^[a-f0-9]{64}$/)
    expect(gate.fshellEnvelope.inventoryDigest).toBe(gate.inventoryDigest)
    expect(DOMAIN_OWNED_FORMULA_EXCLUSIONS.length).toBeGreaterThanOrEqual(6)
    expect(gate.overall, gate.blockers.join('; ')).toBe('PASS')

    mkdirSync(BASIS, { recursive: true })
    mkdirSync(EVIDENCE, { recursive: true })
    const payload = buildT15EvidencePayload(gate)
    writeFileSync(join(BASIS, 'T15-full-inventory-run.json'), JSON.stringify(payload, null, 2), 'utf8')
    writeFileSync(join(EVIDENCE, 'envelope.json'), JSON.stringify(gate.fshellEnvelope, null, 2), 'utf8')

    const index = buildIndexMarkdown(gate, payload)
    writeFileSync(join(EVIDENCE, 'INDEX.md'), index, 'utf8')

    const tracked = [
      'basis/T15-full-inventory-run.json',
      'basis/T15-grid-host-exemption.json',
      'basis/T14-playwright/host-matrix.json',
      'basis/T13-mutation-report.json',
      'evidence/F-SHELL/contract.json',
      'evidence/F-SHELL/envelope.json',
      'evidence/F-SHELL/INDEX.md',
    ]
    writeFileSync(
      join(BASIS, 'T15-tracked-artifacts.json'),
      JSON.stringify(
        {
          recordedAt: gate.generatedAt,
          artifacts: tracked.map((p) => ({
            path: p,
            exists: existsSync(join(SPEC, p)),
          })),
          inventoryDigest: gate.inventoryDigest,
        },
        null,
        2,
      ),
      'utf8',
    )
  })

  it('grid exemption is formal and word exemption is superseded', () => {
    const grid = JSON.parse(readFileSync(join(BASIS, 'T15-grid-host-exemption.json'), 'utf8'))
    expect(grid.host).toBe('grid')
    expect(grid.denominator).toBe(true)
    expect(grid.owner).toBeTruthy()
    expect(grid.expiresAt).toBeTruthy()
    expect(grid.sourceDigest).toBeTruthy()

    const word = JSON.parse(readFileSync(join(BASIS, 'T12-word-host-exemption.json'), 'utf8'))
    expect(word.supersededBy).toBeTruthy()
  })
})

function buildIndexMarkdown(
  gate: ReturnType<typeof runFullInventoryGate>,
  payload: Record<string, unknown>,
): string {
  const hosts = gate.hostAdjudications
    .map((h) => `| ${h.host} | ${h.status} | ${h.wp_code || h.reason || ''} |`)
    .join('\n')
  return `# F-SHELL INDEX

**Overall:** ${gate.overall}  
**inventoryDigest:** \`${gate.inventoryDigest}\`  
**Generated:** ${gate.generatedAt}  
**Producer tasks:** 13 (publish) → 15 (inventory pin / archive gate)

## Host denominator

| Host | Status | Detail |
|---|---|---|
${hosts}

## Counts

| Metric | Value |
|---|---|
| inventory entries | ${gate.inventoryRun.entries.length} |
| domain exclusions | ${gate.inventoryRun.domainExclusions.length} |
| raw duplicate hits | ${gate.duplicates.rawCount} |
| forbidden duplicates | ${gate.duplicates.forbidden.length} |
| legacy findings | ${gate.legacy.findings.length} |
| stale evidence | ${gate.staleEvidence.length} |
| blockers | ${gate.blockers.length} |

## Owners

| Surface | Owner |
|---|---|
| FormulaManagerDialog (workpaper route) | ThreeColumnLayout |
| AI assist | DSH / ThreeColumnLayout |
| AI review | GtWpAiReviewToolbar |
| Guidance rail | WorkpaperCapabilityShell + WpGuidancePanel |
| Human review rail | WorkpaperCapabilityShell (GtWpReviewRail suppressed) |
| Grid host (absent) | T15-grid-host-exemption |

## Blockers

${gate.blockers.length ? gate.blockers.map((b) => `- ${b}`).join('\n') : '_none_'}

## Re-run

\`\`\`bash
cd audit-platform/frontend
npx vitest run src/shell/formula/__tests__/fullInventoryGate.spec.ts src/shell/formula/__tests__/fShellConformance.spec.ts
python ../../backend/scripts/diagnose/mutate_formula_task15_closure.py
SKIP_E2E_SEED=1 npx playwright test e2e/workpaper-formula-toolbar-shell.spec.ts --workers=1
\`\`\`

## Evidence SHA

\`${String((payload as { evidenceSha256?: string }).evidenceSha256 || '')}\`
`
}
