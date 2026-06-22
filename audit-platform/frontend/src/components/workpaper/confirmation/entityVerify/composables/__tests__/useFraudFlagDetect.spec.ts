/**
 * useFraudFlagDetect.spec.ts — 反舞弊检测 composable 测试
 */
import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import type { EntityVerifyRow } from '../../entityVerifyTypes'
import {
  useFraudFlagDetect,
  CONSISTENCY_RULES,
  normalizeAddress,
  areAdjacent,
} from '../useFraudFlagDetect'

function makeRow(overrides: Partial<EntityVerifyRow> = {}): EntityVerifyRow {
  return {
    _row_id: overrides._row_id ?? `row-${Math.random().toString(36).slice(2, 8)}`,
    seq: 1,
    entity_name: '测试公司',
    entity_address: '北京市朝阳区',
    contact_phone: '13800138001',
    ...overrides,
  }
}

describe('useFraudFlagDetect', () => {
  describe('checkRowConsistency — 5 consistency rules', () => {
    it('detects name_mismatch when name_match is inconsistent', () => {
      const rows = ref<EntityVerifyRow[]>([])
      const { checkRowConsistency } = useFraudFlagDetect(rows)
      const row = makeRow({ name_match: 'inconsistent' })
      const flags = checkRowConsistency(row)
      expect(flags).toContain('name_mismatch')
    })

    it('detects address_mismatch when address_match is inconsistent', () => {
      const rows = ref<EntityVerifyRow[]>([])
      const { checkRowConsistency } = useFraudFlagDetect(rows)
      const row = makeRow({ address_match: 'inconsistent' })
      const flags = checkRowConsistency(row)
      expect(flags).toContain('address_mismatch')
    })

    it('detects contact_mismatch when contact_match is inconsistent', () => {
      const rows = ref<EntityVerifyRow[]>([])
      const { checkRowConsistency } = useFraudFlagDetect(rows)
      const row = makeRow({ contact_match: 'inconsistent' })
      const flags = checkRowConsistency(row)
      expect(flags).toContain('contact_mismatch')
    })

    it('detects phone_mismatch when phone_match is inconsistent', () => {
      const rows = ref<EntityVerifyRow[]>([])
      const { checkRowConsistency } = useFraudFlagDetect(rows)
      const row = makeRow({ phone_match: 'inconsistent' })
      const flags = checkRowConsistency(row)
      expect(flags).toContain('phone_mismatch')
    })

    it('detects unreasonable_return when reason_reasonable is 不合理', () => {
      const rows = ref<EntityVerifyRow[]>([])
      const { checkRowConsistency } = useFraudFlagDetect(rows)
      const row = makeRow({ reason_reasonable: '不合理' })
      const flags = checkRowConsistency(row)
      expect(flags).toContain('unreasonable_return')
    })

    it('fires multiple rules simultaneously', () => {
      const rows = ref<EntityVerifyRow[]>([])
      const { checkRowConsistency } = useFraudFlagDetect(rows)
      const row = makeRow({
        name_match: 'inconsistent',
        address_match: 'inconsistent',
        reason_reasonable: '不合理',
      })
      const flags = checkRowConsistency(row)
      expect(flags).toHaveLength(3)
      expect(flags).toContain('name_mismatch')
      expect(flags).toContain('address_mismatch')
      expect(flags).toContain('unreasonable_return')
    })
  })

  describe('missing fields → no flag', () => {
    it('returns empty flags when match fields are undefined', () => {
      const rows = ref<EntityVerifyRow[]>([])
      const { checkRowConsistency } = useFraudFlagDetect(rows)
      const row = makeRow({}) // no match fields set
      const flags = checkRowConsistency(row)
      expect(flags).toHaveLength(0)
    })

    it('returns empty flags when match fields are pending', () => {
      const rows = ref<EntityVerifyRow[]>([])
      const { checkRowConsistency } = useFraudFlagDetect(rows)
      const row = makeRow({
        name_match: 'pending',
        address_match: 'pending',
        contact_match: 'pending',
        phone_match: 'pending',
      })
      const flags = checkRowConsistency(row)
      expect(flags).toHaveLength(0)
    })

    it('returns empty flags when match fields are consistent', () => {
      const rows = ref<EntityVerifyRow[]>([])
      const { checkRowConsistency } = useFraudFlagDetect(rows)
      const row = makeRow({
        name_match: 'consistent',
        address_match: 'consistent',
        contact_match: 'consistent',
        phone_match: 'consistent',
        reason_reasonable: '合理',
      })
      const flags = checkRowConsistency(row)
      expect(flags).toHaveLength(0)
    })
  })

  describe('_overridden → preserved', () => {
    it('preserves existing fraud_flags when _overridden is true', () => {
      const rows = ref<EntityVerifyRow[]>([])
      const { checkRowConsistency } = useFraudFlagDetect(rows)
      const row = makeRow({
        _overridden: true,
        fraud_flags: ['manual_flag_1', 'manual_flag_2'],
        name_match: 'inconsistent', // would normally trigger
      })
      const flags = checkRowConsistency(row)
      expect(flags).toEqual(['manual_flag_1', 'manual_flag_2'])
    })

    it('returns empty array when _overridden and no fraud_flags', () => {
      const rows = ref<EntityVerifyRow[]>([])
      const { checkRowConsistency } = useFraudFlagDetect(rows)
      const row = makeRow({
        _overridden: true,
        name_match: 'inconsistent',
      })
      const flags = checkRowConsistency(row)
      expect(flags).toEqual([])
    })
  })

  describe('detectAddressClustering — 3+ same address', () => {
    it('flags when 3+ rows share normalized address', () => {
      const rows = ref<EntityVerifyRow[]>([
        makeRow({ _row_id: 'r1', entity_address: '北京市 朝阳区 建国路88号' }),
        makeRow({ _row_id: 'r2', entity_address: '北京市朝阳区建国路88号' }),
        makeRow({ _row_id: 'r3', entity_address: '北京市朝阳区 建国路88号' }),
      ])
      const { detectAddressClustering } = useFraudFlagDetect(rows)
      const flags = detectAddressClustering()
      expect(flags).toHaveLength(1)
      expect(flags[0].type).toBe('address_cluster')
      expect(flags[0].affectedRowIds).toHaveLength(3)
    })

    it('does not flag when only 2 rows share address', () => {
      const rows = ref<EntityVerifyRow[]>([
        makeRow({ _row_id: 'r1', entity_address: '上海市浦东新区' }),
        makeRow({ _row_id: 'r2', entity_address: '上海市浦东新区' }),
        makeRow({ _row_id: 'r3', entity_address: '深圳市南山区' }),
      ])
      const { detectAddressClustering } = useFraudFlagDetect(rows)
      const flags = detectAddressClustering()
      expect(flags).toHaveLength(0)
    })

    it('ignores rows with empty address', () => {
      const rows = ref<EntityVerifyRow[]>([
        makeRow({ _row_id: 'r1', entity_address: '' }),
        makeRow({ _row_id: 'r2', entity_address: '' }),
        makeRow({ _row_id: 'r3', entity_address: '' }),
      ])
      const { detectAddressClustering } = useFraudFlagDetect(rows)
      const flags = detectAddressClustering()
      expect(flags).toHaveLength(0)
    })
  })

  describe('detectPhoneAdjacent — phone number adjacency', () => {
    it('detects adjacent phone numbers (last 4 digits differ by ≤2)', () => {
      const rows = ref<EntityVerifyRow[]>([
        makeRow({ _row_id: 'r1', contact_phone: '021-65431001' }),
        makeRow({ _row_id: 'r2', contact_phone: '021-65431003' }),
      ])
      const { detectPhoneAdjacent } = useFraudFlagDetect(rows)
      const flags = detectPhoneAdjacent()
      expect(flags).toHaveLength(1)
      expect(flags[0].type).toBe('phone_adjacent')
      expect(flags[0].affectedRowIds).toEqual(['r1', 'r2'])
    })

    it('does not flag when last 4 digits differ by more than 2', () => {
      const rows = ref<EntityVerifyRow[]>([
        makeRow({ _row_id: 'r1', contact_phone: '13800001000' }),
        makeRow({ _row_id: 'r2', contact_phone: '13800001010' }),
      ])
      const { detectPhoneAdjacent } = useFraudFlagDetect(rows)
      const flags = detectPhoneAdjacent()
      expect(flags).toHaveLength(0)
    })

    it('does not flag identical phone numbers', () => {
      const rows = ref<EntityVerifyRow[]>([
        makeRow({ _row_id: 'r1', contact_phone: '13800001001' }),
        makeRow({ _row_id: 'r2', contact_phone: '13800001001' }),
      ])
      const { detectPhoneAdjacent } = useFraudFlagDetect(rows)
      const flags = detectPhoneAdjacent()
      expect(flags).toHaveLength(0)
    })

    it('ignores short phone numbers', () => {
      const rows = ref<EntityVerifyRow[]>([
        makeRow({ _row_id: 'r1', contact_phone: '12345' }),
        makeRow({ _row_id: 'r2', contact_phone: '12346' }),
      ])
      const { detectPhoneAdjacent } = useFraudFlagDetect(rows)
      const flags = detectPhoneAdjacent()
      expect(flags).toHaveLength(0)
    })
  })

  describe('deriveRowStatus thresholds', () => {
    it('returns ok when no flags and no cross flag', () => {
      const rows = ref<EntityVerifyRow[]>([])
      const { deriveRowStatus } = useFraudFlagDetect(rows)
      expect(deriveRowStatus(0, false)).toBe('ok')
    })

    it('returns suspect when exactly 1 flag', () => {
      const rows = ref<EntityVerifyRow[]>([])
      const { deriveRowStatus } = useFraudFlagDetect(rows)
      expect(deriveRowStatus(1, false)).toBe('suspect')
    })

    it('returns fraud_flag when 2+ flags', () => {
      const rows = ref<EntityVerifyRow[]>([])
      const { deriveRowStatus } = useFraudFlagDetect(rows)
      expect(deriveRowStatus(2, false)).toBe('fraud_flag')
      expect(deriveRowStatus(5, false)).toBe('fraud_flag')
    })

    it('returns fraud_flag when hasCrossFlag regardless of flagCount', () => {
      const rows = ref<EntityVerifyRow[]>([])
      const { deriveRowStatus } = useFraudFlagDetect(rows)
      expect(deriveRowStatus(0, true)).toBe('fraud_flag')
      expect(deriveRowStatus(1, true)).toBe('fraud_flag')
    })
  })

  describe('runScreening integration', () => {
    it('returns combined results', () => {
      const rows = ref<EntityVerifyRow[]>([
        makeRow({
          _row_id: 'r1',
          name_match: 'inconsistent',
          entity_address: '同一地址',
        }),
        makeRow({
          _row_id: 'r2',
          address_match: 'inconsistent',
          phone_match: 'inconsistent',
          entity_address: '同一地址',
        }),
        makeRow({
          _row_id: 'r3',
          entity_address: '同一地址',
        }),
      ])
      const { runScreening } = useFraudFlagDetect(rows)
      const { rowFlags, crossFlags } = runScreening()
      expect(rowFlags.size).toBe(2)
      expect(rowFlags.get('r1')).toEqual(['name_mismatch'])
      expect(rowFlags.get('r2')).toEqual(['address_mismatch', 'phone_mismatch'])
      expect(crossFlags.length).toBeGreaterThanOrEqual(1)
      expect(crossFlags[0].type).toBe('address_cluster')
    })
  })

  describe('helper: normalizeAddress', () => {
    it('removes spaces and parentheses', () => {
      expect(normalizeAddress('北京市 朝阳区（东三环）')).toBe('北京市朝阳区东三环')
    })

    it('returns empty string for undefined', () => {
      expect(normalizeAddress(undefined)).toBe('')
    })
  })

  describe('helper: areAdjacent', () => {
    it('returns true for adjacent numbers', () => {
      expect(areAdjacent('13800001001', '13800001002')).toBe(true)
    })

    it('returns false for same number', () => {
      expect(areAdjacent('13800001001', '13800001001')).toBe(false)
    })

    it('returns false for numbers too far apart', () => {
      expect(areAdjacent('13800001001', '13800001010')).toBe(false)
    })
  })
})
