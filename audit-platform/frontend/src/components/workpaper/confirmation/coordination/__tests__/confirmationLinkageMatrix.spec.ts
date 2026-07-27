import { describe, it, expect } from 'vitest'
import {
  findLinkageGaps,
  CONFIRMATION_LINKAGE_MATRIX,
  type HubCycleSpec,
  type LinkageCapability,
  type CapabilityState,
} from '../confirmationLinkageMatrix'

describe('confirmationLinkageMatrix', () => {
  describe('findLinkageGaps', () => {
    it('returns empty when all capabilities are implemented', () => {
      const matrix: HubCycleSpec[] = [
        {
          cycle: 'F0',
          summarySheet: '函证结果汇总表F0-1',
          alternativeSheets: ['预付及采购替代程序F0-5'],
          capabilities: {
            sync_to_center: 'implemented',
            reply_backflow: 'implemented',
            unreplied_pull: 'implemented',
            center_entry: 'implemented',
          },
        },
      ]
      expect(findLinkageGaps(matrix)).toEqual([])
    })

    it('lists stub capabilities as gaps', () => {
      const matrix: HubCycleSpec[] = [
        {
          cycle: 'F0',
          summarySheet: '函证结果汇总表F0-1',
          alternativeSheets: ['预付及采购替代程序F0-5'],
          capabilities: {
            sync_to_center: 'implemented',
            reply_backflow: 'implemented',
            unreplied_pull: 'stub',
            center_entry: 'implemented',
          },
        },
      ]
      const gaps = findLinkageGaps(matrix)
      expect(gaps).toHaveLength(1)
      expect(gaps[0]).toEqual({ cycle: 'F0', capability: 'unreplied_pull', state: 'stub' })
    })

    it('lists missing capabilities as gaps', () => {
      const matrix: HubCycleSpec[] = [
        {
          cycle: 'K0',
          summarySheet: '函证结果汇总表K0-1',
          alternativeSheets: ['其他应收款替代程序K0-5'],
          capabilities: {
            sync_to_center: 'implemented',
            reply_backflow: 'implemented',
            unreplied_pull: 'missing',
            center_entry: 'implemented',
          },
        },
      ]
      const gaps = findLinkageGaps(matrix)
      expect(gaps).toHaveLength(1)
      expect(gaps[0].state).toBe('missing')
    })

    it('treats not_applicable without reason as gap', () => {
      const matrix: HubCycleSpec[] = [
        {
          cycle: 'E0',
          summarySheet: '函证结果汇总表E0-1',
          alternativeSheets: [],
          capabilities: {
            sync_to_center: 'implemented',
            reply_backflow: 'implemented',
            unreplied_pull: 'not_applicable',
            center_entry: 'implemented',
          },
          // notApplicableReason missing!
        },
      ]
      const gaps = findLinkageGaps(matrix)
      expect(gaps).toHaveLength(1)
      expect(gaps[0]).toEqual({ cycle: 'E0', capability: 'unreplied_pull', state: 'not_applicable' })
    })

    it('accepts not_applicable with reason as non-gap', () => {
      const matrix: HubCycleSpec[] = [
        {
          cycle: 'E0',
          summarySheet: '函证结果汇总表E0-1',
          alternativeSheets: [],
          capabilities: {
            sync_to_center: 'implemented',
            reply_backflow: 'implemented',
            unreplied_pull: 'not_applicable',
            center_entry: 'implemented',
          },
          notApplicableReason: 'E0 源模板无替代程序 sheet',
        },
      ]
      expect(findLinkageGaps(matrix)).toEqual([])
    })

    it('production matrix has no gaps (spec target state)', () => {
      // This verifies Property 16: Linkage_Matrix 无遗漏
      const gaps = findLinkageGaps(CONFIRMATION_LINKAGE_MATRIX)
      expect(gaps).toEqual([])
    })
  })

  describe('route contract (Property 2)', () => {
    it('confirmation-hub is in HTML_RENDERER_ROUTE_SET but not HTML_COMPONENT_TYPE_SET', async () => {
      // Dynamic import to get the actual sets from the registry
      const { HTML_RENDERER_ROUTE_SET, HTML_COMPONENT_TYPE_SET } = await import(
        '@/components/workpaper/htmlRendererRegistry'
      )
      expect(HTML_RENDERER_ROUTE_SET.has('confirmation-hub')).toBe(true)
      expect(HTML_COMPONENT_TYPE_SET.has('confirmation-hub')).toBe(false)
    })
  })
})
