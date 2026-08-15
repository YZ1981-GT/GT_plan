import { describe, it, expect } from 'vitest'
import {
  normalizeMovementRow,
  seedMovementFromI22,
  enrichFromI26,
  seedNatureCapitalizedFromI27,
  applyNatureCapitalizedMap,
  defaultNatureRows,
  summarizeMovement,
  recalcMovementEnd,
} from '../i2DisclosureModel'
import {
  buildI2ListedSyncPayloads,
  buildI2SoeSyncPayloads,
  buildI2ListedNatureSubTable,
} from '../i2DisclosureSyncPayload'
import { I2_NOTE_SECTION, isI2DisclosureApplicable } from '../i2NoteSectionMap'

describe('i2DisclosureModel', () => {
  it('滚动期末 = 期初 + 增加 − 减少', () => {
    const row = normalizeMovementRow({
      name: '课题1',
      beginBalance: 100,
      increaseInternal: 50,
      increaseOther: 10,
      decreaseToIntangible: 30,
      decreaseToExpense: 5,
      decreaseOther: 0,
    })
    expect(row.endBalance).toBe(125)
  })

  it('从 I2-2 带入项目滚动', () => {
    const rows = seedMovementFromI22([
      { projectName: '课题1', capBeginAmount: 10, capIncrease: 20, transferToI1: 5, capStartDate: '2024-01-01' },
      { projectName: '合计', capBeginAmount: 99 },
    ])
    expect(rows).toHaveLength(1)
    expect(rows[0].name).toBe('课题1')
    expect(rows[0].increaseInternal).toBe(20)
    expect(rows[0].decreaseToIntangible).toBe(5)
    expect(rows[0].capStartDate).toBe('2024-01-01')
  })

  it('I2-6 补齐资本化时点/依据（修复 #REF!）', () => {
    const { movement, filled } = enrichFromI26(
      [normalizeMovementRow({ name: '课题1', beginBalance: 1 })],
      [],
      [{ projectName: '课题1', capStartDate: '2023-06-01', capBasis: '五条件满足', progress: '80%' }],
    )
    expect(filled).toBeGreaterThan(0)
    expect(movement[0].capStartDate).toBe('2023-06-01')
    expect(movement[0].capBasis).toBe('五条件满足')
  })

  it('I2-6 项目名模糊匹配（空格/大小写）', () => {
    const { movement, filled, fuzzyMatched, unmatched } = enrichFromI26(
      [normalizeMovementRow({ name: '课题 1', beginBalance: 1 })],
      [],
      [{ projectName: '课题1', capStartDate: '2023-06-01', capBasis: '五条件' }],
    )
    expect(filled).toBeGreaterThan(0)
    expect(movement[0].capStartDate).toBe('2023-06-01')
    expect(fuzzyMatched.length).toBeGreaterThan(0)
    expect(unmatched).toEqual([])
  })

  it('I2-6 无法匹配时返回 unmatched', () => {
    const { unmatched } = enrichFromI26(
      [normalizeMovementRow({ name: '未知项目', beginBalance: 1 })],
      [],
      [{ projectName: '课题1', capStartDate: '2023-06-01' }],
    )
    expect(unmatched).toContain('未知项目')
  })

  it('I2-7 材料/人工映射到性质表资本化列', () => {
    const cmap = seedNatureCapitalizedFromI27([
      { increase: { material: 100, labor: 50, depreciation: 20, energy: 0, outsource: 0, other: 0 } },
    ])
    const rows = applyNatureCapitalizedMap(defaultNatureRows(), cmap)
    expect(rows.find((r) => r.name === '材料费')?.currentCapitalized).toBe(100)
    expect(rows.find((r) => r.name === '人工费')?.currentCapitalized).toBe(50)
  })
})

describe('i2DisclosureSyncPayload', () => {
  it('上市同步目标五、27', () => {
    const payloads = buildI2ListedSyncPayloads('wp-i2', ['listed_standalone'], {
      natureRows: defaultNatureRows().map((r) => ({ ...r, currentCapitalized: r.name === '材料费' ? 100 : 0 })),
      movementRows: [normalizeMovementRow({ name: '课题1', beginBalance: 10, increaseInternal: 20 })],
      importantRows: [],
      impairmentRows: [],
      noteText: '测试说明',
      noteCap: '',
      noteImpairTest: '',
      notePurchased: '',
    })
    expect(payloads).toHaveLength(1)
    expect(payloads[0].section_id).toBe(I2_NOTE_SECTION.listed)
    expect(payloads[0].sub_table_data['开发支出']?.length).toBeGreaterThan(0)
    expect(payloads[0].sub_table_data._note_texts).toBeTruthy()
  })

  it('国企同步目标八、28', () => {
    const payloads = buildI2SoeSyncPayloads('wp-i2', ['soe_standalone'], {
      movementRows: [normalizeMovementRow({ name: '数据资源', beginBalance: 5, increaseInternal: 3 })],
      noteText: '国企说明',
    })
    expect(payloads).toHaveLength(1)
    expect(payloads[0].section_id).toBe('八、28')
  })

  it('上市标准下国企 payload 为空', () => {
    expect(isI2DisclosureApplicable('soe', ['listed_standalone'])).toBe(false)
    expect(buildI2SoeSyncPayloads('wp', ['listed_standalone'], { movementRows: [], noteText: '' })).toEqual([])
  })

  it('性质子表含合计行', () => {
    const rows = buildI2ListedNatureSubTable([
      { rowId: '1', name: '人工费', currentExpensed: 10, currentCapitalized: 20, priorExpensed: 0, priorCapitalized: 0 },
    ])
    expect(rows.at(-1)?.label).toBe('合计')
    // 行字段名对齐 I2_NATURE_COLUMNS[].key（模板 §五、27 同构），投影器按 key 取值
    expect(rows.at(-1)?.['cur_capitalize']).toBe(20)
  })

  it('summarizeMovement 与 recalc 一致', () => {
    const row = normalizeMovementRow({ name: 'A', beginBalance: 100, increaseInternal: 50, decreaseToIntangible: 20 })
    recalcMovementEnd(row)
    const s = summarizeMovement([row])
    expect(s.end).toBe(130)
  })
})
