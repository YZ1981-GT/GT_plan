import { describe, it, expect } from 'vitest'
import { groupNetExposureRows } from '../g12NetExposureGroups'
import type { G12NetExposureRow } from '../useG12NetExposure'

function row(partial: Partial<G12NetExposureRow> & { rowId: string }): G12NetExposureRow {
  return {
    seq: 1,
    hedgeRelationId: '',
    item: '',
    currency: '',
    position1Desc: '',
    position1Amount: '',
    position2Desc: '',
    position2Amount: '',
    netPosition: '',
    netPositionManual: false,
    supportingEvidence: '',
    hedgingInstrument: '',
    indexRef: '',
    ...partial,
  }
}

describe('groupNetExposureRows', () => {
  it('同项目多币种合并为一组', () => {
    const groups = groupNetExposureRows([
      row({ rowId: 'a', item: '外汇净头寸', currency: 'USD', seq: 1 }),
      row({ rowId: 'b', item: '外汇净头寸', currency: 'EUR', seq: 2 }),
    ])
    expect(groups).toHaveLength(1)
    expect(groups[0].rows).toHaveLength(2)
    expect(groups[0].currencies).toEqual(['USD', 'EUR'])
  })

  it('不同项目分组', () => {
    const groups = groupNetExposureRows([
      row({ rowId: 'a', item: '项目A', currency: 'USD' }),
      row({ rowId: 'b', item: '项目B', currency: 'USD' }),
    ])
    expect(groups).toHaveLength(2)
  })

  it('空项目名按 rowId 独立分组', () => {
    const groups = groupNetExposureRows([
      row({ rowId: 'x1', item: '  ', currency: 'USD' }),
      row({ rowId: 'x2', item: '', currency: 'EUR' }),
    ])
    expect(groups).toHaveLength(2)
    expect(groups[0].key).toBe('__row_x1')
  })
})
