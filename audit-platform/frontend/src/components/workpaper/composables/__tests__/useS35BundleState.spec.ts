/**
 * useS35BundleState — 单元测试
 *
 * 测试纯函数：buildS35WpIdMap, computeVisibleTabs
 * Spec: .kiro/specs/s35-refinancing-bundle/ Task 3.1
 * Validates: Requirements 6.1, 6.2
 */
import { describe, it, expect } from 'vitest'
import {
  buildS35WpIdMap,
  computeVisibleTabs,
  S35_TAB_DEFS,
  S35_ALL_CODES,
} from '../useS35BundleState'

describe('useS35BundleState', () => {
  describe('buildS35WpIdMap', () => {
    it('should extract S35-* wp_code → wp_id using item.wp_id (not item.id)', () => {
      const items = [
        { wp_code: 'S35-1', wp_id: 'wp-uuid-1', id: 'index-id-1' },
        { wp_code: 'S35-2', wp_id: 'wp-uuid-2', id: 'index-id-2' },
        { wp_code: 'S35-1-1', wp_id: 'wp-uuid-1-1', id: 'index-id-1-1' },
      ]
      const map = buildS35WpIdMap(items)
      expect(map['S35-1']).toBe('wp-uuid-1')
      expect(map['S35-2']).toBe('wp-uuid-2')
      expect(map['S35-1-1']).toBe('wp-uuid-1-1')
      // 🔴 铁律验证：不能用 item.id
      expect(map['S35-1']).not.toBe('index-id-1')
    })

    it('should ignore items where wp_id is null/undefined', () => {
      const items = [
        { wp_code: 'S35-3', wp_id: null, id: 'index-id-3' },
        { wp_code: 'S35-4', wp_id: undefined, id: 'index-id-4' },
        { wp_code: 'S35-5', wp_id: 'wp-uuid-5', id: 'index-id-5' },
      ]
      const map = buildS35WpIdMap(items)
      expect(map['S35-3']).toBeUndefined()
      expect(map['S35-4']).toBeUndefined()
      expect(map['S35-5']).toBe('wp-uuid-5')
    })

    it('should ignore non-S35 wp_codes', () => {
      const items = [
        { wp_code: 'S34-1', wp_id: 'wp-s34', id: 'id-s34' },
        { wp_code: 'A10-1', wp_id: 'wp-a10', id: 'id-a10' },
        { wp_code: 'S35-1', wp_id: 'wp-s35', id: 'id-s35' },
      ]
      const map = buildS35WpIdMap(items)
      expect(Object.keys(map)).toEqual(['S35-1'])
      expect(map['S35-1']).toBe('wp-s35')
    })

    it('should handle all S35 codes including sub-tables', () => {
      const items = S35_ALL_CODES.map((code, i) => ({
        wp_code: code,
        wp_id: `wp-${i}`,
        id: `idx-${i}`,
      }))
      const map = buildS35WpIdMap(items)
      expect(Object.keys(map).sort()).toEqual(S35_ALL_CODES.sort())
    })

    it('should return empty map for empty input', () => {
      expect(buildS35WpIdMap([])).toEqual({})
    })
  })

  describe('computeVisibleTabs', () => {
    it('should return only tabs whose wpCode exists in wpIdMap', () => {
      const wpIdMap = { 'S35-1': 'wp-1', 'S35-3': 'wp-3' }
      const visible = computeVisibleTabs(wpIdMap)
      expect(visible.map(t => t.id)).toEqual(['S35-1', 'S35-3'])
    })

    it('should return all tabs when all wp_ids exist', () => {
      const wpIdMap = {
        'S35-1': 'wp-1',
        'S35-2': 'wp-2',
        'S35-3': 'wp-3',
        'S35-4': 'wp-4',
        'S35-5': 'wp-5',
      }
      const visible = computeVisibleTabs(wpIdMap)
      expect(visible).toHaveLength(5)
      expect(visible.map(t => t.id)).toEqual(['S35-1', 'S35-2', 'S35-3', 'S35-4', 'S35-5'])
    })

    it('should return empty array when wpIdMap is empty', () => {
      const visible = computeVisibleTabs({})
      expect(visible).toEqual([])
    })

    it('should not count sub-table wp_ids as tab visibility', () => {
      // S35-1-1 子表存在不代表 S35-1 Tab 可见（必须 S35-1 自身有 wp_id）
      const wpIdMap = { 'S35-1-1': 'wp-sub' }
      const visible = computeVisibleTabs(wpIdMap)
      expect(visible).toEqual([])
    })

    it('should preserve tab order from S35_TAB_DEFS', () => {
      const wpIdMap = { 'S35-5': 'wp-5', 'S35-1': 'wp-1' }
      const visible = computeVisibleTabs(wpIdMap)
      // S35-1 should come before S35-5 per TAB_DEFS order
      expect(visible[0].id).toBe('S35-1')
      expect(visible[1].id).toBe('S35-5')
    })
  })

  describe('S35_TAB_DEFS', () => {
    it('should have exactly 5 tabs', () => {
      expect(S35_TAB_DEFS).toHaveLength(5)
    })

    it('should have correct sub-sheet mapping', () => {
      const withSubSheets = S35_TAB_DEFS.filter(t => t.subSheets && t.subSheets.length > 0)
      expect(withSubSheets).toHaveLength(3)
      expect(withSubSheets.map(t => t.id)).toEqual(['S35-1', 'S35-2', 'S35-3'])
    })

    it('should have S35-4 and S35-5 without sub-sheets', () => {
      const noSub = S35_TAB_DEFS.filter(t => !t.subSheets)
      expect(noSub.map(t => t.id)).toEqual(['S35-4', 'S35-5'])
    })
  })
})
