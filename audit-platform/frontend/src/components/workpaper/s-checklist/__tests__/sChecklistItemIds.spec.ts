import { describe, expect, it } from 'vitest'

import { HTML_RENDERER_REGISTRY } from '../../htmlRendererRegistry'
import { sChecklistItemIds } from '../sChecklistItemIds'

const EXPECTED_ITEM_IDS = {
  's1-regulation-record': 'S1-1-sheet-data',
  's8-adjudication': 'S8-1-sheet-data',
  's9-adjudication': 'S9-1-sheet-data',
  's9-internal-control': 'S9-2-sheet-data',
  's9-legal-regulations': null,
  's9-program-description': null,
  's10-adjudication': 'S10-1-sheet-data',
  's10-internal-control': 'S10-2-sheet-data',
  's10-environmental-regulations': null,
  's17-nonrecurring-detail': 'S17-1-sheet-data',
  's17-reconciliation': 'S17-11-sheet-data',
  's17-tax-impact': 'S17-21-sheet-data',
} as const

describe('D3.2 S checklist item identity map', () => {
  it('keeps the 12-type item map exact', () => {
    expect(sChecklistItemIds).toEqual(EXPECTED_ITEM_IDS)
    expect(Object.keys(sChecklistItemIds)).toHaveLength(12)
  })

  it('has a frontend registry entry for every mapped componentType', () => {
    for (const componentType of Object.keys(sChecklistItemIds)) {
      expect(HTML_RENDERER_REGISTRY.has(componentType)).toBe(true)
    }
  })
})
