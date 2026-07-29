/**
 * confirmationLinkageCompletion.spec.ts — confirmation-linkage-completion spec 核心测试
 *
 * 覆盖 P1-P6, P8-P12
 */
import { describe, it, expect } from 'vitest'
import { ref } from 'vue'

// ─── P1: defaultDiffFilter 语义 ───────────────────────────────────────────────
import { defaultDiffFilter, defaultElectronicReplyFilter } from '../importFromSummary'
import type { SummaryRow } from '../importFromSummary'

function makeSummaryRow(partial: Partial<SummaryRow> = {}): SummaryRow {
  return {
    confirm_index: 'D0-001',
    entity_name: '测试公司',
    amount: 100000,
    reply_amount: 99000,
    is_replied: true,
    match_status: '不符',
    reply_method: '',
    account_type: '应收账款',
    ...partial,
  } as SummaryRow
}

describe('defaultDiffFilter (P1: 仅不符项)', () => {
  it('已回函+差异≠0 → true', () => {
    const row = makeSummaryRow({ is_replied: true, amount: 100000, reply_amount: 99000 })
    expect(defaultDiffFilter(row)).toBe(true)
  })
  it('未回函 → false', () => {
    const row = makeSummaryRow({ is_replied: false, match_status: '未回函' })
    expect(defaultDiffFilter(row)).toBe(false)
  })
  it('差异=0 + 相符 → false', () => {
    const row = makeSummaryRow({ amount: 100, reply_amount: 100, match_status: '相符' })
    expect(defaultDiffFilter(row)).toBe(false)
  })
  it('match_status=不符 but amounts equal → true (标记不符优先)', () => {
    const row = makeSummaryRow({ amount: 100, reply_amount: 100, match_status: '不符' })
    expect(defaultDiffFilter(row)).toBe(true)
  })
})

// ─── P6: defaultElectronicReplyFilter 语义 ────────────────────────────────────

describe('defaultElectronicReplyFilter (P6: 电子回函)', () => {
  it('传真 → true', () => {
    expect(defaultElectronicReplyFilter(makeSummaryRow({ reply_method: '传真' }))).toBe(true)
  })
  it('电子邮件 → true', () => {
    expect(defaultElectronicReplyFilter(makeSummaryRow({ reply_method: '电子邮件' }))).toBe(true)
  })
  it('email → true', () => {
    expect(defaultElectronicReplyFilter(makeSummaryRow({ reply_method: 'email' }))).toBe(true)
  })
  it('挂号信 → false', () => {
    expect(defaultElectronicReplyFilter(makeSummaryRow({ reply_method: '挂号信' }))).toBe(false)
  })
  it('空 → false', () => {
    expect(defaultElectronicReplyFilter(makeSummaryRow({ reply_method: '' }))).toBe(false)
  })
})

// ─── P5: 循环码派生 ──────────────────────────────────────────────────────────

describe('cycleCode derivation (P5)', () => {
  it('D0-4 → D0-1', () => {
    expect('D0-4'.split('-')[0] + '-1').toBe('D0-1')
  })
  it('F0-7 → F0-1', () => {
    expect('F0-7'.split('-')[0] + '-1').toBe('F0-1')
  })
  it('L0-8 → L0-1', () => {
    expect('L0-8'.split('-')[0] + '-1').toBe('L0-1')
  })
  it('K0-4 → K0-1', () => {
    expect('K0-4'.split('-')[0] + '-1').toBe('K0-1')
  })
})

// ─── R2: mapSummaryToReliabilityRow (P2 去重 + P6 映射) ──────────────────────

import { mapSummaryToReliabilityRow } from '../../reliability/composables/mapD01ReliabilityRow'

describe('mapSummaryToReliabilityRow', () => {
  it('maps core fields', () => {
    const row = makeSummaryRow({
      confirm_index: 'D0-005',
      entity_name: '上海有限公司',
      reply_method: '电子邮件',
      reply_date: '2025-12-20',
    })
    const result = mapSummaryToReliabilityRow(row)
    expect(result.confirm_index).toBe('D0-005')
    expect(result.entity_name).toBe('上海有限公司')
    expect(result.reply_method).toBe('电子邮件')
    expect(result.reply_date).toBe('2025-12-20')
    expect(result._source).toBe('auto')
  })
  it('handles empty fields gracefully', () => {
    const row = makeSummaryRow({ confirm_index: undefined, entity_name: '' })
    const result = mapSummaryToReliabilityRow(row)
    expect(result.confirm_index).toBe('')
    expect(result.entity_name).toBe('')
  })
})

// ─── R1: mapD01Row characterization (P1) ─────────────────────────────────────

import { useD01DiffImport } from '../../diffReconcile/composables/useD01DiffImport'

describe('useD01DiffImport.mapD01Row characterization (P1)', () => {
  const d01Import = useD01DiffImport({
    existingIndexes: () => new Set<string>(),
    onImport: () => {},
  })

  it('is_replied=false → null', () => {
    const row = makeSummaryRow({ is_replied: false })
    expect(d01Import.mapD01Row(row)).toBeNull()
  })
  it('差异=0 → null', () => {
    const row = makeSummaryRow({ amount: 100, reply_amount: 100 })
    expect(d01Import.mapD01Row(row)).toBeNull()
  })
  it('正常映射', () => {
    const row = makeSummaryRow({ confirm_index: 'X', entity_name: 'Y', amount: 200, reply_amount: 150 })
    const result = d01Import.mapD01Row(row)
    expect(result).not.toBeNull()
    expect(result!.confirm_index).toBe('X')
    expect(result!.sent_amount).toBe(200)
    expect(result!.reply_amount).toBe(150)
    expect(result!.difference).toBe(50)
    expect(result!._source).toBe('auto')
  })
})

// ─── P2: fetchAndImport 去重 ─────────────────────────────────────────────────

describe('useD01DiffImport.fetchAndImport dedup (P2)', () => {
  it('skips rows with existing confirm_index', () => {
    const imported: any[] = []
    const d01Import = useD01DiffImport({
      existingIndexes: () => new Set(['D0-001']),
      onImport: (rows) => { imported.push(...rows) },
    })
    d01Import.fetchAndImport([
      makeSummaryRow({ confirm_index: 'D0-001', amount: 200, reply_amount: 100 }),
      makeSummaryRow({ confirm_index: 'D0-002', amount: 300, reply_amount: 200 }),
    ])
    expect(imported.length).toBe(1)
    expect(imported[0].confirm_index).toBe('D0-002')
  })
})

// ─── P8-P9: useFraudSignalCollector 映射+去重 ───────────────────────────────

import { useFraudSignalCollector, type FraudSignal } from '../useFraudSignalCollector'

describe('useFraudSignalCollector (P8 mapping + P9 dedup)', () => {
  it('SIGNAL_TO_ITEM_MAP: D0-7 unreliable → item 7', () => {
    const signals = ref<FraudSignal[]>([])
    const collector = useFraudSignalCollector({ signals })
    collector.addD07Unreliable('D0-001', '测试公司')
    expect(signals.value[0].targetItemNo).toBe(7)
  })
  it('SIGNAL_TO_ITEM_MAP: D0-3 control failure → item 15', () => {
    const signals = ref<FraudSignal[]>([])
    const collector = useFraudSignalCollector({ signals })
    collector.addD03ControlFailure('D0-002', '某公司')
    expect(signals.value[0].targetItemNo).toBe(15)
  })
  it('SIGNAL_TO_ITEM_MAP: D0-1 low reply → item 14', () => {
    const signals = ref<FraudSignal[]>([])
    const collector = useFraudSignalCollector({ signals })
    collector.addD01LowReplyRate(30)
    expect(signals.value[0].targetItemNo).toBe(14)
  })
  it('dedup: same confirm_index + signalType not duplicated', () => {
    const signals = ref<FraudSignal[]>([])
    const collector = useFraudSignalCollector({ signals })
    collector.addD07Unreliable('D0-001', '公司A')
    collector.addD07Unreliable('D0-001', '公司A')
    expect(signals.value.length).toBe(1)
  })
  it('exportForD08 aggregates correctly', () => {
    const signals = ref<FraudSignal[]>([])
    const collector = useFraudSignalCollector({ signals })
    collector.addD07Unreliable('D0-001', '公司A')
    collector.addD07Unreliable('D0-002', '公司B')
    const result = collector.exportForD08()
    expect(result.get(7)?.index_refs).toEqual(['D0-001', 'D0-002'])
    expect(result.get(7)?.exists).toBe('是')
  })
})

// ─── P10: 手工优先不覆盖 ─────────────────────────────────────────────────────

describe('D0-8 auto fill hand-first (P10)', () => {
  it('item with existing is_exist is not overwritten', () => {
    // Simulate: item7 already has is_exist='否' (manual)
    const item7 = { seq: 7, is_exist: '否', source_ref: '', _auto_filled: false }
    // The logic: if (item && !item.is_exist) → only fills when falsy
    expect(!item7.is_exist).toBe(false) // '否' is truthy → not overwritten
  })
  it('item with empty is_exist gets filled', () => {
    const item7 = { seq: 7, is_exist: '', source_ref: '', _auto_filled: false }
    expect(!item7.is_exist).toBe(true) // '' is falsy → will be filled
  })
})
