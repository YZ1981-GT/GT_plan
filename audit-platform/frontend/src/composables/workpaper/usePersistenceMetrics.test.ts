/**
 * wp_persistence_dirty_items 前端开发诊断指标单元测试
 *
 * Task 7.3: 建立 render/save 指标并优化重复调用
 * Requirements: 8.1
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { persistenceMetrics } from './usePersistenceMetrics'

describe('usePersistenceMetrics', () => {
  beforeEach(() => {
    persistenceMetrics.reset()
  })

  it('initial state is all zeros', () => {
    expect(persistenceMetrics.dirtyCount.value).toBe(0)
    expect(persistenceMetrics.saveSuccessCount.value).toBe(0)
    expect(persistenceMetrics.saveErrorCount.value).toBe(0)
    expect(persistenceMetrics.conflictCount.value).toBe(0)
  })

  it('trackDirty increments and untrackDirty decrements dirty count', () => {
    persistenceMetrics.trackDirty('item-a')
    persistenceMetrics.trackDirty('item-b')
    expect(persistenceMetrics.dirtyCount.value).toBe(2)

    persistenceMetrics.untrackDirty('item-a')
    expect(persistenceMetrics.dirtyCount.value).toBe(1)

    persistenceMetrics.untrackDirty('item-b')
    expect(persistenceMetrics.dirtyCount.value).toBe(0)
  })

  it('duplicate trackDirty for same item does not double count', () => {
    persistenceMetrics.trackDirty('item-x')
    persistenceMetrics.trackDirty('item-x')
    expect(persistenceMetrics.dirtyCount.value).toBe(1)
  })

  it('recordSaveSuccess increments success counter', () => {
    persistenceMetrics.recordSaveSuccess()
    persistenceMetrics.recordSaveSuccess()
    expect(persistenceMetrics.saveSuccessCount.value).toBe(2)
  })

  it('recordSaveError increments error counter', () => {
    persistenceMetrics.recordSaveError()
    expect(persistenceMetrics.saveErrorCount.value).toBe(1)
  })

  it('recordConflict increments conflict counter', () => {
    persistenceMetrics.recordConflict()
    persistenceMetrics.recordConflict()
    expect(persistenceMetrics.conflictCount.value).toBe(2)
  })

  it('reset clears all counters', () => {
    persistenceMetrics.trackDirty('a')
    persistenceMetrics.recordSaveSuccess()
    persistenceMetrics.recordSaveError()
    persistenceMetrics.recordConflict()

    persistenceMetrics.reset()

    expect(persistenceMetrics.dirtyCount.value).toBe(0)
    expect(persistenceMetrics.saveSuccessCount.value).toBe(0)
    expect(persistenceMetrics.saveErrorCount.value).toBe(0)
    expect(persistenceMetrics.conflictCount.value).toBe(0)
  })
})
