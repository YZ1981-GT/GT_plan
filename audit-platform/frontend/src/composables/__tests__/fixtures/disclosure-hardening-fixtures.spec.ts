/**
 * Trivial import verification for disclosure-hardening-fixtures.
 * Ensures the fixture module is correctly importable and exports expected shapes.
 */
import { describe, expect, it } from 'vitest'
import {
  createCapabilityResponse,
  createCellWithAddrId,
  createCellWithManual,
  createCellWithProvenance,
  createCellWithTrace,
  createMockSessionStorage,
  createReactiveContext,
  useFakeTimers,
} from './disclosure-hardening-fixtures'

describe('disclosure-hardening-fixtures import verification', () => {
  it('createMockSessionStorage returns functional mock', () => {
    const storage = createMockSessionStorage()
    storage.setItem('key', 'value')
    expect(storage.getItem('key')).toBe('value')
    expect(storage.length).toBe(1)
    storage.removeItem('key')
    expect(storage.getItem('key')).toBeNull()
    expect(storage.length).toBe(0)
  })

  it('useFakeTimers provides advanceByMs and restore', () => {
    const timers = useFakeTimers()
    expect(typeof timers.advanceByMs).toBe('function')
    expect(typeof timers.restore).toBe('function')
    timers.restore()
  })

  it('createReactiveContext creates refs with defaults and overrides', () => {
    const ctx = createReactiveContext({ project_id: 'p1', year: 2025, section: 's1' })
    expect(ctx.project_id.value).toBe('p1')
    expect(ctx.year.value).toBe(2025)
    expect(ctx.section.value).toBe('s1')
    const snapshot = ctx.toContext()
    expect(snapshot).toEqual({ project_id: 'p1', year: 2025, section: 's1' })
  })

  it('createCellWithManual creates cell with manual flag', () => {
    const cell = createCellWithManual(42, true)
    expect(cell).toEqual({ value: 42, manual: true })
  })

  it('createCellWithProvenance creates cell with provenance array', () => {
    const prov = [{ source: 'query', id: 'q1' }]
    const cell = createCellWithProvenance('hello', prov)
    expect(cell.provenance).toEqual(prov)
    expect(cell.manual).toBe(false)
  })

  it('createCellWithTrace creates cell with trace array', () => {
    const trace = [{ step: 1 }, { step: 2 }]
    const cell = createCellWithTrace(100, trace)
    expect(cell.trace).toEqual(trace)
    expect(cell.manual).toBe(false)
  })

  it('createCellWithAddrId creates cell with addr_id', () => {
    const cell = createCellWithAddrId('val', 'D2/D2-2/E10')
    expect(cell.addr_id).toBe('D2/D2-2/E10')
    expect(cell.manual).toBe(false)
  })

  it('createCapabilityResponse defaults historical_upload=false', () => {
    const resp = createCapabilityResponse()
    expect(resp.historical_upload).toBe(false)
    expect(resp.advanced_query).toBe(true)
    expect(resp.disclosure_writeback).toBe(true)
    expect(resp.historical_upload_reason).toContain('Word/PDF')
  })

  it('createCapabilityResponse accepts overrides', () => {
    const resp = createCapabilityResponse({ historical_upload: true })
    expect(resp.historical_upload).toBe(true)
  })
})
