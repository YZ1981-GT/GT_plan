import { describe, expect, it } from 'vitest'
import * as fc from 'fast-check'
import {
  markDisclosureCellManual,
  mergeDisclosureCell,
  mergeQueryIntoDisclosure,
} from '../useManualPreservingMerge'

const scalarArb = fc.oneof(fc.integer(), fc.string(), fc.boolean(), fc.constant(null))
const historyArb = fc.array(fc.record({ id: fc.string({ maxLength: 8 }) }), { maxLength: 6 })

describe('Feature: advanced-query-disclosure-integration-hardening, Property P11', () => {
  it('manual=true 的值不被自动填充覆盖，来源只追加去重且 addr_id 保留', () => {
    fc.assert(fc.property(
      scalarArb,
      scalarArb,
      historyArb,
      historyArb,
      (manualValue, automaticValue, oldHistory, newHistory) => {
        const current = {
          value: manualValue,
          manual: true,
          provenance: oldHistory,
          trace: oldHistory,
          addr_id: 'D2/D2-2/E10',
        }
        const merged = mergeDisclosureCell(current, {
          value: automaticValue,
          manual: false,
          provenance: newHistory,
          trace: newHistory,
          addr_id: 'changed/address',
        })
        expect(merged.value).toEqual(manualValue)
        expect(merged.manual).toBe(true)
        expect(merged.addr_id).toBe(current.addr_id)
        expect(new Set(merged.provenance!.map(JSON.stringify)).size).toBe(merged.provenance!.length)
        oldHistory.forEach((item) => expect(merged.provenance).toContainEqual(item))
        newHistory.forEach((item) => expect(merged.trace).toContainEqual(item))
      },
    ), { numRuns: 40 })
  })

  it('用户编辑将单元格标为 manual 并保留历史元数据', () => {
    const row = {
      row_id: 'r1',
      cells: [{ value: 10, provenance: [{ id: 'source' }], trace: [{ id: 'trace' }], addr_id: 'A/B/C' }],
    }
    const edited = markDisclosureCellManual(row, 0, 99)
    expect(edited.cells[0]).toMatchObject({
      value: 99, manual: true, mode: 'manual', addr_id: 'A/B/C',
    })
    expect(edited.cells[0].provenance).toEqual([{ id: 'source' }])
    expect(edited._cell_modes).toEqual({ '0': 'manual' })
  })
})

describe('Feature: advanced-query-disclosure-integration-hardening, Property P12', () => {
  it('任意自动刷新序列保持 manual/provenance/trace/addr_id 不变量', () => {
    fc.assert(fc.property(
      scalarArb,
      fc.array(fc.record({
        operation: fc.constantFrom('save', 'refresh', 'pagination', 'template', 'reopen'),
        value: scalarArb,
      }), { minLength: 1, maxLength: 12 }),
      (manualValue, operations) => {
        let table: any = {
          rows: [{
            row_id: 'r1',
            values: [manualValue],
            _cell_modes: { '0': 'manual' },
            _cell_meta: { '0': {
              provenance: [{ id: 'original' }],
              trace: [{ id: 'original-trace' }],
              addr_id: 'D2/D2-2/E10',
            } },
          }],
        }
        operations.forEach(({ operation, value }, index) => {
          if (operation === 'save') return
          table = mergeQueryIntoDisclosure(table, {
            rows: [{
              row_id: 'r1',
              values: [value],
              _cell_modes: { '0': 'auto' },
              _cell_meta: { '0': {
                provenance: [{ id: `refresh-${index}` }],
                trace: [{ id: `trace-${index}` }],
                addr_id: `incoming-${index}`,
              } },
            }],
          })
        })
        expect(table.rows[0].values[0]).toEqual(manualValue)
        expect(table.rows[0]._cell_modes['0']).toBe('manual')
        expect(table.rows[0]._cell_meta['0'].addr_id).toBe('D2/D2-2/E10')
        expect(table.rows[0]._cell_meta['0'].provenance).toContainEqual({ id: 'original' })
        expect(table.rows[0]._cell_meta['0'].trace).toContainEqual({ id: 'original-trace' })
      },
    ), { numRuns: 40 })
  })
})
