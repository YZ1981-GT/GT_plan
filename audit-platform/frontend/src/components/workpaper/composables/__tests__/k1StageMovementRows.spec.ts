/**
 * k1StageMovementRows 单测：源模板行集重建 + 历史迁移.
 *
 * spec: .kiro/specs/k1-extraction-chain-and-note-alignment/
 * Requirements 5.1~5.6, 6.5 / Properties 4, 5
 */
import { describe, it, expect } from 'vitest'
import {
  buildK1ProvisionMovementRows,
  buildK1BalanceMovementRows,
  migrateK1MovementRows,
} from '../k1StageMovementRows'

describe('buildK1ProvisionMovementRows — 源模板 12 行', () => {
  it('listed 变体：标签序列逐字对齐源模板（上市口径）', () => {
    const rows = buildK1ProvisionMovementRows('listed')
    expect(rows.map((r) => r.label)).toEqual([
      '上年年末余额',
      '上年年末余额在本期',
      '--转入第二阶段',
      '--转入第三阶段',
      '--转回第二阶段',
      '--转回第一阶段',
      '本期计提',
      '本期转回',
      '本期转销',
      '本期核销',
      '其他变动',
      '期末余额',
    ])
  })

  it('soe 变体：首两行改期初口径 + 全角破折号', () => {
    const rows = buildK1ProvisionMovementRows('soe')
    expect(rows[0].label).toBe('期初余额')
    expect(rows[1].label).toBe('期初余额在本期')
    expect(rows[2].label).toBe('—转入第二阶段')
  })

  it('无重复行标签', () => {
    for (const variant of ['listed', 'soe'] as const) {
      const labels = buildK1ProvisionMovementRows(variant).map((r) => r.label)
      expect(new Set(labels).size).toBe(labels.length)
    }
  })

  it('行数恰为 12（源模板行数）', () => {
    expect(buildK1ProvisionMovementRows('listed')).toHaveLength(12)
  })

  it('含「本期转销」行（F8-8 勾稽依赖它）', () => {
    const rows = buildK1ProvisionMovementRows('listed')
    expect(rows.some((r) => r.key === 'writeOffTransfer' && r.label === '本期转销')).toBe(true)
  })

  it('opening/openingInPeriod/closing 不可编辑，其余可编辑', () => {
    const rows = buildK1ProvisionMovementRows('listed')
    const nonEditable = rows.filter((r) => !r.editable).map((r) => r.key)
    expect(nonEditable.sort()).toEqual(['closing', 'openingInPeriod'])
  })
})

describe('buildK1BalanceMovementRows — 源模板 10 行', () => {
  it('标签序列逐字对齐源模板（国企账面余额变动）', () => {
    const rows = buildK1BalanceMovementRows()
    expect(rows.map((r) => r.label)).toEqual([
      '期初余额',
      '期初余额在本期',
      '—转入第二阶段',
      '—转入第三阶段',
      '—转回第二阶段',
      '—转回第一阶段',
      '本期新增',
      '本期终止确认',
      '其他变动',
      '期末余额',
    ])
  })

  it('无重复行标签（原实现两对重复已修）', () => {
    const labels = buildK1BalanceMovementRows().map((r) => r.label)
    expect(new Set(labels).size).toBe(labels.length)
  })

  it('行数恰为 10', () => {
    expect(buildK1BalanceMovementRows()).toHaveLength(10)
  })
})

describe('migrateK1MovementRows — Property 5：迁移金额守恒', () => {
  it('旧 13 行 provision 形态迁移后阶段列总额守恒', () => {
    const legacy = [
      { key: 'opening', label: '期初余额', stage1: 100, stage2: 10, stage3: 1, editable: true },
      { key: 's1-s2', label: '第一阶段→第二阶段', stage1: -20, stage2: 20, stage3: 0, editable: true },
      { key: 's1-s3', label: '第一阶段→第三阶段', stage1: -5, stage2: 0, stage3: 5, editable: true },
      { key: 's2-s3', label: '第二阶段→第三阶段', stage1: 0, stage2: -3, stage3: 3, editable: true },
      { key: 's2-s1', label: '第二阶段→第一阶段', stage1: 2, stage2: -2, stage3: 0, editable: true },
      { key: 's3-s1', label: '第三阶段→第一阶段', stage1: 1, stage2: 0, stage3: -1, editable: true },
      { key: 's3-s2', label: '第三阶段→第二阶段', stage1: 0, stage2: 1, stage3: -1, editable: true },
      { key: 'provision', label: '本年计提', stage1: 50, stage2: 5, stage3: 0, editable: true },
      { key: 'reversal', label: '本年转回', stage1: -10, stage2: 0, stage3: 0, editable: true },
      { key: 'writeoff', label: '本年核销', stage1: 0, stage2: -2, stage3: 0, editable: true },
      { key: 'fx', label: '汇兑差异', stage1: 1, stage2: 0, stage3: 0, editable: true },
      { key: 'other', label: '其他', stage1: 0, stage2: 1, stage3: 0, editable: true },
      { key: 'closing', label: '期末余额', stage1: 0, stage2: 0, stage3: 0, editable: false },
    ]
    const sumBefore = (field: 'stage1' | 'stage2' | 'stage3') =>
      legacy.filter((r) => r.key !== 'closing').reduce((s, r) => s + (r as any)[field], 0)

    const migrated = migrateK1MovementRows(legacy, 'provision', 'listed')
    const sumAfter = (field: 'stage1' | 'stage2' | 'stage3') =>
      migrated.filter((r) => r.key !== 'closing').reduce((s, r) => s + (r as any)[field], 0)

    expect(sumAfter('stage1')).toBeCloseTo(sumBefore('stage1'), 2)
    expect(sumAfter('stage2')).toBeCloseTo(sumBefore('stage2'), 2)
    expect(sumAfter('stage3')).toBeCloseTo(sumBefore('stage3'), 2)
    expect(migrated).toHaveLength(12)
  })

  it('折叠：s1-s3 + s2-s3 金额求和进 to3', () => {
    const legacy = [
      { key: 's1-s3', label: '', stage1: -3, stage2: 0, stage3: 3, editable: true },
      { key: 's2-s3', label: '', stage1: 0, stage2: -4, stage3: 4, editable: true },
    ]
    const migrated = migrateK1MovementRows(legacy, 'provision', 'listed')
    const to3 = migrated.find((r) => r.key === 'to3')!
    expect(to3.stage1).toBe(-3)
    expect(to3.stage2).toBe(-4)
    expect(to3.stage3).toBe(7)
  })

  it('折叠：s2-s1 + s3-s1 金额求和进 back1', () => {
    const legacy = [
      { key: 's2-s1', label: '', stage1: 2, stage2: -2, stage3: 0, editable: true },
      { key: 's3-s1', label: '', stage1: 1, stage2: 0, stage3: -1, editable: true },
    ]
    const migrated = migrateK1MovementRows(legacy, 'provision', 'listed')
    const back1 = migrated.find((r) => r.key === 'back1')!
    expect(back1.stage1).toBe(3)
    expect(back1.stage2).toBe(-2)
    expect(back1.stage3).toBe(-1)
  })

  it('fx + other 金额求和进 other', () => {
    const legacy = [
      { key: 'fx', label: '', stage1: 5, stage2: 0, stage3: 0, editable: true },
      { key: 'other', label: '', stage1: 0, stage2: 3, stage3: 0, editable: true },
    ]
    const migrated = migrateK1MovementRows(legacy, 'provision', 'listed')
    const other = migrated.find((r) => r.key === 'other')!
    expect(other.stage1).toBe(5)
    expect(other.stage2).toBe(3)
  })

  it('旧 11 行 balance 形态迁移后行数为 10 且金额守恒', () => {
    const legacy = [
      { key: 'opening', label: '', stage1: 10, stage2: 0, stage3: 0, editable: false },
      { key: 's1-s2', label: '', stage1: -5, stage2: 5, stage3: 0, editable: false },
      { key: 's1-s3', label: '', stage1: 0, stage2: 0, stage3: 0, editable: false },
      { key: 's2-s1', label: '', stage1: 0, stage2: 0, stage3: 0, editable: false },
      { key: 's2-s3', label: '', stage1: 0, stage2: -2, stage3: 2, editable: false },
      { key: 's3-s1', label: '', stage1: 0, stage2: 0, stage3: 0, editable: false },
      { key: 's3-s2', label: '', stage1: 0, stage2: 0, stage3: 0, editable: false },
      { key: 'addition', label: '', stage1: 3, stage2: 0, stage3: 0, editable: true },
      { key: 'collection', label: '', stage1: -1, stage2: 0, stage3: 0, editable: true },
      { key: 'other', label: '', stage1: 0, stage2: 0, stage3: 0, editable: true },
      { key: 'closing', label: '', stage1: 0, stage2: 0, stage3: 0, editable: false },
    ]
    const sumBefore = legacy
      .filter((r) => r.key !== 'closing')
      .reduce((s, r) => s + r.stage1 + r.stage2 + r.stage3, 0)
    const migrated = migrateK1MovementRows(legacy, 'balance')
    const sumAfter = migrated
      .filter((r) => r.key !== 'closing')
      .reduce((s, r) => s + r.stage1 + r.stage2 + r.stage3, 0)
    expect(migrated).toHaveLength(10)
    expect(sumAfter).toBeCloseTo(sumBefore, 2)
    // collection → derecognition
    expect(migrated.find((r) => r.key === 'derecognition')?.stage1).toBe(-1)
  })

  it('空/缺失输入返回模板（无迁移）', () => {
    expect(migrateK1MovementRows(undefined, 'provision', 'listed')).toHaveLength(12)
    expect(migrateK1MovementRows([], 'balance')).toHaveLength(10)
  })

  it('已是新行集时幂等（key 已对齐，金额原样保留）', () => {
    const already = buildK1ProvisionMovementRows('soe').map((r) => ({ ...r, stage1: 9 }))
    const migrated = migrateK1MovementRows(already, 'provision', 'soe')
    expect(migrated.every((r) => r.stage1 === 9)).toBe(true)
    expect(migrated.map((r) => r.label)).toEqual(already.map((r) => r.label))
  })

  it('未知 key 被丢弃但不影响已知 key 求和（防御性）', () => {
    const legacy = [
      { key: 'mystery-key', label: '', stage1: 999, stage2: 999, stage3: 999, editable: true },
      { key: 'opening', label: '', stage1: 5, stage2: 0, stage3: 0, editable: true },
    ]
    const migrated = migrateK1MovementRows(legacy, 'provision', 'listed')
    expect(migrated.find((r) => r.key === 'opening')?.stage1).toBe(5)
  })
})
