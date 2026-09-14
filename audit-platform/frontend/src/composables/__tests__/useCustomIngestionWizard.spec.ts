/**
 * Task 12 — F-SHELL 消费与向导不变量
 */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import {
  assertNoForbiddenShellCopies,
  CUSTOM_INGESTION_FSHELL_CONSUMER,
  CUSTOM_INGESTION_REQUIRED_CAPABILITIES,
  entrySuccessMessage,
  gateFShellForCustomIngestion,
  useCustomIngestionWizard,
} from '@/composables/useCustomIngestionWizard'
import { FSHELL_CONTRACT_VERSION, FSHELL_NON_CAPABILITIES } from '@/shell/formula'

describe('custom ingestion F-SHELL gate', () => {
  it('consumer is compatible with published F-SHELL 1.x', () => {
    const gate = gateFShellForCustomIngestion()
    expect(gate).toEqual({ ok: true })
    expect(FSHELL_CONTRACT_VERSION.startsWith('1.')).toBe(true)
    expect(CUSTOM_INGESTION_FSHELL_CONSUMER).toContain('X12')
  })

  it('required capabilities are published and not forbidden', () => {
    for (const cap of CUSTOM_INGESTION_REQUIRED_CAPABILITIES) {
      expect(FSHELL_NON_CAPABILITIES).not.toContain(cap)
    }
  })

  it('wizard vue does not copy forbidden shell pieces', () => {
    const wizardPath = resolve(
      __dirname,
      '../../views/extension/CustomIngestionWizard.vue',
    )
    const blob = readFileSync(wizardPath, 'utf8')
    expect(assertNoForbiddenShellCopies(blob)).toEqual([])
    // composable may *reference* NON_CAPABILITIES names for the gate; vue template must not embed them
    expect(blob.includes('copy_formula_button')).toBe(false)
  })

  it('upload success does not register host facts; ACTIVE does', () => {
    const w = useCustomIngestionWizard()
    expect(w.fshell.ok).toBe(true)
    w.selectEntry('ingest_excel')
    w.markCandidatePreview()
    expect(w.state.value.staticPreviewOnly).toBe(true)
    expect(w.state.value.hostFactsRegistered).toBe(false)
    expect(entrySuccessMessage('ingest_excel')).toContain('≠')

    w.markActiveAndRegisterHostFacts()
    expect(w.state.value.phase).toBe('active')
    expect(w.state.value.hostFactsRegistered).toBe(true)
  })

  it('capability revocation clears host facts', () => {
    const w = useCustomIngestionWizard()
    w.selectEntry('ingest_excel')
    w.markActiveAndRegisterHostFacts()
    w.revalidateCapabilities(false)
    expect(w.state.value.hostFactsRegistered).toBe(false)
    expect(w.state.value.phase).toBe('blocked')
  })
})
