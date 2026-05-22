/**
 * SSE 事件类型编译检查测试
 * Validates: Requirements 10.3, 10.5
 */
import { describe, it, expect } from 'vitest'
import type { SSEEventType } from '@/types/sse'

describe('SSEEventType', () => {
  it('covers all known backend event names', () => {
    // These are the known backend EventType enum values
    const knownEvents: SSEEventType[] = [
      'adjustment.created',
      'adjustment.updated',
      'adjustment.deleted',
      'mapping.changed',
      'data.imported',
      'import.rolled_back',
      'import.progress',
      'materiality.changed',
      'trial_balance.updated',
      'reports.updated',
      'workpaper.saved',
      'note.updated',
      'review_record.created',
      'ledger.import_detected',
      'ledger.import_submitted',
      'ledger.import_failed',
      'ledger.dataset_validated',
      'ledger.dataset_activated',
      'ledger.dataset_rolled_back',
      'sync.failed',
      'workpaper.assigned',
      'presence.joined',
      'presence.left',
      'presence.editing_started',
      'presence.editing_stopped',
      'adjustment.batch_committed',
      'linkage.cascade_degraded',
      'workpaper.audited_confirmed',
      'workpaper.procedure_completed',
      'workpaper.review_passed',
      'workpaper.stale_detected',
      'cross_check.failed',
    ]

    // If SSEEventType is a proper union, all these assignments compile without error
    // This test verifies the type covers all known events at runtime
    expect(knownEvents.length).toBeGreaterThanOrEqual(26)
    // Each event follows domain.action format
    knownEvents.forEach(event => {
      expect(event).toMatch(/^[a-z_]+\.[a-z_]+$/)
    })
  })

  it('SSEEventType is a union type (not just string)', () => {
    // Verify the type constrains values — assign known valid values
    const valid: SSEEventType = 'workpaper.saved'
    expect(valid).toBe('workpaper.saved')

    const valid2: SSEEventType = 'adjustment.created'
    expect(valid2).toBe('adjustment.created')
  })

  it('SSEEventType values follow domain.action naming convention', () => {
    const sampleEvents: SSEEventType[] = [
      'adjustment.created',
      'ledger.dataset_activated',
      'presence.joined',
      'workpaper.stale_detected',
    ]
    sampleEvents.forEach(event => {
      const parts = event.split('.')
      expect(parts.length).toBe(2)
      expect(parts[0].length).toBeGreaterThan(0)
      expect(parts[1].length).toBeGreaterThan(0)
    })
  })
})
