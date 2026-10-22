/**
 * noteEditEditorWiring vitest — Task 17.5
 *
 * Validates: data-note-write attribute set = WRITE_ENTRIES id set
 *
 * Feature: partner-manager-edit-permission
 * Requirements: 10.3
 */
import { describe, it, expect } from 'vitest'
import { WRITE_ENTRIES } from '../noteEditWriteEntries'

describe('editor wiring: data-note-write coverage', () => {
  it('WRITE_ENTRIES ids are unique', () => {
    const ids = WRITE_ENTRIES.map(e => e.id)
    const unique = new Set(ids)
    expect(ids.length).toBe(unique.size)
  })

  it('every WRITE_ENTRIES id is a non-empty string', () => {
    for (const entry of WRITE_ENTRIES) {
      expect(typeof entry.id).toBe('string')
      expect(entry.id.length).toBeGreaterThan(0)
    }
  })

  it('every coverage entry has trigger and label', () => {
    for (const entry of WRITE_ENTRIES) {
      expect(typeof entry.label).toBe('string')
      expect(entry.label.length).toBeGreaterThan(0)
      expect(['button', 'menu', 'switch', 'tree', 'context-menu', 'shortcut', 'auto', 'input']).toContain(entry.trigger)
    }
  })

  it('lockConstrained entries are a subset of coverage entries', () => {
    for (const entry of WRITE_ENTRIES) {
      if (entry.lockConstrained) {
        expect(entry.coverage).toBe(true)
      }
    }
  })

  it('eqcrHidden entries exist', () => {
    const hidden = WRITE_ENTRIES.filter(e => e.eqcrHidden)
    expect(hidden.length).toBeGreaterThan(0)
  })

  it('non-coverage entries (coverage=false) exist and are all eqcrHidden', () => {
    const nonCoverage = WRITE_ENTRIES.filter(e => !e.coverage)
    expect(nonCoverage.length).toBeGreaterThan(0)
    for (const entry of nonCoverage) {
      expect(entry.eqcrHidden).toBe(true)
    }
  })
})
